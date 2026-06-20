"""Future external connectors and local mock connectors."""

from app.connectors.base import BaseConnector, ConnectorFinding, ConnectorResult
from app.connectors.google_workspace_checks import (
    GOOGLE_WORKSPACE_CHECKS,
    GoogleWorkspaceCheckDefinition,
    list_google_workspace_checks,
)
from app.connectors.mock_google_workspace import MockGoogleWorkspaceConnector

__all__ = [
    "BaseConnector",
    "ConnectorFinding",
    "ConnectorResult",
    "GOOGLE_WORKSPACE_CHECKS",
    "GoogleWorkspaceCheckDefinition",
    "list_google_workspace_checks",
    "MockGoogleWorkspaceConnector",
]
