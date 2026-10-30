# WGASuite

**Open-source administration and security for Google Workspace.**

WGASuite is an open-source web platform for Google Workspace administration, security checks,
assessments, and operational workflows. It aims to make common administration and security tasks
more approachable through a web interface instead of requiring every workflow to be performed in
an admin console or custom script.

> **Project status:** early development / pre-release. The current repository provides a working
> local foundation, service-account authentication/client infrastructure, a real read-only
> Google Workspace connection test, paginated user directory, exact user and alias lookup,
> read-only Organizational Units hierarchy, verified user-to-group context, and guarded Gmail
> mailbox delegation and Google Groups
> direct-membership management. This remains
> pre-production software.

WGASuite is an independent open-source project and is not affiliated with or endorsed by Google.

## Overview

Google Workspace teams often combine the Google Admin console, API scripts and command-line tools
to operate their environments. WGASuite is exploring a focused web-based layer for those
workflows, with customer scoping, security assessment data and auditable operational context in one
application.

The default interface now focuses on working customer context, connection management, exact
Directory user browsing and exact user/alias lookup, guarded Gmail delegate changes, and
customer-scoped Google Groups membership administration. The earlier assessment workflow and mock Google Workspace security
checks remain in the codebase for future evidence-backed work, but are hidden from standard
navigation. WGASuite must not yet be treated as a production Google Workspace management platform.

## Current capabilities

Implemented today:

- local development authentication with signed bearer tokens and environment-configured
  credentials;
- platform roles and customer memberships;
- customer and organization context with backend-enforced customer data scoping;
- assessments, assets, findings and DREAD risk scoring;
- assessment reports suitable for browser printing or saving as PDF;
- support-access audit events for selected customer, connector, scan and report reads;
- a read-only Platform Admin overview for platform administrators and support roles;
- Google Workspace connector configuration metadata and status overview;
- a tenant-scoped file credential provider plus reusable service-account Domain-Wide Delegation
  and explicitly scoped Google API client factories;
- a real, organization-scoped Admin SDK Directory API connection test with persisted status and
  sanitized audit/error reporting;
- exact, read-only Google Directory user lookup by primary email or user alias, with tenant-scoped
  authorization and safe account details;
- read-only, customer-scoped Directory user listing with server-side search and filters, supported
  sorting, opaque-token pagination, and selection into the exact user detail workflow;
- read-only, customer-scoped Organizational Units hierarchy and identifier-based details, with
  fail-closed parent/cycle validation and no persisted Directory data;
- bounded, read-only reverse group membership pages for a canonical user, with current-customer
  ownership and direct MEMBER/MANAGER/OWNER role verification;
- Gmail mailbox delegate listing plus explicit-preview, one-time-confirmation create/remove
  operations for authorized administrators, with owner impersonation and structured auditing;
- customer-ID-scoped Google Groups search/details, direct-member pagination, and confirmed add or
  remove operations for existing internal users, with read-only reconciliation after ambiguous
  writes;
- customer-admin-only Google Workspace user suspension and safe reactivation of verified
  administrator-suspended accounts, with protected-admin checks, one-time confirmation and
  read-only reconciliation after ambiguous writes;
- a catalog of Google Workspace security checks;
- mock scan runs, generated demo findings and recent scan-run history.

The assessment and mock-scan capabilities above are preserved development foundations. They are
not shown in the standard administration interface and must not be interpreted as live Workspace
security evidence.

Mock/demo-only today:

- Google Workspace scans use fictitious local data;
- all check-catalog entries have `mock_only` status;
- generated findings demonstrate the assessment and DREAD reporting flow only.

The standard navigation contains Dashboard, Customer Context, Organizations, Google Workspace and,
for authorized platform roles, Platform Admin. A development-only demonstration flag can expose the
preserved assessment screens locally; it is disabled by default and ignored by production builds.

Not implemented today:

- unrestricted or bulk Google Workspace user updates, deleted-user recovery, bulk export, group
  creation/deletion/role changes, Gmail message access or broader Gmail settings administration;
- OAuth admin-consent authentication or external cloud secret-manager integrations;
- production identity management, SSO, account recovery or hardened session management;
- unrestricted user/group administration, ChromeOS/device administration, Organizational Unit
  create/update/delete and user/device movement, or license administration;
- a complete production deployment and operations model.

## Google Workspace status

