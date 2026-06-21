from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.roles import (
    CUSTOMER_ADMIN,
    CUSTOMER_USER,
    CUSTOMER_VIEWER,
    PLATFORM_ADMIN,
    PLATFORM_SUPPORT,
    is_platform_admin_role,
)
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


def is_platform_support(user: User) -> bool:
    return user.role == PLATFORM_SUPPORT


def is_platform_user(user: User) -> bool:
    return user.role in {PLATFORM_ADMIN, PLATFORM_SUPPORT}


def require_platform_admin(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if not is_platform_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin role required.",
        )
    return current_user


def get_active_customer_memberships(user: User) -> list[CustomerMembership]:
    return [membership for membership in user.customer_memberships if membership.is_active]


def get_active_customer_ids_for_user(user: User) -> set[UUID]:
    return {membership.customer_id for membership in get_active_customer_memberships(user)}


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


def get_active_customer_membership_for_user(
    user: User,
    customer_id: UUID,
) -> CustomerMembership | None:
    for membership in get_active_customer_memberships(user):
        if membership.customer_id == customer_id:
            return membership
    return None


def user_can_access_customer(user: User, customer_id: UUID | None) -> bool:
    return user_can_read_customer(user, customer_id)


def user_can_read_customer(user: User, customer_id: UUID | None) -> bool:
    if is_platform_user(user):
        return True
    if customer_id is None:
        return False
    return get_active_customer_membership_for_user(user, customer_id) is not None


def user_can_write_customer(user: User, customer_id: UUID | None) -> bool:
    if is_platform_admin(user):
        return True
    if is_platform_support(user) or customer_id is None:
        return False

    membership = get_active_customer_membership_for_user(user, customer_id)
    return membership is not None and membership.role in {CUSTOMER_ADMIN, CUSTOMER_USER}


def user_can_admin_customer(user: User, customer_id: UUID | None) -> bool:
    if is_platform_admin(user):
        return True
    if is_platform_support(user) or customer_id is None:
        return False

    membership = get_active_customer_membership_for_user(user, customer_id)
    return membership is not None and membership.role == CUSTOMER_ADMIN


def user_can_operate_customer_connector(user: User, customer_id: UUID | None) -> bool:
    if is_platform_admin(user) or is_platform_support(user):
        return True
    if customer_id is None:
        return False

    membership = get_active_customer_membership_for_user(user, customer_id)
    return membership is not None and membership.role in {CUSTOMER_ADMIN, CUSTOMER_USER}


def require_customer_access(user: User, customer_id: UUID | None) -> None:
    require_customer_read_access(user, customer_id)


def require_customer_read_access(user: User, customer_id: UUID | None) -> None:
    if not user_can_read_customer(user, customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer access required.",
        )


def require_customer_write_access(user: User, customer_id: UUID | None) -> None:
    if not user_can_write_customer(user, customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer write access required.",
        )


def require_customer_admin_access(user: User, customer_id: UUID | None) -> None:
    if not user_can_admin_customer(user, customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer admin access required.",
        )


def require_customer_connector_operation_access(user: User, customer_id: UUID | None) -> None:
    if not user_can_operate_customer_connector(user, customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer connector operation access required.",
        )


def is_customer_viewer_membership(user: User, customer_id: UUID | None) -> bool:
    if customer_id is None or is_platform_user(user):
        return False
    membership = get_active_customer_membership_for_user(user, customer_id)
    return membership is not None and membership.role == CUSTOMER_VIEWER
