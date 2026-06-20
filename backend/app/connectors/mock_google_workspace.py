from app.connectors.base import ConnectorFinding, ConnectorResult
from app.connectors.google_workspace_checks import list_google_workspace_checks


class MockGoogleWorkspaceConnector:
    connector_type = "google_workspace_mock"

    def run(self) -> ConnectorResult:
        findings = [
            ConnectorFinding(
                check_id=check.check_id,
                title=check.maps_to_finding_title,
                description=check.description,
                impact=check.risk_statement,
                recommendation=check.recommendation,
                category=check.category,
                dread_score=check.default_dread_score,
            )
            for check in list_google_workspace_checks()
        ]
        return ConnectorResult(
            connector_type=self.connector_type,
            summary=(
                "Mock Google Workspace scan completed. Demo findings were created from "
                "the Google Workspace check catalog; no real Google data was accessed."
            ),
            findings=findings,
        )