WGASuite provides a five-step connection wizard and can perform a real connection test through
`admin.directory_v1.users.get` for the
configured delegated administrator, using only the
`https://www.googleapis.com/auth/admin.directory.user.readonly` scope. The result and timestamp are
persisted, while the returned Google profile is discarded. Connector records store only non-secret
metadata and safe service-account identifiers; service-account JSON is stored only in a protected,
backend-only credential volume (or an operator-provisioned read-only file), never the database or
API. Credential upload is customer-admin-only.

Authorized administrators can also perform an exact `users.get` lookup using either a primary
email address or user alias. The result shows the canonical user, aliases, account state,
organizational unit and mailbox-setup state when Google supplies them. Profiles are not persisted,
searched addresses are not written to lookup audit metadata, and Group aliases are intentionally
outside this MVP. The same existing read-only Directory scope is used. After lookup,
administrators can load the selected user's Gmail delegates. Gmail calls impersonate the
canonical mailbox owner—not the connector administrator—and use `gmail.settings.basic` for
listing or `gmail.settings.sharing` for create/delete. Writes require a server-issued,
short-lived, single-use confirmation after canonical owner/delegate revalidation. If Google does
not return a reliable mutation response, WGASuite never resubmits the write: it can only reconcile
the current state through bounded, read-only delegate-list calls. The mock scanner remains entirely
local and fictional.

The **User Directory** uses `users.list(customer=<verified customerId>)`, `projection=basic`, and
`viewType=admin_view` with the same read-only Directory scope. It supports Google-backed search,
account/admin/archive and organizational-unit filters, email/given/family-name ordering, page sizes
of 25, 50 or 100, and opaque next-page tokens. Results can include users from every verified domain
in the customer and are not persisted. Google does not provide a total result count, and page
tokens may expire. Selecting a result opens the existing exact lookup rather than expanding the
list response or granting any write capability. The unified detail also lists bounded pages of
verified direct group memberships and can open a selected group in the existing Groups tool.

The **Organizational Units** tool verifies the immutable Google customer ID through the configured
delegated administrator, then calls `orgunits.list` with `type=allIncludingParent` and the
least-privilege `admin.directory.orgunit.readonly` scope. It normalizes unordered results into a
stable expandable hierarchy, rejects duplicate, orphaned or cyclic structures, and exposes a
separate identifier-only `orgunits.get` endpoint. OU data is never persisted or cached between
customers. Create, rename, move, delete and user/device movement remain unavailable.

Reverse membership discovery calls `groups.list(userKey=<immutable user ID>)`. Because Google does
not permit `userKey` and `customer` together, every candidate is separately matched by ID and
primary email through an exact `groups.list(customer=<verified customerId>)` query before
`members.get` establishes a direct role. External candidates and indirect-only memberships are
omitted with page-level counts. Pages are limited to 10 or 25 candidates and at most 50 ownership
and membership verification calls; no tenant-wide scan, membership cache or shadow directory is
created. The response remains explicit about verification and preserves Google's opaque
continuation token, including when filtering leaves an empty page. This path uses only the existing
user and group read-only scopes and never invokes a group mutation.

The **Groups** tool searches with `groups.list(customer=<verified customerId>)`, so secondary-domain
groups remain in tenant scope without relying on email suffixes. It shows group details and direct
members only. Existing internal users may be added as `MEMBER`; direct internal non-owner members
may be removed after a server-issued, one-time confirmation. Nested, external, customer-wide,
owner, dynamic and other unsupported memberships remain visible but read-only. Read and write
clients use separate `admin.directory.group.readonly` and `admin.directory.group.member` scopes.
Ambiguous writes are never replayed and can only be checked with bounded direct-member reads.

The central user detail also allows customer administrators to suspend an eligible standard user
or reactivate a user only when Google reports an administrator-controlled suspension. Super and
delegated administrators, the configured DWD administrator, the identifiable acting administrator,
archived/deleted accounts, configured service identities and unknown or Google-enforced suspension
reasons are blocked server-side. Preview creates an actor/customer/organization/connector/user/
action/state-bound five-minute confirmation whose token is stored only as a digest. Confirmation
revalidates the current account and sends one `users.update` request by immutable Google user ID
with only `{"suspended": true}` or `{"suspended": false}` and `num_retries=0`. Ambiguous responses
are never replayed; bounded `users.get` calls using the read-only scope can verify only the current
state. This capability requires separately authorizing
`https://www.googleapis.com/auth/admin.directory.user`; the existing read-only connection test does
not verify write permission. Suspension restricts service access without deleting data and license
charges may continue. Reactivation is not deleted-user recovery.

