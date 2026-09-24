from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID

from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import user_can_operate_customer_connector
from app.connectors.google_workspace_credentials import (
    CredentialProviderRegistry,
    DelegatedCredentialFactory,
    FileCredentialProvider,
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


class GoogleWorkspaceClientFactory:
    """Create an uncached, least-privilege Google client after tenant authorization."""

    def __init__(
        self,
        db: Session,
        credential_providers: CredentialProviderRegistry,
        *,
        client_builder: GoogleClientBuilder = build,
    ) -> None:
        self.db = db
        self.credential_factory = DelegatedCredentialFactory(credential_providers)
        self.client_builder = client_builder

    @classmethod
    def from_settings(
        cls,
        db: Session,
        *,
        client_builder: GoogleClientBuilder = build,
    ) -> "GoogleWorkspaceClientFactory":
        settings = get_settings()
        providers = CredentialProviderRegistry(
            [FileCredentialProvider(settings.google_workspace_credentials_directory)]
        )
        return cls(db, providers, client_builder=client_builder)

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
            "version=%s scopes=%s admin_subject=%s",
            organization_id,
            connector_config.id,
            service,
            version,
            list(normalized_scopes),
            connector_config.admin_subject_email,
        )
        try:
            return self.client_builder(
                service,
                version,
                credentials=credentials,
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
