from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select, update
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
    GoogleWorkspaceOrgUnitCreationConfirmation,
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
    OrganizationalUnitHierarchy,
    OrganizationalUnitTreeNode,
    is_workspace_guests_organizational_unit_or_descendant,
)
from app.services.google_workspace_user_lookup import GoogleWorkspaceUserLookup

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrgUnitCreatePreview:
    parent_org_unit_id: str
    parent_path: str
    name: str
    description: str | None
    expected_path: str
    confirmation_token: str
    expires_at: datetime
    effect: str


@dataclass(frozen=True)
class OrgUnitCreateResult:
    organizational_unit: OrganizationalUnit
    outcome: Literal["created"]
    message: str


@dataclass(frozen=True)
class OrgUnitCreateReconciliationResult:
    status: Literal["verified", "unknown"]
    organizational_unit: OrganizationalUnit | None
    expected_path: str
    attempts: int
    correlation_id: str
    message: str


class OrgUnitCreateError(GoogleWorkspaceError):
    def __init__(
        self,
        code: GoogleWorkspaceErrorCode,
        expected_path: str | None = None,
        *,
        retryable: bool = False,
        google_reason: str | None = None,
    ) -> None:
        self.expected_path = expected_path
        super().__init__(code, retryable=retryable, google_reason=google_reason)


class OrgUnitCreateAmbiguousError(OrgUnitCreateError):
    def __init__(
        self,
        code: GoogleWorkspaceErrorCode,
        correlation_id: UUID,
        expected_path: str,
        *,
        google_reason: str | None = None,
    ) -> None:
        self.correlation_id = str(correlation_id)
        super().__init__(code, expected_path, google_reason=google_reason)


class OrgUnitCreateReconciliationError(OrgUnitCreateError):
    def __init__(
        self,
        code: GoogleWorkspaceErrorCode,
        correlation_id: UUID,
        attempts: int,
        expected_path: str,
        *,
        retryable: bool = False,
    ) -> None:
        self.correlation_id = str(correlation_id)
        self.attempts = attempts
        super().__init__(code, expected_path, retryable=retryable)


