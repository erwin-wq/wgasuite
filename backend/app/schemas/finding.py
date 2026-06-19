import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FindingBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    affected_asset: str | None = Field(default=None, max_length=255)
    status: str = Field(default="open", max_length=40)
    mitigation: str | None = None
    dread_damage: int = Field(..., ge=0, le=10)
    dread_reproducibility: int = Field(..., ge=0, le=10)
    dread_exploitability: int = Field(..., ge=0, le=10)
    dread_affected_users: int = Field(..., ge=0, le=10)
    dread_discoverability: int = Field(..., ge=0, le=10)


class FindingCreate(FindingBase):
    pass


class FindingRead(FindingBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assessment_id: uuid.UUID
    risk_score: float
    created_at: datetime
    updated_at: datetime
