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

from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
)
from app.models import AuditEvent
from app.services.google_workspace_connection import DIRECTORY_USER_READONLY_SCOPE
from app.services.google_workspace_user_directory import (
    GoogleWorkspaceDirectoryUser,
    GoogleWorkspaceUserDirectory,
    GoogleWorkspaceUserDirectoryResult,
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
    def __init__(self, response: object) -> None:
        self.response = response
        self.execute_kwargs: dict[str, Any] | None = None

    def execute(self, **kwargs: Any) -> object:
        self.execute_kwargs = kwargs
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeUsersResource:
    def __init__(self, request: FakeRequest) -> None:
        self.request = request
        self.list_kwargs: dict[str, Any] | None = None

    def list(self, **kwargs: Any) -> FakeRequest:
        self.list_kwargs = kwargs
        return self.request


class FakeDirectoryClient:
    def __init__(self, response: object) -> None:
        self.request = FakeRequest(response)
        self.users_resource = FakeUsersResource(self.request)
        self.closed = False

    def users(self) -> FakeUsersResource:
        return self.users_resource

    def close(self) -> None:
        self.closed = True


class FakeClientFactory:
    def __init__(self, client: FakeDirectoryClient) -> None:
        self.client = client
        self.calls: list[dict[str, Any]] = []

    def for_organization(self, **kwargs: Any) -> FakeDirectoryClient:
        self.calls.append(kwargs)
        return self.client


class FakeLookup:
    def __init__(self, customer_id: str = "google-customer-1") -> None:
        self.customer_id = customer_id
        self.calls: list[dict[str, Any]] = []

    def lookup(self, **kwargs: Any) -> GoogleWorkspaceUserLookupResult:
        self.calls.append(kwargs)
        return GoogleWorkspaceUserLookupResult(
            id="admin-id",
            customer_id=self.customer_id,
            full_name="Directory Administrator",
            primary_email="admin@example.com",
            aliases=[],
            non_editable_aliases=[],
            suspended=False,
            archived=False,
            org_unit_path="/",
            is_mailbox_setup=True,
            matched_by="primary_email",
        )


def user_response(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "user-1",
        "customerId": "google-customer-1",
        "primaryEmail": "alex@primary.example",
        "name": {
            "fullName": "Alex Example",
            "givenName": "Alex",
            "familyName": "Example",
        },
        "orgUnitPath": "/Engineering",
        "suspended": False,
        "archived": False,
        "isAdmin": True,
        "isDelegatedAdmin": False,
        "creationTime": "2024-01-02T03:04:05Z",
        "lastLoginTime": "2026-09-10T11:12:13Z",
    }
    value.update(overrides)
    return value


def directory_service(
    db_session: Session, response: object
) -> tuple[GoogleWorkspaceUserDirectory, FakeClientFactory, UUID, Any]:
    connector, actor = create_connector(db_session)
    client = FakeDirectoryClient(response)
    factory = FakeClientFactory(client)
    service = GoogleWorkspaceUserDirectory(
        db_session,
        factory,  # type: ignore[arg-type]
        FakeLookup(),  # type: ignore[arg-type]
    )
    return service, factory, connector.organization_id, actor


def list_users(service: GoogleWorkspaceUserDirectory, actor: Any, organization_id: UUID, **kwargs):
    defaults = {
        "search": "",
        "search_field": "all",
        "org_unit_path": None,
        "suspended": "all",
        "admin_status": "all",
        "archived": "all",
        "order_by": "email",
        "sort_direction": "ascending",
        "page_size": 50,
        "page_token": None,
    }
    defaults.update(kwargs)
    return service.list_users(actor=actor, organization_id=organization_id, **defaults)


def test_list_users_uses_verified_customer_minimal_projection_scope_and_pagination(
    db_session: Session,
) -> None:
    secondary = user_response(
        id="user-2",
        primaryEmail="blair@secondary.example",
        name={"fullName": "Blair Example"},
        lastLoginTime=None,
    )
    service, factory, organization_id, actor = directory_service(
        db_session,
        {"users": [user_response(), secondary], "nextPageToken": "next-page"},
    )

    result = list_users(
        service,
        actor,
        organization_id,
        page_size=25,
        page_token="current-page",
        order_by="family_name",
        sort_direction="descending",
    )

    assert [user.primary_email for user in result.users] == [
        "alex@primary.example",
        "blair@secondary.example",
    ]
    assert result.users[0].creation_time is not None
    assert result.users[1].last_login_time is None
    assert result.next_page_token == "next-page"
    assert factory.calls == [
        {
            "actor": actor,
            "organization_id": organization_id,
            "service": "admin",
            "version": "directory_v1",
            "scopes": [DIRECTORY_USER_READONLY_SCOPE],
        }
    ]
    request = factory.client.users_resource.list_kwargs
    assert request is not None
    assert request["customer"] == "google-customer-1"
    assert "domain" not in request
    assert request["projection"] == "basic"
    assert request["viewType"] == "admin_view"
    assert request["maxResults"] == 25
    assert request["orderBy"] == "familyName"
    assert request["sortOrder"] == "DESCENDING"
    assert request["pageToken"] == "current-page"
    assert "customSchemas" not in request["fields"]
    assert factory.client.request.execute_kwargs == {"num_retries": 0}
    assert factory.client.closed is True


def test_empty_page_preserves_opaque_next_page_token(db_session: Session) -> None:
    service, _, organization_id, actor = directory_service(
        db_session, {"users": [], "nextPageToken": "another-empty-page"}
    )

    result = list_users(service, actor, organization_id)

    assert result.users == []
    assert result.next_page_token == "another-empty-page"


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"search": "alex", "search_field": "all"}, "alex"),
        (
            {"search": "alex@secondary.example", "search_field": "email"},
            "email:alex@secondary.example*",
        ),
        ({"search": "Al", "search_field": "given_name"}, "givenName:Al*"),
        ({"search": "O'Neil", "search_field": "family_name"}, "familyName:O\\'Neil*"),
        ({"search": "Alex Example", "search_field": "full_name"}, "name:'Alex Example'"),
        (
            {
                "org_unit_path": "/People's Team",
                "suspended": "active",
                "admin_status": "delegated_admin",
                "archived": "not_archived",
            },
            "orgUnitPath='/People\\'s Team' isSuspended=false isDelegatedAdmin=true "
            "isArchived=false",
        ),
        (
            {"suspended": "suspended", "admin_status": "super_admin", "archived": "archived"},
            "isSuspended=true isAdmin=true isArchived=true",
        ),
    ],
)
def test_directory_query_uses_only_supported_escaped_clauses(
    kwargs: dict[str, str | None], expected: str
) -> None:
    values: dict[str, Any] = {
        "search": "",
        "search_field": "all",
        "org_unit_path": None,
        "suspended": "all",
        "admin_status": "all",
        "archived": "all",
    }
    values.update(kwargs)

    assert GoogleWorkspaceUserDirectory.build_query(**values) == expected


