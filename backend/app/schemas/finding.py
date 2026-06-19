import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.dread_score import DreadScoreCreate, DreadScoreRead, DreadScoreUpdate


class FindingCreate(BaseModel):
    assessment_id: uuid.UUID
    asset_id: uuid.UUID | None = None
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    status: str = Field(default="open", max_length=40)
    mitigation: str | None = None
    dread_score: DreadScoreCreate


class FindingUpdate(BaseModel):
    asset_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = Field(default=None, max_length=40)
    mitigation: str | None = None
    dread_score: DreadScoreUpdate | None = None


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assessment_id: uuid.UUID
    asset_id: uuid.UUID | None
    title: str
    description: str | None
    status: str
    mitigation: str | None
    dread_score: DreadScoreRead
    created_at: datetime
    updated_at: datetime
