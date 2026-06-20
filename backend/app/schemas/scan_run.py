import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

ScanRunStatus = Literal["pending", "running", "completed", "failed"]
ScanConnectorType = Literal["google_workspace_mock"]


class ScanRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assessment_id: uuid.UUID
    connector_type: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    findings_created: int
    summary: str | None
    raw_result_json: dict[str, Any] | None
