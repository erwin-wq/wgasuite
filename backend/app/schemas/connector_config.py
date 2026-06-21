import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConnectorType = Literal["google_workspace"]
ConnectorAuthMethod = Literal[
    "service_account_domain_wide_delegation",
    "oauth_admin_consent",
    "manual_import",
]
ConnectorStatus = Literal[
    "not_configured",
    "configured",
    "connected",
    "connection_failed",
]


class ConnectorConfigCreate(BaseModel):
    display_name: str = Field(default="Google Workspace", min_length=1, max_length=255)
    primary_domain: str | None = Field(default=None, max_length=255)
    admin_subject_email: str | None = Field(default=None, max_length=255)
    auth_method: ConnectorAuthMethod = "service_account_domain_wide_delegation"
    status: ConnectorStatus = "configured"
    notes: str | None = None


class ConnectorConfigUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    primary_domain: str | None = Field(default=None, max_length=255)
    admin_subject_email: str | None = Field(default=None, max_length=255)
    auth_method: ConnectorAuthMethod | None = None
    status: ConnectorStatus | None = None
    notes: str | None = None


class ConnectorConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    connector_type: ConnectorType
    auth_method: ConnectorAuthMethod
    status: ConnectorStatus
    display_name: str
    primary_domain: str | None
    admin_subject_email: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    last_tested_at: datetime | None
    last_error: str | None


class ConnectorConfigTestRead(BaseModel):
    status: Literal["not_implemented"]
    message: str
    recommended_next_step: str
