from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from httplib2 import Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
)
from app.models import ConnectorConfig, Customer, Organization, User
from app.services.google_workspace_connection import (
    DIRECTORY_USER_READONLY_SCOPE,
    GoogleWorkspaceConnectionTester,
)


class FakeRequest:
    def __init__(self, response: object, on_execute: Callable[[], None] | None = None) -> None:
        self.response = response
        self.on_execute = on_execute
        self.execute_kwargs: dict[str, Any] | None = None

    def execute(self, **kwargs: Any) -> object:
        self.execute_kwargs = kwargs
        if self.on_execute:
            self.on_execute()
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeUsersResource:
    def __init__(self, request: FakeRequest) -> None:
        self.request = request
        self.get_kwargs: dict[str, Any] | None = None

    def get(self, **kwargs: Any) -> FakeRequest:
        self.get_kwargs = kwargs
        return self.request


class FakeGoogleClient:
    def __init__(self, response: object, on_execute: Callable[[], None] | None = None) -> None:
        self.request = FakeRequest(response, on_execute)
        self.users_resource = FakeUsersResource(self.request)
        self.closed = False

    def users(self) -> FakeUsersResource:
        return self.users_resource

    def close(self) -> None:
        self.closed = True


class FakeClientFactory:
    def __init__(self, client_or_error: FakeGoogleClient | GoogleWorkspaceError) -> None:
        self.client_or_error = client_or_error
        self.calls: list[dict[str, Any]] = []

    def for_organization(self, **kwargs: Any) -> FakeGoogleClient:
        self.calls.append(kwargs)
        if isinstance(self.client_or_error, GoogleWorkspaceError):
            raise self.client_or_error
        return self.client_or_error


def create_connector(db: Session) -> tuple[ConnectorConfig, User]:
    customer = Customer(name="Connection Test Customer", slug=f"connection-{uuid4().hex}")
    db.add(customer)
    db.flush()
    organization = Organization(name=f"Connection Test Org {uuid4()}", customer_id=customer.id)
    db.add(organization)
    db.flush()
    connector = ConnectorConfig(
        organization_id=organization.id,
        connector_type="google_workspace",
        auth_method="service_account_domain_wide_delegation",
        status="configured",
        display_name="Google Workspace",
        primary_domain="example.com",
        admin_subject_email="admin@example.com",
        credential_provider="file",
        credential_ref="opaque-reference",
    )
    db.add(connector)
    db.commit()
    db.refresh(connector)
    actor = db.scalar(select(User).where(User.email == "admin@example.local"))
    assert actor is not None
    return connector, actor


def test_connection_probe_uses_exact_directory_request_and_persists_success(
    db_session: Session,
) -> None:
    connector, actor = create_connector(db_session)
    client = FakeGoogleClient(
        {
            "id": "safe-google-user-id",
            "primaryEmail": "ADMIN@example.com",
            "customerId": "safe-customer-id",
        }
    )
    factory = FakeClientFactory(client)

    result = GoogleWorkspaceConnectionTester(db_session, factory).test(
        actor=actor,
        connector_config=connector,
    )

    assert result.status == "connected"
    assert result.error_code is None
    assert result.persisted is True
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
        "userKey": "admin@example.com",
        "projection": "basic",
        "viewType": "admin_view",
        "fields": "id,primaryEmail,customerId",
    }
    assert client.request.execute_kwargs == {"num_retries": 0}
    assert client.closed is True

    db_session.refresh(connector)
    assert connector.status == "connected"
    assert connector.last_tested_at is not None
    assert connector.last_error_code is None
    assert connector.last_error is None


