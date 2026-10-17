# Architectuur

Dit document beschrijft de huidige technische foundation. Zie
[PRODUCT_STRATEGY.md](PRODUCT_STRATEGY.md) voor de gekozen direct-API richting voor toekomstige
Google Workspace integraties. De herbruikbare authenticatie- en clientfoundation is beschikbaar;
de echte API-operaties omvatten read-only connectietests, gepagineerde user-directory, exacte
user/alias lookup, bewaakte Gmail mailboxdelegatie en bewaakte Google Groups direct-membership
changes, plus bewaakte user suspension/reactivation.

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
- `POST /api/v1/organizations/{organization_id}/google-workspace/users/lookup`
- `POST /api/v1/organizations/{organization_id}/google-workspace/users/list`
- `POST /api/v1/organizations/{organization_id}/google-workspace/users/suspend/preview`
- `POST /api/v1/organizations/{organization_id}/google-workspace/users/suspend`
- `POST /api/v1/organizations/{organization_id}/google-workspace/users/suspend/reconcile`
- `POST /api/v1/organizations/{organization_id}/google-workspace/users/reactivate/preview`
- `POST /api/v1/organizations/{organization_id}/google-workspace/users/reactivate`
- `POST /api/v1/organizations/{organization_id}/google-workspace/users/reactivate/reconcile`
- `POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/list`
- `POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/create/preview`
- `POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/create`
- `POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/create/reconcile`
- `POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/remove/preview`
- `POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/remove`
- `POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/remove/reconcile`
- `POST /api/v1/organizations/{organization_id}/google-workspace/groups/search`
- `POST /api/v1/organizations/{organization_id}/google-workspace/groups/get`
- `POST /api/v1/organizations/{organization_id}/google-workspace/groups/members/list`
- `POST /api/v1/organizations/{organization_id}/google-workspace/groups/members/add/preview`
- `POST /api/v1/organizations/{organization_id}/google-workspace/groups/members/add`
- `POST /api/v1/organizations/{organization_id}/google-workspace/groups/members/add/reconcile`
- `POST /api/v1/organizations/{organization_id}/google-workspace/groups/members/remove/preview`
- `POST /api/v1/organizations/{organization_id}/google-workspace/groups/members/remove`
- `POST /api/v1/organizations/{organization_id}/google-workspace/groups/members/remove/reconcile`
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

Gmail-delegatie voegt na Directory tenant- en identityvalidatie een afzonderlijk, beperkt pad toe:
canonical mailbox owner als DWD-subject, vaste `gmail/v1` client en exact één read- of write-scope.
Een onduidelijke mutation-response wordt als `unknown` opgeslagen. De aparte reconciliation-service
kan met dezelfde actor/organization/operation-bound confirmation uitsluitend begrensde
`delegates.list` calls uitvoeren; de write-client is vanuit dat pad niet bereikbaar.
Mutaties gebruiken een database-backed, eenmalige confirmation en worden niet automatisch herhaald.

Google Groups gebruikt een afzonderlijke, operation-scoped Directory-client. Read requests vragen
alleen `admin.directory.group.readonly`; bevestigde writes alleen
`admin.directory.group.member`. De service bepaalt eerst de Google `customerId` via de canonical
delegated administrator en gebruikt die waarde voor `groups.list`. Een `groups.get` resultaat is
pas bruikbaar nadat dezelfde group-id in die customer-scope is teruggevonden. Membership listing
zet `includeDerivedMembership=false`. Add/remove bevestigingen staan in
`google_workspace_group_membership_confirmations`; tokens worden alleen als SHA-256 digest bewaard.
De reconciliation-service kan na een ambigu resultaat uitsluitend begrensde direct-member reads
uitvoeren en heeft geen pad dat `members.insert` of `members.delete` opnieuw aanroept.

De user-directory verifieert eerst de delegated administrator via de bestaande exacte lookup en
gebruikt diens Google `customerId` voor `users.list`. Zoekopdrachten en filters worden server-side
naar een begrensde Directory-query vertaald. Alleen Google's ondersteunde sortering en opaque
pagination-token worden doorgegeven. Elk resultaat moet dezelfde customer-id dragen; profielen,
zoektermen en tokens worden niet opgeslagen.

De centrale user-detail gebruikt dezelfde canonical `users.get` identity voor reverse
group-membership context. `groups.list(userKey=<immutable user-id>)` kan volgens Google niet met
`customer` worden gecombineerd en levert daarom alleen kandidaten. Per kandidaat bewijst een
exacte `groups.list(customer=<verified customerId>, query=email=...)` match op group-id én primary
email het tenant-eigendom; pas daarna bepaalt `members.get(groupKey=<id>, memberKey=<user-id>)` de
directe MEMBER/MANAGER/OWNER-rol. Maximaal 25 kandidaten en 50 verificatiecalls worden per pagina
toegestaan. Externe en indirect-only resultaten worden met veilige aantallen weggelaten. Er is geen
tenant-brede scan, cache of persistent membershipkopie en dit pad gebruikt uitsluitend de bestaande
user- en group-readonly scopes.

User-statusmutaties gebruiken een eigen operation-scoped Directory-client: reads uitsluitend
`admin.directory.user.readonly`, writes uitsluitend `admin.directory.user`. De service bindt een
vijf minuten geldige confirmation aan actor, lokale customer, organization, connector, Google
customer, immutable user-id, action en verwachte status. Alleen het token-digest en veilige
bindingsmetadata staan in `google_workspace_user_status_confirmations`. Na volledige hervalidatie
wordt exact één `users.update` met uitsluitend het `suspended` veld en `num_retries=0` uitgevoerd.
Admin-, DWD-, self-, service-, archived/deleted en onbetrouwbaar gesuspendeerde accounts zijn
server-side beschermd. Een ambigu resultaat kan uitsluitend via begrensde read-only `users.get`
polling worden waargenomen; de write-client is niet bereikbaar vanuit reconciliation.

`connector_configs` bevat alleen metadata, waaronder `credential_provider` en een opaque
`credential_ref`. Credentialmateriaal staat per organization buiten de database. De file provider
is de eerste implementatie; de abstractie laat een latere secrets manager toe. De connection test
de gepagineerde user-directory en exacte user/alias lookup gebruiken echte, minimaal gescopete
Directory API-calls zonder profielen op te slaan. De mock scanner blijft fictieve findings genereren. Zie
[GOOGLE_WORKSPACE_CONNECTOR.md](GOOGLE_WORKSPACE_CONNECTOR.md).
