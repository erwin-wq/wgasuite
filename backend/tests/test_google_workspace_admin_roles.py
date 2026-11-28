from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.google_workspace_credentials import (
    DIRECTORY_GROUP_READONLY_SCOPE,
    DIRECTORY_ROLE_MANAGEMENT_READONLY_SCOPE,
)
from app.connectors.google_workspace_errors import GoogleWorkspaceError, GoogleWorkspaceErrorCode
from app.models import AuditEvent
from app.services.google_workspace_admin_roles import (
    GoogleWorkspaceAdminRoles,
    WorkspaceAdminPrincipal,
    WorkspaceAdminRole,
    WorkspaceAdminRoleInventory,
    WorkspaceRoleAssignment,
    WorkspaceRolePrivilege,
    WorkspaceUserRoleAssignment,
    WorkspaceUserRoleAssignmentInventory,
)
from app.services.google_workspace_user_lookup import GoogleWorkspaceUserLookupResult
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


def selected_user(
    customer_id: str = "customer-immutable-1",
) -> GoogleWorkspaceUserLookupResult:
    return GoogleWorkspaceUserLookupResult(
        id="109999999999999999999",
        customer_id=customer_id,
        full_name="Selected User",
        primary_email="selected@example.test",
        aliases=[],
        non_editable_aliases=[],
        suspended=False,
        archived=False,
        org_unit_path="/",
        is_mailbox_setup=True,
        matched_by="immutable_id",
    )


def test_lists_per_user_direct_assignments_through_empty_continuation_page(
    db_session: Session,
) -> None:
    roles = [{"items": [{"roleId": "1001", "roleName": "Help Desk"}]}]
    assignments = [
        {"items": [], "nextPageToken": "assignment-2"},
        {
            "items": [
                {
                    "roleAssignmentId": "2001",
                    "roleId": "1001",
                    "assignedTo": "109999999999999999999",
                    "assigneeType": "USER",
                    "scopeType": "CUSTOMER",
                }
            ]
        },
    ]
    service, factory, connector, actor = role_service(db_session, roles, assignments)
    service.user_lookup.lookup_by_id = MagicMock(return_value=selected_user())  # type: ignore[method-assign]

    result = service.list_user_assignments(
        actor=actor,
        organization_id=connector.organization_id,
        user_id="109999999999999999999",
    )

    assert len(result.assignments) == 1
    assert result.assignments[0].provenance == "DIRECT"
    assert result.assignments[0].role is not None
    assert result.assignments[0].principal.account_status == "ACTIVE"
    calls = factory.client.assignments_resource.calls
    assert calls[0]["customer"] == "customer-immutable-1"
    assert calls[0]["userKey"] == "109999999999999999999"
    assert calls[0]["includeIndirectRoleAssignments"] is True
    assert calls[1]["pageToken"] == "assignment-2"
    assert all(
        request.execute_kwargs == {"num_retries": 0}
        for request in factory.client.assignments_resource.requests
    )


def test_classifies_only_verified_group_principal_as_google_reported_indirect(
    db_session: Session,
) -> None:
    roles = [{"items": [{"roleId": "1001", "roleName": "Groups Admin"}]}]
    assignments = [
        {
            "items": [
                {
                    "roleAssignmentId": "2002",
                    "roleId": "1001",
                    "assignedTo": "108888888888888888888",
                    "assigneeType": "GROUP",
                    "scopeType": "ORG_UNIT",
                    "orgUnitId": "03ph8a2z1z3e34p",
                    "condition": "securityGroup",
                    "expirationDetails": {"expireTime": "2026-12-31T00:00:00Z"},
                }
            ]
        }
    ]
    service, _, connector, actor = role_service(db_session, roles, assignments)
    service.user_lookup.lookup_by_id = MagicMock(return_value=selected_user())  # type: ignore[method-assign]
    service._resolve_group_principal = MagicMock(
        return_value=WorkspaceAdminPrincipal(  # type: ignore[method-assign]
            outcome="verified",
            identity_type="GROUP",
            principal_id="108888888888888888888",
            primary_email="admins@example.test",
            display_name="Administrators",
        )
    )

    result = service.list_user_assignments(
        actor=actor,
        organization_id=connector.organization_id,
        user_id="109999999999999999999",
    )

    assert result.assignments[0].provenance == "GROUP_DERIVED"
    assert result.assignments[0].assignment.scope_type == "ORG_UNIT"
    assert result.assignments[0].assignment.condition == "securityGroup"


