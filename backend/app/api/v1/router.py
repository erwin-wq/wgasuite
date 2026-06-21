from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_platform_admin
from app.connectors import MockGoogleWorkspaceConnector, list_google_workspace_checks
from app.core.config import get_settings
from app.db.session import get_db
from app.models import (
    Assessment,
    Asset,
    ConnectorConfig,
    Customer,
    CustomerMembership,
    DreadScore,
    Finding,
    Organization,
    ScanRun,
    User,
)
from app.schemas.assessment import AssessmentCreate, AssessmentRead
from app.schemas.asset import AssetCreate, AssetRead
from app.schemas.auth import LoginRequest, TokenResponse, UserRead
from app.schemas.connector_config import (
    ConnectorConfigCreate,
    ConnectorConfigRead,
    ConnectorConfigTestRead,
    ConnectorConfigUpdate,
)
from app.schemas.customer import CustomerCreate, CustomerRead, CustomerUpdate
from app.schemas.customer_membership import (
    CustomerMembershipCreate,
    CustomerMembershipRead,
    CustomerMembershipUpdate,
    UserCustomerMembershipRead,
)
from app.schemas.finding import FindingCreate, FindingRead, FindingUpdate
from app.schemas.google_workspace_check import GoogleWorkspaceCheckRead
from app.schemas.organization import OrganizationCreate, OrganizationRead
from app.schemas.report import AssessmentReportRead, RiskLevelCounts
from app.schemas.scan_run import ScanRunRead
from app.services.dread import calculate_dread_score
from app.services.passwords import verify_password
from app.services.tokens import encode_access_token

api_router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentPlatformAdmin = Annotated[User, Depends(require_platform_admin)]


def get_customer_or_404(db: Session, customer_id: UUID) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )
    return customer


def get_organization_or_404(db: Session, organization_id: UUID) -> Organization:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found.",
        )
    return organization


def get_assessment_or_404(db: Session, assessment_id: UUID) -> Assessment:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found.",
        )
    return assessment


def get_asset_or_404(db: Session, asset_id: UUID) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found.",
        )
    return asset


def get_finding_or_404(db: Session, finding_id: UUID) -> Finding:
    statement = (
        select(Finding).where(Finding.id == finding_id).options(selectinload(Finding.dread_score))
    )
    finding = db.scalar(statement)
    if finding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Finding not found.",
        )
    return finding


def get_scan_run_or_404(db: Session, scan_run_id: UUID) -> ScanRun:
    scan_run = db.get(ScanRun, scan_run_id)
    if scan_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan run not found.",
        )
    return scan_run


def get_connector_config_or_404(db: Session, connector_config_id: UUID) -> ConnectorConfig:
    connector_config = db.get(ConnectorConfig, connector_config_id)
    if connector_config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector config not found.",
        )
    return connector_config


def get_customer_membership_or_404(db: Session, membership_id: UUID) -> CustomerMembership:
    membership = db.get(CustomerMembership, membership_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer membership not found.",
        )
    return membership


def build_user_read(db: Session, user: User) -> UserRead:
    statement = (
        select(CustomerMembership)
        .where(CustomerMembership.user_id == user.id)
        .options(selectinload(CustomerMembership.customer))
        .order_by(CustomerMembership.created_at.desc())
    )
    memberships = [
        UserCustomerMembershipRead(
            customer_id=membership.customer_id,
            customer_name=membership.customer.name,
            role=membership.role,
            is_active=membership.is_active,
        )
        for membership in db.scalars(statement).all()
    ]
    return UserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        customer_memberships=memberships,
    )


def validate_asset_scope(
    db: Session,
    asset_id: UUID | None,
    assessment: Assessment,
) -> Asset | None:
    if asset_id is None:
        return None

    asset = get_asset_or_404(db, asset_id)
    if asset.organization_id != assessment.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Asset must belong to the same organization as the assessment.",
        )
    return asset


