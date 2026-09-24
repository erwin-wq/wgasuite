import json
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from googleapiclient.errors import HttpError
from httplib2 import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.google_workspace import (
    CredentialProviderRegistry,
    DelegatedCredentialFactory,
    FileCredentialProvider,
    GoogleWorkspaceClientFactory,
    GoogleWorkspaceError,
    map_google_api_error,
)
from app.models import (
    ConnectorConfig,
    Customer,
    CustomerMembership,
    Organization,
    User,
)
from app.services.passwords import hash_password


def fake_service_account_info() -> dict[str, str]:
    return {
        "type": "service_account",
        "project_id": "test-only-project",
        "private_key_id": "test-only-key-id",
        "private_key": "test-only-not-a-real-private-key",
        "client_email": "test-only-service-account@example.invalid",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def write_credential_file(root: Path, organization_id: UUID, content: object) -> Path:
    organization_directory = root / str(organization_id)
    organization_directory.mkdir(parents=True)
    credential_path = organization_directory / "workspace.json"
    credential_path.write_text(json.dumps(content), encoding="utf-8")
    return credential_path


def connector_config(
    organization_id: UUID,
    *,
    admin_subject_email: str | None = "admin@example.com",
) -> ConnectorConfig:
    return ConnectorConfig(
        organization_id=organization_id,
        connector_type="google_workspace",
        auth_method="service_account_domain_wide_delegation",
        status="configured",
        display_name="Test Google Workspace",
        primary_domain="example.com",
        admin_subject_email=admin_subject_email,
        credential_provider="file",
        credential_ref="workspace",
    )


def assert_error_code(error: pytest.ExceptionInfo[GoogleWorkspaceError], code: str) -> None:
    assert error.value.code == code
    assert "private_key" not in str(error.value)
    assert "test-only" not in str(error.value)


def test_file_credential_provider_resolves_tenant_scoped_reference(tmp_path: Path) -> None:
    organization_id = uuid4()
    expected = fake_service_account_info()
    write_credential_file(tmp_path, organization_id, expected)

    provider = FileCredentialProvider(tmp_path)

    assert provider.load_service_account_info(
        organization_id=organization_id,
        credential_ref="workspace",
    ) == expected


def test_file_credential_provider_returns_safe_typed_missing_error(tmp_path: Path) -> None:
    provider = FileCredentialProvider(tmp_path)

    with pytest.raises(GoogleWorkspaceError) as error:
        provider.load_service_account_info(
            organization_id=uuid4(),
            credential_ref="missing-secret",
        )

    assert_error_code(error, "credentials_not_found")
    assert "missing-secret" not in str(error.value)


@pytest.mark.parametrize("content", ["not-json", "[]", '{"type": "authorized_user"}'])
def test_file_credential_provider_returns_safe_typed_malformed_error(
    tmp_path: Path,
    content: str,
) -> None:
    organization_id = uuid4()
    organization_directory = tmp_path / str(organization_id)
    organization_directory.mkdir()
    (organization_directory / "workspace.json").write_text(content, encoding="utf-8")

    with pytest.raises(GoogleWorkspaceError) as error:
        FileCredentialProvider(tmp_path).load_service_account_info(
            organization_id=organization_id,
            credential_ref="workspace",
        )

    assert_error_code(error, "invalid_credentials")


def test_file_credential_provider_rejects_arbitrary_paths(tmp_path: Path) -> None:
    with pytest.raises(GoogleWorkspaceError) as error:
        FileCredentialProvider(tmp_path).load_service_account_info(
            organization_id=uuid4(),
            credential_ref="../another-tenant/secret",
        )

    assert_error_code(error, "invalid_credentials")


def test_file_credential_provider_rejects_symlinked_credential(tmp_path: Path) -> None:
    organization_id = uuid4()
    other_organization_id = uuid4()
    source = write_credential_file(tmp_path, other_organization_id, fake_service_account_info())
    organization_directory = tmp_path / str(organization_id)
    organization_directory.mkdir()
    (organization_directory / "workspace.json").symlink_to(source)

    with pytest.raises(GoogleWorkspaceError) as error:
        FileCredentialProvider(tmp_path).load_service_account_info(
            organization_id=organization_id,
            credential_ref="workspace",
        )

    assert_error_code(error, "invalid_credentials")


class FakeBaseCredentials:
    def __init__(self) -> None:
        self.subject: str | None = None

    def with_subject(self, subject: str) -> "FakeBaseCredentials":
        self.subject = subject
        return self


def test_delegated_credentials_apply_normalized_scopes_and_subject(tmp_path: Path) -> None:
    organization_id = uuid4()
    credential_info = fake_service_account_info()
    write_credential_file(tmp_path, organization_id, credential_info)
    config = connector_config(organization_id)
    base_credentials = FakeBaseCredentials()
    factory = DelegatedCredentialFactory(
        CredentialProviderRegistry([FileCredentialProvider(tmp_path)])
    )

    with patch(
        "app.connectors.google_workspace_credentials."
        "service_account.Credentials.from_service_account_info",
        return_value=base_credentials,
    ) as from_service_account_info:
        delegated, scopes = factory.create(
            config,
            [" scope:one ", "scope:two", "scope:one"],
        )

    assert delegated is base_credentials
    assert base_credentials.subject == "admin@example.com"
    assert scopes == ("scope:one", "scope:two")
    from_service_account_info.assert_called_once_with(
        credential_info,
        scopes=("scope:one", "scope:two"),
    )


@pytest.mark.parametrize("admin_subject", [None, "", "not-an-email", "admin@localhost"])
def test_delegated_credentials_reject_invalid_admin_subject(
    tmp_path: Path,
    admin_subject: str | None,
) -> None:
    config = connector_config(uuid4(), admin_subject_email=admin_subject)
    factory = DelegatedCredentialFactory(
        CredentialProviderRegistry([FileCredentialProvider(tmp_path)])
    )

    with pytest.raises(GoogleWorkspaceError) as error:
        factory.create(config, ["scope:one"])

    assert_error_code(error, "invalid_admin_subject")


def test_delegated_credentials_require_explicit_scopes(tmp_path: Path) -> None:
    factory = DelegatedCredentialFactory(
        CredentialProviderRegistry([FileCredentialProvider(tmp_path)])
    )

    with pytest.raises(GoogleWorkspaceError) as error:
        factory.create(connector_config(uuid4()), [" ", ""])

    assert_error_code(error, "missing_scope_or_permission")


@pytest.mark.parametrize(
    ("status_code", "content", "expected_code", "retryable"),
    [
        (401, b"{}", "google_unauthorized", False),
        (
            403,
            b'{"error":{"errors":[{"reason":"insufficientPermissions"}]}}',
            "missing_scope_or_permission",
            False,
        ),
        (403, b"{}", "google_forbidden", False),
        (429, b"{}", "google_rate_limited", True),
        (503, b"{}", "google_service_unavailable", True),
        (400, b"{}", "google_api_error", False),
    ],
)
def test_google_api_errors_are_mapped_without_upstream_content(
    status_code: int,
    content: bytes,
    expected_code: str,
    retryable: bool,
) -> None:
    mapped = map_google_api_error(HttpError(Response({"status": str(status_code)}), content))

    assert mapped.code == expected_code
    assert mapped.retryable is retryable
    assert "insufficientPermissions" not in str(mapped)


class InMemoryCredentialProvider:
    name = "file"

    def __init__(self) -> None:
        self.organization_ids: list[UUID] = []

    def load_service_account_info(
        self,
        *,
        organization_id: UUID,
        credential_ref: str,
    ) -> dict[str, str]:
        self.organization_ids.append(organization_id)
        assert credential_ref == "shared-name"
        return fake_service_account_info()


def create_tenant_data(db: Session) -> tuple[Organization, Organization, User]:
    customer_a = Customer(name="Customer A", slug=f"customer-a-{uuid4().hex}")
    customer_b = Customer(name="Customer B", slug=f"customer-b-{uuid4().hex}")
    db.add_all([customer_a, customer_b])
    db.flush()
    organization_a = Organization(name=f"Organization A {uuid4()}", customer_id=customer_a.id)
    organization_b = Organization(name=f"Organization B {uuid4()}", customer_id=customer_b.id)
    db.add_all([organization_a, organization_b])
    db.flush()
    db.add_all(
        [
            connector_config(organization_a.id),
            connector_config(organization_b.id),
        ]
    )
    for config in db.new:
        if isinstance(config, ConnectorConfig):
            config.credential_ref = "shared-name"
    actor = User(
        email=f"tenant-a-{uuid4().hex}@example.local",
        full_name="Tenant A Operator",
        hashed_password=hash_password("ChangeMe123!"),
        role="customer_user",
        is_active=True,
    )
    db.add(actor)
    db.flush()
    db.add(
        CustomerMembership(
            user_id=actor.id,
            customer_id=customer_a.id,
            role="customer_admin",
            is_active=True,
        )
    )
    db.commit()
    db.refresh(organization_a)
    db.refresh(organization_b)
    db.refresh(actor)
    return organization_a, organization_b, actor


def test_client_factory_enforces_tenant_access_before_credential_resolution(
    db_session: Session,
) -> None:
    _, organization_b, actor = create_tenant_data(db_session)
    provider = InMemoryCredentialProvider()
    factory = GoogleWorkspaceClientFactory(
        db_session,
        CredentialProviderRegistry([provider]),
        client_builder=lambda *args, **kwargs: object(),
    )

    with pytest.raises(GoogleWorkspaceError) as error:
        factory.for_organization(
            actor=actor,
            organization_id=organization_b.id,
            service="admin",
            version="directory_v1",
            scopes=["scope:directory.readonly"],
        )

    assert_error_code(error, "organization_access_denied")
    assert provider.organization_ids == []


def test_client_factory_uses_requested_service_version_scopes_and_fresh_clients(
    db_session: Session,
) -> None:
    organization_a, organization_b, _ = create_tenant_data(db_session)
    platform_admin = db_session.scalar(select(User).where(User.email == "admin@example.local"))
    assert platform_admin is not None
    provider = InMemoryCredentialProvider()
    builder_calls: list[tuple[tuple, dict]] = []

    def client_builder(*args, **kwargs):
        builder_calls.append((args, kwargs))
        return object()

    factory = GoogleWorkspaceClientFactory(
        db_session,
        CredentialProviderRegistry([provider]),
        client_builder=client_builder,
    )

    with patch(
        "app.connectors.google_workspace_credentials."
        "service_account.Credentials.from_service_account_info",
        side_effect=[FakeBaseCredentials(), FakeBaseCredentials()],
    ) as credential_constructor:
        client_a = factory.for_organization(
            actor=platform_admin,
            organization_id=organization_a.id,
            service="admin",
            version="directory_v1",
            scopes=["scope:users.readonly", "scope:users.readonly"],
        )
        client_b = factory.for_organization(
            actor=platform_admin,
            organization_id=organization_b.id,
            service="gmail",
            version="v1",
            scopes=["scope:gmail.delegates"],
        )

    assert client_a is not client_b
    assert provider.organization_ids == [organization_a.id, organization_b.id]
    assert [call[0] for call in builder_calls] == [("admin", "directory_v1"), ("gmail", "v1")]
    assert all(call[1]["cache_discovery"] is False for call in builder_calls)
    assert builder_calls[0][1]["credentials"].subject == "admin@example.com"
    assert credential_constructor.call_args_list[0].kwargs["scopes"] == (
        "scope:users.readonly",
    )
    assert credential_constructor.call_args_list[1].kwargs["scopes"] == (
        "scope:gmail.delegates",
    )
