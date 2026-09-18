import pytest

from app.services.development_credentials import (
    DevelopmentCredentials,
    load_development_credentials,
)


def test_load_development_credentials_returns_explicit_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DEVELOPMENT_ADMIN_EMAIL", "configured-admin@example.local")
    monkeypatch.setenv("DEVELOPMENT_ADMIN_PASSWORD", "test-only-password")

    assert load_development_credentials() == DevelopmentCredentials(
        email="configured-admin@example.local",
        password="test-only-password",
    )


def test_development_credentials_repr_does_not_expose_password() -> None:
    credentials = DevelopmentCredentials(
        email="configured-admin@example.local",
        password="test-only-password",
    )

    assert "test-only-password" not in repr(credentials)


def test_load_development_credentials_rejects_partial_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DEVELOPMENT_ADMIN_EMAIL", "configured-admin@example.local")
    monkeypatch.delenv("DEVELOPMENT_ADMIN_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="must both be set"):
        load_development_credentials()


def test_load_development_credentials_rejects_example_password_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DEVELOPMENT_ADMIN_EMAIL", "configured-admin@example.local")
    monkeypatch.setenv(
        "DEVELOPMENT_ADMIN_PASSWORD",
        "replace-with-a-unique-local-admin-password",
    )

    with pytest.raises(RuntimeError, match="example placeholder"):
        load_development_credentials()


def test_load_development_credentials_is_required_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("DEVELOPMENT_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("DEVELOPMENT_ADMIN_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="before running development migrations"):
        load_development_credentials()


def test_load_development_credentials_is_optional_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DEVELOPMENT_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("DEVELOPMENT_ADMIN_PASSWORD", raising=False)

    assert load_development_credentials() is None
