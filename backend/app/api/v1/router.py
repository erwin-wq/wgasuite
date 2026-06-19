from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Assessment, Finding, Organization
from app.schemas.assessment import AssessmentCreate, AssessmentRead
from app.schemas.finding import FindingCreate, FindingRead
from app.schemas.organization import OrganizationCreate, OrganizationRead
from app.services.dread import calculate_dread_score

api_router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]


@api_router.get("/organizations", response_model=list[OrganizationRead], tags=["organizations"])
def list_organizations(db: DbSession) -> list[Organization]:
    statement = select(Organization).order_by(Organization.created_at.desc())
    return list(db.scalars(statement).all())


@api_router.post(
    "/organizations",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
    tags=["organizations"],
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


@api_router.post(
    "/organizations/{organization_id}/assessments",
    response_model=AssessmentRead,
    status_code=status.HTTP_201_CREATED,
    tags=["assessments"],
)
def create_assessment(
    organization_id: UUID,
    payload: AssessmentCreate,
    db: DbSession,
) -> Assessment:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found.",
        )

    assessment = Assessment(organization_id=organization.id, **payload.model_dump())
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment


@api_router.get(
    "/organizations/{organization_id}/assessments",
    response_model=list[AssessmentRead],
    tags=["assessments"],
)
def list_assessments(
    organization_id: UUID,
    db: DbSession,
) -> list[Assessment]:
    statement = (
        select(Assessment)
        .where(Assessment.organization_id == organization_id)
        .order_by(Assessment.created_at.desc())
    )
    return list(db.scalars(statement).all())


@api_router.post(
    "/assessments/{assessment_id}/findings",
    response_model=FindingRead,
    status_code=status.HTTP_201_CREATED,
    tags=["findings"],
)
def create_finding(
    assessment_id: UUID,
    payload: FindingCreate,
    db: DbSession,
) -> Finding:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found.",
        )

    payload_data = payload.model_dump()
    finding = Finding(
        assessment_id=assessment.id,
        risk_score=calculate_dread_score(payload_data),
        **payload_data,
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return finding


@api_router.get(
    "/assessments/{assessment_id}/findings",
    response_model=list[FindingRead],
    tags=["findings"],
)
def list_findings(
    assessment_id: UUID,
    db: DbSession,
) -> list[Finding]:
    statement = (
        select(Finding)
        .where(Finding.assessment_id == assessment_id)
        .order_by(Finding.created_at.desc())
    )
    return list(db.scalars(statement).all())