def apply_dread_score(score: DreadScore, values: dict[str, int]) -> None:
    for field, value in values.items():
        setattr(score, field, value)

    current_values = {
        "damage": score.damage,
        "reproducibility": score.reproducibility,
        "exploitability": score.exploitability,
        "affected_users": score.affected_users,
        "discoverability": score.discoverability,
    }
    total_score, risk_level = calculate_dread_score(current_values)
    score.total_score = total_score
    score.risk_level = risk_level


def get_or_create_google_workspace_asset(db: Session, assessment: Assessment) -> Asset:
    statement = select(Asset).where(
        Asset.organization_id == assessment.organization_id,
        Asset.name == "Google Workspace Tenant",
    )
    asset = db.scalar(statement)
    if asset is not None:
        return asset

    asset = Asset(
        organization_id=assessment.organization_id,
        name="Google Workspace Tenant",
        asset_type="SaaS Platform",
        identifier="google-workspace-mock",
        description="Demo asset created by the mock Google Workspace scan.",
    )
    db.add(asset)
    db.flush()
    return asset


@api_router.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    access_token = encode_access_token(
        subject=str(user.id),
        secret_key=settings.auth_secret_key,
        expires_minutes=settings.auth_token_expires_minutes,
        extra_claims={"email": user.email, "role": user.role},
    )
    return TokenResponse(access_token=access_token)


@api_router.get("/auth/me", response_model=UserRead, tags=["auth"])
def get_me(current_user: CurrentUser, db: DbSession) -> UserRead:
    return build_user_read(db, current_user)


@api_router.get(
    "/connectors/google-workspace/checks",
    response_model=list[GoogleWorkspaceCheckRead],
    tags=["connectors"],
    dependencies=[Depends(get_current_user)],
)
def list_google_workspace_check_catalog() -> list[dict[str, object]]:
    return [check.as_dict() for check in list_google_workspace_checks()]


@api_router.post(
    "/customers",
    response_model=CustomerRead,
    status_code=status.HTTP_201_CREATED,
    tags=["customers"],
    dependencies=[Depends(get_current_user)],
)
def create_customer(
    payload: CustomerCreate,
    db: DbSession,
) -> Customer:
    existing = db.scalar(select(Customer).where(Customer.slug == payload.slug))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Customer with this slug already exists.",
        )

    customer = Customer(**payload.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@api_router.get(
    "/customers",
    response_model=list[CustomerRead],
    tags=["customers"],
    dependencies=[Depends(get_current_user)],
)
def list_customers(db: DbSession) -> list[Customer]:
    statement = select(Customer).order_by(Customer.created_at.desc())
    return list(db.scalars(statement).all())


@api_router.get(
    "/customers/{customer_id}",
    response_model=CustomerRead,
    tags=["customers"],
    dependencies=[Depends(get_current_user)],
)
def get_customer(customer_id: UUID, db: DbSession) -> Customer:
    return get_customer_or_404(db, customer_id)


@api_router.patch(
    "/customers/{customer_id}",
    response_model=CustomerRead,
    tags=["customers"],
    dependencies=[Depends(get_current_user)],
)
def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    db: DbSession,
) -> Customer:
    customer = get_customer_or_404(db, customer_id)
    update_data = payload.model_dump(exclude_unset=True)

    if "slug" in update_data and update_data["slug"] != customer.slug:
        existing = db.scalar(select(Customer).where(Customer.slug == update_data["slug"]))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Customer with this slug already exists.",
            )

    for field, value in update_data.items():
        setattr(customer, field, value)

    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@api_router.get(
    "/customers/{customer_id}/memberships",
    response_model=list[CustomerMembershipRead],
    tags=["customer-memberships"],
)
def list_customer_memberships(
    customer_id: UUID,
    db: DbSession,
    _current_admin: CurrentPlatformAdmin,
) -> list[CustomerMembership]:
    get_customer_or_404(db, customer_id)
    statement = (
        select(CustomerMembership)
        .where(CustomerMembership.customer_id == customer_id)
        .order_by(CustomerMembership.created_at.desc())
    )
    return list(db.scalars(statement).all())


