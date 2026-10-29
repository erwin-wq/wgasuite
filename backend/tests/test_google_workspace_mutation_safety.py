from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
)
from app.models import GoogleWorkspaceDelegateConfirmation
from app.services.google_workspace_mutation_safety import (
    BoundedReconciliationWindow,
    aware_utc,
    confirmation_blocks_new_preview,
    confirmation_is_expired,
    confirmation_token_digest,
    consume_confirmation,
    is_ambiguous_mutation_error,
    issue_confirmation,
    mark_confirmation_reconciled,
    mutation_audit_metadata,
    set_confirmation_status,
)
from tests.test_google_workspace_connection import create_connector


def test_confirmation_grant_is_short_lived_and_only_digest_is_reusable() -> None:
    issued_at = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)

    grant = issue_confirmation(now=issued_at)

    assert len(grant.token) >= 32
    assert grant.token not in grant.token_digest
    assert grant.token_digest == confirmation_token_digest(grant.token)
    assert grant.expires_at == issued_at + timedelta(minutes=5)
    assert confirmation_is_expired(grant.expires_at, now=grant.expires_at)
    assert not confirmation_is_expired(
        grant.expires_at, now=grant.expires_at - timedelta(microseconds=1)
    )


def test_confirmation_preview_blocking_is_status_and_expiry_bound() -> None:
    now = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
    future = now + timedelta(minutes=1)
    past = now - timedelta(seconds=1)

    assert confirmation_blocks_new_preview("executing", future, now=now)
    assert confirmation_blocks_new_preview("unknown", future, now=now)
    assert not confirmation_blocks_new_preview("pending", future, now=now)
    assert not confirmation_blocks_new_preview("succeeded", past, now=now)
    assert aware_utc(future.replace(tzinfo=None)).tzinfo == UTC


def test_atomic_confirmation_consumption_allows_exactly_one_caller(
    db_session: Session,
) -> None:
    connector, actor = create_connector(db_session)
    grant = issue_confirmation()
    confirmation = GoogleWorkspaceDelegateConfirmation(
        organization_id=connector.organization_id,
        actor_user_id=actor.id,
        operation="create",
        owner_google_id="owner-1",
        owner_primary_email="owner@example.test",
        delegate_google_id="delegate-1",
        delegate_primary_email="delegate@example.test",
        token_digest=grant.token_digest,
        expires_at=grant.expires_at,
    )
    db_session.add(confirmation)
    db_session.commit()

    first = consume_confirmation(
        db_session,
        GoogleWorkspaceDelegateConfirmation,
        confirmation_id=confirmation.id,
        token_digest=grant.token_digest,
    )
    second = consume_confirmation(
        db_session,
        GoogleWorkspaceDelegateConfirmation,
        confirmation_id=confirmation.id,
        token_digest=grant.token_digest,
    )
    db_session.refresh(confirmation)

    assert first is True
    assert second is False
    assert confirmation.status == "executing"
    assert confirmation.consumed_at is not None


def test_atomic_confirmation_consumption_rejects_expiry_race(
    db_session: Session,
) -> None:
    connector, actor = create_connector(db_session)
    now = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
    grant = issue_confirmation(now=now)
    confirmation = GoogleWorkspaceDelegateConfirmation(
        organization_id=connector.organization_id,
        actor_user_id=actor.id,
        operation="create",
        owner_google_id="owner-expired",
        owner_primary_email="owner@example.test",
        delegate_google_id="delegate-expired",
        delegate_primary_email="delegate@example.test",
        token_digest=grant.token_digest,
        expires_at=grant.expires_at,
    )
    db_session.add(confirmation)
    db_session.commit()

    consumed = consume_confirmation(
        db_session,
        GoogleWorkspaceDelegateConfirmation,
        confirmation_id=confirmation.id,
        token_digest=grant.token_digest,
        consumed_at=grant.expires_at,
    )
    db_session.refresh(confirmation)

    assert consumed is False
    assert confirmation.status == "pending"
    assert confirmation.consumed_at is None


def test_reconciliation_transition_only_accepts_unknown_confirmation(
    db_session: Session,
) -> None:
    connector, actor = create_connector(db_session)
    grant = issue_confirmation()
    confirmation = GoogleWorkspaceDelegateConfirmation(
        organization_id=connector.organization_id,
        actor_user_id=actor.id,
        operation="remove",
        owner_google_id="owner-2",
        owner_primary_email="owner@example.test",
        delegate_google_id="delegate-2",
        delegate_primary_email="delegate@example.test",
        token_digest=grant.token_digest,
        expires_at=grant.expires_at,
    )
    db_session.add(confirmation)
    db_session.commit()

    assert not mark_confirmation_reconciled(
        db_session, GoogleWorkspaceDelegateConfirmation, confirmation.id
    )
    set_confirmation_status(
        db_session, GoogleWorkspaceDelegateConfirmation, confirmation.id, "unknown"
    )
    assert mark_confirmation_reconciled(
        db_session, GoogleWorkspaceDelegateConfirmation, confirmation.id
    )
    assert not mark_confirmation_reconciled(
        db_session, GoogleWorkspaceDelegateConfirmation, confirmation.id
    )


def test_bounded_reconciliation_window_has_read_timeout_and_validated_delays() -> None:
    sleeps: list[float] = []
    window = BoundedReconciliationWindow(
        poll_delays=(0.0, 0.25, 0.5),
        max_wait_seconds=2.0,
        request_timeout_seconds=0.75,
        sleeper=sleeps.append,
        monotonic=lambda: 0.0,
    )

    attempts = list(window.attempts())

    assert [attempt.number for attempt in attempts] == [1, 2, 3]
    assert [attempt.request_timeout_seconds for attempt in attempts] == [0.75] * 3
    assert sleeps == [0.25, 0.5]
    with pytest.raises(ValueError):
        BoundedReconciliationWindow(poll_delays=(0.1,))
    with pytest.raises(ValueError):
        BoundedReconciliationWindow(poll_delays=(0.0, -0.1))


@pytest.mark.parametrize(
    ("code", "ambiguous"),
    [
        (GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT, True),
        (GoogleWorkspaceErrorCode.GOOGLE_NETWORK_ERROR, True),
        (GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE, True),
        (GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED, False),
        (GoogleWorkspaceErrorCode.GOOGLE_FORBIDDEN, False),
    ],
)
def test_ambiguous_write_classification_is_shared(
    code: GoogleWorkspaceErrorCode, ambiguous: bool
) -> None:
    assert is_ambiguous_mutation_error(GoogleWorkspaceError(code)) is ambiguous


def test_mutation_audit_metadata_rejects_secrets_and_non_json_values() -> None:
    assert mutation_audit_metadata(
        {"operation": "suspend", "previous_suspended": False}
    ) == {"operation": "suspend", "previous_suspended": False}
    assert mutation_audit_metadata(None) is None

    with pytest.raises(ValueError, match="sensitive"):
        mutation_audit_metadata({"nested": {"confirmation_token": "secret"}})
    with pytest.raises(ValueError, match="JSON-safe"):
        mutation_audit_metadata({"operation": object()})
