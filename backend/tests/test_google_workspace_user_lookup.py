from __future__ import annotations

from unittest.mock import patch
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
from app.services.google_workspace_user_lookup import (
    USER_LOOKUP_FIELDS,
    GoogleWorkspaceUserLookup,
)
from tests.test_customer_data_scoping import (
    add_membership,
    add_user,
    create_customer,
    create_organization,
    login_headers,
)
from tests.test_google_workspace_connection import (
    FakeClientFactory,
    FakeGoogleClient,
    create_connector,
)


def lookup_response(**overrides: object) -> dict[str, object]:
    response: dict[str, object] = {
        "id": "google-user-123",
        "primaryEmail": "person@primary.example",
        "customerId": "workspace-customer-123",
        "name": {"fullName": "Example Person"},
        "aliases": ["person.alias@primary.example", "person@secondary.example"],
        "nonEditableAliases": ["person@legacy.example"],
        "suspended": False,
        "archived": False,
        "orgUnitPath": "/Engineering",
        "isMailboxSetup": True,
    }
    response.update(overrides)
    return response


def test_lookup_by_primary_email_uses_exact_read_only_directory_request(
    db_session: Session,
) -> None:
    connector, actor = create_connector(db_session)
    client = FakeGoogleClient(lookup_response())
    factory = FakeClientFactory(client)

    result = GoogleWorkspaceUserLookup(factory).lookup(
        actor=actor,
        organization_id=connector.organization_id,
        email="person@primary.example",
    )

    assert result.full_name == "Example Person"
    assert result.primary_email == "person@primary.example"
    assert result.matched_by == "primary_email"
    assert result.aliases == ["person.alias@primary.example", "person@secondary.example"]
    assert result.non_editable_aliases == ["person@legacy.example"]
    assert result.suspended is False
    assert result.archived is False
    assert result.org_unit_path == "/Engineering"
    assert result.is_mailbox_setup is True
    assert factory.calls == [
        {
            "actor": actor,
            "organization_id": connector.organization_id,
            "service": "admin",
            "version": "directory_v1",
            "scopes": [DIRECTORY_USER_READONLY_SCOPE],
        }
    ]
    assert client.users_resource.get_kwargs == {
        "userKey": "person@primary.example",
        "projection": "basic",
        "viewType": "admin_view",
        "fields": USER_LOOKUP_FIELDS,
    }
    assert client.request.execute_kwargs == {"num_retries": 0}
    assert client.closed is True


@pytest.mark.parametrize(
    ("searched_email", "expected_match"),
    [
        ("PERSON.ALIAS@PRIMARY.EXAMPLE", "alias"),
        ("person@secondary.example", "alias"),
        ("person@legacy.example", "non_editable_alias"),
    ],
)
def test_lookup_distinguishes_alias_types_and_allows_multiple_domains(
    db_session: Session,
    searched_email: str,
    expected_match: str,
) -> None:
    connector, actor = create_connector(db_session)

    lookup = GoogleWorkspaceUserLookup(FakeClientFactory(FakeGoogleClient(lookup_response())))
    result = lookup.lookup(
        actor=actor, organization_id=connector.organization_id, email=searched_email
    )

    assert result.matched_by == expected_match
    assert result.primary_email == "person@primary.example"


def test_lookup_handles_no_aliases_and_optional_fields(db_session: Session) -> None:
    connector, actor = create_connector(db_session)
    response = lookup_response(
        aliases=None,
        nonEditableAliases=None,
        name=None,
        archived=None,
        orgUnitPath=None,
        isMailboxSetup=None,
        suspended=True,
    )

    result = GoogleWorkspaceUserLookup(FakeClientFactory(FakeGoogleClient(response))).lookup(
        actor=actor,
        organization_id=connector.organization_id,
        email="person@primary.example",
    )

    assert result.full_name is None
    assert result.aliases == []
    assert result.non_editable_aliases == []
    assert result.suspended is True
    assert result.archived is None
    assert result.org_unit_path is None
    assert result.is_mailbox_setup is None


def test_lookup_rejects_a_response_that_does_not_match_the_requested_address(
    db_session: Session,
) -> None:
    connector, actor = create_connector(db_session)

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        GoogleWorkspaceUserLookup(
            FakeClientFactory(FakeGoogleClient(lookup_response()))
        ).lookup(
            actor=actor,
            organization_id=connector.organization_id,
            email="unrelated@example.net",
        )

    assert exc_info.value.code == GoogleWorkspaceErrorCode.GOOGLE_USER_LOOKUP_MISMATCH


