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
from app.models import AuditEvent, GoogleWorkspaceUserStatusConfirmation
from app.services.google_workspace_user_lookup import GoogleWorkspaceUserLookupResult
from app.services.google_workspace_user_status import (
    GoogleWorkspaceUserStatusReconciliationService,
    GoogleWorkspaceUserStatusService,
    UserStatusChangePreview,
    UserStatusMutationAmbiguousError,
    UserStatusMutationResult,
    UserStatusReconciliationResult,
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

    def update(self, **kwargs: Any) -> FakeRequest:
        self.client.calls.append({"method": "update", "kwargs": kwargs})
        return FakeRequest(self.client, self.client.responses.pop(0))

    def get(self, **kwargs: Any) -> FakeRequest:
        self.client.calls.append({"method": "get", "kwargs": kwargs})
        return FakeRequest(self.client, self.client.responses.pop(0))


class FakeDirectoryClient:
    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def users(self) -> FakeUsers:
        return FakeUsers(self)

    def close(self) -> None:
        self.closed = True


class FakeClientFactory:
    def __init__(self, clients: list[FakeDirectoryClient]) -> None:
        self.clients = list(clients)
        self.calls: list[dict[str, Any]] = []

    def for_directory_users(self, **kwargs: Any) -> FakeDirectoryClient:
        self.calls.append(kwargs)
        return self.clients.pop(0)


class FakeLookup:
    def __init__(self, identities: dict[str, GoogleWorkspaceUserLookupResult]) -> None:
        self.identities = {key.casefold(): value for key, value in identities.items()}
        self.calls: list[str] = []

    def lookup(self, **kwargs: Any) -> GoogleWorkspaceUserLookupResult:
        email = str(kwargs["email"]).casefold()
        self.calls.append(email)
        return self.identities[email]


def identity(
    email: str,
    google_id: str,
    *,
    suspended: bool = False,
    reason: str | None = None,
    customer_id: str = "google-customer-1",
    is_super_admin: bool = False,
    is_delegated_admin: bool = False,
    archived: bool = False,
    deletion_time: datetime | None = None,
    aliases: list[str] | None = None,
) -> GoogleWorkspaceUserLookupResult:
    return GoogleWorkspaceUserLookupResult(
        id=google_id,
        customer_id=customer_id,
        full_name="Example User",
        primary_email=email,
        aliases=aliases or [],
        non_editable_aliases=[],
        suspended=suspended,
        archived=archived,
        org_unit_path="/People",
        is_mailbox_setup=True,
        matched_by="primary_email",
        is_super_admin=is_super_admin,
        is_delegated_admin=is_delegated_admin,
        suspension_reason=reason,
        deletion_time=deletion_time,
    )


def google_response(user: GoogleWorkspaceUserLookupResult, suspended: bool) -> dict[str, object]:
    return {
        "id": user.id,
        "customerId": user.customer_id,
        "primaryEmail": user.primary_email,
        "aliases": user.aliases,
        "suspended": suspended,
        "archived": False,
        "isAdmin": False,
        "isDelegatedAdmin": False,
        **({"suspensionReason": "ADMIN"} if suspended else {}),
    }


def status_service(
    db_session: Session,
    clients: list[FakeDirectoryClient] | None = None,
    *,
    target: GoogleWorkspaceUserLookupResult | None = None,
) -> tuple[GoogleWorkspaceUserStatusService, FakeClientFactory, Any, Any, FakeLookup]:
    connector, actor = create_connector(db_session)
    target = target or identity(
        "person@primary.example",
        "user-1",
        aliases=["person@secondary.example"],
    )
    lookup = FakeLookup(
        {
            "admin@example.com": identity(
                "admin@example.com", "admin-1", is_super_admin=True
            ),
            target.primary_email: target,
            **{alias: target for alias in target.aliases},
        }
    )
    factory = FakeClientFactory(clients or [])
    service = GoogleWorkspaceUserStatusService(db_session, factory, lookup)  # type: ignore[arg-type]
    return service, factory, connector, actor, lookup


def test_preview_resolves_alias_and_persists_only_hashed_bound_confirmation(
    db_session: Session,
) -> None:
    service, _, connector, actor, _ = status_service(db_session)

    result = service.preview_change(
        actor=actor,
        organization_id=connector.organization_id,
        operation="suspend",
        user_email="person@secondary.example",
    )

    assert result.target_google_id == "user-1"
    assert result.target_primary_email == "person@primary.example"
    assert result.previous_suspended is False
    confirmation = db_session.scalar(select(GoogleWorkspaceUserStatusConfirmation))
    assert confirmation is not None
    assert confirmation.token_digest != result.confirmation_token
    assert result.confirmation_token not in confirmation.token_digest
    assert confirmation.actor_user_id == actor.id
    assert confirmation.connector_config_id == connector.id
    assert confirmation.customer_id is not None
    assert confirmation.google_customer_id == "google-customer-1"
    assert service._aware(confirmation.expires_at) > datetime.now(UTC)


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (
            identity("root@example.com", "user-2", is_super_admin=True),
            GoogleWorkspaceErrorCode.GOOGLE_USER_ADMIN_PROTECTED,
        ),
        (
            identity("delegated@example.com", "user-2", is_delegated_admin=True),
            GoogleWorkspaceErrorCode.GOOGLE_USER_ADMIN_PROTECTED,
        ),
        (
            identity("archived@example.com", "user-2", archived=True),
            GoogleWorkspaceErrorCode.GOOGLE_USER_ARCHIVED,
        ),
        (
            identity("deleted@example.com", "user-2", deletion_time=datetime.now(UTC)),
            GoogleWorkspaceErrorCode.GOOGLE_USER_DELETED,
        ),
    ],
)
def test_preview_fails_closed_for_protected_accounts(
    db_session: Session,
    target: GoogleWorkspaceUserLookupResult,
    expected: GoogleWorkspaceErrorCode,
) -> None:
    service, _, connector, actor, _ = status_service(db_session, target=target)

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        service.preview_change(
            actor=actor,
            organization_id=connector.organization_id,
            operation="suspend",
            user_email=target.primary_email,
        )

    assert exc_info.value.code == expected


