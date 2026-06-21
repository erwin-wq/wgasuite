from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.roles import is_platform_admin_role
from app.db.session import get_db
from app.models import CustomerMembership, User
from app.services.tokens import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    unauthorized_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized_error

    settings = get_settings()
    payload = decode_access_token(credentials.credentials, settings.auth_secret_key)
    if payload is None:
        raise unauthorized_error

    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise unauthorized_error

    try:
        user_id = UUID(subject)
    except ValueError as exc:
        raise unauthorized_error from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized_error

    return user


def is_platform_admin(user: User) -> bool:
    return is_platform_admin_role(user.role)


def require_platform_admin(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if not is_platform_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin role required.",
        )
    return current_user


def get_customer_membership_for_user(
    db: Session,
    user: User,
    customer_id: UUID,
) -> CustomerMembership | None:
    """Return a user's active customer membership.

    TODO: Use this helper to enforce customer-scoped access on existing API endpoints in the next
    tenant-scoping feature.
    """
    statement = select(CustomerMembership).where(
        CustomerMembership.user_id == user.id,
        CustomerMembership.customer_id == customer_id,
        CustomerMembership.is_active.is_(True),
    )
    return db.scalar(statement)
