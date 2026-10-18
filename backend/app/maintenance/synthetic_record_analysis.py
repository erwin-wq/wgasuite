from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, not_, or_, select
from sqlalchemy.orm import Session

from app.connectors.google_workspace_checks import GOOGLE_WORKSPACE_CHECKS
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

SMOKE_MARKER = "Created by scripts/dev/smoke_api.sh"
SMOKE_CONNECTOR_NOTES = "Smoke test metadata only; no secrets stored."
RUN_TOKEN_PATTERN = re.compile(r"^\d{14}-\d+$")
CUSTOMER_NAME_PATTERN = re.compile(r"^Smoke Customer (?P<token>\d{14}-\d+)$")
CUSTOMER_SLUG_PATTERN = re.compile(r"^smoke-customer-(?P<token>\d{14}-\d+)$")
ORGANIZATION_NAME_PATTERN = re.compile(r"^Smoke Test Org (?P<token>\d{14}-\d+)$")


def _count(session: Session, statement: Select[Any]) -> int:
    return int(session.scalar(statement) or 0)


def _ids(records: list[Any]) -> list[str]:
    return sorted(str(record.id) for record in records)


def customer_run_token(customer: Customer) -> str | None:
    """Return the correlated smoke run token only for the exact script fingerprint."""
    name_match = CUSTOMER_NAME_PATTERN.fullmatch(customer.name)
    slug_match = CUSTOMER_SLUG_PATTERN.fullmatch(customer.slug)
    if (
        name_match is None
        or slug_match is None
        or name_match.group("token") != slug_match.group("token")
        or customer.contact_name != "Smoke Tester"
        or customer.contact_email != "smoke@example.local"
        or customer.status != "active"
        or customer.notes != SMOKE_MARKER
    ):
        return None
    token = name_match.group("token")
    return token if RUN_TOKEN_PATTERN.fullmatch(token) else None


def organization_run_token(organization: Organization) -> str | None:
    match = ORGANIZATION_NAME_PATTERN.fullmatch(organization.name)
    if match is None or organization.description != SMOKE_MARKER:
        return None
    token = match.group("token")
    return token if RUN_TOKEN_PATTERN.fullmatch(token) else None


@dataclass
class CandidateSet:
    token: str
    customer: Customer
    organization: Organization
    connector_configs: list[ConnectorConfig] = field(default_factory=list)
    connector_accounts: list[ConnectorAccount] = field(default_factory=list)
    assessments: list[Assessment] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    dread_scores: list[DreadScore] = field(default_factory=list)
    scan_runs: list[ScanRun] = field(default_factory=list)
    memberships: list[CustomerMembership] = field(default_factory=list)
    audit_events: list[AuditEvent] = field(default_factory=list)
    delegate_confirmations: list[GoogleWorkspaceDelegateConfirmation] = field(
        default_factory=list
    )
    group_membership_confirmations: list[GoogleWorkspaceGroupMembershipConfirmation] = field(
        default_factory=list
    )
    user_status_confirmations: list[GoogleWorkspaceUserStatusConfirmation] = field(
        default_factory=list
    )

    @property
    def credential_bearing_connector_count(self) -> int:
        return sum(config.credential_ref is not None for config in self.connector_configs)

    def counts(self) -> dict[str, int]:
        return {
            "customers": 1,
            "organizations": 1,
            "connector_configs": len(self.connector_configs),
            "credential_bearing_connector_configs": self.credential_bearing_connector_count,
            "connector_accounts": len(self.connector_accounts),
            "assessments": len(self.assessments),
            "assets": len(self.assets),
            "findings": len(self.findings),
            "dread_scores": len(self.dread_scores),
            "scan_runs": len(self.scan_runs),
            "customer_memberships": len(self.memberships),
            "audit_events_preserved_and_detached": len(self.audit_events),
            "delegate_confirmations": len(self.delegate_confirmations),
            "group_membership_confirmations": len(self.group_membership_confirmations),
            "user_status_confirmations": len(self.user_status_confirmations),
        }

    def private_manifest_entry(self) -> dict[str, Any]:
        return {
            "run_token": self.token,
            "customer_id": str(self.customer.id),
            "organization_id": str(self.organization.id),
            "records_expected_to_be_deleted": {
                "customers": [str(self.customer.id)],
                "organizations": [str(self.organization.id)],
                "connector_configs": _ids(self.connector_configs),
                "connector_accounts": _ids(self.connector_accounts),
                "assessments": _ids(self.assessments),
                "assets": _ids(self.assets),
                "findings": _ids(self.findings),
                "dread_scores": _ids(self.dread_scores),
                "scan_runs": _ids(self.scan_runs),
                "customer_memberships": _ids(self.memberships),
                "delegate_confirmations": _ids(self.delegate_confirmations),
                "group_membership_confirmations": _ids(
                    self.group_membership_confirmations
                ),
                "user_status_confirmations": _ids(self.user_status_confirmations),
            },
            "records_expected_to_be_preserved": {
                "audit_events_detached_from_customer": _ids(self.audit_events),
            },
            "connector_credential_state": [
                {
                    "connector_config_id": str(config.id),
                    "credential_reference_present": config.credential_ref is not None,
                    "service_account_metadata_present": bool(
                        config.service_account_email or config.service_account_client_id
                    ),
                }
                for config in self.connector_configs
            ],
            "expected_counts": self.counts(),
        }


