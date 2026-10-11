from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.google_workspace_user import EMAIL_PATTERN


class GroupSearchRequest(BaseModel):
    query: str = Field(default="", max_length=100)
    page_token: str | None = Field(default=None, max_length=2048)
    max_results: int = Field(default=50, ge=1, le=200)

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class GroupReferenceRequest(BaseModel):
    group_email: str = Field(min_length=3, max_length=254, pattern=EMAIL_PATTERN)

    @field_validator("group_email", mode="before")
    @classmethod
    def normalize_group_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class GroupMemberListRequest(GroupReferenceRequest):
    page_token: str | None = Field(default=None, max_length=2048)
    max_results: int = Field(default=50, ge=1, le=200)


class GroupMembershipPreviewRequest(GroupReferenceRequest):
    member_email: str = Field(min_length=3, max_length=254, pattern=EMAIL_PATTERN)

    @field_validator("member_email", mode="before")
    @classmethod
    def normalize_member_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class GroupMembershipMutationRequest(BaseModel):
    confirmation_token: str = Field(min_length=32, max_length=256)


class GoogleWorkspaceGroupRead(BaseModel):
    id: str
    primary_email: str
    name: str
    description: str | None
    aliases: list[str]
    non_editable_aliases: list[str]
    direct_members_count: int | None
    membership_mutable: bool
    restriction_reason: str | None


class GroupSearchRead(BaseModel):
    groups: list[GoogleWorkspaceGroupRead]
    next_page_token: str | None


class GroupMemberRead(BaseModel):
    id: str
    email: str | None
    type: Literal["USER", "GROUP", "CUSTOMER", "EXTERNAL", "UNKNOWN"]
    role: Literal["MEMBER", "MANAGER", "OWNER", "UNKNOWN"]
    status: str | None
    direct: bool = True
    mutation_supported: bool
    restriction_reason: str | None


class GroupMemberListRead(BaseModel):
    group: GoogleWorkspaceGroupRead
    members: list[GroupMemberRead]
    next_page_token: str | None


class GroupMembershipPreviewRead(BaseModel):
    operation: Literal["add", "remove"]
    group_primary_email: str
    member_primary_email: str
    member_role: Literal["MEMBER", "MANAGER", "OWNER"]
    confirmation_token: str
    expires_at: datetime
    effect: str


class GroupMembershipMutationRead(BaseModel):
    operation: Literal["add", "remove"]
    group_primary_email: str
    member_primary_email: str
    outcome: Literal["added", "removed"]
    message: str


class GroupMembershipReconciliationRead(BaseModel):
    operation: Literal["add", "remove"]
    group_primary_email: str
    member_primary_email: str
    status: Literal["verified", "unknown"]
    observed_state: Literal["present", "absent"]
    attempts: int
    correlation_id: str
    message: str
