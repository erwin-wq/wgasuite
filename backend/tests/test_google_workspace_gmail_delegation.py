from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from httplib2 import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.google_workspace_credentials import (
    GMAIL_DELEGATE_READ_SCOPE,
    GMAIL_DELEGATE_WRITE_SCOPE,
)
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
)
from app.models import AuditEvent, GoogleWorkspaceDelegateConfirmation
from app.services.google_workspace_gmail_delegation import (
    GmailDelegate,
    GmailDelegateListResult,
    GmailDelegateMutationResult,
    GoogleWorkspaceGmailDelegationService,
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


class FakeDelegatesResource:
    def __init__(self, response: object) -> None:
        self.request = FakeRequest(response)
        self.method: str | None = None
        self.kwargs: dict[str, Any] | None = None

    def list(self, **kwargs: Any) -> FakeRequest:
        self.method = "list"
        self.kwargs = kwargs
        return self.request

    def create(self, **kwargs: Any) -> FakeRequest:
        self.method = "create"
        self.kwargs = kwargs
        return self.request

    def delete(self, **kwargs: Any) -> FakeRequest:
        self.method = "delete"
        self.kwargs = kwargs
        return self.request


class FakeSettingsResource:
    def __init__(self, delegates: FakeDelegatesResource) -> None:
        self.delegates_resource = delegates

    def delegates(self) -> FakeDelegatesResource:
        return self.delegates_resource


class FakeUsersResource:
    def __init__(self, settings: FakeSettingsResource) -> None:
        self.settings_resource = settings

    def settings(self) -> FakeSettingsResource:
        return self.settings_resource


class FakeGmailClient:
    def __init__(self, response: object) -> None:
        self.delegates_resource = FakeDelegatesResource(response)
        self.users_resource = FakeUsersResource(FakeSettingsResource(self.delegates_resource))
        self.closed = False

    def users(self) -> FakeUsersResource:
        return self.users_resource

    def close(self) -> None:
        self.closed = True


class FakeClientFactory:
    def __init__(self, clients_or_errors: list[FakeGmailClient | GoogleWorkspaceError]) -> None:
        self.clients_or_errors = list(clients_or_errors)
        self.calls: list[dict[str, Any]] = []

    def for_gmail_delegates(self, **kwargs: Any) -> FakeGmailClient:
        self.calls.append(kwargs)
        client_or_error = self.clients_or_errors.pop(0)
        if isinstance(client_or_error, GoogleWorkspaceError):
            raise client_or_error
        return client_or_error


class FakeUserLookup:
    def __init__(self, identities: dict[str, GoogleWorkspaceUserLookupResult]) -> None:
        self.identities = {key.casefold(): value for key, value in identities.items()}
        self.calls: list[str] = []

    def lookup(self, **kwargs: Any) -> GoogleWorkspaceUserLookupResult:
        email = str(kwargs["email"]).casefold()
        self.calls.append(email)
        identity = self.identities.get(email)
        if identity is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_USER_NOT_FOUND)
        return identity


def identity(
    email: str,
    *,
    google_id: str,
    customer_id: str = "google-customer-1",
    suspended: bool = False,
    archived: bool | None = False,
    mailbox: bool | None = True,
) -> GoogleWorkspaceUserLookupResult:
    return GoogleWorkspaceUserLookupResult(
        id=google_id,
        customer_id=customer_id,
        full_name=email.split("@", maxsplit=1)[0].title(),
        primary_email=email,
        aliases=[],
        non_editable_aliases=[],
        suspended=suspended,
        archived=archived,
        org_unit_path="/People",
        is_mailbox_setup=mailbox,
        matched_by="primary_email",
    )


def delegation_service(
    db_session: Session,
    clients: list[FakeGmailClient | GoogleWorkspaceError],
    *,
    extra_identities: dict[str, GoogleWorkspaceUserLookupResult] | None = None,
) -> tuple[
    GoogleWorkspaceGmailDelegationService,
    FakeClientFactory,
    FakeUserLookup,
    UUID,
    Any,
]:
    connector, actor = create_connector(db_session)
    identities = {
        "admin@example.com": identity("admin@example.com", google_id="admin-id"),
        "owner@example.com": identity("owner@example.com", google_id="owner-id"),
        "delegate@example.com": identity("delegate@example.com", google_id="delegate-id"),
        "delegate.alias@example.com": identity(
            "delegate@example.com", google_id="delegate-id"
        ),
    }
    identities.update(extra_identities or {})
    factory = FakeClientFactory(clients)
    lookup = FakeUserLookup(identities)
    service = GoogleWorkspaceGmailDelegationService(db_session, factory, lookup)  # type: ignore[arg-type]
    return service, factory, lookup, connector.organization_id, actor


