# Contributing to AdminDeck

Thanks for helping improve AdminDeck. The project is in early development, so focused bug fixes,
security improvements, documentation corrections and well-scoped feature foundations are
especially useful.

AdminDeck currently combines Google Workspace administration foundations with security assessment
workflows. DREAD remains the name of the risk-scoring methodology used by the application; it is
not the product name.

## Development setup

Follow the [README](README.md#quick-start) for the Docker Compose workflow. For host-side checks,
use Python 3.12 and Node.js 22.

Create backend dependencies:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt
```

Install frontend dependencies from the lockfile:

```sh
npm --prefix frontend ci
```

Copy `.env.example` to `.env` for local runtime configuration and replace every required
placeholder. Never commit `.env`.

## Working on a change

- Branch from `main` and use a short, descriptive branch name.
- Keep each change focused and avoid unrelated formatting or refactors.
- Preserve backwards compatibility unless the change explicitly documents a migration path.
- Do not edit historical Alembic migrations. Add a new migration for schema changes.
- Add backend tests for new backend behavior.
- Keep documentation aligned with what is implemented, mock-only and planned.
- Do not describe mock Google Workspace behavior as a real API integration.

## Validation

Run the relevant checks before opening a pull request:

```sh
make backend-checks
npm --prefix frontend audit
npm --prefix frontend audit --omit=dev
npm --prefix frontend run lint
npm --prefix frontend run build
git diff --check
```

There is not yet a frontend automated test suite. If your change introduces one, keep the setup
small, document it and add it to CI. Always describe any checks you could not run.

For changes that affect the local stack, also run when practical:

```sh
make check-env
make docker-up
make db-upgrade
make smoke-api
```

## Security expectations

- Never commit passwords, tokens, API keys, private keys, service-account JSON or real customer
  data.
- Use `.env.example` only for non-secret examples and explicit placeholders.
- Do not log credentials or include them in screenshots, fixtures or issue reports.
- Fixed credentials are acceptable only in clearly isolated automated test fixtures.
- Follow [SECURITY.md](SECURITY.md) for vulnerability reporting. Do not disclose an active
  vulnerability in a public issue.

## Pull requests

A useful pull request:

- explains the problem and the chosen approach;
- separates implemented behavior from mock or planned behavior;
- lists tests, lint, build and migration checks that were run;
- calls out schema, configuration, security or compatibility impact;
- updates user-facing documentation when behavior changes;
- contains no generated build output or secrets.

Use the pull request template as a final checklist. Maintainers may ask for a large change to be
split into smaller reviewable steps.

## Bugs and feature requests

Use the GitHub issue forms once the repository is available on GitHub. Redact tenant names, email
addresses, identifiers, logs and screenshots before submitting. Security vulnerabilities belong in
the private reporting path described in [SECURITY.md](SECURITY.md), not in public issues.
