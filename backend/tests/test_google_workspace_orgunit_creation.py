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
from app.models import AuditEvent, GoogleWorkspaceOrgUnitCreationConfirmation
from app.services.google_workspace_mutation_safety import (
    confirmation_token_digest,
    consume_confirmation,
)
from app.services.google_workspace_orgunit_creation import (
    GoogleWorkspaceOrgUnitCreationReconciliationService,
    GoogleWorkspaceOrgUnitCreationService,
    OrgUnitCreateAmbiguousError,
    OrgUnitCreatePreview,
    OrgUnitCreateResult,
)
from app.services.google_workspace_orgunits import (
    OrganizationalUnit,
    OrganizationalUnitHierarchy,
    OrganizationalUnitTreeNode,
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


def unit(
    unit_id: str,
    name: str,
    path: str,
    parent_id: str | None,
    parent_path: str | None,
    *,
    description: str | None = None,
    children: tuple[OrganizationalUnitTreeNode, ...] = (),
) -> OrganizationalUnitTreeNode:
    return OrganizationalUnitTreeNode(
        id=unit_id,
        name=name,
        description=description,
        path=path,
        parent_id=parent_id,
        parent_path=parent_path,
        children=children,
    )


ROOT = unit("id:root", "Example", "/", None, None)


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
    def __init__(self, hierarchy: OrganizationalUnitHierarchy) -> None:
        self.hierarchy = hierarchy
        self.parent_override: OrganizationalUnit | Exception | None = None
        self.list_calls: list[dict[str, Any]] = []

    def get_organizational_unit(self, *, org_unit_id: str, **kwargs: Any) -> OrganizationalUnit:
        if self.parent_override is not None:
            if isinstance(self.parent_override, Exception):
                raise self.parent_override
            return self.parent_override
        pending = list(self.hierarchy.roots)
        while pending:
            current = pending.pop()
            if current.id == org_unit_id:
                return OrganizationalUnit(
                    current.id,
                    current.name,
                    current.description,
                    current.path,
                    current.parent_id,
                    current.parent_path,
                )
            pending.extend(current.children)
        raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_NOT_FOUND)

    def list_hierarchy(self, **kwargs: Any) -> OrganizationalUnitHierarchy:
        self.list_calls.append(kwargs)
        return self.hierarchy


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

    def insert(self, **kwargs: Any) -> FakeRequest:
        self.client.calls.append({"method": "insert", "kwargs": kwargs})
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


def response(
    name: str = "Security",
    path: str = "/Security",
    parent_id: str = "id:root",
    parent_path: str = "/",
    description: str | None = "Restricted test unit",
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "orgUnitId": "id:created",
        "name": name,
        "orgUnitPath": path,
        "parentOrgUnitId": parent_id,
        "parentOrgUnitPath": parent_path,
    }
    if description is not None:
        value["description"] = description
    return value


def service(
    db: Session,
    *,
    hierarchy: OrganizationalUnitHierarchy | None = None,
    write_response: object | None = None,
) -> tuple[GoogleWorkspaceOrgUnitCreationService, FakeFactory, FakeOrgunits, Any, Any]:
    connector, actor = create_connector(db)
    orgunits = FakeOrgunits(hierarchy or OrganizationalUnitHierarchy((ROOT,), 1))
    factory = FakeFactory(FakeClient(write_response or response()))
    creation = GoogleWorkspaceOrgUnitCreationService(
        db,
        factory,
        FakeLookup(),
        orgunits,  # type: ignore[arg-type]
    )
    return creation, factory, orgunits, connector, actor


def test_create_root_child_uses_verified_customer_minimal_payload_and_one_write(
    db_session: Session,
) -> None:
    creation, factory, _, connector, actor = service(db_session)
    preview = creation.preview_creation(
        actor=actor,
        organization_id=connector.organization_id,
        parent_org_unit_id="id:root",
        name=" Security ",
        description=" Restricted test unit ",
    )
    result = creation.execute_creation(
        actor=actor,
        organization_id=connector.organization_id,
        confirmation_token=preview.confirmation_token,
    )

    assert result.organizational_unit.path == "/Security"
    assert factory.calls[0]["scopes"] == (DIRECTORY_ORGUNIT_WRITE_SCOPE,)
    write = factory.client.calls[0]
    assert write["kwargs"] == {
        "customerId": "C-google-1",
        "body": {
            "name": "Security",
            "parentOrgUnitPath": "/",
            "description": "Restricted test unit",
        },
        "fields": "orgUnitId,name,description,orgUnitPath,parentOrgUnitId,parentOrgUnitPath",
    }
    assert write["execute_kwargs"] == {"num_retries": 0}
    assert factory.client.closed is True
    saved = db_session.scalar(select(GoogleWorkspaceOrgUnitCreationConfirmation))
    assert saved is not None
    assert saved.status == "succeeded"
    assert saved.created_org_unit_id == "id:created"
    assert saved.token_digest != preview.confirmation_token