def test_filters_and_search_are_forwarded_as_server_side_query(db_session: Session) -> None:
    service, factory, organization_id, actor = directory_service(db_session, {"users": []})

    list_users(
        service,
        actor,
        organization_id,
        search="Alex",
        search_field="given_name",
        org_unit_path="/Engineering",
        suspended="active",
        admin_status="super_admin",
        archived="not_archived",
    )

    request = factory.client.users_resource.list_kwargs
    assert request is not None
    assert request["query"] == (
        "givenName:Alex* orgUnitPath='/Engineering' isSuspended=false "
        "isAdmin=true isArchived=false"
    )


def test_cross_tenant_user_in_list_is_rejected(db_session: Session) -> None:
    service, _, organization_id, actor = directory_service(
        db_session,
        {"users": [user_response(customerId="different-customer")]},
    )

    with pytest.raises(GoogleWorkspaceError) as error:
        list_users(service, actor, organization_id)

    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH


def test_expired_or_invalid_page_token_is_sanitized(db_session: Session) -> None:
    upstream = HttpError(
        Response({"status": "400"}), b'{"error":{"message":"private expired token"}}'
    )
    service, _, organization_id, actor = directory_service(db_session, upstream)

    with pytest.raises(GoogleWorkspaceError) as error:
        list_users(service, actor, organization_id, page_token="opaque-expired-token")

    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_PAGE_TOKEN_INVALID
    assert "private" not in str(error.value)
    assert "opaque" not in str(error.value)