def test_configured_admin_and_local_actor_are_protected(db_session: Session) -> None:
    service, _, connector, actor, lookup = status_service(db_session)
    lookup.identities[actor.email.casefold()] = identity(actor.email, "self-google")

    with pytest.raises(GoogleWorkspaceError) as admin_error:
        service.preview_change(
            actor=actor,
            organization_id=connector.organization_id,
            operation="suspend",
            user_email="admin@example.com",
        )
    with pytest.raises(GoogleWorkspaceError) as self_error:
        service.preview_change(
            actor=actor,
            organization_id=connector.organization_id,
            operation="suspend",
            user_email=actor.email,
        )

    assert admin_error.value.code == GoogleWorkspaceErrorCode.GOOGLE_USER_ADMIN_PROTECTED
    assert self_error.value.code == GoogleWorkspaceErrorCode.GOOGLE_USER_SELF_PROTECTED


@pytest.mark.parametrize("reason", [None, "", "GOOGLE", "UNKNOWN"])
def test_reactivation_requires_verified_admin_suspension_reason(
    db_session: Session, reason: str | None
) -> None:
    target = identity("person@example.com", "user-1", suspended=True, reason=reason)
    service, _, connector, actor, _ = status_service(db_session, target=target)

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        service.preview_change(
            actor=actor,
            organization_id=connector.organization_id,
            operation="reactivate",
            user_email=target.primary_email,
        )

    assert (
        exc_info.value.code
        == GoogleWorkspaceErrorCode.GOOGLE_USER_SUSPENSION_REASON_UNSUPPORTED
    )


@pytest.mark.parametrize(
    ("operation", "initial_suspended", "reason", "requested"),
    [
        ("suspend", False, None, True),
        ("reactivate", True, "ADMIN", False),
    ],
)
def test_execute_uses_immutable_id_exact_payload_write_scope_and_no_retry(
    db_session: Session,
    operation: str,
    initial_suspended: bool,
    reason: str | None,
    requested: bool,
) -> None:
    target = identity(
        "person@example.com", "immutable-user-1", suspended=initial_suspended, reason=reason
    )
    client = FakeDirectoryClient(google_response(target, requested))
    service, factory, connector, actor, _ = status_service(
        db_session, [client], target=target
    )
    preview = service.preview_change(
        actor=actor,
        organization_id=connector.organization_id,
        operation=operation,  # type: ignore[arg-type]
        user_email=target.primary_email,
    )

    result = service.execute_change(
        actor=actor,
        organization_id=connector.organization_id,
        operation=operation,  # type: ignore[arg-type]
        confirmation_token=preview.confirmation_token,
    )

    assert result.suspended is requested
    assert factory.calls == [
        {
            "actor": actor,
            "organization_id": connector.organization_id,
            "scopes": (DIRECTORY_USER_WRITE_SCOPE,),
        }
    ]
    assert client.calls[0]["kwargs"]["userKey"] == "immutable-user-1"
    assert client.calls[0]["kwargs"]["body"] == {"suspended": requested}
    assert set(client.calls[0]["kwargs"]) == {"userKey", "body", "fields"}
    assert client.calls[0]["execute_kwargs"] == {"num_retries": 0}
    assert client.closed is True