@api_router.post(
    "/customers/{customer_id}/memberships",
    response_model=CustomerMembershipRead,
    status_code=status.HTTP_201_CREATED,
    tags=["customer-memberships"],
)
def upsert_customer_membership(
    customer_id: UUID,
    payload: CustomerMembershipCreate,
    db: DbSession,
    _current_admin: CurrentPlatformAdmin,
) -> CustomerMembership:
    get_customer_or_404(db, customer_id)
    user = db.scalar(select(User).where(User.email == payload.user_email.strip().lower()))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    statement = select(CustomerMembership).where(
        CustomerMembership.user_id == user.id,
        CustomerMembership.customer_id == customer_id,
    )
    membership = db.scalar(statement)
    if membership is None:
        membership = CustomerMembership(
            user_id=user.id,
            customer_id=customer_id,
            role=payload.role,
            is_active=payload.is_active,
        )
    else:
        membership.role = payload.role
        membership.is_active = payload.is_active

    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


@api_router.patch(
    "/customer-memberships/{membership_id}",
    response_model=CustomerMembershipRead,
    tags=["customer-memberships"],
)
def update_customer_membership(
    membership_id: UUID,
    payload: CustomerMembershipUpdate,
    db: DbSession,
    _current_admin: CurrentPlatformAdmin,
) -> CustomerMembership:
    membership = get_customer_membership_or_404(db, membership_id)
    update_data = payload.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(membership, field, value)

    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


@api_router.post(
    "/organizations",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
    tags=["organizations"],
    dependencies=[Depends(get_current_user)],
)
def create_organization(
    payload: OrganizationCreate,
    db: DbSession,
) -> Organization:
    if payload.customer_id is not None:
        get_customer_or_404(db, payload.customer_id)

    existing = db.scalar(select(Organization).where(Organization.name == payload.name))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization with this name already exists.",
        )

    organization = Organization(**payload.model_dump())
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


@api_router.get(
    "/organizations",
    response_model=list[OrganizationRead],
    tags=["organizations"],
    dependencies=[Depends(get_current_user)],
)
def list_organizations(db: DbSession) -> list[Organization]:
    statement = select(Organization).order_by(Organization.created_at.desc())
    return list(db.scalars(statement).all())


@api_router.get(
    "/organizations/{organization_id}",
    response_model=OrganizationRead,
    tags=["organizations"],
    dependencies=[Depends(get_current_user)],
)
def get_organization(organization_id: UUID, db: DbSession) -> Organization:
    return get_organization_or_404(db, organization_id)


@api_router.post(
    "/organizations/{organization_id}/connector-configs/google-workspace",
    response_model=ConnectorConfigRead,
    status_code=status.HTTP_201_CREATED,
    tags=["connector-configs"],
    dependencies=[Depends(get_current_user)],
)
def upsert_google_workspace_connector_config(
    organization_id: UUID,
    payload: ConnectorConfigCreate,
    db: DbSession,
) -> ConnectorConfig:
    get_organization_or_404(db, organization_id)
    statement = select(ConnectorConfig).where(
        ConnectorConfig.organization_id == organization_id,
        ConnectorConfig.connector_type == "google_workspace",
    )
    connector_config = db.scalar(statement)
    payload_data = payload.model_dump()

    if connector_config is None:
        connector_config = ConnectorConfig(
            organization_id=organization_id,
            connector_type="google_workspace",
            **payload_data,
        )
        db.add(connector_config)
    else:
        for field, value in payload_data.items():
            setattr(connector_config, field, value)
        db.add(connector_config)

    db.commit()
    db.refresh(connector_config)
    return connector_config


@api_router.get(
    "/organizations/{organization_id}/connector-configs",
    response_model=list[ConnectorConfigRead],
    tags=["connector-configs"],
    dependencies=[Depends(get_current_user)],
)
def list_organization_connector_configs(
    organization_id: UUID,
    db: DbSession,
) -> list[ConnectorConfig]:
    get_organization_or_404(db, organization_id)
    statement = (
        select(ConnectorConfig)
        .where(ConnectorConfig.organization_id == organization_id)
        .order_by(ConnectorConfig.created_at.desc())
    )
    return list(db.scalars(statement).all())


