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
