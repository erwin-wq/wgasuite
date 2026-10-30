from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httplib2
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import user_can_admin_customer, user_can_operate_customer_connector
from app.connectors.google_workspace_credentials import (
    DIRECTORY_GROUP_MEMBER_SCOPE,
    DIRECTORY_USER_WRITE_SCOPE,
    CredentialProviderRegistry,
    DelegatedCredentialFactory,
    FileCredentialProvider,
    ManagedFileCredentialProvider,
    normalize_scopes,
)
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
    map_google_api_error,
)
from app.core.config import get_settings
from app.models import ConnectorConfig, Organization, User

logger = logging.getLogger(__name__)
GoogleClientBuilder = Callable[..., Any]
DEFAULT_REQUEST_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class VerifiedMailboxOwner:
    """Canonical Directory identity approved by the delegation service."""

    google_user_id: str
    primary_email: str
    customer_id: str


class GoogleWorkspaceClientFactory:
    """Create an uncached, least-privilege Google client after tenant authorization."""

    def __init__(
        self,
        db: Session,
        credential_providers: CredentialProviderRegistry,
        *,
        client_builder: GoogleClientBuilder = build,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.db = db
        self.credential_factory = DelegatedCredentialFactory(credential_providers)
        self.client_builder = client_builder
        self.request_timeout_seconds = request_timeout_seconds

    @classmethod
    def from_settings(
        cls,
        db: Session,
        *,
        client_builder: GoogleClientBuilder = build,
    ) -> "GoogleWorkspaceClientFactory":
        settings = get_settings()
        providers = CredentialProviderRegistry(
            [
                FileCredentialProvider(settings.google_workspace_credentials_directory),
                ManagedFileCredentialProvider(
                    settings.google_workspace_managed_credentials_directory
                ),
            ]
        )
        return cls(
            db,
            providers,
            client_builder=client_builder,
            request_timeout_seconds=settings.google_workspace_request_timeout_seconds,
        )

    def for_organization(
        self,
        *,
        actor: User,
        organization_id: UUID,
        service: str,
        version: str,
        scopes: Sequence[str],
    ) -> Any:
        organization = self.db.get(Organization, organization_id)
        if organization is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.ORGANIZATION_NOT_FOUND)
        if not user_can_operate_customer_connector(actor, organization.customer_id):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.ORGANIZATION_ACCESS_DENIED)

        statement = select(ConnectorConfig).where(
            ConnectorConfig.organization_id == organization_id,
            ConnectorConfig.connector_type == "google_workspace",
        )
        connector_config = self.db.scalar(statement)
        if connector_config is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED)

        credentials, normalized_scopes = self.credential_factory.create(connector_config, scopes)
        logger.info(
            "Creating Google API client organization_id=%s connector_id=%s service=%s "
            "version=%s scopes=%s",
            organization_id,
            connector_config.id,
            service,
            version,
            list(normalized_scopes),
        )
        try:
            authorized_http = AuthorizedHttp(
                credentials,
                http=httplib2.Http(timeout=self.request_timeout_seconds),
            )
            return self.client_builder(
                service,
                version,
                http=authorized_http,
                cache_discovery=False,
            )
        except GoogleWorkspaceError:
            raise
        except Exception as error:
            logger.warning(
                "Google API client creation failed organization_id=%s connector_id=%s "
                "service=%s version=%s",
                organization_id,
                connector_config.id,
                service,
                version,
            )
            raise map_google_api_error(error) from None

    def for_gmail_delegates(
        self,
        *,
        actor: User,
        organization_id: UUID,
        owner: VerifiedMailboxOwner,
        scopes: Sequence[str],
        request_timeout_seconds: float | None = None,
    ) -> Any:
        """Build a fixed Gmail delegate client for one Directory-verified mailbox owner."""

        organization = self.db.get(Organization, organization_id)
        if organization is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.ORGANIZATION_NOT_FOUND)
        if not user_can_admin_customer(actor, organization.customer_id):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.ORGANIZATION_ACCESS_DENIED)
        if not owner.google_user_id or not owner.customer_id:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_USER_LOOKUP_MISMATCH)

        statement = select(ConnectorConfig).where(
            ConnectorConfig.organization_id == organization_id,
            ConnectorConfig.connector_type == "google_workspace",
        )
        connector_config = self.db.scalar(statement)
        if connector_config is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED)

        credentials, normalized_scopes = self.credential_factory.create_for_gmail_mailbox_owner(
            connector_config,
            scopes,
            owner.primary_email,
        )
        logger.info(
            "Creating owner-impersonated Gmail delegate client organization_id=%s "
            "connector_id=%s scopes=%s",
            organization_id,
            connector_config.id,
            list(normalized_scopes),
        )
        timeout_seconds = self.request_timeout_seconds
        if request_timeout_seconds is not None:
            timeout_seconds = max(
                0.1,
                min(request_timeout_seconds, self.request_timeout_seconds),
            )
        try:
            authorized_http = AuthorizedHttp(
                credentials,
                http=httplib2.Http(timeout=timeout_seconds),
            )
            return self.client_builder(
                "gmail",
                "v1",
                http=authorized_http,
                cache_discovery=False,
            )
        except GoogleWorkspaceError:
            raise
        except Exception as error:
            logger.warning(
                "Gmail delegate client creation failed organization_id=%s connector_id=%s",
                organization_id,
                connector_config.id,
            )
            raise map_google_api_error(error) from None

    def for_directory_groups(
        self,
        *,
        actor: User,
        organization_id: UUID,
        scopes: Sequence[str],
        request_timeout_seconds: float | None = None,
    ) -> Any:
        """Build an authorized, operation-scoped Directory groups client."""

        organization = self.db.get(Organization, organization_id)
        if organization is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.ORGANIZATION_NOT_FOUND)
        requested_scopes = normalize_scopes(scopes)
        is_membership_write = requested_scopes == (DIRECTORY_GROUP_MEMBER_SCOPE,)
        authorized = (
            user_can_admin_customer(actor, organization.customer_id)
            if is_membership_write
            else user_can_operate_customer_connector(actor, organization.customer_id)
        )
        if not authorized:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.ORGANIZATION_ACCESS_DENIED)
        connector_config = self.db.scalar(
            select(ConnectorConfig).where(
                ConnectorConfig.organization_id == organization_id,
                ConnectorConfig.connector_type == "google_workspace",
            )
        )
        if connector_config is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED)
        credentials, normalized_scopes = self.credential_factory.create_for_directory_groups(
            connector_config, scopes
        )
        timeout_seconds = self.request_timeout_seconds
        if request_timeout_seconds is not None:
            timeout_seconds = max(0.1, min(request_timeout_seconds, timeout_seconds))
        logger.info(
            "Creating Directory groups client organization_id=%s connector_id=%s scopes=%s",
            organization_id,
            connector_config.id,
            list(normalized_scopes),
        )
        try:
            authorized_http = AuthorizedHttp(
                credentials,
                http=httplib2.Http(timeout=timeout_seconds),
            )
            return self.client_builder(
                "admin",
                "directory_v1",
                http=authorized_http,
                cache_discovery=False,
            )
        except GoogleWorkspaceError:
            raise
        except Exception as error:
            logger.warning(
                "Directory groups client creation failed organization_id=%s connector_id=%s",
                organization_id,
                connector_config.id,
            )
            raise map_google_api_error(error) from None

    def for_directory_users(
        self,
        *,
        actor: User,
        organization_id: UUID,
        scopes: Sequence[str],
        request_timeout_seconds: float | None = None,
    ) -> Any:
        """Build an authorized, operation-scoped Directory users client."""

        organization = self.db.get(Organization, organization_id)
        if organization is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.ORGANIZATION_NOT_FOUND)
        requested_scopes = normalize_scopes(scopes)
        is_user_write = requested_scopes == (DIRECTORY_USER_WRITE_SCOPE,)
        authorized = (
            user_can_admin_customer(actor, organization.customer_id)
            if is_user_write
            else user_can_operate_customer_connector(actor, organization.customer_id)
        )
        if not authorized:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.ORGANIZATION_ACCESS_DENIED)
        connector_config = self.db.scalar(
            select(ConnectorConfig).where(
                ConnectorConfig.organization_id == organization_id,
                ConnectorConfig.connector_type == "google_workspace",
            )
        )
        if connector_config is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED)
        credentials, normalized_scopes = self.credential_factory.create_for_directory_users(
            connector_config, scopes
        )
        timeout_seconds = self.request_timeout_seconds
        if request_timeout_seconds is not None:
            timeout_seconds = max(0.1, min(request_timeout_seconds, timeout_seconds))
        logger.info(
            "Creating Directory users client organization_id=%s connector_id=%s scopes=%s",
            organization_id,
            connector_config.id,
            list(normalized_scopes),
        )
        try:
            authorized_http = AuthorizedHttp(
                credentials,
                http=httplib2.Http(timeout=timeout_seconds),
            )
            return self.client_builder(
                "admin",
                "directory_v1",
                http=authorized_http,
                cache_discovery=False,
            )
        except GoogleWorkspaceError:
            raise
        except Exception as error:
            logger.warning(
                "Directory users client creation failed organization_id=%s connector_id=%s",
                organization_id,
                connector_config.id,
            )
            raise map_google_api_error(error) from None

    def for_directory_orgunits(
        self,
        *,
        actor: User,
        organization_id: UUID,
        scopes: Sequence[str],
        request_timeout_seconds: float | None = None,
    ) -> Any:
        """Build a fresh, read-only Directory organizational-units client."""

        organization = self.db.get(Organization, organization_id)
        if organization is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.ORGANIZATION_NOT_FOUND)
        if not user_can_operate_customer_connector(actor, organization.customer_id):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.ORGANIZATION_ACCESS_DENIED)
        connector_config = self.db.scalar(
            select(ConnectorConfig).where(
                ConnectorConfig.organization_id == organization_id,
                ConnectorConfig.connector_type == "google_workspace",
            )
        )
        if connector_config is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED)
        credentials, normalized_scopes = (
            self.credential_factory.create_for_directory_orgunits(connector_config, scopes)
        )
        timeout_seconds = self.request_timeout_seconds
        if request_timeout_seconds is not None:
            timeout_seconds = max(0.1, min(request_timeout_seconds, timeout_seconds))
        logger.info(
            "Creating Directory orgunits client organization_id=%s connector_id=%s scopes=%s",
            organization_id,
            connector_config.id,
            list(normalized_scopes),
        )
        try:
            authorized_http = AuthorizedHttp(
                credentials,
                http=httplib2.Http(timeout=timeout_seconds),
            )
            return self.client_builder(
                "admin",
                "directory_v1",
                http=authorized_http,
                cache_discovery=False,
            )
        except GoogleWorkspaceError:
            raise
        except Exception as error:
            logger.warning(
                "Directory orgunits client creation failed organization_id=%s connector_id=%s",
                organization_id,
                connector_config.id,
            )
            raise map_google_api_error(error) from None
