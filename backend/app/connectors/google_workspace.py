"""Public Google Workspace connector foundation exports.

No API operation or connection test is implemented here. Feature services request explicitly
scoped clients from ``GoogleWorkspaceClientFactory`` when their own work is implemented.
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