See [Google Workspace connector](docs/GOOGLE_WORKSPACE_CONNECTOR.md) for setup, scope,
security and live-verification instructions, and [mutation safety](docs/MUTATION_SAFETY.md) for the
shared confirmation, single-execution, outcome and audit contract. Gmail delegation cannot read or
modify messages, and Groups management cannot create/delete groups, change roles or perform bulk
operations.

After a successful connection, the Google Workspace page shows a compact persisted connection
status and provides **Users & aliases**, **Groups**, and **Organizational Units** administration
tabs. The users area opens on
the paginated Directory and retains a separate exact lookup view. Select **Manage
connection** to reopen the existing five-step wizard. Unconfigured organizations show the wizard
prominently, while failed connectors show their persisted sanitized failure and an inspection
action. The page never tests Google automatically on load.

## Screenshots

Screenshots have not been added yet. When representative UI captures are available, place them in
`docs/screenshots/` and reference them here. Do not use screenshots containing real tenant names,
email addresses, credentials or customer data.

## Architecture

- React 18 and TypeScript frontend built with Vite 6
- FastAPI backend on Python 3.12
- SQLAlchemy data access and Pydantic request/response models
- PostgreSQL 16 for local persistent storage
- Alembic migration chain
- REST API with development bearer-token authentication
- Docker Compose local environment
- GitLab CI and GitHub Actions checks

The backend currently keeps assessment and administration foundations in one API. PostgreSQL names
such as the default development database/user `dread` and DREAD schema fields are retained for
backwards compatibility; they do not represent the WGASuite product name.

## Requirements

Recommended local setup:

- Docker Engine with Docker Compose
- GNU Make
- Node.js 22 and npm for host-side frontend checks
- Python 3.12 for host-side backend checks

The Docker workflow is the simplest way to run the full stack.

## Quick start

Clone the repository and create local configuration:

```sh
git clone YOUR_REPOSITORY_URL wgasuite
cd wgasuite
cp .env.example .env
```

Edit `.env` and replace every `replace-with-...` placeholder. Choose unique local values for the
database password, signing key and development-admin password. Never commit `.env`.

Check the local tools and start the stack:

```sh
make check-env
make docker-up
make db-upgrade
```

`make db-upgrade` applies the migration chain and then explicitly creates or updates the local
development administrator from `DEVELOPMENT_ADMIN_EMAIL` and `DEVELOPMENT_ADMIN_PASSWORD`. This
credential operation does not run during ordinary API startup.

Open:

- frontend: <http://localhost:5173>
- API health: <http://localhost:8000/health>
- API documentation: <http://localhost:8000/docs>

Optionally verify the running API:

```sh
make smoke-api
```

The smoke target creates a uniquely named, temporary PostgreSQL and backend Compose project. Its
database has no host port, its backend uses a random loopback port, and neither local Google
credential directory nor the managed credential volume is mounted. Synthetic rows exist only in
that disposable database, which is removed on success, failure or interruption. The normal
WGASuite stack remains running and unchanged.

Stop the local stack with:

```sh
make docker-down
```

## Configuration

`.env.example` contains placeholders and non-secret local defaults only.

| Variable | Required | Purpose |
| --- | --- | --- |
| `APP_NAME` | No | API title; defaults to `WGASuite API` in the example. |
| `ENVIRONMENT` | No | Runtime environment label. |
| `POSTGRES_DB` | Yes for Compose | Local database name; `dread` is retained for compatibility. |
| `POSTGRES_USER` | Yes for Compose | Local database user; `dread` is retained for compatibility. |
| `POSTGRES_PASSWORD` | Yes | Unique database password; Docker Compose fails closed if absent. |
| `AUTH_SECRET_KEY` | Yes | Signing key of at least 32 characters; replace the placeholder. |
| `AUTH_TOKEN_EXPIRES_MINUTES` | No | Development bearer-token lifetime. |
| `DEVELOPMENT_ADMIN_EMAIL` | Yes for local login | Explicit local development administrator email. |
| `DEVELOPMENT_ADMIN_PASSWORD` | Yes for local login | Explicit local development password; no default is provided. |
| `BACKEND_CORS_ORIGINS` | No | Comma-separated allowed frontend origins. |
| `VITE_API_BASE_URL` | No | API base URL used by the frontend. |
| `VITE_ENABLE_DEMO_FEATURES` | No | Development-only opt-in for preserved mock assessment screens; defaults to `false` and is ignored by production builds. |
| `GOOGLE_WORKSPACE_CONNECTOR_ENABLED` | No | Reserved connector rollout setting. |
| `GOOGLE_WORKSPACE_CREDENTIALS_DIRECTORY` | No | Read-only root for organization-partitioned service-account files. |
| `GOOGLE_WORKSPACE_MANAGED_CREDENTIALS_DIRECTORY` | No | Backend-only persistent root for wizard-uploaded credentials. |
| `GOOGLE_WORKSPACE_CREDENTIAL_MAX_BYTES` | No | Maximum JSON credential upload size; defaults to 65536 bytes. |
| `GOOGLE_WORKSPACE_REQUEST_TIMEOUT_SECONDS` | No | Bounded Google HTTP timeout; defaults to 20 seconds and must be at most 60. |

