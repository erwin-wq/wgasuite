from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from googleapiclient.errors import HttpError
from httplib2 import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.google_workspace_credentials import DIRECTORY_ORGUNIT_WRITE_SCOPE
from app.connectors.google_workspace_errors import GoogleWorkspaceError, GoogleWorkspaceErrorCode
from app.models import AuditEvent, GoogleWorkspaceOrgUnitDescriptionConfirmation
from app.services.google_workspace_mutation_safety import (
    confirmation_token_digest,
    consume_confirmation,
)
from app.services.google_workspace_orgunit_description import (
    GoogleWorkspaceOrgUnitDescriptionReconciliationService,
    GoogleWorkspaceOrgUnitDescriptionService,
    OrgUnitDescriptionAmbiguousError,
    OrgUnitDescriptionPreview,
    OrgUnitDescriptionResult,
)
from app.services.google_workspace_orgunits import OrganizationalUnit
from app.services.google_workspace_user_lookup import GoogleWorkspaceUserLookupResult
from tests.test_customer_data_scoping import (
    add_membership,
    add_user,
    create_customer,
    create_organization,
    login_headers,
)
from tests.test_google_workspace_connection import create_connector

TARGET = OrganizationalUnit(
    "id:target", "WGASuite QA", "Original", "/WGASuite-QA", "id:root", "/"
)


class FakeLookup:
    def lookup(self, **kwargs: Any) -> GoogleWorkspaceUserLookupResult:
        return GoogleWorkspaceUserLookupResult(
            id="admin-1",
            customer_id="C-google-1",
            full_name="Admin",
            primary_email="admin@example.com",
            aliases=[],
            non_editable_aliases=[],
            suspended=False,
            archived=False,
            org_unit_path="/",
            is_mailbox_setup=True,
            matched_by="primary_email",
            is_super_admin=True,
            is_delegated_admin=False,
            is_guest_user=False,
        )


class FakeOrgunits:
    def __init__(self, target: OrganizationalUnit = TARGET) -> None:
        self.target: OrganizationalUnit | Exception = target
        self.calls: list[dict[str, Any]] = []

    def get_organizational_unit(self, **kwargs: Any) -> OrganizationalUnit:
        self.calls.append(kwargs)
        if isinstance(self.target, Exception):
            raise self.target
        if kwargs["org_unit_id"] != self.target.id:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_NOT_FOUND)
        return self.target


class FakeRequest:
    def __init__(self, client: FakeClient) -> None:
        self.client = client

    def execute(self, **kwargs: Any) -> Any:
        self.client.calls[-1]["execute_kwargs"] = kwargs
        if isinstance(self.client.response, Exception):
            raise self.client.response
        return self.client.response


class FakeResource:
    def __init__(self, client: FakeClient) -> None:
        self.client = client

    def patch(self, **kwargs: Any) -> FakeRequest:
        self.client.calls.append({"method": "patch", "kwargs": kwargs})
        return FakeRequest(self.client)


class FakeClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def orgunits(self) -> FakeResource:
        return FakeResource(self)

    def close(self) -> None:
        self.closed = True


class FakeFactory:
    def __init__(self, client: FakeClient) -> None:
        self.client = client
        self.calls: list[dict[str, Any]] = []

    def for_directory_orgunits(self, **kwargs: Any) -> FakeClient:
        self.calls.append(kwargs)
        return self.client


def response(description: str | None = "Updated") -> dict[str, Any]:
    value: dict[str, Any] = {
        "orgUnitId": TARGET.id,
        "name": TARGET.name,
        "orgUnitPath": TARGET.path,
        "parentOrgUnitId": TARGET.parent_id,
        "parentOrgUnitPath": TARGET.parent_path,
    }
    if description is not None:
        value["description"] = description
    return value


def service(
    db: Session, *, target: OrganizationalUnit = TARGET, write_response: object | None = None
) -> tuple[GoogleWorkspaceOrgUnitDescriptionService, FakeFactory, FakeOrgunits, Any, Any]:
    connector, actor = create_connector(db)
    orgunits = FakeOrgunits(target)
    factory = FakeFactory(FakeClient(write_response if write_response is not None else response()))
    result = GoogleWorkspaceOrgUnitDescriptionService(
        db, factory, FakeLookup(), orgunits  # type: ignore[arg-type]
    )
    return result, factory, orgunits, connector, actor


