from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.connectors.google_workspace_client import GoogleWorkspaceClientFactory
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
    map_google_api_error,
)
from app.models import ConnectorConfig, User

logger = logging.getLogger(__name__)

DIRECTORY_USER_READONLY_SCOPE = (
    "https://www.googleapis.com/auth/admin.directory.user.readonly"
)
CONNECTION_CRITICAL_FIELDS = frozenset(
    {
        "auth_method",
        "admin_subject_email",
        "credential_provider",
        "credential_ref",
    }
)

CONFIGURATION_ERROR_CODES = frozenset(
    {
        GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED,
        GoogleWorkspaceErrorCode.CREDENTIAL_REFERENCE_MISSING,
        GoogleWorkspaceErrorCode.CREDENTIALS_NOT_FOUND,
        GoogleWorkspaceErrorCode.INVALID_CREDENTIALS,
        GoogleWorkspaceErrorCode.INVALID_ADMIN_SUBJECT,
        GoogleWorkspaceErrorCode.DELEGATION_FAILED,
    }
)
NETWORK_ERROR_CODES = frozenset(
    {
        GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT,
        GoogleWorkspaceErrorCode.GOOGLE_NETWORK_ERROR,
    }
)

ErrorCategory = Literal["configuration", "google", "network", "unexpected"]


@dataclass(frozen=True)
class ConnectionTestResult:
    status: Literal["connected", "connection_failed"]
    tested_at: datetime
    message: str
    error_code: str | None = None
    error_category: ErrorCategory | None = None
    retryable: bool = False
    persisted: bool = True


def invalidate_connection_result(connector_config: ConnectorConfig) -> None:
    """Invalidate a verification after connection-critical metadata changes."""

    connector_config.status = "configured"
    connector_config.last_tested_at = None
    connector_config.last_error_code = None
    connector_config.last_error = None
    connector_config.connection_config_revision += 1
    connector_config.connection_test_generation += 1


def categorize_error(code: GoogleWorkspaceErrorCode) -> ErrorCategory:
    if code in CONFIGURATION_ERROR_CODES:
        return "configuration"
    if code in NETWORK_ERROR_CODES:
        return "network"
    if code == GoogleWorkspaceErrorCode.GOOGLE_API_ERROR:
        return "unexpected"
    return "google"


class GoogleWorkspaceConnectionTester:
    """Run and persist one minimally scoped Directory API connection probe."""

    def __init__(
        self,
        db: Session,
        client_factory: GoogleWorkspaceClientFactory,
    ) -> None:
        self.db = db
        self.client_factory = client_factory

    @classmethod
    def from_settings(cls, db: Session) -> GoogleWorkspaceConnectionTester:
        return cls(db, GoogleWorkspaceClientFactory.from_settings(db))

    def test(
        self,
        *,
        actor: User,
        connector_config: ConnectorConfig,
    ) -> ConnectionTestResult:
        connector_config_id = connector_config.id
        organization_id = connector_config.organization_id
        admin_subject_email = connector_config.admin_subject_email
        revision, generation = self._start_test(connector_config_id)
        tested_at = datetime.now(UTC)
        google_client: Any | None = None

        try:
            google_client = self.client_factory.for_organization(
                actor=actor,
                organization_id=organization_id,
                service="admin",
                version="directory_v1",
                scopes=[DIRECTORY_USER_READONLY_SCOPE],
            )
            response = (
                google_client.users()
                .get(
                    userKey=admin_subject_email,
                    projection="basic",
                    viewType="admin_view",
                    fields="id,primaryEmail,customerId",
                )
                .execute(num_retries=0)
            )
            self._validate_response(response, admin_subject_email)
            result = ConnectionTestResult(
                status="connected",
                tested_at=tested_at,
                message=(
                    "Connected. Google Admin SDK Directory API access was verified with the "
                    "configured delegated administrator."
                ),
            )
        except GoogleWorkspaceError as error:
            result = self._failure_result(error, tested_at)
        except Exception as error:
            result = self._failure_result(map_google_api_error(error), tested_at)
        finally:
            if google_client is not None:
                close = getattr(google_client, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        logger.warning(
                            "Closing Google API client failed connector_id=%s",
                            connector_config_id,
                        )

        persisted = self._persist_result(
            connector_config_id=connector_config_id,
            revision=revision,
            generation=generation,
            result=result,
        )
        if persisted:
            return result

        return ConnectionTestResult(
            status=result.status,
            tested_at=result.tested_at,
            message=(
                "The connection test completed, but its result was not saved because the "
                "connector configuration or a newer test changed while it was running."
            ),
            error_code=result.error_code,
            error_category=result.error_category,
            retryable=result.retryable,
            persisted=False,
        )

    def _start_test(self, connector_config_id: UUID) -> tuple[int, int]:
        statement = (
            update(ConnectorConfig)
            .where(ConnectorConfig.id == connector_config_id)
            .values(
                connection_test_generation=ConnectorConfig.connection_test_generation + 1,
            )
            .returning(
                ConnectorConfig.connection_config_revision,
                ConnectorConfig.connection_test_generation,
            )
        )
        row = self.db.execute(statement).one()
        self.db.commit()
        return row.connection_config_revision, row.connection_test_generation

    def _persist_result(
        self,
        *,
        connector_config_id: UUID,
        revision: int,
        generation: int,
        result: ConnectionTestResult,
    ) -> bool:
        statement = (
            update(ConnectorConfig)
            .where(
                ConnectorConfig.id == connector_config_id,
                ConnectorConfig.connection_config_revision == revision,
                ConnectorConfig.connection_test_generation == generation,
            )
            .values(
                status=result.status,
                last_tested_at=result.tested_at,
                last_error_code=result.error_code,
                last_error=result.message if result.error_code else None,
            )
            .returning(ConnectorConfig.id)
        )
        persisted_id = self.db.execute(statement).scalar_one_or_none()
        self.db.commit()
        return persisted_id is not None

    @staticmethod
    def _validate_response(response: Any, expected_subject: str | None) -> None:
        if not isinstance(response, dict):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)
        primary_email = response.get("primaryEmail")
        if (
            not isinstance(primary_email, str)
            or not expected_subject
            or primary_email.casefold() != expected_subject.casefold()
        ):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_SUBJECT_MISMATCH)

    @staticmethod
    def _failure_result(
        error: GoogleWorkspaceError,
        tested_at: datetime,
    ) -> ConnectionTestResult:
        return ConnectionTestResult(
            status="connection_failed",
            tested_at=tested_at,
            message=str(error),
            error_code=error.code.value,
            error_category=categorize_error(error.code),
            retryable=error.retryable,
        )
