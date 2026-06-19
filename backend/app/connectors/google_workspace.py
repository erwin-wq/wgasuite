from dataclasses import dataclass


@dataclass(frozen=True)
class GoogleWorkspaceConnector:
    """Placeholder for a future Google Workspace connector.

    This class intentionally stores no credentials and performs no external calls.
    """

    enabled: bool = False

    def is_available(self) -> bool:
        return self.enabled
