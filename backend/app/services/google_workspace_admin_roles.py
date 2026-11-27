from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.google_workspace_client import GoogleWorkspaceClientFactory
from app.connectors.google_workspace_credentials import (
    DIRECTORY_ROLE_MANAGEMENT_READONLY_SCOPE,
)
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
    map_google_api_error,
)
from app.models import ConnectorConfig, User
from app.services.google_workspace_user_lookup import GoogleWorkspaceUserLookup

ROLE_FIELDS = (
    "items(roleId,roleName,roleDescription,isSystemRole,isSuperAdminRole,"
    "rolePrivileges(serviceId,privilegeName)),nextPageToken"
)
ROLE_DETAIL_FIELDS = (
    "roleId,roleName,roleDescription,isSystemRole,isSuperAdminRole,"
    "rolePrivileges(serviceId,privilegeName),etag"
)
ASSIGNMENT_FIELDS = (
    "items(roleAssignmentId,roleId,assignedTo,assigneeType,scopeType,orgUnitId,condition,"
    "expirationDetails(expireTime)),"
    "nextPageToken"
)
ASSIGNMENT_DETAIL_FIELDS = (
    "roleAssignmentId,roleId,assignedTo,assigneeType,scopeType,orgUnitId,condition,"
    "expirationDetails(expireTime),etag"
)
MAX_PAGES = 100
MAX_RECORDS = 10_000
MAX_TEXT_LENGTH = 4_096
RESOURCE_ID_PATTERN = re.compile(r"^[0-9]{1,30}$")


@dataclass(frozen=True)
class WorkspaceRolePrivilege:
    service_id: str
    privilege_name: str


@dataclass(frozen=True)
class WorkspaceAdminRole:
    role_id: str
    name: str
    description: str | None
    is_system_role: bool
    is_super_admin_role: bool
    privileges: tuple[WorkspaceRolePrivilege, ...]
    etag: str | None = None


@dataclass(frozen=True)
class WorkspaceRoleAssignment:
    assignment_id: str
    role_id: str
    assigned_to: str
    assignee_type: Literal["USER", "GROUP", "UNKNOWN"]
    scope_type: Literal["CUSTOMER", "ORG_UNIT", "UNKNOWN"]
    org_unit_id: str | None
    condition: str | None
    expires_at: datetime | None = None
    etag: str | None = None


@dataclass(frozen=True)
class WorkspaceAdminRoleInventory:
    roles: tuple[WorkspaceAdminRole, ...]
    assignments: tuple[WorkspaceRoleAssignment, ...]


