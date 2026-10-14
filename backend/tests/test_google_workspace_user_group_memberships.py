from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from googleapiclient.errors import HttpError
from httplib2 import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.google_workspace_credentials import DIRECTORY_GROUP_READONLY_SCOPE
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
)
from app.models import AuditEvent
from app.services.google_workspace_groups import GoogleWorkspaceGroupsService
from app.services.google_workspace_user_group_memberships import (
    MAX_VERIFICATION_CALLS_PER_PAGE,
    GoogleWorkspaceUserGroupMemberships,
    UserDirectGroupMembership,
    UserGroupMembershipListResult,
)
from app.services.google_workspace_user_lookup import GoogleWorkspaceUserLookupResult
from tests.test_customer_data_scoping import (
    add_membership,
    add_user,
    create_customer,
    create_organization,
    login_headers,
)
from tests.test_google_workspace_connection import create_connector


class FakeRequest:
    def __init__(self, client: FakeDirectoryClient, response: object) -> None:
        self.client = client
        self.response = response

    def execute(self, **kwargs: Any) -> object:
        self.client.calls[-1]["execute_kwargs"] = kwargs
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeResource:
    def __init__(self, client: FakeDirectoryClient, resource: str) -> None:
        self.client = client
        self.resource = resource

    def __getattr__(self, method: str) -> Any:
        def invoke(**kwargs: Any) -> FakeRequest:
            response = self.client.responses.pop(0)
            self.client.calls.append(
                {"resource": self.resource, "method": method, "kwargs": kwargs}
            )
            return FakeRequest(self.client, response)

        return invoke


class FakeDirectoryClient:
    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def groups(self) -> FakeResource:
        return FakeResource(self, "groups")

    def members(self) -> FakeResource:
        return FakeResource(self, "members")

    def close(self) -> None:
        self.closed = True


class FakeClientFactory:
    def __init__(self, client: FakeDirectoryClient) -> None:
        self.client = client
        self.calls: list[dict[str, Any]] = []

    def for_directory_groups(self, **kwargs: Any) -> FakeDirectoryClient:
        self.calls.append(kwargs)
        return self.client


class FakeUserLookup:
    def __init__(self, selected: GoogleWorkspaceUserLookupResult) -> None:
        self.selected = selected
        self.calls: list[str] = []

    def lookup(self, **kwargs: Any) -> GoogleWorkspaceUserLookupResult:
        email = str(kwargs["email"]).casefold()
        self.calls.append(email)
        if email == "admin@example.com":
            return user_identity("admin@example.com", "admin-id")
        return self.selected


def user_identity(
    primary_email: str = "person@primary.example",
    google_id: str = "user-id",
    *,
    customer_id: str = "google-customer-1",
    matched_by: str = "primary_email",
) -> GoogleWorkspaceUserLookupResult:
    return GoogleWorkspaceUserLookupResult(
        id=google_id,
        customer_id=customer_id,
        full_name="Synthetic Person",
        primary_email=primary_email,
        aliases=["alias@secondary.example"],
        non_editable_aliases=[],
        suspended=False,
        archived=False,
        org_unit_path="/Engineering",
        is_mailbox_setup=True,
        matched_by=matched_by,  # type: ignore[arg-type]
    )


def group(group_id: str, email: str, name: str = "Synthetic Group") -> dict[str, str]:
    return {"id": group_id, "email": email, "name": name}


def member(role: str = "MEMBER", **overrides: str) -> dict[str, str]:
    value = {
        "id": "user-id",
        "email": "person@primary.example",
        "role": role,
        "type": "USER",
        "status": "ACTIVE",
    }
    value.update(overrides)
    return value


