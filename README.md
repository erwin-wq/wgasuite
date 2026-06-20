# DREAD Risk Assessment Tool

Webbased MVP-foundation voor DREAD risk assessments. De eerste versie legt de basis om organisaties aan te maken, assessments te starten, findings vast te leggen en DREAD-scores te registreren.

## Stack

- Backend: Python, FastAPI, SQLAlchemy, Alembic
- Database: PostgreSQL
- Frontend: React, TypeScript, Vite
- Dev: Docker Compose
- CI: GitLab lint/test/build jobs

## Lokaal starten

Maak eerst een lokale environment file:

```sh
cp .env.example .env
```

Start de stack:

```sh
docker compose up -d --build
docker compose exec backend alembic upgrade head
```

Open daarna:

- Frontend: http://localhost:5173
- API health: http://localhost:8000/health
- API docs: http://localhost:8000/docs

## Development login

De MVP heeft een eerste dev-only auth foundation. Na `make db-upgrade` bestaat er lokaal een demo admin gebruiker:

- Email: `admin@example.local`
- Password: `ChangeMe123!`
- Role: `admin`

Dit account is alleen bedoeld voor lokale development en demo's. Gebruik deze gegevens niet voor productie of echte klantdata. De auth foundation gebruikt een bearer token en `AUTH_SECRET_KEY` uit environment variables. `.env.example` bevat alleen een veilige placeholder; zet echte secrets nooit in git.

Productie hardening volgt later, zoals secret rotation, sterker accountbeheer, password reset, rate limiting, audit logging, session policies en eventueel externe identity providers.

## Project lokaal starten

Dit is de korte route om lokaal te controleren of alles werkt.

1. Controleer je omgeving:

```sh
make check-env
```

2. Start Docker Compose:

```sh
cp .env.example .env
make docker-up
```

3. Draai de database migraties:

```sh
make db-upgrade
```

4. Draai de API smoke test:

```sh
make smoke-api
```

Gebruik een andere API URL als dat nodig is:

```sh
API_BASE_URL=http://localhost:8000 make smoke-api
```

5. Draai backend tests en checks:

```sh
make backend-checks
```

6. Installeer en start de frontend:

```sh
make frontend-install
make frontend-dev
```

De belangrijkste URLs zijn:

- Frontend: http://localhost:5173
- API health: http://localhost:8000/health
- API docs: http://localhost:8000/docs

Log lokaal in met de development login hierboven.

## Customer foundation

Een Customer is de bovenliggende klantlaag voor toekomstig klantbeheer. Organizations kunnen
optioneel aan een Customer gekoppeld worden. Na `make db-upgrade` bestaat lokaal ook een demo
customer:

- Name: `Demo Customer`
- Slug: `demo-customer`
- Status: `active`

Dit is alleen een eerste foundation. Het is nog geen volledige tenant-isolatie, billing,
abonnementenbeheer of productieklantbeheer.

## Tests en checks

Backend:

```sh
make backend-checks
```

Frontend:

```sh
make frontend-install
npm --prefix frontend run lint
npm --prefix frontend run build
```

## Connector-status

Er is bewust nog geen echte Google Workspace koppeling. De code bevat alleen een connector-namespace en een metadata-tabel voor toekomstige connectoraccounts. Sla geen tokens, wachtwoorden of API keys op in git.
