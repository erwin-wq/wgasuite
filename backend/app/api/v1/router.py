from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models import Assessment, Asset, DreadScore, Finding, Organization, User
from app.schemas.assessment import AssessmentCreate, AssessmentRead
from app.schemas.asset import AssetCreate, AssetRead
from app.schemas.auth import LoginRequest, TokenResponse, UserRead
from app.schemas.finding import FindingCreate, FindingRead, FindingUpdate
from app.schemas.organization import OrganizationCreate, OrganizationRead
from app.schemas.report import AssessmentReportRead, RiskLevelCounts
from app.services.dread import calculate_dread_score
from app.services.passwords import verify_password
from app.services.tokens import encode_access_token

api_router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


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
def get_me(current_user: CurrentUser) -> User:
    return current_user


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