def delegate_response(email: str = "delegate@example.com") -> dict[str, object]:
    return {"delegates": [{"delegateEmail": email, "verificationStatus": "accepted"}]}


def preview_create(
    service: GoogleWorkspaceGmailDelegationService,
    actor: Any,
    organization_id: UUID,
    *,
    delegate_email: str = "delegate@example.com",
) -> Any:
    return service.preview_change(
        actor=actor,
        organization_id=organization_id,
        operation="create",
        owner_email="owner@example.com",
        delegate_email=delegate_email,
    )


def test_lists_delegates_with_owner_impersonation_and_read_scope(db_session: Session) -> None:
    gmail = FakeGmailClient(delegate_response())
    service, factory, _, organization_id, actor = delegation_service(db_session, [gmail])

    result = service.list_delegates(
        actor=actor,
        organization_id=organization_id,
        owner_email="owner@example.com",
    )

    assert result.owner_primary_email == "owner@example.com"
    assert result.delegates == [GmailDelegate("delegate@example.com", "accepted")]
    assert factory.calls[0]["owner"].primary_email == "owner@example.com"
    assert factory.calls[0]["scopes"] == [GMAIL_DELEGATE_READ_SCOPE]
    assert gmail.delegates_resource.method == "list"
    assert gmail.delegates_resource.kwargs == {"userId": "me"}
    assert gmail.delegates_resource.request.execute_kwargs == {"num_retries": 0}
    assert gmail.closed is True


@pytest.mark.parametrize("response", [{}, {"delegates": []}, {"delegates": None}])
def test_empty_delegate_response_is_success(db_session: Session, response: object) -> None:
    service, _, _, organization_id, actor = delegation_service(
        db_session, [FakeGmailClient(response)]
    )

    result = service.list_delegates(
        actor=actor, organization_id=organization_id, owner_email="owner@example.com"
    )

    assert result.delegates == []


def test_create_preview_canonicalizes_alias_and_execute_uses_write_scope(
    db_session: Session,
) -> None:
    preview_list = FakeGmailClient({"delegates": []})
    revalidation_list = FakeGmailClient({"delegates": []})
    create_client = FakeGmailClient(
        {"delegateEmail": "delegate@example.com", "verificationStatus": "accepted"}
    )
    service, factory, _, organization_id, actor = delegation_service(
        db_session, [preview_list, revalidation_list, create_client]
    )

    preview = preview_create(
        service,
        actor,
        organization_id,
        delegate_email="delegate.alias@example.com",
    )
    result = service.execute_change(
        actor=actor,
        organization_id=organization_id,
        operation="create",
        confirmation_token=preview.confirmation_token,
    )

    assert preview.delegate_primary_email == "delegate@example.com"
    assert result.outcome == "created"
    assert factory.calls[0]["scopes"] == [GMAIL_DELEGATE_READ_SCOPE]
    assert factory.calls[1]["scopes"] == [GMAIL_DELEGATE_READ_SCOPE]
    assert factory.calls[2]["scopes"] == [GMAIL_DELEGATE_WRITE_SCOPE]
    assert create_client.delegates_resource.method == "create"
    assert create_client.delegates_resource.kwargs == {
        "userId": "me",
        "body": {"delegateEmail": "delegate@example.com"},
    }
    confirmation = db_session.scalar(select(GoogleWorkspaceDelegateConfirmation))
    assert confirmation is not None
    assert confirmation.status == "succeeded"
    assert confirmation.token_digest != preview.confirmation_token


def test_remove_requires_confirmation_and_uses_canonical_primary_email(
    db_session: Session,
) -> None:
    remove_client = FakeGmailClient({})
    service, factory, _, organization_id, actor = delegation_service(
        db_session,
        [
            FakeGmailClient(delegate_response()),
            FakeGmailClient(delegate_response()),
            remove_client,
        ],
    )
    preview = service.preview_change(
        actor=actor,
        organization_id=organization_id,
        operation="remove",
        owner_email="owner@example.com",
        delegate_email="delegate.alias@example.com",
    )

    result = service.execute_change(
        actor=actor,
        organization_id=organization_id,
        operation="remove",
        confirmation_token=preview.confirmation_token,
    )

    assert result.outcome == "removed"
    assert factory.calls[-1]["scopes"] == [GMAIL_DELEGATE_WRITE_SCOPE]
    assert remove_client.delegates_resource.method == "delete"
    assert remove_client.delegates_resource.kwargs == {
        "userId": "me",
        "delegateEmail": "delegate@example.com",
    }
    assert len(factory.calls) == 3


