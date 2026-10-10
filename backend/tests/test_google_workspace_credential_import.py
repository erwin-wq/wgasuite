import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, ConnectorConfig
from app.services.google_workspace_credential_import import ManagedCredentialStore
from tests.test_connector_config import create_google_workspace_config, create_organization
from tests.test_customer_data_scoping import (
    add_membership,
    add_user,
    create_customer,
    login_headers,
)


def service_account_key() -> dict[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "sensitive-key-id",
        "private_key": pem,
        "client_email": "scanner@test-project.iam.gserviceaccount.com",
        "client_id": "123456789012345678901",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/scanner",
        "universe_domain": "googleapis.com",
    }


def settings(managed: Path, external: Path, max_bytes: int = 65_536) -> SimpleNamespace:
    return SimpleNamespace(
        google_workspace_managed_credentials_directory=managed,
        google_workspace_credentials_directory=external,
        google_workspace_credential_max_bytes=max_bytes,
    )


def test_managed_import_persists_private_file_and_only_returns_safe_metadata(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    tmp_path: Path,
) -> None:
    organization = create_organization(client, auth_headers)
    connector = create_google_workspace_config(client, auth_headers, organization["id"])
    managed = tmp_path / "managed"
    external = tmp_path / "external"
    before_import = db_session.get(ConnectorConfig, UUID(connector["id"]))
    assert before_import is not None
    before_import.status = "connected"
    before_import.last_tested_at = before_import.updated_at
    original_revision = before_import.connection_config_revision
    db_session.commit()

    with patch("app.api.v1.router.get_settings", return_value=settings(managed, external)):
        response = client.put(
            f"/api/v1/connector-configs/{connector['id']}/credentials",
            content=json.dumps(service_account_key()),
            headers={**auth_headers, "Content-Type": "application/json"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "credential_provider": "managed_file",
        "credentials_configured": True,
        "service_account_email": "scanner@test-project.iam.gserviceaccount.com",
        "service_account_client_id": "123456789012345678901",
    }
    assert "private_key" not in response.text
    stored = managed / organization["id"] / "service-account.json"
    assert stored.exists()
    assert stored.stat().st_mode & 0o777 == 0o600
    assert stored.parent.stat().st_mode & 0o777 == 0o700

    db_session.expire_all()
    persisted = db_session.get(ConnectorConfig, UUID(connector["id"]))
    assert persisted is not None
    assert persisted.status == "configured"
    assert persisted.last_tested_at is None
    assert persisted.credential_provider == "managed_file"
    assert persisted.credential_ref == "service-account"
    assert persisted.connection_config_revision == original_revision + 2

    event = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "connector_credentials.imported")
        .order_by(AuditEvent.created_at.desc())
    )
    assert event is not None
    assert "private_key" not in str(event.metadata_json)
    assert "sensitive-key-id" not in str(event.metadata_json)


