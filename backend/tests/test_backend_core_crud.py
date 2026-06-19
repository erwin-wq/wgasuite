from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture
def client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_backend_core_crud_flow_with_dread_scoring(client: TestClient) -> None:
    organization_response = client.post(
        "/api/v1/organizations",
        json={"name": "Acme Security", "description": "Internal security team"},
    )
    assert organization_response.status_code == 201
    organization = organization_response.json()

    organization_lookup = client.get(f"/api/v1/organizations/{organization['id']}")
    assert organization_lookup.status_code == 200
    assert organization_lookup.json()["name"] == "Acme Security"

    assessment_response = client.post(
        "/api/v1/assessments",
        json={
            "organization_id": organization["id"],
            "title": "Identity assessment",
            "scope_summary": "Core identity controls",
        },
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
    )
    assert finding_response.status_code == 201
    finding = finding_response.json()
    assert finding["dread_score"]["total_score"] == 8.0
    assert finding["dread_score"]["risk_level"] == "Critical"

    finding_lookup = client.get(f"/api/v1/findings/{finding['id']}")
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
    )
    assert updated_response.status_code == 200
    updated_finding = updated_response.json()
    assert updated_finding["dread_score"]["total_score"] == 6.0
    assert updated_finding["dread_score"]["risk_level"] == "High"

    assert client.get("/api/v1/organizations").status_code == 200
    assert client.get("/api/v1/assessments").status_code == 200
    assert client.get(f"/api/v1/assessments/{assessment['id']}").status_code == 200
    assert client.get("/api/v1/assets").status_code == 200
    assert client.get(f"/api/v1/assets/{asset['id']}").status_code == 200
    assert client.get("/api/v1/findings").status_code == 200