def test_update_uses_immutable_id_minimal_body_and_exactly_one_nonretried_patch(
    db_session: Session,
) -> None:
    description, factory, _, connector, actor = service(db_session)
    preview = description.preview_update(
        actor=actor,
        organization_id=connector.organization_id,
        org_unit_id=TARGET.id,
        description="  Updated  ",
    )
    result = description.execute_update(
        actor=actor,
        organization_id=connector.organization_id,
        confirmation_token=preview.confirmation_token,
    )

    assert result.organizational_unit.description == "Updated"
    assert factory.calls == [
        {
            "actor": actor,
            "organization_id": connector.organization_id,
            "scopes": (DIRECTORY_ORGUNIT_WRITE_SCOPE,),
        }
    ]
    assert factory.client.calls == [
        {
            "method": "patch",
            "kwargs": {
                "customerId": "C-google-1",
                "orgUnitPath": TARGET.id,
                "body": {"description": "Updated"},
                "fields": (
                    "orgUnitId,name,description,orgUnitPath,"
                    "parentOrgUnitId,parentOrgUnitPath"
                ),
            },
            "execute_kwargs": {"num_retries": 0},
        }
    ]
    saved = db_session.scalar(select(GoogleWorkspaceOrgUnitDescriptionConfirmation))
    assert saved is not None and saved.status == "succeeded" and saved.consumed_at is not None
    assert saved.token_digest != preview.confirmation_token


def test_empty_description_clears_with_only_empty_description_body(db_session: Session) -> None:
    description, factory, _, connector, actor = service(
        db_session, write_response=response(None)
    )
    preview = description.preview_update(
        actor=actor,
        organization_id=connector.organization_id,
        org_unit_id=TARGET.id,
        description="   ",
    )
    assert preview.proposed_description is None
    description.execute_update(
        actor=actor,
        organization_id=connector.organization_id,
        confirmation_token=preview.confirmation_token,
    )
    assert factory.client.calls[0]["kwargs"]["body"] == {"description": ""}


@pytest.mark.parametrize("value", ["Original", " Original "])
def test_noop_description_is_rejected_before_confirmation(
    db_session: Session, value: str
) -> None:
    description, factory, _, connector, actor = service(db_session)
    with pytest.raises(GoogleWorkspaceError) as error:
        description.preview_update(
            actor=actor,
            organization_id=connector.organization_id,
            org_unit_id=TARGET.id,
            description=value,
        )
    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_UNCHANGED
    assert factory.calls == []
    assert db_session.scalar(select(GoogleWorkspaceOrgUnitDescriptionConfirmation)) is None


@pytest.mark.parametrize("value", ["bad\x00value", "x" * 4097])
def test_invalid_description_is_rejected_before_google(
    db_session: Session, value: str
) -> None:
    description, factory, _, connector, actor = service(db_session)
    with pytest.raises(GoogleWorkspaceError) as error:
        description.preview_update(
            actor=actor,
            organization_id=connector.organization_id,
            org_unit_id=TARGET.id,
            description=value,
        )
    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_INVALID
    assert factory.calls == []


@pytest.mark.parametrize(
    "target",
    [
        OrganizationalUnit("id:root", "Example", None, "/", None, None),
        OrganizationalUnit(
            "id:guests", "Workspace Guests", None, "/Workspace Guests", "id:root", "/"
        ),
        OrganizationalUnit(
            "id:nested",
            "Contractors",
            None,
            "/Workspace Guests/Contractors",
            "id:guests",
            "/Workspace Guests",
        ),
    ],
)
def test_root_and_workspace_guests_subtree_are_protected(
    db_session: Session, target: OrganizationalUnit
) -> None:
    description, _, _, connector, actor = service(db_session, target=target)
    with pytest.raises(GoogleWorkspaceError) as error:
        description.preview_update(
            actor=actor,
            organization_id=connector.organization_id,
            org_unit_id=target.id,
            description="Updated",
        )
    assert (
        error.value.code
        == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_TARGET_PROTECTED
    )


def test_workspace_guests_name_false_positive_is_editable(db_session: Session) -> None:
    target = OrganizationalUnit(
        "id:training",
        "Workspace Guests Training",
        None,
        "/Workspace Guests Training",
        "id:root",
        "/",
    )
    description, _, _, connector, actor = service(db_session, target=target)
    preview = description.preview_update(
        actor=actor,
        organization_id=connector.organization_id,
        org_unit_id=target.id,
        description="Updated",
    )
    assert preview.path == target.path


