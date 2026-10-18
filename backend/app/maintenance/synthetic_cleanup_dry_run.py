from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.maintenance.synthetic_cleanup_plan import (
    build_review_manifest,
    get_database_context,
    safe_plan_summary,
    write_review_manifest,
)
from app.maintenance.synthetic_record_analysis import (
    SyntheticDataAnalysis,
    analyze_synthetic_records,
    manifest_uuid_sets,
)
from app.models import (
    Assessment,
    Asset,
    AuditEvent,
    ConnectorAccount,
    ConnectorConfig,
    Customer,
    CustomerMembership,
    DreadScore,
    Finding,
    Organization,
    ScanRun,
)

VALIDATION_DATABASE = "wgasuite_cleanup_validation"
VALIDATION_GUARD_TABLE = "wgasuite_cleanup_validation_guard"
VALIDATION_MODE = "isolated_restored_backup"
COMMITTED_TEST_DATABASE = "wgasuite_cleanup_test"
COMMITTED_TEST_VALIDATION_MODE = "isolated_committed_cleanup_test"


def _aggregate_summary(
    analysis: SyntheticDataAnalysis,
    *,
    checksum: str | None = None,
    manifest_name: str | None = None,
    cascade_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "mode": "private_cleanup_dry_run",
        "identifiers_included": False,
        "candidate_sets": len(analysis.candidates),
        "aggregate_counts": analysis.aggregate_counts(),
        "review_blockers": analysis.blocker_counts,
        "cleanup_eligibility": (
            "eligible_for_manual_review_only"
            if analysis.eligible_for_manifest
            else "refused_ambiguous_or_mixed_data"
        ),
        "safe_to_delete_now": False,
        "requires_separate_human_approval": True,
        "audit_handling": "preserve rows and detach customer references",
    }
    if checksum is not None:
        summary["manifest_sha256"] = checksum
    if manifest_name is not None:
        summary["private_manifest_file"] = manifest_name
    if cascade_validation is not None:
        summary["cascade_validation"] = cascade_validation
    return summary


def _count_ids(session: Session, model: Any, identifiers: list[Any]) -> int:
    if not identifiers:
        return 0
    return int(
        session.scalar(
            select(func.count()).select_from(model).where(model.id.in_(identifiers))
        )
        or 0
    )


def _require_isolated_validation_guard(session: Session) -> None:
    mode = os.getenv("WGASUITE_CLEANUP_VALIDATION_MODE")
    expected_databases = {
        VALIDATION_MODE: VALIDATION_DATABASE,
        COMMITTED_TEST_VALIDATION_MODE: COMMITTED_TEST_DATABASE,
    }
    if mode not in expected_databases:
        raise RuntimeError("Rollback validation requires the isolated-restored-backup mode guard.")
    if session.bind is None or session.bind.dialect.name != "postgresql":
        raise RuntimeError("Rollback validation is supported only on isolated PostgreSQL.")
    database_name = session.scalar(text("SELECT current_database()"))
    if database_name != expected_databases[mode]:
        raise RuntimeError("Rollback validation refused: unexpected database name.")

    expected_nonce = os.getenv("WGASUITE_CLEANUP_VALIDATION_NONCE", "")
    if len(expected_nonce) < 32:
        raise RuntimeError("Rollback validation refused: missing validation sentinel nonce.")
    try:
        actual_nonce = session.scalar(
            text(f"SELECT nonce FROM {VALIDATION_GUARD_TABLE} WHERE nonce = :nonce"),
            {"nonce": expected_nonce},
        )
    except Exception as exc:
        raise RuntimeError("Rollback validation refused: sentinel table is absent.") from exc
    if actual_nonce != expected_nonce:
        raise RuntimeError("Rollback validation refused: sentinel nonce mismatch.")


