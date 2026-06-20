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
- Codex mag geen software installeren zonder expliciete toestemming.

## Feature workflow

Codex mag code aanpassen voor de gevraagde feature of frontend/backend wijziging. Na elke feature voert Codex zelf de lokale Docker build en smoke checks uit waar mogelijk. De vaste volgorde is:

1. `make check-env`
2. `make docker-up`
3. `make db-upgrade`
4. `make smoke-api`
5. `make backend-checks`
6. `npm --prefix frontend run build`
7. `npm --prefix frontend run lint`
8. `git diff --check`

Regels:

- Docker, Node en npm zijn beschikbaar in de juiste VS Code omgeving en mogen voor deze checks gebruikt worden.
- Als Docker al draait, mag `docker compose up -d --build` gebruikt worden.
- Als iets faalt, stopt Codex en vat de fout duidelijk samen.
- Als containers opnieuw gebouwd zijn, meldt Codex welke containers draaien.
- Codex meldt of database migraties gelukt zijn.
- Codex meldt of de API smoke test gelukt is.
- Codex controleert en meldt of de frontend bereikbaar is op `http://localhost:5173`.
- Codex controleert en meldt of de backend docs bereikbaar zijn op `http://localhost:8000/docs`.
- Codex meldt wat de gebruiker handmatig in de browser moet controleren.
- De gebruiker hoeft zo min mogelijk losse terminalcommando's te plakken.

## Committen en pushen

- Codex mag na een feature niet automatisch committen.
- Codex werkt `docs/PROJECT_LOG.md` wel bij tijdens de feature.
- De logboekwijziging blijft uncommitted totdat de gebruiker expliciet vraagt om te committen.
- Codex stopt na een feature met een duidelijke clean/dirty git status en een samenvatting.
- Committen gebeurt alleen via een aparte expliciete commit-opdracht.
- Codex mag nooit automatisch pushen na een feature.
- Pushen gebeurt alleen via een aparte expliciete push-opdracht.

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
