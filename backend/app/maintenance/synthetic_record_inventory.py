from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Select, and_, func, not_, select, text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import (
    Assessment,
    Asset,
    AuditEvent,
    ConnectorAccount,
    ConnectorConfig,
    Customer,
    CustomerMembership,
    Finding,
    Organization,
    ScanRun,
)

SMOKE_MARKER = "Created by scripts/dev/smoke_api.sh"


def _customer_fingerprint() -> Any:
    return and_(
        Customer.name.like("Smoke Customer %"),
        Customer.slug.like("smoke-customer-%"),
        Customer.contact_name == "Smoke Tester",
        Customer.contact_email == "smoke@example.local",
        Customer.notes == SMOKE_MARKER,
    )


def _organization_fingerprint() -> Any:
    return and_(
        Organization.name.like("Smoke Test Org %"),
        Organization.description == SMOKE_MARKER,
    )


def _count(session: Session, statement: Select[Any]) -> int:
    return int(session.scalar(statement) or 0)


def build_inventory(session: Session) -> dict[str, Any]:
    """Return aggregate-only likely-synthetic record metadata without changing data."""
    customer_ids = select(Customer.id).where(_customer_fingerprint())
    organization_ids = select(Organization.id).where(_organization_fingerprint())
    assessment_ids = select(Assessment.id).where(Assessment.organization_id.in_(organization_ids))

    customer_count = _count(
        session,
        select(func.count()).select_from(Customer).where(_customer_fingerprint()),
    )
    organization_count = _count(
        session,
        select(func.count()).select_from(Organization).where(_organization_fingerprint()),
    )
    customer_organization_count = _count(
        session,
        select(func.count())
        .select_from(Organization)
        .where(Organization.customer_id.in_(customer_ids)),
    )
    non_candidate_customer_organizations = _count(
        session,
        select(func.count())
        .select_from(Organization)
        .where(
            Organization.customer_id.in_(customer_ids),
            not_(_organization_fingerprint()),
        ),
    )
    connector_configs = _count(
        session,
        select(func.count())
        .select_from(ConnectorConfig)
        .where(ConnectorConfig.organization_id.in_(organization_ids)),
    )
    credential_bearing_connectors = _count(
        session,
        select(func.count())
        .select_from(ConnectorConfig)
        .where(
            ConnectorConfig.organization_id.in_(organization_ids),
            ConnectorConfig.credential_ref.is_not(None),
        ),
    )
    assessments = _count(
        session,
        select(func.count())
        .select_from(Assessment)
        .where(Assessment.organization_id.in_(organization_ids)),
    )
    assets = _count(
        session,
        select(func.count()).select_from(Asset).where(Asset.organization_id.in_(organization_ids)),
    )
    connector_accounts = _count(
        session,
        select(func.count())
        .select_from(ConnectorAccount)
        .where(ConnectorAccount.organization_id.in_(organization_ids)),
    )
    findings = _count(
        session,
        select(func.count()).select_from(Finding).where(Finding.assessment_id.in_(assessment_ids)),
    )
    scan_runs = _count(
        session,
        select(func.count()).select_from(ScanRun).where(ScanRun.assessment_id.in_(assessment_ids)),
    )
    memberships = _count(
        session,
        select(func.count())
        .select_from(CustomerMembership)
        .where(CustomerMembership.customer_id.in_(customer_ids)),
    )
    audit_events = _count(
        session,
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.customer_id.in_(customer_ids)),
    )

    if customer_count == 0 and organization_count == 0:
        cleanup_eligibility = "none_found"
    elif credential_bearing_connectors > 0:
        cleanup_eligibility = "manual_review_required_credentials_present"
    elif non_candidate_customer_organizations > 0:
        cleanup_eligibility = "manual_review_required_mixed_customer_data"
    else:
        cleanup_eligibility = "eligible_for_manual_review_only"

    associations = {
        "customer_organizations": customer_organization_count,
        "non_candidate_customer_organizations": non_candidate_customer_organizations,
        "connector_configs": connector_configs,
        "credential_bearing_connector_configs": credential_bearing_connectors,
        "connector_accounts": connector_accounts,
        "assessments": assessments,
        "assets": assets,
        "findings": findings,
        "scan_runs": scan_runs,
        "customer_memberships": memberships,
        "audit_events": audit_events,
    }

    return {
        "mode": "read_only_aggregate_inventory",
        "identifiers_included": False,
        "candidate_groups": [
            {
                "record_type": "customer",
                "record_count": customer_count,
                "reason": (
                    "Exact smoke-api fingerprint: generated name and slug patterns, local smoke "
                    "contact, and the script marker."
                ),
            },
            {
                "record_type": "organization",
                "record_count": organization_count,
                "reason": "Exact smoke-api organization name pattern and script marker.",
            },
        ],
        "associated_data": associations,
        "deletion_impact": [
            (
                "Organization deletion would cascade to assessments, assets, connector accounts, "
                "and connector configs."
            ),
            "Assessment deletion would cascade to findings, DREAD scores, and scan runs.",
            (
                "Customer deletion would remove memberships, detach organizations, and detach "
                "audit-event customer references."
            ),
            (
                "Credential-bearing connector records require credential-store reconciliation "
                "and are never auto-approved."
            ),
        ],
        "cleanup_eligibility": cleanup_eligibility,
        "safe_to_delete_now": False,
        "required_next_step": (
            "Backup, inspect candidates privately, dry-run, and obtain explicit approval."
        ),
    }


def main() -> None:
    with SessionLocal() as session:
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            session.execute(text("SET TRANSACTION READ ONLY"))
        report = build_inventory(session)
        session.rollback()
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
