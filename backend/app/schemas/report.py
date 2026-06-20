from datetime import datetime

from pydantic import BaseModel

from app.schemas.assessment import AssessmentRead
from app.schemas.asset import AssetRead
from app.schemas.finding import FindingRead
from app.schemas.organization import OrganizationRead


class RiskLevelCounts(BaseModel):
    low: int = 0
    medium: int = 0
    high: int = 0
    critical: int = 0


class AssessmentReportRead(BaseModel):
    generated_at: datetime
    assessment: AssessmentRead
    organization: OrganizationRead
    assets: list[AssetRead]
    findings: list[FindingRead]
    total_findings: int
    findings_per_risk_level: RiskLevelCounts
    average_score: float | None
    highest_score: float | None
    highest_risk_level: str | None
