import json
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.google_workspace_checks import GOOGLE_WORKSPACE_CHECKS
from app.maintenance.synthetic_cleanup_dry_run import (
    validate_cascade_with_rollback,
)
from app.maintenance.synthetic_cleanup_plan import (
    build_review_manifest,
    load_review_manifest,
    write_review_manifest,
)
from app.maintenance.synthetic_record_analysis import (
    SMOKE_CONNECTOR_NOTES,
    SMOKE_MARKER,
    analyze_synthetic_records,
)
from app.maintenance.synthetic_record_inventory import build_inventory
from app.models import (
    Assessment,
    Asset,
    AuditEvent,
    ConnectorAccount,
    ConnectorConfig,
    Customer,
    DreadScore,
    Finding,
    GoogleWorkspaceDelegateConfirmation,
    GoogleWorkspaceGroupMembershipConfirmation,
    GoogleWorkspaceUserStatusConfirmation,
    Organization,
    ScanRun,
    User,
)

SMOKE_TOKEN = "20261010120000-12345"
TEST_DATABASE_CONTEXT = {
    "database_name": "wgasuite_test",
    "database_user": "test_user",
    "database_oid": "16384",
    "server_version_num": "160000",
    "system_identifier": "123456789",
    "alembic_revision": "0014_google_group_membership",
}


def create_complete_smoke_set(db_session: Session) -> tuple[Customer, Organization]:
    customer = Customer(
        name=f"Smoke Customer {SMOKE_TOKEN}",
        slug=f"smoke-customer-{SMOKE_TOKEN}",
        contact_name="Smoke Tester",
        contact_email="smoke@example.local",
        status="active",
        notes=SMOKE_MARKER,
    )
    db_session.add(customer)
    db_session.flush()
    organization = Organization(
        customer_id=customer.id,
        name=f"Smoke Test Org {SMOKE_TOKEN}",
        description=SMOKE_MARKER,
    )
    db_session.add(organization)
    db_session.flush()
    connector = ConnectorConfig(
        organization_id=organization.id,
        connector_type="google_workspace",
        auth_method="service_account_domain_wide_delegation",
        status="connection_failed",
        display_name="Smoke Google Workspace",
        primary_domain="smoke.example.local",
        admin_subject_email="admin@smoke.example.local",
        credential_provider="file",
        notes=SMOKE_CONNECTOR_NOTES,
        last_error_code="credential_reference_missing",
    )
    assessment = Assessment(
        organization_id=organization.id,
        title=f"Smoke assessment {SMOKE_TOKEN}",
        status="draft",
        scope_summary="API smoke test scope",
    )
    manual_asset = Asset(
        organization_id=organization.id,
        name=f"Smoke asset {SMOKE_TOKEN}",
        asset_type="saas",
        identifier=f"smoke-{SMOKE_TOKEN}",
        description="API smoke test asset",
    )
    mock_asset = Asset(
        organization_id=organization.id,
        name="Google Workspace Tenant",
        asset_type="SaaS Platform",
        identifier="google-workspace-mock",
        description="Demo asset created by the mock Google Workspace scan.",
    )
    db_session.add_all([connector, assessment, manual_asset, mock_asset])
    db_session.flush()

    findings = [
        Finding(
            assessment_id=assessment.id,
            asset_id=manual_asset.id,
            title=f"Smoke finding {SMOKE_TOKEN}",
            description="API smoke test finding",
            status="open",
            mitigation="Validate controls",
        )
    ]
    findings.extend(
        Finding(
            assessment_id=assessment.id,
            asset_id=mock_asset.id,
            title=check.maps_to_finding_title,
            description="Mock finding",
            status="open",
            mitigation=check.recommendation,
        )
        for check in GOOGLE_WORKSPACE_CHECKS
    )
    db_session.add_all(findings)
    db_session.flush()
    for finding in findings:
        db_session.add(
            DreadScore(
                finding_id=finding.id,
                damage=6,
                reproducibility=6,
                exploitability=6,
                affected_users=6,
                discoverability=6,
                total_score=6.0,
                risk_level="High",
            )
        )
    db_session.add(
        ScanRun(
            assessment_id=assessment.id,
            connector_type="google_workspace_mock",
            status="completed",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            findings_created=len(GOOGLE_WORKSPACE_CHECKS),
            summary="Mock Google Workspace scan completed.",
        )
    )
    db_session.add(
        AuditEvent(
            customer_id=customer.id,
            action="report.viewed",
            object_type="assessment_report",
            object_id=str(assessment.id),
            outcome="success",
        )
    )
    db_session.commit()
    return customer, organization


