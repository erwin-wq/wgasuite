from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from googleapiclient.errors import HttpError
from httplib2 import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.google_workspace_credentials import (
    DIRECTORY_USER_READONLY_SCOPE,
    DIRECTORY_USER_WRITE_SCOPE,
)
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
)
from app.models import AuditEvent, GoogleWorkspaceUserOrgUnitConfirmation
from app.services.google_workspace_orgunits import OrganizationalUnit
from app.services.google_workspace_user_lookup import GoogleWorkspaceUserLookupResult
from app.services.google_workspace_user_orgunit import (
    GoogleWorkspaceUserOrgUnitReconciliationService,
    GoogleWorkspaceUserOrgUnitService,
    UserOrgUnitMovePreview,
    UserOrgUnitMutationAmbiguousError,
)
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


class FakeUsers:
    def __init__(self, client: FakeDirectoryClient) -> None:
        self.client = client

    def get(self, **kwargs: Any) -> FakeRequest:
        self.client.calls.append({"method": "get", "kwargs": kwargs})
        return FakeRequest(self.client, self.client.response)

    def update(self, **kwargs: Any) -> FakeRequest:
        self.client.calls.append({"method": "update", "kwargs": kwargs})
        return FakeRequest(self.client, self.client.response)


class FakeDirectoryClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def users(self) -> FakeUsers:
        return FakeUsers(self)

    def close(self) -> None:
        self.closed = True


class FakeClientFactory:
    def __init__(self, *clients: FakeDirectoryClient) -> None:
        self.clients = list(clients)
        self.all_clients = list(clients)
        self.calls: list[dict[str, Any]] = []

    def for_directory_users(self, **kwargs: Any) -> FakeDirectoryClient:
        self.calls.append(kwargs)
        return self.clients.pop(0)


class FakeLookup:
    def __init__(self, admin: GoogleWorkspaceUserLookupResult) -> None:
        self.admin = admin

    def lookup(self, **kwargs: Any) -> GoogleWorkspaceUserLookupResult:
        return self.admin


class FakeOrgunits:
    def __init__(self, destination: OrganizationalUnit | Exception) -> None:
        self.destination = destination

    def get_organizational_unit(self, **kwargs: Any) -> OrganizationalUnit:
        if isinstance(self.destination, Exception):
            raise self.destination
        return self.destination


def user_response(
    path: str,
    *,
    google_id: str = "user-1",
    customer_id: str = "google-customer-1",
    is_admin: bool = False,
    is_delegated_admin: bool = False,
    archived: bool = False,
) -> dict[str, object]:
    return {
        "id": google_id,
        "customerId": customer_id,
        "primaryEmail": "person@example.com",
        "aliases": [],
        "nonEditableAliases": [],
        "suspended": False,
        "archived": archived,
        "orgUnitPath": path,
        "isAdmin": is_admin,
        "isDelegatedAdmin": is_delegated_admin,
    }


def lookup_result(
    email: str, google_id: str, *, admin: bool = False
) -> GoogleWorkspaceUserLookupResult:
    return GoogleWorkspaceUserLookupResult(
        id=google_id,
        customer_id="google-customer-1",
        full_name="Example",
        primary_email=email,
        aliases=[],
        non_editable_aliases=[],
        suspended=False,
        archived=False,
        org_unit_path="/",
        is_mailbox_setup=True,
        matched_by="primary_email",
        is_super_admin=admin,
        is_delegated_admin=False,
    )


def destination(unit_id: str = "id:engineering", path: str = "/Engineering") -> OrganizationalUnit:
    return OrganizationalUnit(
        id=unit_id,
        name=path.rsplit("/", 1)[-1] or "Root",
        description=None,
        path=path,
        parent_id="id:root" if path != "/" else None,
        parent_path="/" if path != "/" else None,
    )


