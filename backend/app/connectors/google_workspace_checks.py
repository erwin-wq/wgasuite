from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class GoogleWorkspaceCheckDefinition:
    check_id: str
    title: str
    category: str
    risk_statement: str
    description: str
    recommendation: str
    mock_status: str
    data_source_hint: str
    future_google_api_hint: str
    default_dread_score: dict[str, int]
    default_risk_level: str
    maps_to_finding_title: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


GOOGLE_WORKSPACE_MOCK_PREFIX = "[Mock Google Workspace]"

GOOGLE_WORKSPACE_CHECKS: tuple[GoogleWorkspaceCheckDefinition, ...] = (
    GoogleWorkspaceCheckDefinition(
        check_id="GW-MFA-001",
        title="MFA not enforced for all users",
        category="Identity and access",
        risk_statement="Accounts zonder MFA hebben een verhoogd risico op account takeover.",
        description=(
            "Fictieve controle: 18 van 120 demo users hebben geen verplichte MFA. "
            "Dit simuleert een identity hardening gap."
        ),
        recommendation="Require MFA for all users and enforce conditional access policies.",
        mock_status="mock_only",
        data_source_hint="User authentication and MFA enrollment settings",
        future_google_api_hint="Admin SDK Directory API and Reports API login activity",
        default_dread_score={
            "damage": 8,
            "reproducibility": 8,
            "exploitability": 7,
            "affected_users": 8,
            "discoverability": 7,
        },
        default_risk_level="High",
        maps_to_finding_title=f"{GOOGLE_WORKSPACE_MOCK_PREFIX} MFA not enforced for all users",
    ),
    GoogleWorkspaceCheckDefinition(
        check_id="GW-ADMIN-001",
        title="Too many super admins",
        category="Privileged access",
        risk_statement="Te veel super admins vergroten de impact van credential misuse.",
        description=(
            "Fictieve controle: de demo tenant heeft 7 super admin accounts. "
            "Least privilege is hierdoor niet strak ingericht."
        ),
        recommendation="Reduce super admins to a minimal break-glass set and review roles monthly.",
        mock_status="mock_only",
        data_source_hint="Admin role assignments and privileged user inventory",
        future_google_api_hint="Admin SDK Directory API role assignments",
        default_dread_score={
            "damage": 9,
            "reproducibility": 7,
            "exploitability": 6,
            "affected_users": 9,
            "discoverability": 6,
        },
        default_risk_level="High",
        maps_to_finding_title=f"{GOOGLE_WORKSPACE_MOCK_PREFIX} Too many super admins",
    ),
    GoogleWorkspaceCheckDefinition(
        check_id="GW-SHARING-001",
        title="External sharing enabled",
        category="Data protection",
        risk_statement="Gevoelige documenten kunnen buiten de organisatie worden gedeeld.",
        description=(
            "Fictieve controle: Drive sharing to external domains is broadly allowed. "
            "Dit simuleert een data exposure risico."
        ),
        recommendation="Limit external sharing and require trusted domains or approval workflows.",
        mock_status="mock_only",
        data_source_hint="Drive sharing settings and external sharing audit events",
        future_google_api_hint="Drive API, Drive Activity API and Admin SDK Reports API",
        default_dread_score={
            "damage": 7,
            "reproducibility": 8,
            "exploitability": 6,
            "affected_users": 7,
            "discoverability": 7,
        },
        default_risk_level="High",
        maps_to_finding_title=f"{GOOGLE_WORKSPACE_MOCK_PREFIX} External sharing enabled",
    ),
    GoogleWorkspaceCheckDefinition(
        check_id="GW-USERS-001",
        title="Inactive users detected",
        category="Lifecycle management",
        risk_statement="Inactieve accounts kunnen misbruikt worden zonder dat dit snel opvalt.",
        description=(
            "Fictieve controle: 11 demo accounts zijn langer dan 90 dagen inactief. "
            "Deze accounts blijven toegang houden."
        ),
        recommendation="Disable inactive users and automate joiner/mover/leaver reviews.",
        mock_status="mock_only",
        data_source_hint="User last login timestamps and account suspension state",
        future_google_api_hint="Admin SDK Directory API users and Reports API login events",
        default_dread_score={
            "damage": 6,
            "reproducibility": 7,
            "exploitability": 5,
            "affected_users": 5,
            "discoverability": 6,
        },
        default_risk_level="Medium",
        maps_to_finding_title=f"{GOOGLE_WORKSPACE_MOCK_PREFIX} Inactive users detected",
    ),
    GoogleWorkspaceCheckDefinition(
        check_id="GW-AUTH-001",
        title="Weak password policy",
        category="Authentication policy",
        risk_statement="Zwakke wachtwoorden verhogen de kans op credential attacks.",
        description=(
            "Fictieve controle: password policy settings zijn ruim ingesteld en missen "
            "voldoende complexity guidance."
        ),
        recommendation="Tighten password policy and prefer phishing-resistant MFA.",
        mock_status="mock_only",
        data_source_hint="Authentication policy and password policy settings",
        future_google_api_hint="Admin console settings export or future policy API where available",
        default_dread_score={
            "damage": 6,
            "reproducibility": 8,
            "exploitability": 6,
            "affected_users": 7,
            "discoverability": 6,
        },
        default_risk_level="High",
        maps_to_finding_title=f"{GOOGLE_WORKSPACE_MOCK_PREFIX} Weak password policy",
    ),
    GoogleWorkspaceCheckDefinition(
        check_id="GW-LEGACY-001",
        title="Legacy IMAP/POP access enabled",
        category="Mail security",
        risk_statement="Legacy access can bypass stronger sign-in controls in some environments.",
        description=(
            "Fictieve controle: legacy mail protocols are enabled for a subset of users. "
            "Deze protocollen passen slecht bij moderne access controls."
        ),
        recommendation="Disable IMAP/POP where possible and monitor exceptions.",
        mock_status="mock_only",
        data_source_hint="Gmail service settings and user protocol access exceptions",
        future_google_api_hint="Admin SDK and Gmail settings APIs where policy access is available",
        default_dread_score={
            "damage": 7,
            "reproducibility": 7,
            "exploitability": 7,
            "affected_users": 6,
            "discoverability": 6,
        },
        default_risk_level="High",
        maps_to_finding_title=f"{GOOGLE_WORKSPACE_MOCK_PREFIX} Legacy IMAP/POP access enabled",
    ),
    GoogleWorkspaceCheckDefinition(
        check_id="GW-OAUTH-001",
        title="Third-party OAuth apps not reviewed",
        category="Third-party access",
        risk_statement=(
            "Ongecontroleerde OAuth apps kunnen data uitlezen of persistent toegang houden."
        ),
        description=(
            "Fictieve controle: 24 OAuth apps hebben toegang tot demo workspace data "
            "zonder recente security review."
        ),
        recommendation="Review OAuth app access and block untrusted or unused applications.",
        mock_status="mock_only",
        data_source_hint="Third-party app grants, OAuth scopes and app access control settings",
        future_google_api_hint="Admin SDK Reports Token events and app access control inventory",
        default_dread_score={
            "damage": 8,
            "reproducibility": 7,
            "exploitability": 6,
            "affected_users": 8,
            "discoverability": 7,
        },
        default_risk_level="High",
        maps_to_finding_title=(
            f"{GOOGLE_WORKSPACE_MOCK_PREFIX} Third-party OAuth apps not reviewed"
        ),
    ),
)


def list_google_workspace_checks() -> list[GoogleWorkspaceCheckDefinition]:
    return list(GOOGLE_WORKSPACE_CHECKS)
