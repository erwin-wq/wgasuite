from fastapi.testclient import TestClient


def test_backend_core_crud_flow_with_dread_scoring(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    organization_response = client.post(
        "/api/v1/organizations",
        json={"name": "Acme Security", "description": "Internal security team"},
        headers=auth_headers,
    )
    assert organization_response.status_code == 201
    organization = organization_response.json()

    organization_lookup = client.get(
        f"/api/v1/organizations/{organization['id']}",
        headers=auth_headers,
    )
    assert organization_lookup.status_code == 200
    assert organization_lookup.json()["name"] == "Acme Security"

    assessment_response = client.post(
        "/api/v1/assessments",
        json={
            "organization_id": organization["id"],
            "title": "Identity assessment",
            "scope_summary": "Core identity controls",
        },
        headers=auth_headers,
    )
    assert assessment_response.status_code == 201
    assessment = assessment_response.json()

    asset_response = client.post(
        "/api/v1/assets",
        json={
            "organization_id": organization["id"],
            "name": "Google Workspace",
            "asset_type": "saas",
            "identifier": "workspace-primary",
            "description": "Primary collaboration tenant",
        },
        headers=auth_headers,
    )
    assert asset_response.status_code == 201
    asset = asset_response.json()

    finding_response = client.post(
        "/api/v1/findings",
        json={
            "assessment_id": assessment["id"],
            "asset_id": asset["id"],
            "title": "MFA coverage gap",
            "description": "Some users are not enforced through MFA.",
            "status": "open",
            "mitigation": "Enforce MFA for all users.",
            "dread_score": {
                "damage": 8,
                "reproducibility": 8,
                "exploitability": 7,
                "affected_users": 9,
                "discoverability": 8,
            },
        },
        headers=auth_headers,
    )
    assert finding_response.status_code == 201
    finding = finding_response.json()
    assert finding["dread_score"]["total_score"] == 8.0
    assert finding["dread_score"]["risk_level"] == "Critical"

    finding_lookup = client.get(f"/api/v1/findings/{finding['id']}", headers=auth_headers)
    assert finding_lookup.status_code == 200
    assert finding_lookup.json()["id"] == finding["id"]

    updated_response = client.patch(
        f"/api/v1/findings/{finding['id']}",
        json={
            "dread_score": {
                "damage": 6,
                "reproducibility": 6,
                "exploitability": 6,
                "affected_users": 6,
                "discoverability": 6,
            }
        },
        headers=auth_headers,
    )
    assert updated_response.status_code == 200
    updated_finding = updated_response.json()
    assert updated_finding["dread_score"]["total_score"] == 6.0
    assert updated_finding["dread_score"]["risk_level"] == "High"

    assert client.get("/api/v1/organizations", headers=auth_headers).status_code == 200
    assert client.get("/api/v1/assessments", headers=auth_headers).status_code == 200
    assert (
        client.get(f"/api/v1/assessments/{assessment['id']}", headers=auth_headers).status_code
        == 200
    )
    assert client.get("/api/v1/assets", headers=auth_headers).status_code == 200
    assert client.get(f"/api/v1/assets/{asset['id']}", headers=auth_headers).status_code == 200
    assert client.get("/api/v1/findings", headers=auth_headers).status_code == 200