@dataclass
class SyntheticDataAnalysis:
    candidates: list[CandidateSet]
    blocker_codes: list[str]
    candidate_like_customers: int
    candidate_like_organizations: int
    non_candidate_customer_organizations: int
    cross_tenant_findings: int

    @property
    def blocker_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(self.blocker_codes).items()))

    @property
    def eligible_for_manifest(self) -> bool:
        return bool(self.candidates) and not self.blocker_codes

    def aggregate_counts(self) -> dict[str, int]:
        totals: Counter[str] = Counter()
        for candidate in self.candidates:
            totals.update(candidate.counts())
        totals["candidate_like_customers"] = self.candidate_like_customers
        totals["candidate_like_organizations"] = self.candidate_like_organizations
        totals["non_candidate_customer_organizations"] = (
            self.non_candidate_customer_organizations
        )
        totals["cross_tenant_findings"] = self.cross_tenant_findings
        return dict(sorted(totals.items()))


def _connector_matches_smoke(config: ConnectorConfig) -> bool:
    return (
        config.connector_type == "google_workspace"
        and config.auth_method == "service_account_domain_wide_delegation"
        and config.display_name == "Smoke Google Workspace"
        and config.primary_domain == "smoke.example.local"
        and config.admin_subject_email == "admin@smoke.example.local"
        and config.credential_provider == "file"
        and config.credential_ref is None
        and config.service_account_email is None
        and config.service_account_client_id is None
        and config.notes == SMOKE_CONNECTOR_NOTES
        and config.status == "connection_failed"
        and config.last_error_code == "credential_reference_missing"
    )


def _assessment_matches_smoke(assessment: Assessment, token: str) -> bool:
    return (
        assessment.title == f"Smoke assessment {token}"
        and assessment.scope_summary == "API smoke test scope"
        and assessment.status == "draft"
    )


def _asset_kind(asset: Asset, token: str) -> str | None:
    if (
        asset.name == f"Smoke asset {token}"
        and asset.asset_type == "saas"
        and asset.identifier == f"smoke-{token}"
        and asset.description == "API smoke test asset"
    ):
        return "manual"
    if (
        asset.name == "Google Workspace Tenant"
        and asset.asset_type == "SaaS Platform"
        and asset.identifier == "google-workspace-mock"
        and asset.description == "Demo asset created by the mock Google Workspace scan."
    ):
        return "mock"
    return None


def _scan_run_matches_smoke(scan_run: ScanRun) -> bool:
    return (
        scan_run.connector_type == "google_workspace_mock"
        and scan_run.status == "completed"
        and scan_run.findings_created == len(GOOGLE_WORKSPACE_CHECKS)
        and scan_run.completed_at is not None
    )


def _finding_fingerprints_match(
    findings: list[Finding],
    assets: list[Asset],
    token: str,
) -> bool:
    assets_by_kind = {_asset_kind(asset, token): asset for asset in assets}
    if set(assets_by_kind) != {"manual", "mock"}:
        return False
    manual_asset = assets_by_kind["manual"]
    mock_asset = assets_by_kind["mock"]
    expected_mock_titles = {check.maps_to_finding_title for check in GOOGLE_WORKSPACE_CHECKS}

    manual_findings = [
        finding
        for finding in findings
        if finding.title == f"Smoke finding {token}"
        and finding.asset_id == manual_asset.id
        and finding.description == "API smoke test finding"
        and finding.status == "open"
        and finding.mitigation == "Validate controls"
    ]
    mock_findings = [
        finding
        for finding in findings
        if finding.title in expected_mock_titles
        and finding.asset_id == mock_asset.id
        and finding.status == "open"
    ]
    return (
        len(manual_findings) == 1
        and len(mock_findings) == len(expected_mock_titles)
        and {finding.title for finding in mock_findings} == expected_mock_titles
        and len(findings) == 1 + len(expected_mock_titles)
    )


