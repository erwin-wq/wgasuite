from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.google_workspace_user import EMAIL_PATTERN


class UserStatusPreviewRequest(BaseModel):
    user_email: str = Field(min_length=3, max_length=254, pattern=EMAIL_PATTERN)

    @field_validator("user_email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class UserStatusMutationRequest(BaseModel):
    confirmation_token: str = Field(min_length=32, max_length=255)


class UserStatusPreviewRead(BaseModel):
    operation: Literal["suspend", "reactivate"]
    organization_id: UUID
    customer_id: UUID
    target_google_id: str
    target_primary_email: str
    previous_suspended: bool
    requested_suspended: bool
    confirmation_token: str
    expires_at: datetime
    effect: str


class UserStatusMutationRead(BaseModel):
    operation: Literal["suspend", "reactivate"]
    target_google_id: str
    target_primary_email: str
    previous_suspended: bool
    suspended: bool
    outcome: Literal["suspended", "reactivated"]
    message: str


class UserStatusReconciliationRead(BaseModel):
    operation: Literal["suspend", "reactivate"]
    target_google_id: str
    target_primary_email: str
    status: Literal["verified", "unknown"]
    observed_suspended: bool
    attempts: int
    correlation_id: str
    message: str
