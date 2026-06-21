from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import CustomerMembership, User
from app.services.passwords import hash_password


def add_user(
    db_session: Session,
    email: str,
    role: str = "customer_user",
    password: str = "ChangeMe123!",
) -> User:
    user = User(
        email=email,
        full_name="Scoping Test User",
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
    is_active: bool = True,
) -> CustomerMembership:
    membership = CustomerMembership(
        user_id=user.id,
        customer_id=UUID(customer_id),
        role=role,
        is_active=is_active,
    )
    db_session.add(membership)
    db_session.commit()
    db_session.refresh(membership)
    return membership


def login_headers(
    client: TestClient,
    email: str,
    password: str = "ChangeMe123!",
) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_customer(
    client: TestClient,
    auth_headers: dict[str, str],
    name: str = "Scoped Customer",
) -> dict:
    slug = f"{name.lower().replace(' ', '-')}-{uuid4().hex[:8]}"
    response = client.post(
        "/api/v1/customers",
        json={
            "name": name,
            "slug": slug,
            "contact_name": None,
            "contact_email": None,
            "status": "active",
            "notes": "Created for customer scoping tests.",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def create_organization(
    client: TestClient,
    auth_headers: dict[str, str],
    customer_id: str | None,
    name: str = "Scoped Organization",
) -> dict:
    response = client.post(
        "/api/v1/organizations",
        json={
            "name": f"{name} {uuid4().hex[:8]}",
            "description": "Created for customer scoping tests.",
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
    title: str = "Scoped assessment",
) -> dict:
    response = client.post(
        "/api/v1/assessments",
        json={
            "organization_id": organization_id,
            "title": f"{title} {uuid4().hex[:8]}",
            "scope_summary": "Scoped test assessment.",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def create_asset(
    client: TestClient,
    auth_headers: dict[str, str],
    organization_id: str,
    name: str = "Scoped asset",
) -> dict:
    response = client.post(
        "/api/v1/assets",
        json={
            "organization_id": organization_id,
            "name": f"{name} {uuid4().hex[:8]}",
            "asset_type": "saas",
            "identifier": None,
            "description": "Scoped test asset.",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def create_finding(
    client: TestClient,
    auth_headers: dict[str, str],
    assessment_id: str,
    asset_id: str | None = None,
) -> dict:
    response = client.post(
        "/api/v1/findings",
        json={
            "assessment_id": assessment_id,
            "asset_id": asset_id,
            "title": f"Scoped finding {uuid4().hex[:8]}",
            "description": "Scoped test finding.",
            "status": "open",
            "mitigation": "Mitigate scoped finding.",
            "dread_score": {
                "damage": 5,
                "reproducibility": 5,
                "exploitability": 5,
                "affected_users": 5,
                "discoverability": 5,
            },
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
            "display_name": "Scoped Google Workspace",
            "primary_domain": "scoped.example.local",
            "admin_subject_email": "admin@scoped.example.local",
            "auth_method": "service_account_domain_wide_delegation",
            "status": "configured",
            "notes": "Metadata only; no secrets.",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def setup_two_customer_workspace(
    client: TestClient,
    auth_headers: dict[str, str],
) -> dict[str, dict]:
    own_customer = create_customer(client, auth_headers, "Own Customer")
    other_customer = create_customer(client, auth_headers, "Other Customer")
    own_org = create_organization(client, auth_headers, own_customer["id"], "Own Org")
    other_org = create_organization(client, auth_headers, other_customer["id"], "Other Org")
    customerless_org = create_organization(client, auth_headers, None, "Platform Org")
    own_assessment = create_assessment(client, auth_headers, own_org["id"], "Own Assessment")
    other_assessment = create_assessment(
        client,
        auth_headers,
        other_org["id"],
        "Other Assessment",
    )
    own_asset = create_asset(client, auth_headers, own_org["id"], "Own Asset")
    other_asset = create_asset(client, auth_headers, other_org["id"], "Other Asset")
    own_finding = create_finding(client, auth_headers, own_assessment["id"], own_asset["id"])
    other_finding = create_finding(client, auth_headers, other_assessment["id"], other_asset["id"])
    own_connector = create_connector_config(client, auth_headers, own_org["id"])
    other_connector = create_connector_config(client, auth_headers, other_org["id"])

    return {
        "own_customer": own_customer,
        "other_customer": other_customer,
        "own_org": own_org,
        "other_org": other_org,
        "customerless_org": customerless_org,
        "own_assessment": own_assessment,
        "other_assessment": other_assessment,
        "own_asset": own_asset,
        "other_asset": other_asset,
        "own_finding": own_finding,
        "other_finding": other_finding,
        "own_connector": own_connector,
        "other_connector": other_connector,
    }


def test_platform_admin_can_continue_full_operational_flow(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    customer = create_customer(client, auth_headers, "Platform Flow Customer")
    organization = create_organization(client, auth_headers, customer["id"], "Platform Flow Org")
    assessment = create_assessment(client, auth_headers, organization["id"])
    asset = create_asset(client, auth_headers, organization["id"])
    finding = create_finding(client, auth_headers, assessment["id"], asset["id"])

    assert client.get("/api/v1/customers", headers=auth_headers).status_code == 200
    organization_response = client.get(
        f"/api/v1/organizations/{organization['id']}",
        headers=auth_headers,
    )
    assessment_response = client.get(
        f"/api/v1/assessments/{assessment['id']}",
        headers=auth_headers,
    )
    assert client.get(f"/api/v1/findings/{finding['id']}", headers=auth_headers).status_code == 200
    report_response = client.get(
        f"/api/v1/assessments/{assessment['id']}/report",
        headers=auth_headers,
    )

    assert organization_response.status_code == 200
    assert assessment_response.status_code == 200
    assert report_response.status_code == 200


def test_customer_admin_sees_only_own_customer_and_cannot_read_other_customer(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    workspace = setup_two_customer_workspace(client, auth_headers)
    user = add_user(db_session, "scope-admin-list@example.local")
    add_membership(db_session, user, workspace["own_customer"]["id"], "customer_admin")
    user_headers = login_headers(client, user.email)

    response = client.get("/api/v1/customers", headers=user_headers)

    assert response.status_code == 200
    assert [customer["id"] for customer in response.json()] == [workspace["own_customer"]["id"]]
    other_response = client.get(
        f"/api/v1/customers/{workspace['other_customer']['id']}",
        headers=user_headers,
    )
    assert other_response.status_code == 403


def test_customer_admin_only_sees_own_organizations_and_not_customerless_organizations(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    workspace = setup_two_customer_workspace(client, auth_headers)
    user = add_user(db_session, "scope-admin-org-list@example.local")
    add_membership(db_session, user, workspace["own_customer"]["id"], "customer_admin")
    user_headers = login_headers(client, user.email)

    response = client.get("/api/v1/organizations", headers=user_headers)

    assert response.status_code == 200
    organization_ids = {organization["id"] for organization in response.json()}
    assert workspace["own_org"]["id"] in organization_ids
    assert workspace["other_org"]["id"] not in organization_ids
    assert workspace["customerless_org"]["id"] not in organization_ids
    customerless_response = client.get(
        f"/api/v1/organizations/{workspace['customerless_org']['id']}",
        headers=user_headers,
    )
    assert customerless_response.status_code == 403


def test_customer_admin_can_create_organization_only_inside_own_customer(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    workspace = setup_two_customer_workspace(client, auth_headers)
    user = add_user(db_session, "scope-admin-create-org@example.local")
    add_membership(db_session, user, workspace["own_customer"]["id"], "customer_admin")
    user_headers = login_headers(client, user.email)

    own_response = client.post(
        "/api/v1/organizations",
        json={
            "name": f"Own Scoped Org {uuid4().hex[:8]}",
            "description": None,
            "customer_id": workspace["own_customer"]["id"],
        },
        headers=user_headers,
    )
    other_response = client.post(
        "/api/v1/organizations",
        json={
            "name": f"Other Scoped Org {uuid4().hex[:8]}",
            "description": None,
            "customer_id": workspace["other_customer"]["id"],
        },
        headers=user_headers,
    )
    customerless_response = client.post(
        "/api/v1/organizations",
        json={
            "name": f"Customerless Scoped Org {uuid4().hex[:8]}",
            "description": None,
            "customer_id": None,
        },
        headers=user_headers,
    )

    assert own_response.status_code == 201
    assert other_response.status_code == 403
    assert customerless_response.status_code == 403


def test_customer_user_cannot_access_or_write_other_customer_assessment(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    workspace = setup_two_customer_workspace(client, auth_headers)
    user = add_user(db_session, "scope-user-other-assessment@example.local")
    add_membership(db_session, user, workspace["own_customer"]["id"], "customer_user")
    user_headers = login_headers(client, user.email)

    assessment_response = client.get(
        f"/api/v1/assessments/{workspace['other_assessment']['id']}",
        headers=user_headers,
    )
    finding_response = client.post(
        "/api/v1/findings",
        json={
            "assessment_id": workspace["other_assessment"]["id"],
            "asset_id": workspace["other_asset"]["id"],
            "title": "Cross customer finding",
            "description": None,
            "status": "open",
            "mitigation": None,
            "dread_score": {
                "damage": 5,
                "reproducibility": 5,
                "exploitability": 5,
                "affected_users": 5,
                "discoverability": 5,
            },
        },
        headers=user_headers,
    )

    assert assessment_response.status_code == 403
    assert finding_response.status_code == 403


def test_customer_viewer_can_read_own_report_but_cannot_write_or_start_scan(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    workspace = setup_two_customer_workspace(client, auth_headers)
    user = add_user(db_session, "scope-viewer@example.local")
    add_membership(db_session, user, workspace["own_customer"]["id"], "customer_viewer")
    user_headers = login_headers(client, user.email)

    report_response = client.get(
        f"/api/v1/assessments/{workspace['own_assessment']['id']}/report",
        headers=user_headers,
    )
    finding_response = client.post(
        "/api/v1/findings",
        json={
            "assessment_id": workspace["own_assessment"]["id"],
            "asset_id": workspace["own_asset"]["id"],
            "title": "Viewer finding",
            "description": None,
            "status": "open",
            "mitigation": None,
            "dread_score": {
                "damage": 5,
                "reproducibility": 5,
                "exploitability": 5,
                "affected_users": 5,
                "discoverability": 5,
            },
        },
        headers=user_headers,
    )
    scan_response = client.post(
        f"/api/v1/assessments/{workspace['own_assessment']['id']}/scan-runs/google-workspace-mock",
        headers=user_headers,
    )

    assert report_response.status_code == 200
    assert finding_response.status_code == 403
    assert scan_response.status_code == 403


def test_platform_support_can_read_support_data_but_cannot_write(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    workspace = setup_two_customer_workspace(client, auth_headers)
    support_user = add_user(
        db_session,
        "platform-support@example.local",
        role="platform_support",
    )
    support_headers = login_headers(client, support_user.email)

    customer_list = client.get("/api/v1/customers", headers=support_headers)
    org_response = client.get(
        f"/api/v1/organizations/{workspace['other_org']['id']}",
        headers=support_headers,
    )
    create_customer_response = client.post(
        "/api/v1/customers",
        json={
            "name": f"Support Write Customer {uuid4().hex[:8]}",
            "slug": f"support-write-{uuid4().hex[:8]}",
            "contact_name": None,
            "contact_email": None,
            "status": "active",
            "notes": None,
        },
        headers=support_headers,
    )
    create_org_response = client.post(
        "/api/v1/organizations",
        json={
            "name": f"Support Write Org {uuid4().hex[:8]}",
            "description": None,
            "customer_id": workspace["own_customer"]["id"],
        },
        headers=support_headers,
    )
    connector_test_response = client.post(
        f"/api/v1/connector-configs/{workspace['own_connector']['id']}/test",
        headers=support_headers,
    )

    assert customer_list.status_code == 200
    assert org_response.status_code == 200
    assert create_customer_response.status_code == 403
    assert create_org_response.status_code == 403
    assert connector_test_response.status_code == 200


def test_inactive_membership_gives_no_customer_access(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    workspace = setup_two_customer_workspace(client, auth_headers)
    user = add_user(db_session, "inactive-membership@example.local")
    add_membership(
        db_session,
        user,
        workspace["own_customer"]["id"],
        "customer_admin",
        is_active=False,
    )
    user_headers = login_headers(client, user.email)

    list_response = client.get("/api/v1/customers", headers=user_headers)
    detail_response = client.get(
        f"/api/v1/customers/{workspace['own_customer']['id']}",
        headers=user_headers,
    )

    assert list_response.status_code == 200
    assert list_response.json() == []
    assert detail_response.status_code == 403


def test_connector_config_from_other_customer_is_not_accessible(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    workspace = setup_two_customer_workspace(client, auth_headers)
    user = add_user(db_session, "connector-scope@example.local")
    add_membership(db_session, user, workspace["own_customer"]["id"], "customer_admin")
    user_headers = login_headers(client, user.email)

    detail_response = client.get(
        f"/api/v1/connector-configs/{workspace['other_connector']['id']}",
        headers=user_headers,
    )
    list_response = client.get(
        f"/api/v1/organizations/{workspace['other_org']['id']}/connector-configs",
        headers=user_headers,
    )
    test_response = client.post(
        f"/api/v1/connector-configs/{workspace['other_connector']['id']}/test",
        headers=user_headers,
    )

    assert detail_response.status_code == 403
    assert list_response.status_code == 403
    assert test_response.status_code == 403


def test_mock_scan_for_other_customer_is_not_allowed(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    workspace = setup_two_customer_workspace(client, auth_headers)
    user = add_user(db_session, "mock-scan-scope@example.local")
    add_membership(db_session, user, workspace["own_customer"]["id"], "customer_user")
    user_headers = login_headers(client, user.email)

    response = client.post(
        f"/api/v1/assessments/{workspace['other_assessment']['id']}/scan-runs/google-workspace-mock",
        headers=user_headers,
    )

    assert response.status_code == 403
