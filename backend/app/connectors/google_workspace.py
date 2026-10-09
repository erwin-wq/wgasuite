"""Public Google Workspace authentication and client-foundation exports.

The connection-test service requests its exact read-only scope through this foundation. Future
features must continue to request their own explicitly scoped clients.
"""

from app.connectors.google_workspace_client import GoogleWorkspaceClientFactory
from app.connectors.google_workspace_credentials import (
    CredentialProvider,
    CredentialProviderRegistry,
    DelegatedCredentialFactory,
    FileCredentialProvider,
    normalize_scopes,
)
from app.connectors.google_workspace_errors import (
    GoogleWorkspaceError,
    GoogleWorkspaceErrorCode,
    map_google_api_error,
)

__all__ = [
    "CredentialProvider",
    "CredentialProviderRegistry",
    "DelegatedCredentialFactory",
    "FileCredentialProvider",
    "GoogleWorkspaceClientFactory",
    "GoogleWorkspaceError",
    "GoogleWorkspaceErrorCode",
    "map_google_api_error",
    "normalize_scopes",
]
