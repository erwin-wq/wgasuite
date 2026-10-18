from __future__ import annotations

import argparse
import hmac
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.maintenance.synthetic_cleanup_plan import (
    MAX_PRIVATE_JSON_BYTES,
    CleanupPlanError,
    analysis_matches_plan,
    get_database_context,
    load_review_manifest,
    manifest_audit_expectations,
    manifest_customer_ids,
    manifest_organization_ids,
    manifest_record_ids,
    require_private_file,
    sha256_bytes,
    sha256_file,
)
from app.maintenance.synthetic_record_analysis import (
    analyze_synthetic_records,
    audit_event_content_digest,
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
    GoogleWorkspaceDelegateConfirmation,
    GoogleWorkspaceGroupMembershipConfirmation,
    GoogleWorkspaceUserStatusConfirmation,
    Organization,
    ScanRun,
)

APPROVAL_SCHEMA_VERSION = 1
BACKUP_ATTESTATION_SCHEMA_VERSION = 1
APPROVAL_TTL = timedelta(minutes=15)
MAX_BACKUP_AGE = timedelta(hours=24)
EXECUTION_ADVISORY_LOCK_KEY = 6_235_510_021_001
COMMIT_AUDIT_ACTION = "maintenance.synthetic_cleanup.committed"
COMMIT_AUDIT_OBJECT_TYPE = "synthetic_cleanup_plan"

MODEL_BY_RECORD_KEY: dict[str, Any] = {
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
    "delegate_confirmations": GoogleWorkspaceDelegateConfirmation,
    "group_membership_confirmations": GoogleWorkspaceGroupMembershipConfirmation,
    "user_status_confirmations": GoogleWorkspaceUserStatusConfirmation,
}


class CleanupExecutionError(RuntimeError):
    """A guarded cleanup precondition failed before a known commit."""


class CleanupCommitOutcomeUnknown(RuntimeError):
    """The commit response was uncertain and must be reconciled without retrying."""


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise CleanupExecutionError(f"{field} must be an ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CleanupExecutionError(f"{field} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise CleanupExecutionError(f"{field} must include a timezone.")
    return parsed.astimezone(UTC)


def _non_sensitive_reference(value: Any, field: str, *, max_length: int = 160) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > max_length
        or not value.isprintable()
    ):
        raise CleanupExecutionError(
            f"{field} must be a short, printable, non-sensitive reference."
        )
    return value


