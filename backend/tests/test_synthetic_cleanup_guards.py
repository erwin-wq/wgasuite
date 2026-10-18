import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from app.maintenance.synthetic_cleanup_execution import (
    CleanupCommitOutcomeUnknown,
    CleanupExecutionError,
    _commit_once_without_retry,
    _require_exact_cli_selections,
    require_exact_confirmation,
    require_matching_database_context,
    validate_approval,
    validate_backup_attestation,
)
from app.maintenance.synthetic_cleanup_plan import (
    CleanupPlanError,
    canonical_json_bytes,
    load_review_manifest,
    sha256_bytes,
    sha256_file,
)


def _minimal_manifest(now: datetime) -> dict:
    customer_id = str(uuid4())
    organization_id = str(uuid4())
    audit_id = str(uuid4())
    plan = {
        "plan_schema_version": 2,
        "generated_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=30)).isoformat(),
        "database_context": {
            "database_name": "isolated_test",
            "database_user": "test",
            "database_oid": "42",
            "server_version_num": "160000",
            "system_identifier": "1234",
            "alembic_revision": "0014_google_group_membership",
        },
        "database_context_sha256": "placeholder",
        "selection_policy": "strict",
        "aggregate_counts": {},
        "impact_counts": {
            "records_expected_to_be_deleted": 2,
            "audit_events_expected_to_be_preserved_and_detached": 1,
        },
        "candidate_sets": [
            {
                "customer_id": customer_id,
                "organization_id": organization_id,
                "records_expected_to_be_deleted": {
                    "customers": [customer_id],
                    "organizations": [organization_id],
                    "connector_configs": [],
                    "connector_accounts": [],
                    "assessments": [],
                    "assets": [],
                    "findings": [],
                    "dread_scores": [],
                    "scan_runs": [],
                    "customer_memberships": [],
                    "delegate_confirmations": [],
                    "group_membership_confirmations": [],
                    "user_status_confirmations": [],
                },
                "records_expected_to_be_preserved": {
                    "audit_events_detached_from_customer": [audit_id]
                },
                "audit_event_original_customer_associations": [
                    {
                        "audit_event_id": audit_id,
                        "original_customer_id": customer_id,
                        "retained_content_sha256": "a" * 64,
                    }
                ],
            }
        ],
        "audit_policy": "preserve",
    }
    plan["database_context_sha256"] = sha256_bytes(
        canonical_json_bytes(plan["database_context"])
    )
    digest = sha256_bytes(canonical_json_bytes(plan))
    return {
        "schema_version": 2,
        "mode": "private_cleanup_review_plan",
        "plan": plan,
        "plan_digest": digest,
        "required_confirmation": f"DELETE REVIEWED SYNTHETIC RECORDS {digest}",
    }


def _approval(manifest: dict, manifest_sha256: str, now: datetime) -> dict:
    candidate = manifest["plan"]["candidate_sets"][0]
    return {
        "schema_version": 1,
        "mode": "synthetic_cleanup_human_approval",
        "plan_digest": manifest["plan_digest"],
        "manifest_sha256": manifest_sha256,
        "approved_customer_ids": [candidate["customer_id"]],
        "approved_organization_ids": [candidate["organization_id"]],
        "approved_by": "isolated-test-reviewer",
        "approval_reference": "isolated-test-only",
        "approved_at": (now + timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(minutes=10)).isoformat(),
    }


