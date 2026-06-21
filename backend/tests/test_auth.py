from fastapi.testclient import TestClient

DEMO_EMAIL = "admin@example.local"
DEMO_PASSWORD = "ChangeMe123!"


def test_login_with_valid_credentials_returns_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"


def test_login_with_wrong_password_returns_401(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": DEMO_EMAIL, "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_auth_me_with_token_returns_current_user(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.get("/api/v1/auth/me", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == DEMO_EMAIL
    assert body["role"] == "platform_admin"
    assert body["is_active"] is True
    assert body["customer_memberships"] == []


def test_auth_me_without_token_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_protected_endpoint_without_token_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/organizations")

    assert response.status_code == 401


def test_protected_endpoint_with_token_allows_access(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.get("/api/v1/organizations", headers=auth_headers)

    assert response.status_code == 200
