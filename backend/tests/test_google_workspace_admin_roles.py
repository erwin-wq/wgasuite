from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.google_workspace_credentials import (
    DIRECTORY_ROLE_MANAGEMENT_READONLY_SCOPE,
)
from app.connectors.google_workspace_errors import GoogleWorkspaceError, GoogleWorkspaceErrorCode
from app.models import AuditEvent
from app.services.google_workspace_admin_roles import (
    GoogleWorkspaceAdminRoles,
    WorkspaceAdminRole,
    WorkspaceAdminRoleInventory,
    WorkspaceRoleAssignment,
    WorkspaceRolePrivilege,
)
from tests.test_customer_data_scoping import add_user, login_headers
from tests.test_google_workspace_connection import create_connector
from tests.test_google_workspace_domains import FakeLookup


class FakeRequest:
    def __init__(self, response: object) -> None:
        self.response = response
        self.execute_kwargs: dict[str, Any] | None = None

    def execute(self, **kwargs: Any) -> object:
        self.execute_kwargs = kwargs
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class PagedResource:
    def __init__(self, responses: list[object], get_response: object | None = None) -> None:
        self.responses = responses
        self.get_response = get_response
        self.calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []
        self.requests: list[FakeRequest] = []

    def list(self, **kwargs: Any) -> FakeRequest:
        self.calls.append(kwargs)
        response = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        request = FakeRequest(response)
        self.requests.append(request)
        return request

    def get(self, **kwargs: Any) -> FakeRequest:
        self.get_calls.append(kwargs)
        request = FakeRequest(self.get_response)
        self.requests.append(request)
        return request


class FakeHttp:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeClient:
    def __init__(
        self,
        roles: list[object],
        assignments: list[object],
        role_detail: object | None = None,
        assignment_detail: object | None = None,
    ) -> None:
        self.roles_resource = PagedResource(roles, role_detail)
        self.assignments_resource = PagedResource(assignments, assignment_detail)
        self._http = FakeHttp()

    def roles(self) -> PagedResource:
        return self.roles_resource

    def roleAssignments(self) -> PagedResource:  # noqa: N802
        return self.assignments_resource


class FakeFactory:
    def __init__(self, client: FakeClient) -> None:
        self.client = client
        self.calls: list[dict[str, Any]] = []

    def for_directory_role_management(self, **kwargs: Any) -> FakeClient:
        self.calls.append(kwargs)
        return self.client


def role_service(
    db_session: Session,
    roles: list[object],
    assignments: list[object],
    role_detail: object | None = None,
    assignment_detail: object | None = None,
) -> tuple[GoogleWorkspaceAdminRoles, FakeFactory, Any, Any]:
    connector, actor = create_connector(db_session)
    factory = FakeFactory(FakeClient(roles, assignments, role_detail, assignment_detail))
    service = GoogleWorkspaceAdminRoles(
        db_session,
        factory,  # type: ignore[arg-type]
        FakeLookup("customer-immutable-1"),  # type: ignore[arg-type]
    )
    return service, factory, connector, actor


def test_lists_all_pages_with_verified_customer_exact_scope_and_no_retries(
    db_session: Session,
) -> None:
    roles = [
        {"items": [], "nextPageToken": "roles-2"},
        {
            "items": [
                {
                    "roleId": "1001",
                    "roleName": "Help Desk",
                    "roleDescription": "Limited user support",
                    "isSystemRole": True,
                    "isSuperAdminRole": False,
                    "rolePrivileges": [{"serviceId": "02", "privilegeName": "USERS_RETRIEVE"}],
                }
            ]
        },
    ]
    assignments = [
        {
            "items": [
                {
                    "roleAssignmentId": "2001",
                    "roleId": "1001",
                    "assignedTo": "109999999999999999999",
                    "assigneeType": "USER",
                    "scopeType": "ORG_UNIT",
                    "orgUnitId": "id:ou-1",
                    "condition": "securityGroup",
                }
            ]
        }
    ]
    service, factory, connector, actor = role_service(db_session, roles, assignments)

    result = service.list_inventory(actor=actor, organization_id=connector.organization_id)

    assert result.roles[0].name == "Help Desk"
    assert result.assignments[0].scope_type == "ORG_UNIT"
    assert factory.calls == [
        {
            "actor": actor,
            "organization_id": connector.organization_id,
            "scopes": (DIRECTORY_ROLE_MANAGEMENT_READONLY_SCOPE,),
        }
    ]
    assert [call["customer"] for call in factory.client.roles_resource.calls] == [
        "customer-immutable-1",
        "customer-immutable-1",
    ]
    assert factory.client.roles_resource.calls[1]["pageToken"] == "roles-2"
    assert factory.client.roles_resource.calls[0]["maxResults"] == 100
    assert factory.client.assignments_resource.calls[0]["maxResults"] == 200
    assert "pageToken" not in factory.client.roles_resource.calls[0]
    assert "includeIndirectRoleAssignments" not in factory.client.assignments_resource.calls[0]
    assert all(
        request.execute_kwargs == {"num_retries": 0}
        for request in [
            *factory.client.roles_resource.requests,
            *factory.client.assignments_resource.requests,
        ]
    )
    assert factory.client._http.closed is True


@pytest.mark.parametrize(
    ("roles", "assignments", "expected"),
    [
        (
            [
                {
                    "items": [
                        {"roleId": "1001", "roleName": "One"},
                        {"roleId": "1001", "roleName": "Duplicate"},
                    ]
                }
            ],
            [{"items": []}],
            GoogleWorkspaceErrorCode.GOOGLE_API_ERROR,
        ),
        (
            [{"items": [], "nextPageToken": "same"}, {"items": [], "nextPageToken": "same"}],
            [{"items": []}],
            GoogleWorkspaceErrorCode.GOOGLE_PAGE_TOKEN_INVALID,
        ),
        (
            [{"items": [{"roleId": "1001", "roleName": "One"}]}],
            [{"items": [{"roleAssignmentId": "2002", "roleId": "missing", "assignedTo": "u"}]}],
            GoogleWorkspaceErrorCode.GOOGLE_API_ERROR,
        ),
        (
            [{"items": [{"roleId": "1001", "roleName": "One"}]}],
            [
                {
                    "items": [
                        {
                            "roleAssignmentId": "2002",
                            "roleId": "1001",
                            "assignedTo": "u",
                            "scopeType": "ORG_UNIT",
                        }
                    ]
                }
            ],
            GoogleWorkspaceErrorCode.GOOGLE_API_ERROR,
        ),
    ],
)
def test_invalid_or_ambiguous_google_data_fails_closed(
    db_session: Session,
    roles: list[object],
    assignments: list[object],
    expected: GoogleWorkspaceErrorCode,
) -> None:
    service, _, connector, actor = role_service(db_session, roles, assignments)
    with pytest.raises(GoogleWorkspaceError) as error:
        service.list_inventory(actor=actor, organization_id=connector.organization_id)
    assert error.value.code == expected


def test_unknown_enums_are_preserved_as_unknown(db_session: Session) -> None:
    service, _, connector, actor = role_service(
        db_session,
        [{"items": [{"roleId": "1001", "roleName": "Custom"}]}],
        [
            {
                "items": [
                    {
                        "roleAssignmentId": "2002",
                        "roleId": "1001",
                        "assignedTo": "opaque",
                        "assigneeType": "FUTURE",
                        "scopeType": "FUTURE",
                    }
                ]
            }
        ],
    )
    assignment = service.list_inventory(
        actor=actor, organization_id=connector.organization_id
    ).assignments[0]
    assert assignment.assignee_type == "UNKNOWN"
    assert assignment.scope_type == "UNKNOWN"


def test_gets_authoritative_role_and_assignment_with_exact_ids_and_no_retries(
    db_session: Session,
) -> None:
    service, factory, connector, actor = role_service(
        db_session,
        [],
        [],
        role_detail={
            "roleId": "1001",
            "roleName": "Custom Security Reader",
            "roleDescription": "Read security settings",
            "isSystemRole": False,
            "isSuperAdminRole": False,
            "rolePrivileges": [
                {"serviceId": "02", "privilegeName": "USERS_RETRIEVE"},
                {"serviceId": "03", "privilegeName": "GROUPS_RETRIEVE"},
            ],
            "etag": "role-etag",
        },
        assignment_detail={
            "roleAssignmentId": "2001",
            "roleId": "1001",
            "assignedTo": "109999999999999999999",
            "assigneeType": "GROUP",
            "scopeType": "ORG_UNIT",
            "orgUnitId": "id:ou-1",
            "condition": "resource.type == 'example'",
            "expirationDetails": {"expireTime": "2026-12-02T15:01:23.045123456+05:30"},
            "etag": "assignment-etag",
        },
    )

    role = service.get_role(actor=actor, organization_id=connector.organization_id, role_id="1001")
    assignment = service.get_assignment(
        actor=actor, organization_id=connector.organization_id, assignment_id="2001"
    )

    assert role.name == "Custom Security Reader"
    assert role.is_system_role is False
    assert role.is_super_admin_role is False
    assert [item.privilege_name for item in role.privileges] == [
        "GROUPS_RETRIEVE",
        "USERS_RETRIEVE",
    ]
    assert role.etag == "role-etag"
    assert assignment.assignee_type == "GROUP"
    assert assignment.scope_type == "ORG_UNIT"
    assert assignment.condition == "resource.type == 'example'"
    assert assignment.expires_at == datetime(2026, 12, 2, 9, 31, 23, 45123, tzinfo=UTC)
    assert assignment.etag == "assignment-etag"
    assert factory.client.roles_resource.get_calls == [
        {
            "customer": "customer-immutable-1",
            "roleId": "1001",
            "fields": (
                "roleId,roleName,roleDescription,isSystemRole,isSuperAdminRole,"
                "rolePrivileges(serviceId,privilegeName),etag"
            ),
        }
    ]
    assert factory.client.assignments_resource.get_calls[0]["customer"] == ("customer-immutable-1")
    assert factory.client.assignments_resource.get_calls[0]["roleAssignmentId"] == "2001"
    assert all(
        request.execute_kwargs == {"num_retries": 0}
        for request in [
            *factory.client.roles_resource.requests,
            *factory.client.assignments_resource.requests,
        ]
    )
    assert factory.client._http.closed is True


def test_get_details_accepts_absent_optional_metadata_and_unknown_principal(
    db_session: Session,
) -> None:
    service, _, connector, actor = role_service(
        db_session,
        [],
        [],
        role_detail={"roleId": "1001", "roleName": "Empty role"},
        assignment_detail={
            "roleAssignmentId": "2001",
            "roleId": "1001",
            "assignedTo": "opaque-principal",
            "assigneeType": "SERVICE_ACCOUNT",
            "scopeType": "FUTURE_SCOPE",
        },
    )
    role = service.get_role(actor=actor, organization_id=connector.organization_id, role_id="1001")
    assignment = service.get_assignment(
        actor=actor, organization_id=connector.organization_id, assignment_id="2001"
    )
    assert role.description is None
    assert role.privileges == ()
    assert assignment.assignee_type == "UNKNOWN"
    assert assignment.scope_type == "UNKNOWN"
    assert assignment.expires_at is None


@pytest.mark.parametrize("resource_id", ["", "role-1", "-1", "1 2", "1" * 31])
def test_detail_ids_are_validated_before_google(db_session: Session, resource_id: str) -> None:
    service, factory, connector, actor = role_service(db_session, [], [])
    with pytest.raises(GoogleWorkspaceError) as error:
        service.get_role(
            actor=actor,
            organization_id=connector.organization_id,
            role_id=resource_id,
        )
    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_RESOURCE_ID_INVALID
    assert factory.calls == []


def test_detail_lookup_fails_closed_without_connector(db_session: Session) -> None:
    service, factory, connector, actor = role_service(db_session, [], [])
    organization_id = connector.organization_id
    db_session.delete(connector)
    db_session.commit()
    with pytest.raises(GoogleWorkspaceError) as error:
        service.get_role(actor=actor, organization_id=organization_id, role_id="1001")
    assert error.value.code == GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED
    assert factory.calls == []


@pytest.mark.parametrize(
    "expire_time",
    ["not-a-time", "2026-12-02T15:01:23", "2026-12-02", 123],
)
def test_assignment_rejects_invalid_expiration(db_session: Session, expire_time: object) -> None:
    service, _, connector, actor = role_service(
        db_session,
        [],
        [],
        assignment_detail={
            "roleAssignmentId": "2001",
            "roleId": "1001",
            "assignedTo": "opaque",
            "expirationDetails": {"expireTime": expire_time},
        },
    )
    with pytest.raises(GoogleWorkspaceError) as error:
        service.get_assignment(
            actor=actor,
            organization_id=connector.organization_id,
            assignment_id="2001",
        )
    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_API_ERROR


def test_endpoint_returns_direct_only_contract_and_count_only_audit(
    client: TestClient,
    db_session: Session,
    auth_headers: dict[str, str],
) -> None:
    connector, _ = create_connector(db_session)
    service = MagicMock()
    service.list_inventory.return_value = WorkspaceAdminRoleInventory(
        roles=(
            WorkspaceAdminRole(
                "role-private-id",
                "Help Desk",
                None,
                True,
                False,
                (WorkspaceRolePrivilege("02", "USERS_RETRIEVE"),),
            ),
        ),
        assignments=(
            WorkspaceRoleAssignment(
                "assignment-private-id",
                "role-private-id",
                "user-private-id",
                "USER",
                "CUSTOMER",
                None,
                None,
            ),
        ),
    )
    with patch("app.api.v1.router.GoogleWorkspaceAdminRoles.from_settings", return_value=service):
        response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/admin-roles/list",
            headers=auth_headers,
        )
    assert response.status_code == 200
    body = response.json()
    assert body["direct_assignments_only"] is True
    assert body["effective_permissions_included"] is False
    assert body["assignment_count"] == 1
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "google_workspace.admin_role_inventory.listed"
        )
    )
    assert event is not None
    serialized_metadata = str(event.metadata_json)
    assert "user-private-id" not in serialized_metadata
    assert "assignment-private-id" not in serialized_metadata
    assert "role-private-id" not in serialized_metadata


def test_detail_endpoints_return_authoritative_records_and_redacted_audit(
    client: TestClient,
    db_session: Session,
    auth_headers: dict[str, str],
) -> None:
    connector, _ = create_connector(db_session)
    service = MagicMock()
    service.get_role.return_value = WorkspaceAdminRole(
        "1001",
        "Super administrator",
        "Full administration",
        True,
        True,
        (WorkspaceRolePrivilege("02", "USERS_RETRIEVE"),),
        "private-role-etag",
    )
    service.get_assignment.return_value = WorkspaceRoleAssignment(
        "2001",
        "1001",
        "private-principal-id",
        "USER",
        "CUSTOMER",
        None,
        None,
        datetime(2020, 1, 1, tzinfo=UTC),
        "private-assignment-etag",
    )
    with patch("app.api.v1.router.GoogleWorkspaceAdminRoles.from_settings", return_value=service):
        role_response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/admin-roles/get",
            headers=auth_headers,
            json={"id": "1001"},
        )
        assignment_response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/admin-role-assignments/get",
            headers=auth_headers,
            json={"id": "2001"},
        )
    assert role_response.status_code == 200
    assert role_response.json()["role"]["is_super_admin_role"] is True
    assert assignment_response.status_code == 200
    assignment_body = assignment_response.json()
    assert assignment_body["assignment"]["expired"] is True
    assert assignment_body["direct_assignment"] is True
    assert assignment_body["effective_permissions_included"] is False
    events = list(
        db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.action.in_(
                    {
                        "google_workspace.admin_role.viewed",
                        "google_workspace.admin_role_assignment.viewed",
                    }
                )
            )
        ).all()
    )
    assert len(events) == 2
    serialized = str([event.metadata_json for event in events])
    assert "private-principal-id" not in serialized
    assert "1001" not in serialized
    assert "2001" not in serialized
    assert "etag" not in serialized


@pytest.mark.parametrize(
    "path",
    ["admin-roles/get", "admin-role-assignments/get"],
)
def test_detail_endpoints_reject_invalid_identifiers(
    client: TestClient,
    db_session: Session,
    auth_headers: dict[str, str],
    path: str,
) -> None:
    connector, _ = create_connector(db_session)
    with patch("app.api.v1.router.GoogleWorkspaceAdminRoles.from_settings") as factory:
        response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/{path}",
            headers=auth_headers,
            json={"id": "not-an-immutable-id"},
        )
    assert response.status_code == 422
    factory.assert_not_called()


def test_cross_customer_actor_cannot_reach_role_service(
    client: TestClient, db_session: Session
) -> None:
    connector, _ = create_connector(db_session)
    add_user(db_session, "role-outsider@example.local")
    headers = login_headers(client, "role-outsider@example.local")
    with patch("app.api.v1.router.GoogleWorkspaceAdminRoles.from_settings") as factory:
        response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/admin-roles/list",
            headers=headers,
        )
    assert response.status_code == 403
    factory.assert_not_called()
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "google_workspace.admin_role_inventory.listed"
        )
    )
    assert event is not None
    assert event.object_type == "google_workspace_admin_role_inventory"
    assert event.metadata_json == {
        "read_only": True,
        "direct_assignments_only": True,
    }


@pytest.mark.parametrize(
    "path",
    ["admin-roles/get", "admin-role-assignments/get"],
)
def test_cross_customer_actor_cannot_reach_detail_services(
    client: TestClient, db_session: Session, path: str
) -> None:
    connector, _ = create_connector(db_session)
    add_user(db_session, f"detail-outsider-{path.split('/')[0]}@example.local")
    headers = login_headers(client, f"detail-outsider-{path.split('/')[0]}@example.local")
    with patch("app.api.v1.router.GoogleWorkspaceAdminRoles.from_settings") as factory:
        response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/{path}",
            headers=headers,
            json={"id": "1001"},
        )
    assert response.status_code == 403
    factory.assert_not_called()


@pytest.mark.parametrize(
    ("path", "method", "code", "status_code"),
    [
        (
            "admin-roles/get",
            "get_role",
            GoogleWorkspaceErrorCode.GOOGLE_ADMIN_ROLE_NOT_FOUND,
            404,
        ),
        (
            "admin-role-assignments/get",
            "get_assignment",
            GoogleWorkspaceErrorCode.GOOGLE_ROLE_ASSIGNMENT_NOT_FOUND,
            404,
        ),
        ("admin-roles/get", "get_role", GoogleWorkspaceErrorCode.GOOGLE_FORBIDDEN, 403),
        (
            "admin-role-assignments/get",
            "get_assignment",
            GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED,
            429,
        ),
        ("admin-roles/get", "get_role", GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE, 503),
        (
            "admin-role-assignments/get",
            "get_assignment",
            GoogleWorkspaceErrorCode.GOOGLE_NETWORK_ERROR,
            503,
        ),
    ],
)
def test_detail_endpoints_map_safe_errors(
    client: TestClient,
    db_session: Session,
    auth_headers: dict[str, str],
    path: str,
    method: str,
    code: GoogleWorkspaceErrorCode,
    status_code: int,
) -> None:
    connector, _ = create_connector(db_session)
    service = MagicMock()
    getattr(service, method).side_effect = GoogleWorkspaceError(code)
    with patch("app.api.v1.router.GoogleWorkspaceAdminRoles.from_settings", return_value=service):
        response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/{path}",
            headers=auth_headers,
            json={"id": "1001"},
        )
    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code.value


@pytest.mark.parametrize(
    ("code", "status_code"),
    [
        (GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION, 403),
        (GoogleWorkspaceErrorCode.DELEGATION_REJECTED, 403),
        (GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED, 429),
        (GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE, 503),
    ],
)
def test_endpoint_maps_sanitized_google_errors(
    client: TestClient,
    db_session: Session,
    auth_headers: dict[str, str],
    code: GoogleWorkspaceErrorCode,
    status_code: int,
) -> None:
    connector, _ = create_connector(db_session)
    service = MagicMock()
    service.list_inventory.side_effect = GoogleWorkspaceError(code)
    with patch("app.api.v1.router.GoogleWorkspaceAdminRoles.from_settings", return_value=service):
        response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/admin-roles/list",
            headers=auth_headers,
        )
    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code.value
