from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import User
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
