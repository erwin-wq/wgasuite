# Portal & Roles Design

## Doel

WGASuite gebruikt één applicatie met twee logische verantwoordelijkheden:

1. Customer Portal
2. Platform Admin Portal

Het customer-gedeelte is voor klanten die binnen hun eigen scope risico-assessments, Google
Workspace checks, scans, findings en rapportages beheren. Een volledig afzonderlijke Customer
Portal-frontend is nog niet geïmplementeerd.

Het Platform Admin-gedeelte is voor platformbeheer en support. De huidige frontend bevat een
read-only overzicht; een volledig afzonderlijke beheerportal en supportmodus zijn nog gepland.

## Customer Portal

De klant ziet alleen de eigen omgeving.

De huidige API-rollen kunnen binnen hun customer scope, afhankelijk van hun rechten:

- eigen klantomgeving
- eigen organisaties / tenants
- eigen assessments
- Google Workspace connector
- scans
- findings
- rapportages
- eigen customer memberships bekijken

User invitations en volledig accountbeheer zijn nog niet geïmplementeerd.

Belangrijke regels:

- klant ziet alleen eigen data
- klant ziet geen andere customers
- klant ziet geen platformbrede instellingen
- klant kan geen andere klanten beheren
- klant kan geen verborgen support- of systeeminformatie zien
- klant kan geen secrets, tokens of private keys zien

## Platform Admin Portal

De huidige `platform_admin`-rol kan klanten en omgevingen beheren. `platform_admin` en
`platform_support` hebben daarnaast toegang tot het read-only Platform Admin-overzicht.

De platform-admin kan zien/beheren:

- alle customers
- alle organisaties
- scan runs
- connectorstatussen
- foutmeldingen
- support/troubleshooting informatie
- customers aanmaken
- customer memberships beheren (`platform_admin`)
- geselecteerde audit events bekijken

User invitations, expliciete support-sessies en volledige auditdekking zijn nog niet
geïmplementeerd.

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
Platform admin support access gestart
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

De backend kent de volgende rollen:

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

De API dwingt de volgende regels af:

- platform_admin ziet alles
- platform_support ziet supportinformatie, maar acties worden gelogd
- customer_admin ziet alleen eigen customer data
- customer_user ziet alleen eigen customer data
- customer_viewer ziet alleen eigen customer data
- organizations, assessments, assets, findings, connector configs en scan runs zijn
  customer-scoped
- dedicated backendtests controleren cross-customer toegang en rolgrenzen

## MVP status

Wat we nu al hebben:

- development login/auth foundation
- Customer model en organization/customer koppeling
- customer memberships en rolchecks
- backend customer data scoping
- support-access audit events voor geselecteerde read-acties
- read-only Platform Admin overview voor platformrollen
- Google Workspace connector metadata en statusoverzicht
- mock Google Workspace scan en check catalog
- DREAD-rapportage en navigatiestructuur

Wat we nog niet hebben:

- volledige productie-harde tenant-isolatie
- volledige visuele splitsing tussen Customer Portal en Platform Admin Portal
- user invitations en accountbeheer
- customer impersonation of een volledige supportmodus
- billing of abonnementenbeheer
- volledige auditdekking voor alle mutaties
- echte Google Workspace API-koppeling

## Implementatiestatus

### Afgerond: documentatie en terminologie

Customer Portal en Platform Admin Portal vastleggen.

### Afgerond: rollen

De volgende rollen zijn geïmplementeerd:

- platform_admin
- platform_support
- customer_admin
- customer_user
- customer_viewer

### Afgerond: customer memberships

Het membershipmodel bevat:

- user_id
- customer_id
- role

Hiermee kan één user aan één of meer customers gekoppeld worden.

### Afgerond: API data scoping

De API dwingt af:

- customer users zien alleen eigen customer data
- platform_admin ziet alles
- platform_support krijgt supporttoegang met logging

### Gepland: frontend verder splitsen

Navigatie splitsen in:

- Customer Portal
- Platform Admin Portal

### Gedeeltelijk geïmplementeerd: support tooling

Beschikbaar zijn een read-only Platform Admin-overzicht, geselecteerde audit events, scan runs en
connectorstatus. Nog gepland zijn:

- supportmodus
- volledige auditdekking
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
- Wanneer bouwen we echte user invitations?
