from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import user_can_admin_customer
from app.connectors.google_workspace_client import GoogleWorkspaceClientFactory
from app.connectors.google_workspace_credentials import DIRECTORY_ORGUNIT_WRITE_SCOPE
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
    map_google_api_error,
)
from app.models import (
    ConnectorConfig,
    GoogleWorkspaceOrgUnitDescriptionConfirmation,
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
    ORGUNIT_FIELDS,
    GoogleWorkspaceOrganizationalUnits,
    OrganizationalUnit,
    is_workspace_guests_organizational_unit_or_descendant,
)
from app.services.google_workspace_user_lookup import GoogleWorkspaceUserLookup


@dataclass(frozen=True)
class OrgUnitDescriptionPreview:
    org_unit_id: str
    name: str
    path: str
    original_description: str | None
    proposed_description: str | None
    confirmation_token: str
    expires_at: datetime
    effect: str


@dataclass(frozen=True)
class OrgUnitDescriptionResult:
    organizational_unit: OrganizationalUnit
    previous_description: str | None
    outcome: Literal["updated"]
    message: str


@dataclass(frozen=True)
class OrgUnitDescriptionReconciliationResult:
    status: Literal["verified", "unknown"]
    organizational_unit: OrganizationalUnit | None
    attempts: int
    correlation_id: str
    message: str


class OrgUnitDescriptionError(GoogleWorkspaceError):
    def __init__(
        self,
        code: GoogleWorkspaceErrorCode,
        org_unit_id: str | None = None,
        *,
        retryable: bool = False,
        google_reason: str | None = None,
    ) -> None:
        self.org_unit_id = org_unit_id
        super().__init__(code, retryable=retryable, google_reason=google_reason)


class OrgUnitDescriptionAmbiguousError(OrgUnitDescriptionError):
    def __init__(
        self,
        code: GoogleWorkspaceErrorCode,
        correlation_id: UUID,
        org_unit_id: str,
        *,
        google_reason: str | None = None,
    ) -> None:
        self.correlation_id = str(correlation_id)
        super().__init__(code, org_unit_id, google_reason=google_reason)


class OrgUnitDescriptionReconciliationError(OrgUnitDescriptionError):
    def __init__(
        self,
        code: GoogleWorkspaceErrorCode,
        correlation_id: UUID,
        attempts: int,
        org_unit_id: str,
        *,
        retryable: bool = False,
    ) -> None:
        self.correlation_id = str(correlation_id)
        self.attempts = attempts
        super().__init__(code, org_unit_id, retryable=retryable)


