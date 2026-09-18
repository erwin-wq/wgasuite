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
- `app/connectors`: connectorgrens, een check catalog en een lokale mock Google Workspace
  connector zonder externe calls.

## Datamodel

- `organizations`
- `assessments`
- `assets`
- `findings`
- `dread_scores`
- `connector_accounts`

Findings hebben een optionele koppeling naar een asset. De DREAD-score staat in een aparte `dread_scores` tabel met de velden damage, reproducibility, exploitability, affected users en discoverability. De API berekent `total_score` als gemiddelde van deze vijf waarden en bepaalt automatisch `risk_level`.

## API-vorm

- `GET /health`
- `POST /api/v1/organizations`
- `GET /api/v1/organizations`
- `GET /api/v1/organizations/{organization_id}`
- `POST /api/v1/assessments`
- `GET /api/v1/assessments`
- `GET /api/v1/assessments/{assessment_id}`
- `POST /api/v1/assets`
- `GET /api/v1/assets`
- `GET /api/v1/assets/{asset_id}`
- `POST /api/v1/findings`
- `GET /api/v1/findings`
- `GET /api/v1/findings/{finding_id}`
- `PATCH /api/v1/findings/{finding_id}`

## Connector boundary

Connectoren staan onder `backend/app/connectors`. De huidige implementatie bevat configuratiemetadata,
een check catalog en een mock scanner die fictieve findings genereert. Er zijn geen echte Google
API-calls en er worden geen connectorcredentials opgeslagen. Toekomstige connectoren moeten tokens
buiten git houden en encrypted storage of een secrets manager gebruiken.