def test_inventory_reports_only_exact_aggregate_candidates_without_mutating(
    db_session: Session,
):
    db_session.add(Customer(name="Real Customer", slug="real-customer", status="active"))
    create_complete_smoke_set(db_session)

    customer_count_before = db_session.scalar(select(func.count()).select_from(Customer))
    report = build_inventory(db_session)
    serialized_report = json.dumps(report)

    assert report["candidate_groups"][0]["record_count"] == 1
    assert report["candidate_groups"][1]["record_count"] == 1
    assert report["associated_data"]["connector_configs"] == 1
    assert report["associated_data"]["assessments"] == 1
    assert report["associated_data"]["assets"] == 2
    assert report["associated_data"]["findings"] == 8
    assert report["associated_data"]["dread_scores"] == 8
    assert report["associated_data"]["audit_events"] == 1
    assert report["review_blockers"] == {}
    assert report["cleanup_eligibility"] == "eligible_for_manual_review_only"
    assert report["safe_to_delete_now"] is False
    assert SMOKE_TOKEN not in serialized_report
    assert "Real Customer" not in serialized_report
    assert db_session.scalar(select(func.count()).select_from(Customer)) == customer_count_before


def test_inventory_requires_manual_review_for_credential_bearing_candidate(
    db_session: Session,
):
    _, organization = create_complete_smoke_set(db_session)
    connector = db_session.scalar(
        select(ConnectorConfig).where(ConnectorConfig.organization_id == organization.id)
    )
    assert connector is not None
    connector.credential_ref = "private-reference"
    db_session.commit()

    report = build_inventory(db_session)

    assert report["associated_data"]["credential_bearing_connector_configs"] == 1
    assert report["cleanup_eligibility"] == "manual_review_required_credentials_present"
    assert report["safe_to_delete_now"] is False
    assert "private-reference" not in json.dumps(report)


def test_analysis_refuses_mixed_customer_relationships(db_session: Session):
    customer, _ = create_complete_smoke_set(db_session)
    db_session.add(
        Organization(
            customer_id=customer.id,
            name="Production Workspace",
            description="Customer-owned data",
        )
    )
    db_session.commit()

    analysis = analyze_synthetic_records(db_session)

    assert analysis.eligible_for_manifest is False
    assert analysis.blocker_counts["mixed_customer_organizations"] == 1
    assert analysis.non_candidate_customer_organizations == 1


def test_analysis_rejects_marker_records_without_correlated_strict_tokens(
    db_session: Session,
):
    db_session.add(
        Customer(
            name="Smoke Customer 20261010",
            slug="smoke-customer-different",
            contact_name="Smoke Tester",
            contact_email="smoke@example.local",
            status="active",
            notes=SMOKE_MARKER,
        )
    )
    db_session.commit()

    analysis = analyze_synthetic_records(db_session)

    assert analysis.eligible_for_manifest is False
    assert analysis.blocker_counts["customer_fingerprint_mismatch"] == 1


def test_analysis_rejects_unexpected_connector_account(db_session: Session):
    _, organization = create_complete_smoke_set(db_session)
    db_session.add(
        ConnectorAccount(
            organization_id=organization.id,
            provider="unexpected-provider",
            status="active",
            metadata_json={},
        )
    )
    db_session.commit()

    analysis = analyze_synthetic_records(db_session)

    assert analysis.eligible_for_manifest is False
    assert analysis.blocker_counts["unexpected_connector_accounts"] == 1


def test_analysis_rejects_changed_dependency_count(db_session: Session):
    _, organization = create_complete_smoke_set(db_session)
    db_session.add(
        Asset(
            organization_id=organization.id,
            name="Unexpected asset",
            asset_type="system",
        )
    )
    db_session.commit()

    analysis = analyze_synthetic_records(db_session)

    assert analysis.eligible_for_manifest is False
    assert analysis.blocker_counts["asset_fingerprint_mismatch"] == 1


def test_analysis_rejects_cross_tenant_finding_relationship(db_session: Session):
    _, organization = create_complete_smoke_set(db_session)
    candidate_asset = db_session.scalar(
        select(Asset).where(Asset.organization_id == organization.id)
    )
    other_organization = Organization(name="Other tenant")
    db_session.add(other_organization)
    db_session.flush()
    other_assessment = Assessment(
        organization_id=other_organization.id,
        title="Other assessment",
        status="draft",
    )
    db_session.add(other_assessment)
    db_session.flush()
    db_session.add(
        Finding(
            assessment_id=other_assessment.id,
            asset_id=candidate_asset.id,
            title="Cross-tenant finding",
            status="open",
        )
    )
    db_session.commit()

    analysis = analyze_synthetic_records(db_session)

    assert analysis.eligible_for_manifest is False
    assert analysis.cross_tenant_findings == 1
    assert analysis.blocker_counts["cross_tenant_finding_asset_relationship"] == 1