class GoogleWorkspaceOrgUnitDescriptionService:
    """Update only the description of one verified, non-protected OU."""

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
    def from_settings(cls, db: Session) -> GoogleWorkspaceOrgUnitDescriptionService:
        factory = GoogleWorkspaceClientFactory.from_settings(db)
        lookup = GoogleWorkspaceUserLookup(factory)
        return cls(db, factory, lookup, GoogleWorkspaceOrganizationalUnits(db, factory, lookup))

    def preview_update(
        self,
        *,
        actor: User,
        organization_id: UUID,
        org_unit_id: str,
        description: str,
    ) -> OrgUnitDescriptionPreview:
        proposed = self._normalize_description(description)
        organization, connector, google_customer_id, target = self._resolve(
            actor, organization_id, org_unit_id
        )
        if target.description == proposed:
            raise OrgUnitDescriptionError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_UNCHANGED, target.id
            )
        grant = issue_confirmation()
        confirmation = self.db.scalar(
            select(GoogleWorkspaceOrgUnitDescriptionConfirmation).where(
                GoogleWorkspaceOrgUnitDescriptionConfirmation.organization_id == organization_id,
                GoogleWorkspaceOrgUnitDescriptionConfirmation.target_org_unit_id == target.id,
            )
        )
        if confirmation is not None and confirmation_blocks_new_preview(
            confirmation.status, confirmation.expires_at
        ):
            raise OrgUnitDescriptionError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_CONFIRMATION_USED, target.id
            )
        values = {
            "customer_id": organization.customer_id,
            "connector_config_id": connector.id,
            "actor_user_id": actor.id,
            "google_customer_id": google_customer_id,
            "target_name": target.name,
            "target_path": target.path,
            "parent_org_unit_id": target.parent_id,
            "parent_path": target.parent_path,
            "original_description": target.description,
            "requested_description": proposed,
            "token_digest": grant.token_digest,
            "status": "pending",
            "expires_at": grant.expires_at,
            "consumed_at": None,
        }
        if confirmation is None:
            confirmation = GoogleWorkspaceOrgUnitDescriptionConfirmation(
                organization_id=organization_id,
                target_org_unit_id=target.id,
                **values,
            )
            self.db.add(confirmation)
        else:
            for field, value in values.items():
                setattr(confirmation, field, value)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise OrgUnitDescriptionError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_CONFIRMATION_USED, target.id
            ) from None
        return OrgUnitDescriptionPreview(
            org_unit_id=target.id,
            name=target.name,
            path=target.path,
            original_description=target.description,
            proposed_description=proposed,
            confirmation_token=grant.token,
            expires_at=grant.expires_at,
            effect=(
                "Only this Organizational Unit's description will change. WGASuite does not "
                "change its name, parent, users, or effective policies."
            ),
        )

    def execute_update(
        self, *, actor: User, organization_id: UUID, confirmation_token: str
    ) -> OrgUnitDescriptionResult:
        digest = confirmation_token_digest(confirmation_token)
        confirmation = self.db.scalar(
            select(GoogleWorkspaceOrgUnitDescriptionConfirmation).where(
                GoogleWorkspaceOrgUnitDescriptionConfirmation.token_digest == digest,
                GoogleWorkspaceOrgUnitDescriptionConfirmation.organization_id == organization_id,
                GoogleWorkspaceOrgUnitDescriptionConfirmation.actor_user_id == actor.id,
            )
        )
        if confirmation is None:
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_CONFIRMATION_INVALID
            )
        if confirmation.status != "pending":
            raise OrgUnitDescriptionError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_CONFIRMATION_USED,
                confirmation.target_org_unit_id,
            )
        if confirmation_is_expired(confirmation.expires_at):
            set_confirmation_status(
                self.db,
                GoogleWorkspaceOrgUnitDescriptionConfirmation,
                confirmation.id,
                "expired",
            )
            raise OrgUnitDescriptionError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_CONFIRMATION_EXPIRED,
                confirmation.target_org_unit_id,
            )
        try:
            organization, connector, google_customer_id, target = self._resolve(
                actor, organization_id, confirmation.target_org_unit_id
            )
        except GoogleWorkspaceError:
            set_confirmation_status(
                self.db,
                GoogleWorkspaceOrgUnitDescriptionConfirmation,
                confirmation.id,
                "rejected",
            )
            raise
        if (
            organization.customer_id != confirmation.customer_id
            or connector.id != confirmation.connector_config_id
            or google_customer_id != confirmation.google_customer_id
            or not self._identity_matches(target, confirmation)
            or target.description != confirmation.original_description
        ):
            set_confirmation_status(
                self.db,
                GoogleWorkspaceOrgUnitDescriptionConfirmation,
                confirmation.id,
                "rejected",
            )
            raise OrgUnitDescriptionError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_STATE_CHANGED, target.id
            )
        if not consume_confirmation(
            self.db,
            GoogleWorkspaceOrgUnitDescriptionConfirmation,
            confirmation_id=confirmation.id,
            token_digest=digest,
        ):
            raise OrgUnitDescriptionError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_CONFIRMATION_USED, target.id
            )
        try:
            updated = self._write_update(
                actor,
                organization_id,
                google_customer_id,
                target,
                confirmation.requested_description,
            )
        except GoogleWorkspaceError as error:
            status = "unknown" if is_ambiguous_mutation_error(error) else "failed"
            set_confirmation_status(
                self.db,
                GoogleWorkspaceOrgUnitDescriptionConfirmation,
                confirmation.id,
                status,
            )
            if status == "unknown":
                raise OrgUnitDescriptionAmbiguousError(
                    error.code,
                    confirmation.id,
                    target.id,
                    google_reason=error.google_reason,
                ) from None
            raise OrgUnitDescriptionError(
                error.code,
                target.id,
                retryable=error.retryable,
                google_reason=error.google_reason,
            ) from None
        if (
            not self._identity_matches(updated, confirmation)
            or updated.description != confirmation.requested_description
        ):
            set_confirmation_status(
                self.db,
                GoogleWorkspaceOrgUnitDescriptionConfirmation,
                confirmation.id,
                "unknown",
            )
            raise OrgUnitDescriptionAmbiguousError(
                GoogleWorkspaceErrorCode.GOOGLE_API_ERROR, confirmation.id, target.id
            )
        set_confirmation_status(
            self.db,
            GoogleWorkspaceOrgUnitDescriptionConfirmation,
            confirmation.id,
            "succeeded",
        )
        return OrgUnitDescriptionResult(
            organizational_unit=updated,
            previous_description=confirmation.original_description,
            outcome="updated",
            message=f"The description for {updated.path} was updated.",
        )

    def _resolve(
        self, actor: User, organization_id: UUID, org_unit_id: str
    ) -> tuple[Organization, ConnectorConfig, str, OrganizationalUnit]:
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
        administrator = self.user_lookup.lookup(
            actor=actor,
            organization_id=organization_id,
            email=connector.admin_subject_email,
        )
        target = self.orgunits.get_organizational_unit(
            actor=actor, organization_id=organization_id, org_unit_id=org_unit_id
        )
        if target.path == "/" or is_workspace_guests_organizational_unit_or_descendant(target):
            raise OrgUnitDescriptionError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_TARGET_PROTECTED, target.id
            )
        return organization, connector, administrator.customer_id, target

    def _write_update(
        self,
        actor: User,
        organization_id: UUID,
        google_customer_id: str,
        target: OrganizationalUnit,
        description: str | None,
    ) -> OrganizationalUnit:
        client: Any | None = None
        try:
            client = self.client_factory.for_directory_orgunits(
                actor=actor,
                organization_id=organization_id,
                scopes=(DIRECTORY_ORGUNIT_WRITE_SCOPE,),
            )
            response = (
                client.orgunits()
                .patch(
                    customerId=google_customer_id,
                    orgUnitPath=target.id,
                    body={"description": description or ""},
                    fields=ORGUNIT_FIELDS,
                )
                .execute(num_retries=0)
            )
            return GoogleWorkspaceOrganizationalUnits._to_unit(response)
        except GoogleWorkspaceError:
            raise
        except Exception as error:
            raise map_google_api_error(error) from None
        finally:
            GoogleWorkspaceOrganizationalUnits._close_client(client, organization_id)

    @staticmethod
    def _normalize_description(value: str) -> str | None:
        if not isinstance(value, str) or len(value) > 4096:
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_INVALID
            )
        normalized = value.strip()
        if any(ord(character) < 32 and character not in "\n\r\t" for character in normalized):
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_INVALID
            )
        return normalized or None

    @staticmethod
    def _identity_matches(
        unit: OrganizationalUnit,
        confirmation: GoogleWorkspaceOrgUnitDescriptionConfirmation,
    ) -> bool:
        return (
            unit.id == confirmation.target_org_unit_id
            and unit.name == confirmation.target_name
            and unit.path == confirmation.target_path
            and unit.parent_id == confirmation.parent_org_unit_id
            and unit.parent_path == confirmation.parent_path
        )


