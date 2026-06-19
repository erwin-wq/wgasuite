import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AssessmentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    scope_summary: str | None = None


class AssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    status: str
    scope_summary: str | None
    created_at: datetime
    updated_at: datetime