def _load_private_json(path: Path, expected_sha256: str) -> dict[str, Any]:
    resolved = require_private_file(path, max_bytes=MAX_PRIVATE_JSON_BYTES)
    payload = resolved.read_bytes()
    if not hmac.compare_digest(sha256_bytes(payload), expected_sha256.lower()):
        raise CleanupExecutionError("Private artifact SHA-256 does not match.")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise CleanupExecutionError("Private artifact is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise CleanupExecutionError("Private artifact must contain a JSON object.")
    return value


def _uuid_strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise CleanupExecutionError(f"{field} must be a non-empty UUID list.")
    try:
        normalized = [str(UUID(item)) for item in value]
    except (AttributeError, TypeError, ValueError) as exc:
        raise CleanupExecutionError(f"{field} contains an invalid UUID.") from exc
    if len(set(normalized)) != len(normalized):
        raise CleanupExecutionError(f"{field} contains duplicate UUIDs.")
    return normalized


def validate_approval(
    approval: dict[str, Any],
    manifest: dict[str, Any],
    manifest_sha256: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    if approval.get("schema_version") != APPROVAL_SCHEMA_VERSION or approval.get(
        "mode"
    ) != "synthetic_cleanup_human_approval":
        raise CleanupExecutionError("Unsupported cleanup approval artifact.")
    if approval.get("plan_digest") != manifest["plan_digest"] or approval.get(
        "manifest_sha256"
    ) != manifest_sha256.lower():
        raise CleanupExecutionError("Human approval is not bound to this exact manifest.")
    expected_customers = manifest_customer_ids(manifest)
    expected_organizations = manifest_organization_ids(manifest)
    if _uuid_strings(approval.get("approved_customer_ids"), "approved_customer_ids") != (
        expected_customers
    ):
        raise CleanupExecutionError("Human approval does not repeat the exact customer UUIDs.")
    if _uuid_strings(
        approval.get("approved_organization_ids"), "approved_organization_ids"
    ) != expected_organizations:
        raise CleanupExecutionError(
            "Human approval does not repeat the exact organization UUIDs."
        )
    approved_by = approval.get("approved_by")
    if not isinstance(approved_by, str) or not approved_by.strip():
        raise CleanupExecutionError("Human approval must identify its approver.")
    _non_sensitive_reference(approval.get("approval_reference"), "approval_reference")
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    approved_at = _timestamp(approval.get("approved_at"), "approved_at")
    expires_at = _timestamp(approval.get("expires_at"), "approval expires_at")
    plan_generated_at = _timestamp(manifest["plan"]["generated_at"], "generated_at")
    plan_expires_at = _timestamp(manifest["plan"]["expires_at"], "expires_at")
    if approved_at < plan_generated_at or approved_at > current_time + timedelta(minutes=1):
        raise CleanupExecutionError("Human approval timestamp is outside the valid review window.")
    if (
        expires_at <= approved_at
        or expires_at - approved_at > APPROVAL_TTL
        or current_time >= expires_at
        or expires_at > plan_expires_at
    ):
        raise CleanupExecutionError("Human approval is expired or has an invalid lifetime.")
    return approval


def _validate_backup_entry(
    entry: Any,
    field: str,
    *,
    now: datetime,
    require_restore: bool,
) -> None:
    if not isinstance(entry, dict):
        raise CleanupExecutionError(f"{field} backup attestation is missing.")
    path_value = entry.get("path")
    checksum = entry.get("sha256")
    if not isinstance(path_value, str) or not Path(path_value).is_absolute():
        raise CleanupExecutionError(f"{field} backup path must be absolute.")
    if not isinstance(checksum, str) or len(checksum) != 64:
        raise CleanupExecutionError(f"{field} backup SHA-256 is invalid.")
    path = require_private_file(Path(path_value))
    if not hmac.compare_digest(sha256_file(path), checksum.lower()):
        raise CleanupExecutionError(f"{field} backup content does not match its SHA-256.")
    created_at = _timestamp(entry.get("created_at"), f"{field}.created_at")
    if created_at > now + timedelta(minutes=1) or now - created_at > MAX_BACKUP_AGE:
        raise CleanupExecutionError(f"{field} backup is future-dated or too old.")
    verification_field = "restore_verified_at" if require_restore else "recovery_verified_at"
    verified_at = _timestamp(entry.get(verification_field), f"{field}.{verification_field}")
    if verified_at < created_at or verified_at > now + timedelta(minutes=1):
        raise CleanupExecutionError(f"{field} backup verification timestamp is invalid.")
    _non_sensitive_reference(
        entry.get("verification_reference"), f"{field}.verification_reference"
    )


def validate_backup_attestation(
    attestation: dict[str, Any],
    manifest: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    if attestation.get("schema_version") != BACKUP_ATTESTATION_SCHEMA_VERSION or attestation.get(
        "mode"
    ) != "synthetic_cleanup_backup_attestation":
        raise CleanupExecutionError("Unsupported backup attestation artifact.")
    if attestation.get("plan_digest") != manifest["plan_digest"] or attestation.get(
        "database_context_sha256"
    ) != manifest["plan"]["database_context_sha256"]:
        raise CleanupExecutionError("Backup attestation is not bound to this cleanup plan.")
    _non_sensitive_reference(attestation.get("backup_set_id"), "backup_set_id")
    if not isinstance(attestation.get("attested_by"), str) or not attestation[
        "attested_by"
    ].strip():
        raise CleanupExecutionError("Backup attestation requires attested_by.")
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    attested_at = _timestamp(attestation.get("attested_at"), "attested_at")
    plan_generated_at = _timestamp(manifest["plan"]["generated_at"], "generated_at")
    if attested_at < plan_generated_at or attested_at > current_time + timedelta(minutes=1):
        raise CleanupExecutionError("Backup attestation timestamp is outside the review window.")
    _validate_backup_entry(
        attestation.get("database_backup"),
        "database",
        now=current_time,
        require_restore=True,
    )
    _validate_backup_entry(
        attestation.get("credential_backup"),
        "credential",
        now=current_time,
        require_restore=False,
    )
    cascade_validation = attestation.get("cascade_validation")
    if not isinstance(cascade_validation, dict) or cascade_validation.get(
        "status"
    ) != "passed_and_rolled_back":
        raise CleanupExecutionError(
            "Backup attestation requires passed rollback-only cascade validation."
        )
    cascade_verified_at = _timestamp(
        cascade_validation.get("verified_at"), "cascade_validation.verified_at"
    )
    if cascade_verified_at > current_time + timedelta(minutes=1):
        raise CleanupExecutionError("Cascade validation timestamp is future-dated.")
    impact = manifest["plan"]["impact_counts"]
    if cascade_validation.get("records_temporarily_removed") != impact.get(
        "records_expected_to_be_deleted"
    ) or cascade_validation.get("audit_events_preserved_and_detached") != impact.get(
        "audit_events_expected_to_be_preserved_and_detached"
    ):
        raise CleanupExecutionError("Cascade validation impact does not match the cleanup plan.")
    _non_sensitive_reference(
        cascade_validation.get("verification_reference"),
        "cascade_validation.verification_reference",
    )
    return attestation


def _assert_distinct_artifacts(paths: list[Path]) -> None:
    try:
        resolved = [path.resolve(strict=True) for path in paths]
        file_identities = [(path.stat().st_dev, path.stat().st_ino) for path in resolved]
    except OSError as exc:
        raise CleanupExecutionError("A required private artifact is unavailable.") from exc
    if len(set(resolved)) != len(resolved) or len(set(file_identities)) != len(
        file_identities
    ):
        raise CleanupExecutionError(
            "Manifest, approval, and backup artifacts must be distinct files."
        )


def _require_exact_cli_selections(
    manifest: dict[str, Any], customer_ids: list[str], organization_ids: list[str]
) -> None:
    if customer_ids != manifest_customer_ids(manifest):
        raise CleanupExecutionError("CLI customer selections do not exactly match the plan.")
    if organization_ids != manifest_organization_ids(manifest):
        raise CleanupExecutionError("CLI organization selections do not exactly match the plan.")


def require_exact_confirmation(manifest: dict[str, Any], confirmation: str) -> None:
    if not hmac.compare_digest(confirmation, manifest["required_confirmation"]):
        raise CleanupExecutionError("Typed cleanup confirmation is not exact.")


def require_matching_database_context(
    manifest: dict[str, Any], current_context: dict[str, str]
) -> None:
    if current_context != manifest["plan"]["database_context"]:
        raise CleanupExecutionError("Cleanup plan targets a different database identity.")


def _count_ids(session: Session, model: Any, identifiers: list[str]) -> int:
    if not identifiers:
        return 0
    return int(
        session.scalar(
            select(func.count()).select_from(model).where(model.id.in_(identifiers))
        )
        or 0
    )


def _lock_exact_rows(
    session: Session, identifiers: dict[str, list[str]], audit_ids: list[str]
) -> None:
    lock_order = (
        "customers",
        "organizations",
        "connector_configs",
        "connector_accounts",
        "assessments",
        "assets",
        "findings",
        "dread_scores",
        "scan_runs",
        "customer_memberships",
        "delegate_confirmations",
        "group_membership_confirmations",
        "user_status_confirmations",
    )
    for key in lock_order:
        expected = identifiers[key]
        if not expected:
            continue
        model = MODEL_BY_RECORD_KEY[key]
        locked = session.scalars(
            select(model.id)
            .where(model.id.in_(expected))
            .order_by(model.id)
            .with_for_update(nowait=True)
        ).all()
        if {str(item) for item in locked} != set(expected):
            raise CleanupExecutionError(f"Cleanup plan {key} rows changed before locking.")
    if audit_ids:
        locked_audits = session.scalars(
            select(AuditEvent.id)
            .where(AuditEvent.id.in_(audit_ids))
            .order_by(AuditEvent.id)
            .with_for_update(nowait=True)
        ).all()
        if {str(item) for item in locked_audits} != set(audit_ids):
            raise CleanupExecutionError("Cleanup plan audit rows changed before locking.")


def _existing_commit_marker(session: Session, plan_digest: str) -> bool:
    return bool(
        session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action == COMMIT_AUDIT_ACTION,
                AuditEvent.object_type == COMMIT_AUDIT_OBJECT_TYPE,
                AuditEvent.object_id == plan_digest,
            )
        )
    )


def _commit_once_without_retry(session: Session) -> None:
    try:
        session.commit()
    except Exception as exc:
        raise CleanupCommitOutcomeUnknown(
            "Cleanup commit outcome is uncertain. Do not retry; run read-only reconciliation."
        ) from exc


def execute_cleanup(
    manifest: dict[str, Any],
    manifest_sha256: str,
    approval: dict[str, Any],
    approval_sha256: str,
    backup_attestation: dict[str, Any],
    backup_attestation_sha256: str,
) -> dict[str, Any]:
    validate_backup_attestation(backup_attestation, manifest)
    # Hashing large backups can take time; validate the short-lived approval last so its
    # freshness is checked immediately before opening the deletion transaction.
    validate_approval(approval, manifest, manifest_sha256)
    identifiers = manifest_record_ids(manifest)
    audit_expectations = manifest_audit_expectations(manifest)
    session = SessionLocal()
    try:
        session.connection(execution_options={"isolation_level": "SERIALIZABLE"})
        session.execute(text("SET LOCAL lock_timeout = '5s'"))
        session.execute(text("SET LOCAL statement_timeout = '60s'"))
        acquired = session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
            {"lock_key": EXECUTION_ADVISORY_LOCK_KEY},
        )
        if not acquired:
            raise CleanupExecutionError("Another synthetic cleanup attempt is in progress.")
        if _existing_commit_marker(session, manifest["plan_digest"]):
            raise CleanupExecutionError("This cleanup plan was already committed; replay refused.")
        current_context = get_database_context(session)
        require_matching_database_context(manifest, current_context)
        _lock_exact_rows(session, identifiers, identifiers["audit_events"])
        analysis = analyze_synthetic_records(session)
        if not analysis_matches_plan(analysis, manifest, current_context):
            raise CleanupExecutionError("Fresh preflight differs from the approved cleanup plan.")

        organization_result = session.execute(
            delete(Organization).where(Organization.id.in_(identifiers["organizations"]))
        )
        customer_result = session.execute(
            delete(Customer).where(Customer.id.in_(identifiers["customers"]))
        )
        session.flush()
        if organization_result.rowcount != len(identifiers["organizations"]):
            raise CleanupExecutionError("Exact organization deletion count did not match the plan.")
        if customer_result.rowcount != len(identifiers["customers"]):
            raise CleanupExecutionError("Exact customer deletion count did not match the plan.")
        # Refresh retained rows after database-side SET NULL/CASCADE actions before verifying
        # them. The preflight analysis loaded these objects into the identity map.
        session.expire_all()
        for key, model in MODEL_BY_RECORD_KEY.items():
            if _count_ids(session, model, identifiers[key]):
                raise CleanupExecutionError(f"Post-delete verification found remaining {key} rows.")

        audits = session.scalars(
            select(AuditEvent).where(AuditEvent.id.in_(identifiers["audit_events"]))
        ).all()
        if len(audits) != len(identifiers["audit_events"]):
            raise CleanupExecutionError("Post-delete verification found missing audit events.")
        for event in audits:
            expected = audit_expectations[str(event.id)]
            if event.customer_id is not None or not hmac.compare_digest(
                audit_event_content_digest(event), expected["retained_content_sha256"]
            ):
                raise CleanupExecutionError(
                    "Post-delete audit preservation or detachment verification failed."
                )

        deleted_count = sum(
            len(values) for key, values in identifiers.items() if key != "audit_events"
        )
        session.add(
            AuditEvent(
                action=COMMIT_AUDIT_ACTION,
                object_type=COMMIT_AUDIT_OBJECT_TYPE,
                object_id=manifest["plan_digest"],
                outcome="success",
                reason="Guarded cleanup of separately reviewed synthetic smoke-test records.",
                metadata_json={
                    "records_deleted": deleted_count,
                    "audit_events_preserved_and_detached": len(audits),
                    "approval_reference": approval["approval_reference"],
                    "manifest_sha256": manifest_sha256,
                    "approval_sha256": approval_sha256,
                    "backup_attestation_sha256": backup_attestation_sha256,
                    "backup_set_id": backup_attestation["backup_set_id"],
                },
            )
        )
        session.flush()
        _commit_once_without_retry(session)
        return {
            "mode": "guarded_synthetic_cleanup_execution",
            "status": "committed",
            "identifiers_included": False,
            "plan_digest": manifest["plan_digest"],
            "records_deleted": deleted_count,
            "audit_events_preserved_and_detached": len(audits),
        }
    except CleanupCommitOutcomeUnknown:
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reconcile_cleanup(manifest: dict[str, Any]) -> dict[str, Any]:
    identifiers = manifest_record_ids(manifest)
    audit_expectations = manifest_audit_expectations(manifest)
    with SessionLocal() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        context_matches = get_database_context(session) == manifest["plan"]["database_context"]
        marker_exists = _existing_commit_marker(session, manifest["plan_digest"])
        remaining = {
            key: _count_ids(session, model, identifiers[key])
            for key, model in MODEL_BY_RECORD_KEY.items()
        }
        audits = session.scalars(
            select(AuditEvent).where(AuditEvent.id.in_(identifiers["audit_events"]))
        ).all()
        audit_content_matches = len(audits) == len(identifiers["audit_events"]) and all(
            audit_event_content_digest(event)
            == audit_expectations[str(event.id)]["retained_content_sha256"]
            for event in audits
        )
        audits_detached = audit_content_matches and all(
            event.customer_id is None for event in audits
        )
        audits_original = audit_content_matches and all(
            str(event.customer_id)
            == audit_expectations[str(event.id)]["original_customer_id"]
            for event in audits
        )
        if context_matches and marker_exists and not any(remaining.values()) and audits_detached:
            status = "committed"
        elif context_matches and not marker_exists and audits_original:
            analysis = analyze_synthetic_records(session)
            status = (
                "not_committed"
                if analysis_matches_plan(analysis, manifest, get_database_context(session))
                else "unknown_manual_review"
            )
        else:
            status = "unknown_manual_review"
        session.rollback()
    return {
        "mode": "read_only_synthetic_cleanup_reconciliation",
        "status": status,
        "identifiers_included": False,
        "plan_digest": manifest["plan_digest"],
        "automatic_retry_permitted": False,
    }