def test_create_nested_child_and_omit_empty_description(db_session: Session) -> None:
    engineering = unit("id:engineering", "Engineering", "/Engineering", "id:root", "/")
    root = unit("id:root", "Example", "/", None, None, children=(engineering,))
    creation, factory, _, connector, actor = service(
        db_session,
        hierarchy=OrganizationalUnitHierarchy((root,), 2),
        write_response=response(
            "Platform", "/Engineering/Platform", "id:engineering", "/Engineering", None
        ),
    )
    preview = creation.preview_creation(
        actor=actor,
        organization_id=connector.organization_id,
        parent_org_unit_id="id:engineering",
        name="Platform",
        description="  ",
    )
    creation.execute_creation(
        actor=actor,
        organization_id=connector.organization_id,
        confirmation_token=preview.confirmation_token,
    )
    assert preview.expected_path == "/Engineering/Platform"
    assert factory.client.calls[0]["kwargs"]["body"] == {
        "name": "Platform",
        "parentOrgUnitPath": "/Engineering",
    }


@pytest.mark.parametrize("name", ["", "   ", "a/b", "bad\x00name", "x" * 257])
def test_invalid_names_fail_before_google(db_session: Session, name: str) -> None:
    creation, factory, _, connector, actor = service(db_session)
    with pytest.raises(GoogleWorkspaceError) as error:
        creation.preview_creation(
            actor=actor,
            organization_id=connector.organization_id,
            parent_org_unit_id="id:root",
            name=name,
            description=None,
        )
    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_NAME_INVALID
    assert factory.calls == []


def test_duplicate_name_is_case_insensitive_and_fails_before_confirmation(
    db_session: Session,
) -> None:
    existing = unit("id:security", "Security", "/Security", "id:root", "/")
    root = unit("id:root", "Example", "/", None, None, children=(existing,))
    creation, _, _, connector, actor = service(
        db_session, hierarchy=OrganizationalUnitHierarchy((root,), 2)
    )
    with pytest.raises(GoogleWorkspaceError) as error:
        creation.preview_creation(
            actor=actor,
            organization_id=connector.organization_id,
            parent_org_unit_id="id:root",
            name="security",
            description=None,
        )
    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_ALREADY_EXISTS
    assert db_session.scalar(select(GoogleWorkspaceOrgUnitCreationConfirmation)) is None


def test_unknown_parent_fails_before_confirmation_or_google_write(db_session: Session) -> None:
    creation, factory, _, connector, actor = service(db_session)

    with pytest.raises(GoogleWorkspaceError) as error:
        creation.preview_creation(
            actor=actor,
            organization_id=connector.organization_id,
            parent_org_unit_id="id:missing",
            name="Security",
            description=None,
        )

    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_NOT_FOUND
    assert factory.calls == []
    assert db_session.scalar(select(GoogleWorkspaceOrgUnitCreationConfirmation)) is None


def test_workspace_guests_parent_is_protected(db_session: Session) -> None:
    guests = unit("id:guests", "Workspace Guests", "/Workspace Guests", "id:root", "/")
    root = unit("id:root", "Example", "/", None, None, children=(guests,))
    creation, _, _, connector, actor = service(
        db_session, hierarchy=OrganizationalUnitHierarchy((root,), 2)
    )
    with pytest.raises(GoogleWorkspaceError) as error:
        creation.preview_creation(
            actor=actor,
            organization_id=connector.organization_id,
            parent_org_unit_id="id:guests",
            name="Unsafe",
            description=None,
        )
    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_PARENT_PROTECTED


