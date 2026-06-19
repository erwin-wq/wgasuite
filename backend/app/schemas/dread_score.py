import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DreadScoreBase(BaseModel):
    damage: int = Field(..., ge=0, le=10)
    reproducibility: int = Field(..., ge=0, le=10)
    exploitability: int = Field(..., ge=0, le=10)
    affected_users: int = Field(..., ge=0, le=10)
    discoverability: int = Field(..., ge=0, le=10)


class DreadScoreCreate(DreadScoreBase):
    pass


class DreadScoreUpdate(BaseModel):
    damage: int | None = Field(default=None, ge=0, le=10)
    reproducibility: int | None = Field(default=None, ge=0, le=10)
    exploitability: int | None = Field(default=None, ge=0, le=10)
    affected_users: int | None = Field(default=None, ge=0, le=10)
    discoverability: int | None = Field(default=None, ge=0, le=10)


class DreadScoreRead(DreadScoreBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    finding_id: uuid.UUID
    total_score: float
    risk_level: str
    created_at: datetime
    updated_at: datetime
