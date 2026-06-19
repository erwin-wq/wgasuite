# Architectuur

## Overzicht

De applicatie bestaat uit een FastAPI backend, PostgreSQL database en React/Vite frontend. Alembic beheert schemawijzigingen. Docker Compose verbindt de services in development.

## Componenten

- `frontend`: React + TypeScript UI voor organisatie-, assessment- en findingbeheer.
- `backend`: FastAPI API met SQLAlchemy ORM en Pydantic schemas.
- `postgres`: relationele opslag voor assessmentdata.
- `alembic`: database migraties.

## Backend lagen

- `app/api`: HTTP routes.
- `app/schemas`: request/response modellen.
- `app/models`: SQLAlchemy datamodellen.
- `app/db`: engine, sessies en metadata.
- `app/services`: domeinlogica zoals DREAD-scoreberekening.
- `app/connectors`: toekomstige connectoren, nu alleen placeholder.

## Datamodel

- `organizations`
- `assessments`
- `findings`
- `connector_accounts`

Findings bevatten vijf DREAD-factoren: damage, reproducibility, exploitability, affected users en discoverability. De API berekent `risk_score` als gemiddelde van deze vijf waarden.

## API-vorm

- `GET /health`
- `GET /api/v1/organizations`
- `POST /api/v1/organizations`
- `GET /api/v1/organizations/{organization_id}/assessments`
- `POST /api/v1/organizations/{organization_id}/assessments`
- `GET /api/v1/assessments/{assessment_id}/findings`
- `POST /api/v1/assessments/{assessment_id}/findings`

## Connector boundary

Connectoren komen onder `backend/app/connectors`. De huidige Google Workspace placeholder doet geen externe calls en bevat geen credentials. Toekomstige connectoren moeten tokens buiten git houden en bij voorkeur encrypted storage of een secrets manager gebruiken.
