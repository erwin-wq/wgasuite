from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from googleapiclient.errors import HttpError
from sqlalchemy import select
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
    GoogleWorkspaceUserOrgUnitConfirmation,
    Organization,
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
from app.services.google_workspace_orgunits import (
    GoogleWorkspaceOrganizationalUnits,
    OrganizationalUnit,
)
from app.services.google_workspace_user_lookup import (
    GoogleWorkspaceUserLookup,
    GoogleWorkspaceUserLookupResult,
)

logger = logging.getLogger(__name__)
USER_ORGUNIT_FIELDS = (
    "id,primaryEmail,customerId,aliases,nonEditableAliases,suspended,archived,"
    "orgUnitPath,isAdmin,isDelegatedAdmin,deletionTime"
)


@dataclass(frozen=True)
class UserOrgUnitMovePreview:
    organization_id: UUID
    customer_id: UUID
    target_google_id: str
    target_primary_email: str
    source_org_unit_path: str
    destination_org_unit_id: str
    destination_org_unit_path: str
    confirmation_token: str
    expires_at: datetime
    effect: str


@dataclass(frozen=True)
class UserOrgUnitMoveResult:
    target_google_id: str
    target_primary_email: str
    previous_org_unit_path: str
    org_unit_path: str
    outcome: Literal["moved"]
    message: str


@dataclass(frozen=True)
class UserOrgUnitMoveReconciliationResult:
    target_google_id: str
    target_primary_email: str
    status: Literal["verified", "unknown"]
    observed_org_unit_path: str
    attempts: int
    correlation_id: str
    message: str


class UserOrgUnitTargetError(GoogleWorkspaceError):
    def __init__(
        self, code: GoogleWorkspaceErrorCode, target_google_id: str, *, retryable: bool = False
    ) -> None:
        self.target_google_id = target_google_id
        super().__init__(code, retryable=retryable)


class UserOrgUnitMutationAmbiguousError(UserOrgUnitTargetError):
    def __init__(
        self, code: GoogleWorkspaceErrorCode, correlation_id: UUID, target_google_id: str
    ) -> None:
        self.correlation_id = str(correlation_id)
        super().__init__(code, target_google_id)


class UserOrgUnitReconciliationError(UserOrgUnitTargetError):
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


