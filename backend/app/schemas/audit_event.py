import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    actor_email: str | None
    actor_role: str | None
    customer_id: uuid.UUID | None
    action: str
    object_type: str
    object_id: str | None
    outcome: str
    reason: str | None
    metadata_json: dict[str, Any] | None
