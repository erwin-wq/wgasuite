from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, ConnectorConfig
from app.services.google_workspace_connection import GoogleWorkspaceConnectionTester
from tests.test_google_workspace_connection import FakeClientFactory, FakeGoogleClient


def create_organization(
    client: TestClient,
    auth_headers: dict[str, str],
    name: str = "Connector Config Org",
) -> dict:
    response = client.post(
        "/api/v1/organizations",
        json={"name": name, "description": "Organization for connector config tests."},
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def create_google_workspace_config(
    client: TestClient,
    auth_headers: dict[str, str],
    organization_id: str,
    display_name: str = "Primary Google Workspace",
) -> dict:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/connector-configs/google-workspace",
        json={
            "display_name": display_name,
            "primary_domain": "example.local",
            "admin_subject_email": "admin@example.local",
            "auth_method": "service_account_domain_wide_delegation",
            "credential_provider": "file",
            "credential_ref": "test-workspace",
            "status": "configured",
            "notes": "Metadata only; no secrets stored.",
            "private_key": "must-not-be-accepted",
            "service_account_json": {"private_key": "must-not-be-accepted"},
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def test_connector_config_without_token_returns_401(client: TestClient) -> None:
    response = client.get(f"/api/v1/organizations/{uuid4()}/connector-configs")

    assert response.status_code == 401


def test_create_google_workspace_config_with_token(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    organization = create_organization(client, auth_headers)

    connector_config = create_google_workspace_config(client, auth_headers, organization["id"])

    assert connector_config["organization_id"] == organization["id"]
    assert connector_config["connector_type"] == "google_workspace"
    assert connector_config["auth_method"] == "service_account_domain_wide_delegation"
    assert connector_config["status"] == "configured"
    assert connector_config["display_name"] == "Primary Google Workspace"
    assert connector_config["primary_domain"] == "example.local"
    assert connector_config["admin_subject_email"] == "admin@example.local"
    assert connector_config["credential_provider"] == "file"
    assert connector_config["credentials_configured"] is True
    assert "credential_ref" not in connector_config


def test_list_detail_and_patch_connector_config(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    organization = create_organization(client, auth_headers)
    connector_config = create_google_workspace_config(client, auth_headers, organization["id"])

    list_response = client.get(
        f"/api/v1/organizations/{organization['id']}/connector-configs",
        headers=auth_headers,
    )
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [connector_config["id"]]

    detail_response = client.get(
        f"/api/v1/connector-configs/{connector_config['id']}",
        headers=auth_headers,
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == connector_config["id"]

    patch_response = client.patch(
        f"/api/v1/connector-configs/{connector_config['id']}",
        json={
            "display_name": "Workspace OAuth readiness",
            "primary_domain": "workspace.example.local",
            "admin_subject_email": "workspace-admin@example.local",
            "auth_method": "oauth_admin_consent",
            "status": "connection_failed",
            "notes": "Waiting for later OAuth implementation.",
        },
        headers=auth_headers,
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["display_name"] == "Workspace OAuth readiness"
    assert patched["primary_domain"] == "workspace.example.local"
    assert patched["admin_subject_email"] == "workspace-admin@example.local"
    assert patched["auth_method"] == "oauth_admin_consent"
    assert patched["status"] == "configured"
    assert patched["notes"] == "Waiting for later OAuth implementation."


def test_duplicate_post_updates_existing_google_workspace_config(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    organization = create_organization(client, auth_headers)
    original = create_google_workspace_config(client, auth_headers, organization["id"])

    response = client.post(
        f"/api/v1/organizations/{organization['id']}/connector-configs/google-workspace",
        json={
            "display_name": "Updated Google Workspace",
            "primary_domain": "updated.example.local",
            "admin_subject_email": None,
            "auth_method": "manual_import",
            "status": "not_configured",
            "notes": "Updated through idempotent POST.",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    updated = response.json()
    assert updated["id"] == original["id"]
    assert updated["display_name"] == "Updated Google Workspace"
    assert updated["primary_domain"] == "updated.example.local"
    assert updated["admin_subject_email"] is None
    assert updated["auth_method"] == "manual_import"
    assert updated["status"] == "configured"
    assert updated["credentials_configured"] is True
    assert "credential_ref" not in updated


def test_test_endpoint_returns_real_structured_result_and_audits_attempt(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    organization = create_organization(client, auth_headers)
    connector_config = create_google_workspace_config(client, auth_headers, organization["id"])
    google_client = FakeGoogleClient({"primaryEmail": "admin@example.local"})
    client_factory = FakeClientFactory(google_client)

    with patch(
        "app.api.v1.router.GoogleWorkspaceConnectionTester.from_settings",
        side_effect=lambda db: GoogleWorkspaceConnectionTester(db, client_factory),
    ):
        response = client.post(
            f"/api/v1/connector-configs/{connector_config['id']}/test",
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "connected"
    assert body["tested_at"] is not None
    assert body["error_code"] is None
    assert body["persisted"] is True

    detail_response = client.get(
        f"/api/v1/connector-configs/{connector_config['id']}",
        headers=auth_headers,
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["last_tested_at"] is not None
    assert detail["status"] == "connected"
    assert detail["last_error_code"] is None
    assert detail["last_error"] is None

    event = db_session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.object_id == connector_config["id"],
            AuditEvent.action == "connector_config.tested",
        )
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.outcome == "success"
    assert event.metadata_json == {
        "connector_type": "google_workspace",
        "status": "connected",
        "error_code": None,
        "persisted": True,
    }
    assert "test-workspace" not in str(event.metadata_json)


def test_connection_critical_update_invalidates_previous_success(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    organization = create_organization(client, auth_headers)
    created = create_google_workspace_config(client, auth_headers, organization["id"])
    connector = db_session.get(ConnectorConfig, UUID(created["id"]))
    assert connector is not None
    connector.status = "connected"
    connector.last_tested_at = connector.updated_at
    connector.last_error_code = None
    connector.last_error = None
    original_revision = connector.connection_config_revision
    db_session.commit()

    response = client.patch(
        f"/api/v1/connector-configs/{created['id']}",
        json={"admin_subject_email": "new-admin@example.local", "status": "connected"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "configured"
    assert body["last_tested_at"] is None
    assert body["last_error_code"] is None
    db_session.refresh(connector)
    assert connector.connection_config_revision == original_revision + 1


def test_connector_config_for_unknown_organization_returns_404(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.post(
        f"/api/v1/organizations/{uuid4()}/connector-configs/google-workspace",
        json={"display_name": "Google Workspace"},
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found."


def test_connector_config_response_has_no_secret_fields(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    organization = create_organization(client, auth_headers)

    connector_config = create_google_workspace_config(client, auth_headers, organization["id"])

    forbidden_fields = {
        "client_secret",
        "credentials",
        "private_key",
        "refresh_token",
        "service_account_json",
        "token",
        "credential_ref",
    }
    assert forbidden_fields.isdisjoint(connector_config.keys())


def test_connector_credential_reference_change_is_audited_without_value(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    organization = create_organization(client, auth_headers)

    connector_config = create_google_workspace_config(client, auth_headers, organization["id"])

    event = db_session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.object_id == connector_config["id"],
            AuditEvent.action == "connector_config.created",
        )
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert event.metadata_json is not None
    assert event.metadata_json["credential_reference_changed"] is True
    assert "credential_ref" not in event.metadata_json["changed_fields"]
    assert "test-workspace" not in str(event.metadata_json)