def _load_candidate_set(
    session: Session,
    token: str,
    customer: Customer,
    organization: Organization,
) -> CandidateSet:
    connector_configs = list(
        session.scalars(
            select(ConnectorConfig).where(ConnectorConfig.organization_id == organization.id)
        ).all()
    )
    connector_accounts = list(
        session.scalars(
            select(ConnectorAccount).where(ConnectorAccount.organization_id == organization.id)
        ).all()
    )
    assessments = list(
        session.scalars(
            select(Assessment).where(Assessment.organization_id == organization.id)
        ).all()
    )
    assessment_ids = [assessment.id for assessment in assessments]
    assets = list(
        session.scalars(select(Asset).where(Asset.organization_id == organization.id)).all()
    )
    findings = (
        list(
            session.scalars(
                select(Finding).where(Finding.assessment_id.in_(assessment_ids))
            ).all()
        )
        if assessment_ids
        else []
    )
    finding_ids = [finding.id for finding in findings]
    dread_scores = (
        list(
            session.scalars(
                select(DreadScore).where(DreadScore.finding_id.in_(finding_ids))
            ).all()
        )
        if finding_ids
        else []
    )
    scan_runs = (
        list(
            session.scalars(
                select(ScanRun).where(ScanRun.assessment_id.in_(assessment_ids))
            ).all()
        )
        if assessment_ids
        else []
    )
    memberships = list(
        session.scalars(
            select(CustomerMembership).where(CustomerMembership.customer_id == customer.id)
        ).all()
    )
    audit_events = list(
        session.scalars(select(AuditEvent).where(AuditEvent.customer_id == customer.id)).all()
    )
    delegate_confirmations = list(
        session.scalars(
            select(GoogleWorkspaceDelegateConfirmation).where(
                GoogleWorkspaceDelegateConfirmation.organization_id == organization.id
            )
        ).all()
    )
    group_membership_confirmations = list(
        session.scalars(
            select(GoogleWorkspaceGroupMembershipConfirmation).where(
                GoogleWorkspaceGroupMembershipConfirmation.organization_id == organization.id
            )
        ).all()
    )
    user_status_confirmations = list(
        session.scalars(
            select(GoogleWorkspaceUserStatusConfirmation).where(
                or_(
                    GoogleWorkspaceUserStatusConfirmation.organization_id == organization.id,
                    GoogleWorkspaceUserStatusConfirmation.customer_id == customer.id,
                    GoogleWorkspaceUserStatusConfirmation.connector_config_id.in_(
                        [config.id for config in connector_configs]
                    )
                    if connector_configs
                    else False,
                )
            )
        ).all()
    )
    return CandidateSet(
        token=token,
        customer=customer,
        organization=organization,
        connector_configs=connector_configs,
        connector_accounts=connector_accounts,
        assessments=assessments,
        assets=assets,
        findings=findings,
        dread_scores=dread_scores,
        scan_runs=scan_runs,
        memberships=memberships,
        audit_events=audit_events,
        delegate_confirmations=delegate_confirmations,
        group_membership_confirmations=group_membership_confirmations,
        user_status_confirmations=user_status_confirmations,
    )