class GoogleWorkspaceOrgUnitCreationService:
    """Create one child OU after tenant-bound preview and atomic confirmation."""

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
    def from_settings(cls, db: Session) -> GoogleWorkspaceOrgUnitCreationService:
        factory = GoogleWorkspaceClientFactory.from_settings(db)
        lookup = GoogleWorkspaceUserLookup(factory)
        return cls(db, factory, lookup, GoogleWorkspaceOrganizationalUnits(db, factory, lookup))

    def preview_creation(
        self,
        *,
        actor: User,
        organization_id: UUID,
        parent_org_unit_id: str,
        name: str,
        description: str | None,
    ) -> OrgUnitCreatePreview:
        normalized_name, normalized_description = self._validate_input(name, description)
        organization, connector, google_customer_id, parent, hierarchy = self._resolve(
            actor, organization_id, parent_org_unit_id
        )
        expected_path = self._expected_path(parent.path, normalized_name)
        self._ensure_available(hierarchy, parent.id, expected_path)
        grant = issue_confirmation()
        path_key = expected_path.casefold()
        confirmation = self.db.scalar(
            select(GoogleWorkspaceOrgUnitCreationConfirmation).where(
                GoogleWorkspaceOrgUnitCreationConfirmation.organization_id == organization_id,
                GoogleWorkspaceOrgUnitCreationConfirmation.expected_path_key == path_key,
            )
        )
        if confirmation is not None and confirmation_blocks_new_preview(
            confirmation.status, confirmation.expires_at
        ):
            raise OrgUnitCreateError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CREATE_CONFIRMATION_USED, expected_path
            )
        values = {
            "customer_id": organization.customer_id,
            "connector_config_id": connector.id,
            "actor_user_id": actor.id,
            "google_customer_id": google_customer_id,
            "parent_org_unit_id": parent.id,
            "parent_path": parent.path,
            "requested_name": normalized_name,
            "expected_path": expected_path,
            "expected_path_key": path_key,
            "description": normalized_description,
            "token_digest": grant.token_digest,
            "status": "pending",
            "expires_at": grant.expires_at,
            "consumed_at": None,
            "created_org_unit_id": None,
        }
        try:
            if confirmation is None:
                confirmation = GoogleWorkspaceOrgUnitCreationConfirmation(
                    organization_id=organization_id, **values
                )
                self.db.add(confirmation)
            else:
                for field, value in values.items():
                    setattr(confirmation, field, value)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise OrgUnitCreateError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CREATE_CONFIRMATION_USED, expected_path
            ) from None
        return OrgUnitCreatePreview(
            parent_org_unit_id=parent.id,
            parent_path=parent.path,
            name=normalized_name,
            description=normalized_description,
            expected_path=expected_path,
            confirmation_token=grant.token,
            expires_at=grant.expires_at,
            effect=(
                "One child Organizational Unit will be created. It normally inherits parent "
                "settings, but the Directory API does not verify effective policy inheritance."
            ),
        )

    def execute_creation(
        self, *, actor: User, organization_id: UUID, confirmation_token: str
    ) -> OrgUnitCreateResult:
        digest = confirmation_token_digest(confirmation_token)
        confirmation = self.db.scalar(
            select(GoogleWorkspaceOrgUnitCreationConfirmation).where(
                GoogleWorkspaceOrgUnitCreationConfirmation.token_digest == digest,
                GoogleWorkspaceOrgUnitCreationConfirmation.organization_id == organization_id,
                GoogleWorkspaceOrgUnitCreationConfirmation.actor_user_id == actor.id,
            )
        )
        if confirmation is None:
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CREATE_CONFIRMATION_INVALID
            )
        if confirmation.status != "pending":
            raise OrgUnitCreateError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CREATE_CONFIRMATION_USED,
                confirmation.expected_path,
            )
        if confirmation_is_expired(confirmation.expires_at):
            set_confirmation_status(
                self.db, GoogleWorkspaceOrgUnitCreationConfirmation, confirmation.id, "expired"
            )
            raise OrgUnitCreateError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CREATE_CONFIRMATION_EXPIRED,
                confirmation.expected_path,
            )
        try:
            organization, connector, google_customer_id, parent, hierarchy = self._resolve(
                actor, organization_id, confirmation.parent_org_unit_id
            )
            self._ensure_available(hierarchy, parent.id, confirmation.expected_path)
        except GoogleWorkspaceError:
            set_confirmation_status(
                self.db, GoogleWorkspaceOrgUnitCreationConfirmation, confirmation.id, "rejected"
            )
            raise
        if (
            organization.customer_id != confirmation.customer_id
            or connector.id != confirmation.connector_config_id
            or google_customer_id != confirmation.google_customer_id
            or parent.id != confirmation.parent_org_unit_id
            or parent.path != confirmation.parent_path
            or self._expected_path(parent.path, confirmation.requested_name)
            != confirmation.expected_path
        ):
            set_confirmation_status(
                self.db, GoogleWorkspaceOrgUnitCreationConfirmation, confirmation.id, "rejected"
            )
            raise OrgUnitCreateError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CREATE_STATE_CHANGED,
                confirmation.expected_path,
            )
        if not consume_confirmation(
            self.db,
            GoogleWorkspaceOrgUnitCreationConfirmation,
            confirmation_id=confirmation.id,
            token_digest=digest,
        ):
            raise OrgUnitCreateError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CREATE_CONFIRMATION_USED,
                confirmation.expected_path,
            )
        try:
            created = self._write_creation(
                actor,
                organization_id,
                google_customer_id,
                parent.path,
                confirmation.requested_name,
                confirmation.description,
            )
        except GoogleWorkspaceError as error:
            status = "unknown" if is_ambiguous_mutation_error(error) else "failed"
            set_confirmation_status(
                self.db, GoogleWorkspaceOrgUnitCreationConfirmation, confirmation.id, status
            )
            if status == "unknown":
                raise OrgUnitCreateAmbiguousError(
                    error.code,
                    confirmation.id,
                    confirmation.expected_path,
                    google_reason=error.google_reason,
                ) from None
            raise OrgUnitCreateError(
                error.code,
                confirmation.expected_path,
                retryable=error.retryable,
                google_reason=error.google_reason,
            ) from None
        if not self._matches(created, confirmation):
            set_confirmation_status(
                self.db, GoogleWorkspaceOrgUnitCreationConfirmation, confirmation.id, "unknown"
            )
            raise OrgUnitCreateAmbiguousError(
                GoogleWorkspaceErrorCode.GOOGLE_API_ERROR,
                confirmation.id,
                confirmation.expected_path,
            )
        self.db.execute(
            update(GoogleWorkspaceOrgUnitCreationConfirmation)
            .where(GoogleWorkspaceOrgUnitCreationConfirmation.id == confirmation.id)
            .values(status="succeeded", created_org_unit_id=created.id)
        )
        self.db.commit()
        return OrgUnitCreateResult(created, "created", f"{created.path} was created.")

    def _resolve(
        self, actor: User, organization_id: UUID, parent_id: str
    ) -> tuple[Organization, ConnectorConfig, str, OrganizationalUnit, OrganizationalUnitHierarchy]:
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
            actor=actor, organization_id=organization_id, email=connector.admin_subject_email
        )
        parent = self.orgunits.get_organizational_unit(
            actor=actor, organization_id=organization_id, org_unit_id=parent_id
        )
        if is_workspace_guests_organizational_unit_or_descendant(parent):
            raise OrgUnitCreateError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_PARENT_PROTECTED, parent.path
            )
        hierarchy = self.orgunits.list_hierarchy(actor=actor, organization_id=organization_id)
        if self._find(hierarchy, parent.id) != parent:
            raise OrgUnitCreateError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CREATE_STATE_CHANGED, parent.path
            )
        return organization, connector, admin.customer_id, parent, hierarchy

    def _write_creation(
        self,
        actor: User,
        organization_id: UUID,
        customer_id: str,
        parent_path: str,
        name: str,
        description: str | None,
    ) -> OrganizationalUnit:
        client: Any | None = None
        try:
            client = self.client_factory.for_directory_orgunits(
                actor=actor,
                organization_id=organization_id,
                scopes=(DIRECTORY_ORGUNIT_WRITE_SCOPE,),
            )
            body: dict[str, str] = {"name": name, "parentOrgUnitPath": parent_path}
            if description is not None:
                body["description"] = description
            response = (
                client.orgunits()
                .insert(customerId=customer_id, body=body, fields=ORGUNIT_FIELDS)
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
    def _validate_input(name: str, description: str | None) -> tuple[str, str | None]:
        normalized_name = name.strip() if isinstance(name, str) else ""
        if (
            not normalized_name
            or len(normalized_name) > 256
            or "/" in normalized_name
            or any(ord(c) < 32 for c in normalized_name)
        ):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_NAME_INVALID)
        normalized_description = description.strip() if isinstance(description, str) else None
        normalized_description = normalized_description or None
        if normalized_description is not None and (
            len(normalized_description) > 4096
            or any(ord(c) < 32 and c not in "\n\r\t" for c in normalized_description)
        ):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_DESCRIPTION_INVALID)
        return normalized_name, normalized_description

    @staticmethod
    def _expected_path(parent_path: str, name: str) -> str:
        path = f"/{name}" if parent_path == "/" else f"{parent_path}/{name}"
        if len(path) > 1000:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_NAME_INVALID)
        return path

    @classmethod
    def _find(
        cls, hierarchy: OrganizationalUnitHierarchy, unit_id: str
    ) -> OrganizationalUnit | None:
        pending = list(hierarchy.roots)
        while pending:
            unit = pending.pop()
            if unit.id == unit_id:
                return OrganizationalUnit(
                    unit.id,
                    unit.name,
                    unit.description,
                    unit.path,
                    unit.parent_id,
                    unit.parent_path,
                )
            pending.extend(unit.children)
        return None

    @classmethod
    def _ensure_available(
        cls, hierarchy: OrganizationalUnitHierarchy, parent_id: str, expected_path: str
    ) -> None:
        pending = list(hierarchy.roots)
        while pending:
            unit = pending.pop()
            if unit.path.casefold() == expected_path.casefold() or (
                unit.parent_id == parent_id
                and unit.name.casefold() == expected_path.rsplit("/", 1)[-1].casefold()
            ):
                raise OrgUnitCreateError(
                    GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_ALREADY_EXISTS, expected_path
                )
            pending.extend(unit.children)

    @staticmethod
    def _matches(
        unit: OrganizationalUnit, confirmation: GoogleWorkspaceOrgUnitCreationConfirmation
    ) -> bool:
        return (
            unit.name == confirmation.requested_name
            and unit.path == confirmation.expected_path
            and unit.parent_id == confirmation.parent_org_unit_id
            and unit.parent_path == confirmation.parent_path
            and unit.description == confirmation.description
        )


