from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.services.development_admin import (
    DISABLED_PASSWORD_HASH,
    configure_development_admin,
)
from app.services.passwords import hash_password, verify_password


def test_configure_development_admin_rotates_existing_user(db_session: Session) -> None:
    user = configure_development_admin(
        db_session,
        "admin@example.local",
        "new-test-only-password",
    )

    assert user.role == "platform_admin"
    assert user.is_active is True
    assert verify_password("new-test-only-password", user.hashed_password)


def test_configure_development_admin_is_idempotent(db_session: Session) -> None:
    first_user = configure_development_admin(
        db_session,
        "admin@example.local",
        "idempotent-test-only-password",
    )
    first_password_hash = first_user.hashed_password

    second_user = configure_development_admin(
        db_session,
        "admin@example.local",
        "idempotent-test-only-password",
    )

    assert second_user.id == first_user.id
    assert second_user.hashed_password == first_password_hash


def test_configure_development_admin_can_replace_legacy_login(db_session: Session) -> None:
    legacy_user = db_session.scalar(select(User).where(User.email == "admin@example.local"))
    assert legacy_user is not None
    db_session.add(
        User(
            email="configured-admin@example.local",
            full_name="Existing Development Admin",
            hashed_password=hash_password("old-test-only-password"),
            role="customer_user",
            is_active=False,
        )
    )
    db_session.commit()

    configured_user = configure_development_admin(
        db_session,
        "configured-admin@example.local",
        "another-test-only-password",
    )

    db_session.refresh(legacy_user)
    assert configured_user.email == "configured-admin@example.local"
    assert verify_password("another-test-only-password", configured_user.hashed_password)
    assert legacy_user.is_active is False
    assert legacy_user.hashed_password == DISABLED_PASSWORD_HASH