def service(
    db: Session,
    *responses: object,
    target_destination: OrganizationalUnit | Exception | None = None,
) -> tuple[GoogleWorkspaceUserOrgUnitService, FakeClientFactory, Any, Any, FakeOrgunits]:
    connector, actor = create_connector(db)
    factory = FakeClientFactory(*(FakeDirectoryClient(value) for value in responses))
    orgunits = FakeOrgunits(target_destination or destination())
    result = GoogleWorkspaceUserOrgUnitService(
        db,
        factory,  # type: ignore[arg-type]
        FakeLookup(lookup_result("admin@example.com", "admin-1", admin=True)),  # type: ignore[arg-type]
        orgunits,  # type: ignore[arg-type]
    )
    return result, factory, connector, actor, orgunits


@pytest.mark.parametrize(
    ("source", "target"),
    [("/", "/Engineering"), ("/Engineering", "/"), ("/Engineering", "/Engineering/Platform")],
)
def test_move_uses_immutable_id_minimal_payload_and_exactly_one_write(
    db_session: Session, source: str, target: str
) -> None:
    target_unit = destination("id:target", target)
    move, factory, connector, actor, _ = service(
        db_session,
        user_response(source),
        user_response(source),
        user_response(target),
        target_destination=target_unit,
    )
    preview = move.preview_move(
        actor=actor,
        organization_id=connector.organization_id,
        user_id="user-1",
        destination_org_unit_id=target_unit.id,
    )
    result = move.execute_move(
        actor=actor,
        organization_id=connector.organization_id,
        confirmation_token=preview.confirmation_token,
    )

    assert result.previous_org_unit_path == source
    assert result.org_unit_path == target
    assert [call["scopes"] for call in factory.calls] == [
        (DIRECTORY_USER_READONLY_SCOPE,),
        (DIRECTORY_USER_READONLY_SCOPE,),
        (DIRECTORY_USER_WRITE_SCOPE,),
    ]
    writes = [
        call
        for client in factory.all_clients
        for call in client.calls
        if call["method"] == "update"
    ]
    assert len(writes) == 1
    assert writes[0]["kwargs"]["userKey"] == "user-1"
    assert writes[0]["kwargs"]["body"] == {"orgUnitPath": target}
    assert set(writes[0]["kwargs"]) == {"userKey", "body", "fields"}
    assert writes[0]["execute_kwargs"] == {"num_retries": 0}


def test_preview_hashes_confirmation_and_rejects_same_ou(db_session: Session) -> None:
    move, _, connector, actor, _ = service(
        db_session,
        user_response("/"),
        target_destination=destination("id:root", "/"),
    )
    with pytest.raises(GoogleWorkspaceError) as same:
        move.preview_move(
            actor=actor,
            organization_id=connector.organization_id,
            user_id="user-1",
            destination_org_unit_id="id:root",
        )
    assert same.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_UNCHANGED

    move, _, connector, actor, _ = service(db_session, user_response("/"))
    preview = move.preview_move(
        actor=actor,
        organization_id=connector.organization_id,
        user_id="user-1",
        destination_org_unit_id="id:engineering",
    )
    confirmation = db_session.scalar(select(GoogleWorkspaceUserOrgUnitConfirmation))
    assert confirmation is not None
    assert confirmation.token_digest != preview.confirmation_token
    assert confirmation.expected_source_path == "/"
    assert confirmation.destination_path == "/Engineering"


@pytest.mark.parametrize("field", ["is_admin", "is_delegated_admin", "archived"])
def test_privileged_or_restricted_user_is_rejected(db_session: Session, field: str) -> None:
    response = user_response("/", **{field: True})
    move, _, connector, actor, _ = service(db_session, response)
    with pytest.raises(GoogleWorkspaceError) as rejected:
        move.preview_move(
            actor=actor,
            organization_id=connector.organization_id,
            user_id="user-1",
            destination_org_unit_id="id:engineering",
        )
    expected = (
        GoogleWorkspaceErrorCode.GOOGLE_USER_ARCHIVED
        if field == "archived"
        else GoogleWorkspaceErrorCode.GOOGLE_USER_ADMIN_PROTECTED
    )
    assert rejected.value.code == expected


