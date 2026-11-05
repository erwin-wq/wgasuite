from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

ORGUNIT_ID_PATTERN = r"^[A-Za-z0-9:_-]+$"


class UserOrgUnitMovePreviewRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    destination_org_unit_id: str = Field(
        min_length=1, max_length=256, pattern=ORGUNIT_ID_PATTERN
    )

    @field_validator("user_id", "destination_org_unit_id", mode="before")
    @classmethod
    def normalize_identifier(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class UserOrgUnitMoveRequest(BaseModel):
    confirmation_token: str = Field(min_length=32, max_length=255)


class UserOrgUnitMovePreviewRead(BaseModel):
    organization_id: UUID
    customer_id: UUID
    target_google_id: str
    target_primary_email: str
    source_org_unit_path: str
    destination_org_unit_id: str
    destination_org_unit_path: str
    confirmation_token: str
    expires_at: datetime
    effect: str


class UserOrgUnitMoveRead(BaseModel):
    target_google_id: str
    target_primary_email: str
    previous_org_unit_path: str
    org_unit_path: str
    outcome: Literal["moved"]
    message: str


class UserOrgUnitMoveReconciliationRead(BaseModel):
    target_google_id: str
    target_primary_email: str
    status: Literal["verified", "unknown"]
    observed_org_unit_path: str
    attempts: int
    correlation_id: str
    message: str