@pytest.mark.parametrize(
    ("upstream_error", "expected_code", "retryable"),
    [
        (
            HttpError(Response({"status": "401"}), b"secret upstream body"),
            GoogleWorkspaceErrorCode.GOOGLE_UNAUTHORIZED,
            False,
        ),
        (
            HttpError(Response({"status": "403"}), b"secret upstream body"),
            GoogleWorkspaceErrorCode.GOOGLE_FORBIDDEN,
            False,
        ),
        (
            HttpError(Response({"status": "429"}), b"secret upstream body"),
            GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED,
            True,
        ),
        (
            HttpError(Response({"status": "503"}), b"secret upstream body"),
            GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE,
            True,
        ),
        (TimeoutError("secret timeout"), GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT, True),
        (OSError("secret network"), GoogleWorkspaceErrorCode.GOOGLE_NETWORK_ERROR, True),
    ],
)
def test_lookup_maps_upstream_failures_without_leaking_details(
    db_session: Session,
    upstream_error: Exception,
    expected_code: GoogleWorkspaceErrorCode,
    retryable: bool,
) -> None:
    connector, actor = create_connector(db_session)

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        GoogleWorkspaceUserLookup(
            FakeClientFactory(FakeGoogleClient(upstream_error))
        ).lookup(
            actor=actor,
            organization_id=connector.organization_id,
            email="person@primary.example",
        )

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is retryable
    assert "secret" not in str(exc_info.value)


def test_lookup_maps_missing_google_user_to_normal_not_found(db_session: Session) -> None:
    connector, actor = create_connector(db_session)
    missing = HttpError(Response({"status": "404"}), b"sensitive upstream response")

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        GoogleWorkspaceUserLookup(FakeClientFactory(FakeGoogleClient(missing))).lookup(
            actor=actor,
            organization_id=connector.organization_id,
            email="missing@example.net",
        )

    assert exc_info.value.code == GoogleWorkspaceErrorCode.GOOGLE_USER_NOT_FOUND
    assert "sensitive" not in str(exc_info.value)


def test_lookup_endpoint_returns_only_typed_safe_fields_and_safe_audit_metadata(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    organization = create_organization(client, auth_headers, None, "Lookup Endpoint Org")
    google_response = lookup_response(
        privateKey="must-not-be-returned",
        access_token="must-not-be-returned",
        customSchemas={"sensitive": "must-not-be-returned"},
    )
    lookup = GoogleWorkspaceUserLookup(FakeClientFactory(FakeGoogleClient(google_response)))

    with patch(
        "app.api.v1.router.GoogleWorkspaceUserLookup.from_settings",
        return_value=lookup,
    ):
        response = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/users/lookup",
            json={"email": "Person.Alias@Primary.Example"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "id": "google-user-123",
        "full_name": "Example Person",
        "primary_email": "person@primary.example",
        "aliases": ["person.alias@primary.example", "person@secondary.example"],
        "non_editable_aliases": ["person@legacy.example"],
        "suspended": False,
        "archived": False,
        "org_unit_path": "/Engineering",
        "is_mailbox_setup": True,
        "matched_by": "alias",
    }
    serialized = str(body)
    assert "private" not in serialized.lower()
    assert "token" not in serialized.lower()
    assert "must-not-be-returned" not in serialized

    event = db_session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.object_id == organization["id"],
            AuditEvent.action == "google_workspace.user_lookup",
        )
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.outcome == "success"
    assert event.metadata_json == {"matched_by": "alias"}
    assert "person.alias" not in str(event.metadata_json).lower()


def test_lookup_endpoint_rejects_invalid_email_before_google_client_creation(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    organization = create_organization(client, auth_headers, None, "Invalid Lookup Org")

    with patch("app.api.v1.router.GoogleWorkspaceUserLookup.from_settings") as factory:
        response = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/users/lookup",
            json={"email": "not-an-email"},
            headers=auth_headers,
        )

    assert response.status_code == 422
    factory.assert_not_called()


