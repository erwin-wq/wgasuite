from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, CustomerMembership, User
from app.services.audit import record_audit_event
from app.services.passwords import hash_password


def add_user(
    db_session: Session,
    email: str,
    role: str = "customer_user",
    password: str = "ChangeMe123!",
) -> User:
    user = User(
        email=email,
        full_name="Audit Test User",
        hashed_password=hash_password(password),
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


def login_headers(client: TestClient, email: str, password: str = "ChangeMe123!") -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_customer(
    client: TestClient,
    auth_headers: dict[str, str],
    name: str = "Audit Customer",
) -> dict:
    response = client.post(
        "/api/v1/customers",
        json={
            "name": f"{name} {uuid4().hex[:8]}",
            "slug": f"audit-customer-{uuid4().hex[:8]}",
            "contact_name": None,
            "contact_email": None,
            "status": "active",
            "notes": "Created for audit tests.",
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
            "name": f"Audit Org {uuid4().hex[:8]}",
            "description": "Created for audit tests.",
            "customer_id": customer_id,
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
            "title": f"Audit assessment {uuid4().hex[:8]}",
            "scope_summary": "Created for audit tests.",
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
            "display_name": "Audit Google Workspace",
            "primary_domain": "audit.example.local",
            "admin_subject_email": "admin@audit.example.local",
            "auth_method": "service_account_domain_wide_delegation",
            "status": "configured",
            "notes": "Metadata only; no secrets.",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def create_workspace(client: TestClient, auth_headers: dict[str, str]) -> dict[str, dict]:
    customer = create_customer(client, auth_headers)
    organization = create_organization(client, auth_headers, customer["id"])
    assessment = create_assessment(client, auth_headers, organization["id"])
    connector_config = create_connector_config(client, auth_headers, organization["id"])
    return {
        "customer": customer,
        "organization": organization,
        "assessment": assessment,
        "connector_config": connector_config,
    }


def record_test_event(
    db_session: Session,
    actor: User,
    customer_id: str,
    action: str = "customer.viewed",
) -> AuditEvent:
    event = record_audit_event(
        db=db_session,
        actor=actor,
        action=action,
        object_type="customer",
        object_id=customer_id,
        customer_id=UUID(customer_id),
        metadata={"source": "test"},
    )
    assert event is not None
    return event


def get_demo_admin(db_session: Session) -> User:
    admin = db_session.scalar(select(User).where(User.email == "admin@example.local"))
    assert admin is not None
    return admin


def test_audit_events_endpoint_requires_token(client: TestClient) -> None:
    response = client.get("/api/v1/audit-events")

    assert response.status_code == 401


def test_platform_admin_can_read_audit_events(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    workspace = create_workspace(client, auth_headers)
    record_test_event(db_session, get_demo_admin(db_session), workspace["customer"]["id"])

    response = client.get("/api/v1/audit-events", headers=auth_headers)

    assert response.status_code == 200
    assert any(event["action"] == "customer.viewed" for event in response.json())


def test_platform_support_can_read_audit_events(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    workspace = create_workspace(client, auth_headers)
    record_test_event(db_session, get_demo_admin(db_session), workspace["customer"]["id"])
    support_user = add_user(db_session, "audit-support@example.local", role="platform_support")
    support_headers = login_headers(client, support_user.email)

    response = client.get("/api/v1/audit-events", headers=support_headers)

    assert response.status_code == 200
    assert len(response.json()) >= 1


def test_customer_admin_can_read_own_customer_audit_events(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    workspace = create_workspace(client, auth_headers)
    record_test_event(db_session, get_demo_admin(db_session), workspace["customer"]["id"])
    customer_admin = add_user(db_session, "audit-customer-admin@example.local")
    add_membership(db_session, customer_admin, workspace["customer"]["id"], "customer_admin")
    customer_headers = login_headers(client, customer_admin.email)

    response = client.get(
        f"/api/v1/customers/{workspace['customer']['id']}/audit-events",
        headers=customer_headers,
    )

    assert response.status_code == 200
    assert [event["customer_id"] for event in response.json()] == [workspace["customer"]["id"]]


def test_customer_user_and_viewer_cannot_read_audit_events(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    workspace = create_workspace(client, auth_headers)

    for role in ("customer_user", "customer_viewer"):
        user = add_user(db_session, f"audit-{role}-{uuid4().hex[:8]}@example.local")
        add_membership(db_session, user, workspace["customer"]["id"], role)
        headers = login_headers(client, user.email)

        response = client.get(
            f"/api/v1/customers/{workspace['customer']['id']}/audit-events",
            headers=headers,
        )

        assert response.status_code == 403


def test_customer_admin_cannot_read_other_customer_audit_events(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    own_workspace = create_workspace(client, auth_headers)
    other_workspace = create_workspace(client, auth_headers)
    record_test_event(db_session, get_demo_admin(db_session), other_workspace["customer"]["id"])
    customer_admin = add_user(db_session, "audit-admin-other@example.local")
    add_membership(db_session, customer_admin, own_workspace["customer"]["id"], "customer_admin")
    customer_headers = login_headers(client, customer_admin.email)

    response = client.get(
        f"/api/v1/customers/{other_workspace['customer']['id']}/audit-events",
        headers=customer_headers,
    )

    assert response.status_code == 403


def test_customer_view_by_platform_admin_creates_audit_event(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    workspace = create_workspace(client, auth_headers)

    view_response = client.get(
        f"/api/v1/customers/{workspace['customer']['id']}",
        headers=auth_headers,
    )
    audit_response = client.get(
        f"/api/v1/audit-events?customer_id={workspace['customer']['id']}&action=customer.viewed",
        headers=auth_headers,
    )

    assert view_response.status_code == 200
    assert audit_response.status_code == 200
    assert audit_response.json()[0]["object_id"] == workspace["customer"]["id"]


def test_connector_test_by_platform_admin_creates_audit_event(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    workspace = create_workspace(client, auth_headers)

    test_response = client.post(
        f"/api/v1/connector-configs/{workspace['connector_config']['id']}/test",
        headers=auth_headers,
    )
    audit_response = client.get(
        "/api/v1/audit-events"
        f"?customer_id={workspace['customer']['id']}&action=connector_config.tested",
        headers=auth_headers,
    )

    assert test_response.status_code == 200
    assert audit_response.status_code == 200
    assert audit_response.json()[0]["object_type"] == "connector_config"


def test_scan_run_detail_by_platform_admin_creates_audit_event(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    workspace = create_workspace(client, auth_headers)
    scan_response = client.post(
        f"/api/v1/assessments/{workspace['assessment']['id']}/scan-runs/google-workspace-mock",
        headers=auth_headers,
    )
    assert scan_response.status_code == 201
    scan_run_id = scan_response.json()["id"]

    detail_response = client.get(f"/api/v1/scan-runs/{scan_run_id}", headers=auth_headers)
    audit_response = client.get(
        f"/api/v1/audit-events?customer_id={workspace['customer']['id']}&action=scan_run.viewed",
        headers=auth_headers,
    )

    assert detail_response.status_code == 200
    assert audit_response.status_code == 200
    assert audit_response.json()[0]["object_id"] == scan_run_id


def test_report_view_by_platform_admin_creates_audit_event(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    workspace = create_workspace(client, auth_headers)

    report_response = client.get(
        f"/api/v1/assessments/{workspace['assessment']['id']}/report",
        headers=auth_headers,
    )
    audit_response = client.get(
        f"/api/v1/audit-events?customer_id={workspace['customer']['id']}&action=report.viewed",
        headers=auth_headers,
    )

    assert report_response.status_code == 200
    assert audit_response.status_code == 200
    assert audit_response.json()[0]["object_type"] == "assessment_report"


def test_audit_metadata_sanitization_removes_sensitive_keys(
    db_session: Session,
) -> None:
    event = record_audit_event(
        db=db_session,
        actor=get_demo_admin(db_session),
        action="support.access_started",
        object_type="customer",
        metadata={
            "safe": "visible",
            "password": "hidden",
            "access_token": "hidden",
            "nested": {"private_key": "hidden", "safe_nested": "visible"},
        },
    )

    assert event is not None
    assert event.metadata_json == {
        "safe": "visible",
        "nested": {"safe_nested": "visible"},
    }


def test_audit_events_limit_and_max_limit_are_enforced(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    workspace = create_workspace(client, auth_headers)
    admin = get_demo_admin(db_session)
    for index in range(205):
        record_test_event(
            db_session,
            admin,
            workspace["customer"]["id"],
            action=f"limit.test.{index}",
        )

    small_response = client.get("/api/v1/audit-events?limit=2", headers=auth_headers)
    large_response = client.get("/api/v1/audit-events?limit=500", headers=auth_headers)

    assert small_response.status_code == 200
    assert large_response.status_code == 200
    assert len(small_response.json()) == 2
    assert len(large_response.json()) == 200
