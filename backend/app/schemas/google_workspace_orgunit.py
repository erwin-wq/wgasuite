from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ORGUNIT_ID_PATTERN = r"^[A-Za-z0-9:_-]+$"


class OrganizationalUnitReferenceRequest(BaseModel):
    org_unit_id: str = Field(min_length=1, max_length=256, pattern=ORGUNIT_ID_PATTERN)

    @field_validator("org_unit_id", mode="before")
    @classmethod
    def normalize_org_unit_id(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class OrganizationalUnitRead(BaseModel):
    id: str
    name: str
    description: str | None
    path: str
    parent_id: str | None
    parent_path: str | None
    read_only: bool = True
    user_move_protected: bool


class OrganizationalUnitTreeNodeRead(OrganizationalUnitRead):
    children: list[OrganizationalUnitTreeNodeRead] = Field(default_factory=list)


class OrganizationalUnitHierarchyRead(BaseModel):
    roots: list[OrganizationalUnitTreeNodeRead]
    total: int


class OrganizationalUnitCreatePreviewRequest(BaseModel):
    parent_org_unit_id: str = Field(min_length=1, max_length=256, pattern=ORGUNIT_ID_PATTERN)
    name: str = Field(min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=4096)

    @field_validator("parent_org_unit_id", "name", mode="before")
    @classmethod
    def normalize_required(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None


class OrganizationalUnitCreatePreviewRead(BaseModel):
    parent_org_unit_id: str
    parent_path: str
    name: str
    description: str | None
    expected_path: str
    confirmation_token: str
    expires_at: datetime
    effect: str


class OrganizationalUnitCreateRequest(BaseModel):
    confirmation_token: str = Field(min_length=32, max_length=512)


class OrganizationalUnitCreateRead(BaseModel):
    organizational_unit: OrganizationalUnitRead
    outcome: Literal["created"]
    message: str


class OrganizationalUnitCreateReconciliationRead(BaseModel):
    status: Literal["verified", "unknown"]
    organizational_unit: OrganizationalUnitRead | None
    expected_path: str
    attempts: int
    correlation_id: str
    message: str


class OrganizationalUnitDescriptionPreviewRequest(BaseModel):
    org_unit_id: str = Field(min_length=1, max_length=256, pattern=ORGUNIT_ID_PATTERN)
    description: str = Field(max_length=4096)

    @field_validator("org_unit_id", mode="before")
    @classmethod
    def normalize_org_unit_id(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class OrganizationalUnitDescriptionPreviewRead(BaseModel):
    org_unit_id: str
    name: str
    path: str
    original_description: str | None
    proposed_description: str | None
    confirmation_token: str
    expires_at: datetime
    effect: str


class OrganizationalUnitDescriptionUpdateRequest(BaseModel):
    confirmation_token: str = Field(min_length=32, max_length=512)


class OrganizationalUnitDescriptionUpdateRead(BaseModel):
    organizational_unit: OrganizationalUnitRead
    previous_description: str | None
    outcome: Literal["updated"]
    message: str


class OrganizationalUnitDescriptionReconciliationRead(BaseModel):
    status: Literal["verified", "unknown"]
    organizational_unit: OrganizationalUnitRead | None
    attempts: int
    correlation_id: str
    message: str
