# Security

## Secrets

- Commit geen echte wachtwoorden, tokens, client secrets of API keys.
- Gebruik `.env` lokaal en commit alleen `.env.example`.
- De voorbeeldwaarden zijn development placeholders en moeten per omgeving worden vervangen.

## Connectoren

- De Google Workspace connector ondersteunt een echte, read-only Directory API-connection test,
  customer-scoped user-directory, exacte user/alias lookup, bevestigde Gmail delegate create/remove
  en bevestigde Google Groups direct-membership changes via service accounts met Domain-Wide
  Delegation. Bevestigde user suspension en veilig beperkte reactivation zijn eveneens beschikbaar.
- Service-account JSON staat buiten database, API-responses, frontend, logs en git.
- De file provider partitioneert credentials op organization-id en accepteert alleen opaque
  references; het runtimepad wordt read-only gemount.
- Elke feature moet scopes expliciet en minimaal aanvragen. Clients worden niet tussen tenants of
  scope-sets gecachet.
- Directory listing gebruikt uitsluitend de bestaande `admin.directory.user.readonly` scope,
  verifieert Google's `customerId` op ieder resultaat en bewaart geen profielen, zoekwaarden of
  opaque page tokens. Auditmetadata bevat alleen veilige filtercategorieën en aantallen.
- Reverse user-group listing gebruikt alleen de bestaande user- en group-readonly scopes. Omdat
  `groups.list(userKey)` geen `customer` accepteert, wordt iedere kandidaat eerst met immutable ID
  en primary email in de geverifieerde customer-scope bevestigd en daarna met `members.get` als
  direct lid gevalideerd. Externe/indirecte resultaten lekken niet door; fan-out is begrensd tot 25
  kandidaten en 50 verificatiecalls en wordt niet gecachet of opgeslagen.
- Gmail delegate reads gebruiken alleen `gmail.settings.basic`; create/delete gebruiken apart
  alleen `gmail.settings.sharing`. De mailboxeigenaar wordt pas geïmpersoneerd nadat actor,
  organization, Google `customerId` en canonical identity zijn gevalideerd.
- Gmail writes vereisen een korte, eenmalige server-side confirmation, worden vlak voor uitvoering
  opnieuw gevalideerd en worden na onduidelijke netwerkfouten nooit automatisch herhaald. Alleen
  actor/tenant/operation/identity-gebonden, begrensde `delegates.list` reconciliation is toegestaan.
- Groups reads gebruiken alleen `admin.directory.group.readonly`; bevestigde membership writes
  gebruiken apart alleen `admin.directory.group.member`. Group-eigendom wordt met de geverifieerde
  Google `customerId` bewezen, niet met domeinsuffixen. Alleen canonical interne users zijn
  mutabel; owner-, nested-, external-, customer-wide en herkende special-group memberships zijn
  read-only.
- Groups writes gebruiken dezelfde korte, actor/tenant/operation/identity-gebonden one-time
  confirmations. Timeouts worden nooit automatisch opnieuw verzonden; alleen begrensde,
  direct-only `members.list` reconciliation is toegestaan en bewijst toestand, niet causaliteit.
- Connection-testresultaten en lookup-audit events bevatten alleen gesaniteerde foutcodes en
  minimale metadata; zoekadressen, ruwe Google-responses en profielen worden niet opgeslagen.
- OAuth tokens mogen niet in git, logs of onbeveiligde JSON velden terechtkomen.
- Delegate-audits bevatten minimale canonical mailboxidentiteiten voor onderzoek, maar nooit
  credentials, confirmation tokens, headers, ruwe Google-responses of volledige profielen.
  Mutation-timeouts en latere reconciliation krijgen afzonderlijke audit-events met dezelfde
  veilige correlation-id; het oorspronkelijke fout-event wordt niet overschreven.
- Group-audits bevatten geen credentials, confirmation tokens, headers of ruwe Google-responses.
  Mutation- en reconciliation-events blijven afzonderlijk zodat het oorspronkelijke onbekende
  resultaat behouden blijft.
- User-status reads en writes gebruiken afzonderlijk `admin.directory.user.readonly` en
  `admin.directory.user`. Alleen customer-admins kunnen muteren; canonical immutable ID en Google
  `customerId` worden opnieuw gevalideerd. Admin-, DWD-, self-, service-, archived/deleted en
  onbekend/Google-gesuspendeerde accounts zijn fail-closed beschermd.
- User-status confirmations zijn vijf minuten geldig, atomisch single-use en gebonden aan actor,
  customer, organization, connector, Google customer, user-id, action en verwachte status. De
  database bevat alleen het SHA-256 token-digest en veilige metadata. Eén `users.update` wijzigt
  uitsluitend `suspended`; timeouts leiden alleen tot begrensde read-only `users.get`
  reconciliation en nooit tot een herhaalde write.
- User-status audits gebruiken immutable target-ID en veilige state/outcome/correlation metadata;
  confirmation tokens, userprofielen, credentials en ruwe Google-responses worden niet opgeslagen.

## Applicatiebeveiliging

- De huidige development-authenticatie en rollenfoundation zijn niet geschikt als productie
  identity management. Voeg voor productie sterkere authenticatie, accountbeheer, rate limiting en
  session policies toe.
- Valideer DREAD-waarden server-side; huidige API beperkt waarden tot 0 t/m 10.
- Houd database-migraties reviewbaar en klein.
- Beperk CORS per omgeving via `BACKEND_CORS_ORIGINS`.

## Synthetische data cleanup

- Een cleanup-reviewplan is read-only, maximaal 30 minuten geldig en op zichzelf nooit toestemming
  om data te verwijderen. Exacte UUID's en audit/customer-koppelingen blijven in genegeerde,
  private bestanden met directorymodus `0700` en bestandsmodus `0600`.
- De offline executor mag niet als API, UI-actie, scheduler of automatische job worden aangeboden.
  Uitvoering vereist een aparte menselijke goedkeuring, volledig database/credential-backupherstel,
  expliciete UUID-selecties en de volledige plan-digestbevestiging.
- Uitvoering gebruikt één `SERIALIZABLE` PostgreSQL-transactie, een transactionele advisory lock en
  row locks. Iedere drift of lockconflict weigert en rolt terug. Na een ambigu commitresultaat is
  alleen read-only reconciliation toegestaan; nooit automatisch opnieuw uitvoeren.
- Google-credentialvolumes en Workspace-API's maken geen deel uit van cleanup. Audit-events blijven
  bestaan en alleen hun verwijzing naar een verwijderde, goedgekeurde synthetische customer wordt
  via de bestaande foreign key losgekoppeld.
- Zie `docs/SYNTHETIC_DATA_CLEANUP.md` voor het volledige operator- en herstelproces.

## Logging

- Log geen request bodies met gevoelige informatie.
- Log geen secrets of connector credentials.
- Voeg audit logging toe voor assessment- en finding-wijzigingen zodra gebruikersbeheer bestaat.

## CI/CD

- GitLab CI en GitHub Actions voeren backend lint/tests en frontend audit/lint/tests/build uit.
- Frontend CI controleert npm dependencies; secret scans worden tijdens public-readiness reviews
  uitgevoerd.
- Gebruik CI secrets/variables voor echte omgevingsconfiguratie en print die waarden nooit.
- Zie `/SECURITY.md` voor het publieke disclosurebeleid. GitHub Private Vulnerability Reporting moet
  vóór publicatie als repositorysetting worden ingeschakeld.