@pytest.mark.parametrize("changed", ["source", "destination"])
def test_stale_source_or_destination_rejects_without_write(
    db_session: Session, changed: str
) -> None:
    move, factory, connector, actor, orgunits = service(
        db_session,
        user_response("/"),
        user_response("/Changed" if changed == "source" else "/"),
    )
    preview = move.preview_move(
        actor=actor,
        organization_id=connector.organization_id,
        user_id="user-1",
        destination_org_unit_id="id:engineering",
    )
    if changed == "destination":
        orgunits.destination = destination("id:engineering", "/Renamed")
    with pytest.raises(GoogleWorkspaceError) as stale:
        move.execute_move(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )
    assert stale.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_STATE_CHANGED
    assert all(call["scopes"] != (DIRECTORY_USER_WRITE_SCOPE,) for call in factory.calls)


def test_missing_or_deleted_destination_is_rejected_without_write(db_session: Session) -> None:
    missing = GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_NOT_FOUND)
    move, factory, connector, actor, _ = service(
        db_session, user_response("/"), target_destination=missing
    )

    with pytest.raises(GoogleWorkspaceError) as rejected:
        move.preview_move(
            actor=actor,
            organization_id=connector.organization_id,
            user_id="user-1",
            destination_org_unit_id="id:deleted",
        )

    assert rejected.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_NOT_FOUND
    assert all(call["scopes"] != (DIRECTORY_USER_WRITE_SCOPE,) for call in factory.calls)


def test_expired_and_replayed_confirmation_never_duplicate_write(db_session: Session) -> None:
    move, _, connector, actor, _ = service(
        db_session, user_response("/"), user_response("/"), user_response("/Engineering")
    )
    preview = move.preview_move(
        actor=actor,
        organization_id=connector.organization_id,
        user_id="user-1",
        destination_org_unit_id="id:engineering",
    )
    confirmation = db_session.scalar(select(GoogleWorkspaceUserOrgUnitConfirmation))
    assert confirmation is not None
    confirmation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    with pytest.raises(GoogleWorkspaceError) as expired:
        move.execute_move(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )
    assert expired.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CONFIRMATION_EXPIRED


def test_consumed_confirmation_cannot_be_replayed(db_session: Session) -> None:
    move, factory, connector, actor, _ = service(
        db_session, user_response("/"), user_response("/"), user_response("/Engineering")
    )
    preview = move.preview_move(
        actor=actor,
        organization_id=connector.organization_id,
        user_id="user-1",
        destination_org_unit_id="id:engineering",
    )
    move.execute_move(
        actor=actor,
        organization_id=connector.organization_id,
        confirmation_token=preview.confirmation_token,
    )

    with pytest.raises(GoogleWorkspaceError) as replayed:
        move.execute_move(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )

    assert replayed.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CONFIRMATION_USED
    writes = [
        call
        for client in factory.all_clients
        for call in client.calls
        if call["method"] == "update"
    ]
    assert len(writes) == 1


def test_cross_tenant_target_is_rejected_before_preview(db_session: Session) -> None:
    move, factory, connector, actor, _ = service(
        db_session, user_response("/", customer_id="different-google-customer")
    )

    with pytest.raises(GoogleWorkspaceError) as rejected:
        move.preview_move(
            actor=actor,
            organization_id=connector.organization_id,
            user_id="user-1",
            destination_org_unit_id="id:engineering",
        )

    assert rejected.value.code == GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH
    assert all(call["scopes"] != (DIRECTORY_USER_WRITE_SCOPE,) for call in factory.calls)


def test_timeout_is_ambiguous_and_reconciliation_is_read_only(db_session: Session) -> None:
    move, factory, connector, actor, _ = service(
        db_session,
        user_response("/"),
        user_response("/"),
        TimeoutError("ambiguous"),
        user_response("/Engineering"),
    )
    preview = move.preview_move(
        actor=actor,
        organization_id=connector.organization_id,
        user_id="user-1",
        destination_org_unit_id="id:engineering",
    )
    with pytest.raises(UserOrgUnitMutationAmbiguousError):
        move.execute_move(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )
    result = GoogleWorkspaceUserOrgUnitReconciliationService(
        db_session, move, poll_delays=(0.0,), sleeper=lambda _: None
    ).reconcile_move(
        actor=actor,
        organization_id=connector.organization_id,
        confirmation_token=preview.confirmation_token,
    )
    assert result.status == "verified"
    assert [call["scopes"] for call in factory.calls].count((DIRECTORY_USER_WRITE_SCOPE,)) == 1
    assert factory.calls[-1]["scopes"] == (DIRECTORY_USER_READONLY_SCOPE,)