@pytest.mark.parametrize("confirmation_kind", ["delegate", "group", "user_status"])
def test_analysis_rejects_google_mutation_confirmation_records(
    db_session: Session,
    confirmation_kind: str,
):
    customer, organization = create_complete_smoke_set(db_session)
    actor = db_session.scalar(select(User))
    connector = db_session.scalar(
        select(ConnectorConfig).where(ConnectorConfig.organization_id == organization.id)
    )
    common = {
        "organization_id": organization.id,
        "actor_user_id": actor.id,
        "operation": "create",
        "token_digest": confirmation_kind.ljust(64, "0"),
        "expires_at": datetime.now(UTC) + timedelta(minutes=5),
    }
    if confirmation_kind == "delegate":
        confirmation = GoogleWorkspaceDelegateConfirmation(
            **common,
            owner_google_id="owner-id",
            owner_primary_email="owner@example.invalid",
            delegate_google_id="delegate-id",
            delegate_primary_email="delegate@example.invalid",
        )
    elif confirmation_kind == "group":
        confirmation = GoogleWorkspaceGroupMembershipConfirmation(
            **common,
            group_google_id="group-id",
            group_primary_email="group@example.invalid",
            member_google_id="member-id",
            member_primary_email="member@example.invalid",
        )
    else:
        confirmation = GoogleWorkspaceUserStatusConfirmation(
            **common,
            customer_id=customer.id,
            connector_config_id=connector.id,
            google_customer_id="google-customer-id",
            target_google_id="target-id",
            target_primary_email="target@example.invalid",
            expected_suspended=False,
            requested_suspended=True,
        )
    db_session.add(confirmation)
    db_session.commit()

    analysis = analyze_synthetic_records(db_session)

    assert analysis.eligible_for_manifest is False
    assert analysis.blocker_counts["unexpected_google_mutation_confirmations"] == 1


def test_plan_digest_is_stable_and_database_context_bound(db_session: Session):
    create_complete_smoke_set(db_session)
    analysis = analyze_synthetic_records(db_session)
    generated_at = datetime(2026, 10, 18, tzinfo=UTC)

    first = build_review_manifest(
        analysis, TEST_DATABASE_CONTEXT, generated_at=generated_at
    )
    second = build_review_manifest(
        analysis, TEST_DATABASE_CONTEXT, generated_at=generated_at
    )
    changed_context = dict(TEST_DATABASE_CONTEXT)
    changed_context["database_oid"] = "99999"
    different_database = build_review_manifest(
        analysis, changed_context, generated_at=generated_at
    )

    assert first["plan_digest"] == second["plan_digest"]
    assert first["plan_digest"] != different_database["plan_digest"]


def test_private_manifest_is_exact_restricted_and_keeps_audits_outside_delete_set(
    db_session: Session,
    tmp_path: Path,
):
    create_complete_smoke_set(db_session)
    analysis = analyze_synthetic_records(db_session)
    private_directory = tmp_path / "private"

    manifest = build_review_manifest(analysis, TEST_DATABASE_CONTEXT)
    manifest_path, checksum = write_review_manifest(manifest, private_directory)
    manifest = json.loads(manifest_path.read_text())

    assert len(checksum) == 64
    assert stat.S_IMODE(private_directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(manifest_path.with_suffix(".sha256").stat().st_mode) == 0o600
    assert manifest["safe_to_delete_now"] is False
    assert manifest["cleanup_execution_supported"] == "guarded_phase_b_only"
    assert len(manifest["plan_digest"]) == 64
    assert manifest["required_confirmation"].endswith(manifest["plan_digest"])
    candidate = manifest["plan"]["candidate_sets"][0]
    assert len(candidate["records_expected_to_be_deleted"]["findings"]) == 8
    assert len(
        candidate["records_expected_to_be_preserved"][
            "audit_events_detached_from_customer"
        ]
    ) == 1
    assert "audit_events" not in candidate["records_expected_to_be_deleted"]
    assert load_review_manifest(manifest_path, checksum) == manifest


def test_cascade_validation_refuses_an_unguarded_database(db_session: Session):
    create_complete_smoke_set(db_session)
    analysis = analyze_synthetic_records(db_session)

    with pytest.raises(RuntimeError, match="isolated-restored-backup mode guard"):
        validate_cascade_with_rollback(db_session, analysis)
