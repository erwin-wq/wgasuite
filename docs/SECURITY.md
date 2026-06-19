# Security

## Secrets

- Commit geen echte wachtwoorden, tokens, client secrets of API keys.
- Gebruik `.env` lokaal en commit alleen `.env.example`.
- De voorbeeldwaarden zijn development placeholders en moeten per omgeving worden vervangen.

## Connectoren

- Er is nog geen echte Google Workspace koppeling.
- Toekomstige OAuth tokens mogen niet in git, logs of onbeveiligde JSON velden terechtkomen.
- Connector metadata mag alleen niet-gevoelige statusinformatie bevatten.

## Applicatiebeveiliging

- Voeg authenticatie en autorisatie toe voordat de tool buiten development wordt gebruikt.
- Valideer DREAD-waarden server-side; huidige API beperkt waarden tot 0 t/m 10.
- Houd database-migraties reviewbaar en klein.
- Beperk CORS per omgeving via `BACKEND_CORS_ORIGINS`.

## Logging

- Log geen request bodies met gevoelige informatie.
- Log geen secrets of connector credentials.
- Voeg audit logging toe voor assessment- en finding-wijzigingen zodra gebruikersbeheer bestaat.

## CI/CD

- CI voert basis lint/test/build uit.
- Voeg later dependency scanning, container scanning en secret scanning toe.
- Gebruik GitLab CI variables voor echte omgevingsconfiguratie.
