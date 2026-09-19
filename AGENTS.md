# AGENTS.md

Repository guidance for coding agents contributing to WGASuite.

## Repository context

- The backend uses FastAPI, SQLAlchemy, Alembic and PostgreSQL.
- The frontend uses React, TypeScript and Vite.
- `README.md` is authoritative for current, mock-only and planned capabilities.
- `CONTRIBUTING.md` describes the human contribution workflow.
- `docs/DEVELOPMENT_RULES.md` contains durable engineering constraints.
- DREAD is the risk-assessment methodology used by the product, not the product name.

## Working rules

- Inspect the current Git status and read relevant files before editing.
- Keep changes focused, small and reviewable; preserve unrelated work in the tree.
- Add or update tests for new backend behavior.
- Do not create or commit secrets, credentials, tokens, private keys or real customer data.
- Never commit `.env`; keep `.env.example` limited to safe placeholders and non-secret examples.
- Do not commit generated dependencies, build output, caches or scan reports.
- Keep documentation clear about what is implemented, mock-only and planned.

## Architecture and compatibility

- Keep API routes focused; move substantial domain logic into services.
- Use SQLAlchemy for persistence and Alembic for schema changes.
- Add a new migration for schema changes. Do not destructively rewrite historical migrations.
- Preserve compatibility identifiers such as `dread`, `dread_scores` and `dread_score` unless an
  explicit migration plan requires otherwise.
- Preserve customer scoping and role boundaries when changing data access or API behavior.

## Google Workspace integration

- Real Google Admin SDK/API integration is not implemented.
- Keep connector and scan behavior mock-only unless a change explicitly introduces a reviewed,
  least-privilege integration and secure credential design.
- Never store Google credentials or OAuth tokens in source control or ordinary connector metadata.

## Validation

Run checks relevant to the files changed. The standard checks are:

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

Report checks that were not run and why. Preserve the development database volume unless a task
explicitly requires destructive database cleanup.

## Git and review safety

- Do not rewrite history, force-push, alter remotes or discard unrelated changes.
- Stage and commit only files that belong to the requested change.
- Follow `CONTRIBUTING.md` for branches, pull requests and review expectations.