def test_cross_tenant_actor_cannot_preview(db_session: Session) -> None:
    description, factory, _, connector, _ = service(db_session)
    other_connector, _ = create_connector(db_session)
    actor = add_user(db_session, f"ou-description-{uuid4().hex}@example.invalid")
    add_membership(
        db_session,
        actor,
        str(other_connector.organization.customer_id),
        "customer_admin",
    )
    with pytest.raises(GoogleWorkspaceError) as error:
        description.preview_update(
            actor=actor,
            organization_id=connector.organization_id,
            org_unit_id=TARGET.id,
            description="Updated",
        )
    assert error.value.code == GoogleWorkspaceErrorCode.ORGANIZATION_ACCESS_DENIED
    assert factory.calls == []


@pytest.mark.parametrize(
    "changed",
    [
        OrganizationalUnit(TARGET.id, TARGET.name, "External", TARGET.path, TARGET.parent_id, "/"),
        OrganizationalUnit(TARGET.id, TARGET.name, "Original", "/Renamed", TARGET.parent_id, "/"),
    ],
)
def test_stale_description_or_path_rejects_without_write(
    db_session: Session, changed: OrganizationalUnit
) -> None:
    description, factory, orgunits, connector, actor = service(db_session)
    preview = description.preview_update(
        actor=actor,
        organization_id=connector.organization_id,
        org_unit_id=TARGET.id,
        description="Updated",
    )
    orgunits.target = changed
    with pytest.raises(GoogleWorkspaceError) as error:
        description.execute_update(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )
    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_STATE_CHANGED
    assert factory.calls == []


def test_confirmation_is_atomic_and_cannot_be_replayed(db_session: Session) -> None:
    description, factory, _, connector, actor = service(db_session)
    preview = description.preview_update(
        actor=actor,
        organization_id=connector.organization_id,
        org_unit_id=TARGET.id,
        description="Updated",
    )
    row = db_session.scalar(select(GoogleWorkspaceOrgUnitDescriptionConfirmation))
    assert row is not None
    token_digest = confirmation_token_digest(preview.confirmation_token)
    assert consume_confirmation(
        db_session,
        GoogleWorkspaceOrgUnitDescriptionConfirmation,
        confirmation_id=row.id,
        token_digest=token_digest,
    )
    assert not consume_confirmation(
        db_session,
        GoogleWorkspaceOrgUnitDescriptionConfirmation,
        confirmation_id=row.id,
        token_digest=token_digest,
    )
    with pytest.raises(GoogleWorkspaceError) as error:
        description.execute_update(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )
    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_CONFIRMATION_USED
    assert factory.calls == []


def google_error(status: int, reason: str) -> HttpError:
    content = json.dumps({"error": {"message": "private", "errors": [{"reason": reason}]}}).encode()
    return HttpError(Response({"status": str(status)}), content)


@pytest.mark.parametrize(
    ("write_error", "code", "confirmation_status"),
    [
        (
            google_error(403, "insufficientPermissions"),
            GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION,
            "failed",
        ),
        (
            google_error(404, "notFound"),
            GoogleWorkspaceErrorCode.GOOGLE_SUBJECT_NOT_FOUND,
            "failed",
        ),
        (
            google_error(409, "duplicate"),
            GoogleWorkspaceErrorCode.GOOGLE_CONFLICT,
            "failed",
        ),
        (
            google_error(429, "rateLimitExceeded"),
            GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED,
            "failed",
        ),
        (
            google_error(503, "backendError"),
            GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE,
            "unknown",
        ),
        (
            OSError("private network detail"),
            GoogleWorkspaceErrorCode.GOOGLE_NETWORK_ERROR,
            "unknown",
        ),
    ],
)
def test_google_errors_map_without_retry_or_duplicate_write(
    db_session: Session,
    write_error: Exception,
    code: GoogleWorkspaceErrorCode,
    confirmation_status: str,
) -> None:
    description, factory, _, connector, actor = service(db_session, write_response=write_error)
    preview = description.preview_update(
        actor=actor,
        organization_id=connector.organization_id,
        org_unit_id=TARGET.id,
        description="Updated",
    )
    with pytest.raises(GoogleWorkspaceError) as error:
        description.execute_update(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )
    assert error.value.code == code
    assert len(factory.client.calls) == 1
    assert factory.client.calls[0]["execute_kwargs"] == {"num_retries": 0}
    row = db_session.scalar(select(GoogleWorkspaceOrgUnitDescriptionConfirmation))
    assert row is not None and row.status == confirmation_status