def test_different_email_domains_are_allowed_for_same_google_customer(
    db_session: Session,
) -> None:
    external = identity("delegate@secondary.example", google_id="delegate-secondary")
    service, _, _, organization_id, actor = delegation_service(
        db_session,
        [FakeGmailClient({"delegates": []})],
        extra_identities={"delegate@secondary.example": external},
    )

    preview = preview_create(
        service,
        actor,
        organization_id,
        delegate_email="delegate@secondary.example",
    )

    assert preview.delegate_primary_email == "delegate@secondary.example"


def test_cross_tenant_delegate_is_rejected_even_with_similar_address(
    db_session: Session,
) -> None:
    foreign = identity(
        "delegate@example.com",
        google_id="foreign-id",
        customer_id="google-customer-2",
    )
    service, factory, _, organization_id, actor = delegation_service(
        db_session,
        [],
        extra_identities={"delegate@example.com": foreign},
    )

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        preview_create(service, actor, organization_id)

    assert exc_info.value.code == GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH
    assert factory.calls == []


@pytest.mark.parametrize(
    ("owner_overrides", "expected_code"),
    [
        ({"suspended": True}, GoogleWorkspaceErrorCode.GMAIL_USER_INELIGIBLE),
        ({"archived": True}, GoogleWorkspaceErrorCode.GMAIL_USER_INELIGIBLE),
        ({"mailbox": False}, GoogleWorkspaceErrorCode.GMAIL_MAILBOX_NOT_CONFIGURED),
    ],
)
def test_ineligible_owner_is_rejected_before_gmail_call(
    db_session: Session,
    owner_overrides: dict[str, object],
    expected_code: GoogleWorkspaceErrorCode,
) -> None:
    owner = identity("owner@example.com", google_id="owner-id", **owner_overrides)  # type: ignore[arg-type]
    service, factory, _, organization_id, actor = delegation_service(
        db_session, [], extra_identities={"owner@example.com": owner}
    )

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        service.list_delegates(
            actor=actor, organization_id=organization_id, owner_email="owner@example.com"
        )

    assert exc_info.value.code == expected_code
    assert factory.calls == []


@pytest.mark.parametrize("attribute", ["suspended", "archived", "mailbox"])
def test_ineligible_delegate_is_rejected_for_create(
    db_session: Session, attribute: str
) -> None:
    overrides = {attribute: False if attribute == "mailbox" else True}
    delegate = identity(
        "delegate@example.com", google_id="delegate-id", **overrides  # type: ignore[arg-type]
    )
    service, factory, _, organization_id, actor = delegation_service(
        db_session, [], extra_identities={"delegate@example.com": delegate}
    )

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        preview_create(service, actor, organization_id)

    assert exc_info.value.code == GoogleWorkspaceErrorCode.GMAIL_USER_INELIGIBLE
    assert factory.calls == []


def test_self_delegation_is_rejected_by_google_identity(db_session: Session) -> None:
    same_user = identity("owner@example.com", google_id="owner-id")
    service, _, _, organization_id, actor = delegation_service(
        db_session, [], extra_identities={"owner.alias@example.com": same_user}
    )

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        preview_create(
            service,
            actor,
            organization_id,
            delegate_email="owner.alias@example.com",
        )

    assert exc_info.value.code == GoogleWorkspaceErrorCode.GMAIL_SELF_DELEGATION


@pytest.mark.parametrize(
    ("operation", "response", "expected_code"),
    [
        ("create", delegate_response(), GoogleWorkspaceErrorCode.GMAIL_DELEGATE_ALREADY_EXISTS),
        ("remove", {"delegates": []}, GoogleWorkspaceErrorCode.GMAIL_DELEGATE_NOT_FOUND),
    ],
)
def test_preview_rejects_existing_or_missing_relationship(
    db_session: Session,
    operation: str,
    response: object,
    expected_code: GoogleWorkspaceErrorCode,
) -> None:
    service, _, _, organization_id, actor = delegation_service(
        db_session, [FakeGmailClient(response)]
    )

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        service.preview_change(
            actor=actor,
            organization_id=organization_id,
            operation=operation,  # type: ignore[arg-type]
            owner_email="owner@example.com",
            delegate_email="delegate@example.com",
        )

    assert exc_info.value.code == expected_code