def test_per_user_assignments_reject_cross_tenant_user(db_session: Session) -> None:
    service, factory, connector, actor = role_service(db_session, [{"items": []}], [{"items": []}])
    service.user_lookup.lookup_by_id = MagicMock(  # type: ignore[method-assign]
        return_value=selected_user("different-customer")
    )

    with pytest.raises(GoogleWorkspaceError) as caught:
        service.list_user_assignments(
            actor=actor,
            organization_id=connector.organization_id,
            user_id="109999999999999999999",
        )

    assert caught.value.code == GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH
    assert factory.calls == []


def test_per_user_assignments_preserve_missing_role_and_unknown_provenance(
    db_session: Session,
) -> None:
    assignments = [
        {
            "items": [
                {
                    "roleAssignmentId": "2003",
                    "roleId": "9999",
                    "assignedTo": "107777777777777777777",
                    "scopeType": "CUSTOMER",
                }
            ]
        }
    ]
    service, _, connector, actor = role_service(db_session, [{"items": []}], assignments)
    service.user_lookup.lookup_by_id = MagicMock(return_value=selected_user())  # type: ignore[method-assign]

    result = service.list_user_assignments(
        actor=actor,
        organization_id=connector.organization_id,
        user_id="109999999999999999999",
    )

    assert result.assignments[0].role is None
    assert result.assignments[0].provenance == "UNKNOWN"
    assert (
        result.assignments[0].principal.reason == "google_did_not_identify_indirect_principal_type"
    )


def test_per_user_assignments_reject_duplicate_records(db_session: Session) -> None:
    duplicate = {
        "roleAssignmentId": "2004",
        "roleId": "1001",
        "assignedTo": "109999999999999999999",
        "scopeType": "CUSTOMER",
    }
    service, _, connector, actor = role_service(
        db_session,
        [{"items": [{"roleId": "1001", "roleName": "Role"}]}],
        [{"items": [duplicate, duplicate]}],
    )
    service.user_lookup.lookup_by_id = MagicMock(return_value=selected_user())  # type: ignore[method-assign]

    with pytest.raises(GoogleWorkspaceError) as caught:
        service.list_user_assignments(
            actor=actor,
            organization_id=connector.organization_id,
            user_id="109999999999999999999",
        )

    assert caught.value.code == GoogleWorkspaceErrorCode.GOOGLE_API_ERROR


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
    assert assignment.assignee_type == "SERVICE_ACCOUNT"
    assert assignment.scope_type == "UNKNOWN"


def test_resolves_verified_user_by_immutable_id_and_customer(db_session: Session) -> None:
    assignment = {
        "roleAssignmentId": "2001",
        "roleId": "1001",
        "assignedTo": "109999999999999999999",
        "assigneeType": "USER",
        "scopeType": "CUSTOMER",
    }
    service, _, connector, actor = role_service(db_session, [], [], assignment_detail=assignment)
    user = GoogleWorkspaceUserLookupResult(
        id=assignment["assignedTo"],
        customer_id="customer-immutable-1",
        full_name="Verified Administrator",
        primary_email="verified@example.test",
        aliases=[],
        non_editable_aliases=[],
        suspended=True,
        archived=False,
        org_unit_path="/",
        is_mailbox_setup=True,
        matched_by="immutable_id",
    )
    service.user_lookup.lookup_by_id = MagicMock(return_value=user)  # type: ignore[attr-defined]

    resolved_assignment, principal = service.get_assignment_principal(
        actor=actor,
        organization_id=connector.organization_id,
        assignment_id="2001",
    )

    assert resolved_assignment.assigned_to == assignment["assignedTo"]
    assert principal == WorkspaceAdminPrincipal(
        outcome="verified",
        identity_type="USER",
        principal_id=assignment["assignedTo"],
        primary_email="verified@example.test",
        display_name="Verified Administrator",
        account_status="SUSPENDED",
    )
    service.user_lookup.lookup_by_id.assert_called_once_with(  # type: ignore[attr-defined]
        actor=actor,
        organization_id=connector.organization_id,
        user_id=assignment["assignedTo"],
    )


