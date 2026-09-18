import uuid
from datetime import datetime

from pydantic import BaseModel


class PlatformAdminTotals(BaseModel):
    customers_count: int
    organizations_count: int
    assessments_count: int
    connector_configs_count: int
    scan_runs_count: int
    audit_events_count: int


class PlatformAdminCustomerSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    organization_count: int
    connector_config_count: int
    last_scan_run_at: datetime | None
    last_audit_event_at: datetime | None


class PlatformAdminConnectorSummary(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID | None
    customer_name: str | None
    organization_id: uuid.UUID
    organization_name: str
    connector_type: str
    status: str
    auth_method: str
    primary_domain: str | None
    last_tested_at: datetime | None
    last_error: str | None


class PlatformAdminScanRunSummary(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID | None
    customer_name: str | None
    organization_id: uuid.UUID
    organization_name: str
    assessment_id: uuid.UUID
    assessment_title: str
    connector_type: str
    status: str
    findings_created: int
    started_at: datetime
    completed_at: datetime | None
    summary: str | None


class PlatformAdminAuditEventSummary(BaseModel):
    id: uuid.UUID
    created_at: datetime
    actor_email: str | None
    actor_role: str | None
    customer_id: uuid.UUID | None
    customer_name: str | None
    action: str
    object_type: str
    object_id: str | None
    outcome: str


class PlatformAdminOverview(BaseModel):
    totals: PlatformAdminTotals
    customers: list[PlatformAdminCustomerSummary]
    connector_configs: list[PlatformAdminConnectorSummary]
    recent_scan_runs: list[PlatformAdminScanRunSummary]
    recent_audit_events: list[PlatformAdminAuditEventSummary]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "totals": {
                        "customers_count": 1,
                        "organizations_count": 1,
                        "assessments_count": 1,
                        "connector_configs_count": 1,
                        "scan_runs_count": 1,
                        "audit_events_count": 1,
                    },
                    "customers": [],
                    "connector_configs": [],
                    "recent_scan_runs": [],
                    "recent_audit_events": [],
                }
            ]
        }
    }
