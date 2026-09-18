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

- De huidige development-authenticatie en rollenfoundation zijn niet geschikt als productie
  identity management. Voeg voor productie sterkere authenticatie, accountbeheer, rate limiting en
  session policies toe.
- Valideer DREAD-waarden server-side; huidige API beperkt waarden tot 0 t/m 10.
- Houd database-migraties reviewbaar en klein.
- Beperk CORS per omgeving via `BACKEND_CORS_ORIGINS`.

## Logging

- Log geen request bodies met gevoelige informatie.
- Log geen secrets of connector credentials.
- Voeg audit logging toe voor assessment- en finding-wijzigingen zodra gebruikersbeheer bestaat.

## CI/CD

- GitLab CI en GitHub Actions voeren backend lint/tests en frontend lint/build uit.
- Frontend CI controleert npm dependencies; secret scans worden tijdens public-readiness reviews
  uitgevoerd.
- Gebruik CI secrets/variables voor echte omgevingsconfiguratie en print die waarden nooit.
- Zie `/SECURITY.md` voor het publieke disclosurebeleid. GitHub Private Vulnerability Reporting moet
  vóór publicatie als repositorysetting worden ingeschakeld.