class GoogleWorkspaceUserOrgUnitService:
    """Move one verified nonprivileged user to one verified existing OU."""

    def __init__(
        self,
        db: Session,
        client_factory: GoogleWorkspaceClientFactory,
        user_lookup: GoogleWorkspaceUserLookup,
        orgunits: GoogleWorkspaceOrganizationalUnits,
    ) -> None:
        self.db = db
        self.client_factory = client_factory
        self.user_lookup = user_lookup
        self.orgunits = orgunits

    @classmethod
    def from_settings(cls, db: Session) -> GoogleWorkspaceUserOrgUnitService:
        factory = GoogleWorkspaceClientFactory.from_settings(db)
        lookup = GoogleWorkspaceUserLookup(factory)
        return cls(db, factory, lookup, GoogleWorkspaceOrganizationalUnits(db, factory, lookup))

    def preview_move(
        self,
        *,
        actor: User,
        organization_id: UUID,
        user_id: str,
        destination_org_unit_id: str,
    ) -> UserOrgUnitMovePreview:
        organization, connector, target, destination = self._resolve(
            actor, organization_id, user_id, destination_org_unit_id
        )
        source_path = self._required_path(target)
        if source_path == destination.path:
            raise UserOrgUnitTargetError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_UNCHANGED, target.id
            )
        grant = issue_confirmation()
        statement = select(GoogleWorkspaceUserOrgUnitConfirmation).where(
            GoogleWorkspaceUserOrgUnitConfirmation.organization_id == organization_id,
            GoogleWorkspaceUserOrgUnitConfirmation.target_google_id == target.id,
        )
        confirmation = self.db.scalar(statement)
        if confirmation is not None and confirmation_blocks_new_preview(
            confirmation.status, confirmation.expires_at
        ):
            raise UserOrgUnitTargetError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CONFIRMATION_USED, target.id
            )
        values = {
            "customer_id": organization.customer_id,
            "connector_config_id": connector.id,
            "actor_user_id": actor.id,
            "google_customer_id": target.customer_id,
            "target_primary_email": target.primary_email,
            "expected_source_path": source_path,
            "destination_org_unit_id": destination.id,
            "destination_path": destination.path,
            "token_digest": grant.token_digest,
            "status": "pending",
            "expires_at": grant.expires_at,
            "consumed_at": None,
        }
        if confirmation is None:
            confirmation = GoogleWorkspaceUserOrgUnitConfirmation(
                organization_id=organization_id, target_google_id=target.id, **values
            )
            self.db.add(confirmation)
        else:
            for key, value in values.items():
                setattr(confirmation, key, value)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise UserOrgUnitTargetError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CONFIRMATION_USED, target.id
            ) from None
        return UserOrgUnitMovePreview(
            organization_id=organization_id,
            customer_id=organization.customer_id,
            target_google_id=target.id,
            target_primary_email=target.primary_email,
            source_org_unit_path=source_path,
            destination_org_unit_id=destination.id,
            destination_org_unit_path=destination.path,
            confirmation_token=grant.token,
            expires_at=grant.expires_at,
            effect=(
                "The user will move to the selected Organizational Unit. Applicable Google "
                "Workspace services and policies may change; WGASuite cannot calculate the "
                "exact impact."
            ),
        )

    def execute_move(
        self,
        *,
        actor: User,
        organization_id: UUID,
        confirmation_token: str,
    ) -> UserOrgUnitMoveResult:
        digest = confirmation_token_digest(confirmation_token)
        confirmation = self.db.scalar(
            select(GoogleWorkspaceUserOrgUnitConfirmation).where(
                GoogleWorkspaceUserOrgUnitConfirmation.token_digest == digest,
                GoogleWorkspaceUserOrgUnitConfirmation.organization_id == organization_id,
                GoogleWorkspaceUserOrgUnitConfirmation.actor_user_id == actor.id,
            )
        )
        if confirmation is None:
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CONFIRMATION_INVALID
            )
        if confirmation.status != "pending":
            raise UserOrgUnitTargetError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CONFIRMATION_USED,
                confirmation.target_google_id,
            )
        if confirmation_is_expired(confirmation.expires_at):
            set_confirmation_status(
                self.db, GoogleWorkspaceUserOrgUnitConfirmation, confirmation.id, "expired"
            )
            raise UserOrgUnitTargetError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CONFIRMATION_EXPIRED,
                confirmation.target_google_id,
            )
        try:
            organization, connector, target, destination = self._resolve(
                actor,
                organization_id,
                confirmation.target_google_id,
                confirmation.destination_org_unit_id,
            )
        except GoogleWorkspaceError:
            set_confirmation_status(
                self.db, GoogleWorkspaceUserOrgUnitConfirmation, confirmation.id, "rejected"
            )
            raise
        if (
            organization.customer_id != confirmation.customer_id
            or connector.id != confirmation.connector_config_id
            or target.customer_id != confirmation.google_customer_id
            or target.id != confirmation.target_google_id
            or target.primary_email.casefold() != confirmation.target_primary_email.casefold()
            or self._required_path(target) != confirmation.expected_source_path
            or destination.id != confirmation.destination_org_unit_id
            or destination.path != confirmation.destination_path
        ):
            set_confirmation_status(
                self.db, GoogleWorkspaceUserOrgUnitConfirmation, confirmation.id, "rejected"
            )
            raise UserOrgUnitTargetError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_STATE_CHANGED,
                confirmation.target_google_id,
            )
        if not consume_confirmation(
            self.db,
            GoogleWorkspaceUserOrgUnitConfirmation,
            confirmation_id=confirmation.id,
            token_digest=digest,
        ):
            raise UserOrgUnitTargetError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CONFIRMATION_USED,
                confirmation.target_google_id,
            )
        try:
            updated = self._write_move(actor, organization_id, target, destination.path)
        except GoogleWorkspaceError as error:
            status = "unknown" if is_ambiguous_mutation_error(error) else "failed"
            set_confirmation_status(
                self.db, GoogleWorkspaceUserOrgUnitConfirmation, confirmation.id, status
            )
            if status == "unknown":
                raise UserOrgUnitMutationAmbiguousError(
                    error.code, confirmation.id, target.id
                ) from None
            raise UserOrgUnitTargetError(error.code, target.id, retryable=error.retryable) from None
        if (
            updated.id != target.id
            or updated.customer_id != target.customer_id
            or self._required_path(updated) != destination.path
        ):
            set_confirmation_status(
                self.db, GoogleWorkspaceUserOrgUnitConfirmation, confirmation.id, "unknown"
            )
            raise UserOrgUnitMutationAmbiguousError(
                GoogleWorkspaceErrorCode.GOOGLE_API_ERROR, confirmation.id, target.id
            )
        set_confirmation_status(
            self.db, GoogleWorkspaceUserOrgUnitConfirmation, confirmation.id, "succeeded"
        )
        return UserOrgUnitMoveResult(
            target_google_id=target.id,
            target_primary_email=updated.primary_email,
            previous_org_unit_path=confirmation.expected_source_path,
            org_unit_path=destination.path,
            outcome="moved",
            message=f"{updated.primary_email} was moved to {destination.path}.",
        )

    def _resolve(
        self, actor: User, organization_id: UUID, user_id: str, destination_id: str
    ) -> tuple[Organization, ConnectorConfig, GoogleWorkspaceUserLookupResult, OrganizationalUnit]:
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
        target = self._read_user(actor, organization_id, user_id)
        if target.customer_id != admin.customer_id:
            raise UserOrgUnitTargetError(
                GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH, target.id
            )
        self._validate_eligibility(actor, connector, admin, target)
        destination = self.orgunits.get_organizational_unit(
            actor=actor, organization_id=organization_id, org_unit_id=destination_id
        )
        return organization, connector, target, destination

    @staticmethod
    def _validate_eligibility(
        actor: User,
        connector: ConnectorConfig,
        admin: GoogleWorkspaceUserLookupResult,
        target: GoogleWorkspaceUserLookupResult,
    ) -> None:
        identities = {
            target.primary_email.casefold(),
            *(value.casefold() for value in target.aliases),
            *(value.casefold() for value in target.non_editable_aliases),
        }
        code: GoogleWorkspaceErrorCode | None = None
        if (
            target.id == admin.id
            or target.is_super_admin is not False
            or target.is_delegated_admin is not False
            or (connector.admin_subject_email or "").casefold() in identities
        ):
            code = GoogleWorkspaceErrorCode.GOOGLE_USER_ADMIN_PROTECTED
        elif actor.email.casefold() in identities:
            code = GoogleWorkspaceErrorCode.GOOGLE_USER_SELF_PROTECTED
        elif (connector.service_account_email or "").casefold() in identities:
            code = GoogleWorkspaceErrorCode.GOOGLE_USER_SERVICE_ACCOUNT_PROTECTED
        elif target.deletion_time is not None:
            code = GoogleWorkspaceErrorCode.GOOGLE_USER_DELETED
        elif target.archived is True:
            code = GoogleWorkspaceErrorCode.GOOGLE_USER_ARCHIVED
        if code is not None:
            raise UserOrgUnitTargetError(code, target.id)

    def _read_user(
        self,
        actor: User,
        organization_id: UUID,
        user_id: str,
        request_timeout_seconds: float | None = None,
    ) -> GoogleWorkspaceUserLookupResult:
        client: Any | None = None
        try:
            client = self.client_factory.for_directory_users(
                actor=actor,
                organization_id=organization_id,
                scopes=(DIRECTORY_USER_READONLY_SCOPE,),
                request_timeout_seconds=request_timeout_seconds,
            )
            response = (
                client.users()
                .get(
                    userKey=user_id,
                    projection="basic",
                    viewType="admin_view",
                    fields=USER_ORGUNIT_FIELDS,
                )
                .execute(num_retries=0)
            )
            email = response.get("primaryEmail") if isinstance(response, dict) else None
            if not isinstance(email, str):
                raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
            result = GoogleWorkspaceUserLookup._to_result(response, email.casefold())
            if result.id != user_id:
                raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_USER_LOOKUP_MISMATCH)
            return result
        except GoogleWorkspaceError:
            raise
        except HttpError as error:
            if error.resp.status == 404:
                raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_USER_NOT_FOUND) from None
            raise map_google_api_error(error) from None
        except Exception as error:
            raise map_google_api_error(error) from None
        finally:
            self._close(client, organization_id)

    def _write_move(
        self,
        actor: User,
        organization_id: UUID,
        target: GoogleWorkspaceUserLookupResult,
        destination_path: str,
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
                    body={"orgUnitPath": destination_path},
                    fields=USER_ORGUNIT_FIELDS,
                )
                .execute(num_retries=0)
            )
            email = response.get("primaryEmail") if isinstance(response, dict) else None
            if not isinstance(email, str):
                raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
            return GoogleWorkspaceUserLookup._to_result(response, email.casefold())
        except GoogleWorkspaceError:
            raise
        except HttpError as error:
            if error.resp.status == 404:
                raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_USER_NOT_FOUND) from None
            raise map_google_api_error(error) from None
        except Exception as error:
            raise map_google_api_error(error) from None
        finally:
            self._close(client, organization_id)

    @staticmethod
    def _required_path(user: GoogleWorkspaceUserLookupResult) -> str:
        if user.org_unit_path is None or not user.org_unit_path.startswith("/"):
            raise UserOrgUnitTargetError(
                GoogleWorkspaceErrorCode.GOOGLE_API_ERROR, user.id
            )
        return user.org_unit_path

    @staticmethod
    def _close(client: Any | None, organization_id: UUID) -> None:
        close = getattr(client, "close", None) if client is not None else None
        if callable(close):
            try:
                close()
            except Exception:
                logger.warning(
                    "Closing Directory users client failed organization_id=%s",
                    organization_id,
                )