def _base_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute or reconcile an exact, separately approved synthetic cleanup plan."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    execute = subparsers.add_parser("execute")
    reconcile = subparsers.add_parser("reconcile")
    for subparser in (execute, reconcile):
        subparser.add_argument("--manifest", type=Path, required=True)
        subparser.add_argument("--manifest-sha256", required=True)
        subparser.add_argument("--plan-digest", required=True)
    execute.add_argument("--approval", type=Path, required=True)
    execute.add_argument("--approval-sha256", required=True)
    execute.add_argument("--backup-attestation", type=Path, required=True)
    execute.add_argument("--backup-attestation-sha256", required=True)
    execute.add_argument("--approve-customer", action="append", required=True)
    execute.add_argument("--approve-organization", action="append", required=True)
    execute.add_argument("--confirmation", required=True)
    return parser


def main() -> None:
    args = _base_parser().parse_args()
    manifest = load_review_manifest(
        args.manifest,
        args.manifest_sha256,
        require_current=args.command == "execute",
    )
    if not hmac.compare_digest(manifest["plan_digest"], args.plan_digest):
        raise CleanupExecutionError("CLI plan digest does not match the manifest.")
    if args.command == "reconcile":
        print(json.dumps(reconcile_cleanup(manifest), indent=2, sort_keys=True))
        return

    _assert_distinct_artifacts(
        [args.manifest, args.approval, args.backup_attestation]
    )
    require_exact_confirmation(manifest, args.confirmation)
    _require_exact_cli_selections(
        manifest, args.approve_customer, args.approve_organization
    )
    approval = _load_private_json(args.approval, args.approval_sha256)
    validate_approval(approval, manifest, args.manifest_sha256)
    backup_attestation = _load_private_json(
        args.backup_attestation, args.backup_attestation_sha256
    )
    validate_backup_attestation(backup_attestation, manifest)
    result = execute_cleanup(
        manifest,
        args.manifest_sha256,
        approval,
        args.approval_sha256,
        backup_attestation,
        args.backup_attestation_sha256,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except CleanupCommitOutcomeUnknown as exc:
        raise SystemExit(str(exc)) from exc
    except (CleanupPlanError, CleanupExecutionError, SQLAlchemyError) as exc:
        raise SystemExit(f"Cleanup refused: {exc}") from exc
