# Development Rules

## Stack

- Backend: FastAPI
- Frontend: React + TypeScript + Vite
- Database: PostgreSQL
- Migrations: Alembic
- Lokaal draaien via Docker Compose

## Backend

- Nieuwe backend logica moet tests hebben.
- Gebruik SQLAlchemy voor database interactie.
- Gebruik Alembic voor schemawijzigingen.
- Houd API routes klein en duidelijk.
- Plaats domeinlogica in services wanneer routes te groot worden.

## Frontend

- Gebruik React met TypeScript.
- Gebruik Vite voor development en build.
- Houd componenten duidelijk en gericht op de gebruikerstaak.
- Voeg geen onnodige UI of marketingpagina's toe aan de MVP tool.

## Database en migraties

- PostgreSQL is de primaire database.
- Elke schemawijziging krijgt een Alembic migratie.
- Migraties moeten klein en reviewbaar blijven.

## Development omgeving

- Gebruik Docker Compose voor lokaal draaien.
- Gebruik `.env` lokaal en commit dit bestand nooit.
- Commit alleen `.env.example` met veilige voorbeeldwaarden.

## Connectoren

- Geen echte Google Workspace koppeling in MVP fase 1.
- Gebruik eerst een mock connector.
- Connectoren moeten read-only zijn waar mogelijk.
- Secrets lopen via environment variables of een secrets manager, niet via code of git.

## Security

- Werk security-by-design.
- Gebruik read-only toegang waar mogelijk.
- Log geen secrets, tokens of gevoelige request bodies.
- Houd configuratie per omgeving gescheiden.
- Gebruik environment variables voor gevoelige configuratie.