def test_confirmation_is_one_time_and_duplicate_create_is_not_sent(db_session: Session) -> None:
    create_client = FakeGmailClient({})
    service, _, _, organization_id, actor = delegation_service(
        db_session,
        [
            FakeGmailClient({"delegates": []}),
            FakeGmailClient({"delegates": []}),
            create_client,
            FakeGmailClient({"delegates": []}),
        ],
    )
    preview = preview_create(service, actor, organization_id)
    service.execute_change(
        actor=actor,
        organization_id=organization_id,
        operation="create",
        confirmation_token=preview.confirmation_token,
    )

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        service.execute_change(
            actor=actor,
            organization_id=organization_id,
            operation="create",
            confirmation_token=preview.confirmation_token,
        )

    assert exc_info.value.code == GoogleWorkspaceErrorCode.GMAIL_CONFIRMATION_USED
    assert create_client.delegates_resource.method == "create"

    with pytest.raises(GoogleWorkspaceError) as new_preview_error:
        preview_create(service, actor, organization_id)
    assert new_preview_error.value.code == GoogleWorkspaceErrorCode.GMAIL_CONFIRMATION_USED


def test_expired_confirmation_never_reaches_google_write(db_session: Session) -> None:
    service, factory, _, organization_id, actor = delegation_service(
        db_session, [FakeGmailClient({"delegates": []})]
    )
    preview = preview_create(service, actor, organization_id)
    confirmation = db_session.scalar(select(GoogleWorkspaceDelegateConfirmation))
    assert confirmation is not None
    confirmation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        service.execute_change(
            actor=actor,
            organization_id=organization_id,
            operation="create",
            confirmation_token=preview.confirmation_token,
        )

    assert exc_info.value.code == GoogleWorkspaceErrorCode.GMAIL_CONFIRMATION_EXPIRED
    assert len(factory.calls) == 1


def google_http_error(status: int, reason: str | None = None) -> HttpError:
    body = (
        f'{{"error":{{"errors":[{{"reason":"{reason}"}}]}}}}'.encode()
        if reason
        else b'{"error":{"message":"private upstream detail"}}'
    )
    return HttpError(Response({"status": str(status)}), body)


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (google_http_error(401), GoogleWorkspaceErrorCode.GOOGLE_UNAUTHORIZED),
        (
            google_http_error(403, "insufficientPermissions"),
            GoogleWorkspaceErrorCode.GMAIL_SCOPE_MISSING,
        ),
        (
            RefreshError("private OAuth detail", {"error": "unauthorized_client"}),
            GoogleWorkspaceErrorCode.GMAIL_SCOPE_MISSING,
        ),
        (
            google_http_error(403, "accessNotConfigured"),
            GoogleWorkspaceErrorCode.GMAIL_API_UNAVAILABLE,
        ),
        (google_http_error(404), GoogleWorkspaceErrorCode.GMAIL_MAILBOX_NOT_CONFIGURED),
        (google_http_error(429), GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED),
        (google_http_error(503), GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE),
        (TimeoutError("private timeout detail"), GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT),
    ],
)
def test_list_maps_google_failures_without_leaking_details(
    db_session: Session,
    failure: Exception,
    expected_code: GoogleWorkspaceErrorCode,
) -> None:
    service, _, _, organization_id, actor = delegation_service(
        db_session, [FakeGmailClient(failure)]
    )

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        service.list_delegates(
            actor=actor, organization_id=organization_id, owner_email="owner@example.com"
        )

    assert exc_info.value.code == expected_code
    assert "private" not in str(exc_info.value)


def test_ambiguous_write_timeout_is_consumed_and_never_retried(db_session: Session) -> None:
    write_client = FakeGmailClient(TimeoutError("private ambiguous detail"))
    service, factory, _, organization_id, actor = delegation_service(
        db_session,
        [
            FakeGmailClient({"delegates": []}),
            FakeGmailClient({"delegates": []}),
            write_client,
        ],
    )
    preview = preview_create(service, actor, organization_id)

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        service.execute_change(
            actor=actor,
            organization_id=organization_id,
            operation="create",
            confirmation_token=preview.confirmation_token,
        )

    assert exc_info.value.code == GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT
    confirmation = db_session.scalar(select(GoogleWorkspaceDelegateConfirmation))
    assert confirmation is not None
    assert confirmation.status == "failed"
    assert len(factory.calls) == 3
    with pytest.raises(GoogleWorkspaceError) as replay_error:
        service.execute_change(
            actor=actor,
            organization_id=organization_id,
            operation="create",
            confirmation_token=preview.confirmation_token,
        )
    assert replay_error.value.code == GoogleWorkspaceErrorCode.GMAIL_CONFIRMATION_USED