def test_rejects_cross_tenant_user_resolution(db_session: Session) -> None:
    assignment = {
        "roleAssignmentId": "2001",
        "roleId": "1001",
        "assignedTo": "109999999999999999999",
        "assigneeType": "USER",
        "scopeType": "CUSTOMER",
    }
    service, _, connector, actor = role_service(db_session, [], [], assignment_detail=assignment)
    service.user_lookup.lookup_by_id = MagicMock(  # type: ignore[attr-defined]
        return_value=GoogleWorkspaceUserLookupResult(
            id=assignment["assignedTo"],
            customer_id="different-customer",
            full_name=None,
            primary_email="other@example.test",
            aliases=[],
            non_editable_aliases=[],
            suspended=False,
            archived=False,
            org_unit_path="/",
            is_mailbox_setup=True,
            matched_by="immutable_id",
        )
    )
    with pytest.raises(GoogleWorkspaceError) as error:
        service.get_assignment_principal(
            actor=actor,
            organization_id=connector.organization_id,
            assignment_id="2001",
        )
    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH


def test_resolves_group_only_with_customer_scoped_inventory_proof(db_session: Session) -> None:
    principal_id = "109888888888888888888"
    assignment = {
        "roleAssignmentId": "2001",
        "roleId": "1001",
        "assignedTo": principal_id,
        "assigneeType": "GROUP",
        "scopeType": "CUSTOMER",
    }
    service, factory, connector, actor = role_service(
        db_session, [], [], assignment_detail=assignment
    )
    group_resource = PagedResource(
        [{"groups": [{"id": principal_id, "email": "admins@example.test", "name": "Admins"}]}],
        {"id": principal_id, "email": "admins@example.test", "name": "Admins"},
    )
    group_client = MagicMock()
    group_client.groups.return_value = group_resource
    group_client._http = FakeHttp()
    factory.for_directory_groups = MagicMock(return_value=group_client)  # type: ignore[attr-defined]

    _, principal = service.get_assignment_principal(
        actor=actor,
        organization_id=connector.organization_id,
        assignment_id="2001",
    )

    assert principal.outcome == "verified"
    assert principal.identity_type == "GROUP"
    assert principal.primary_email == "admins@example.test"
    factory.for_directory_groups.assert_called_once_with(  # type: ignore[attr-defined]
        actor=actor,
        organization_id=connector.organization_id,
        scopes=(DIRECTORY_GROUP_READONLY_SCOPE,),
    )
    assert group_resource.get_calls == [{"groupKey": principal_id, "fields": "id,email,name"}]
    assert group_resource.calls[0]["customer"] == "customer-immutable-1"
    assert group_resource.calls[0]["maxResults"] == 10
    assert all(request.execute_kwargs == {"num_retries": 0} for request in group_resource.requests)
    assert group_client._http.closed is True


def test_untyped_principal_stays_unresolved_when_customer_indexes_do_not_match(
    db_session: Session,
) -> None:
    service, factory, connector, actor = role_service(
        db_session,
        [],
        [],
        assignment_detail={
            "roleAssignmentId": "2001",
            "roleId": "1001",
            "assignedTo": "opaque-principal",
            "assigneeType": "FUTURE",
            "scopeType": "CUSTOMER",
        },
    )
    user_resource = PagedResource([{"users": []}])
    group_resource = PagedResource([{"groups": []}])
    user_client = MagicMock()
    user_client.users.return_value = user_resource
    user_client._http = FakeHttp()
    group_client = MagicMock()
    group_client.groups.return_value = group_resource
    group_client._http = FakeHttp()
    factory.for_directory_users = MagicMock(return_value=user_client)  # type: ignore[attr-defined]
    factory.for_directory_groups = MagicMock(return_value=group_client)  # type: ignore[attr-defined]
    service.user_lookup.lookup_by_id = MagicMock()  # type: ignore[attr-defined]

    _, principal = service.get_assignment_principal(
        actor=actor,
        organization_id=connector.organization_id,
        assignment_id="2001",
    )

    assert principal.outcome == "unresolved"
    assert principal.identity_type == "UNKNOWN"
    assert principal.reason == "principal_not_found_in_customer_indexes"
    service.user_lookup.lookup_by_id.assert_not_called()  # type: ignore[attr-defined]
    assert user_resource.calls[0]["customer"] == "customer-immutable-1"
    assert group_resource.calls[0]["customer"] == "customer-immutable-1"
    assert all(request.execute_kwargs == {"num_retries": 0} for request in user_resource.requests)
    assert all(request.execute_kwargs == {"num_retries": 0} for request in group_resource.requests)


