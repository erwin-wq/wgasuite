from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AdminDeck API"
    environment: str = "development"
    database_url: str | None = None
    postgres_db: str | None = None
    postgres_user: str | None = None
    postgres_password: SecretStr | None = Field(default=None, min_length=1)
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    backend_cors_origins: str = "http://localhost:5173"
    google_workspace_connector_enabled: bool = False
    auth_secret_key: SecretStr = Field(min_length=32)
    auth_token_expires_minutes: int = 480

    @model_validator(mode="after")
    def validate_database_configuration(self) -> "Settings":
        if self.auth_secret_key.get_secret_value().startswith("replace-with-"):
            raise ValueError("AUTH_SECRET_KEY still contains an example placeholder.")

        if self.database_url:
            return self

        required_values = {
            "POSTGRES_DB": self.postgres_db,
            "POSTGRES_USER": self.postgres_user,
            "POSTGRES_PASSWORD": self.postgres_password,
        }
        missing = [name for name, value in required_values.items() if not value]
        if missing:
            raise ValueError(
                "Set DATABASE_URL or all required PostgreSQL variables: " + ", ".join(missing)
            )
        password_is_placeholder = (
            self.postgres_password is not None
            and self.postgres_password.get_secret_value().startswith("replace-with-")
        )
        if password_is_placeholder:
            raise ValueError("POSTGRES_PASSWORD still contains an example placeholder.")
        return self

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url:
            return self.database_url

        if self.postgres_db is None or self.postgres_user is None or self.postgres_password is None:
            raise RuntimeError("PostgreSQL configuration was not validated.")

        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