def _private_file(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    os.chmod(path, 0o600)
    return path


def test_approval_requires_exact_ids_and_fresh_separate_review():
    now = datetime.now(UTC)
    manifest = _minimal_manifest(now)
    approval = _approval(manifest, "b" * 64, now)

    assert validate_approval(
        approval, manifest, "b" * 64, now=now + timedelta(minutes=2)
    ) == approval

    approval["approved_customer_ids"] = [str(uuid4())]
    with pytest.raises(CleanupExecutionError, match="exact customer UUIDs"):
        validate_approval(
            approval, manifest, "b" * 64, now=now + timedelta(minutes=2)
        )


def test_approval_and_cli_selections_are_order_sensitive_exact_repetitions():
    now = datetime.now(UTC)
    manifest = _minimal_manifest(now)
    customer_id = manifest["plan"]["candidate_sets"][0]["customer_id"]
    organization_id = manifest["plan"]["candidate_sets"][0]["organization_id"]

    _require_exact_cli_selections(manifest, [customer_id], [organization_id])
    with pytest.raises(CleanupExecutionError, match="CLI customer selections"):
        _require_exact_cli_selections(manifest, [str(uuid4())], [organization_id])


def test_database_identity_must_match_every_bound_field():
    manifest = _minimal_manifest(datetime.now(UTC))
    current_context = dict(manifest["plan"]["database_context"])

    require_matching_database_context(manifest, current_context)
    current_context["database_oid"] = "43"
    with pytest.raises(CleanupExecutionError, match="different database identity"):
        require_matching_database_context(manifest, current_context)


def test_operator_confirmation_requires_the_complete_exact_plan_digest():
    manifest = _minimal_manifest(datetime.now(UTC))

    require_exact_confirmation(manifest, manifest["required_confirmation"])
    with pytest.raises(CleanupExecutionError, match="not exact"):
        require_exact_confirmation(manifest, "DELETE REVIEWED SYNTHETIC RECORDS")


def test_ambiguous_commit_is_reported_without_retry():
    class FailingSession:
        commit_calls = 0

        def commit(self):
            self.commit_calls += 1
            raise ConnectionError("simulated lost commit response")

    session = FailingSession()
    with pytest.raises(CleanupCommitOutcomeUnknown, match="Do not retry"):
        _commit_once_without_retry(session)
    assert session.commit_calls == 1


def test_backup_attestation_requires_hashes_and_both_recovery_verifications(
    tmp_path: Path,
):
    now = datetime.now(UTC)
    manifest = _minimal_manifest(now)
    database_backup = _private_file(tmp_path / "database.dump", b"isolated db backup")
    credential_backup = _private_file(
        tmp_path / "credentials.tar.gz", b"isolated credential archive"
    )
    attestation = {
        "schema_version": 1,
        "mode": "synthetic_cleanup_backup_attestation",
        "plan_digest": manifest["plan_digest"],
        "database_context_sha256": manifest["plan"]["database_context_sha256"],
        "backup_set_id": "isolated-test-backups",
        "attested_by": "isolated-test-runner",
        "attested_at": (now + timedelta(minutes=1)).isoformat(),
        "database_backup": {
            "path": str(database_backup),
            "sha256": sha256_file(database_backup),
            "created_at": now.isoformat(),
            "restore_verified_at": (now + timedelta(seconds=10)).isoformat(),
            "verification_reference": "isolated restore completed",
        },
        "credential_backup": {
            "path": str(credential_backup),
            "sha256": sha256_file(credential_backup),
            "created_at": now.isoformat(),
            "recovery_verified_at": (now + timedelta(seconds=10)).isoformat(),
            "verification_reference": "isolated extraction and content comparison completed",
        },
        "cascade_validation": {
            "status": "passed_and_rolled_back",
            "verified_at": (now + timedelta(seconds=20)).isoformat(),
            "records_temporarily_removed": None,
            "audit_events_preserved_and_detached": None,
            "verification_reference": "isolated rollback-only cascade validation",
        },
    }
    attestation["cascade_validation"]["records_temporarily_removed"] = manifest[
        "plan"
    ]["impact_counts"].get("records_expected_to_be_deleted")
    attestation["cascade_validation"][
        "audit_events_preserved_and_detached"
    ] = manifest["plan"]["impact_counts"].get(
        "audit_events_expected_to_be_preserved_and_detached"
    )

    assert validate_backup_attestation(
        attestation, manifest, now=now + timedelta(minutes=2)
    ) == attestation

    del attestation["credential_backup"]["recovery_verified_at"]
    with pytest.raises(CleanupExecutionError, match="recovery_verified_at"):
        validate_backup_attestation(
            attestation, manifest, now=now + timedelta(minutes=2)
        )


def test_review_manifest_rejects_tampering_expiry_and_open_permissions(tmp_path: Path):
    now = datetime.now(UTC)
    manifest = _minimal_manifest(now)
    payload = (json.dumps(manifest, sort_keys=True) + "\n").encode()
    path = _private_file(tmp_path / "plan.json", payload)
    checksum = sha256_bytes(payload)

    assert load_review_manifest(path, checksum, now=now + timedelta(minutes=1)) == manifest
    with pytest.raises(CleanupPlanError, match="expired"):
        load_review_manifest(path, checksum, now=now + timedelta(hours=1))

    os.chmod(path, 0o644)
    with pytest.raises(CleanupPlanError, match="mode 0600"):
        load_review_manifest(path, checksum, now=now + timedelta(minutes=1))

    os.chmod(path, 0o600)
    path.write_bytes(payload + b" ")
    with pytest.raises(CleanupPlanError, match="SHA-256"):
        load_review_manifest(path, checksum, now=now + timedelta(minutes=1))
