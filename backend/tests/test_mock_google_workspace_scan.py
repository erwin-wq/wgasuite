from uuid import uuid4

from fastapi.testclient import TestClient


def create_organization(
    client: TestClient,
    auth_headers: dict[str, str],
    name: str = "Mock Scan Org",
) -> dict:
    response = client.post(
        "/api/v1/organizations",
        json={"name": name, "description": "Organization for mock scan tests."},
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def create_assessment(
    client: TestClient,
    auth_headers: dict[str, str],
    organization_id: str,
    title: str = "Google Workspace mock scan",
) -> dict:
    response = client.post(
        "/api/v1/assessments",
        json={
            "organization_id": organization_id,
            "title": title,
            "scope_summary": "Mock Google Workspace controls",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def create_assessment_for_scan(client: TestClient, auth_headers: dict[str, str]) -> dict:
    organization = create_organization(client, auth_headers)
    return create_assessment(client, auth_headers, organization["id"])


def run_mock_scan(client: TestClient, auth_headers: dict[str, str], assessment_id: str) -> dict:
    response = client.post(
        f"/api/v1/assessments/{assessment_id}/scan-runs/google-workspace-mock",
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def test_mock_scan_without_token_returns_401(client: TestClient) -> None:
    response = client.post(f"/api/v1/assessments/{uuid4()}/scan-runs/google-workspace-mock")

    assert response.status_code == 401


def test_mock_scan_for_unknown_assessment_returns_404(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.post(
        f"/api/v1/assessments/{uuid4()}/scan-runs/google-workspace-mock",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Assessment not found."


def test_mock_scan_with_token_creates_completed_scan_run_and_findings(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    assessment = create_assessment_for_scan(client, auth_headers)

    scan_run = run_mock_scan(client, auth_headers, assessment["id"])

    assert scan_run["assessment_id"] == assessment["id"]
    assert scan_run["connector_type"] == "google_workspace_mock"
    assert scan_run["status"] == "completed"
    assert scan_run["completed_at"] is not None
    assert scan_run["findings_created"] >= 7
    assert "demo findings" in scan_run["summary"]

    findings_response = client.get("/api/v1/findings", headers=auth_headers)
    assert findings_response.status_code == 200
    findings = [
        finding
        for finding in findings_response.json()
        if finding["assessment_id"] == assessment["id"]
    ]
    assert len(findings) == scan_run["findings_created"]
    assert all(finding["title"].startswith("[Mock Google Workspace]") for finding in findings)
    assert all(finding["asset_id"] is not None for finding in findings)
    assert all(finding["dread_score"]["total_score"] > 0 for finding in findings)
    assert all(finding["dread_score"]["risk_level"] for finding in findings)


def test_scan_run_list_and_detail_endpoints_work(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    assessment = create_assessment_for_scan(client, auth_headers)
    scan_run = run_mock_scan(client, auth_headers, assessment["id"])

    list_response = client.get(
        f"/api/v1/assessments/{assessment['id']}/scan-runs",
        headers=auth_headers,
    )
    assert list_response.status_code == 200
    scan_runs = list_response.json()
    assert [item["id"] for item in scan_runs] == [scan_run["id"]]

    detail_response = client.get(f"/api/v1/scan-runs/{scan_run['id']}", headers=auth_headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == scan_run["id"]


def test_report_contains_mock_scan_findings_after_scan(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    assessment = create_assessment_for_scan(client, auth_headers)
    scan_run = run_mock_scan(client, auth_headers, assessment["id"])

    report_response = client.get(
        f"/api/v1/assessments/{assessment['id']}/report",
        headers=auth_headers,
    )

    assert report_response.status_code == 200
    report = report_response.json()
    assert report["total_findings"] == scan_run["findings_created"]
    assert len(report["findings"]) == scan_run["findings_created"]
    assert any(
        finding["title"] == "[Mock Google Workspace] MFA not enforced for all users"
        for finding in report["findings"]
    )
    assert report["assets"][0]["name"] == "Google Workspace Tenant"
