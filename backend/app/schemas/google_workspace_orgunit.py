from __future__ import annotations

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


class OrganizationalUnitTreeNodeRead(OrganizationalUnitRead):
    children: list[OrganizationalUnitTreeNodeRead] = Field(default_factory=list)


class OrganizationalUnitHierarchyRead(BaseModel):
    roots: list[OrganizationalUnitTreeNodeRead]
    total: int
