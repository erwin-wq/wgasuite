from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import make_url

from app.core.config import Settings


def test_settings_build_database_url_from_postgres_values() -> None:
    password = "test-only-p@ssword:/% value"
    settings = Settings(
        _env_file=None,
        database_url=None,
        postgres_db="dread_test",
        postgres_user="dread_user",
        postgres_password=password,
        auth_secret_key="test-only-auth-key-with-32-characters",
    )

    database_url = make_url(settings.sqlalchemy_database_url)

    assert database_url.drivername == "postgresql+psycopg"
    assert database_url.username == "dread_user"
    assert database_url.password == password
    assert database_url.host == "postgres"
    assert database_url.port == 5432
    assert database_url.database == "dread_test"
    assert password not in repr(settings)


def test_settings_accept_explicit_database_url_override() -> None:
    settings = Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        auth_secret_key="test-only-auth-key-with-32-characters",
    )

    assert settings.sqlalchemy_database_url == "sqlite+pysqlite:///:memory:"
    assert settings.google_workspace_credentials_directory == Path(
        "/run/secrets/wgasuite/google"
    )


def test_settings_fail_closed_without_database_configuration() -> None:
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        Settings(
            _env_file=None,
            database_url=None,
            postgres_db="dread_test",
            postgres_user="dread_user",
            postgres_password=None,
            auth_secret_key="test-only-auth-key-with-32-characters",
        )


def test_settings_reject_empty_auth_secret() -> None:
    with pytest.raises(ValidationError, match="auth_secret_key"):
        Settings(
            _env_file=None,
            database_url="sqlite+pysqlite:///:memory:",
            auth_secret_key="",
        )


@pytest.mark.parametrize(
    ("postgres_password", "auth_secret_key", "expected_error"),
    [
        (
            "replace-with-a-database-password",
            "test-only-auth-key-with-32-characters",
            "POSTGRES_PASSWORD",
        ),
        (
            "test-only-database-password",
            "replace-with-a-long-random-signing-key",
            "AUTH_SECRET_KEY",
        ),
    ],
)
def test_settings_reject_example_secret_placeholders(
    postgres_password: str,
    auth_secret_key: str,
    expected_error: str,
) -> None:
    with pytest.raises(ValidationError, match=expected_error):
        Settings(
            _env_file=None,
            database_url=None,
            postgres_db="dread_test",
            postgres_user="dread_user",
            postgres_password=postgres_password,
            auth_secret_key=auth_secret_key,
        )
