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

## Tests en checks

Backend:

```sh
cd backend
pip install -r requirements-dev.txt
pytest
ruff check .
```

Frontend:

```sh
cd frontend
npm install
npm run lint
npm run build
```

## Connector-status

Er is bewust nog geen echte Google Workspace koppeling. De code bevat alleen een connector-namespace en een metadata-tabel voor toekomstige connectoraccounts. Sla geen tokens, wachtwoorden of API keys op in git.
