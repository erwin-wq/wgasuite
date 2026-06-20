from fastapi.testclient import TestClient


def create_customer(
    client: TestClient,
    auth_headers: dict[str, str],
    slug: str = "acme-customer",
) -> dict:
    response = client.post(
        "/api/v1/customers",
        json={
            "name": "Acme Customer",
            "slug": slug,
            "contact_name": "Alex Admin",
            "contact_email": "alex@example.local",
            "status": "active",
            "notes": "Customer used by backend tests.",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def test_create_customer_with_valid_token(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    customer = create_customer(client, auth_headers)

    assert customer["name"] == "Acme Customer"
    assert customer["slug"] == "acme-customer"
    assert customer["status"] == "active"
    assert customer["contact_email"] == "alex@example.local"


def test_list_customers_with_valid_token(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    customer = create_customer(client, auth_headers)

    response = client.get("/api/v1/customers", headers=auth_headers)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [customer["id"]]


def test_get_customer_detail(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    customer = create_customer(client, auth_headers)

    response = client.get(f"/api/v1/customers/{customer['id']}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == customer["id"]


def test_patch_customer_updates_fields(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    customer = create_customer(client, auth_headers)

    response = client.patch(
        f"/api/v1/customers/{customer['id']}",
        json={
            "name": "Acme Customer Updated",
            "status": "prospect",
            "notes": "Updated customer notes.",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    updated_customer = response.json()
    assert updated_customer["name"] == "Acme Customer Updated"
    assert updated_customer["status"] == "prospect"
    assert updated_customer["notes"] == "Updated customer notes."


def test_customer_endpoint_without_token_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/customers")

    assert response.status_code == 401


def test_create_organization_with_customer_id_returns_customer_id(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    customer = create_customer(client, auth_headers)

    response = client.post(
        "/api/v1/organizations",
        json={
            "name": "Acme Security",
            "description": "Internal security team",
            "customer_id": customer["id"],
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    organization = response.json()
    assert organization["customer_id"] == customer["id"]

    detail_response = client.get(
        f"/api/v1/organizations/{organization['id']}",
        headers=auth_headers,
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["customer_id"] == customer["id"]


def test_existing_organization_flow_without_customer_id_still_works(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/organizations",
        json={"name": "Standalone Organization", "description": None},
        headers=auth_headers,
    )

    assert response.status_code == 201
    organization = response.json()
    assert organization["customer_id"] is None
    assert organization["name"] == "Standalone Organization"