@api_router.get(
    "/connector-configs/{connector_config_id}",
    response_model=ConnectorConfigRead,
    tags=["connector-configs"],
    dependencies=[Depends(get_current_user)],
)
def get_connector_config(connector_config_id: UUID, db: DbSession) -> ConnectorConfig:
    return get_connector_config_or_404(db, connector_config_id)


@api_router.patch(
    "/connector-configs/{connector_config_id}",
    response_model=ConnectorConfigRead,
    tags=["connector-configs"],
    dependencies=[Depends(get_current_user)],
)
def update_connector_config(
    connector_config_id: UUID,
    payload: ConnectorConfigUpdate,
    db: DbSession,
) -> ConnectorConfig:
    connector_config = get_connector_config_or_404(db, connector_config_id)
    update_data = payload.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(connector_config, field, value)

    db.add(connector_config)
    db.commit()
    db.refresh(connector_config)
    return connector_config


@api_router.post(
    "/connector-configs/{connector_config_id}/test",
    response_model=ConnectorConfigTestRead,
    tags=["connector-configs"],
    dependencies=[Depends(get_current_user)],
)
def test_connector_config(
    connector_config_id: UUID,
    db: DbSession,
) -> ConnectorConfigTestRead:
    connector_config = get_connector_config_or_404(db, connector_config_id)
    connector_config.last_tested_at = datetime.now(UTC)
    connector_config.last_error = "Real Google Workspace connection testing is not implemented yet."
    db.add(connector_config)
    db.commit()

    return ConnectorConfigTestRead(
        status="not_implemented",
        message="Real Google Workspace connection testing is not implemented yet.",
        recommended_next_step=(
            "Configure service account domain-wide delegation or OAuth admin consent in a future "
            "release."
        ),
    )


@api_router.post(
    "/assessments",
    response_model=AssessmentRead,
    status_code=status.HTTP_201_CREATED,
    tags=["assessments"],
    dependencies=[Depends(get_current_user)],
)
def create_assessment(
    payload: AssessmentCreate,
    db: DbSession,
) -> Assessment:
    get_organization_or_404(db, payload.organization_id)

    assessment = Assessment(**payload.model_dump())
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment


@api_router.get(
    "/assessments",
    response_model=list[AssessmentRead],
    tags=["assessments"],
    dependencies=[Depends(get_current_user)],
)
def list_assessments(db: DbSession) -> list[Assessment]:
    statement = select(Assessment).order_by(Assessment.created_at.desc())
    return list(db.scalars(statement).all())


@api_router.get(
    "/assessments/{assessment_id}",
    response_model=AssessmentRead,
    tags=["assessments"],
    dependencies=[Depends(get_current_user)],
)
def get_assessment(assessment_id: UUID, db: DbSession) -> Assessment:
    return get_assessment_or_404(db, assessment_id)


@api_router.get(
    "/assessments/{assessment_id}/report",
    response_model=AssessmentReportRead,
    tags=["assessments"],
    dependencies=[Depends(get_current_user)],
)
def get_assessment_report(assessment_id: UUID, db: DbSession) -> AssessmentReportRead:
    assessment_statement = (
        select(Assessment)
        .where(Assessment.id == assessment_id)
        .options(selectinload(Assessment.organization))
    )
    assessment = db.scalar(assessment_statement)
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found.",
        )

    findings_statement = (
        select(Finding)
        .where(Finding.assessment_id == assessment_id)
        .options(
            selectinload(Finding.asset),
            selectinload(Finding.dread_score),
        )
        .order_by(Finding.created_at.asc(), Finding.title.asc())
    )
    findings = list(db.scalars(findings_statement).all())

    assets_by_id = {
        finding.asset.id: finding.asset
        for finding in findings
        if finding.asset is not None
    }

    risk_counts = RiskLevelCounts()
    scores = [finding.dread_score.total_score for finding in findings]
    for finding in findings:
        risk_level = finding.dread_score.risk_level.lower()
        current_count = getattr(risk_counts, risk_level)
        setattr(risk_counts, risk_level, current_count + 1)

    highest_finding = max(
        findings,
        key=lambda finding: finding.dread_score.total_score,
        default=None,
    )

    return AssessmentReportRead(
        generated_at=datetime.now(UTC),
        assessment=assessment,
        organization=assessment.organization,
        assets=list(assets_by_id.values()),
        findings=findings,
        total_findings=len(findings),
        findings_per_risk_level=risk_counts,
        average_score=round(sum(scores) / len(scores), 2) if scores else None,
        highest_score=highest_finding.dread_score.total_score if highest_finding else None,
        highest_risk_level=highest_finding.dread_score.risk_level if highest_finding else None,
    )


