from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.google_workspace_user import EMAIL_PATTERN


class UserGroupMembershipListRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=EMAIL_PATTERN)
    page_size: Literal[10, 25] = 10
    page_token: str | None = Field(default=None, max_length=2048)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class UserDirectGroupMembershipRead(BaseModel):
    group_id: str
    group_name: str
    group_primary_email: str
    role: Literal["MEMBER", "MANAGER", "OWNER"]
    member_type: Literal["USER"]
    status: str | None


class UserGroupMembershipListRead(BaseModel):
    user_id: str
    user_primary_email: str
    matched_by: Literal["primary_email", "alias", "non_editable_alias"]
    memberships: list[UserDirectGroupMembershipRead]
    next_page_token: str | None
    verification_complete: bool
    candidates_examined: int
    omitted_external_count: int
    omitted_indirect_count: int
