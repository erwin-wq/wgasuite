# AGENTS.md

Werkafspraken voor Codex in deze repository.

## Basisregels

- Werk in kleine logische stappen.
- Controleer eerst de huidige git status voordat je bestanden wijzigt.
- Maak geen secrets, wachtwoorden, tokens of API keys aan.
- Commit nooit `.env` bestanden.
- Gebruik `.env.example` alleen met veilige voorbeeldwaarden.
- Overschrijf bestaande bestanden niet onnodig.
- Houd taal simpel en duidelijk.

## Logboek

- Update na elke opdracht `docs/PROJECT_LOG.md`.
- Schrijf in het logboek wat er is aangepast, waarom, welke tests zijn uitgevoerd en wat de volgende stap is.
- Zet de volledige eindsamenvatting ook in het logboek.
- Als iets niet getest kon worden, vermeld duidelijk waarom.

## Werkwijze

- Lees bestaande bestanden voordat je ze wijzigt.
- Houd wijzigingen klein en reviewbaar.
- Voeg tests toe bij nieuwe backend logica.
- Maak geen echte Google Workspace koppeling in MVP fase 1.
- Gebruik eerst een mock connector of placeholder voor connectorwerk.
- Meld duidelijk of er een GitLab remote bestaat.
- Push niet automatisch naar GitLab zonder dit eerst duidelijk te melden.

## Automatische validatie na features

- Na elke feature of frontend/backend wijziging probeert Codex zelf de lokale Docker build en smoke checks uit te voeren.
- Codex mag deze checks uitvoeren omdat Docker, Node en npm beschikbaar zijn in de juiste VS Code omgeving.
- Codex mag geen software installeren zonder expliciete toestemming.
- Als Docker al draait, mag Codex `docker compose up -d --build` gebruiken.
- Voer de checks in deze volgorde uit:
  1. `make check-env`
  2. `make docker-up`
  3. `make db-upgrade`
  4. `make smoke-api`
  5. `make backend-checks`
  6. `npm --prefix frontend run build`
  7. `npm --prefix frontend run lint`
  8. `git diff --check`
- Als iets faalt, stop dan en vat de fout duidelijk samen.
- Als containers opnieuw gebouwd zijn, meld duidelijk welke containers draaien, of migraties gelukt zijn, of de smoke test gelukt is, of de frontend bereikbaar is op `http://localhost:5173`, en of de backend docs bereikbaar zijn op `http://localhost:8000/docs`.
- De gebruiker moet zo min mogelijk losse terminalcommando's hoeven plakken.
