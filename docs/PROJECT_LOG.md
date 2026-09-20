# WGASuite Engineering History

This document records significant product, architecture, security and release-engineering
decisions. It is intentionally a curated history rather than a transcript of individual development
sessions. DREAD references describe the risk-assessment methodology and compatibility-sensitive
data model; WGASuite is the current product name.

## 2026-09-20 — v0.2 product strategy

- Competitive and product-gap research was promoted into a concise public product strategy without
  copying time-sensitive competitor statistics into the repository.
- Direct official Google APIs were selected as the primary integration architecture. GAM remains a
  respected coverage benchmark; it is not the WGASuite execution engine or part of the `v0.2.0`
  roadmap. An isolated optional adapter may be reconsidered for long-tail workflows later.
- The first integration vertical was defined as read-only Google Workspace user inventory with
  search, detail and related group membership context. Guarded suspend/restore follows only after
  the read path and its security boundaries are proven.
- The `v0.2.0` roadmap was focused on eight dependency-ordered deliverables: production identity,
  secure connector credentials, connector validation, a direct Directory API foundation, user
  inventory, group membership context, guarded suspend/restore and selected evidence-based checks.
- README positioning remains explicit that `v0.1.0` is early, mock-only for Google Workspace and
  not production-ready. Architecture and original PRD documentation now link to the strategy as
  the source of truth for future integration direction.
- This documentation-only change was validated with Markdown link checks, terminology and claim
  review, `git diff --check`, and repository status checks. No application code, dependencies,
  database schema or migrations changed.

Next step: implement the roadmap through separately reviewed vertical slices, beginning with the
production identity and secure connector trust boundaries rather than Google administration code.

## 2026-09-19 — Private GitHub staging and public-release hardening

- The validated open-source release candidate was staged in a private GitHub repository while the
  existing GitLab remote and history were preserved.
- GitHub community files, CI, repository metadata, dependency security features and Apache-2.0
  license detection were verified. CI retained separate `Backend checks` and `Frontend checks`.
- Docker development ports for PostgreSQL, the API and the frontend were restricted to
  `127.0.0.1`; internal Compose service networking remained available.
- Repository guidance was separated by audience: `CONTRIBUTING.md` covers the human contribution
  workflow, `AGENTS.md` contains coding-agent guidance and `docs/DEVELOPMENT_RULES.md` contains
  durable technical constraints.
- Deprecated Node.js 20 GitHub Actions were upgraded to supported releases without changing job
  names, workflow permissions or validation behavior.
- Backend dependency intent remains in the top-level requirements files, while separate generated
  Python 3.12 production and development constraint locks make Docker, CI and contributor installs
  reproducible without introducing a new package manager.
- A final public-source review corrected stale portal-status documentation and found no release
  blocker in tracked source, repository metadata, licensing or the focused source-security review.
- The release-hardening validation completed with 99 backend tests, Ruff, Python compilation,
  frontend lint/build, zero npm audit findings, Docker smoke testing and clean Gitleaks and
  TruffleHog scans.

The staging repository remained private. Branch protection and private vulnerability reporting
were left as explicit repository-administration steps for the eventual public launch.

## 2026-09-18 — WGASuite open-source release preparation

### Final product identity

- The final public product name became WGASuite, with the description "Open-source administration
  and security for Google Workspace."
- AdminDeck is retained only as historical context and in the one-time browser-storage migration
  key `admindeck.authToken:v1` used to move existing local sessions to `wgasuite.authToken`.
- DREAD terminology remains in scoring, reports, schemas, API fields and database identifiers
  because it names the risk methodology and preserves compatibility.
- The internal PostgreSQL database and user name `dread` were also retained to avoid breaking
  existing development databases and migration history.

### Open-source repository foundation