def test_explicit_service_account_is_unsupported_without_directory_probing(
    db_session: Session,
) -> None:
    service, factory, connector, actor = role_service(
        db_session,
        [],
        [],
        assignment_detail={
            "roleAssignmentId": "2001",
            "roleId": "1001",
            "assignedTo": "opaque-principal",
            "assigneeType": "SERVICE_ACCOUNT",
            "scopeType": "CUSTOMER",
        },
    )
    service.user_lookup.lookup_by_id = MagicMock()  # type: ignore[attr-defined]
    _, principal = service.get_assignment_principal(
        actor=actor,
        organization_id=connector.organization_id,
        assignment_id="2001",
    )
    assert principal.outcome == "unsupported"
    service.user_lookup.lookup_by_id.assert_not_called()  # type: ignore[attr-defined]
    assert not hasattr(factory, "for_directory_groups")
    assert not hasattr(factory, "for_directory_users")


def test_untyped_principal_resolves_only_after_unique_customer_user_index_match(
    db_session: Session,
) -> None:
    principal_id = "109999999999999999999"
    service, factory, connector, actor = role_service(
        db_session,
        [],
        [],
        assignment_detail={
            "roleAssignmentId": "2001",
            "roleId": "1001",
            "assignedTo": principal_id,
            "scopeType": "CUSTOMER",
        },
    )
    user_resource = PagedResource(
        [{"users": [], "nextPageToken": "next"}, {"users": [{"id": principal_id}]}]
    )
    group_resource = PagedResource([{"groups": []}])
    user_client = MagicMock()
    user_client.users.return_value = user_resource
    user_client._http = FakeHttp()
    group_client = MagicMock()
    group_client.groups.return_value = group_resource
    group_client._http = FakeHttp()
    factory.for_directory_users = MagicMock(return_value=user_client)  # type: ignore[attr-defined]
    factory.for_directory_groups = MagicMock(return_value=group_client)  # type: ignore[attr-defined]
    service.user_lookup.lookup_by_id = MagicMock(  # type: ignore[attr-defined]
        return_value=GoogleWorkspaceUserLookupResult(
            id=principal_id,
            customer_id="customer-immutable-1",
            full_name="Verified Administrator",
            primary_email="verified@example.test",
            aliases=[],
            non_editable_aliases=[],
            suspended=False,
            archived=False,
            org_unit_path="/",
            is_mailbox_setup=True,
            matched_by="immutable_id",
        )
    )

    _, principal = service.get_assignment_principal(
        actor=actor,
        organization_id=connector.organization_id,
        assignment_id="2001",
    )

    assert principal.outcome == "verified"
    assert principal.identity_type == "USER"
    assert user_resource.calls[1]["pageToken"] == "next"
    service.user_lookup.lookup_by_id.assert_called_once()  # type: ignore[attr-defined]


def test_untyped_principal_conflicting_customer_indexes_are_ambiguous(
    db_session: Session,
) -> None:
    principal_id = "109999999999999999999"
    service, factory, connector, actor = role_service(
        db_session,
        [],
        [],
        assignment_detail={
            "roleAssignmentId": "2001",
            "roleId": "1001",
            "assignedTo": principal_id,
            "scopeType": "CUSTOMER",
        },
    )
    user_resource = PagedResource([{"users": [{"id": principal_id}]}])
    group_resource = PagedResource([{"groups": [{"id": principal_id}]}])
    user_client = MagicMock()
    user_client.users.return_value = user_resource
    user_client._http = FakeHttp()
    group_client = MagicMock()
    group_client.groups.return_value = group_resource
    group_client._http = FakeHttp()
    factory.for_directory_users = MagicMock(return_value=user_client)  # type: ignore[attr-defined]
    factory.for_directory_groups = MagicMock(return_value=group_client)  # type: ignore[attr-defined]
    service.user_lookup.lookup_by_id = MagicMock()  # type: ignore[attr-defined]

    _, principal = service.get_assignment_principal(
        actor=actor,
        organization_id=connector.organization_id,
        assignment_id="2001",
    )

    assert principal.outcome == "ambiguous"
    assert principal.identity_type == "UNKNOWN"
    assert principal.reason == "conflicting_customer_identity_indexes"
    service.user_lookup.lookup_by_id.assert_not_called()  # type: ignore[attr-defined]


