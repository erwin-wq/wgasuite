from __future__ import annotations

import hashlib
import logging
import secrets
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from googleapiclient.errors import HttpError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import user_can_admin_customer
from app.connectors.google_workspace_client import GoogleWorkspaceClientFactory
from app.connectors.google_workspace_credentials import (
    DIRECTORY_USER_READONLY_SCOPE,
    DIRECTORY_USER_WRITE_SCOPE,
)
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
    map_google_api_error,
)
from app.models import (
    ConnectorConfig,
    GoogleWorkspaceUserStatusConfirmation,
    Organization,
    User,
)
from app.services.google_workspace_user_lookup import (
    GoogleWorkspaceUserLookup,
    GoogleWorkspaceUserLookupResult,
)

logger = logging.getLogger(__name__)
UserStatusOperation = Literal["suspend", "reactivate"]
CONFIRMATION_LIFETIME = timedelta(minutes=5)
AMBIGUOUS_MUTATION_CODES = frozenset(
    {
        GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT,
        GoogleWorkspaceErrorCode.GOOGLE_NETWORK_ERROR,
        GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE,
    }
)
RECONCILIATION_MAX_WAIT_SECONDS = 20.0
RECONCILIATION_REQUEST_TIMEOUT_SECONDS = 5.0
RECONCILIATION_BACKOFF_SECONDS = (0.0, 0.5, 1.0, 2.0)
USER_STATUS_FIELDS = (
    "id,primaryEmail,customerId,suspended,suspensionReason,archived,isAdmin,"
    "isDelegatedAdmin,deletionTime"
)


@dataclass(frozen=True)
class UserStatusChangePreview:
    operation: UserStatusOperation
    organization_id: UUID
    customer_id: UUID
    target_google_id: str
    target_primary_email: str
    previous_suspended: bool
    requested_suspended: bool
    confirmation_token: str
    expires_at: datetime
    effect: str


@dataclass(frozen=True)
class UserStatusMutationResult:
    operation: UserStatusOperation
    target_google_id: str
    target_primary_email: str
    previous_suspended: bool
    suspended: bool
    outcome: Literal["suspended", "reactivated"]
    message: str


@dataclass(frozen=True)
class UserStatusReconciliationResult:
    operation: UserStatusOperation
    target_google_id: str
    target_primary_email: str
    status: Literal["verified", "unknown"]
    observed_suspended: bool
    attempts: int
    correlation_id: str
    message: str


class UserStatusTargetError(GoogleWorkspaceError):
    def __init__(
        self,
        code: GoogleWorkspaceErrorCode,
        target_google_id: str,
        *,
        retryable: bool = False,
    ) -> None:
        self.target_google_id = target_google_id
        super().__init__(code, retryable=retryable)


class AmbiguousGoogleWriteResponseError(GoogleWorkspaceError):
    """The write returned, but its response cannot establish the resulting state."""


class UserStatusMutationAmbiguousError(UserStatusTargetError):
    def __init__(
        self, code: GoogleWorkspaceErrorCode, correlation_id: UUID, target_google_id: str
    ) -> None:
        self.correlation_id = str(correlation_id)
        super().__init__(code, target_google_id)


class UserStatusReconciliationError(UserStatusTargetError):
    def __init__(
        self,
        code: GoogleWorkspaceErrorCode,
        correlation_id: UUID,
        attempts: int,
        target_google_id: str,
        *,
        retryable: bool = False,
    ) -> None:
        self.correlation_id = str(correlation_id)
        self.attempts = attempts
        super().__init__(code, target_google_id, retryable=retryable)


