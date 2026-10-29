from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from googleapiclient.errors import HttpError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors.google_workspace_client import (
    GoogleWorkspaceClientFactory,
    VerifiedMailboxOwner,
)
from app.connectors.google_workspace_credentials import (
    GMAIL_DELEGATE_READ_SCOPE,
    GMAIL_DELEGATE_WRITE_SCOPE,
)
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
    map_google_api_error,
)
from app.models import (
    ConnectorConfig,
    GoogleWorkspaceDelegateConfirmation,
    User,
)
from app.services.google_workspace_mutation_safety import (
    RECONCILIATION_BACKOFF_SECONDS,
    RECONCILIATION_MAX_WAIT_SECONDS,
    BoundedReconciliationWindow,
    confirmation_blocks_new_preview,
    confirmation_is_expired,
    confirmation_token_digest,
    consume_confirmation,
    is_ambiguous_mutation_error,
    issue_confirmation,
    mark_confirmation_reconciled,
    set_confirmation_status,
)
from app.services.google_workspace_user_lookup import (
    GoogleWorkspaceUserLookup,
    GoogleWorkspaceUserLookupResult,
)

logger = logging.getLogger(__name__)
DelegateOperation = Literal["create", "remove"]


@dataclass(frozen=True)
class GmailDelegate:
    primary_email: str
    verification_status: Literal["accepted", "pending", "rejected", "unknown"]


@dataclass(frozen=True)
class GmailDelegateListResult:
    owner_primary_email: str
    delegates: list[GmailDelegate]


@dataclass(frozen=True)
class GmailDelegateChangePreview:
    operation: DelegateOperation
    owner_primary_email: str
    delegate_primary_email: str
    confirmation_token: str
    expires_at: datetime
    effect: str


@dataclass(frozen=True)
class GmailDelegateMutationResult:
    operation: DelegateOperation
    owner_primary_email: str
    delegate_primary_email: str
    outcome: Literal["created", "removed"]
    message: str


@dataclass(frozen=True)
class GmailDelegateReconciliationResult:
    operation: DelegateOperation
    owner_primary_email: str
    delegate_primary_email: str
    status: Literal["verified", "unknown"]
    observed_state: Literal[
        "accepted", "absent", "not_observed", "pending", "rejected", "unknown", "present"
    ]
    attempts: int
    correlation_id: str
    message: str


class GmailDelegateMutationAmbiguousError(GoogleWorkspaceError):
    """A consumed mutation whose response did not prove the resulting Google state."""

    def __init__(self, code: GoogleWorkspaceErrorCode, correlation_id: UUID) -> None:
        self.correlation_id = str(correlation_id)
        super().__init__(code)


class GmailDelegateReconciliationError(GoogleWorkspaceError):
    """A secret-safe reconciliation failure with auditable attempt context."""

    def __init__(
        self,
        code: GoogleWorkspaceErrorCode,
        correlation_id: UUID,
        attempts: int,
        *,
        retryable: bool = False,
    ) -> None:
        self.correlation_id = str(correlation_id)
        self.attempts = attempts
        super().__init__(code, retryable=retryable)