class GoogleWorkspaceOrgUnitDescriptionReconciliationService:
    def __init__(
        self,
        db: Session,
        service: GoogleWorkspaceOrgUnitDescriptionService,
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
    def from_settings(cls, db: Session) -> GoogleWorkspaceOrgUnitDescriptionReconciliationService:
        return cls(db, GoogleWorkspaceOrgUnitDescriptionService.from_settings(db))

    def reconcile_update(
        self, *, actor: User, organization_id: UUID, confirmation_token: str
    ) -> OrgUnitDescriptionReconciliationResult:
        confirmation = self.db.scalar(
            select(GoogleWorkspaceOrgUnitDescriptionConfirmation).where(
                GoogleWorkspaceOrgUnitDescriptionConfirmation.token_digest
                == confirmation_token_digest(confirmation_token),
                GoogleWorkspaceOrgUnitDescriptionConfirmation.organization_id == organization_id,
                GoogleWorkspaceOrgUnitDescriptionConfirmation.actor_user_id == actor.id,
            )
        )
        if confirmation is None:
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_RECONCILIATION_NOT_AVAILABLE
            )
        if confirmation_is_expired(confirmation.expires_at):
            raise OrgUnitDescriptionReconciliationError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_RECONCILIATION_EXPIRED,
                confirmation.id,
                0,
                confirmation.target_org_unit_id,
            )
        if confirmation.status not in {"unknown", "reconciled"}:
            raise OrgUnitDescriptionReconciliationError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_RECONCILIATION_NOT_AVAILABLE,
                confirmation.id,
                0,
                confirmation.target_org_unit_id,
            )
        organization = self.db.get(Organization, organization_id)
        if (
            organization is None
            or organization.customer_id != confirmation.customer_id
            or not user_can_admin_customer(actor, confirmation.customer_id)
        ):
            raise OrgUnitDescriptionReconciliationError(
                GoogleWorkspaceErrorCode.ORGANIZATION_ACCESS_DENIED,
                confirmation.id,
                0,
                confirmation.target_org_unit_id,
            )
        attempts = 0
        window = BoundedReconciliationWindow(
            poll_delays=self.poll_delays,
            max_wait_seconds=self.max_wait_seconds,
            sleeper=self.sleeper,
            monotonic=self.monotonic,
        )
        for attempt in window.attempts():
            attempts = attempt.number
            try:
                unit = self.service.orgunits.get_organizational_unit(
                    actor=actor,
                    organization_id=organization_id,
                    org_unit_id=confirmation.target_org_unit_id,
                    request_timeout_seconds=attempt.request_timeout_seconds,
                )
            except GoogleWorkspaceError as error:
                if error.retryable and attempts < len(self.poll_delays):
                    continue
                raise OrgUnitDescriptionReconciliationError(
                    error.code,
                    confirmation.id,
                    attempts,
                    confirmation.target_org_unit_id,
                    retryable=error.retryable,
                ) from None
            if not self.service._identity_matches(unit, confirmation):
                raise OrgUnitDescriptionReconciliationError(
                    GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_STATE_CHANGED,
                    confirmation.id,
                    attempts,
                    confirmation.target_org_unit_id,
                )
            if unit.description == confirmation.requested_description:
                if confirmation.status == "unknown" and not mark_confirmation_reconciled(
                    self.db, GoogleWorkspaceOrgUnitDescriptionConfirmation, confirmation.id
                ):
                    self.db.refresh(confirmation)
                    if confirmation.status != "reconciled":
                        raise OrgUnitDescriptionReconciliationError(
                            GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_RECONCILIATION_NOT_AVAILABLE,
                            confirmation.id,
                            attempts,
                            confirmation.target_org_unit_id,
                        )
                return self._result(confirmation, unit, attempts)
            if unit.description != confirmation.original_description:
                raise OrgUnitDescriptionReconciliationError(
                    GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_STATE_CHANGED,
                    confirmation.id,
                    attempts,
                    confirmation.target_org_unit_id,
                )
        return self._result(confirmation, None, attempts)

    @staticmethod
    def _result(
        confirmation: GoogleWorkspaceOrgUnitDescriptionConfirmation,
        unit: OrganizationalUnit | None,
        attempts: int,
    ) -> OrgUnitDescriptionReconciliationResult:
        verified = unit is not None
        return OrgUnitDescriptionReconciliationResult(
            status="verified" if verified else "unknown",
            organizational_unit=unit,
            attempts=attempts,
            correlation_id=str(confirmation.id),
            message=(
                f"The description for {confirmation.target_path} is verified."
                if verified
                else "Google's final description is still unknown. Refresh before continuing."
            ),
        )