@pytest.mark.parametrize(
    ("upstream", "expected_code"),
    [
        (TimeoutError("private directory detail"), GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT),
        (
            HttpError(Response({"status": "401"}), b'{"error":{"message":"private"}}'),
            GoogleWorkspaceErrorCode.GOOGLE_UNAUTHORIZED,
        ),
        (
            HttpError(Response({"status": "403"}), b'{"error":{"message":"private"}}'),
            GoogleWorkspaceErrorCode.GOOGLE_FORBIDDEN,
        ),
        (
            HttpError(Response({"status": "404"}), b'{"error":{"message":"private"}}'),
            GoogleWorkspaceErrorCode.GOOGLE_SUBJECT_NOT_FOUND,
        ),
        (
            HttpError(Response({"status": "429"}), b'{"error":{"message":"private"}}'),
            GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED,
        ),
        (
            HttpError(Response({"status": "503"}), b'{"error":{"message":"private"}}'),
            GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE,
        ),
    ],
)
def test_directory_google_failures_are_typed_without_upstream_details(
    db_session: Session, upstream: Exception, expected_code: GoogleWorkspaceErrorCode
) -> None:
    service, _, organization_id, actor = directory_service(db_session, upstream)

    with pytest.raises(GoogleWorkspaceError) as error:
        list_users(service, actor, organization_id)

    assert error.value.code == expected_code
    assert "private" not in str(error.value)


def test_directory_endpoint_returns_typed_fields_and_safe_audit_metadata(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    organization = create_organization(client, auth_headers, None, "Directory Endpoint Org")
    service = MagicMock()
    service.list_users.return_value = GoogleWorkspaceUserDirectoryResult(
        users=[
            GoogleWorkspaceDirectoryUser(
                id="safe-id",
                full_name="Synthetic Person",
                given_name=None,
                family_name=None,
                primary_email="synthetic@example.test",
                org_unit_path=None,
                suspended=None,
                archived=None,
                is_super_admin=None,
                is_delegated_admin=None,
                creation_time=None,
                last_login_time=None,
            )
        ],
        next_page_token=None,
    )

    with patch(
        "app.api.v1.router.GoogleWorkspaceUserDirectory.from_settings",
        return_value=service,
    ):
        response = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/users/list",
            json={"search": "Synthetic Person", "search_field": "full_name"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["users"][0]["primary_email"] == "synthetic@example.test"
    assert response.json()["users"][0]["creation_time"] is None
    event = db_session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.object_id == organization["id"],
            AuditEvent.action == "google_workspace.user_directory.listed",
        )
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.metadata_json is not None
    assert event.metadata_json["has_search"] is True
    assert "Synthetic" not in str(event.metadata_json)
    assert "synthetic@example.test" not in str(event.metadata_json)


@pytest.mark.parametrize(
    "payload",
    [
        {"page_size": 10},
        {"order_by": "last_login"},
        {"sort_direction": "sideways"},
        {"org_unit_path": "Engineering"},
        {"search": "bad\nquery"},
        {"search": "email:injected*"},
    ],
)
def test_directory_endpoint_rejects_invalid_parameters_before_service_creation(
    client: TestClient,
    auth_headers: dict[str, str],
    payload: dict[str, object],
) -> None:
    organization = create_organization(client, auth_headers, None, "Invalid Directory Org")

    with patch("app.api.v1.router.GoogleWorkspaceUserDirectory.from_settings") as factory:
        response = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/users/list",
            json=payload,
            headers=auth_headers,
        )

    assert response.status_code == 422
    factory.assert_not_called()


def test_cross_tenant_directory_access_is_denied_before_service_creation(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    customer = create_customer(client, auth_headers, "Directory Foreign Customer")
    organization = create_organization(
        client, auth_headers, customer["id"], "Directory Foreign Organization"
    )
    other = create_customer(client, auth_headers, "Directory Other Customer")
    foreign_admin = add_user(db_session, "directory-foreign@example.test")
    add_membership(db_session, foreign_admin, other["id"], "customer_admin")
    headers = login_headers(client, foreign_admin.email)

    with patch("app.api.v1.router.GoogleWorkspaceUserDirectory.from_settings") as factory:
        response = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/users/list",
            json={},
            headers=headers,
        )

    assert response.status_code == 403
    factory.assert_not_called()


def test_directory_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000001/"
        "google-workspace/users/list",
        json={},
    )

    assert response.status_code == 401
