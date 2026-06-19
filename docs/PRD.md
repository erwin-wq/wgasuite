# Product Requirements Document

## Doel

Bouw een webbased DREAD Risk Assessment Tool waarmee security teams risico's consistent kunnen vastleggen, scoren en opvolgen.

## MVP-scope

- Organisatie aanmaken
- Assessment starten voor een organisatie
- Finding toevoegen aan een assessment
- DREAD-score invullen per finding
- Automatisch gemiddelde risicoscore berekenen
- Basis UI voor handmatige invoer
- Ruimte voor latere connectoren, zonder echte Google Workspace koppeling

## Buiten scope voor deze stap

- Authenticatie en autorisatie
- Multi-tenant hardening
- Google Workspace OAuth of API-integratie
- Rapportage-export
- Workflow notificaties

## Primaire gebruiker

Security consultant, risk analyst of interne security engineer die assessments uitvoert en findings wil normaliseren.

## Kernobjecten

- Organization: de klant, business unit of interne organisatie.
- Assessment: een risicobeoordeling met scope en status.
- Finding: een vastgesteld risico met DREAD-factoren en mitigatie.
- ConnectorAccount: toekomstige metadata voor externe koppelingen.

## Acceptatiecriteria MVP-foundation

- De backend exposeert health, organization, assessment en finding endpoints.
- De database heeft Alembic migraties voor de kernobjecten.
- De frontend kan de basisflow bedienen via de API.
- Docker Compose start PostgreSQL, backend en frontend.
- Voorbeeldconfiguratie bevat geen echte secrets.
