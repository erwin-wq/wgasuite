from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from sqlalchemy.orm import Session

from app.connectors.google_workspace_credentials import (
    REQUIRED_SERVICE_ACCOUNT_FIELDS,
    FileCredentialProvider,
)
from app.connectors.google_workspace_errors import GoogleWorkspaceError
from app.models import ConnectorConfig
from app.services.google_workspace_connection import (
    DIRECTORY_USER_READONLY_SCOPE,
    invalidate_connection_result,
)

MANAGED_CREDENTIAL_REFERENCE = "service-account"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
SERVICE_ACCOUNT_EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.iam\.gserviceaccount\.com$", re.IGNORECASE
)
NUMERIC_CLIENT_ID_PATTERN = re.compile(r"^[0-9]{6,255}$")


class CredentialImportError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ServiceAccountMetadata:
    email: str
    client_id: str


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CredentialImportError(
                "invalid_json", "The credential JSON contains duplicate fields."
            )
        result[key] = value
    return result


def validate_service_account_json(
    raw_content: bytes,
) -> tuple[dict[str, Any], ServiceAccountMetadata]:
    try:
        parsed = json.loads(raw_content.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except CredentialImportError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CredentialImportError(
            "invalid_json", "Upload a valid UTF-8 JSON service-account key file."
        ) from None

    if not isinstance(parsed, dict):
        raise CredentialImportError(
            "invalid_json", "The credential file must contain one JSON object."
        )
    if parsed.get("type") != "service_account":
        raise CredentialImportError(
            "invalid_credential_type", "The JSON file is not a Google service-account key."
        )

    required_fields = REQUIRED_SERVICE_ACCOUNT_FIELDS | {"client_id"}
    missing = sorted(
        field
        for field in required_fields
        if not isinstance(parsed.get(field), str) or not parsed[field].strip()
    )
    if missing:
        raise CredentialImportError(
            "missing_required_fields",
            "The service-account key is missing required Google fields.",
        )

    email = parsed["client_email"].strip()
    client_id = parsed["client_id"].strip()
    if not SERVICE_ACCOUNT_EMAIL_PATTERN.fullmatch(email):
        raise CredentialImportError(
            "invalid_service_account_email",
            "The service-account email in the credential file is invalid.",
        )
    if not NUMERIC_CLIENT_ID_PATTERN.fullmatch(client_id):
        raise CredentialImportError(
            "invalid_client_id", "The service-account client ID must be numeric."
        )
    if parsed["token_uri"].strip() != GOOGLE_TOKEN_URI:
        raise CredentialImportError(
            "invalid_token_uri", "The credential file does not use Google's trusted token endpoint."
        )

    try:
        service_account.Credentials.from_service_account_info(
            parsed,
            scopes=(DIRECTORY_USER_READONLY_SCOPE,),
        )
    except (TypeError, ValueError):
        raise CredentialImportError(
            "invalid_private_key", "The service-account private key is invalid."
        ) from None

    return parsed, ServiceAccountMetadata(email=email, client_id=client_id)


class ManagedCredentialStore:
    """Atomically persist one private credential file per organization."""

    def __init__(self, root_directory: Path) -> None:
        self.root_directory = root_directory

    def store(self, organization_id: object, credential_info: dict[str, Any]) -> None:
        self._prepare_directory(self.root_directory)
        organization_directory = self.root_directory / str(organization_id)
        self._prepare_directory(organization_directory)
        if organization_directory.resolve().parent != self.root_directory.resolve():
            raise CredentialImportError("storage_error", "Credential storage is unavailable.")

        destination_name = f"{MANAGED_CREDENTIAL_REFERENCE}.json"
        temporary_name = f".credential-{secrets.token_hex(16)}.tmp"
        payload = json.dumps(credential_info, separators=(",", ":"), sort_keys=True).encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        directory_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            directory_flags |= os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
            directory_flags |= os.O_NOFOLLOW

        descriptor: int | None = None
        directory_descriptor: int | None = None
        try:
            directory_descriptor = os.open(organization_directory, directory_flags)
            descriptor = os.open(
                temporary_name,
                flags,
                0o600,
                dir_fd=directory_descriptor,
            )
            with os.fdopen(descriptor, "wb", closefd=True) as credential_file:
                descriptor = None
                credential_file.write(payload)
                credential_file.flush()
                os.fsync(credential_file.fileno())
            os.replace(
                temporary_name,
                destination_name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
            )
            os.fsync(directory_descriptor)
        except OSError:
            raise CredentialImportError(
                "storage_error", "The credential could not be saved securely."
            ) from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if directory_descriptor is not None:
                try:
                    os.unlink(temporary_name, dir_fd=directory_descriptor)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
                os.close(directory_descriptor)

    @staticmethod
    def _prepare_directory(directory: Path) -> None:
        try:
            if directory.is_symlink():
                raise CredentialImportError(
                    "storage_error", "Credential storage is unavailable."
                )
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(directory, 0o700)
        except OSError:
            raise CredentialImportError(
                "storage_error", "Credential storage is unavailable."
            ) from None


class GoogleWorkspaceCredentialImporter:
    def __init__(
        self,
        db: Session,
        managed_store: ManagedCredentialStore,
        external_provider: FileCredentialProvider,
    ) -> None:
        self.db = db
        self.managed_store = managed_store
        self.external_provider = external_provider

    def import_managed(
        self, connector_config: ConnectorConfig, raw_content: bytes
    ) -> ServiceAccountMetadata:
        credential_info, metadata = validate_service_account_json(raw_content)

        # Invalidate any prior verification before the underlying secret can change.
        invalidate_connection_result(connector_config)
        connector_config.service_account_email = None
        connector_config.service_account_client_id = None
        self.db.add(connector_config)
        self.db.commit()

        self.managed_store.store(connector_config.organization_id, credential_info)
        connector_config.credential_provider = "managed_file"
        connector_config.credential_ref = MANAGED_CREDENTIAL_REFERENCE
        connector_config.service_account_email = metadata.email
        connector_config.service_account_client_id = metadata.client_id
        invalidate_connection_result(connector_config)
        self.db.add(connector_config)
        self.db.commit()
        self.db.refresh(connector_config)
        return metadata

    def select_external(
        self, connector_config: ConnectorConfig, credential_ref: str
    ) -> ServiceAccountMetadata:
        try:
            credential_info = self.external_provider.load_service_account_info(
                organization_id=connector_config.organization_id,
                credential_ref=credential_ref,
            )
        except GoogleWorkspaceError:
            raise CredentialImportError(
                "external_credential_unavailable",
                "The provisioned credential reference is missing or invalid.",
            ) from None

        raw_content = json.dumps(dict(credential_info)).encode("utf-8")
        _, metadata = validate_service_account_json(raw_content)
        connector_config.credential_provider = "file"
        connector_config.credential_ref = credential_ref
        connector_config.service_account_email = metadata.email
        connector_config.service_account_client_id = metadata.client_id
        invalidate_connection_result(connector_config)
        self.db.add(connector_config)
        self.db.commit()
        self.db.refresh(connector_config)
        return metadata
