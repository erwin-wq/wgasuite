from uuid import uuid4

from fastapi.testclient import TestClient


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
    assert patched["status"] == "connection_failed"
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
    assert updated["status"] == "not_configured"


def test_test_endpoint_returns_not_implemented(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    organization = create_organization(client, auth_headers)
    connector_config = create_google_workspace_config(client, auth_headers, organization["id"])

    response = client.post(
        f"/api/v1/connector-configs/{connector_config['id']}/test",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_implemented"
    assert body["message"] == "Real Google Workspace connection testing is not implemented yet."
    expected_next_step = (
        "Configure service account domain-wide delegation or OAuth admin consent in a future "
        "release."
    )
    assert (
        body["recommended_next_step"]
        == expected_next_step
    )

    detail_response = client.get(
        f"/api/v1/connector-configs/{connector_config['id']}",
        headers=auth_headers,
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["last_tested_at"] is not None
    expected_error = "Real Google Workspace connection testing is not implemented yet."
    assert detail["last_error"] == expected_error


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
    }
    assert forbidden_fields.isdisjoint(connector_config.keys())
