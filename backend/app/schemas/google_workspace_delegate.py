from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.google_workspace_user import EMAIL_PATTERN


class _NormalizedEmailRequest(BaseModel):
    @field_validator("owner_email", "delegate_email", mode="before", check_fields=False)
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class GmailDelegateListRequest(_NormalizedEmailRequest):
    owner_email: str = Field(min_length=3, max_length=254, pattern=EMAIL_PATTERN)


class GmailDelegateChangePreviewRequest(GmailDelegateListRequest):
    delegate_email: str = Field(min_length=3, max_length=254, pattern=EMAIL_PATTERN)


class GmailDelegateMutationRequest(BaseModel):
    confirmation_token: str = Field(min_length=32, max_length=256)


class GmailDelegateRead(BaseModel):
    primary_email: str
    verification_status: Literal["accepted", "pending", "rejected", "unknown"]


class GmailDelegateListRead(BaseModel):
    owner_primary_email: str
    delegates: list[GmailDelegateRead]


class GmailDelegateChangePreviewRead(BaseModel):
    operation: Literal["create", "remove"]
    owner_primary_email: str
    delegate_primary_email: str
    confirmation_token: str
    expires_at: datetime
    effect: str


class GmailDelegateMutationRead(BaseModel):
    operation: Literal["create", "remove"]
    owner_primary_email: str
    delegate_primary_email: str
    outcome: Literal["created", "removed"]
    message: str