def test_create_maps_google_conflict_to_existing_delegate(db_session: Session) -> None:
    service, _, _, organization_id, actor = delegation_service(
        db_session,
        [
            FakeGmailClient({"delegates": []}),
            FakeGmailClient({"delegates": []}),
            FakeGmailClient(google_http_error(409)),
        ],
    )
    preview = preview_create(service, actor, organization_id)

    with pytest.raises(GoogleWorkspaceError) as exc_info:
        service.execute_change(
            actor=actor,
            organization_id=organization_id,
            operation="create",
            confirmation_token=preview.confirmation_token,
        )

    assert exc_info.value.code == GoogleWorkspaceErrorCode.GMAIL_DELEGATE_ALREADY_EXISTS


class FakeEndpointService:
    def __init__(self, result: object | Exception) -> None:
        self.result = result

    def list_delegates(self, **kwargs: Any) -> object:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def execute_change(self, **kwargs: Any) -> object:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_list_endpoint_records_sanitized_success_audit(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    organization = create_organization(client, auth_headers, None, "Gmail Delegate Org")
    result = GmailDelegateListResult(
        owner_primary_email="owner@example.test",
        delegates=[GmailDelegate("delegate@example.test", "accepted")],
    )
    with patch(
        "app.api.v1.router.GoogleWorkspaceGmailDelegationService.from_settings",
        return_value=FakeEndpointService(result),
    ):
        response = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/gmail-delegates/list",
            json={"owner_email": "owner@example.test"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["delegates"][0]["primary_email"] == "delegate@example.test"
    event = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "google_workspace.gmail_delegate.listed")
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.outcome == "success"
    assert event.metadata_json == {
        "owner_primary_email": "owner@example.test",
        "delegate_count": 1,
    }


def test_viewer_cannot_list_or_mutate_and_denial_is_audited(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    customer = create_customer(client, auth_headers, "Delegate Security Customer")
    organization = create_organization(
        client, auth_headers, customer["id"], "Delegate Security Org"
    )
    viewer = add_user(db_session, f"delegate-viewer-{uuid4().hex}@example.test")
    add_membership(db_session, viewer, customer["id"], "customer_viewer")
    headers = login_headers(client, viewer.email)

    response = client.post(
        f"/api/v1/organizations/{organization['id']}/google-workspace/gmail-delegates/list",
        json={"owner_email": "owner@example.test"},
        headers=headers,
    )

    assert response.status_code == 403
    event = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "google_workspace.gmail_delegate.listed")
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.outcome == "rejected"
    assert event.reason == "organization_access_denied"
    assert "token" not in str(event.metadata_json).lower()


@pytest.mark.parametrize(
    ("result", "expected_status", "expected_outcome", "expected_reason"),
    [
        (
            GmailDelegateMutationResult(
                operation="create",
                owner_primary_email="owner@example.test",
                delegate_primary_email="delegate@example.test",
                outcome="created",
                message="Mailbox delegate added.",
            ),
            201,
            "success",
            None,
        ),
        (
            GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT),
            504,
            "failure",
            "google_timeout",
        ),
        (
            GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_CONFIRMATION_USED),
            409,
            "rejected",
            "gmail_confirmation_used",
        ),
    ],
)
def test_mutation_endpoint_audits_success_and_failure_without_confirmation_token(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    result: object,
    expected_status: int,
    expected_outcome: str,
    expected_reason: str | None,
) -> None:
    organization = create_organization(client, auth_headers, None, "Mutation Audit Org")
    with patch(
        "app.api.v1.router.GoogleWorkspaceGmailDelegationService.from_settings",
        return_value=FakeEndpointService(result),
    ):
        response = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/"
            "gmail-delegates/create",
            json={"confirmation_token": "x" * 48},
            headers=auth_headers,
        )

    assert response.status_code == expected_status
    event = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "google_workspace.gmail_delegate.created")
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.outcome == expected_outcome
    assert event.reason == expected_reason
    assert "confirmation" not in str(event.metadata_json).lower()
    assert "x" * 32 not in str(event.metadata_json)