- `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, issue forms, a pull-request template and GitHub
  Actions CI were added and aligned with the project's early-development status.
- Documentation distinguishes implemented assessment and administration foundations from mock-only
  Google Workspace checks and planned real integrations.
- The standard Apache License 2.0 text was added as `LICENSE`; no copyright holder was invented.
- Frontend installs use `package-lock.json` and `npm ci`. A focused lockfile refresh remediated six
  development-tooling audit findings through compatible transitive updates, leaving both full and
  production npm audits at zero findings without a major upgrade.

### Credential and authentication hardening

- Built-in frontend login credentials and visible demo credential instructions were removed.
- PostgreSQL, token-signing and development-admin secrets became explicit environment
  configuration. Docker Compose fails closed when required secrets are absent.
- Backend settings use secret-aware types, validate signing-key strength and construct the Compose
  database URL from separately supplied PostgreSQL fields without duplicating the password.
- Development-admin creation is an explicit, idempotent setup operation. Passwords are hashed
  before persistence, are never returned through the API and are not logged.
- Smoke testing reuses the configured development account without printing its password.
- Fixed credentials remain only in isolated automated test fixtures.

### Legacy credential remediation

- Historical migration `0003_auth_foundation.py` remains unchanged as part of the immutable
  migration record.
- Migration `0009_public_auth_cleanup.py` detects the historical seeded account only when its
  stored password hash still matches the legacy seed. It then deactivates the account and replaces
  the hash with a non-verifiable marker.
- An account whose password was already rotated is left unchanged. Downgrade does not restore the
  unsafe credential.
- Tests covered a fresh migration chain, an existing installation at `0008` with the old seed and
  an installation where the credential had already been rotated.

### Release validation

- The release candidate passed 99 backend tests, Ruff, Python compilation, Alembic head checks,
  frontend lint/build and both npm audits.
- Docker startup, PostgreSQL health, migrations, development-admin setup and the complete API smoke
  flow passed.
- Gitleaks found no secrets in the reachable Git history or tracked source. TruffleHog found no
  verified or unverified secrets in the source snapshot.
- `.env`, virtual environments, dependency directories, build output, caches and generated scan
  reports remained untracked.

## 2026-06-21 — Tenant isolation, auditability and platform operations

### Customer memberships and roles

- Migration `0007_customer_memberships.py` introduced customer memberships, customer roles and
  active/inactive membership state.
- Platform roles became `platform_admin` and `platform_support`; customer roles became
  `customer_admin`, `customer_user` and `customer_viewer`.
- Platform administrators received membership-management endpoints, while `/auth/me` began
  returning the current user's memberships.

### Customer data scoping

- Central authorization helpers enforce active memberships and customer read, write, admin and
  connector-operation access.
- Customer, organization, assessment, report, asset, finding, connector and scan-run endpoints were
  scoped according to the role model.
- Platform support is read-only apart from the explicitly permitted connector test operation;
  customer viewers are read-only and inactive memberships grant no access.
- Dedicated tests cover cross-customer isolation and role boundaries.

### Audit log foundation

- Migration `0008_audit_events.py` added structured audit events for actor, customer, action,
  object, outcome, reason, metadata and timestamp.
- Audit metadata is sanitized before persistence to remove sensitive fields such as passwords,
  tokens, secrets, private keys and API keys.
- Platform roles and customer administrators can read the audit records permitted by their scope.
  Relevant support reads, report views and connector operations generate audit events.

### Platform Admin overview

- A read-only overview was added for `platform_admin` and `platform_support`, with totals, customer
  summaries, connector status, recent scan runs and recent audit events.
- The overview does not expose connector secrets, permit customer impersonation or introduce
  administrative writes.
- The implementation brought the backend suite to 99 tests and extended the API smoke flow to
  verify the platform overview.

## 2026-06-20 — Authentication, customer administration and mock Workspace foundations

### Authentication and customer administration

- Migration `0003_auth_foundation.py` added the initial user/authentication foundation and protected
  API routes. This development authentication model was never presented as production identity
  management.
- Migration `0004_customer_admin_foundation.py` added customer administration and customer-linked
  organizations while preserving the assessment workflow.
- Subsequent public-security work remediated the historical development credential through the new
  `0009` migration rather than rewriting `0003`.

### Mock Google Workspace workflow

- Migration `0005_mock_google_workspace_scan.py` introduced scan runs and a mock scanner that
  creates fictional findings from an in-repository check catalog.
- The catalog grew to seven security checks with implementation status and remediation guidance.
- Migration `0006_connector_config.py` added metadata-only Google Workspace connector records and
  protected CRUD/test endpoints.
- Connector testing deliberately returns `not_implemented`. No Google API, OAuth flow, token,
  private key or service-account JSON is used or stored.

### Application navigation and portal direction

- The frontend evolved from a single workspace into Dashboard, Customer context, Organizations,
  Assessment workspace, Google Workspace and Reports sections.
- Portal and role design documented the intended separation between customer users and platform
  administration, including least-privilege access and support audit requirements.
- The dashboard and connector workflow were clarified so mock data and planned real integrations
  cannot be mistaken for production Google Workspace access.

## 2026-06-19 — Initial application foundation

### Architecture and data model

- The initial stack used FastAPI, SQLAlchemy, Alembic and PostgreSQL for the backend, with React,
  TypeScript and Vite for the frontend.
- Migration `0001_initial_schema.py` established the first schema. Migration
  `0002_backend_core_crud.py` added the core customer, organization, assessment, asset, finding and
  DREAD score workflow.
- DREAD scoring validates five dimensions from 0 through 10, calculates the average score and maps
  it to a risk level.
- A browser-printable assessment report was added with assets, findings, DREAD dimensions, totals
  and risk levels.

### Development and frontend foundations

- Docker Compose, environment validation, Alembic migration commands and an API smoke script were
  established for local development.
- The frontend gained the initial dashboard, responsive navigation, customer/assessment workflow,
  finding entry and reporting interface.
- Project documentation established the architecture, product requirements, roadmap and durable
  development rules.

## Continuing constraints

- WGASuite remains an early-development, pre-production project.
- Real Google Workspace API access and production identity management are not implemented.
- Historical Alembic migrations are immutable; compatibility or security corrections require new
  migrations.
- Customer scoping, least privilege, auditability and secret-free source control remain mandatory
  design constraints.
