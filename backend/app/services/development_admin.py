import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.services.passwords import hash_password, verify_password

LEGACY_DEVELOPMENT_ADMIN_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
LEGACY_DEVELOPMENT_ADMIN_EMAIL = "admin@example.local"
DISABLED_PASSWORD_HASH = "disabled-legacy-development-credential"


def configure_development_admin(db: Session, email: str, password: str) -> User:
    configured_user = db.scalar(select(User).where(User.email == email))
    legacy_user = db.get(User, LEGACY_DEVELOPMENT_ADMIN_ID)
    if legacy_user is None:
        legacy_user = db.scalar(
            select(User).where(User.email == LEGACY_DEVELOPMENT_ADMIN_EMAIL)
        )

    if configured_user is not None:
        configured_user.full_name = "Development Admin"
        if not verify_password(password, configured_user.hashed_password):
            configured_user.hashed_password = hash_password(password)
        configured_user.role = "platform_admin"
        configured_user.is_active = True

        if legacy_user is not None and legacy_user.id != configured_user.id:
            legacy_user.hashed_password = DISABLED_PASSWORD_HASH
            legacy_user.is_active = False

        db.commit()
        db.refresh(configured_user)
        return configured_user

    if legacy_user is not None:
        legacy_user.email = email
        legacy_user.full_name = "Development Admin"
        if not verify_password(password, legacy_user.hashed_password):
            legacy_user.hashed_password = hash_password(password)
        legacy_user.role = "platform_admin"
        legacy_user.is_active = True
        db.commit()
        db.refresh(legacy_user)
        return legacy_user

    user = User(
        id=LEGACY_DEVELOPMENT_ADMIN_ID,
        email=email,
        full_name="Development Admin",
        hashed_password=hash_password(password),
        role="platform_admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
