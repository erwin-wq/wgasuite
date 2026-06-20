from app.connectors.base import ConnectorFinding, ConnectorResult


class MockGoogleWorkspaceConnector:
    connector_type = "google_workspace_mock"

    def run(self) -> ConnectorResult:
        findings = [
            ConnectorFinding(
                title="[Mock Google Workspace] MFA not enforced for all users",
                description=(
                    "Fictieve controle: 18 van 120 demo users hebben geen verplichte MFA. "
                    "Dit simuleert een identity hardening gap."
                ),
                impact="Accounts zonder MFA hebben een verhoogd risico op account takeover.",
                recommendation="Require MFA for all users and enforce conditional access policies.",
                category="Identity and access",
                dread_score={
                    "damage": 8,
                    "reproducibility": 8,
                    "exploitability": 7,
                    "affected_users": 8,
                    "discoverability": 7,
                },
            ),
            ConnectorFinding(
                title="[Mock Google Workspace] Too many super admins",
                description=(
                    "Fictieve controle: de demo tenant heeft 7 super admin accounts. "
                    "Least privilege is hierdoor niet strak ingericht."
                ),
                impact="Te veel super admins vergroten de impact van credential misuse.",
                recommendation=(
                    "Reduce super admins to a minimal break-glass set and review roles monthly."
                ),
                category="Privileged access",
                dread_score={
                    "damage": 9,
                    "reproducibility": 7,
                    "exploitability": 6,
                    "affected_users": 9,
                    "discoverability": 6,
                },
            ),
            ConnectorFinding(
                title="[Mock Google Workspace] External sharing enabled",
                description=(
                    "Fictieve controle: Drive sharing to external domains is broadly allowed. "
                    "Dit simuleert een data exposure risico."
                ),
                impact="Gevoelige documenten kunnen buiten de organisatie worden gedeeld.",
                recommendation=(
                    "Limit external sharing and require trusted domains or approval workflows."
                ),
                category="Data protection",
                dread_score={
                    "damage": 7,
                    "reproducibility": 8,
                    "exploitability": 6,
                    "affected_users": 7,
                    "discoverability": 7,
                },
            ),
            ConnectorFinding(
                title="[Mock Google Workspace] Inactive users detected",
                description=(
                    "Fictieve controle: 11 demo accounts zijn langer dan 90 dagen inactief. "
                    "Deze accounts blijven toegang houden."
                ),
                impact="Inactieve accounts kunnen misbruikt worden zonder dat dit snel opvalt.",
                recommendation="Disable inactive users and automate joiner/mover/leaver reviews.",
                category="Lifecycle management",
                dread_score={
                    "damage": 6,
                    "reproducibility": 7,
                    "exploitability": 5,
                    "affected_users": 5,
                    "discoverability": 6,
                },
            ),
            ConnectorFinding(
                title="[Mock Google Workspace] Weak password policy",
                description=(
                    "Fictieve controle: password policy settings zijn ruim ingesteld en missen "
                    "voldoende complexity guidance."
                ),
                impact="Zwakke wachtwoorden verhogen de kans op credential attacks.",
                recommendation="Tighten password policy and prefer phishing-resistant MFA.",
                category="Authentication policy",
                dread_score={
                    "damage": 6,
                    "reproducibility": 8,
                    "exploitability": 6,
                    "affected_users": 7,
                    "discoverability": 6,
                },
            ),
            ConnectorFinding(
                title="[Mock Google Workspace] Legacy IMAP/POP access enabled",
                description=(
                    "Fictieve controle: legacy mail protocols are enabled for a subset of users. "
                    "Deze protocollen passen slecht bij moderne access controls."
                ),
                impact="Legacy access can bypass stronger sign-in controls in some environments.",
                recommendation="Disable IMAP/POP where possible and monitor exceptions.",
                category="Mail security",
                dread_score={
                    "damage": 7,
                    "reproducibility": 7,
                    "exploitability": 7,
                    "affected_users": 6,
                    "discoverability": 6,
                },
            ),
            ConnectorFinding(
                title="[Mock Google Workspace] Third-party OAuth apps not reviewed",
                description=(
                    "Fictieve controle: 24 OAuth apps hebben toegang tot demo workspace data "
                    "zonder recente security review."
                ),
                impact=(
                    "Ongecontroleerde OAuth apps kunnen data uitlezen of persistent toegang houden."
                ),
                recommendation=(
                    "Review OAuth app access and block untrusted or unused applications."
                ),
                category="Third-party access",
                dread_score={
                    "damage": 8,
                    "reproducibility": 7,
                    "exploitability": 6,
                    "affected_users": 8,
                    "discoverability": 7,
                },
            ),
        ]
        return ConnectorResult(
            connector_type=self.connector_type,
            summary=(
                "Mock Google Workspace scan completed. Demo findings were created; "
                "no real Google data was accessed."
            ),
            findings=findings,
        )
