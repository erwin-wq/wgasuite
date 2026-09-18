# Roadmap

AdminDeck is in early development. This roadmap describes direction, not delivery dates or
commitments. The README is authoritative for current capabilities.

## Foundations available today

- React/TypeScript frontend and FastAPI/PostgreSQL backend
- Alembic migration chain
- development authentication and role foundations
- customers, organizations and customer memberships
- backend customer data scoping
- assessments, assets, findings and DREAD scoring
- report view and browser/PDF printing flow
- selected support-access audit events
- read-only Platform Admin overview
- connector configuration metadata
- Google Workspace check catalog and mock scans

## Near-term quality and security

- add focused frontend automated tests
- expand audit coverage for relevant write operations
- improve authentication and session security beyond the development foundation
- document production deployment, backups, monitoring and recovery
- add security headers and rate limiting
- complete public project governance and choose an open-source license

## Product workflow

- clearer Customer Portal and Platform Admin Portal separation
- assessment status workflows, filtering and sorting
- improved report export and management views
- user invitation and account lifecycle foundations
- explicit support workflows with customer-visible auditability

## Google Workspace integration

Real Google Workspace access is not implemented. Future work should proceed with least-privilege,
read-only scopes first and secure credential storage before enabling operational changes.

Potential areas:

- connector health and consent validation
- read-only tenant and user inventory
- security posture checks backed by real APIs
- user and group administration
- organizational-unit and license administration
- ChromeOS and device administration
- Google Workspace audit/event workflows

## Integrations and operations

- secure webhooks and ticketing integrations
- management dashboards
- operational alerts and scheduled workflows
- production-ready SSO and identity-provider integration

AdminDeck will remain independent software and must not imply affiliation with or endorsement by
Google.