class GoogleWorkspaceUserStatusService:
    """Guarded, customer-scoped suspension and reactivation of Directory users."""

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
    def from_settings(cls, db: Session) -> GoogleWorkspaceUserStatusService:
        factory = GoogleWorkspaceClientFactory.from_settings(db)
        return cls(db, factory, GoogleWorkspaceUserLookup(factory))

    def preview_change(
        self,
        *,
        actor: User,
        organization_id: UUID,
        operation: UserStatusOperation,
        user_email: str,
    ) -> UserStatusChangePreview:
        organization, connector, target = self._resolve_target(
            actor, organization_id, user_email, operation
        )
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + CONFIRMATION_LIFETIME
        statement = select(GoogleWorkspaceUserStatusConfirmation).where(
            GoogleWorkspaceUserStatusConfirmation.organization_id == organization_id,
            GoogleWorkspaceUserStatusConfirmation.operation == operation,
            GoogleWorkspaceUserStatusConfirmation.target_google_id == target.id,
        )
        confirmation = self.db.scalar(statement)
        if confirmation is not None and self._confirmation_blocks_new_preview(confirmation):
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.GOOGLE_USER_CONFIRMATION_USED
            )
        values = {
            "customer_id": organization.customer_id,
            "connector_config_id": connector.id,
            "google_customer_id": target.customer_id,
            "actor_user_id": actor.id,
            "target_primary_email": target.primary_email,
            "expected_suspended": target.suspended,
            "requested_suspended": operation == "suspend",
            "expected_suspension_reason": target.suspension_reason,
            "token_digest": self._token_digest(token),
            "status": "pending",
            "expires_at": expires_at,
            "consumed_at": None,
        }
        if confirmation is None:
            confirmation = GoogleWorkspaceUserStatusConfirmation(
                organization_id=organization_id,
                operation=operation,
                target_google_id=target.id,
                **values,
            )
            self.db.add(confirmation)
        else:
            for key, value in values.items():
                setattr(confirmation, key, value)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            confirmation = self.db.scalar(statement)
            if confirmation is None or self._confirmation_blocks_new_preview(confirmation):
                raise GoogleWorkspaceError(
                    GoogleWorkspaceErrorCode.GOOGLE_USER_CONFIRMATION_USED
                ) from None
            for key, value in values.items():
                setattr(confirmation, key, value)
            self.db.commit()
        return UserStatusChangePreview(
            operation=operation,
            organization_id=organization_id,
            customer_id=organization.customer_id,
            target_google_id=target.id,
            target_primary_email=target.primary_email,
            previous_suspended=target.suspended,
            requested_suspended=operation == "suspend",
            confirmation_token=token,
            expires_at=expires_at,
            effect=(
                "The user will be suspended and lose access to Google Workspace services. "
                "Their data is not deleted, and license charges may continue."
                if operation == "suspend"
                else "The administrator-controlled suspension will be removed and access to "
                "Google Workspace services may be restored."
            ),
        )

    def execute_change(
        self,
        *,
        actor: User,
        organization_id: UUID,
        operation: UserStatusOperation,
        confirmation_token: str,
    ) -> UserStatusMutationResult:
        digest = self._token_digest(confirmation_token)
        confirmation = self.db.scalar(
            select(GoogleWorkspaceUserStatusConfirmation).where(
                GoogleWorkspaceUserStatusConfirmation.token_digest == digest,
                GoogleWorkspaceUserStatusConfirmation.organization_id == organization_id,
                GoogleWorkspaceUserStatusConfirmation.operation == operation,
                GoogleWorkspaceUserStatusConfirmation.actor_user_id == actor.id,
            )
        )
        if confirmation is None:
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.GOOGLE_USER_CONFIRMATION_INVALID
            )
        if confirmation.status != "pending":
            raise UserStatusTargetError(
                GoogleWorkspaceErrorCode.GOOGLE_USER_CONFIRMATION_USED,
                confirmation.target_google_id,
            )
        if self._aware(confirmation.expires_at) <= datetime.now(UTC):
            confirmation.status = "expired"
            self.db.commit()
            raise UserStatusTargetError(
                GoogleWorkspaceErrorCode.GOOGLE_USER_CONFIRMATION_EXPIRED,
                confirmation.target_google_id,
            )
        try:
            organization, connector, target = self._resolve_target(
                actor, organization_id, confirmation.target_primary_email, operation
            )
        except UserStatusTargetError as error:
            confirmation.status = "rejected"
            self.db.commit()
            if error.code in {
                GoogleWorkspaceErrorCode.GOOGLE_USER_ALREADY_SUSPENDED,
                GoogleWorkspaceErrorCode.GOOGLE_USER_ALREADY_ACTIVE,
            }:
                raise UserStatusTargetError(
                    GoogleWorkspaceErrorCode.GOOGLE_USER_STATE_CHANGED,
                    error.target_google_id,
                ) from None
            raise
        if (
            organization.customer_id != confirmation.customer_id
            or connector.id != confirmation.connector_config_id
            or target.customer_id != confirmation.google_customer_id
            or target.id != confirmation.target_google_id
            or target.primary_email.casefold()
            != confirmation.target_primary_email.casefold()
            or target.suspended != confirmation.expected_suspended
            or target.suspension_reason != confirmation.expected_suspension_reason
        ):
            confirmation.status = "rejected"
            self.db.commit()
            raise UserStatusTargetError(
                GoogleWorkspaceErrorCode.GOOGLE_USER_STATE_CHANGED,
                confirmation.target_google_id,
            )
        consumed_id = self.db.execute(
            update(GoogleWorkspaceUserStatusConfirmation)
            .where(
                GoogleWorkspaceUserStatusConfirmation.id == confirmation.id,
                GoogleWorkspaceUserStatusConfirmation.status == "pending",
                GoogleWorkspaceUserStatusConfirmation.token_digest == digest,
            )
            .values(status="executing", consumed_at=datetime.now(UTC))
            .returning(GoogleWorkspaceUserStatusConfirmation.id)
        ).scalar_one_or_none()
        self.db.commit()
        if consumed_id is None:
            raise UserStatusTargetError(
                GoogleWorkspaceErrorCode.GOOGLE_USER_CONFIRMATION_USED,
                confirmation.target_google_id,
            )
        try:
            updated = self._execute_google_change(
                actor, organization_id, target, operation == "suspend"
            )
        except GoogleWorkspaceError as error:
            if error.code in AMBIGUOUS_MUTATION_CODES or isinstance(
                error, AmbiguousGoogleWriteResponseError
            ):
                self._set_confirmation_status(confirmation.id, "unknown")
                raise UserStatusMutationAmbiguousError(
                    error.code, confirmation.id, confirmation.target_google_id
                ) from None
            self._set_confirmation_status(confirmation.id, "failed")
            raise UserStatusTargetError(
                error.code,
                confirmation.target_google_id,
                retryable=error.retryable,
            ) from None
        if (
            updated.id != target.id
            or updated.customer_id != target.customer_id
            or updated.suspended != (operation == "suspend")
        ):
            self._set_confirmation_status(confirmation.id, "unknown")
            raise UserStatusMutationAmbiguousError(
                GoogleWorkspaceErrorCode.GOOGLE_API_ERROR,
                confirmation.id,
                confirmation.target_google_id,
            )
        self._set_confirmation_status(confirmation.id, "succeeded")
        return UserStatusMutationResult(
            operation=operation,
            target_google_id=target.id,
            target_primary_email=updated.primary_email,
            previous_suspended=target.suspended,
            suspended=updated.suspended,
            outcome="suspended" if updated.suspended else "reactivated",
            message=(
                f"{updated.primary_email} was suspended."
                if updated.suspended
                else f"{updated.primary_email} was reactivated."
            ),
        )

    def _resolve_target(
        self,
        actor: User,
        organization_id: UUID,
        user_email: str,
        operation: UserStatusOperation,
    ) -> tuple[Organization, ConnectorConfig, GoogleWorkspaceUserLookupResult]:
        organization = self.db.get(Organization, organization_id)
        if organization is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.ORGANIZATION_NOT_FOUND)
        if organization.customer_id is None or not user_can_admin_customer(
            actor, organization.customer_id
        ):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.ORGANIZATION_ACCESS_DENIED)
        connector = self.db.scalar(
            select(ConnectorConfig).where(
                ConnectorConfig.organization_id == organization_id,
                ConnectorConfig.connector_type == "google_workspace",
            )
        )
        if connector is None or not connector.admin_subject_email:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED)
        admin = self.user_lookup.lookup(
            actor=actor,
            organization_id=organization_id,
            email=connector.admin_subject_email,
        )
        target = (
            admin
            if user_email.casefold() == connector.admin_subject_email.casefold()
            else self.user_lookup.lookup(
                actor=actor, organization_id=organization_id, email=user_email
            )
        )
        if target.customer_id != admin.customer_id:
            raise UserStatusTargetError(
                GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH, target.id
            )
        try:
            self._validate_eligibility(actor, connector, admin, target, operation)
        except GoogleWorkspaceError as error:
            raise UserStatusTargetError(
                error.code, target.id, retryable=error.retryable
            ) from None
        return organization, connector, target

    @staticmethod
    def _validate_eligibility(
        actor: User,
        connector: ConnectorConfig,
        admin: GoogleWorkspaceUserLookupResult,
        target: GoogleWorkspaceUserLookupResult,
        operation: UserStatusOperation,
    ) -> None:
        identities = {
            target.primary_email.casefold(),
            *(value.casefold() for value in target.aliases),
            *(value.casefold() for value in target.non_editable_aliases),
        }
        if target.id == admin.id or (
            connector.admin_subject_email
            and connector.admin_subject_email.casefold() in identities
        ):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_USER_ADMIN_PROTECTED)
        if target.is_super_admin is not False or target.is_delegated_admin is not False:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_USER_ADMIN_PROTECTED)
        if actor.email.casefold() in identities:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_USER_SELF_PROTECTED)
        if (
            connector.service_account_email
            and connector.service_account_email.casefold() in identities
        ):
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.GOOGLE_USER_SERVICE_ACCOUNT_PROTECTED
            )
        if target.deletion_time is not None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_USER_DELETED)
        if target.archived is True:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_USER_ARCHIVED)
        if operation == "suspend":
            if target.suspended:
                raise GoogleWorkspaceError(
                    GoogleWorkspaceErrorCode.GOOGLE_USER_ALREADY_SUSPENDED
                )
            return
        if not target.suspended:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_USER_ALREADY_ACTIVE)
        if not target.suspension_reason or target.suspension_reason.strip().upper() != "ADMIN":
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.GOOGLE_USER_SUSPENSION_REASON_UNSUPPORTED
            )

    def _execute_google_change(
        self,
        actor: User,
        organization_id: UUID,
        target: GoogleWorkspaceUserLookupResult,
        suspended: bool,
    ) -> GoogleWorkspaceUserLookupResult:
        client: Any | None = None
        try:
            client = self.client_factory.for_directory_users(
                actor=actor,
                organization_id=organization_id,
                scopes=(DIRECTORY_USER_WRITE_SCOPE,),
            )
            response = (
                client.users()
                .update(
                    userKey=target.id,
                    body={"suspended": suspended},
                    fields=USER_STATUS_FIELDS,
                )
                .execute(num_retries=0)
            )
            try:
                return GoogleWorkspaceUserLookup._to_result(
                    response, target.primary_email.casefold()
                )
            except GoogleWorkspaceError:
                raise AmbiguousGoogleWriteResponseError(
                    GoogleWorkspaceErrorCode.GOOGLE_API_ERROR
                ) from None
        except GoogleWorkspaceError:
            raise
        except HttpError as error:
            if error.resp.status == 404:
                raise GoogleWorkspaceError(
                    GoogleWorkspaceErrorCode.GOOGLE_USER_NOT_FOUND
                ) from None
            raise map_google_api_error(error) from None
        except Exception as error:
            raise map_google_api_error(error) from None
        finally:
            self._close_client(client, organization_id)

    @staticmethod
    def _token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _confirmation_blocks_new_preview(
        confirmation: GoogleWorkspaceUserStatusConfirmation,
    ) -> bool:
        if confirmation.status not in {"executing", "succeeded", "unknown", "reconciled"}:
            return False
        return GoogleWorkspaceUserStatusService._aware(
            confirmation.expires_at
        ) > datetime.now(UTC)

    def _set_confirmation_status(self, confirmation_id: UUID, status: str) -> None:
        self.db.execute(
            update(GoogleWorkspaceUserStatusConfirmation)
            .where(GoogleWorkspaceUserStatusConfirmation.id == confirmation_id)
            .values(status=status)
        )
        self.db.commit()

    @staticmethod
    def _close_client(client: Any | None, organization_id: UUID) -> None:
        if client is None:
            return
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                logger.warning(
                    "Closing Directory users client failed organization_id=%s",
                    organization_id,
                )