class GoogleWorkspaceGmailDelegationService:
    """Manage Gmail delegates without exposing generic Gmail or DWD-subject access."""

    def __init__(
        self,
        db: Session,
        client_factory: GoogleWorkspaceClientFactory,
        user_lookup: GoogleWorkspaceUserLookup,
    ) -> None:
        self.db = db
        self.client_factory = client_factory
        self.user_lookup = user_lookup

    @classmethod
    def from_settings(cls, db: Session) -> GoogleWorkspaceGmailDelegationService:
        client_factory = GoogleWorkspaceClientFactory.from_settings(db)
        return cls(db, client_factory, GoogleWorkspaceUserLookup(client_factory))

    def list_delegates(
        self,
        *,
        actor: User,
        organization_id: UUID,
        owner_email: str,
    ) -> GmailDelegateListResult:
        owner = self._resolve_owner(
            actor=actor,
            organization_id=organization_id,
            owner_email=owner_email,
        )
        return self._list_for_owner(actor, organization_id, owner)

    def preview_change(
        self,
        *,
        actor: User,
        organization_id: UUID,
        operation: DelegateOperation,
        owner_email: str,
        delegate_email: str,
    ) -> GmailDelegateChangePreview:
        owner, delegate = self._resolve_change_identities(
            actor=actor,
            organization_id=organization_id,
            owner_email=owner_email,
            delegate_email=delegate_email,
            operation=operation,
        )
        delegates = self._list_for_owner(actor, organization_id, owner).delegates
        existing = self._find_delegate(delegates, delegate.primary_email)
        if operation == "create" and existing is not None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_DELEGATE_ALREADY_EXISTS)
        if operation == "remove" and existing is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_DELEGATE_NOT_FOUND)

        grant = issue_confirmation()
        statement = select(GoogleWorkspaceDelegateConfirmation).where(
            GoogleWorkspaceDelegateConfirmation.organization_id == organization_id,
            GoogleWorkspaceDelegateConfirmation.operation == operation,
            GoogleWorkspaceDelegateConfirmation.owner_google_id == owner.id,
            GoogleWorkspaceDelegateConfirmation.delegate_google_id == delegate.id,
        )
        confirmation = self.db.scalar(statement)
        if confirmation is not None and self._confirmation_blocks_new_preview(confirmation):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_CONFIRMATION_USED)
        if confirmation is None:
            confirmation = GoogleWorkspaceDelegateConfirmation(
                organization_id=organization_id,
                actor_user_id=actor.id,
                operation=operation,
                owner_google_id=owner.id,
                owner_primary_email=owner.primary_email,
                delegate_google_id=delegate.id,
                delegate_primary_email=delegate.primary_email,
                token_digest=grant.token_digest,
                expires_at=grant.expires_at,
            )
            self.db.add(confirmation)
        else:
            confirmation.actor_user_id = actor.id
            confirmation.owner_primary_email = owner.primary_email
            confirmation.delegate_primary_email = delegate.primary_email
            confirmation.token_digest = grant.token_digest
            confirmation.status = "pending"
            confirmation.expires_at = grant.expires_at
            confirmation.consumed_at = None
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            confirmation = self.db.scalar(statement)
            if confirmation is None:
                raise GoogleWorkspaceError(
                    GoogleWorkspaceErrorCode.GMAIL_CONFIRMATION_INVALID
                ) from None
            if self._confirmation_blocks_new_preview(confirmation):
                raise GoogleWorkspaceError(
                    GoogleWorkspaceErrorCode.GMAIL_CONFIRMATION_USED
                ) from None
            confirmation.actor_user_id = actor.id
            confirmation.owner_primary_email = owner.primary_email
            confirmation.delegate_primary_email = delegate.primary_email
            confirmation.token_digest = grant.token_digest
            confirmation.status = "pending"
            confirmation.expires_at = grant.expires_at
            confirmation.consumed_at = None
            self.db.commit()

        effect = (
            "The delegate will be able to read, send, and delete messages in the mailbox. "
            "Google may take approximately one minute to make access usable."
            if operation == "create"
            else "The delegate's access to read, send, and delete mailbox messages will be revoked."
        )
        return GmailDelegateChangePreview(
            operation=operation,
            owner_primary_email=owner.primary_email,
            delegate_primary_email=delegate.primary_email,
            confirmation_token=grant.token,
            expires_at=grant.expires_at,
            effect=effect,
        )

    def execute_change(
        self,
        *,
        actor: User,
        organization_id: UUID,
        operation: DelegateOperation,
        confirmation_token: str,
    ) -> GmailDelegateMutationResult:
        token_digest = confirmation_token_digest(confirmation_token)
        confirmation = self.db.scalar(
            select(GoogleWorkspaceDelegateConfirmation).where(
                GoogleWorkspaceDelegateConfirmation.token_digest == token_digest,
                GoogleWorkspaceDelegateConfirmation.organization_id == organization_id,
                GoogleWorkspaceDelegateConfirmation.operation == operation,
                GoogleWorkspaceDelegateConfirmation.actor_user_id == actor.id,
            )
        )
        if confirmation is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_CONFIRMATION_INVALID)
        if confirmation.status != "pending":
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_CONFIRMATION_USED)

        now = datetime.now(UTC)
        if confirmation_is_expired(confirmation.expires_at, now=now):
            confirmation.status = "expired"
            self.db.commit()
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_CONFIRMATION_EXPIRED)

        owner, delegate = self._resolve_change_identities(
            actor=actor,
            organization_id=organization_id,
            owner_email=confirmation.owner_primary_email,
            delegate_email=confirmation.delegate_primary_email,
            operation=operation,
        )
        if (
            owner.id != confirmation.owner_google_id
            or delegate.id != confirmation.delegate_google_id
            or owner.primary_email.casefold() != confirmation.owner_primary_email.casefold()
            or delegate.primary_email.casefold() != confirmation.delegate_primary_email.casefold()
        ):
            confirmation.status = "rejected"
            self.db.commit()
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_CONFIRMATION_INVALID)

        current = self._list_for_owner(actor, organization_id, owner).delegates
        existing = self._find_delegate(current, delegate.primary_email)
        if operation == "create" and existing is not None:
            confirmation.status = "rejected"
            self.db.commit()
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_DELEGATE_ALREADY_EXISTS)
        if operation == "remove" and existing is None:
            confirmation.status = "rejected"
            self.db.commit()
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_DELEGATE_NOT_FOUND)

        if not consume_confirmation(
            self.db,
            GoogleWorkspaceDelegateConfirmation,
            confirmation_id=confirmation.id,
            token_digest=token_digest,
            consumed_at=now,
        ):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_CONFIRMATION_USED)

        try:
            self._execute_google_change(
                actor=actor,
                organization_id=organization_id,
                operation=operation,
                owner=owner,
                delegate_email=delegate.primary_email,
            )
        except GoogleWorkspaceError as error:
            if is_ambiguous_mutation_error(error):
                self._set_confirmation_status(confirmation.id, "unknown")
                raise GmailDelegateMutationAmbiguousError(error.code, confirmation.id) from None
            self._set_confirmation_status(confirmation.id, "failed")
            raise
        except Exception as error:
            mapped = self._map_gmail_error(error, operation=operation)
            if is_ambiguous_mutation_error(mapped):
                self._set_confirmation_status(confirmation.id, "unknown")
                raise GmailDelegateMutationAmbiguousError(mapped.code, confirmation.id) from None
            self._set_confirmation_status(confirmation.id, "failed")
            raise mapped from None

        self._set_confirmation_status(confirmation.id, "succeeded")
        outcome: Literal["created", "removed"] = (
            "created" if operation == "create" else "removed"
        )
        message = (
            "Mailbox delegate added. Google may take approximately one minute to make "
            "access usable."
            if operation == "create"
            else "Mailbox delegate removed. Google may take a short time to propagate the change."
        )
        return GmailDelegateMutationResult(
            operation=operation,
            owner_primary_email=owner.primary_email,
            delegate_primary_email=delegate.primary_email,
            outcome=outcome,
            message=message,
        )

    def _resolve_owner(
        self,
        *,
        actor: User,
        organization_id: UUID,
        owner_email: str,
    ) -> GoogleWorkspaceUserLookupResult:
        connector = self.db.scalar(
            select(ConnectorConfig).where(
                ConnectorConfig.organization_id == organization_id,
                ConnectorConfig.connector_type == "google_workspace",
            )
        )
        if connector is None or not connector.admin_subject_email:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED)

        identities: dict[str, GoogleWorkspaceUserLookupResult] = {}
        for email in (connector.admin_subject_email, owner_email):
            key = email.strip().casefold()
            if key not in identities:
                identities[key] = self.user_lookup.lookup(
                    actor=actor,
                    organization_id=organization_id,
                    email=email,
                )
        tenant_admin = identities[connector.admin_subject_email.strip().casefold()]
        owner = identities[owner_email.strip().casefold()]
        if tenant_admin.customer_id != owner.customer_id:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH)
        self._validate_mailbox_owner(owner)
        return owner

    def _resolve_change_identities(
        self,
        *,
        actor: User,
        organization_id: UUID,
        owner_email: str,
        delegate_email: str,
        operation: DelegateOperation,
    ) -> tuple[GoogleWorkspaceUserLookupResult, GoogleWorkspaceUserLookupResult]:
        owner = self._resolve_owner(
            actor=actor,
            organization_id=organization_id,
            owner_email=owner_email,
        )
        delegate = self.user_lookup.lookup(
            actor=actor,
            organization_id=organization_id,
            email=delegate_email,
        )
        if owner.customer_id != delegate.customer_id:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH)
        if owner.id == delegate.id:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_SELF_DELEGATION)
        if operation == "create" and (
            delegate.suspended
            or delegate.archived is True
            or delegate.is_mailbox_setup is not True
        ):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_USER_INELIGIBLE)
        return owner, delegate

    @staticmethod
    def _validate_mailbox_owner(owner: GoogleWorkspaceUserLookupResult) -> None:
        if owner.suspended or owner.archived is True:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_USER_INELIGIBLE)
        if owner.is_mailbox_setup is not True:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_MAILBOX_NOT_CONFIGURED)

    def _list_for_owner(
        self,
        actor: User,
        organization_id: UUID,
        owner: GoogleWorkspaceUserLookupResult,
        *,
        request_timeout_seconds: float | None = None,
    ) -> GmailDelegateListResult:
        client: Any | None = None
        try:
            client_options: dict[str, Any] = {
                "actor": actor,
                "organization_id": organization_id,
                "owner": self._verified_owner(owner),
                "scopes": [GMAIL_DELEGATE_READ_SCOPE],
            }
            if request_timeout_seconds is not None:
                client_options["request_timeout_seconds"] = request_timeout_seconds
            client = self.client_factory.for_gmail_delegates(
                **client_options,
            )
            response = (
                client.users()
                .settings()
                .delegates()
                .list(userId="me")
                .execute(num_retries=0)
            )
            return GmailDelegateListResult(
                owner_primary_email=owner.primary_email,
                delegates=self._parse_delegates(response),
            )
        except GoogleWorkspaceError:
            raise
        except Exception as error:
            raise self._map_gmail_error(error, operation="list") from None
        finally:
            self._close_client(client, organization_id)

    def _execute_google_change(
        self,
        *,
        actor: User,
        organization_id: UUID,
        operation: DelegateOperation,
        owner: GoogleWorkspaceUserLookupResult,
        delegate_email: str,
    ) -> None:
        client: Any | None = None
        try:
            client = self.client_factory.for_gmail_delegates(
                actor=actor,
                organization_id=organization_id,
                owner=self._verified_owner(owner),
                scopes=[GMAIL_DELEGATE_WRITE_SCOPE],
            )
            delegates = client.users().settings().delegates()
            request = (
                delegates.create(
                    userId="me",
                    body={"delegateEmail": delegate_email},
                )
                if operation == "create"
                else delegates.delete(userId="me", delegateEmail=delegate_email)
            )
            request.execute(num_retries=0)
        except GoogleWorkspaceError:
            raise
        except Exception as error:
            raise self._map_gmail_error(error, operation=operation) from None
        finally:
            self._close_client(client, organization_id)

    @staticmethod
    def _parse_delegates(response: Any) -> list[GmailDelegate]:
        if not isinstance(response, dict):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        raw_delegates = response.get("delegates", [])
        if raw_delegates is None:
            raw_delegates = []
        if not isinstance(raw_delegates, list):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)

        delegates: list[GmailDelegate] = []
        for item in raw_delegates:
            if not isinstance(item, dict) or not isinstance(item.get("delegateEmail"), str):
                raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
            verification = item.get("verificationStatus")
            if verification not in {"accepted", "pending", "rejected"}:
                verification = "unknown"
            delegates.append(
                GmailDelegate(
                    primary_email=item["delegateEmail"],
                    verification_status=verification,
                )
            )
        return delegates

    @staticmethod
    def _find_delegate(
        delegates: list[GmailDelegate], delegate_email: str
    ) -> GmailDelegate | None:
        expected = delegate_email.casefold()
        return next(
            (delegate for delegate in delegates if delegate.primary_email.casefold() == expected),
            None,
        )

    @staticmethod
    def _verified_owner(owner: GoogleWorkspaceUserLookupResult) -> VerifiedMailboxOwner:
        return VerifiedMailboxOwner(
            google_user_id=owner.id,
            primary_email=owner.primary_email,
            customer_id=owner.customer_id,
        )

    def _set_confirmation_status(self, confirmation_id: UUID, status: str) -> None:
        set_confirmation_status(
            self.db,
            GoogleWorkspaceDelegateConfirmation,
            confirmation_id,
            status,  # type: ignore[arg-type]
        )

    @staticmethod
    def _confirmation_blocks_new_preview(
        confirmation: GoogleWorkspaceDelegateConfirmation,
    ) -> bool:
        return confirmation_blocks_new_preview(
            confirmation.status, confirmation.expires_at
        )

    @staticmethod
    def _map_gmail_error(
        error: Exception,
        *,
        operation: Literal["list", "create", "remove"],
    ) -> GoogleWorkspaceError:
        mapped = map_google_api_error(error)
        if mapped.code == GoogleWorkspaceErrorCode.GOOGLE_API_UNAVAILABLE:
            return GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_API_UNAVAILABLE)
        if mapped.code in {
            GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION,
            GoogleWorkspaceErrorCode.GOOGLE_FORBIDDEN,
            GoogleWorkspaceErrorCode.DELEGATION_REJECTED,
        }:
            return GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_SCOPE_MISSING)
        if mapped.code == GoogleWorkspaceErrorCode.GOOGLE_SUBJECT_NOT_FOUND:
            code = (
                GoogleWorkspaceErrorCode.GMAIL_DELEGATE_NOT_FOUND
                if operation == "remove"
                else GoogleWorkspaceErrorCode.GMAIL_MAILBOX_NOT_CONFIGURED
            )
            return GoogleWorkspaceError(code)
        if isinstance(error, HttpError) and error.resp.status == 409 and operation == "create":
            return GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_DELEGATE_ALREADY_EXISTS)
        return mapped

    @staticmethod
    def _close_client(client: Any | None, organization_id: UUID) -> None:
        if client is None:
            return
        close = getattr(client, "close", None)
        if not callable(close):
            return
        try:
            close()
        except Exception:
            logger.warning(
                "Closing Gmail delegate client failed organization_id=%s",
                organization_id,
            )


