from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "DREAD Risk Assessment API"
    environment: str = "development"
    database_url: str = (
        "postgresql+psycopg://dread:dread_dev_password_change_me@localhost:5432/dread"
    )
    backend_cors_origins: str = "http://localhost:5173"
    google_workspace_connector_enabled: bool = False
    auth_secret_key: str = "dev-only-auth-secret-change-me"
    auth_token_expires_minutes: int = 480

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