def analyze_synthetic_records(session: Session) -> SyntheticDataAnalysis:
    """Build an exact, read-only graph of smoke records and conservative blockers."""
    candidate_like_customers = list(
        session.scalars(select(Customer).where(Customer.notes == SMOKE_MARKER)).all()
    )
    candidate_like_organizations = list(
        session.scalars(select(Organization).where(Organization.description == SMOKE_MARKER)).all()
    )
    blockers: list[str] = []

    customers_by_token: dict[str, Customer] = {}
    for customer in candidate_like_customers:
        token = customer_run_token(customer)
        if token is None:
            blockers.append("customer_fingerprint_mismatch")
        elif token in customers_by_token:
            blockers.append("duplicate_customer_run_token")
        else:
            customers_by_token[token] = customer

    organizations_by_token: dict[str, Organization] = {}
    for organization in candidate_like_organizations:
        token = organization_run_token(organization)
        if token is None:
            blockers.append("organization_fingerprint_mismatch")
        elif token in organizations_by_token:
            blockers.append("duplicate_organization_run_token")
        else:
            organizations_by_token[token] = organization

    if set(customers_by_token) != set(organizations_by_token):
        blockers.append("unpaired_customer_or_organization")

    candidates: list[CandidateSet] = []
    non_candidate_customer_organizations = 0
    for token in sorted(set(customers_by_token) & set(organizations_by_token)):
        customer = customers_by_token[token]
        organization = organizations_by_token[token]
        if organization.customer_id != customer.id:
            blockers.append("customer_organization_relationship_mismatch")
            continue

        customer_organizations = list(
            session.scalars(
                select(Organization).where(Organization.customer_id == customer.id)
            ).all()
        )
        extras = [item for item in customer_organizations if item.id != organization.id]
        non_candidate_customer_organizations += len(extras)
        if extras:
            blockers.append("mixed_customer_organizations")

        candidate = _load_candidate_set(session, token, customer, organization)
        candidates.append(candidate)

        if len(candidate.connector_configs) != 1 or not all(
            _connector_matches_smoke(config) for config in candidate.connector_configs
        ):
            blockers.append("connector_config_fingerprint_mismatch")
        if candidate.credential_bearing_connector_count:
            blockers.append("credential_reference_present")
        if any(
            config.service_account_email or config.service_account_client_id
            for config in candidate.connector_configs
        ):
            blockers.append("credential_metadata_present")
        if candidate.connector_accounts:
            blockers.append("unexpected_connector_accounts")
        if len(candidate.assessments) != 1 or not all(
            _assessment_matches_smoke(assessment, token)
            for assessment in candidate.assessments
        ):
            blockers.append("assessment_fingerprint_mismatch")
        if len(candidate.assets) != 2 or {
            _asset_kind(asset, token) for asset in candidate.assets
        } != {"manual", "mock"}:
            blockers.append("asset_fingerprint_mismatch")
        if not _finding_fingerprints_match(candidate.findings, candidate.assets, token):
            blockers.append("finding_fingerprint_mismatch")
        if len(candidate.dread_scores) != len(candidate.findings):
            blockers.append("dread_score_relationship_mismatch")
        if len(candidate.scan_runs) != 1 or not all(
            _scan_run_matches_smoke(scan_run) for scan_run in candidate.scan_runs
        ):
            blockers.append("scan_run_fingerprint_mismatch")
        if candidate.memberships:
            blockers.append("unexpected_customer_memberships")
        if (
            candidate.delegate_confirmations
            or candidate.group_membership_confirmations
            or candidate.user_status_confirmations
        ):
            blockers.append("unexpected_google_mutation_confirmations")

    candidate_asset_ids = [asset.id for candidate in candidates for asset in candidate.assets]
    candidate_assessment_ids = [
        assessment.id for candidate in candidates for assessment in candidate.assessments
    ]
    cross_tenant_findings = 0
    if candidate_asset_ids:
        cross_tenant_findings = _count(
            session,
            select(func.count())
            .select_from(Finding)
            .where(
                Finding.asset_id.in_(candidate_asset_ids),
                not_(Finding.assessment_id.in_(candidate_assessment_ids)),
            ),
        )
        if cross_tenant_findings:
            blockers.append("cross_tenant_finding_asset_relationship")

    return SyntheticDataAnalysis(
        candidates=candidates,
        blocker_codes=blockers,
        candidate_like_customers=len(candidate_like_customers),
        candidate_like_organizations=len(candidate_like_organizations),
        non_candidate_customer_organizations=non_candidate_customer_organizations,
        cross_tenant_findings=cross_tenant_findings,
    )


def manifest_uuid_sets(analysis: SyntheticDataAnalysis) -> dict[str, list[UUID]]:
    """Return exact identifiers for rollback-only validation; never a deletion command."""
    return {
        "customers": [candidate.customer.id for candidate in analysis.candidates],
        "organizations": [candidate.organization.id for candidate in analysis.candidates],
        "connector_configs": [
            item.id for candidate in analysis.candidates for item in candidate.connector_configs
        ],
        "connector_accounts": [
            item.id for candidate in analysis.candidates for item in candidate.connector_accounts
        ],
        "assessments": [
            item.id for candidate in analysis.candidates for item in candidate.assessments
        ],
        "assets": [item.id for candidate in analysis.candidates for item in candidate.assets],
        "findings": [item.id for candidate in analysis.candidates for item in candidate.findings],
        "dread_scores": [
            item.id for candidate in analysis.candidates for item in candidate.dread_scores
        ],
        "scan_runs": [
            item.id for candidate in analysis.candidates for item in candidate.scan_runs
        ],
        "customer_memberships": [
            item.id for candidate in analysis.candidates for item in candidate.memberships
        ],
        "audit_events": [
            item.id for candidate in analysis.candidates for item in candidate.audit_events
        ],
    }