@pytest.mark.parametrize(
    ("upstream_error", "expected_code", "expected_category", "retryable"),
    [
        (
            HttpError(Response({"status": "401"}), b"secret upstream body"),
            "google_unauthorized",
            "google",
            False,
        ),
        (
            HttpError(Response({"status": "403"}), b"secret upstream body"),
            "google_forbidden",
            "google",
            False,
        ),
        (
            HttpError(Response({"status": "429"}), b"secret upstream body"),
            "google_rate_limited",
            "google",
            True,
        ),
        (
            HttpError(Response({"status": "503"}), b"secret upstream body"),
            "google_service_unavailable",
            "google",
            True,
        ),
        (TimeoutError("secret timeout"), "google_timeout", "network", True),
        (OSError("secret network"), "google_network_error", "network", True),
        (
            RefreshError("secret OAuth detail", {"error": "unauthorized_client"}),
            "delegation_rejected",
            "google",
            False,
        ),
    ],
)
def test_connection_probe_maps_and_persists_sanitized_failures(
    db_session: Session,
    upstream_error: Exception,
    expected_code: str,
    expected_category: str,
    retryable: bool,
) -> None:
    connector, actor = create_connector(db_session)
    client = FakeGoogleClient(upstream_error)

    result = GoogleWorkspaceConnectionTester(db_session, FakeClientFactory(client)).test(
        actor=actor,
        connector_config=connector,
    )

    assert result.status == "connection_failed"
    assert result.error_code == expected_code
    assert result.error_category == expected_category
    assert result.retryable is retryable
    assert "secret" not in result.message
    db_session.refresh(connector)
    assert connector.status == "connection_failed"
    assert connector.last_error_code == expected_code
    assert connector.last_error == result.message
    assert "secret" not in connector.last_error


@pytest.mark.parametrize(
    "code",
    [
        GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED,
        GoogleWorkspaceErrorCode.CREDENTIAL_REFERENCE_MISSING,
        GoogleWorkspaceErrorCode.CREDENTIALS_NOT_FOUND,
        GoogleWorkspaceErrorCode.INVALID_CREDENTIALS,
        GoogleWorkspaceErrorCode.INVALID_ADMIN_SUBJECT,
    ],
)
def test_connection_probe_distinguishes_configuration_failures(
    db_session: Session,
    code: GoogleWorkspaceErrorCode,
) -> None:
    connector, actor = create_connector(db_session)
    factory = FakeClientFactory(GoogleWorkspaceError(code))

    result = GoogleWorkspaceConnectionTester(db_session, factory).test(
        actor=actor,
        connector_config=connector,
    )

    assert result.status == "connection_failed"
    assert result.error_code == code.value
    assert result.error_category == "configuration"


def test_connection_probe_rejects_unexpected_google_subject(
    db_session: Session,
) -> None:
    connector, actor = create_connector(db_session)
    client = FakeGoogleClient({"primaryEmail": "different@example.com"})

    result = GoogleWorkspaceConnectionTester(db_session, FakeClientFactory(client)).test(
        actor=actor,
        connector_config=connector,
    )

    assert result.status == "connection_failed"
    assert result.error_code == "google_subject_mismatch"
    assert "different@example.com" not in result.message


def test_slow_result_does_not_overwrite_newer_configuration(
    db_session: Session,
) -> None:
    connector, actor = create_connector(db_session)

    def change_configuration() -> None:
        db_session.execute(
            update(ConnectorConfig)
            .where(ConnectorConfig.id == connector.id)
            .values(
                admin_subject_email="new-admin@example.com",
                status="configured",
                last_tested_at=None,
                last_error_code=None,
                last_error=None,
                connection_config_revision=ConnectorConfig.connection_config_revision + 1,
                connection_test_generation=ConnectorConfig.connection_test_generation + 1,
            )
        )
        db_session.commit()

    client = FakeGoogleClient(
        {"primaryEmail": "admin@example.com"},
        on_execute=change_configuration,
    )

    result = GoogleWorkspaceConnectionTester(db_session, FakeClientFactory(client)).test(
        actor=actor,
        connector_config=connector,
    )

    assert result.status == "connected"
    assert result.persisted is False
    db_session.refresh(connector)
    assert connector.status == "configured"
    assert connector.last_tested_at is None


def test_older_concurrent_test_does_not_overwrite_newer_generation(
    db_session: Session,
) -> None:
    connector, actor = create_connector(db_session)

    def start_newer_test() -> None:
        db_session.execute(
            update(ConnectorConfig)
            .where(ConnectorConfig.id == connector.id)
            .values(
                connection_test_generation=ConnectorConfig.connection_test_generation + 1,
            )
        )
        db_session.commit()

    client = FakeGoogleClient(
        {"primaryEmail": "admin@example.com"},
        on_execute=start_newer_test,
    )

    result = GoogleWorkspaceConnectionTester(db_session, FakeClientFactory(client)).test(
        actor=actor,
        connector_config=connector,
    )

    assert result.persisted is False
    db_session.refresh(connector)
    assert connector.status == "configured"
    assert connector.last_tested_at is None
