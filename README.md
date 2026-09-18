# AdminDeck

**Open-source administration and security operations for Google Workspace.**

AdminDeck is an open-source web console for Google Workspace administration, security
assessments and operational workflows. It aims to make common administration and security tasks
more approachable through a web interface instead of requiring every workflow to be performed in
an admin console or custom script.

> **Project status:** early development / pre-release. The current repository provides a working
> local foundation, but real Google Workspace API administration is not implemented yet.

AdminDeck is an independent open-source project and is not affiliated with or endorsed by Google.

## Overview

Google Workspace teams often combine the Google Admin console, API scripts and command-line tools
to operate their environments. AdminDeck is exploring a focused web-based layer for those
workflows, with customer scoping, security assessment data and auditable operational context in one
application.

The current application is useful for developing and reviewing the data model, role boundaries,
assessment workflow and mock Google Workspace security checks. It must not yet be treated as a
production Google Workspace management platform.

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
- a catalog of Google Workspace security checks;
- mock scan runs, generated demo findings and recent scan-run history.

Mock/demo-only today:

- Google Workspace scans use fictitious local data;
- all check-catalog entries have `mock_only` status;
- connector testing intentionally returns `not_implemented`;
- generated findings demonstrate the assessment and DREAD reporting flow only.

Not implemented today:

- real Google Workspace Admin SDK or other Google API access;
- storage or use of service-account keys, OAuth access tokens or refresh tokens;
- production identity management, SSO, account recovery or hardened session management;
- user, group, ChromeOS/device, organizational-unit or license administration;
- a complete production deployment and operations model.

## Google Workspace status

AdminDeck does not currently connect to a real Google Workspace tenant. Connector records store
non-secret configuration metadata such as display name, primary domain, chosen auth method and
status. The mock scanner reads only the in-repository check catalog and generates fictional
findings; it does not call Google APIs or access customer data.

Future Google Workspace integrations will require explicit API scope design, secure credential
storage, auditability and a production-ready identity model before they can be enabled safely.

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
backwards compatibility; they do not represent the AdminDeck product name.

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
git clone YOUR_REPOSITORY_URL admindeck
cd admindeck
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

The smoke test reads the configured development credentials from the backend container and does not
print the password.

Stop the local stack with:

```sh
make docker-down
```

## Configuration

`.env.example` contains placeholders and non-secret local defaults only.

| Variable | Required | Purpose |
| --- | --- | --- |
| `APP_NAME` | No | API title; defaults to `AdminDeck API` in the example. |
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
| `GOOGLE_WORKSPACE_CONNECTOR_ENABLED` | No | Placeholder feature setting; no real API connector exists yet. |

Outside Docker Compose, `DATABASE_URL` can be supplied as an explicit alternative to the three
`POSTGRES_*` connection values. Do not duplicate a password in both forms unless a separate runtime
requires it.

## Development

Create the backend development environment once:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt
```

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

There is currently no frontend automated test suite. This is a known project-quality gap and a
roadmap item.

## Security

- Never commit `.env`, credentials, API keys, tokens, private keys or service-account JSON.
- Development authentication is a local foundation, not production identity management.
- Production use requires stronger identity controls, secret management, rate limiting, session
  policies and deployment hardening.
- Do not include secrets, active vulnerabilities or customer data in public issues.
- See [SECURITY.md](SECURITY.md) for responsible disclosure guidance.

## Project status

AdminDeck is in early development and is not production-ready. The assessment, scoping, audit and
mock-scan foundations can be exercised locally. Real Google Workspace administration and production
operations remain future work.

## Roadmap

Potential future work includes:

- real, least-privilege Google Workspace Admin SDK integrations;
- user and group administration workflows;
- ChromeOS and device administration;
- organizational-unit and license management;
- expanded security posture checks and audit/event workflows;
- production-ready authentication, SSO and authorization administration;
- frontend automated tests;
- secure connector credential storage and rotation;
- production deployment, backup and monitoring guidance.

Roadmap items are directional and have no committed delivery dates. See
[docs/ROADMAP.md](docs/ROADMAP.md) for the working project roadmap.

## Contributing

Contributions and focused review feedback are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) for
setup, validation and pull-request expectations.

## License

AdminDeck is licensed under the [Apache License 2.0](LICENSE).

## Disclaimer

AdminDeck is an independent open-source project and is not affiliated with or endorsed by Google.
Google Workspace and related product names are trademarks of Google LLC.
