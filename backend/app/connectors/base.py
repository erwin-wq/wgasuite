from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ConnectorFinding:
    check_id: str
    title: str
    description: str
    impact: str
    recommendation: str
    category: str
    dread_score: dict[str, int]


@dataclass(frozen=True)
class ConnectorResult:
    connector_type: str
    summary: str
    findings: list[ConnectorFinding]


class BaseConnector(Protocol):
    connector_type: str

    def run(self) -> ConnectorResult:
        """Run the connector and return normalized findings."""
        ...