class GoogleWorkspaceAdminRoles:
    """Read direct administrator role assignments for one verified customer."""

    def __init__(
        self,
        db: Session,
        client_factory: GoogleWorkspaceClientFactory,
        user_lookup: GoogleWorkspaceUserLookup,
    ) -> None:
        self.db = db
        self.client_factory = client_factory
        self.user_lookup = user_lookup

    @classmethod
    def from_settings(cls, db: Session) -> GoogleWorkspaceAdminRoles:
        factory = GoogleWorkspaceClientFactory.from_settings(db)
        return cls(db, factory, GoogleWorkspaceUserLookup(factory))

    def list_inventory(
        self,
        *,
        actor: User,
        organization_id: UUID,
        request_timeout_seconds: float | None = None,
    ) -> WorkspaceAdminRoleInventory:
        customer_id = self._verified_customer_id(actor, organization_id)
        arguments: dict[str, Any] = {
            "actor": actor,
            "organization_id": organization_id,
            "scopes": (DIRECTORY_ROLE_MANAGEMENT_READONLY_SCOPE,),
        }
        if request_timeout_seconds is not None:
            arguments["request_timeout_seconds"] = request_timeout_seconds
        client: Any | None = None
        try:
            client = self.client_factory.for_directory_role_management(**arguments)
            raw_roles = self._paginate(
                client.roles(), "items", customer_id, ROLE_FIELDS, max_results=100
            )
            raw_assignments = self._paginate(
                client.roleAssignments(),
                "items",
                customer_id,
                ASSIGNMENT_FIELDS,
                max_results=200,
            )
            return self._normalize(raw_roles, raw_assignments)
        except GoogleWorkspaceError:
            raise
        except Exception as error:
            raise map_google_api_error(error) from None
        finally:
            self._close_client(client)

    def get_role(
        self,
        *,
        actor: User,
        organization_id: UUID,
        role_id: str,
        request_timeout_seconds: float | None = None,
    ) -> WorkspaceAdminRole:
        requested_id = self._resource_id(role_id)
        customer_id = self._verified_customer_id(actor, organization_id)
        client: Any | None = None
        try:
            client = self._role_client(actor, organization_id, request_timeout_seconds)
            response = (
                client.roles()
                .get(customer=customer_id, roleId=requested_id, fields=ROLE_DETAIL_FIELDS)
                .execute(num_retries=0)
            )
            role = self._role(response)
            if role.role_id != requested_id:
                self._invalid_response()
            return role
        except GoogleWorkspaceError:
            raise
        except Exception as error:
            raise self._detail_error(
                error, GoogleWorkspaceErrorCode.GOOGLE_ADMIN_ROLE_NOT_FOUND
            ) from None
        finally:
            self._close_client(client)

    def get_assignment(
        self,
        *,
        actor: User,
        organization_id: UUID,
        assignment_id: str,
        request_timeout_seconds: float | None = None,
    ) -> WorkspaceRoleAssignment:
        requested_id = self._resource_id(assignment_id)
        customer_id = self._verified_customer_id(actor, organization_id)
        client: Any | None = None
        try:
            client = self._role_client(actor, organization_id, request_timeout_seconds)
            response = (
                client.roleAssignments()
                .get(
                    customer=customer_id,
                    roleAssignmentId=requested_id,
                    fields=ASSIGNMENT_DETAIL_FIELDS,
                )
                .execute(num_retries=0)
            )
            assignment = self._assignment(response)
            if assignment.assignment_id != requested_id:
                self._invalid_response()
            return assignment
        except GoogleWorkspaceError:
            raise
        except Exception as error:
            raise self._detail_error(
                error, GoogleWorkspaceErrorCode.GOOGLE_ROLE_ASSIGNMENT_NOT_FOUND
            ) from None
        finally:
            self._close_client(client)

    def _role_client(
        self,
        actor: User,
        organization_id: UUID,
        request_timeout_seconds: float | None,
    ) -> Any:
        arguments: dict[str, Any] = {
            "actor": actor,
            "organization_id": organization_id,
            "scopes": (DIRECTORY_ROLE_MANAGEMENT_READONLY_SCOPE,),
        }
        if request_timeout_seconds is not None:
            arguments["request_timeout_seconds"] = request_timeout_seconds
        return self.client_factory.for_directory_role_management(**arguments)

    @classmethod
    def _paginate(
        cls,
        resource: Any,
        field: str,
        customer_id: str,
        fields: str,
        *,
        max_results: int,
    ) -> list[Any]:
        values: list[Any] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()
        for _ in range(MAX_PAGES):
            request: dict[str, Any] = {
                "customer": customer_id,
                "maxResults": max_results,
                "fields": fields,
            }
            if page_token is not None:
                request["pageToken"] = page_token
            response = resource.list(**request).execute(num_retries=0)
            if not isinstance(response, dict):
                cls._invalid_response()
            page_values = response.get(field, [])
            if page_values is None:
                page_values = []
            if not isinstance(page_values, list):
                cls._invalid_response()
            values.extend(page_values)
            if len(values) > MAX_RECORDS:
                raise GoogleWorkspaceError(
                    GoogleWorkspaceErrorCode.GOOGLE_OPERATION_BUDGET_EXCEEDED
                )
            next_token = response.get("nextPageToken")
            if next_token is None:
                return values
            if not isinstance(next_token, str) or not next_token or next_token in seen_tokens:
                raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_PAGE_TOKEN_INVALID)
            seen_tokens.add(next_token)
            page_token = next_token
        raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_OPERATION_BUDGET_EXCEEDED)

    @classmethod
    def _normalize(
        cls, raw_roles: list[Any], raw_assignments: list[Any]
    ) -> WorkspaceAdminRoleInventory:
        roles: dict[str, WorkspaceAdminRole] = {}
        for raw in raw_roles:
            role = cls._role(raw)
            if role.role_id in roles:
                cls._invalid_response()
            roles[role.role_id] = role

        assignments: dict[str, WorkspaceRoleAssignment] = {}
        for raw in raw_assignments:
            assignment = cls._assignment(raw)
            if assignment.assignment_id in assignments or assignment.role_id not in roles:
                cls._invalid_response()
            assignments[assignment.assignment_id] = assignment
        return WorkspaceAdminRoleInventory(
            roles=tuple(sorted(roles.values(), key=lambda item: item.name.casefold())),
            assignments=tuple(sorted(assignments.values(), key=lambda item: item.assignment_id)),
        )

    @classmethod
    def _role(cls, raw: Any) -> WorkspaceAdminRole:
        if not isinstance(raw, dict):
            cls._invalid_response()
        raw_privileges = raw.get("rolePrivileges", [])
        if raw_privileges is None:
            raw_privileges = []
        if not isinstance(raw_privileges, list):
            cls._invalid_response()
        privileges: list[WorkspaceRolePrivilege] = []
        privilege_keys: set[tuple[str, str]] = set()
        for value in raw_privileges:
            if not isinstance(value, dict):
                cls._invalid_response()
            privilege = WorkspaceRolePrivilege(
                service_id=cls._text(value.get("serviceId")),
                privilege_name=cls._text(value.get("privilegeName")),
            )
            key = (privilege.service_id, privilege.privilege_name)
            if key in privilege_keys:
                cls._invalid_response()
            privilege_keys.add(key)
            privileges.append(privilege)
        return WorkspaceAdminRole(
            role_id=cls._resource_id(raw.get("roleId"), invalid_response=True),
            name=cls._text(raw.get("roleName")),
            description=cls._optional_text(raw.get("roleDescription")),
            is_system_role=cls._bool(raw.get("isSystemRole", False)),
            is_super_admin_role=cls._bool(raw.get("isSuperAdminRole", False)),
            privileges=tuple(sorted(privileges, key=lambda item: item.privilege_name)),
            etag=cls._optional_text(raw.get("etag")),
        )

    @classmethod
    def _assignment(cls, raw: Any) -> WorkspaceRoleAssignment:
        if not isinstance(raw, dict):
            cls._invalid_response()
        assignee_type = raw.get("assigneeType", "UNKNOWN")
        if assignee_type not in {"USER", "GROUP"}:
            assignee_type = "UNKNOWN"
        scope_type = raw.get("scopeType", "UNKNOWN")
        if scope_type not in {"CUSTOMER", "ORG_UNIT"}:
            scope_type = "UNKNOWN"
        org_unit_id = cls._optional_text(raw.get("orgUnitId"))
        if scope_type == "ORG_UNIT" and org_unit_id is None:
            cls._invalid_response()
        expiration = raw.get("expirationDetails")
        expires_at: datetime | None = None
        if expiration is not None:
            if not isinstance(expiration, dict) or "expireTime" not in expiration:
                cls._invalid_response()
            expires_at = cls._timestamp(expiration.get("expireTime"))
        return WorkspaceRoleAssignment(
            assignment_id=cls._resource_id(raw.get("roleAssignmentId"), invalid_response=True),
            role_id=cls._resource_id(raw.get("roleId"), invalid_response=True),
            assigned_to=cls._text(raw.get("assignedTo")),
            assignee_type=assignee_type,
            scope_type=scope_type,
            org_unit_id=org_unit_id,
            condition=cls._optional_text(raw.get("condition")),
            expires_at=expires_at,
            etag=cls._optional_text(raw.get("etag")),
        )

    def _verified_customer_id(self, actor: User, organization_id: UUID) -> str:
        connector = self.db.scalar(
            select(ConnectorConfig).where(
                ConnectorConfig.organization_id == organization_id,
                ConnectorConfig.connector_type == "google_workspace",
            )
        )
        if connector is None or not connector.admin_subject_email:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED)
        administrator = self.user_lookup.lookup(
            actor=actor,
            organization_id=organization_id,
            email=connector.admin_subject_email,
        )
        return administrator.customer_id

    @classmethod
    def _text(cls, value: Any) -> str:
        if not isinstance(value, str):
            cls._invalid_response()
        normalized = value.strip()
        if (
            not normalized
            or len(normalized) > MAX_TEXT_LENGTH
            or any(ord(c) < 32 for c in normalized)
        ):
            cls._invalid_response()
        return normalized

    @classmethod
    def _optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        if (
            not isinstance(value, str)
            or len(value) > MAX_TEXT_LENGTH
            or any(ord(c) < 32 for c in value)
        ):
            cls._invalid_response()
        normalized = value.strip()
        return normalized or None

    @classmethod
    def _bool(cls, value: Any) -> bool:
        if not isinstance(value, bool):
            cls._invalid_response()
        return value

    @classmethod
    def _resource_id(cls, value: Any, *, invalid_response: bool = False) -> str:
        if isinstance(value, str):
            normalized = value.strip()
            if RESOURCE_ID_PATTERN.fullmatch(normalized):
                return normalized
        if invalid_response:
            cls._invalid_response()
        raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_RESOURCE_ID_INVALID)

    @classmethod
    def _timestamp(cls, value: Any) -> datetime:
        if not isinstance(value, str) or len(value) > 64:
            cls._invalid_response()
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            cls._invalid_response()
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            cls._invalid_response()
        return parsed.astimezone(UTC)

    @staticmethod
    def _detail_error(
        error: Exception, not_found_code: GoogleWorkspaceErrorCode
    ) -> GoogleWorkspaceError:
        mapped = map_google_api_error(error)
        if mapped.code == GoogleWorkspaceErrorCode.GOOGLE_SUBJECT_NOT_FOUND:
            return GoogleWorkspaceError(not_found_code)
        return mapped

    @staticmethod
    def _close_client(client: Any | None) -> None:
        close = getattr(getattr(client, "_http", None), "close", None)
        if callable(close):
            close()

    @staticmethod
    def _invalid_response() -> None:
        raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
