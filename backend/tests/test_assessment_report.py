from uuid import uuid4

from fastapi.testclient import TestClient


def create_organization(
    client: TestClient,
    auth_headers: dict[str, str],
    name: str = "Acme Security",
) -> dict:
    response = client.post(
        "/api/v1/organizations",
        json={"name": name, "description": "Internal security team"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def create_assessment(
    client: TestClient,
    auth_headers: dict[str, str],
    organization_id: str,
    title: str = "Identity review",
) -> dict:
    response = client.post(
        "/api/v1/assessments",
        json={
            "organization_id": organization_id,
            "title": title,
            "scope_summary": "Identity and SaaS controls",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def create_asset(
    client: TestClient,
    auth_headers: dict[str, str],
    organization_id: str,
    name: str,
) -> dict:
    response = client.post(
        "/api/v1/assets",
        json={
            "organization_id": organization_id,
            "name": name,
            "asset_type": "saas",
            "identifier": name.lower().replace(" ", "-"),
            "description": None,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def create_finding(
    client: TestClient,
    auth_headers: dict[str, str],
    assessment_id: str,
    title: str,
    score_value: int,
    asset_id: str | None = None,
) -> dict:
    response = client.post(
        "/api/v1/findings",
        json={
            "assessment_id": assessment_id,
            "asset_id": asset_id,
            "title": title,
            "description": f"{title} description",
            "status": "open",
            "mitigation": f"Mitigate {title}",
            "dread_score": {
                "damage": score_value,
                "reproducibility": score_value,
                "exploitability": score_value,
                "affected_users": score_value,
                "discoverability": score_value,
            },
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def test_report_endpoint_returns_context_assets_and_multiple_findings(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    organization = create_organization(client, auth_headers)
    assessment = create_assessment(client, auth_headers, organization["id"])
    workspace_asset = create_asset(client, auth_headers, organization["id"], "Google Workspace")
    identity_asset = create_asset(client, auth_headers, organization["id"], "Identity Provider")
    unused_asset = create_asset(client, auth_headers, organization["id"], "Unused Asset")

    low_finding = create_finding(
        client,
        auth_headers,
        assessment["id"],
        "Low finding",
        2,
        workspace_asset["id"],
    )
    medium_finding = create_finding(
        client,
        auth_headers,
        assessment["id"],
        "Medium finding",
        4,
        workspace_asset["id"],
    )
    high_finding = create_finding(
        client,
        auth_headers,
        assessment["id"],
        "High finding",
        6,
        identity_asset["id"],
    )
    critical_finding = create_finding(
        client,
        auth_headers,
        assessment["id"],
        "Critical finding",
        8,
        identity_asset["id"],
    )

    response = client.get(f"/api/v1/assessments/{assessment['id']}/report", headers=auth_headers)

    assert response.status_code == 200
    report = response.json()
    assert report["assessment"]["id"] == assessment["id"]
    assert report["organization"]["id"] == organization["id"]
    assert report["generated_at"]
    assert {asset["id"] for asset in report["assets"]} == {
        workspace_asset["id"],
        identity_asset["id"],
    }
    assert unused_asset["id"] not in {asset["id"] for asset in report["assets"]}
    assert report["total_findings"] == 4
    assert {finding["id"] for finding in report["findings"]} == {
        low_finding["id"],
        medium_finding["id"],
        high_finding["id"],
        critical_finding["id"],
    }


def test_report_summary_counts_average_and_highest_score_are_correct(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    organization = create_organization(client, auth_headers, "Risk Summary Org")
    assessment = create_assessment(client, auth_headers, organization["id"], "Summary assessment")

    create_finding(client, auth_headers, assessment["id"], "Low finding", 2)
    create_finding(client, auth_headers, assessment["id"], "Medium finding", 4)
    create_finding(client, auth_headers, assessment["id"], "High finding", 6)
    create_finding(client, auth_headers, assessment["id"], "Critical finding", 8)

    response = client.get(f"/api/v1/assessments/{assessment['id']}/report", headers=auth_headers)

    assert response.status_code == 200
    report = response.json()
    assert report["findings_per_risk_level"] == {
        "low": 1,
        "medium": 1,
        "high": 1,
        "critical": 1,
    }
    assert report["average_score"] == 5.0
    assert report["highest_score"] == 8.0
    assert report["highest_risk_level"] == "Critical"


def test_report_works_for_empty_assessment(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    organization = create_organization(client, auth_headers, "Empty Report Org")
    assessment = create_assessment(client, auth_headers, organization["id"], "Empty assessment")

    response = client.get(f"/api/v1/assessments/{assessment['id']}/report", headers=auth_headers)

    assert response.status_code == 200
    report = response.json()
    assert report["findings"] == []
    assert report["assets"] == []
    assert report["total_findings"] == 0
    assert report["findings_per_risk_level"] == {
        "low": 0,
        "medium": 0,
        "high": 0,
        "critical": 0,
    }
    assert report["average_score"] is None
    assert report["highest_score"] is None
    assert report["highest_risk_level"] is None


def test_report_returns_404_for_unknown_assessment(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.get(
        f"/api/v1/assessments/{uuid4()}/report",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Assessment not found."
