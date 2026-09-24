from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from google.oauth2 import service_account
from google.oauth2.service_account import Credentials

from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
)
from app.models import ConnectorConfig

CREDENTIAL_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ADMIN_SUBJECT_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$"
)
REQUIRED_SERVICE_ACCOUNT_FIELDS = {
    "type",
    "project_id",
    "private_key_id",
    "private_key",
    "client_email",
    "token_uri",
}


class CredentialProvider(Protocol):
    name: str

    def load_service_account_info(
        self,
        *,
        organization_id: UUID,
        credential_ref: str,
    ) -> Mapping[str, Any]: ...


class FileCredentialProvider:
    """Load tenant-partitioned service-account JSON from a read-only secret directory."""

    name = "file"

    def __init__(self, root_directory: Path) -> None:
        self.root_directory = root_directory.resolve()

    def load_service_account_info(
        self,
        *,
        organization_id: UUID,
        credential_ref: str,
    ) -> Mapping[str, Any]:
        if not CREDENTIAL_REFERENCE_PATTERN.fullmatch(credential_ref):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.INVALID_CREDENTIALS)

        filename = credential_ref if credential_ref.endswith(".json") else f"{credential_ref}.json"
        organization_directory = self.root_directory / str(organization_id)
        unresolved_path = organization_directory / filename
        if organization_directory.is_symlink() or unresolved_path.is_symlink():
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.INVALID_CREDENTIALS)
        credential_path = unresolved_path.resolve()
        expected_parent = organization_directory.resolve()
        if credential_path.parent != expected_parent:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.INVALID_CREDENTIALS)

        try:
            if credential_path.stat().st_size > 1_048_576:
                raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.INVALID_CREDENTIALS)
            raw_content = credential_path.read_text(encoding="utf-8")
        except (FileNotFoundError, IsADirectoryError):
            raise GoogleWorkspaceError(
                GoogleWorkspaceErrorCode.CREDENTIALS_NOT_FOUND
            ) from None
        except OSError:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.INVALID_CREDENTIALS) from None

        try:
            credential_info = json.loads(raw_content)
        except (json.JSONDecodeError, UnicodeError):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.INVALID_CREDENTIALS) from None

        if not isinstance(credential_info, dict):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.INVALID_CREDENTIALS)
        if credential_info.get("type") != "service_account":
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.INVALID_CREDENTIALS)
        if any(
            not isinstance(credential_info.get(field), str) or not credential_info[field].strip()
            for field in REQUIRED_SERVICE_ACCOUNT_FIELDS
        ):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.INVALID_CREDENTIALS)

        return credential_info


class CredentialProviderRegistry:
    def __init__(self, providers: Sequence[CredentialProvider]) -> None:
        self._providers = {provider.name: provider for provider in providers}

    def get(self, name: str) -> CredentialProvider:
        provider = self._providers.get(name)
        if provider is None:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED)
        return provider


def normalize_scopes(scopes: Sequence[str]) -> tuple[str, ...]:
    if isinstance(scopes, str):
        raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION)
    normalized: list[str] = []
    seen: set[str] = set()
    for scope in scopes:
        if not isinstance(scope, str):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION)
        value = scope.strip()
        if value and value not in seen:
            normalized.append(value)
            seen.add(value)
    if not normalized:
        raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION)
    return tuple(normalized)


def is_valid_admin_subject(value: str | None) -> bool:
    if value is None or len(value) > 255 or not ADMIN_SUBJECT_PATTERN.fullmatch(value):
        return False
    local_part, domain = value.rsplit("@", maxsplit=1)
    return bool(local_part and "." in domain and ".." not in domain)


class DelegatedCredentialFactory:
    def __init__(self, providers: CredentialProviderRegistry) -> None:
        self.providers = providers

    def create(
        self,
        connector_config: ConnectorConfig,
        scopes: Sequence[str],
    ) -> tuple[Credentials, tuple[str, ...]]:
        normalized_scopes = normalize_scopes(scopes)
        if (
            connector_config.auth_method != "service_account_domain_wide_delegation"
            or not connector_config.credential_provider
            or not connector_config.credential_ref
        ):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED)
        if not is_valid_admin_subject(connector_config.admin_subject_email):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.INVALID_ADMIN_SUBJECT)

        provider = self.providers.get(connector_config.credential_provider)
        credential_info = provider.load_service_account_info(
            organization_id=connector_config.organization_id,
            credential_ref=connector_config.credential_ref,
        )
        try:
            credentials = service_account.Credentials.from_service_account_info(
                dict(credential_info),
                scopes=normalized_scopes,
            )
        except (TypeError, ValueError):
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.INVALID_CREDENTIALS) from None

        try:
            delegated_credentials = credentials.with_subject(connector_config.admin_subject_email)
        except Exception:
            raise GoogleWorkspaceError(GoogleWorkspaceErrorCode.DELEGATION_FAILED) from None

        return delegated_credentials, normalized_scopes
