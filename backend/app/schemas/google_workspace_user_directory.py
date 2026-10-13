from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class GoogleWorkspaceUserDirectoryRequest(BaseModel):
    search: str = Field(default="", max_length=100)
    search_field: Literal["all", "email", "given_name", "family_name", "full_name"] = "all"
    org_unit_path: str | None = Field(default=None, max_length=1000)
    suspended: Literal["all", "active", "suspended"] = "all"
    admin_status: Literal["all", "super_admin", "delegated_admin"] = "all"
    archived: Literal["all", "archived", "not_archived"] = "all"
    order_by: Literal["email", "given_name", "family_name"] = "email"
    sort_direction: Literal["ascending", "descending"] = "ascending"
    page_size: Literal[25, 50, 100] = 50
    page_token: str | None = Field(default=None, max_length=2048)

    @field_validator("search", mode="before")
    @classmethod
    def normalize_search(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if any(ord(character) < 32 for character in normalized):
            raise ValueError("search cannot contain control characters")
        if any(character in "\\*:={}[]()<>" for character in normalized):
            raise ValueError("search contains unsupported query characters")
        return normalized

    @field_validator("org_unit_path", mode="before")
    @classmethod
    def normalize_org_unit_path(cls, value: object) -> object:
        if value is None or not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            return None
        if not normalized.startswith("/"):
            raise ValueError("organizational unit path must begin with /")
        if any(ord(character) < 32 for character in normalized):
            raise ValueError("organizational unit path cannot contain control characters")
        return normalized


class GoogleWorkspaceDirectoryUserRead(BaseModel):
    id: str
    full_name: str | None
    given_name: str | None
    family_name: str | None
    primary_email: str
    org_unit_path: str | None
    suspended: bool | None
    archived: bool | None
    is_super_admin: bool | None
    is_delegated_admin: bool | None
    creation_time: datetime | None
    last_login_time: datetime | None


class GoogleWorkspaceUserDirectoryRead(BaseModel):
    users: list[GoogleWorkspaceDirectoryUserRead]
    next_page_token: str | None