@api_router.post(
    "/assessments/{assessment_id}/scan-runs/google-workspace-mock",
    response_model=ScanRunRead,
    status_code=status.HTTP_201_CREATED,
    tags=["scan-runs"],
    dependencies=[Depends(get_current_user)],
)
def run_mock_google_workspace_scan(assessment_id: UUID, db: DbSession) -> ScanRun:
    assessment = get_assessment_or_404(db, assessment_id)
    started_at = datetime.now(UTC)
    scan_run = ScanRun(
        assessment_id=assessment.id,
        connector_type=MockGoogleWorkspaceConnector.connector_type,
        status="running",
        started_at=started_at,
        findings_created=0,
        summary="Mock Google Workspace scan started.",
        raw_result_json={"note": "Mock scan only; no real Google data was accessed."},
    )
    db.add(scan_run)
    db.commit()
    db.refresh(scan_run)

    try:
        connector = MockGoogleWorkspaceConnector()
        result = connector.run()
        asset = get_or_create_google_workspace_asset(db, assessment)
        created_count = 0

        for connector_finding in result.findings:
            score_values = connector_finding.dread_score
            total_score, risk_level = calculate_dread_score(score_values)
            finding = Finding(
                assessment_id=assessment.id,
                asset_id=asset.id,
                title=connector_finding.title,
                description=(
                    f"Category: {connector_finding.category}\n\n"
                    f"{connector_finding.description}\n\n"
                    f"Impact: {connector_finding.impact}"
                ),
                status="open",
                mitigation=connector_finding.recommendation,
                dread_score=DreadScore(
                    **score_values,
                    total_score=total_score,
                    risk_level=risk_level,
                ),
            )
            db.add(finding)
            created_count += 1

        completed_at = datetime.now(UTC)
        scan_run.status = "completed"
        scan_run.completed_at = completed_at
        scan_run.findings_created = created_count
        scan_run.summary = (
            f"Mock Google Workspace scan completed. {created_count} demo findings were "
            "created; no real Google data was accessed."
        )
        scan_run.raw_result_json = {
            "connector_type": result.connector_type,
            "summary": result.summary,
            "asset_name": asset.name,
            "findings": [
                {
                    "check_id": finding.check_id,
                    "title": finding.title,
                    "category": finding.category,
                    "impact": finding.impact,
                    "recommendation": finding.recommendation,
                    "dread_score": finding.dread_score,
                }
                for finding in result.findings
            ],
        }
        db.add(scan_run)
        db.commit()
        db.refresh(scan_run)
        return scan_run
    except Exception as exc:
        db.rollback()
        scan_run = get_scan_run_or_404(db, scan_run.id)
        scan_run.status = "failed"
        scan_run.completed_at = datetime.now(UTC)
        scan_run.summary = f"Mock Google Workspace scan failed: {exc}"
        scan_run.raw_result_json = {
            "error": str(exc),
            "note": "Mock scan only; no real Google data was accessed.",
        }
        db.add(scan_run)
        db.commit()
        db.refresh(scan_run)
        return scan_run


@api_router.get(
    "/assessments/{assessment_id}/scan-runs",
    response_model=list[ScanRunRead],
    tags=["scan-runs"],
    dependencies=[Depends(get_current_user)],
)
def list_assessment_scan_runs(assessment_id: UUID, db: DbSession) -> list[ScanRun]:
    get_assessment_or_404(db, assessment_id)
    statement = (
        select(ScanRun)
        .where(ScanRun.assessment_id == assessment_id)
        .order_by(ScanRun.started_at.desc())
    )
    return list(db.scalars(statement).all())