class GoogleWorkspaceOrgUnitCreationReconciliationService:
    def __init__(
        self,
        db: Session,
        service: GoogleWorkspaceOrgUnitCreationService,
        *,
        poll_delays: Sequence[float] = RECONCILIATION_BACKOFF_SECONDS,
        max_wait_seconds: float = RECONCILIATION_MAX_WAIT_SECONDS,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.db, self.service = db, service
        self.poll_delays, self.max_wait_seconds = tuple(poll_delays), max_wait_seconds
        self.sleeper, self.monotonic = sleeper, monotonic

    @classmethod
    def from_settings(cls, db: Session) -> GoogleWorkspaceOrgUnitCreationReconciliationService:
        return cls(db, GoogleWorkspaceOrgUnitCreationService.from_settings(db))

    def reconcile_creation(
        self, *, actor: User, organization_id: UUID, confirmation_token: str
    ) -> OrgUnitCreateReconciliationResult:
        confirmation = self.db.scalar(
            select(GoogleWorkspaceOrgUnitCreationConfirmation).where(
                GoogleWorkspaceOrgUnitCreationConfirmation.token_digest
                == confirmation_token_digest(confirmation_token),
                GoogleWorkspaceOrgUnitCreationConfirmation.organization_id == organization_id,
                GoogleWorkspaceOrgUnitCreationConfirmation.actor_user_id == actor.id,
            )
        )
        if confirmation is None:
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CREATE_RECONCILIATION_NOT_AVAILABLE
            )
        if confirmation_is_expired(confirmation.expires_at):
            raise OrgUnitCreateReconciliationError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CREATE_RECONCILIATION_EXPIRED,
                confirmation.id,
                0,
                confirmation.expected_path,
            )
        if confirmation.status == "reconciled":
            hierarchy = self.service.orgunits.list_hierarchy(
                actor=actor, organization_id=organization_id
            )
            return self._result(
                confirmation, self._by_path(hierarchy, confirmation.expected_path), 0
            )
        if confirmation.status != "unknown":
            raise OrgUnitCreateReconciliationError(
                GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CREATE_RECONCILIATION_NOT_AVAILABLE,
                confirmation.id,
                0,
                confirmation.expected_path,
            )
        organization = self.db.get(Organization, organization_id)
        if (
            organization is None
            or organization.customer_id != confirmation.customer_id
            or not user_can_admin_customer(actor, confirmation.customer_id)
        ):
            raise OrgUnitCreateReconciliationError(
                GoogleWorkspaceErrorCode.ORGANIZATION_ACCESS_DENIED,
                confirmation.id,
                0,
                confirmation.expected_path,
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
                hierarchy = self.service.orgunits.list_hierarchy(
                    actor=actor,
                    organization_id=organization_id,
                    request_timeout_seconds=attempt.request_timeout_seconds,
                )
            except GoogleWorkspaceError as error:
                if error.retryable and attempts < len(self.poll_delays):
                    continue
                raise OrgUnitCreateReconciliationError(
                    error.code,
                    confirmation.id,
                    attempts,
                    confirmation.expected_path,
                    retryable=error.retryable,
                ) from None
            unit = self._by_path(hierarchy, confirmation.expected_path)
            if unit is not None:
                if not self.service._matches(unit, confirmation):
                    raise OrgUnitCreateReconciliationError(
                        GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CREATE_STATE_CHANGED,
                        confirmation.id,
                        attempts,
                        confirmation.expected_path,
                    )
                if not mark_confirmation_reconciled(
                    self.db, GoogleWorkspaceOrgUnitCreationConfirmation, confirmation.id
                ):
                    self.db.refresh(confirmation)
                    if confirmation.status != "reconciled":
                        raise OrgUnitCreateReconciliationError(
                            GoogleWorkspaceErrorCode.GOOGLE_ORGUNIT_CREATE_RECONCILIATION_NOT_AVAILABLE,
                            confirmation.id,
                            attempts,
                            confirmation.expected_path,
                        )
                self.db.execute(
                    update(GoogleWorkspaceOrgUnitCreationConfirmation)
                    .where(GoogleWorkspaceOrgUnitCreationConfirmation.id == confirmation.id)
                    .values(created_org_unit_id=unit.id)
                )
                self.db.commit()
                return self._result(confirmation, unit, attempts)
        return self._result(confirmation, None, attempts)

    @staticmethod
    def _by_path(hierarchy: OrganizationalUnitHierarchy, path: str) -> OrganizationalUnit | None:
        pending: list[OrganizationalUnitTreeNode] = list(hierarchy.roots)
        while pending:
            unit = pending.pop()
            if unit.path == path:
                return OrganizationalUnit(
                    unit.id,
                    unit.name,
                    unit.description,
                    unit.path,
                    unit.parent_id,
                    unit.parent_path,
                )
            pending.extend(unit.children)
        return None

    @staticmethod
    def _result(
        confirmation: GoogleWorkspaceOrgUnitCreationConfirmation,
        unit: OrganizationalUnit | None,
        attempts: int,
    ) -> OrgUnitCreateReconciliationResult:
        verified = unit is not None
        return OrgUnitCreateReconciliationResult(
            "verified" if verified else "unknown",
            unit,
            confirmation.expected_path,
            attempts,
            str(confirmation.id),
            "Google now reports the created Organizational Unit."
            if verified
            else "The creation result is still unknown. Refresh the hierarchy before "
            "considering another creation.",
        )