class GoogleWorkspaceUserStatusReconciliationService:
    """Observe an ambiguous user status change without resubmitting the write."""

    def __init__(
        self,
        db: Session,
        status_service: GoogleWorkspaceUserStatusService,
        *,
        poll_delays: Sequence[float] = RECONCILIATION_BACKOFF_SECONDS,
        max_wait_seconds: float = RECONCILIATION_MAX_WAIT_SECONDS,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not poll_delays or poll_delays[0] != 0:
            raise ValueError("reconciliation polling must start without a delay")
        self.db = db
        self.status_service = status_service
        self.poll_delays = tuple(poll_delays)
        self.max_wait_seconds = max_wait_seconds
        self.sleeper = sleeper
        self.monotonic = monotonic

    @classmethod
    def from_settings(cls, db: Session) -> GoogleWorkspaceUserStatusReconciliationService:
        return cls(db, GoogleWorkspaceUserStatusService.from_settings(db))

    def reconcile_change(
        self,
        *,
        actor: User,
        organization_id: UUID,
        operation: UserStatusOperation,
        confirmation_token: str,
    ) -> UserStatusReconciliationResult:
        confirmation = self.db.scalar(
            select(GoogleWorkspaceUserStatusConfirmation).where(
                GoogleWorkspaceUserStatusConfirmation.token_digest
                == self.status_service._token_digest(confirmation_token),
                GoogleWorkspaceUserStatusConfirmation.organization_id == organization_id,
                GoogleWorkspaceUserStatusConfirmation.operation == operation,
                GoogleWorkspaceUserStatusConfirmation.actor_user_id == actor.id,
            )
        )
        if confirmation is None:
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.GOOGLE_USER_RECONCILIATION_NOT_AVAILABLE
            )
        if self.status_service._aware(confirmation.expires_at) <= datetime.now(UTC):
            raise UserStatusReconciliationError(
                GoogleWorkspaceErrorCode.GOOGLE_USER_RECONCILIATION_EXPIRED,
                confirmation.id,
                0,
                confirmation.target_google_id,
            )
        if confirmation.status == "reconciled":
            return self._result(confirmation, "verified", confirmation.requested_suspended, 0)
        if confirmation.status != "unknown":
            raise UserStatusReconciliationError(
                GoogleWorkspaceErrorCode.GOOGLE_USER_RECONCILIATION_NOT_AVAILABLE,
                confirmation.id,
                0,
                confirmation.target_google_id,
            )
        organization = self.db.get(Organization, organization_id)
        if (
            organization is None
            or organization.customer_id != confirmation.customer_id
            or not user_can_admin_customer(actor, confirmation.customer_id)
        ):
            raise UserStatusReconciliationError(
                GoogleWorkspaceErrorCode.ORGANIZATION_ACCESS_DENIED,
                confirmation.id,
                0,
                confirmation.target_google_id,
            )
        connector = self.db.get(ConnectorConfig, confirmation.connector_config_id)
        if connector is None or connector.organization_id != organization_id:
            raise UserStatusReconciliationError(
                GoogleWorkspaceErrorCode.GOOGLE_USER_CONFIRMATION_INVALID,
                confirmation.id,
                0,
                confirmation.target_google_id,
            )
        started = self.monotonic()
        attempts = 0
        observed = confirmation.expected_suspended
        for delay in self.poll_delays:
            remaining = self.max_wait_seconds - (self.monotonic() - started)
            if remaining <= 0:
                break
            if delay:
                if delay >= remaining:
                    break
                self.sleeper(delay)
                remaining = self.max_wait_seconds - (self.monotonic() - started)
                if remaining <= 0:
                    break
            attempts += 1
            try:
                current = self._read_target(
                    actor,
                    organization_id,
                    confirmation.target_google_id,
                    min(RECONCILIATION_REQUEST_TIMEOUT_SECONDS, remaining),
                )
            except GoogleWorkspaceError as error:
                if error.retryable and attempts < len(self.poll_delays):
                    continue
                raise UserStatusReconciliationError(
                    error.code,
                    confirmation.id,
                    attempts,
                    confirmation.target_google_id,
                    retryable=error.retryable,
                ) from None
            if (
                current.id != confirmation.target_google_id
                or current.customer_id != confirmation.google_customer_id
            ):
                raise UserStatusReconciliationError(
                    GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH,
                    confirmation.id,
                    attempts,
                    confirmation.target_google_id,
                )
            observed = current.suspended
            if observed == confirmation.requested_suspended:
                updated = self.db.execute(
                    update(GoogleWorkspaceUserStatusConfirmation)
                    .where(
                        GoogleWorkspaceUserStatusConfirmation.id == confirmation.id,
                        GoogleWorkspaceUserStatusConfirmation.status == "unknown",
                    )
                    .values(status="reconciled")
                    .returning(GoogleWorkspaceUserStatusConfirmation.id)
                ).scalar_one_or_none()
                self.db.commit()
                if updated is None:
                    self.db.refresh(confirmation)
                    if confirmation.status != "reconciled":
                        raise UserStatusReconciliationError(
                            GoogleWorkspaceErrorCode.GOOGLE_USER_RECONCILIATION_NOT_AVAILABLE,
                            confirmation.id,
                            attempts,
                            confirmation.target_google_id,
                        )
                return self._result(confirmation, "verified", observed, attempts)
        return self._result(confirmation, "unknown", observed, attempts)

    def _read_target(
        self,
        actor: User,
        organization_id: UUID,
        google_user_id: str,
        timeout: float,
    ) -> GoogleWorkspaceUserLookupResult:
        client: Any | None = None
        try:
            client = self.status_service.client_factory.for_directory_users(
                actor=actor,
                organization_id=organization_id,
                scopes=(DIRECTORY_USER_READONLY_SCOPE,),
                request_timeout_seconds=timeout,
            )
            response = (
                client.users()
                .get(
                    userKey=google_user_id,
                    projection="basic",
                    viewType="admin_view",
                    fields=USER_STATUS_FIELDS,
                )
                .execute(num_retries=0)
            )
            if not isinstance(response, dict) or not isinstance(
                response.get("primaryEmail"), str
            ):
                raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
            return GoogleWorkspaceUserLookup._to_result(
                response, response["primaryEmail"].casefold()
            )
        except GoogleWorkspaceError:
            raise
        except Exception as error:
            raise map_google_api_error(error) from None
        finally:
            self.status_service._close_client(client, organization_id)

    @staticmethod
    def _result(
        confirmation: GoogleWorkspaceUserStatusConfirmation,
        status: Literal["verified", "unknown"],
        observed: bool,
        attempts: int,
    ) -> UserStatusReconciliationResult:
        return UserStatusReconciliationResult(
            operation=confirmation.operation,  # type: ignore[arg-type]
            target_google_id=confirmation.target_google_id,
            target_primary_email=confirmation.target_primary_email,
            status=status,
            observed_suspended=observed,
            attempts=attempts,
            correlation_id=str(confirmation.id),
            message=(
                "Google now reports the requested account status."
                if status == "verified"
                else "The result is still unknown. Check the account status again before retrying."
            ),
        )