@pytest.mark.parametrize(
    ("parent_name", "parent_path", "protected"),
    [
        ("Contractors", "/Workspace Guests/Contractors", True),
        ("Workspace Guests Training", "/Workspace Guests Training", False),
    ],
)
def test_workspace_guests_protection_is_segment_aware(
    db_session: Session, parent_name: str, parent_path: str, protected: bool
) -> None:
    parent = unit("id:parent", parent_name, parent_path, "id:root", "/")
    root = unit("id:root", "Example", "/", None, None, children=(parent,))
    creation, _, _, connector, actor = service(
        db_session, hierarchy=OrganizationalUnitHierarchy((root,), 2)
    )

    if protected:
        with pytest.raises(GoogleWorkspaceError) as error:
            creation.preview_creation(
                actor=actor,
                organization_id=connector.organization_id,
                parent_org_unit_id=parent.id,
                name="Child",
                description=None,
            )
        assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_PARENT_PROTECTED
    else:
        preview = creation.preview_creation(
            actor=actor,
            organization_id=connector.organization_id,
            parent_org_unit_id=parent.id,
            name="Child",
            description=None,
        )
        assert preview.expected_path == "/Workspace Guests Training/Child"


def test_cross_tenant_actor_cannot_preview_creation(db_session: Session) -> None:
    creation, factory, _, connector, _ = service(db_session)
    other_connector, _ = create_connector(db_session)
    actor = add_user(db_session, f"ou-cross-tenant-{uuid4().hex}@example.invalid")
    other_customer_id = str(other_connector.organization.customer_id)
    add_membership(db_session, actor, other_customer_id, "customer_admin")

    with pytest.raises(GoogleWorkspaceError) as error:
        creation.preview_creation(
            actor=actor,
            organization_id=connector.organization_id,
            parent_org_unit_id="id:root",
            name="Security",
            description=None,
        )

    assert error.value.code == GoogleWorkspaceErrorCode.ORGANIZATION_ACCESS_DENIED
    assert factory.calls == []


def test_parent_rename_rejects_confirmation_without_write(db_session: Session) -> None:
    creation, factory, orgunits, connector, actor = service(db_session)
    preview = creation.preview_creation(
        actor=actor,
        organization_id=connector.organization_id,
        parent_org_unit_id="id:root",
        name="Security",
        description="Restricted test unit",
    )
    orgunits.parent_override = OrganizationalUnit(
        "id:root", "Renamed", None, "/Renamed", None, None
    )
    with pytest.raises(GoogleWorkspaceError) as error:
        creation.execute_creation(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )
    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CREATE_STATE_CHANGED
    assert factory.calls == []


def test_deleted_parent_rejects_confirmation_without_write(db_session: Session) -> None:
    creation, factory, orgunits, connector, actor = service(db_session)
    preview = creation.preview_creation(
        actor=actor,
        organization_id=connector.organization_id,
        parent_org_unit_id="id:root",
        name="Security",
        description=None,
    )
    orgunits.parent_override = GoogleWorkspaceError(
        GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_NOT_FOUND
    )

    with pytest.raises(GoogleWorkspaceError) as error:
        creation.execute_creation(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )

    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_NOT_FOUND
    assert factory.calls == []


def test_creation_confirmation_consumption_is_atomic(db_session: Session) -> None:
    creation, _, _, connector, actor = service(db_session)
    preview = creation.preview_creation(
        actor=actor,
        organization_id=connector.organization_id,
        parent_org_unit_id="id:root",
        name="Security",
        description=None,
    )
    confirmation = db_session.scalar(select(GoogleWorkspaceOrgUnitCreationConfirmation))
    assert confirmation is not None
    digest = confirmation_token_digest(preview.confirmation_token)

    assert consume_confirmation(
        db_session,
        GoogleWorkspaceOrgUnitCreationConfirmation,
        confirmation_id=confirmation.id,
        token_digest=digest,
    )
    assert not consume_confirmation(
        db_session,
        GoogleWorkspaceOrgUnitCreationConfirmation,
        confirmation_id=confirmation.id,
        token_digest=digest,
    )


def test_confirmation_is_single_use_even_when_write_fails(db_session: Session) -> None:
    denied = GoogleWorkspaceError(GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION)
    creation, factory, _, connector, actor = service(db_session, write_response=denied)
    preview = creation.preview_creation(
        actor=actor,
        organization_id=connector.organization_id,
        parent_org_unit_id="id:root",
        name="Security",
        description="Restricted test unit",
    )
    with pytest.raises(GoogleWorkspaceError) as first:
        creation.execute_creation(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )
    with pytest.raises(GoogleWorkspaceError) as replay:
        creation.execute_creation(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )
    assert first.value.code == GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION
    assert replay.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CREATE_CONFIRMATION_USED
    assert len(factory.client.calls) == 1


def google_http_error(status: int, reason: str, message: str = "sensitive detail") -> HttpError:
    content = json.dumps({"error": {"message": message, "errors": [{"reason": reason}]}}).encode()
    return HttpError(Response({"status": str(status)}), content)


