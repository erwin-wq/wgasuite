"""Future external connectors and local mock connectors."""

from app.connectors.base import BaseConnector, ConnectorFinding, ConnectorResult
from app.connectors.mock_google_workspace import MockGoogleWorkspaceConnector

__all__ = [
    "BaseConnector",
    "ConnectorFinding",
    "ConnectorResult",
    "MockGoogleWorkspaceConnector",
]
