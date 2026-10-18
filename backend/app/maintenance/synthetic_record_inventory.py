from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.maintenance.synthetic_record_analysis import (
    SyntheticDataAnalysis,
    analyze_synthetic_records,
)


def _cleanup_eligibility(analysis: SyntheticDataAnalysis) -> str:
    counts = analysis.aggregate_counts()
    if not analysis.candidates and not (
        analysis.candidate_like_customers or analysis.candidate_like_organizations
    ):
        return "none_found"
    if counts.get("credential_bearing_connector_configs", 0) > 0:
        return "manual_review_required_credentials_present"
    if analysis.blocker_codes:
        return "manual_review_required_ambiguous_or_mixed_data"
    return "eligible_for_manual_review_only"


def build_inventory(session: Session) -> dict[str, Any]:
    """Return aggregate-only likely-synthetic record metadata without changing data."""
    analysis = analyze_synthetic_records(session)
    counts = analysis.aggregate_counts()
    associations = {
        "customer_organizations": counts.get("organizations", 0),
        "non_candidate_customer_organizations": counts.get(
            "non_candidate_customer_organizations", 0
        ),
        "connector_configs": counts.get("connector_configs", 0),
        "credential_bearing_connector_configs": counts.get(
            "credential_bearing_connector_configs", 0
        ),
        "connector_accounts": counts.get("connector_accounts", 0),
        "assessments": counts.get("assessments", 0),
        "assets": counts.get("assets", 0),
        "findings": counts.get("findings", 0),
        "dread_scores": counts.get("dread_scores", 0),
        "scan_runs": counts.get("scan_runs", 0),
        "customer_memberships": counts.get("customer_memberships", 0),
        "audit_events": counts.get("audit_events_preserved_and_detached", 0),
        "delegate_confirmations": counts.get("delegate_confirmations", 0),
        "group_membership_confirmations": counts.get(
            "group_membership_confirmations", 0
        ),
        "user_status_confirmations": counts.get("user_status_confirmations", 0),
        "cross_tenant_findings": counts.get("cross_tenant_findings", 0),
    }

    return {
        "mode": "read_only_aggregate_inventory",
        "identifiers_included": False,
        "candidate_groups": [
            {
                "record_type": "customer",
                "record_count": len(analysis.candidates),
                "reason": (
                    "Exact smoke-api fingerprint: correlated generated name and slug token, "
                    "local smoke contact, active status, and script marker."
                ),
            },
            {
                "record_type": "organization",
                "record_count": len(analysis.candidates),
                "reason": (
                    "Exact smoke-api organization token and marker, linked to its matching "
                    "customer."
                ),
            },
        ],
        "candidate_like_records": {
            "customers": analysis.candidate_like_customers,
            "organizations": analysis.candidate_like_organizations,
        },
        "associated_data": associations,
        "review_blockers": analysis.blocker_counts,
        "deletion_impact": [
            (
                "A separately approved cleanup would explicitly delete candidate organizations, "
                "cascading to assessments, assets, connector accounts, connector configs, and "
                "Google mutation confirmations."
            ),
            "Assessment deletion would cascade to findings, DREAD scores, and scan runs.",
            (
                "Customer deletion would remove memberships. Candidate organizations must be "
                "deleted explicitly because the customer foreign key otherwise detaches them."
            ),
            (
                "Audit events would be preserved; their customer references would be detached by "
                "the database foreign key."
            ),
            (
                "Credential-bearing connector records require credential-store reconciliation "
                "and are never auto-approved."
            ),
        ],
        "cleanup_eligibility": _cleanup_eligibility(analysis),
        "safe_to_delete_now": False,
        "required_next_step": (
            "Privately review a current exact plan, verified recovery evidence, and audit impact; "
            "separate human approval remains required before guarded execution."
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