def test_ambiguous_timeout_reconciles_read_only(db_session: Session) -> None:
    timeout = GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT, retryable=True)
    description, factory, orgunits, connector, actor = service(
        db_session, write_response=timeout
    )
    preview = description.preview_update(
        actor=actor,
        organization_id=connector.organization_id,
        org_unit_id=TARGET.id,
        description="Updated",
    )
    with pytest.raises(OrgUnitDescriptionAmbiguousError):
        description.execute_update(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )
    orgunits.target = OrganizationalUnit(
        TARGET.id, TARGET.name, "Updated", TARGET.path, TARGET.parent_id, TARGET.parent_path
    )
    result = GoogleWorkspaceOrgUnitDescriptionReconciliationService(
        db_session, description, poll_delays=(0.0,), sleeper=lambda _: None
    ).reconcile_update(
        actor=actor,
        organization_id=connector.organization_id,
        confirmation_token=preview.confirmation_token,
    )
    assert result.status == "verified"
    assert len(factory.client.calls) == 1
    assert orgunits.calls[-1]["request_timeout_seconds"] <= 5


def test_expired_confirmation_never_writes(db_session: Session) -> None:
    description, factory, _, connector, actor = service(db_session)
    preview = description.preview_update(
        actor=actor,
        organization_id=connector.organization_id,
        org_unit_id=TARGET.id,
        description="Updated",
    )
    row = db_session.scalar(select(GoogleWorkspaceOrgUnitDescriptionConfirmation))
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    with pytest.raises(GoogleWorkspaceError) as error:
        description.execute_update(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )
    assert error.value.code == (
        GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_CONFIRMATION_EXPIRED
    )
    assert factory.calls == []


def test_preview_and_success_audits_exclude_description_and_confirmation(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    organization = create_organization(client, auth_headers, None, "OU Description Audit")
    token = "private-confirmation-token-123456789012345"
    preview = OrgUnitDescriptionPreview(
        org_unit_id=TARGET.id,
        name=TARGET.name,
        path=TARGET.path,
        original_description="Sensitive original",
        proposed_description="Sensitive proposed",
        confirmation_token=token,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        effect="Only the description changes.",
    )
    result = OrgUnitDescriptionResult(
        OrganizationalUnit(
            TARGET.id,
            TARGET.name,
            "Sensitive proposed",
            TARGET.path,
            TARGET.parent_id,
            TARGET.parent_path,
        ),
        "Sensitive original",
        "updated",
        "Description updated.",
    )
    preview_service = type(
        "PreviewService",
        (),
        {"preview_update": lambda self, **kwargs: preview},
    )()
    update_service = type("UpdateService", (), {"execute_update": lambda self, **kwargs: result})()
    with patch(
        "app.api.v1.router.GoogleWorkspaceOrgUnitDescriptionService.from_settings",
        side_effect=[preview_service, update_service],
    ):
        preview_response = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/orgunits/description/preview",
            json={"org_unit_id": TARGET.id, "description": "Sensitive proposed"},
            headers=auth_headers,
        )
        update_response = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/orgunits/description",
            json={"confirmation_token": token},
            headers=auth_headers,
        )
    assert preview_response.status_code == update_response.status_code == 200
    events = list(
        db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.action.in_(
                    (
                        "google_workspace.orgunit.description_update_previewed",
                        "google_workspace.orgunit.description_updated",
                    )
                )
            )
        )
    )
    assert len(events) == 2
    audit_text = str([event.metadata_json for event in events])
    assert token not in audit_text
    assert "Sensitive original" not in audit_text
    assert "Sensitive proposed" not in audit_text


def test_non_admin_cannot_preview_description(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    customer = create_customer(client, auth_headers, "OU Description Customer")
    organization = create_organization(
        client, auth_headers, customer["id"], "OU Description Restricted"
    )
    actor = add_user(db_session, f"ou-description-{uuid4().hex}@example.invalid")
    add_membership(db_session, actor, customer["id"], "customer_user")
    response_value = client.post(
        f"/api/v1/organizations/{organization['id']}/google-workspace/orgunits/description/preview",
        json={"org_unit_id": TARGET.id, "description": "Updated"},
        headers=login_headers(client, actor.email),
    )
    assert response_value.status_code == 403
