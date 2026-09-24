# Architectuur

Dit document beschrijft de huidige technische foundation. Zie
[PRODUCT_STRATEGY.md](PRODUCT_STRATEGY.md) voor de gekozen direct-API richting voor toekomstige
Google Workspace integraties. De herbruikbare authenticatie- en clientfoundation is beschikbaar;
echte API-operaties zijn nog niet geïmplementeerd.

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
- `app/connectors`: connectorgrens, credential providers, Domain-Wide Delegation, een generieke
  Google discovery-clientfactory, een check catalog en een lokale mock connector.

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

Connectoren staan onder `backend/app/connectors`. Google Workspace gebruikt deze keten:

```text
geautoriseerde actor + organization
  -> connector metadata
  -> tenant-gebonden credential provider
  -> service-account credentials
  -> expliciete OAuth scopes
  -> Domain-Wide Delegation admin subject
  -> ongecachete Google discovery client
```

`connector_configs` bevat alleen metadata, waaronder `credential_provider` en een opaque
`credential_ref`. Credentialmateriaal staat per organization buiten de database. De file provider
is de eerste implementatie; de abstractie laat een latere secrets manager toe. Er zijn nog geen
echte Google API-operaties. De mock scanner blijft fictieve findings genereren. Zie
[GOOGLE_WORKSPACE_CONNECTOR.md](GOOGLE_WORKSPACE_CONNECTOR.md).