@pytest.mark.parametrize(
    ("write_error", "expected_code", "expected_status"),
    [
        (
            google_http_error(403, "insufficientPermissions"),
            GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION,
            "failed",
        ),
        (
            google_http_error(404, "notFound"),
            GoogleWorkspaceErrorCode.GOOGLE_SUBJECT_NOT_FOUND,
            "failed",
        ),
        (
            google_http_error(409, "duplicate"),
            GoogleWorkspaceErrorCode.GOOGLE_CONFLICT,
            "failed",
        ),
        (
            google_http_error(429, "rateLimitExceeded"),
            GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED,
            "failed",
        ),
        (
            google_http_error(503, "backendError"),
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
def test_google_insert_errors_are_mapped_without_retry_or_duplicate_write(
    db_session: Session,
    write_error: Exception,
    expected_code: GoogleWorkspaceErrorCode,
    expected_status: str,
) -> None:
    creation, factory, _, connector, actor = service(db_session, write_response=write_error)
    preview = creation.preview_creation(
        actor=actor,
        organization_id=connector.organization_id,
        parent_org_unit_id="id:root",
        name="Security",
        description=None,
    )

    with pytest.raises(GoogleWorkspaceError) as error:
        creation.execute_creation(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )

    assert error.value.code == expected_code
    assert len(factory.client.calls) == 1
    assert factory.client.calls[0]["execute_kwargs"] == {"num_retries": 0}
    confirmation = db_session.scalar(select(GoogleWorkspaceOrgUnitCreationConfirmation))
    assert confirmation is not None
    assert confirmation.status == expected_status


def test_google_error_content_and_confirmation_token_are_not_logged(
    db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    sensitive = "private-key-and-token-material-must-not-appear"
    creation, _, _, connector, actor = service(
        db_session,
        write_response=google_http_error(403, "forbidden", sensitive),
    )
    preview = creation.preview_creation(
        actor=actor,
        organization_id=connector.organization_id,
        parent_org_unit_id="id:root",
        name="Security",
        description=None,
    )

    with pytest.raises(GoogleWorkspaceError):
        creation.execute_creation(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )

    assert sensitive not in caplog.text
    assert preview.confirmation_token not in caplog.text


def test_stale_confirmation_expires_without_write(db_session: Session) -> None:
    creation, factory, _, connector, actor = service(db_session)
    preview = creation.preview_creation(
        actor=actor,
        organization_id=connector.organization_id,
        parent_org_unit_id="id:root",
        name="Security",
        description="Restricted test unit",
    )
    confirmation = db_session.scalar(select(GoogleWorkspaceOrgUnitCreationConfirmation))
    assert confirmation is not None
    confirmation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    with pytest.raises(GoogleWorkspaceError) as error:
        creation.execute_creation(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )
    assert error.value.code == GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CREATE_CONFIRMATION_EXPIRED
    assert factory.calls == []


def test_timeout_is_ambiguous_and_read_only_reconciliation_finds_created_unit(
    db_session: Session,
) -> None:
    timeout = GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT, retryable=True)
    creation, factory, orgunits, connector, actor = service(db_session, write_response=timeout)
    preview = creation.preview_creation(
        actor=actor,
        organization_id=connector.organization_id,
        parent_org_unit_id="id:root",
        name="Security",
        description="Restricted test unit",
    )
    with pytest.raises(OrgUnitCreateAmbiguousError):
        creation.execute_creation(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )
    created = unit(
        "id:created",
        "Security",
        "/Security",
        "id:root",
        "/",
        description="Restricted test unit",
    )
    orgunits.hierarchy = OrganizationalUnitHierarchy(
        (unit("id:root", "Example", "/", None, None, children=(created,)),), 2
    )
    reconciliation = GoogleWorkspaceOrgUnitCreationReconciliationService(
        db_session, creation, poll_delays=(0.0,), sleeper=lambda _: None
    ).reconcile_creation(
        actor=actor,
        organization_id=connector.organization_id,
        confirmation_token=preview.confirmation_token,
    )
    assert reconciliation.status == "verified"
    assert reconciliation.organizational_unit == OrganizationalUnit(
        "id:created", "Security", "Restricted test unit", "/Security", "id:root", "/"
    )
    assert len(factory.client.calls) == 1
    assert orgunits.list_calls[-1]["request_timeout_seconds"] <= 5


def test_read_only_reconciliation_reports_unknown_when_creation_is_not_observed(
    db_session: Session,
) -> None:
    timeout = GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT, retryable=True)
    creation, factory, _, connector, actor = service(db_session, write_response=timeout)
    preview = creation.preview_creation(
        actor=actor,
        organization_id=connector.organization_id,
        parent_org_unit_id="id:root",
        name="Security",
        description=None,
    )
    with pytest.raises(OrgUnitCreateAmbiguousError):
        creation.execute_creation(
            actor=actor,
            organization_id=connector.organization_id,
            confirmation_token=preview.confirmation_token,
        )

    result = GoogleWorkspaceOrgUnitCreationReconciliationService(
        db_session, creation, poll_delays=(0.0,), sleeper=lambda _: None
    ).reconcile_creation(
        actor=actor,
        organization_id=connector.organization_id,
        confirmation_token=preview.confirmation_token,
    )

    assert result.status == "unknown"
    assert result.organizational_unit is None
    assert len(factory.client.calls) == 1


def test_preview_endpoint_audits_paths_without_confirmation_token(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    organization = create_organization(client, auth_headers, None, "OU Create Endpoint")
    preview = OrgUnitCreatePreview(
        parent_org_unit_id="id:root",
        parent_path="/",
        name="Security",
        description=None,
        expected_path="/Security",
        confirmation_token="private-confirmation-token-123456789012345",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        effect="Parent policies normally apply.",
    )
    fake = type(
        "FakeCreationService",
        (),
        {"preview_creation": lambda self, **kwargs: preview},
    )()
    with patch(
        "app.api.v1.router.GoogleWorkspaceOrgUnitCreationService.from_settings",
        return_value=fake,
    ):
        response_value = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/orgunits/create/preview",
            json={"parent_org_unit_id": "id:root", "name": "Security"},
            headers=auth_headers,
        )
    assert response_value.status_code == 200
    event = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "google_workspace.orgunit.create_previewed")
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.metadata_json == {"parent_path": "/", "expected_path": "/Security"}
    assert preview.confirmation_token not in str(event.metadata_json)


@pytest.mark.parametrize(
    ("service_result", "expected_status", "expected_outcome"),
    [
        (
            OrgUnitCreateResult(
                OrganizationalUnit("id:created", "Security", None, "/Security", "id:root", "/"),
                "created",
                "/Security was created.",
            ),
            200,
            "success",
        ),
        (
            GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_FORBIDDEN),
            403,
            "failure",
        ),
        (
            OrgUnitCreateAmbiguousError(
                GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT, uuid4(), "/Security"
            ),
            504,
            "unknown",
        ),
    ],
)
def test_create_endpoint_audits_success_failure_and_unknown_without_token(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    service_result: OrgUnitCreateResult | Exception,
    expected_status: int,
    expected_outcome: str,
) -> None:
    organization = create_organization(client, auth_headers, None, "OU Create Audit")
    confirmation_token = "private-confirmation-token-123456789012345"

    def execute_creation(self: Any, **kwargs: Any) -> OrgUnitCreateResult:
        if isinstance(service_result, Exception):
            raise service_result
        return service_result

    fake = type("FakeCreationService", (), {"execute_creation": execute_creation})()
    with patch(
        "app.api.v1.router.GoogleWorkspaceOrgUnitCreationService.from_settings",
        return_value=fake,
    ):
        response_value = client.post(
            f"/api/v1/organizations/{organization['id']}/google-workspace/orgunits/create",
            json={"confirmation_token": confirmation_token},
            headers=auth_headers,
        )

    assert response_value.status_code == expected_status
    event = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "google_workspace.orgunit.created")
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.outcome == expected_outcome
    assert confirmation_token not in str(event.metadata_json)
    assert confirmation_token not in response_value.text


def test_non_admin_cannot_preview_creation(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    customer = create_customer(client, auth_headers, "OU Create Customer")
    organization = create_organization(client, auth_headers, customer["id"], "OU Create Restricted")
    actor = add_user(db_session, f"ou-create-{uuid4().hex}@example.invalid")
    add_membership(db_session, actor, customer["id"], "customer_user")
    response_value = client.post(
        f"/api/v1/organizations/{organization['id']}/google-workspace/orgunits/create/preview",
        json={"parent_org_unit_id": "id:root", "name": "Security"},
        headers=login_headers(client, actor.email),
    )
    assert response_value.status_code == 403
    event = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "google_workspace.orgunit.create_previewed")
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.outcome == "rejected"
    assert event.reason == "organization_access_denied"