def test_identity_authorization_failure_is_not_reported_as_not_found(db_session: Session) -> None:
    service, _, connector, actor = role_service(
        db_session,
        [],
        [],
        assignment_detail={
            "roleAssignmentId": "2001",
            "roleId": "1001",
            "assignedTo": "109999999999999999999",
            "assigneeType": "USER",
            "scopeType": "CUSTOMER",
        },
    )
    service.user_lookup.lookup_by_id = MagicMock(  # type: ignore[attr-defined]
        side_effect=GoogleWorkspaceError(GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION)
    )
    _, principal = service.get_assignment_principal(
        actor=actor,
        organization_id=connector.organization_id,
        assignment_id="2001",
    )
    assert principal.outcome == "lookup_unavailable"
    assert principal.reason == "identity_lookup_permission_unavailable"


def test_missing_user_is_unresolved_without_cross_type_guessing(db_session: Session) -> None:
    service, factory, connector, actor = role_service(
        db_session,
        [],
        [],
        assignment_detail={
            "roleAssignmentId": "2001",
            "roleId": "1001",
            "assignedTo": "109999999999999999999",
            "assigneeType": "USER",
            "scopeType": "CUSTOMER",
        },
    )
    service.user_lookup.lookup_by_id = MagicMock(  # type: ignore[attr-defined]
        side_effect=GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_USER_NOT_FOUND)
    )
    _, principal = service.get_assignment_principal(
        actor=actor,
        organization_id=connector.organization_id,
        assignment_id="2001",
    )
    assert principal.outcome == "unresolved"
    assert principal.reason == "directory_user_not_found"
    assert not hasattr(factory, "for_directory_groups")


@pytest.mark.parametrize(
    ("inventory_groups", "outcome", "reason"),
    [
        ([], "unresolved", "tenant_ownership_not_verified"),
        (
            [
                {"id": "109888888888888888888", "email": "admins@example.test"},
                {"id": "109888888888888888888", "email": "admins@example.test"},
            ],
            "ambiguous",
            "conflicting_customer_inventory",
        ),
    ],
)
def test_group_ownership_must_be_unique_in_customer_inventory(
    db_session: Session,
    inventory_groups: list[dict[str, str]],
    outcome: str,
    reason: str,
) -> None:
    principal_id = "109888888888888888888"
    service, factory, connector, actor = role_service(
        db_session,
        [],
        [],
        assignment_detail={
            "roleAssignmentId": "2001",
            "roleId": "1001",
            "assignedTo": principal_id,
            "assigneeType": "GROUP",
            "scopeType": "CUSTOMER",
        },
    )
    group_resource = PagedResource(
        [{"groups": inventory_groups}],
        {"id": principal_id, "email": "admins@example.test", "name": "Admins"},
    )
    group_client = MagicMock()
    group_client.groups.return_value = group_resource
    group_client._http = FakeHttp()
    factory.for_directory_groups = MagicMock(return_value=group_client)  # type: ignore[attr-defined]
    _, principal = service.get_assignment_principal(
        actor=actor,
        organization_id=connector.organization_id,
        assignment_id="2001",
    )
    assert principal.outcome == outcome
    assert principal.reason == reason


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


def test_principal_endpoint_returns_verified_identity_and_redacts_audit(
    client: TestClient,
    db_session: Session,
    auth_headers: dict[str, str],
) -> None:
    connector, _ = create_connector(db_session)
    assignment = WorkspaceRoleAssignment(
        "2001",
        "1001",
        "private-principal-id",
        "USER",
        "CUSTOMER",
        None,
        None,
    )
    principal = WorkspaceAdminPrincipal(
        outcome="verified",
        identity_type="USER",
        principal_id="private-principal-id",
        primary_email="private-admin@example.test",
        display_name="Private Admin",
        account_status="ACTIVE",
    )
    service = MagicMock()
    service.get_assignment_principal.return_value = (assignment, principal)
    with patch("app.api.v1.router.GoogleWorkspaceAdminRoles.from_settings", return_value=service):
        response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/"
            "admin-role-assignments/resolve-principal",
            headers=auth_headers,
            json={"id": "2001"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["principal"]["outcome"] == "verified"
    assert body["principal"]["primary_email"] == "private-admin@example.test"
    assert body["effective_permissions_included"] is False
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "google_workspace.admin_role_assignment.principal_resolved"
        )
    )
    assert event is not None
    serialized = str(event.metadata_json)
    assert "private-principal-id" not in serialized
    assert "private-admin@example.test" not in serialized
    assert "Private Admin" not in serialized
    assert event.metadata_json["resolution_outcome"] == "verified"