Outside Docker Compose, `DATABASE_URL` can be supplied as an explicit alternative to the three
`POSTGRES_*` connection values. Do not duplicate a password in both forms unless a separate runtime
requires it.

## Development

Create the backend development environment once:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt \
  -c backend/requirements-dev.lock
```

`requirements.txt` and `requirements-dev.txt` express direct dependency intent. Their corresponding
`.lock` constraints pin the tested Python 3.12 resolution used by Docker, CI and local development.
See [CONTRIBUTING.md](CONTRIBUTING.md#backend-dependency-locks) for regeneration instructions.

Run backend lint, tests, compile checks and whitespace validation:

```sh
make backend-checks
```

Run individual backend checks when needed:

```sh
backend/.venv/bin/ruff check backend
backend/.venv/bin/pytest backend/tests
```

Install and validate the frontend:

```sh
npm --prefix frontend ci
npm --prefix frontend audit
npm --prefix frontend audit --omit=dev
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run build
```

Start only the frontend development server with:

```sh
make frontend-dev
```

Apply migrations and explicitly configure the development administrator in the running stack:

```sh
make db-upgrade
```

The frontend component suite uses Vitest, jsdom and Testing Library and runs in CI.

### Read-only smoke-record inventory

Older versions of the API smoke test wrote synthetic records to the normal development database.
Inventory those legacy rows using strict, correlated smoke-script fingerprints without printing
names, IDs, domains, emails or credential references:

```sh
docker compose exec -T backend python -m app.maintenance.synthetic_record_inventory
```

This command sets its PostgreSQL transaction to read-only and emits aggregate counts plus
association and deletion-impact guidance. It never deletes records. See
[Synthetic data cleanup](docs/SYNTHETIC_DATA_CLEANUP.md) for the private review-plan workflow,
backup/approval requirements, guarded one-time executor, read-only reconciliation and disposable
committed-path validation. A plan alone is never deletion authorization.

## Security

- Never commit `.env`, credentials, API keys, tokens, private keys or service-account JSON.
- Development authentication is a local foundation, not production identity management.
- Production use requires stronger identity controls, secret management, rate limiting, session
  policies and deployment hardening.
- Do not include secrets, active vulnerabilities or customer data in public issues.
- See [SECURITY.md](SECURITY.md) for responsible disclosure guidance.

## Project status

WGASuite is in early development and is not production-ready. The assessment, scoping, audit,
mock-scan, Google authentication/client foundation, read-only connection test, paginated Directory,
and exact user/alias lookup can be exercised locally. Guarded Gmail and Groups writes exist, but
broader write administration and production operations remain future work.

## Roadmap

Potential future work includes:

- broader user export and other feature-specific Google API operations;
- user and group administration workflows;
- ChromeOS and device administration;
- organizational-unit and license management;
- expanded security posture checks and audit/event workflows;
- production-ready authentication, SSO and authorization administration;
- broader frontend integration and browser coverage;
- external cloud secret-manager providers and automated credential rotation;
- production deployment, backup and monitoring guidance.

Roadmap items are directional and have no committed delivery dates. See
[docs/ROADMAP.md](docs/ROADMAP.md) for the working project roadmap and
[docs/PRODUCT_STRATEGY.md](docs/PRODUCT_STRATEGY.md) for the direct-API architecture decision and
product direction. The versioned PSGSuite/GAM comparison and reproducible capability inventory are
in [docs/parity/README.md](docs/parity/README.md).

## Contributing

Contributions and focused review feedback are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) for
setup, validation and pull-request expectations.

## License

WGASuite is licensed under the [Apache License 2.0](LICENSE).

## Disclaimer

WGASuite is an independent open-source project and is not affiliated with or endorsed by Google.
Google Workspace and related product names are trademarks of Google LLC.