def test_confirmation_is_single_use(db_session: Session) -> None:
    target = identity("person@example.com", "user-1")
    client = FakeDirectoryClient(google_response(target, True))
    service, _, connector, actor, _ = status_service(db_session, [client], target=target)
    preview = service.preview_change(
        actor=actor,
        organization_id=connector.organization_id,
        operation="suspend",
        user_email=target.primary_email,
    )
    service.execute_change(
        actor=actor,
        organization_id=connector.organization_id,
        operation="suspend",
        confirmation_token=preview.confirmation_token,
    )

    with pytest.raises(GoogleWorkspaceError) as replay:
        service.execute_change(
            actor=actor,
            organization_id=connector.organization_id,
            operation="suspend",
            confirmation_token=preview.confirmation_token,
        )
    assert replay.value.code == GoogleWorkspaceErrorCode.GOOGLE_USER_CONFIRMATION_USED



def test_changed_account_state_between_preview_and_confirmation_is_rejected(
    db_session: Session,
) -> None:
    target = identity("person@example.com", "user-1")
    service, _, connector, actor, lookup = status_service(db_session, target=target)
    preview = service.preview_change(
        actor=actor,
        organization_id=connector.organization_id,
        operation="suspend",
        user_email=target.primary_email,
    )
    lookup.identities[target.primary_email] = identity(
        target.primary_email, target.id, suspended=True, reason="ADMIN"
    )

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        service.execute_change(
            actor=actor,
            organization_id=connector.organization_id,
            operation="suspend",
            confirmation_token=preview.confirmation_token,
        )

    assert exc_info.value.code == GoogleWorkspaceErrorCode.GOOGLE_USER_STATE_CHANGED


def test_expired_and_cross_actor_confirmation_are_rejected(db_session: Session) -> None:
    service, _, connector, actor, _ = status_service(db_session)
    preview = service.preview_change(
        actor=actor,
        organization_id=connector.organization_id,
        operation="suspend",
        user_email="person@primary.example",
    )
    confirmation = db_session.scalar(select(GoogleWorkspaceUserStatusConfirmation))
    assert confirmation is not None
    confirmation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    with pytest.raises(GoogleWorkspaceError) as expired:
        service.execute_change(
            actor=actor,
            organization_id=connector.organization_id,
            operation="suspend",
            confirmation_token=preview.confirmation_token,
        )
    assert expired.value.code == GoogleWorkspaceErrorCode.GOOGLE_USER_CONFIRMATION_EXPIRED


def test_timeout_is_ambiguous_and_reconciliation_is_read_only(db_session: Session) -> None:
    target = identity("person@example.com", "user-1")
    write_client = FakeDirectoryClient(TimeoutError("test timeout"))
    read_client = FakeDirectoryClient(google_response(target, True))
    service, factory, connector, actor, _ = status_service(
        db_session, [write_client, read_client], target=target
    )
    preview = service.preview_change(
        actor=actor,
        organization_id=connector.organization_id,
        operation="suspend",
        user_email=target.primary_email,
    )

    with pytest.raises(UserStatusMutationAmbiguousError) as ambiguous:
        service.execute_change(
            actor=actor,
            organization_id=connector.organization_id,
            operation="suspend",
            confirmation_token=preview.confirmation_token,
        )
    assert ambiguous.value.code == GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT

    result = GoogleWorkspaceUserStatusReconciliationService(
        db_session, service, poll_delays=(0.0,), sleeper=lambda _: None
    ).reconcile_change(
        actor=actor,
        organization_id=connector.organization_id,
        operation="suspend",
        confirmation_token=preview.confirmation_token,
    )

    assert result.status == "verified"
    assert [call["scopes"] for call in factory.calls] == [
        (DIRECTORY_USER_WRITE_SCOPE,),
        (DIRECTORY_USER_READONLY_SCOPE,),
    ]
    assert read_client.calls[0]["method"] == "get"
    assert read_client.calls[0]["kwargs"]["userKey"] == target.id
    assert read_client.calls[0]["execute_kwargs"] == {"num_retries": 0}
    assert factory.calls[1]["request_timeout_seconds"] == 5.0


