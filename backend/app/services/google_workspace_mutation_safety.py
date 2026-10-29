from __future__ import annotations

import hashlib
import json
import secrets
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
)
from app.services.audit import sanitize_audit_metadata

CONFIRMATION_LIFETIME = timedelta(minutes=5)
AMBIGUOUS_MUTATION_CODES = frozenset(
    {
        GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT,
        GoogleWorkspaceErrorCode.GOOGLE_NETWORK_ERROR,
        GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE,
    }
)
BLOCKING_CONFIRMATION_STATUSES = frozenset(
    {"executing", "succeeded", "unknown", "reconciled"}
)
RECONCILIATION_MAX_WAIT_SECONDS = 20.0
RECONCILIATION_REQUEST_TIMEOUT_SECONDS = 5.0
RECONCILIATION_BACKOFF_SECONDS = (0.0, 0.5, 1.0, 2.0)

ConfirmationStatus = Literal[
    "pending",
    "executing",
    "succeeded",
    "failed",
    "unknown",
    "reconciled",
    "rejected",
    "expired",
]


@dataclass(frozen=True)
class ConfirmationGrant:
    """A short-lived secret returned once while only its digest is persisted."""

    token: str
    token_digest: str
    expires_at: datetime


@dataclass(frozen=True)
class ReconciliationAttempt:
    """One bounded read-only observation opportunity."""

    number: int
    request_timeout_seconds: float


def confirmation_token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_confirmation(*, now: datetime | None = None) -> ConfirmationGrant:
    issued_at = aware_utc(now or datetime.now(UTC))
    token = secrets.token_urlsafe(32)
    return ConfirmationGrant(
        token=token,
        token_digest=confirmation_token_digest(token),
        expires_at=issued_at + CONFIRMATION_LIFETIME,
    )


def aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def confirmation_is_expired(
    expires_at: datetime,
    *,
    now: datetime | None = None,
) -> bool:
    return aware_utc(expires_at) <= aware_utc(now or datetime.now(UTC))


def confirmation_blocks_new_preview(
    status: str,
    expires_at: datetime,
    *,
    now: datetime | None = None,
) -> bool:
    return status in BLOCKING_CONFIRMATION_STATUSES and not confirmation_is_expired(
        expires_at, now=now
    )


def consume_confirmation(
    db: Session,
    model: type[Any],
    *,
    confirmation_id: UUID,
    token_digest: str,
    consumed_at: datetime | None = None,
) -> bool:
    """Atomically consume a pending, unexpired confirmation before an external write."""

    consumed_timestamp = aware_utc(consumed_at or datetime.now(UTC))
    consumed_id = db.execute(
        update(model)
        .where(
            model.id == confirmation_id,
            model.status == "pending",
            model.token_digest == token_digest,
            model.expires_at > consumed_timestamp,
        )
        .values(
            status="executing",
            consumed_at=consumed_timestamp,
        )
        .returning(model.id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    db.commit()
    return consumed_id is not None


def set_confirmation_status(
    db: Session,
    model: type[Any],
    confirmation_id: UUID,
    status: ConfirmationStatus,
) -> None:
    db.execute(update(model).where(model.id == confirmation_id).values(status=status))
    db.commit()


def mark_confirmation_reconciled(
    db: Session,
    model: type[Any],
    confirmation_id: UUID,
) -> bool:
    """Atomically finalize only an unknown confirmation after read-only observation."""

    updated_id = db.execute(
        update(model)
        .where(model.id == confirmation_id, model.status == "unknown")
        .values(status="reconciled")
        .returning(model.id)
    ).scalar_one_or_none()
    db.commit()
    return updated_id is not None


def is_ambiguous_mutation_error(error: GoogleWorkspaceError) -> bool:
    return error.code in AMBIGUOUS_MUTATION_CODES


class BoundedReconciliationWindow:
    """Generate bounded, explicitly read-only reconciliation attempts."""

    def __init__(
        self,
        *,
        poll_delays: Sequence[float] = RECONCILIATION_BACKOFF_SECONDS,
        max_wait_seconds: float = RECONCILIATION_MAX_WAIT_SECONDS,
        request_timeout_seconds: float = RECONCILIATION_REQUEST_TIMEOUT_SECONDS,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not poll_delays or poll_delays[0] != 0:
            raise ValueError("reconciliation polling must start without a delay")
        if max_wait_seconds <= 0 or request_timeout_seconds <= 0:
            raise ValueError("reconciliation timeouts must be positive")
        if any(delay < 0 for delay in poll_delays):
            raise ValueError("reconciliation delays cannot be negative")
        self.poll_delays = tuple(poll_delays)
        self.max_wait_seconds = max_wait_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.sleeper = sleeper
        self.monotonic = monotonic

    def attempts(self) -> Iterator[ReconciliationAttempt]:
        started_at = self.monotonic()
        for number, delay in enumerate(self.poll_delays, start=1):
            remaining = self.max_wait_seconds - (self.monotonic() - started_at)
            if remaining <= 0:
                break
            if delay:
                if delay >= remaining:
                    break
                self.sleeper(delay)
                remaining = self.max_wait_seconds - (self.monotonic() - started_at)
                if remaining <= 0:
                    break
            yield ReconciliationAttempt(
                number=number,
                request_timeout_seconds=min(self.request_timeout_seconds, remaining),
            )


def mutation_audit_metadata(
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Validate hard-coded mutation audit metadata before persistence.

    General audit logging still sanitizes defensively. Mutation paths additionally fail
    their tests when a developer introduces a secret-bearing key or a non-JSON value.
    """

    if metadata is None:
        return None
    original = dict(metadata)
    sanitized = sanitize_audit_metadata(original)
    if sanitized != original:
        raise ValueError("mutation audit metadata contains a sensitive key")
    try:
        json.dumps(sanitized, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("mutation audit metadata must be JSON-safe") from error
    return sanitized
