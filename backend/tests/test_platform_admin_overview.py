import json
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import CustomerMembership, User
from app.services.passwords import hash_password


def login_headers(client: TestClient, email: str, password: str = "ChangeMe123!") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def add_user(
    db_session: Session,
    email: str,
    role: str = "customer_user",
) -> User:
    user = User(
        email=email,
        full_name="Platform Overview Test User",
        hashed_password=hash_password("ChangeMe123!"),
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def add_membership(
    db_session: Session,
    user: User,
    customer_id: str,
    role: str,
) -> CustomerMembership:
    membership = CustomerMembership(
        user_id=user.id,
        customer_id=UUID(customer_id),
        role=role,
        is_active=True,
    )
    db_session.add(membership)
    db_session.commit()
    db_session.refresh(membership)
    return membership


def create_customer(client: TestClient, auth_headers: dict[str, str]) -> dict:
    unique = uuid4().hex[:8]
    response = client.post(
        "/api/v1/customers",
        json={
            "name": f"Platform Overview Customer {unique}",
            "slug": f"platform-overview-customer-{unique}",
            "contact_name": None,
            "contact_email": None,
            "status": "active",
            "notes": "Created for platform overview tests.",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def create_organization(
    client: TestClient,
    auth_headers: dict[str, str],
    customer_id: str,
) -> dict:
    response = client.post(
        "/api/v1/organizations",
        json={
            "name": f"Platform Overview Org {uuid4().hex[:8]}",
            "description": "Organization for platform overview tests.",
            "customer_id": customer_id,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def create_connector_config(
    client: TestClient,
    auth_headers: dict[str, str],
    organization_id: str,
) -> dict:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/connector-configs/google-workspace",
        json={
            "display_name": "Platform Overview Google Workspace",
            "primary_domain": "platform-overview.example.local",
            "admin_subject_email": "admin@platform-overview.example.local",
            "auth_method": "service_account_domain_wide_delegation",
            "status": "configured",
            "notes": "Metadata only.",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def create_assessment(
    client: TestClient,
    auth_headers: dict[str, str],
    organization_id: str,
) -> dict:
    response = client.post(
        "/api/v1/assessments",
        json={
            "organization_id": organization_id,
            "title": f"Platform Overview Assessment {uuid4().hex[:8]}",
            "scope_summary": "Platform overview test scope.",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def create_workspace(client: TestClient, auth_headers: dict[str, str]) -> dict[str, dict]:
    customer = create_customer(client, auth_headers)
    organization = create_organization(client, auth_headers, customer["id"])
    connector_config = create_connector_config(client, auth_headers, organization["id"])
    test_response = client.post(
        f"/api/v1/connector-configs/{connector_config['id']}/test",
        headers=auth_headers,
    )
    assert test_response.status_code == 200
    assessment = create_assessment(client, auth_headers, organization["id"])
    scan_response = client.post(
        f"/api/v1/assessments/{assessment['id']}/scan-runs/google-workspace-mock",
        headers=auth_headers,
    )
    assert scan_response.status_code == 201
    report_response = client.get(
        f"/api/v1/assessments/{assessment['id']}/report",
        headers=auth_headers,
    )
    assert report_response.status_code == 200
    return {
        "customer": customer,
        "organization": organization,
        "connector_config": connector_config,
        "assessment": assessment,
        "scan_run": scan_response.json(),
    }


def get_overview(client: TestClient, auth_headers: dict[str, str]) -> dict:
    response = client.get("/api/v1/platform-admin/overview", headers=auth_headers)
    assert response.status_code == 200
    return response.json()


def test_platform_admin_overview_without_token_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/platform-admin/overview")

    assert response.status_code == 401


def test_platform_admin_can_read_overview(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    create_workspace(client, auth_headers)

    response = client.get("/api/v1/platform-admin/overview", headers=auth_headers)

    assert response.status_code == 200
    assert "totals" in response.json()


def test_platform_support_can_read_overview(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    create_workspace(client, auth_headers)
    support_user = add_user(db_session, "overview-support@example.local", role="platform_support")
    support_headers = login_headers(client, support_user.email)

    response = client.get("/api/v1/platform-admin/overview", headers=support_headers)

    assert response.status_code == 200


def test_customer_roles_cannot_read_overview(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    workspace = create_workspace(client, auth_headers)

    for role in ("customer_admin", "customer_user", "customer_viewer"):
        user = add_user(db_session, f"overview-{role}-{uuid4().hex[:8]}@example.local")
        add_membership(db_session, user, workspace["customer"]["id"], role)
        member_headers = login_headers(client, user.email)

        response = client.get("/api/v1/platform-admin/overview", headers=member_headers)

        assert response.status_code == 403


def test_overview_contains_totals_customers_connectors_scans_and_audit_events(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    workspace = create_workspace(client, auth_headers)

    overview = get_overview(client, auth_headers)

    assert overview["totals"]["customers_count"] >= 1
    assert overview["totals"]["organizations_count"] >= 1
    assert overview["totals"]["assessments_count"] >= 1
    assert overview["totals"]["connector_configs_count"] >= 1
    assert overview["totals"]["scan_runs_count"] >= 1
    assert overview["totals"]["audit_events_count"] >= 1

    customer_summary = next(
        item for item in overview["customers"] if item["id"] == workspace["customer"]["id"]
    )
    assert customer_summary["name"] == workspace["customer"]["name"]
    assert customer_summary["organization_count"] == 1
    assert customer_summary["connector_config_count"] == 1
    assert customer_summary["last_scan_run_at"] is not None
    assert customer_summary["last_audit_event_at"] is not None

    connector_summary = next(
        item
        for item in overview["connector_configs"]
        if item["id"] == workspace["connector_config"]["id"]
    )
    assert connector_summary["customer_id"] == workspace["customer"]["id"]
    assert connector_summary["customer_name"] == workspace["customer"]["name"]
    assert connector_summary["organization_id"] == workspace["organization"]["id"]
    assert connector_summary["organization_name"] == workspace["organization"]["name"]
    assert connector_summary["connector_type"] == "google_workspace"
    assert connector_summary["last_tested_at"] is not None

    scan_summary = next(
        item for item in overview["recent_scan_runs"] if item["id"] == workspace["scan_run"]["id"]
    )
    assert scan_summary["customer_id"] == workspace["customer"]["id"]
    assert scan_summary["assessment_title"] == workspace["assessment"]["title"]
    assert scan_summary["status"] == "completed"
    assert scan_summary["findings_created"] == 7

    assert any(
        event["action"] == "report.viewed"
        and event["customer_id"] == workspace["customer"]["id"]
        for event in overview["recent_audit_events"]
    )


def test_overview_response_does_not_expose_secret_or_metadata_fields(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    create_workspace(client, auth_headers)

    overview = get_overview(client, auth_headers)
    serialized = json.dumps(overview).lower()

    forbidden_terms = {
        "api_key",
        "client_secret",
        "credentials",
        "metadata_json",
        "private_key",
        "refresh_token",
        "secret",
        "service_account_json",
        "token",
    }
    assert all(term not in serialized for term in forbidden_terms)
