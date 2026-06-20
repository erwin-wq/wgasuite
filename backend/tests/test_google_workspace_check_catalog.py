from fastapi.testclient import TestClient

from app.connectors.google_workspace_checks import list_google_workspace_checks


def test_check_catalog_without_token_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/connectors/google-workspace/checks")

    assert response.status_code == 401


def test_check_catalog_with_token_returns_seven_checks(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.get("/api/v1/connectors/google-workspace/checks", headers=auth_headers)

    assert response.status_code == 200
    checks = response.json()
    assert len(checks) == 7
    assert checks[0]["check_id"] == "GW-MFA-001"
    assert checks[0]["mock_status"] == "mock_only"
    assert checks[0]["maps_to_finding_title"].startswith("[Mock Google Workspace]")


def test_check_catalog_has_unique_check_ids(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.get("/api/v1/connectors/google-workspace/checks", headers=auth_headers)

    assert response.status_code == 200
    check_ids = [check["check_id"] for check in response.json()]
    assert len(check_ids) == len(set(check_ids))


def test_check_catalog_matches_connector_definitions(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.get("/api/v1/connectors/google-workspace/checks", headers=auth_headers)

    assert response.status_code == 200
    api_check_ids = [check["check_id"] for check in response.json()]
    connector_check_ids = [check.check_id for check in list_google_workspace_checks()]
    assert api_check_ids == connector_check_ids
