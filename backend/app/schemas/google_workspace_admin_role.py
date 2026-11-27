from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GoogleWorkspaceAdminResourceReferenceRequest(BaseModel):
    id: str = Field(min_length=1, max_length=30, pattern=r"^[0-9]+$")


class GoogleWorkspaceRolePrivilegeRead(BaseModel):
    service_id: str
    privilege_name: str


class GoogleWorkspaceAdminRoleRead(BaseModel):
    role_id: str
    name: str
    description: str | None
    is_system_role: bool
    is_super_admin_role: bool
    privileges: list[GoogleWorkspaceRolePrivilegeRead]


class GoogleWorkspaceRoleAssignmentRead(BaseModel):
    assignment_id: str
    role_id: str
    assigned_to: str
    assignee_type: Literal["USER", "GROUP", "UNKNOWN"]
    scope_type: Literal["CUSTOMER", "ORG_UNIT", "UNKNOWN"]
    org_unit_id: str | None
    condition: str | None
    expires_at: datetime | None = None
    expired: bool = False


class GoogleWorkspaceAdminRoleInventoryRead(BaseModel):
    roles: list[GoogleWorkspaceAdminRoleRead]
    assignments: list[GoogleWorkspaceRoleAssignmentRead]
    role_count: int
    assignment_count: int
    direct_assignments_only: bool = True
    effective_permissions_included: bool = False
    read_only: bool = True


class GoogleWorkspaceAdminRoleDetailRead(BaseModel):
    role: GoogleWorkspaceAdminRoleRead
    read_only: bool = True


class GoogleWorkspaceRoleAssignmentDetailRead(BaseModel):
    assignment: GoogleWorkspaceRoleAssignmentRead
    direct_assignment: bool = True
    effective_permissions_included: bool = False
    read_only: bool = True
