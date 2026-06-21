# Portal & Roles Design

## Doel

De DREAD Risk Assessment Tool krijgt uiteindelijk twee logische portalen:

1. Customer Portal
2. Platform Admin Portal

Het Customer Portal is voor klanten die hun eigen risico-assessments, Google Workspace checks,
scans, findings en rapportages beheren.

Het Platform Admin Portal is voor de platformbeheerder/SaaS-beheerder om klanten te beheren,
support te leveren en troubleshooting te doen.

## Customer Portal

De klant ziet alleen de eigen omgeving.

De klant kan straks beheren/bekijken:

- eigen klantomgeving
- eigen organisaties / tenants
- eigen assessments
- Google Workspace connector
- scans
- findings
- rapportages
- eventueel later eigen gebruikers

Belangrijke regels:

- klant ziet alleen eigen data
- klant ziet geen andere customers
- klant ziet geen platformbrede instellingen
- klant kan geen andere klanten beheren
- klant kan geen verborgen support- of systeeminformatie zien
- klant kan geen secrets, tokens of private keys zien

## Platform Admin Portal

De platform-admin kan straks alle klanten en omgevingen beheren en ondersteunen.

De platform-admin kan zien/beheren:

- alle customers
- alle organisaties
- scan runs
- connectorstatussen
- foutmeldingen
- support/troubleshooting informatie
- later: klant aanmaken
- later: gebruiker uitnodigen
- later: support access
- later: audit log

Belangrijke regels:

- platform-admin mag klanten helpen met troubleshooting
- platform-admin mag connectorstatus en scanstatus bekijken
- platform-admin mag foutmeldingen zien
- platform-admin mag nooit secrets, tokens of private keys in plain text zien
- supportacties moeten altijd gelogd worden

## Support access en audit logging

Support access is belangrijk en moet expliciet gelogd worden.

Voorbeeld audit event:

```text
Admin support access gestart door Erwin
Customer: X
Tijdstip: Y
Actie: scan run bekeken / connector status bekeken / rapport geopend
```

Minimale support logging:

- wie deed de actie
- voor welke customer
- op welk tijdstip
- welke actie
- welk object is bekeken of aangepast
- resultaat van de actie
- eventueel reden/notitie

Voorbeelden van acties die gelogd moeten worden:

- customer geopend door platform-admin
- connectorstatus bekeken
- scan run bekeken
- foutmelding bekeken
- rapport geopend
- supportmodus gestart
- supportmodus beëindigd
- wijziging gedaan namens klant

Support mag niet onzichtbaar zijn. Als een platform-admin meekijkt of troubleshooting doet, moet
dat later aantoonbaar zijn.

## Rollen

Definieer deze toekomstige rollen:

### platform_admin

Voor de eigenaar/beheerder van het platform.

Mag:

- alle customers zien
- customers aanmaken/beheren
- alle organisaties zien
- scan runs en connectorstatussen bekijken
- support/troubleshooting uitvoeren
- audit log bekijken
- platforminstellingen beheren

### platform_support

Voor supportmedewerkers.

Mag:

- klanten helpen
- connectorstatussen bekijken
- scan runs bekijken
- foutmeldingen bekijken
- rapporten openen voor troubleshooting

Beperkingen:

- geen destructive acties zonder extra toestemming
- geen secrets bekijken
- supportacties worden gelogd

### customer_admin

Voor de beheerder bij de klant.

Mag binnen eigen customer:

- eigen organisaties beheren
- assessments beheren
- Google Workspace connector configureren
- scans starten
- findings beheren
- rapportages bekijken
- later eigen gebruikers uitnodigen

### customer_user

Voor normale klantgebruikers.

Mag binnen eigen customer:

- assessments bekijken/bewerken afhankelijk van rechten
- findings bekijken/bewerken afhankelijk van rechten
- rapportages bekijken afhankelijk van rechten

### customer_viewer

Voor auditor/read-only gebruiker.

Mag binnen eigen customer:

- assessments bekijken
- findings bekijken
- rapportages bekijken

Mag niet:

- configuratie wijzigen
- scans starten
- findings aanpassen
- gebruikers beheren

## Data access regels

Leg vast:

- platform_admin ziet alles
- platform_support ziet supportinformatie, maar acties worden gelogd
- customer_admin ziet alleen eigen customer data
- customer_user ziet alleen eigen customer data
- customer_viewer ziet alleen eigen customer data
- organizations, assessments, assets, findings, connector configs en scan runs moeten uiteindelijk
  customer-scoped zijn
- API endpoints moeten later customer scoping afdwingen

## MVP status

Wat we nu al hebben:

- eerste login/auth foundation
- eerste Customer model
- organization/customer koppeling
- Google Workspace connector metadata
- mock Google Workspace scan
- check catalog
- rapportage
- navigatiestructuur

Wat we nog niet hebben:

- volledige tenant-isolatie
- echte rollenmatrix
- customer membership model
- audit logging
- support access logging
- echte platform admin portal
- echte Google Workspace API-koppeling

## Aanbevolen implementatiefases

### Fase 1 - Documentatie en terminologie

Customer Portal en Platform Admin Portal vastleggen.

### Fase 2 - Rollen uitbreiden

User roles uitbreiden naar:

- platform_admin
- platform_support
- customer_admin
- customer_user
- customer_viewer

### Fase 3 - Customer membership model

Toevoegen:

- user_id
- customer_id
- role

Hiermee kan één user aan één of meer customers gekoppeld worden.

### Fase 4 - API data scoping

Afdwingen:

- customer users zien alleen eigen customer data
- platform_admin ziet alles
- platform_support krijgt supporttoegang met logging

### Fase 5 - Frontend splitsen

Navigatie splitsen in:

- Customer Portal
- Platform Admin Portal

### Fase 6 - Support tooling

Toevoegen:

- supportmodus
- audit log
- scan runs bekijken
- connectorstatus bekijken
- foutmeldingen bekijken

### Fase 7 - Echte Google Workspace integratie

Pas nadat rollen, scoping en supportlogging duidelijk zijn, echte Google Workspace API-checks
verder uitbouwen.

## Open beslissingen

Leg deze open vragen vast:

- Gebruiken Customer Portal en Platform Admin Portal dezelfde login?
- Komen er aparte URLs, bijvoorbeeld `/app` en `/admin`?
- Mag platform_support klantdata wijzigen of alleen bekijken?
- Willen we "view as customer" of alleen supportdetails?
- Moet de klant kunnen zien wanneer support heeft meegekeken?
- Welke audit events zijn minimaal nodig voor MVP?
- Wanneer voegen we tenant-isolation tests toe?
- Wanneer bouwen we echte user invitations?