def test_malformed_success_response_is_ambiguous_and_never_retries_write(
    db_session: Session,
) -> None:
    target = identity("person@example.com", "user-1")
    client = FakeDirectoryClient({"id": target.id})
    service, _, connector, actor, _ = status_service(db_session, [client], target=target)
    preview = service.preview_change(
        actor=actor,
        organization_id=connector.organization_id,
        operation="suspend",
        user_email=target.primary_email,
    )

    with pytest.raises(UserStatusMutationAmbiguousError) as exc_info:
        service.execute_change(
            actor=actor,
            organization_id=connector.organization_id,
            operation="suspend",
            confirmation_token=preview.confirmation_token,
        )

    assert exc_info.value.code == GoogleWorkspaceErrorCode.GOOGLE_API_ERROR
    assert len(client.calls) == 1
    assert client.calls[0]["execute_kwargs"] == {"num_retries": 0}


@pytest.mark.parametrize(
    ("status_code", "content", "expected", "ambiguous"),
    [
        (401, b"{}", GoogleWorkspaceErrorCode.GOOGLE_UNAUTHORIZED, False),
        (403, b"{}", GoogleWorkspaceErrorCode.GOOGLE_FORBIDDEN, False),
        (404, b"{}", GoogleWorkspaceErrorCode.GOOGLE_USER_NOT_FOUND, False),
        (409, b"{}", GoogleWorkspaceErrorCode.GOOGLE_CONFLICT, False),
        (429, b"{}", GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED, False),
        (500, b"{}", GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE, True),
        (503, b"{}", GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE, True),
    ],
)
def test_write_google_errors_are_safe_and_only_ambiguous_failures_reconcile(
    db_session: Session,
    status_code: int,
    content: bytes,
    expected: GoogleWorkspaceErrorCode,
    ambiguous: bool,
) -> None:
    target = identity("person@example.com", "user-1")
    upstream = HttpError(Response({"status": str(status_code)}), content)
    service, _, connector, actor, _ = status_service(
        db_session, [FakeDirectoryClient(upstream)], target=target
    )
    preview = service.preview_change(
        actor=actor,
        organization_id=connector.organization_id,
        operation="suspend",
        user_email=target.primary_email,
    )

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        service.execute_change(
            actor=actor,
            organization_id=connector.organization_id,
            operation="suspend",
            confirmation_token=preview.confirmation_token,
        )

    assert exc_info.value.code == expected
    assert isinstance(exc_info.value, UserStatusMutationAmbiguousError) is ambiguous
    assert content.decode(errors="ignore") not in str(exc_info.value)


def test_execute_rejects_customer_or_identity_change_after_preview(db_session: Session) -> None:
    target = identity("person@example.com", "user-1")
    service, _, connector, actor, lookup = status_service(db_session, target=target)
    preview = service.preview_change(
        actor=actor,
        organization_id=connector.organization_id,
        operation="suspend",
        user_email=target.primary_email,
    )
    lookup.identities[target.primary_email] = identity(
        target.primary_email, "different-id", customer_id="other-google-customer"
    )

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        service.execute_change(
            actor=actor,
            organization_id=connector.organization_id,
            operation="suspend",
            confirmation_token=preview.confirmation_token,
        )

    assert exc_info.value.code == GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH


def test_preview_endpoint_records_immutable_id_without_confirmation_token(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    organization = create_organization(client, auth_headers, None, "Status Endpoint Org")
    result = UserStatusChangePreview(
        operation="suspend",
        organization_id=UUID(organization["id"]),
        customer_id=uuid4(),
        target_google_id="immutable-user-1",
        target_primary_email="person@example.com",
        previous_suspended=False,
        requested_suspended=True,
        confirmation_token="safe-test-confirmation-token-123456789",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        effect="The account will be suspended.",
    )
    fake_service = type(
        "FakeStatusService",
        (),
        {"preview_change": lambda self, **kwargs: result},
    )()

    with patch(
        "app.api.v1.router.GoogleWorkspaceUserStatusService.from_settings",
        return_value=fake_service,
    ):
        response = client.post(
            f"/api/v1/organizations/{organization['id']}"
            "/google-workspace/users/suspend/preview",
            json={"user_email": "person@example.com"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    event = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "google_workspace.user.suspend_previewed")
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.object_id == "immutable-user-1"
    assert result.confirmation_token not in str(event.metadata_json)


def test_connector_operator_cannot_preview_user_status_change(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    customer = create_customer(client, auth_headers, "Status RBAC Customer")
    organization = create_organization(
        client, auth_headers, customer["id"], "Status RBAC Org"
    )
    operator = add_user(db_session, "status-operator@example.test")
    add_membership(db_session, operator, customer["id"], "customer_user")

    response = client.post(
        f"/api/v1/organizations/{organization['id']}"
        "/google-workspace/users/suspend/preview",
        json={"user_email": "person@example.test"},
        headers=login_headers(client, operator.email),
    )

    assert response.status_code == 403
    event = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "google_workspace.user.suspend_previewed")
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.outcome == "rejected"
    assert event.reason == "organization_access_denied"


def test_mutation_endpoint_audits_immutable_target_and_safe_state(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    organization = create_organization(client, auth_headers, None, "Status Mutation Audit Org")
    token = "safe-synthetic-confirmation-token-123456789"
    result = UserStatusMutationResult(
        operation="suspend",
        target_google_id="immutable-user-1",
        target_primary_email="person@example.test",
        previous_suspended=False,
        suspended=True,
        outcome="suspended",
        message="The user was suspended.",
    )
    fake_service = type(
        "FakeStatusService",
        (),
        {"execute_change": lambda self, **kwargs: result},
    )()

    with patch(
        "app.api.v1.router.GoogleWorkspaceUserStatusService.from_settings",
        return_value=fake_service,
    ):
        response = client.post(
            f"/api/v1/organizations/{organization['id']}"
            "/google-workspace/users/suspend",
            json={"confirmation_token": token},
            headers=auth_headers,
        )

    assert response.status_code == 200
    event = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "google_workspace.user.suspended")
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.object_id == result.target_google_id
    assert event.metadata_json == {
        "operation": "suspend",
        "previous_suspended": False,
        "suspended": True,
    }
    assert token not in str(event.metadata_json)


def test_ambiguous_mutation_and_reconciliation_have_separate_safe_audits(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    organization = create_organization(client, auth_headers, None, "Status Reconcile Audit Org")
    token = "safe-synthetic-reconciliation-token-1234567"
    correlation_id = uuid4()
    target_id = "immutable-user-2"

    def ambiguous_change(**kwargs: object) -> None:
        raise UserStatusMutationAmbiguousError(
            GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT,
            correlation_id,
            target_id,
        )

    fake_mutation_service = type(
        "FakeMutationService", (), {"execute_change": lambda self, **kwargs: ambiguous_change()}
    )()
    with patch(
        "app.api.v1.router.GoogleWorkspaceUserStatusService.from_settings",
        return_value=fake_mutation_service,
    ):
        mutation_response = client.post(
            f"/api/v1/organizations/{organization['id']}"
            "/google-workspace/users/suspend",
            json={"confirmation_token": token},
            headers=auth_headers,
        )

    assert mutation_response.status_code == 504
    assert mutation_response.json()["detail"]["correlation_id"] == str(correlation_id)
    reconciliation = UserStatusReconciliationResult(
        operation="suspend",
        target_google_id=target_id,
        target_primary_email="person@example.test",
        status="verified",
        observed_suspended=True,
        attempts=2,
        correlation_id=str(correlation_id),
        message="Google now reports the requested account status.",
    )
    fake_reconciliation = type(
        "FakeReconciliationService",
        (),
        {"reconcile_change": lambda self, **kwargs: reconciliation},
    )()
    with patch(
        "app.api.v1.router.GoogleWorkspaceUserStatusReconciliationService.from_settings",
        return_value=fake_reconciliation,
    ):
        reconciliation_response = client.post(
            f"/api/v1/organizations/{organization['id']}"
            "/google-workspace/users/suspend/reconcile",
            json={"confirmation_token": token},
            headers=auth_headers,
        )

    assert reconciliation_response.status_code == 200
    events = db_session.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.action.in_(
                [
                    "google_workspace.user.suspended",
                    "google_workspace.user.suspend_reconciled",
                ]
            )
        )
        .order_by(AuditEvent.created_at)
    ).all()
    assert len(events) == 2
    by_action = {event.action: event for event in events}
    mutation_event = by_action["google_workspace.user.suspended"]
    reconciliation_event = by_action["google_workspace.user.suspend_reconciled"]
    assert mutation_event.object_id == target_id
    assert mutation_event.outcome == "failure"
    assert mutation_event.reason == "google_timeout"
    assert reconciliation_event.object_id == target_id
    assert reconciliation_event.outcome == "success"
    assert token not in str([event.metadata_json for event in events])