class GoogleWorkspaceGmailDelegationReconciliationService:
    """Observe an ambiguous delegate mutation using only bounded Gmail list calls."""

    def __init__(
        self,
        db: Session,
        delegation_service: GoogleWorkspaceGmailDelegationService,
        *,
        poll_delays: Sequence[float] = RECONCILIATION_BACKOFF_SECONDS,
        max_wait_seconds: float = RECONCILIATION_MAX_WAIT_SECONDS,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not poll_delays or poll_delays[0] != 0:
            raise ValueError("reconciliation polling must start without a delay")
        self.db = db
        self.delegation_service = delegation_service
        self.poll_delays = tuple(poll_delays)
        self.max_wait_seconds = max_wait_seconds
        self.sleeper = sleeper
        self.monotonic = monotonic

    @classmethod
    def from_settings(cls, db: Session) -> GoogleWorkspaceGmailDelegationReconciliationService:
        return cls(db, GoogleWorkspaceGmailDelegationService.from_settings(db))

    def reconcile_change(
        self,
        *,
        actor: User,
        organization_id: UUID,
        operation: DelegateOperation,
        confirmation_token: str,
    ) -> GmailDelegateReconciliationResult:
        confirmation = self.db.scalar(
            select(GoogleWorkspaceDelegateConfirmation).where(
                GoogleWorkspaceDelegateConfirmation.token_digest
                == confirmation_token_digest(confirmation_token),
                GoogleWorkspaceDelegateConfirmation.organization_id == organization_id,
                GoogleWorkspaceDelegateConfirmation.operation == operation,
                GoogleWorkspaceDelegateConfirmation.actor_user_id == actor.id,
            )
        )
        if confirmation is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_RECONCILIATION_NOT_AVAILABLE)
        if confirmation_is_expired(confirmation.expires_at):
            raise GmailDelegateReconciliationError(
                GoogleWorkspaceErrorCode.GMAIL_RECONCILIATION_EXPIRED,
                confirmation.id,
                0,
            )
        if confirmation.status == "reconciled":
            return self._result(confirmation, status="verified", attempts=0)
        if confirmation.status != "unknown":
            raise GmailDelegateReconciliationError(
                GoogleWorkspaceErrorCode.GMAIL_RECONCILIATION_NOT_AVAILABLE,
                confirmation.id,
                0,
            )

        owner, delegate = self.delegation_service._resolve_change_identities(
            actor=actor,
            organization_id=organization_id,
            owner_email=confirmation.owner_primary_email,
            delegate_email=confirmation.delegate_primary_email,
            operation=operation,
        )
        if (
            owner.id != confirmation.owner_google_id
            or delegate.id != confirmation.delegate_google_id
            or owner.primary_email.casefold() != confirmation.owner_primary_email.casefold()
            or delegate.primary_email.casefold() != confirmation.delegate_primary_email.casefold()
        ):
            raise GmailDelegateReconciliationError(
                GoogleWorkspaceErrorCode.GMAIL_CONFIRMATION_INVALID,
                confirmation.id,
                0,
            )

        attempts = 0
        observed_state: Literal[
            "accepted", "absent", "not_observed", "pending", "rejected", "unknown", "present"
        ] = "not_observed" if operation == "create" else "present"
        window = BoundedReconciliationWindow(
            poll_delays=self.poll_delays,
            max_wait_seconds=self.max_wait_seconds,
            sleeper=self.sleeper,
            monotonic=self.monotonic,
        )
        for attempt in window.attempts():
            attempts = attempt.number
            try:
                current = self.delegation_service._list_for_owner(
                    actor,
                    organization_id,
                    owner,
                    request_timeout_seconds=attempt.request_timeout_seconds,
                ).delegates
            except GoogleWorkspaceError as error:
                has_next_attempt = attempts < len(self.poll_delays)
                if error.retryable and has_next_attempt:
                    continue
                raise GmailDelegateReconciliationError(
                    error.code,
                    confirmation.id,
                    attempts,
                    retryable=error.retryable,
                ) from None

            existing = self.delegation_service._find_delegate(
                current, confirmation.delegate_primary_email
            )
            if operation == "create":
                observed_state = (
                    "not_observed" if existing is None else existing.verification_status
                )
                verified = existing is not None and existing.verification_status == "accepted"
            else:
                observed_state = "absent" if existing is None else "present"
                verified = existing is None
            if verified:
                if not mark_confirmation_reconciled(
                    self.db,
                    GoogleWorkspaceDelegateConfirmation,
                    confirmation.id,
                ):
                    self.db.refresh(confirmation)
                    if confirmation.status != "reconciled":
                        raise GmailDelegateReconciliationError(
                            GoogleWorkspaceErrorCode.GMAIL_RECONCILIATION_NOT_AVAILABLE,
                            confirmation.id,
                            attempts,
                        )
                return self._result(
                    confirmation,
                    status="verified",
                    attempts=attempts,
                    observed_state=observed_state,
                )

        return self._result(
            confirmation,
            status="unknown",
            attempts=attempts,
            observed_state=observed_state,
        )

    @staticmethod
    def _result(
        confirmation: GoogleWorkspaceDelegateConfirmation,
        *,
        status: Literal["verified", "unknown"],
        attempts: int,
        observed_state: Literal[
            "accepted", "absent", "not_observed", "pending", "rejected", "unknown", "present"
        ]
        | None = None,
    ) -> GmailDelegateReconciliationResult:
        if observed_state is None:
            observed_state = "accepted" if confirmation.operation == "create" else "absent"
        message = (
            "The requested delegate state is now visible in Google. This verifies the current "
            "state but does not prove which request caused it."
            if status == "verified"
            else "Google still does not show the requested final state. The mutation outcome "
            "remains unknown; the original change was not resubmitted."
        )
        return GmailDelegateReconciliationResult(
            operation=confirmation.operation,  # type: ignore[arg-type]
            owner_primary_email=confirmation.owner_primary_email,
            delegate_primary_email=confirmation.delegate_primary_email,
            status=status,
            observed_state=observed_state,
            attempts=attempts,
            correlation_id=str(confirmation.id),
            message=message,
        )
