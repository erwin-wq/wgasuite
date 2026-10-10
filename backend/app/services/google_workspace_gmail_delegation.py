from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from googleapiclient.errors import HttpError
from sqlalchemy import select, update
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
from app.services.google_workspace_user_lookup import (
    GoogleWorkspaceUserLookup,
    GoogleWorkspaceUserLookupResult,
)

logger = logging.getLogger(__name__)
DelegateOperation = Literal["create", "remove"]
CONFIRMATION_LIFETIME = timedelta(minutes=5)


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

        token = secrets.token_urlsafe(32)
        token_digest = self._token_digest(token)
        expires_at = datetime.now(UTC) + CONFIRMATION_LIFETIME
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
                token_digest=token_digest,
                expires_at=expires_at,
            )
            self.db.add(confirmation)
        else:
            confirmation.actor_user_id = actor.id
            confirmation.owner_primary_email = owner.primary_email
            confirmation.delegate_primary_email = delegate.primary_email
            confirmation.token_digest = token_digest
            confirmation.status = "pending"
            confirmation.expires_at = expires_at
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
            confirmation.token_digest = token_digest
            confirmation.status = "pending"
            confirmation.expires_at = expires_at
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
            confirmation_token=token,
            expires_at=expires_at,
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
        token_digest = self._token_digest(confirmation_token)
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
        expires_at = confirmation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
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

        consumed_id = self.db.execute(
            update(GoogleWorkspaceDelegateConfirmation)
            .where(
                GoogleWorkspaceDelegateConfirmation.id == confirmation.id,
                GoogleWorkspaceDelegateConfirmation.status == "pending",
                GoogleWorkspaceDelegateConfirmation.token_digest == token_digest,
            )
            .values(status="executing", consumed_at=now)
            .returning(GoogleWorkspaceDelegateConfirmation.id)
        ).scalar_one_or_none()
        self.db.commit()
        if consumed_id is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GMAIL_CONFIRMATION_USED)

        try:
            self._execute_google_change(
                actor=actor,
                organization_id=organization_id,
                operation=operation,
                owner=owner,
                delegate_email=delegate.primary_email,
            )
        except GoogleWorkspaceError:
            self._set_confirmation_status(confirmation.id, "failed")
            raise
        except Exception as error:
            self._set_confirmation_status(confirmation.id, "failed")
            raise self._map_gmail_error(error, operation=operation) from None

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
    ) -> GmailDelegateListResult:
        client: Any | None = None
        try:
            client = self.client_factory.for_gmail_delegates(
                actor=actor,
                organization_id=organization_id,
                owner=self._verified_owner(owner),
                scopes=[GMAIL_DELEGATE_READ_SCOPE],
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

    @staticmethod
    def _token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _set_confirmation_status(self, confirmation_id: UUID, status: str) -> None:
        self.db.execute(
            update(GoogleWorkspaceDelegateConfirmation)
            .where(GoogleWorkspaceDelegateConfirmation.id == confirmation_id)
            .values(status=status)
        )
        self.db.commit()

    @staticmethod
    def _confirmation_blocks_new_preview(
        confirmation: GoogleWorkspaceDelegateConfirmation,
    ) -> bool:
        if confirmation.status not in {"executing", "succeeded"}:
            return False
        expires_at = confirmation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at > datetime.now(UTC)

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
