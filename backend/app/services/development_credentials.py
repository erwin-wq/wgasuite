import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DevelopmentCredentials:
    email: str
    password: str = field(repr=False)


def load_development_credentials() -> DevelopmentCredentials | None:
    email = os.getenv("DEVELOPMENT_ADMIN_EMAIL", "").strip()
    password = os.getenv("DEVELOPMENT_ADMIN_PASSWORD", "")
    environment = os.getenv("ENVIRONMENT", "development").strip().lower()

    if bool(email) != bool(password):
        raise RuntimeError(
            "DEVELOPMENT_ADMIN_EMAIL and DEVELOPMENT_ADMIN_PASSWORD must both be set "
            "or both be empty."
        )

    if email and password:
        if password.startswith("replace-with-"):
            raise RuntimeError(
                "DEVELOPMENT_ADMIN_PASSWORD still contains an example placeholder."
            )
        return DevelopmentCredentials(email=email, password=password)

    if environment == "development":
        raise RuntimeError(
            "Set DEVELOPMENT_ADMIN_EMAIL and DEVELOPMENT_ADMIN_PASSWORD before running "
            "development migrations."
        )

    return None
