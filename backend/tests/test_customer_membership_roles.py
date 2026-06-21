from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User
from app.services.passwords import hash_password


def create_customer(
    client: TestClient,
    auth_headers: dict[str, str],
    name: str = "Membership Customer",
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
            "notes": "Customer for membership role tests.",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def add_test_user(
    db_session: Session,
    email: str,
    role: str = "customer_user",
    password: str = "ChangeMe123!",
) -> User:
    user = User(
        email=email,
        full_name="Membership Test User",
        hashed_password=hash_password(password),
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def login_headers(client: TestClient, email: str, password: str = "ChangeMe123!") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_membership(
    client: TestClient,
    auth_headers: dict[str, str],
    customer_id: str,
    user_email: str,
    role: str = "customer_admin",
    is_active: bool = True,
) -> dict:
    response = client.post(
        f"/api/v1/customers/{customer_id}/memberships",
        json={"user_email": user_email, "role": role, "is_active": is_active},
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def test_membership_endpoints_without_token_return_401(client: TestClient) -> None:
    response = client.get(f"/api/v1/customers/{uuid4()}/memberships")

    assert response.status_code == 401


def test_non_platform_admin_cannot_manage_memberships(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    customer = create_customer(client, auth_headers)
    user = add_test_user(db_session, "member-no-admin@example.local", role="customer_user")
    member_headers = login_headers(client, user.email)

    response = client.get(
        f"/api/v1/customers/{customer['id']}/memberships",
        headers=member_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Platform admin role required."


def test_platform_admin_can_list_customer_memberships(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    customer = create_customer(client, auth_headers)

    response = client.get(
        f"/api/v1/customers/{customer['id']}/memberships",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == []


def test_platform_admin_can_link_existing_user_to_customer(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    customer = create_customer(client, auth_headers)
    user = add_test_user(db_session, "customer-admin@example.local", role="customer_user")

    membership = create_membership(client, auth_headers, customer["id"], user.email)

    assert membership["user_id"] == str(user.id)
    assert membership["customer_id"] == customer["id"]
    assert membership["role"] == "customer_admin"
    assert membership["is_active"] is True


def test_duplicate_membership_post_updates_existing_membership(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    customer = create_customer(client, auth_headers)
    user = add_test_user(db_session, "duplicate-member@example.local", role="customer_user")
    original = create_membership(client, auth_headers, customer["id"], user.email)

    updated = create_membership(
        client,
        auth_headers,
        customer["id"],
        user.email,
        role="customer_viewer",
        is_active=False,
    )

    assert updated["id"] == original["id"]
    assert updated["role"] == "customer_viewer"
    assert updated["is_active"] is False


def test_platform_admin_can_patch_membership_role(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    customer = create_customer(client, auth_headers)
    user = add_test_user(db_session, "patch-role@example.local", role="customer_user")
    membership = create_membership(client, auth_headers, customer["id"], user.email)

    response = client.patch(
        f"/api/v1/customer-memberships/{membership['id']}",
        json={"role": "customer_user"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["role"] == "customer_user"


def test_platform_admin_can_deactivate_membership(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    customer = create_customer(client, auth_headers)
    user = add_test_user(db_session, "deactivate-member@example.local", role="customer_user")
    membership = create_membership(client, auth_headers, customer["id"], user.email)

    response = client.patch(
        f"/api/v1/customer-memberships/{membership['id']}",
        json={"is_active": False},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_auth_me_shows_customer_memberships(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    customer = create_customer(client, auth_headers)
    user = add_test_user(db_session, "auth-me-member@example.local", role="customer_user")
    create_membership(client, auth_headers, customer["id"], user.email, role="customer_viewer")
    member_headers = login_headers(client, user.email)

    response = client.get("/api/v1/auth/me", headers=member_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == user.email
    assert body["role"] == "customer_user"
    assert body["customer_memberships"] == [
        {
            "customer_id": customer["id"],
            "customer_name": customer["name"],
            "role": "customer_viewer",
            "is_active": True,
        }
    ]


def test_membership_create_for_unknown_user_returns_404(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    customer = create_customer(client, auth_headers)

    response = client.post(
        f"/api/v1/customers/{customer['id']}/memberships",
        json={
            "user_email": "missing-user@example.local",
            "role": "customer_admin",
            "is_active": True,
        },
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found."


def test_membership_create_for_unknown_customer_returns_404(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    user = add_test_user(db_session, "unknown-customer-member@example.local", role="customer_user")

    response = client.post(
        f"/api/v1/customers/{uuid4()}/memberships",
        json={"user_email": user.email, "role": "customer_admin", "is_active": True},
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Customer not found."