def test_import_rejects_invalid_json_without_writing_file(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    organization = create_organization(client, auth_headers)
    connector = create_google_workspace_config(client, auth_headers, organization["id"])
    managed = tmp_path / "managed"

    with patch(
        "app.api.v1.router.get_settings",
        return_value=settings(managed, tmp_path / "external"),
    ):
        response = client.put(
            f"/api/v1/connector-configs/{connector['id']}/credentials",
            content="not-json",
            headers={**auth_headers, "Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_json"
    assert not managed.exists()


def test_import_rejects_oversized_body_before_validation(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    organization = create_organization(client, auth_headers)
    connector = create_google_workspace_config(client, auth_headers, organization["id"])

    with patch(
        "app.api.v1.router.get_settings",
        return_value=settings(tmp_path / "managed", tmp_path / "external", max_bytes=16),
    ):
        response = client.put(
            f"/api/v1/connector-configs/{connector['id']}/credentials",
            content=b"{" + (b"x" * 32),
            headers={**auth_headers, "Content-Type": "application/json"},
        )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "credential_too_large"


def test_import_rejects_wrong_credential_shape_and_private_key(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    organization = create_organization(client, auth_headers)
    connector = create_google_workspace_config(client, auth_headers, organization["id"])
    config = settings(tmp_path / "managed", tmp_path / "external")

    with patch("app.api.v1.router.get_settings", return_value=config):
        wrong_type = client.put(
            f"/api/v1/connector-configs/{connector['id']}/credentials",
            content=json.dumps({"type": "authorized_user"}),
            headers={**auth_headers, "Content-Type": "application/json"},
        )
        invalid_key = service_account_key()
        invalid_key["private_key"] = "not-a-private-key"
        bad_key = client.put(
            f"/api/v1/connector-configs/{connector['id']}/credentials",
            content=json.dumps(invalid_key),
            headers={**auth_headers, "Content-Type": "application/json"},
        )

    assert wrong_type.status_code == 422
    assert wrong_type.json()["detail"]["code"] == "invalid_credential_type"
    assert bad_key.status_code == 422
    assert bad_key.json()["detail"]["code"] == "invalid_private_key"


def test_external_reference_is_validated_and_selected(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    organization = create_organization(client, auth_headers)
    connector = create_google_workspace_config(client, auth_headers, organization["id"])
    external = tmp_path / "external" / organization["id"]
    external.mkdir(parents=True)
    (external / "provisioned.json").write_text(json.dumps(service_account_key()))

    with patch(
        "app.api.v1.router.get_settings",
        return_value=settings(tmp_path / "managed", tmp_path / "external"),
    ):
        response = client.put(
            f"/api/v1/connector-configs/{connector['id']}/credentials/external",
            json={"credential_ref": "provisioned"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["credential_provider"] == "file"
    assert "credential_ref" not in response.json()


def test_managed_store_replaces_atomically_without_leaving_temporary_files(
    tmp_path: Path,
) -> None:
    store = ManagedCredentialStore(tmp_path / "managed")
    organization_id = "11111111-1111-1111-1111-111111111111"
    first = service_account_key()
    second = {**first, "project_id": "rotated-project"}

    with patch(
        "app.services.google_workspace_credential_import.os.replace",
        wraps=os.replace,
    ) as replace:
        store.store(organization_id, first)
        store.store(organization_id, second)

    target_directory = tmp_path / "managed" / organization_id
    persisted = json.loads((target_directory / "service-account.json").read_text())
    assert persisted["project_id"] == "rotated-project"
    assert replace.call_count == 2
    assert list(target_directory.glob("*.tmp")) == []


def test_customer_user_viewer_and_other_tenant_cannot_import_credentials(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    tmp_path: Path,
) -> None:
    customer = create_customer(client, auth_headers, "Credential Owner")
    other_customer = create_customer(client, auth_headers, "Other Credential Owner")
    organization_response = client.post(
        "/api/v1/organizations",
        json={"name": "Credential tenant", "customer_id": customer["id"]},
        headers=auth_headers,
    )
    assert organization_response.status_code == 201
    organization = organization_response.json()
    connector = create_google_workspace_config(client, auth_headers, organization["id"])

    roles = [
        ("user@credential.test", "customer_user", customer["id"]),
        ("viewer@credential.test", "customer_viewer", customer["id"]),
        ("other-admin@credential.test", "customer_admin", other_customer["id"]),
    ]
    credential = json.dumps(service_account_key())
    role_headers: list[dict[str, str]] = []
    for email, role, customer_id in roles:
        user = add_user(db_session, email)
        add_membership(db_session, user, customer_id, role)
        role_headers.append(login_headers(client, email))

    with (
        patch(
            "app.api.v1.router.get_settings",
            return_value=settings(tmp_path / "managed", tmp_path / "external"),
        ),
        patch("app.api.v1.router.read_credential_request") as body_reader,
    ):
        for headers in role_headers:
            response = client.put(
                f"/api/v1/connector-configs/{connector['id']}/credentials",
                content=credential,
                headers={**headers, "Content-Type": "application/json"},
            )
            assert response.status_code == 403

    body_reader.assert_not_called()
    assert not (tmp_path / "managed").exists()
    denied_events = list(
        db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "connector_credentials.imported",
                AuditEvent.outcome == "failure",
                AuditEvent.reason == "organization_access_denied",
            )
        ).all()
    )
    assert len(denied_events) == 3


def test_credentials_have_no_download_endpoint(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    organization = create_organization(client, auth_headers)
    connector = create_google_workspace_config(client, auth_headers, organization["id"])

    response = client.get(
        f"/api/v1/connector-configs/{connector['id']}/credentials",
        headers=auth_headers,
    )

    assert response.status_code == 405