class GoogleWorkspaceUserOrgUnitReconciliationService:
    def __init__(
        self,
        db: Session,
        service: GoogleWorkspaceUserOrgUnitService,
        *,
        poll_delays: Sequence[float] = RECONCILIATION_BACKOFF_SECONDS,
        max_wait_seconds: float = RECONCILIATION_MAX_WAIT_SECONDS,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.db = db
        self.service = service
        self.poll_delays = tuple(poll_delays)
        self.max_wait_seconds = max_wait_seconds
        self.sleeper = sleeper
        self.monotonic = monotonic

    @classmethod
    def from_settings(cls, db: Session) -> GoogleWorkspaceUserOrgUnitReconciliationService:
        return cls(db, GoogleWorkspaceUserOrgUnitService.from_settings(db))

    def reconcile_move(
        self, *, actor: User, organization_id: UUID, confirmation_token: str
    ) -> UserOrgUnitMoveReconciliationResult:
        confirmation = self.db.scalar(
            select(GoogleWorkspaceUserOrgUnitConfirmation).where(
                GoogleWorkspaceUserOrgUnitConfirmation.token_digest
                == confirmation_token_digest(confirmation_token),
                GoogleWorkspaceUserOrgUnitConfirmation.organization_id == organization_id,
                GoogleWorkspaceUserOrgUnitConfirmation.actor_user_id == actor.id,
            )
        )
        if confirmation is None:
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_RECONCILIATION_NOT_AVAILABLE
            )
        if confirmation_is_expired(confirmation.expires_at):
            raise UserOrgUnitReconciliationError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_RECONCILIATION_EXPIRED,
                confirmation.id,
                0,
                confirmation.target_google_id,
            )
        if confirmation.status == "reconciled":
            return self._result(confirmation, "verified", confirmation.destination_path, 0)
        if confirmation.status != "unknown":
            raise UserOrgUnitReconciliationError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_RECONCILIATION_NOT_AVAILABLE,
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
            raise UserOrgUnitReconciliationError(
                GoogleWorkspaceErrorCode.ORGANIZATION_ACCESS_DENIED,
                confirmation.id,
                0,
                confirmation.target_google_id,
            )
        attempts = 0
        observed = confirmation.expected_source_path
        window = BoundedReconciliationWindow(
            poll_delays=self.poll_delays,
            max_wait_seconds=self.max_wait_seconds,
            sleeper=self.sleeper,
            monotonic=self.monotonic,
        )
        for attempt in window.attempts():
            attempts = attempt.number
            try:
                current = self.service._read_user(
                    actor,
                    organization_id,
                    confirmation.target_google_id,
                    attempt.request_timeout_seconds,
                )
            except GoogleWorkspaceError as error:
                if error.retryable and attempts < len(self.poll_delays):
                    continue
                raise UserOrgUnitReconciliationError(
                    error.code,
                    confirmation.id,
                    attempts,
                    confirmation.target_google_id,
                    retryable=error.retryable,
                ) from None
            if current.customer_id != confirmation.google_customer_id:
                raise UserOrgUnitReconciliationError(
                    GoogleWorkspaceErrorCode.GOOGLE_TENANT_MISMATCH,
                    confirmation.id,
                    attempts,
                    confirmation.target_google_id,
                )
            observed = self.service._required_path(current)
            if observed == confirmation.destination_path:
                if not mark_confirmation_reconciled(
                    self.db, GoogleWorkspaceUserOrgUnitConfirmation, confirmation.id
                ):
                    self.db.refresh(confirmation)
                    if confirmation.status != "reconciled":
                        raise UserOrgUnitReconciliationError(
                            GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_RECONCILIATION_NOT_AVAILABLE,
                            confirmation.id,
                            attempts,
                            confirmation.target_google_id,
                        )
                return self._result(confirmation, "verified", observed, attempts)
        return self._result(confirmation, "unknown", observed, attempts)

    @staticmethod
    def _result(
        confirmation: GoogleWorkspaceUserOrgUnitConfirmation,
        status: Literal["verified", "unknown"],
        observed: str,
        attempts: int,
    ) -> UserOrgUnitMoveReconciliationResult:
        return UserOrgUnitMoveReconciliationResult(
            target_google_id=confirmation.target_google_id,
            target_primary_email=confirmation.target_primary_email,
            status=status,
            observed_org_unit_path=observed,
            attempts=attempts,
            correlation_id=str(confirmation.id),
            message=(
                "Google now reports the requested Organizational Unit."
                if status == "verified"
                else "The result is still unknown. Refresh the user before considering "
                "another move."
            ),
        )