@pytest.mark.parametrize(
    ("status_code", "expected", "ambiguous"),
    [
        (403, GoogleWorkspaceErrorCode.GOOGLE_FORBIDDEN, False),
        (404, GoogleWorkspaceErrorCode.GOOGLE_USER_NOT_FOUND, False),
        (429, GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED, False),
        (500, GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE, True),
    ],
)
def test_write_errors_are_safe_and_never_retried(
    db_session: Session,
    status_code: int,
    expected: GoogleWorkspaceErrorCode,
    ambiguous: bool,
) -> None:
    error = HttpError(Response({"status": str(status_code)}), b'{"private_key":"secret"}')
    move, _, connector, actor, _ = service(
        db_session, user_response("/"), user_response("/"), error
    )
    preview = move.preview_move(
        actor=actor,
        organization_id=connector.organization_id,
        user_id="user-1",
        destination_org_unit_id="id:engineering",
    )
    with pytest.raises(GoogleWorkspaceError) as result:
        move.execute_move(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )
    assert result.value.code == expected
    assert isinstance(result.value, UserOrgUnitMutationAmbiguousError) is ambiguous
    assert "secret" not in str(result.value)


def test_missing_write_scope_is_reported_without_retry(db_session: Session) -> None:
    error = HttpError(
        Response({"status": "403"}),
        b'{"error":{"errors":[{"reason":"insufficientPermissions"}]}}',
    )
    move, factory, connector, actor, _ = service(
        db_session, user_response("/"), user_response("/"), error
    )
    preview = move.preview_move(
        actor=actor,
        organization_id=connector.organization_id,
        user_id="user-1",
        destination_org_unit_id="id:engineering",
    )

    with pytest.raises(GoogleWorkspaceError) as rejected:
        move.execute_move(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )

    assert rejected.value.code == GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION
    write = factory.all_clients[-1].calls[0]
    assert write["method"] == "update"
    assert write["execute_kwargs"] == {"num_retries": 0}


def test_preview_endpoint_audits_paths_without_confirmation_token(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    organization = create_organization(client, auth_headers, None, "OU Move Endpoint")
    preview = UserOrgUnitMovePreview(
        organization_id=UUID(organization["id"]),
        customer_id=uuid4(),
        target_google_id="immutable-user-1",
        target_primary_email="person@example.invalid",
        source_org_unit_path="/",
        destination_org_unit_id="id:engineering",
        destination_org_unit_path="/Engineering",
        confirmation_token="private-confirmation-token-123456789012345",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        effect="Policies may change.",
    )
    fake = type("FakeMoveService", (), {"preview_move": lambda self, **kwargs: preview})()
    with patch(
        "app.api.v1.router.GoogleWorkspaceUserOrgUnitService.from_settings",
        return_value=fake,
    ):
        response = client.post(
            f"/api/v1/organizations/{organization['id']}"
            "/google-workspace/users/orgunit/preview",
            json={"user_id": "immutable-user-1", "destination_org_unit_id": "id:engineering"},
            headers=auth_headers,
        )
    assert response.status_code == 200
    event = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "google_workspace.user.orgunit_move_previewed")
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.object_id == "immutable-user-1"
    assert preview.confirmation_token not in str(event.metadata_json)


def test_non_admin_cannot_preview_move(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    customer = create_customer(client, auth_headers, "OU Move Customer")
    organization = create_organization(
        client, auth_headers, customer["id"], "OU Move Restricted"
    )
    actor = add_user(db_session, "ou-move-user@example.invalid")
    add_membership(db_session, actor, customer["id"], "customer_user")
    response = client.post(
        f"/api/v1/organizations/{organization['id']}"
        "/google-workspace/users/orgunit/preview",
        json={"user_id": "user-1", "destination_org_unit_id": "id:engineering"},
        headers=login_headers(client, actor.email),
    )
    assert response.status_code == 403