def service_with_client(
    db_session: Session,
    client: FakeDirectoryClient,
    *,
    selected: GoogleWorkspaceUserLookupResult | None = None,
) -> tuple[GoogleWorkspaceUserGroupMemberships, FakeClientFactory, FakeUserLookup, UUID, Any]:
    connector, actor = create_connector(db_session)
    lookup = FakeUserLookup(selected or user_identity())
    factory = FakeClientFactory(client)
    groups = GoogleWorkspaceGroupsService(db_session, factory, lookup)  # type: ignore[arg-type]
    service = GoogleWorkspaceUserGroupMemberships(
        factory,  # type: ignore[arg-type]
        lookup,  # type: ignore[arg-type]
        groups,
    )
    return service, factory, lookup, connector.organization_id, actor


def list_memberships(
    service: GoogleWorkspaceUserGroupMemberships,
    actor: Any,
    organization_id: UUID,
    **overrides: Any,
) -> UserGroupMembershipListResult:
    values = {
        "email": "person@primary.example",
        "page_size": 10,
        "page_token": None,
    }
    values.update(overrides)
    return service.list_memberships(actor=actor, organization_id=organization_id, **values)


def test_lists_only_verified_direct_current_tenant_memberships(db_session: Session) -> None:
    direct = group("group-direct", "team@secondary.example", "Direct Team")
    external = group("group-external", "outside@external.example", "External Team")
    indirect = group("group-indirect", "nested@primary.example", "Nested Team")
    not_direct = HttpError(Response({"status": "404"}), b"private indirect detail")
    client = FakeDirectoryClient(
        {"groups": [direct, external, indirect], "nextPageToken": "opaque-next"},
        {"groups": [direct]},
        member("MANAGER"),
        {"groups": []},
        {"groups": [indirect]},
        not_direct,
    )
    selected = user_identity(matched_by="alias")
    service, factory, lookup, organization_id, actor = service_with_client(
        db_session, client, selected=selected
    )

    result = list_memberships(
        service,
        actor,
        organization_id,
        email="alias@secondary.example",
        page_size=25,
        page_token="opaque-current",
    )

    assert result.user_id == "user-id"
    assert result.user_primary_email == "person@primary.example"
    assert result.matched_by == "alias"
    assert [(item.group_id, item.role) for item in result.memberships] == [
        ("group-direct", "MANAGER")
    ]
    assert result.next_page_token == "opaque-next"
    assert result.verification_complete is True
    assert result.candidates_examined == 3
    assert result.omitted_external_count == 1
    assert result.omitted_indirect_count == 1
    assert lookup.calls == ["admin@example.com", "alias@secondary.example"]
    assert factory.calls == [
        {
            "actor": actor,
            "organization_id": organization_id,
            "scopes": (DIRECTORY_GROUP_READONLY_SCOPE,),
        }
    ]
    first_call = client.calls[0]
    assert first_call["kwargs"]["userKey"] == "user-id"
    assert first_call["kwargs"]["pageToken"] == "opaque-current"
    assert first_call["kwargs"]["maxResults"] == 25
    assert "customer" not in first_call["kwargs"]
    assert "domain" not in first_call["kwargs"]
    assert all(call["execute_kwargs"] == {"num_retries": 0} for call in client.calls)
    assert all(call["method"] in {"list", "get"} for call in client.calls)
    assert client.closed is True


@pytest.mark.parametrize("role", ["MEMBER", "MANAGER", "OWNER"])
def test_verifies_each_supported_direct_membership_role(
    db_session: Session, role: str
) -> None:
    candidate = group("group-1", "team@primary.example")
    client = FakeDirectoryClient(
        {"groups": [candidate]},
        {"groups": [candidate]},
        member(role),
    )
    service, _, _, organization_id, actor = service_with_client(db_session, client)

    result = list_memberships(service, actor, organization_id)

    assert result.memberships[0].role == role
    member_call = client.calls[2]
    assert member_call["resource"] == "members"
    assert member_call["method"] == "get"
    assert member_call["kwargs"]["groupKey"] == "group-1"
    assert member_call["kwargs"]["memberKey"] == "user-id"


