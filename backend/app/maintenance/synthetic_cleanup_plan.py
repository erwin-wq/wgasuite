from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.maintenance.synthetic_record_analysis import SyntheticDataAnalysis

PLAN_SCHEMA_VERSION = 2
PLAN_TTL = timedelta(minutes=30)
MAX_PRIVATE_JSON_BYTES = 8 * 1024 * 1024
DELETE_COUNT_KEYS = (
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
    "user_orgunit_confirmations",
)


class CleanupPlanError(RuntimeError):
    """A private review plan is missing, stale, malformed, or does not match current state."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise CleanupPlanError(f"{field} must be an ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CleanupPlanError(f"{field} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise CleanupPlanError(f"{field} must include a timezone.")
    return parsed.astimezone(UTC)


def require_private_file(path: Path, *, max_bytes: int | None = None) -> Path:
    if path.is_symlink() or not path.is_file():
        raise CleanupPlanError("Private artifact must be a regular, non-symlink file.")
    resolved = path.resolve()
    metadata = resolved.stat()
    mode = stat.S_IMODE(metadata.st_mode)
    if mode != 0o600:
        raise CleanupPlanError(f"Private artifact must have mode 0600; found {mode:04o}.")
    if metadata.st_uid != os.geteuid():
        raise CleanupPlanError("Private artifact must be owned by the executing user.")
    if max_bytes is not None and metadata.st_size > max_bytes:
        raise CleanupPlanError("Private artifact exceeds the allowed size.")
    return resolved


def ensure_private_directory(directory: Path) -> Path:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = directory.resolve()
    mode = stat.S_IMODE(directory.stat().st_mode)
    if mode != 0o700:
        raise CleanupPlanError(
            f"Private manifest directory must have mode 0700; found {mode:04o}."
        )
    if directory.stat().st_uid != os.geteuid():
        raise CleanupPlanError("Private manifest directory must be owned by the executing user.")
    return directory


def write_private_file(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def get_database_context(session: Session) -> dict[str, str]:
    if session.bind is None or session.bind.dialect.name != "postgresql":
        raise CleanupPlanError("Synthetic cleanup plans require PostgreSQL database identity.")
    try:
        row = session.execute(
            text(
                """
                SELECT
                    current_database() AS database_name,
                    current_user AS database_user,
                    (SELECT oid::text FROM pg_database WHERE datname = current_database())
                        AS database_oid,
                    current_setting('server_version_num') AS server_version_num,
                    (SELECT system_identifier::text FROM pg_control_system())
                        AS system_identifier,
                    (SELECT version_num FROM alembic_version LIMIT 1) AS alembic_revision
                """
            )
        ).mappings().one()
    except Exception as exc:
        raise CleanupPlanError(
            "Unable to establish the required PostgreSQL cluster/database identity."
        ) from exc
    context = {key: str(value) for key, value in row.items() if value is not None}
    required = {
        "database_name",
        "database_user",
        "database_oid",
        "server_version_num",
        "system_identifier",
        "alembic_revision",
    }
    if set(context) != required:
        raise CleanupPlanError("PostgreSQL database identity is incomplete.")
    return context


def database_context_digest(context: dict[str, str]) -> str:
    return sha256_bytes(canonical_json_bytes(context))


def _impact_counts(analysis: SyntheticDataAnalysis) -> dict[str, int]:
    aggregate = analysis.aggregate_counts()
    return {
        "records_expected_to_be_deleted": sum(aggregate.get(key, 0) for key in DELETE_COUNT_KEYS),
        "audit_events_expected_to_be_preserved_and_detached": aggregate.get(
            "audit_events_preserved_and_detached", 0
        ),
    }


def build_review_manifest(
    analysis: SyntheticDataAnalysis,
    database_context: dict[str, str],
    *,
    generated_at: datetime | None = None,
    ttl: timedelta = PLAN_TTL,
) -> dict[str, Any]:
    if not analysis.eligible_for_manifest:
        raise CleanupPlanError("Ambiguous or mixed synthetic data cannot produce a review plan.")
    generated_at = (generated_at or datetime.now(UTC)).astimezone(UTC)
    if ttl <= timedelta(0) or ttl > PLAN_TTL:
        raise CleanupPlanError("Cleanup review plan lifetime must be between zero and 30 minutes.")
    candidate_sets = [
        candidate.private_manifest_entry() for candidate in analysis.candidates
    ]
    plan = {
        "plan_schema_version": PLAN_SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "expires_at": (generated_at + ttl).isoformat(),
        "database_context": database_context,
        "database_context_sha256": database_context_digest(database_context),
        "selection_policy": (
            "Exact correlated scripts/dev/smoke_api.sh fingerprints and relationships only."
        ),
        "aggregate_counts": analysis.aggregate_counts(),
        "impact_counts": _impact_counts(analysis),
        "candidate_sets": candidate_sets,
        "audit_policy": (
            "Preserve every listed audit event and detach only its customer_id through the "
            "PostgreSQL ON DELETE SET NULL foreign key."
        ),
    }
    plan_digest = sha256_bytes(canonical_json_bytes(plan))
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "mode": "private_cleanup_review_plan",
        "contains_private_identifiers": True,
        "safe_to_delete_now": False,
        "requires_separate_human_approval": True,
        "cleanup_execution_supported": "guarded_phase_b_only",
        "plan": plan,
        "plan_digest": plan_digest,
        "required_confirmation": f"DELETE REVIEWED SYNTHETIC RECORDS {plan_digest}",
    }


def write_review_manifest(manifest: dict[str, Any], directory: Path) -> tuple[Path, str]:
    directory = ensure_private_directory(directory)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    manifest_path = directory / f"synthetic-cleanup-review-{timestamp}.json"
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    checksum = sha256_bytes(payload)
    checksum_path = manifest_path.with_suffix(".sha256")
    previous_umask = os.umask(0o077)
    try:
        write_private_file(manifest_path, payload)
        try:
            write_private_file(
                checksum_path,
                f"{checksum}  {manifest_path.name}\n".encode(),
            )
        except Exception:
            manifest_path.unlink(missing_ok=True)
            raise
    finally:
        os.umask(previous_umask)
    return manifest_path, checksum


def _require_uuid_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise CleanupPlanError(f"{field} must be a non-empty UUID list.")
    try:
        normalized = [str(UUID(item)) for item in value]
    except (TypeError, ValueError, AttributeError) as exc:
        raise CleanupPlanError(f"{field} contains an invalid UUID.") from exc
    if len(set(normalized)) != len(normalized):
        raise CleanupPlanError(f"{field} contains duplicate UUIDs.")
    return normalized


def _require_optional_uuid_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise CleanupPlanError(f"{field} must be a UUID list.")
    if not value:
        return []
    return _require_uuid_list(value, field)


def manifest_customer_ids(manifest: dict[str, Any]) -> list[str]:
    values = [item.get("customer_id") for item in manifest["plan"]["candidate_sets"]]
    return _require_uuid_list(values, "plan customer IDs")


def manifest_organization_ids(manifest: dict[str, Any]) -> list[str]:
    values = [item.get("organization_id") for item in manifest["plan"]["candidate_sets"]]
    return _require_uuid_list(values, "plan organization IDs")


def manifest_record_ids(manifest: dict[str, Any]) -> dict[str, list[str]]:
    identifiers = {key: [] for key in DELETE_COUNT_KEYS}
    identifiers["audit_events"] = []
    for index, candidate in enumerate(manifest["plan"]["candidate_sets"]):
        if not isinstance(candidate, dict):
            raise CleanupPlanError(f"candidate_sets[{index}] must be an object.")
        deleted = candidate.get("records_expected_to_be_deleted")
        preserved = candidate.get("records_expected_to_be_preserved")
        if not isinstance(deleted, dict) or set(deleted) != set(DELETE_COUNT_KEYS):
            raise CleanupPlanError(f"candidate_sets[{index}] has an invalid deletion graph.")
        if not isinstance(preserved, dict) or set(preserved) != {
            "audit_events_detached_from_customer"
        }:
            raise CleanupPlanError(f"candidate_sets[{index}] has an invalid audit graph.")
        for key in DELETE_COUNT_KEYS:
            identifiers[key].extend(
                _require_optional_uuid_list(
                    deleted[key], f"candidate_sets[{index}].{key}"
                )
            )
        identifiers["audit_events"].extend(
            _require_optional_uuid_list(
                preserved["audit_events_detached_from_customer"],
                f"candidate_sets[{index}].audit_events",
            )
        )
    for key, values in identifiers.items():
        if len(values) != len(set(values)):
            raise CleanupPlanError(f"Cleanup plan repeats a {key} UUID.")
    if identifiers["customers"] != manifest_customer_ids(manifest):
        raise CleanupPlanError("Cleanup plan customer selections are inconsistent.")
    if identifiers["organizations"] != manifest_organization_ids(manifest):
        raise CleanupPlanError("Cleanup plan organization selections are inconsistent.")
    return identifiers


def manifest_audit_expectations(manifest: dict[str, Any]) -> dict[str, dict[str, str]]:
    expectations: dict[str, dict[str, str]] = {}
    for index, candidate in enumerate(manifest["plan"]["candidate_sets"]):
        associations = candidate.get("audit_event_original_customer_associations")
        if not isinstance(associations, list):
            raise CleanupPlanError(
                f"candidate_sets[{index}] has invalid audit associations."
            )
        for association in associations:
            if not isinstance(association, dict) or set(association) != {
                "audit_event_id",
                "original_customer_id",
                "retained_content_sha256",
            }:
                raise CleanupPlanError("Cleanup plan has a malformed audit association.")
            try:
                event_id = str(UUID(association["audit_event_id"]))
                customer_id = str(UUID(association["original_customer_id"]))
            except (AttributeError, TypeError, ValueError) as exc:
                raise CleanupPlanError(
                    "Cleanup plan has an invalid audit association UUID."
                ) from exc
            digest = association["retained_content_sha256"]
            if not isinstance(digest, str) or len(digest) != 64:
                raise CleanupPlanError("Cleanup plan has an invalid audit content digest.")
            if event_id in expectations:
                raise CleanupPlanError("Cleanup plan repeats an audit association.")
            expectations[event_id] = {
                "original_customer_id": customer_id,
                "retained_content_sha256": digest,
            }
    if set(expectations) != set(manifest_record_ids(manifest)["audit_events"]):
        raise CleanupPlanError("Cleanup plan audit identifiers are inconsistent.")
    return expectations


def _validate_manifest_structure(manifest: Any) -> dict[str, Any]:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise CleanupPlanError("Unsupported cleanup review manifest schema.")
    if manifest.get("mode") != "private_cleanup_review_plan":
        raise CleanupPlanError("File is not a cleanup review manifest.")
    plan = manifest.get("plan")
    plan_digest = manifest.get("plan_digest")
    if not isinstance(plan, dict) or not isinstance(plan_digest, str):
        raise CleanupPlanError("Cleanup review manifest is incomplete.")
    actual_plan_digest = sha256_bytes(canonical_json_bytes(plan))
    if not hmac.compare_digest(actual_plan_digest, plan_digest):
        raise CleanupPlanError("Canonical cleanup plan digest does not match the manifest.")
    expected_confirmation = f"DELETE REVIEWED SYNTHETIC RECORDS {plan_digest}"
    if manifest.get("required_confirmation") != expected_confirmation:
        raise CleanupPlanError("Cleanup confirmation binding is invalid.")
    if plan.get("plan_schema_version") != PLAN_SCHEMA_VERSION:
        raise CleanupPlanError("Canonical cleanup plan schema is invalid.")
    context = plan.get("database_context")
    if not isinstance(context, dict) or plan.get(
        "database_context_sha256"
    ) != database_context_digest(context):
        raise CleanupPlanError("Cleanup database context binding is invalid.")
    candidates = plan.get("candidate_sets")
    if not isinstance(candidates, list) or not candidates:
        raise CleanupPlanError("Cleanup review manifest has no exact candidate sets.")
    impact = plan.get("impact_counts")
    required_impact_keys = {
        "records_expected_to_be_deleted",
        "audit_events_expected_to_be_preserved_and_detached",
    }
    if (
        not isinstance(impact, dict)
        or set(impact) != required_impact_keys
        or any(
            not isinstance(impact[key], int) or impact[key] < 0
            for key in required_impact_keys
        )
    ):
        raise CleanupPlanError("Cleanup review manifest has invalid impact counts.")
    manifest_customer_ids(manifest)
    manifest_organization_ids(manifest)
    manifest_record_ids(manifest)
    manifest_audit_expectations(manifest)
    return manifest


def load_review_manifest(
    path: Path,
    expected_sha256: str,
    *,
    now: datetime | None = None,
    require_current: bool = True,
) -> dict[str, Any]:
    path = require_private_file(path, max_bytes=MAX_PRIVATE_JSON_BYTES)
    payload = path.read_bytes()
    actual_sha256 = sha256_bytes(payload)
    if not hmac.compare_digest(actual_sha256, expected_sha256.lower()):
        raise CleanupPlanError("Cleanup review manifest SHA-256 does not match.")
    try:
        manifest = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise CleanupPlanError("Cleanup review manifest is not valid JSON.") from exc
    manifest = _validate_manifest_structure(manifest)
    generated_at = _parse_timestamp(manifest["plan"].get("generated_at"), "generated_at")
    expires_at = _parse_timestamp(manifest["plan"].get("expires_at"), "expires_at")
    if expires_at <= generated_at or expires_at - generated_at > PLAN_TTL:
        raise CleanupPlanError("Cleanup review manifest has an invalid lifetime.")
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    if generated_at > current_time + timedelta(minutes=1):
        raise CleanupPlanError("Cleanup review manifest is dated in the future.")
    if require_current and current_time >= expires_at:
        raise CleanupPlanError("Cleanup review manifest has expired; prepare a new plan.")
    return manifest


def analysis_matches_plan(
    analysis: SyntheticDataAnalysis,
    manifest: dict[str, Any],
    database_context: dict[str, str],
) -> bool:
    if not analysis.eligible_for_manifest:
        return False
    plan = manifest["plan"]
    return (
        plan.get("database_context") == database_context
        and plan.get("database_context_sha256") == database_context_digest(database_context)
        and plan.get("aggregate_counts") == analysis.aggregate_counts()
        and plan.get("impact_counts") == _impact_counts(analysis)
        and plan.get("candidate_sets")
        == [candidate.private_manifest_entry() for candidate in analysis.candidates]
    )


def safe_plan_summary(
    analysis: SyntheticDataAnalysis,
    manifest: dict[str, Any],
    *,
    manifest_name: str,
    manifest_sha256: str,
) -> dict[str, Any]:
    return {
        "mode": "private_cleanup_review_plan",
        "identifiers_included": False,
        "candidate_sets": len(analysis.candidates),
        "aggregate_counts": analysis.aggregate_counts(),
        "impact_counts": manifest["plan"]["impact_counts"],
        "review_blockers": analysis.blocker_counts,
        "cleanup_eligibility": "eligible_for_manual_review_only",
        "safe_to_delete_now": False,
        "requires_separate_human_approval": True,
        "manifest_file": manifest_name,
        "manifest_sha256": manifest_sha256,
        "plan_digest": manifest["plan_digest"],
        "expires_at": manifest["plan"]["expires_at"],
        "audit_handling": "preserve rows and detach customer references",
    }
