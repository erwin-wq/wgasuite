# Development Rules

## Stack

- Backend: FastAPI
- Frontend: React + TypeScript + Vite
- Database: PostgreSQL
- Migrations: Alembic
- Local runtime: Docker Compose

## Backend

- Add tests for new backend behavior.
- Use SQLAlchemy for database access and Alembic for schema changes.
- Keep API routes focused and move substantial domain logic into services.
- Preserve customer scoping and role checks when changing data access or endpoints.

## Frontend

- Use React with TypeScript and Vite.
- Keep components focused on the user workflow.
- Do not present planned or mock-only behavior as implemented functionality.

## Database and migrations

- PostgreSQL is the primary database.
- Every schema change requires a small, reviewable Alembic migration.
- Do not destructively edit historical migrations; add a new remediation migration instead.
- Preserve compatibility identifiers such as `dread`, `dread_scores` and `dread_score` unless an
  explicit migration plan requires otherwise.
- DREAD remains the product's risk-assessment methodology and data model terminology.

## Configuration and local development

- Use Docker Compose for the local stack.
- Keep local secrets in `.env` and never commit that file.
- Keep `.env.example` limited to safe placeholders and non-secret examples.
- Do not commit virtual environments, dependency directories, build output, caches or scan reports.

## Validation

Run the checks relevant to a change. The standard source checks are:

```sh
make backend-checks
npm --prefix frontend audit
npm --prefix frontend audit --omit=dev
npm --prefix frontend run lint
npm --prefix frontend run build
git diff --check
```

For stack, configuration or integration changes, also run:

```sh
make check-env
make docker-up
make db-upgrade
make smoke-api
make docker-down
```

Document checks that could not be run. See `CONTRIBUTING.md` for contribution and pull-request
expectations, and `AGENTS.md` for coding-agent guidance.

## Connectors

- Real Google Admin SDK/API integration is not implemented.
- Keep connector behavior mock-only unless an explicitly reviewed integration is in scope.
- Prefer read-only, least-privilege access.
- Store secrets through environment configuration or an appropriate secret manager, never in code
  or Git.

## Security

- Apply security-by-design and least privilege.
- Do not log secrets, tokens, credentials or sensitive request bodies.
- Keep environment-specific configuration separated.
- Use synthetic data in tests, examples, logs and screenshots.
- Treat changes to authentication, authorization and customer scoping as security-sensitive.