@pytest.mark.parametrize(
    "path",
    [
        "admin-roles/get",
        "admin-role-assignments/get",
        "admin-role-assignments/resolve-principal",
    ],
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
    [
        "admin-roles/get",
        "admin-role-assignments/get",
        "admin-role-assignments/resolve-principal",
    ],
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


def test_per_user_endpoint_returns_classified_assignments_and_redacted_audit(
    client: TestClient,
    db_session: Session,
    auth_headers: dict[str, str],
) -> None:
    connector, _ = create_connector(db_session)
    role = WorkspaceAdminRole(
        role_id="1001",
        name="Help Desk",
        description=None,
        is_system_role=True,
        is_super_admin_role=False,
        privileges=(),
    )
    assignment = WorkspaceRoleAssignment(
        assignment_id="2001",
        role_id="1001",
        assigned_to="109999999999999999999",
        assignee_type="USER",
        scope_type="CUSTOMER",
        org_unit_id=None,
        condition=None,
    )
    principal = WorkspaceAdminPrincipal(
        outcome="verified",
        identity_type="USER",
        principal_id="109999999999999999999",
        primary_email="selected@example.test",
        display_name="Selected User",
        account_status="ACTIVE",
    )
    service = MagicMock()
    service.list_user_assignments.return_value = WorkspaceUserRoleAssignmentInventory(
        user=selected_user(),
        assignments=(
            WorkspaceUserRoleAssignment(
                assignment=assignment,
                role=role,
                provenance="DIRECT",
                principal=principal,
            ),
        ),
    )
    with patch("app.api.v1.router.GoogleWorkspaceAdminRoles.from_settings", return_value=service):
        response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/"
            "users/admin-role-assignments/list",
            headers=auth_headers,
            json={"user_id": "109999999999999999999"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["direct_count"] == 1
    assert body["group_derived_count"] == 0
    assert body["assignments"][0]["provenance"] == "DIRECT"
    assert body["effective_permissions_included"] is False
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "google_workspace.user_admin_role_assignments.listed"
        )
    )
    assert event is not None
    serialized = str(event.metadata_json)
    assert "109999999999999999999" not in serialized
    assert "selected@example.test" not in serialized
    assert event.metadata_json["direct_count"] == 1


def test_per_user_endpoint_rejects_invalid_id_before_service(
    client: TestClient,
    db_session: Session,
    auth_headers: dict[str, str],
) -> None:
    connector, _ = create_connector(db_session)
    with patch("app.api.v1.router.GoogleWorkspaceAdminRoles.from_settings") as factory:
        response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/"
            "users/admin-role-assignments/list",
            headers=auth_headers,
            json={"user_id": "not-an-id"},
        )
    assert response.status_code == 422
    factory.assert_not_called()


def test_cross_customer_actor_cannot_query_per_user_assignments(
    client: TestClient, db_session: Session
) -> None:
    connector, _ = create_connector(db_session)
    add_user(db_session, "per-user-role-outsider@example.local")
    headers = login_headers(client, "per-user-role-outsider@example.local")
    with patch("app.api.v1.router.GoogleWorkspaceAdminRoles.from_settings") as factory:
        response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/"
            "users/admin-role-assignments/list",
            headers=headers,
            json={"user_id": "109999999999999999999"},
        )
    assert response.status_code == 403
    factory.assert_not_called()
    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "google_workspace.user_admin_role_assignments.listed"
        )
    )
    assert event is not None
    assert event.metadata_json["google_reported_indirect_requested"] is True
    assert event.metadata_json["effective_permissions_included"] is False


@pytest.mark.parametrize(
    ("code", "status_code"),
    [
        (GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION, 403),
        (GoogleWorkspaceErrorCode.GOOGLE_USER_NOT_FOUND, 404),
        (GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED, 429),
        (GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE, 503),
        (GoogleWorkspaceErrorCode.GOOGLE_NETWORK_ERROR, 503),
    ],
)
def test_per_user_endpoint_maps_sanitized_errors(
    client: TestClient,
    db_session: Session,
    auth_headers: dict[str, str],
    code: GoogleWorkspaceErrorCode,
    status_code: int,
) -> None:
    connector, _ = create_connector(db_session)
    service = MagicMock()
    service.list_user_assignments.side_effect = GoogleWorkspaceError(code)
    with patch("app.api.v1.router.GoogleWorkspaceAdminRoles.from_settings", return_value=service):
        response = client.post(
            f"/api/v1/organizations/{connector.organization_id}/google-workspace/"
            "users/admin-role-assignments/list",
            headers=auth_headers,
            json={"user_id": "109999999999999999999"},
        )
    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == code.value
