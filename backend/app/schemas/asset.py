import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AssetCreate(BaseModel):
    organization_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    asset_type: str = Field(default="system", min_length=1, max_length=80)
    identifier: str | None = Field(default=None, max_length=255)
    description: str | None = None


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    asset_type: str
    identifier: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime
