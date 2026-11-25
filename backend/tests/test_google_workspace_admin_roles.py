from __future__ import annotations

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
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []
        self.requests: list[FakeRequest] = []

    def list(self, **kwargs: Any) -> FakeRequest:
        self.calls.append(kwargs)
        response = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        request = FakeRequest(response)
        self.requests.append(request)
        return request


class FakeHttp:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeClient:
    def __init__(self, roles: list[object], assignments: list[object]) -> None:
        self.roles_resource = PagedResource(roles)
        self.assignments_resource = PagedResource(assignments)
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
) -> tuple[GoogleWorkspaceAdminRoles, FakeFactory, Any, Any]:
    connector, actor = create_connector(db_session)
    factory = FakeFactory(FakeClient(roles, assignments))
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
                    "roleId": "role-1",
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
                    "roleAssignmentId": "assignment-1",
                    "roleId": "role-1",
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
                        {"roleId": "role-1", "roleName": "One"},
                        {"roleId": "role-1", "roleName": "Duplicate"},
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
            [{"items": [{"roleId": "role-1", "roleName": "One"}]}],
            [{"items": [{"roleAssignmentId": "a-1", "roleId": "missing", "assignedTo": "u"}]}],
            GoogleWorkspaceErrorCode.GOOGLE_API_ERROR,
        ),
        (
            [{"items": [{"roleId": "role-1", "roleName": "One"}]}],
            [
                {
                    "items": [
                        {
                            "roleAssignmentId": "a-1",
                            "roleId": "role-1",
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
        [{"items": [{"roleId": "role-1", "roleName": "Custom"}]}],
        [
            {
                "items": [
                    {
                        "roleAssignmentId": "a-1",
                        "roleId": "role-1",
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