@pytest.mark.parametrize(
    ("error_code", "expected_status"),
    [
        (GoogleWorkspaceErrorCode.GOOGLE_USER_NOT_FOUND, 404),
        (GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION, 403),
        (GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED, 429),
        (GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE, 503),
        (GoogleWorkspaceErrorCode.GOOGLE_NETWORK_ERROR, 503),
        (GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT, 504),
        (GoogleWorkspaceErrorCode.GOOGLE_UNAUTHORIZED, 502),
        (GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED, 409),
    ],
)
def test_lookup_endpoint_returns_distinct_sanitized_errors(
    client: TestClient,
    auth_headers: dict[str, str],
    error_code: GoogleWorkspaceErrorCode,
    expected_status: int,
) -> None:
    organization = create_organization(client, auth_headers, None, "Lookup Error Org")
    lookup = GoogleWorkspaceUserLookup(FakeClientFactory(GoogleWorkspaceError(error_code)))

    with patch(
        "app.api.v1.router.GoogleWorkspaceUserLookup.from_settings",
        return_value=lookup,
    ):
        response = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/users/lookup",
            json={"email": "person@example.net"},
            headers=auth_headers,
        )

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == error_code.value
    assert "secret" not in response.text.lower()


def test_customer_admin_cannot_lookup_users_in_another_tenant(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    own_customer = create_customer(client, auth_headers, "Lookup Own Customer")
    other_customer = create_customer(client, auth_headers, "Lookup Other Customer")
    own_organization = create_organization(
        client, auth_headers, own_customer["id"], "Lookup Own Organization"
    )
    other_organization = create_organization(
        client, auth_headers, other_customer["id"], "Lookup Other Organization"
    )
    user = add_user(db_session, "lookup-admin@example.local")
    add_membership(db_session, user, own_customer["id"], "customer_admin")
    customer_headers = login_headers(client, user.email)

    successful_lookup = GoogleWorkspaceUserLookup(
        FakeClientFactory(FakeGoogleClient(lookup_response()))
    )
    with patch(
        "app.api.v1.router.GoogleWorkspaceUserLookup.from_settings",
        return_value=successful_lookup,
    ) as factory:
        own_response = client.post(
            f"/api/v1/organizations/{own_organization['id']}/google-workspace/users/lookup",
            json={"email": "person@primary.example"},
            headers=customer_headers,
        )
        other_response = client.post(
            f"/api/v1/organizations/{other_organization['id']}/google-workspace/users/lookup",
            json={"email": "person@primary.example"},
            headers=customer_headers,
        )

    assert own_response.status_code == 200
    assert other_response.status_code == 403
    assert factory.call_count == 1

    denial_event = db_session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.object_id == other_organization["id"],
            AuditEvent.action == "google_workspace.user_lookup",
        )
        .order_by(AuditEvent.created_at.desc())
    )
    assert denial_event is not None
    assert denial_event.reason == "organization_access_denied"
    assert "person@primary.example" not in str(denial_event.metadata_json)


def test_customer_viewer_cannot_lookup_even_within_own_tenant(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    customer = create_customer(client, auth_headers, "Lookup Viewer Customer")
    organization = create_organization(
        client, auth_headers, customer["id"], "Lookup Viewer Organization"
    )
    viewer = add_user(db_session, "lookup-viewer@example.local")
    add_membership(db_session, viewer, customer["id"], "customer_viewer")
    viewer_headers = login_headers(client, viewer.email)

    with patch("app.api.v1.router.GoogleWorkspaceUserLookup.from_settings") as factory:
        response = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/users/lookup",
            json={"email": "person@primary.example"},
            headers=viewer_headers,
        )

    assert response.status_code == 403
    factory.assert_not_called()


def test_lookup_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/api/v1/organizations/00000000-0000-0000-0000-000000000001/"
        "google-workspace/users/lookup",
        json={"email": "person@example.net"},
    )

    assert response.status_code == 401


def test_lookup_does_not_depend_on_primary_domain(db_session: Session) -> None:
    connector, actor = create_connector(db_session)
    assert connector.primary_domain == "example.com"

    result = GoogleWorkspaceUserLookup(
        FakeClientFactory(FakeGoogleClient(lookup_response()))
    ).lookup(
        actor=actor,
        organization_id=UUID(str(connector.organization_id)),
        email="person@secondary.example",
    )

    assert result.matched_by == "alias"