def test_empty_candidate_page_preserves_continuation_token(db_session: Session) -> None:
    client = FakeDirectoryClient({"groups": [], "nextPageToken": "empty-next"})
    service, _, _, organization_id, actor = service_with_client(db_session, client)

    result = list_memberships(service, actor, organization_id)

    assert result.memberships == []
    assert result.next_page_token == "empty-next"
    assert result.candidates_examined == 0
    assert result.verification_complete is True


def test_selected_user_must_match_verified_google_customer(db_session: Session) -> None:
    selected = user_identity(customer_id="different-google-customer")
    client = FakeDirectoryClient()
    service, factory, _, organization_id, actor = service_with_client(
        db_session, client, selected=selected
    )

    with pytest.raises(GoogleWorkspaceError) as error:
        list_memberships(service, actor, organization_id)

    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH
    assert factory.calls == []


def test_mismatched_direct_member_identity_is_rejected(db_session: Session) -> None:
    candidate = group("group-1", "team@primary.example")
    client = FakeDirectoryClient(
        {"groups": [candidate]},
        {"groups": [candidate]},
        member(id="foreign-user", email="foreign@example.test"),
    )
    service, _, _, organization_id, actor = service_with_client(db_session, client)

    with pytest.raises(GoogleWorkspaceError) as error:
        list_memberships(service, actor, organization_id)

    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH


def test_large_google_page_is_stopped_before_verification_budget_is_exceeded(
    db_session: Session,
) -> None:
    candidates = [
        group(f"group-{index}", f"group-{index}@primary.example")
        for index in range((MAX_VERIFICATION_CALLS_PER_PAGE // 2) + 1)
    ]
    client = FakeDirectoryClient({"groups": candidates, "nextPageToken": "more"})
    service, _, _, organization_id, actor = service_with_client(db_session, client)

    with pytest.raises(GoogleWorkspaceError) as error:
        list_memberships(service, actor, organization_id, page_size=25)

    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_OPERATION_BUDGET_EXCEEDED
    assert len(client.calls) == 1


def test_invalid_or_expired_page_token_is_sanitized(db_session: Session) -> None:
    upstream = HttpError(
        Response({"status": "400"}), b'{"error":{"message":"private expired token"}}'
    )
    client = FakeDirectoryClient(upstream)
    service, _, _, organization_id, actor = service_with_client(db_session, client)

    with pytest.raises(GoogleWorkspaceError) as error:
        list_memberships(
            service, actor, organization_id, page_token="private-opaque-token"
        )

    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_PAGE_TOKEN_INVALID
    assert "private" not in str(error.value)
    assert "opaque" not in str(error.value)


def test_ownership_failure_is_not_mislabeled_as_invalid_page_token(
    db_session: Session,
) -> None:
    candidate = group("group-1", "team@primary.example")
    upstream = HttpError(Response({"status": "400"}), b"private ownership detail")
    client = FakeDirectoryClient({"groups": [candidate]}, upstream)
    service, _, _, organization_id, actor = service_with_client(db_session, client)

    with pytest.raises(GoogleWorkspaceError) as error:
        list_memberships(
            service, actor, organization_id, page_token="valid-opaque-token"
        )

    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_API_ERROR
    assert "private" not in str(error.value)


@pytest.mark.parametrize(
    ("upstream", "expected"),
    [
        (
            HttpError(Response({"status": "401"}), b"private"),
            GoogleWorkspaceErrorCode.GOOGLE_UNAUTHORIZED,
        ),
        (
            HttpError(Response({"status": "403"}), b"private"),
            GoogleWorkspaceErrorCode.GOOGLE_FORBIDDEN,
        ),
        (
            HttpError(Response({"status": "404"}), b"private"),
            GoogleWorkspaceErrorCode.GOOGLE_SUBJECT_NOT_FOUND,
        ),
        (
            HttpError(Response({"status": "429"}), b"private"),
            GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED,
        ),
        (
            HttpError(Response({"status": "503"}), b"private"),
            GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE,
        ),
        (TimeoutError("private timeout"), GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT),
    ],
)
def test_google_failures_are_typed_without_sensitive_details(
    db_session: Session, upstream: Exception, expected: GoogleWorkspaceErrorCode
) -> None:
    client = FakeDirectoryClient(upstream)
    service, _, _, organization_id, actor = service_with_client(db_session, client)

    with pytest.raises(GoogleWorkspaceError) as error:
        list_memberships(service, actor, organization_id)

    assert error.value.code == expected
    assert "private" not in str(error.value)


def test_endpoint_returns_minimal_memberships_and_secret_free_audit(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    organization = create_organization(client, auth_headers, None, "Membership Endpoint Org")
    service = MagicMock()
    service.list_memberships.return_value = UserGroupMembershipListResult(
        user_id="user-id",
        user_primary_email="person@primary.example",
        matched_by="alias",
        memberships=[
            UserDirectGroupMembership(
                group_id="group-id",
                group_name="Synthetic Team",
                group_primary_email="team@secondary.example",
                role="OWNER",
                member_type="USER",
                status="ACTIVE",
            )
        ],
        next_page_token="opaque-next",
        verification_complete=True,
        candidates_examined=3,
        omitted_external_count=1,
        omitted_indirect_count=1,
    )
    with patch(
        "app.api.v1.router.GoogleWorkspaceUserGroupMemberships.from_settings",
        return_value=service,
    ):
        response = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/"
            "users/group-memberships",
            json={"email": "alias@secondary.example", "page_size": 10},
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["memberships"] == [
        {
            "group_id": "group-id",
            "group_name": "Synthetic Team",
            "group_primary_email": "team@secondary.example",
            "role": "OWNER",
            "member_type": "USER",
            "status": "ACTIVE",
        }
    ]
    assert "credential" not in str(body).lower()
    event = db_session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.object_id == organization["id"],
            AuditEvent.action == "google_workspace.user_group_memberships.listed",
        )
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.metadata_json is not None
    assert event.metadata_json["matched_by"] == "alias"
    assert "alias@" not in str(event.metadata_json)
    assert "opaque" not in str(event.metadata_json)


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email"},
        {"email": "person@example.test", "page_size": 50},
        {"email": "person@example.test", "page_token": "x" * 2049},
    ],
)
def test_endpoint_rejects_invalid_input_before_service_creation(
    client: TestClient, auth_headers: dict[str, str], payload: dict[str, object]
) -> None:
    organization = create_organization(client, auth_headers, None, "Invalid Membership Org")
    with patch(
        "app.api.v1.router.GoogleWorkspaceUserGroupMemberships.from_settings"
    ) as factory:
        response = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/"
            "users/group-memberships",
            json=payload,
            headers=auth_headers,
        )

    assert response.status_code == 422
    factory.assert_not_called()


def test_cross_tenant_access_is_denied_before_credentials(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    own_customer = create_customer(client, auth_headers, "Membership Own Customer")
    other_customer = create_customer(client, auth_headers, "Membership Other Customer")
    other_organization = create_organization(
        client, auth_headers, other_customer["id"], "Membership Other Organization"
    )
    actor = add_user(db_session, "membership-admin@example.test")
    add_membership(db_session, actor, own_customer["id"], "customer_admin")
    headers = login_headers(client, actor.email)

    with patch(
        "app.api.v1.router.GoogleWorkspaceUserGroupMemberships.from_settings"
    ) as factory:
        response = client.post(
            f"/api/v1/organizations/{other_organization['id']}/google-workspace/"
            "users/group-memberships",
            json={"email": "person@example.test"},
            headers=headers,
        )

    assert response.status_code == 403
    factory.assert_not_called()


def test_endpoint_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000001/"
        "google-workspace/users/group-memberships",
        json={"email": "person@example.test"},
    )

    assert response.status_code == 401
