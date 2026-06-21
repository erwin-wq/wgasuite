from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditEvent, User

SENSITIVE_METADATA_KEY_FRAGMENTS = {
    "api_key",
    "client_secret",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "service_account_json",
    "token",
}


def is_sensitive_metadata_key(key: str) -> bool:
    key_lower = key.lower()
    return any(fragment in key_lower for fragment in SENSITIVE_METADATA_KEY_FRAGMENTS)


def sanitize_audit_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        clean_metadata: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if is_sensitive_metadata_key(key_text):
                continue
            clean_metadata[key_text] = sanitize_audit_metadata(item)
        return clean_metadata

    if isinstance(value, list):
        return [sanitize_audit_metadata(item) for item in value]

    if isinstance(value, tuple):
        return [sanitize_audit_metadata(item) for item in value]

    return value


def record_audit_event(
    db: Session,
    actor: User | None,
    action: str,
    object_type: str,
    object_id: str | UUID | None = None,
    customer_id: UUID | None = None,
    outcome: str = "success",
    reason: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> AuditEvent | None:
    try:
        event = AuditEvent(
            actor_user_id=actor.id if actor else None,
            actor_email=actor.email if actor else None,
            actor_role=actor.role if actor else None,
            customer_id=customer_id,
            action=action,
            object_type=object_type,
            object_id=str(object_id) if object_id is not None else None,
            outcome=outcome,
            reason=reason,
            metadata_json=sanitize_audit_metadata(metadata) if metadata else None,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event
    except Exception:
        db.rollback()
        return None
