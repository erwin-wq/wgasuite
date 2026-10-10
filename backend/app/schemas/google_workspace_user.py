from typing import Literal

from pydantic import BaseModel, Field, field_validator

EMAIL_PATTERN = (
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


class GoogleWorkspaceUserLookupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=EMAIL_PATTERN)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class GoogleWorkspaceUserRead(BaseModel):
    id: str
    full_name: str | None
    primary_email: str
    aliases: list[str]
    non_editable_aliases: list[str]
    suspended: bool
    archived: bool | None
    org_unit_path: str | None
    is_mailbox_setup: bool | None
    matched_by: Literal["primary_email", "alias", "non_editable_alias"]