@api_router.get(
    "/scan-runs/{scan_run_id}",
    response_model=ScanRunRead,
    tags=["scan-runs"],
    dependencies=[Depends(get_current_user)],
)
def get_scan_run(scan_run_id: UUID, db: DbSession) -> ScanRun:
    return get_scan_run_or_404(db, scan_run_id)


@api_router.post(
    "/assets",
    response_model=AssetRead,
    status_code=status.HTTP_201_CREATED,
    tags=["assets"],
    dependencies=[Depends(get_current_user)],
)
def create_asset(
    payload: AssetCreate,
    db: DbSession,
) -> Asset:
    get_organization_or_404(db, payload.organization_id)

    duplicate = db.scalar(
        select(Asset).where(
            Asset.organization_id == payload.organization_id,
            Asset.name == payload.name,
        )
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Asset with this name already exists for this organization.",
        )

    asset = Asset(**payload.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@api_router.get(
    "/assets",
    response_model=list[AssetRead],
    tags=["assets"],
    dependencies=[Depends(get_current_user)],
)
def list_assets(db: DbSession) -> list[Asset]:
    statement = select(Asset).order_by(Asset.created_at.desc())
    return list(db.scalars(statement).all())


@api_router.get(
    "/assets/{asset_id}",
    response_model=AssetRead,
    tags=["assets"],
    dependencies=[Depends(get_current_user)],
)
def get_asset(asset_id: UUID, db: DbSession) -> Asset:
    return get_asset_or_404(db, asset_id)


@api_router.post(
    "/findings",
    response_model=FindingRead,
    status_code=status.HTTP_201_CREATED,
    tags=["findings"],
    dependencies=[Depends(get_current_user)],
)
def create_finding(
    payload: FindingCreate,
    db: DbSession,
) -> Finding:
    assessment = get_assessment_or_404(db, payload.assessment_id)
    validate_asset_scope(db, payload.asset_id, assessment)

    score_values = payload.dread_score.model_dump()
    total_score, risk_level = calculate_dread_score(score_values)
    finding = Finding(
        assessment_id=payload.assessment_id,
        asset_id=payload.asset_id,
        title=payload.title,
        description=payload.description,
        status=payload.status,
        mitigation=payload.mitigation,
        dread_score=DreadScore(
            **score_values,
            total_score=total_score,
            risk_level=risk_level,
        ),
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return get_finding_or_404(db, finding.id)


@api_router.get(
    "/findings",
    response_model=list[FindingRead],
    tags=["findings"],
    dependencies=[Depends(get_current_user)],
)
def list_findings(db: DbSession) -> list[Finding]:
    statement = (
        select(Finding)
        .options(selectinload(Finding.dread_score))
        .order_by(Finding.created_at.desc())
    )
    return list(db.scalars(statement).all())


@api_router.get(
    "/findings/{finding_id}",
    response_model=FindingRead,
    tags=["findings"],
    dependencies=[Depends(get_current_user)],
)
def get_finding(finding_id: UUID, db: DbSession) -> Finding:
    return get_finding_or_404(db, finding_id)


@api_router.patch(
    "/findings/{finding_id}",
    response_model=FindingRead,
    tags=["findings"],
    dependencies=[Depends(get_current_user)],
)
def update_finding(
    finding_id: UUID,
    payload: FindingUpdate,
    db: DbSession,
) -> Finding:
    finding = get_finding_or_404(db, finding_id)
    assessment = get_assessment_or_404(db, finding.assessment_id)
    update_data = payload.model_dump(exclude_unset=True)

    if "asset_id" in update_data:
        validate_asset_scope(db, update_data["asset_id"], assessment)
        finding.asset_id = update_data["asset_id"]

    for field in ("title", "description", "status", "mitigation"):
        if field in update_data:
            setattr(finding, field, update_data[field])

    if "dread_score" in update_data and update_data["dread_score"] is not None:
        apply_dread_score(finding.dread_score, update_data["dread_score"])

    db.add(finding)
    db.commit()
    db.refresh(finding)
    return get_finding_or_404(db, finding.id)