def validate_cascade_with_rollback(
    session: Session,
    analysis: SyntheticDataAnalysis,
) -> dict[str, Any]:
    """Exercise cascades only in a guarded restored DB and unconditionally roll them back."""
    _require_isolated_validation_guard(session)
    identifiers = manifest_uuid_sets(analysis)
    models = {
        "customers": Customer,
        "organizations": Organization,
        "connector_configs": ConnectorConfig,
        "connector_accounts": ConnectorAccount,
        "assessments": Assessment,
        "assets": Asset,
        "findings": Finding,
        "dread_scores": DreadScore,
        "scan_runs": ScanRun,
        "customer_memberships": CustomerMembership,
    }
    before_counts = {
        name: _count_ids(session, model, identifiers[name]) for name, model in models.items()
    }
    before_audit_count = _count_ids(session, AuditEvent, identifiers["audit_events"])

    validation_result: dict[str, Any]
    try:
        session.execute(
            delete(Organization).where(Organization.id.in_(identifiers["organizations"]))
        )
        session.execute(delete(Customer).where(Customer.id.in_(identifiers["customers"])))
        session.flush()

        remaining = {
            name: _count_ids(session, model, identifiers[name])
            for name, model in models.items()
        }
        audit_count = _count_ids(session, AuditEvent, identifiers["audit_events"])
        attached_audits = (
            int(
                session.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(
                        AuditEvent.id.in_(identifiers["audit_events"]),
                        AuditEvent.customer_id.is_not(None),
                    )
                )
                or 0
            )
            if identifiers["audit_events"]
            else 0
        )
        if any(remaining.values()):
            raise RuntimeError("Cascade validation found undeleted candidate records.")
        if audit_count != before_audit_count or attached_audits != 0:
            raise RuntimeError("Audit retention/detachment did not match the expected policy.")
        validation_result = {
            "database": "guarded isolated restored backup",
            "status": "passed_and_rolled_back",
            "candidate_records_temporarily_removed": sum(before_counts.values()),
            "audit_records_preserved_and_detached": audit_count,
        }
    finally:
        session.rollback()

    restored_counts = {
        name: _count_ids(session, model, identifiers[name]) for name, model in models.items()
    }
    restored_audits = _count_ids(session, AuditEvent, identifiers["audit_events"])
    session.rollback()
    if restored_counts != before_counts or restored_audits != before_audit_count:
        raise RuntimeError("Rollback validation failed to restore the original database state.")
    return validation_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a private, read-only synthetic smoke-record cleanup manifest."
    )
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        required=True,
        help="Existing or new private output directory (must have mode 0700 or stricter).",
    )
    parser.add_argument(
        "--validate-cascade-rollback",
        action="store_true",
        help=(
            "Exercise delete cascades and always roll back. Requires an isolated restored database "
            "with an explicit sentinel; it cannot run against the normal WGASuite database."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cascade_validation: dict[str, Any] | None = None
    with SessionLocal() as session:
        if args.validate_cascade_rollback:
            database_context = get_database_context(session)
            analysis = analyze_synthetic_records(session)
            if not analysis.eligible_for_manifest:
                session.rollback()
                print(json.dumps(_aggregate_summary(analysis), indent=2, sort_keys=True))
                raise SystemExit(2)
            manifest = build_review_manifest(analysis, database_context)
            session.expunge_all()
            cascade_validation = validate_cascade_with_rollback(session, analysis)
        else:
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                session.execute(text("SET TRANSACTION READ ONLY"))
            database_context = get_database_context(session)
            analysis = analyze_synthetic_records(session)
            if not analysis.eligible_for_manifest:
                print(json.dumps(_aggregate_summary(analysis), indent=2, sort_keys=True))
                session.rollback()
                raise SystemExit(2)
            manifest = build_review_manifest(analysis, database_context)
            session.expunge_all()
            session.rollback()

    manifest_path, checksum = write_review_manifest(manifest, args.manifest_dir)
    summary = safe_plan_summary(
        analysis,
        manifest,
        manifest_name=manifest_path.name,
        manifest_sha256=checksum,
    )
    if cascade_validation is not None:
        summary["cascade_validation"] = cascade_validation
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
