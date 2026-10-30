# Google Workspace connector

WGASuite provides a five-step wizard, a real read-only connection test, a paginated read-only
Directory, exact user lookup by primary email or user alias, and guarded Gmail mailbox delegate
management using a service account with Domain-Wide Delegation (DWD). It also provides customer-scoped Google Groups
discovery, a read-only Organizational Units tree, and guarded direct-user membership changes.
Customer administrators can also perform
guarded suspension and safe reactivation from the central user detail. The security-check catalog
remains mock-only as documented in the README.

## Wizard setup flow

Select a customer organization and open **Google Workspace**. For a connected organization, select
**Manage connection** to expand the existing wizard; unconfigured organizations show it
automatically:

1. Follow the official links to select a Google Cloud project, enable Admin SDK, create a service
   account, enable DWD, and download a JSON key. WGASuite does not automate Google Cloud.
2. Upload that JSON key (recommended) or select an operator-provisioned server-file reference.
3. In Google Admin, authorize the numeric client ID shown by the wizard with the exact read-only
   scopes shown below. Each value has a copy button.
4. Save an active delegated administrator email. It may use any domain in the Workspace tenant;
   WGASuite deliberately does not enforce the optional primary-domain suffix.
5. Explicitly click **Test connection**. Tests never run on load or while saving credentials.

Reopening the organization restores safe configuration metadata, current status, last test time,
and any sanitized error. It never restores or reveals credential content.

## Google setup

1. Create a dedicated service account in a Google Cloud project.
2. Enable the Admin SDK API for that project.
3. Enable Domain-Wide Delegation on the service account and record its numeric OAuth client ID.
4. In Google Admin, open **Security > Access and data control > API controls > Manage Domain Wide
   Delegation**, add or edit that client ID, and authorize exactly these read-only scopes:

   ```text
   https://www.googleapis.com/auth/admin.directory.user.readonly
   https://www.googleapis.com/auth/admin.directory.orgunit.readonly
   ```

5. Choose an active delegated administrator with permission to read the requested Directory user.
6. Configure that email as `admin_subject_email` in the wizard.

For Gmail delegate management, also enable the Gmail API and add both scopes below to the same DWD
client while preserving the Directory scope:

```text
https://www.googleapis.com/auth/gmail.settings.basic
https://www.googleapis.com/auth/gmail.settings.sharing
```

The first scope is used only to list delegates. The second is used only for confirmed create and
delete calls. WGASuite does not request `mail.google.com`, `gmail.modify`, or `gmail.readonly` as
shortcuts and never modifies DWD grants automatically.

For Google Groups, add both Directory scopes below while preserving the user and Gmail scopes:

```text
https://www.googleapis.com/auth/admin.directory.group.readonly
https://www.googleapis.com/auth/admin.directory.group.member
```

The first is used for group discovery, details, direct members and reconciliation. The second is
used only for a confirmed `members.insert` or `members.delete`. The UI exposes the existing numeric
client ID, each individual scope and one copyable comma-separated scope set. WGASuite never edits
Google Admin DWD grants and never performs a write to test authorization.

For user suspension and reactivation, add this separate Directory write scope while preserving
every read-only, Gmail and Groups scope:

```text
https://www.googleapis.com/auth/admin.directory.user
```

This scope is used only after an explicit preview and one-time confirmation. The existing
connection test remains read-only and does not prove that this write grant or the delegated
administrator's write privilege is available. WGASuite never edits DWD grants or performs a test
user write.

See Google's official [service-account credential guide](https://developers.google.com/workspace/guides/create-credentials#service-account),
[API enablement guide](https://developers.google.com/workspace/guides/enable-apis), and
[DWD guide](https://support.google.com/a/answer/162106). The Directory connection test itself still
uses only the user read-only scope and does not prove OU access. The OU scope is requested only by
the operation-scoped Organizational Units client. Google Admin changes can take time to propagate.
WGASuite never changes DWD authorization automatically and does not request the full
`admin.directory.orgunit` scope for this read-only feature.

## What the connection test does

After authorization and tenant-scoped configuration resolution, WGASuite constructs fresh
delegated credentials and makes exactly this probe:

```text
Service:    admin
Version:    directory_v1
Method:     users.get
userKey:    configured delegated administrator subject
projection: basic
viewType:   admin_view
fields:     id,primaryEmail,customerId
Scope:      https://www.googleapis.com/auth/admin.directory.user.readonly
```

The request runs once without automatic retries and with a bounded timeout (20 seconds by default,
configured by `GOOGLE_WORKSPACE_REQUEST_TIMEOUT_SECONDS`). The returned profile is discarded.
WGASuite only verifies that its primary email matches the configured subject. It does not compare
the suffix with `primary_domain`, because a Workspace customer may use multiple domains. A success
proves only this one Directory user read; it does not prove Gmail, future write, or mock security-
check access. See the official [`users.get` reference](https://developers.google.com/workspace/admin/directory/reference/rest/v1/users/get).

## User and alias lookup

The **User & Alias Lookup** panel is the primary live administration surface. It uses the active
organization and the same connected credential,
delegated administrator, timeout, and read-only scope as the connection test. It issues one exact
Directory request; it never enumerates the tenant:

```text
POST:       /api/v1/organizations/{organization_id}/google-workspace/users/lookup
Method:     users.get
userKey:    submitted primary email or user alias
projection: basic
viewType:   admin_view
fields:     id,primaryEmail,customerId,name(fullName),aliases,nonEditableAliases,suspended,
            archived,orgUnitPath,isMailboxSetup,isAdmin,isDelegatedAdmin,suspensionReason,
            deletionTime
Scope:      https://www.googleapis.com/auth/admin.directory.user.readonly
```

Google resolves both primary addresses and aliases through `userKey`. WGASuite compares the
submitted address case-insensitively with the canonical primary email, editable aliases, and
non-editable aliases, including aliases on another verified Workspace domain. The typed response
contains only the fields above and a `matched_by` classification. It is displayed and discarded;
no user profile is stored in PostgreSQL.

The endpoint uses POST so the searched address does not appear in a URL. Access requires a platform
administrator or an active `customer_admin` membership for the organization's customer. Tenant
authorization happens before credential resolution. Audit records contain tenant, actor, outcome,
safe error code, and match type only—not the searched address or returned profile.

This feature searches Directory users only. A not-found result does not prove the address is unused:
Google Groups, Group aliases, external forwarding destinations, contacts, and mailbox messages are
separate resources. `isMailboxSetup` describes Google's reported setup state; it does not grant or
verify Gmail delegation or mailbox access.

## Read-only user directory

The **User Directory** is the default users view for a connected organization. It verifies the
configured administrator with the exact lookup service, takes Google's returned `customerId`, and
then performs a bounded list request:

```text
POST:       /api/v1/organizations/{organization_id}/google-workspace/users/list
Method:     users.list
customer:   verified customerId
projection: basic
viewType:   admin_view
maxResults: 25, 50 or 100
orderBy:    email, givenName or familyName
sortOrder:  ASCENDING or DESCENDING
Scope:      https://www.googleapis.com/auth/admin.directory.user.readonly
```

Server-side Google query clauses provide general, email/alias, given-name, family-name and full-name
search, plus suspended, super-administrator, delegated-administrator, archived and organizational-
unit filters. An organizational-unit filter includes descendants, matching the Directory API's
query behavior. Multiple active clauses are combined with `AND`; user input is escaped and bounded
before it reaches Google.

The endpoint returns a typed subset of the basic profile: stable ID, primary email, nullable name
fields, nullable organizational unit and state/admin flags, and nullable creation and last-login
timestamps. It does not return custom schemas, phone numbers, addresses or credential data. Every
returned row must carry the same Google `customerId`; one mismatch fails the entire request.

Pagination tokens remain opaque to the browser and are never decoded or persisted. Google does not
return a total user count and may expire a page token; the UI then requires a return to page one.
Directory responses and filter values are not persisted, and audit metadata records only safe
filter categories, request shape and result count—not queries, emails, profile data or page tokens.
Selecting a row passes its canonical primary email to the existing exact lookup, which remains the
only user-details path. This feature performs no Google Workspace mutations.

## Read-only Organizational Units

The **Organizational Units** tab resolves the immutable Google customer ID through the configured
delegated administrator, then creates a fresh client with only the OU read-only scope:

```text
POST:       /api/v1/organizations/{organization_id}/google-workspace/orgunits/list
Method:     orgunits.list
customerId: verified customerId
type:       allIncludingParent
Scope:      https://www.googleapis.com/auth/admin.directory.orgunit.readonly
Retries:    0
```

`allIncludingParent` is explicit because Google's default `children` type returns only immediate
children and cannot establish the complete hierarchy. WGASuite requests the root and every
descendant in one bounded call, accepts an empty response, and normalizes unordered results by
immutable `orgUnitId`, `parentOrgUnitId`/path and full `orgUnitPath`. Duplicate IDs or paths,
orphaned parents, inconsistent paths and cycles fail closed instead of being displayed as a
trusted tree. Results are not persisted or cached.

An identifier-only detail endpoint is also available:

```text
POST:       /api/v1/organizations/{organization_id}/google-workspace/orgunits/get
Body:       {"org_unit_id":"<immutable Google OU ID>"}
Method:     orgunits.get
```

Paths and customer IDs supplied by callers are not accepted. Both endpoints authorize the actor
against the selected organization's customer before credential access, use the same verified
Google customer ID, disable client retries and emit privacy-safe audit metadata. The UI is
explicitly read-only; OU creation, update, deletion, user/device movement and bulk/CSV workflows
remain future DIR-003 work.

## User detail and reverse group memberships

The exact user detail combines Directory identity, aliases, account/admin flags and available
timestamps with the existing Gmail delegation section and a read-only direct-group section:

```text
POST /api/v1/organizations/{organization_id}/google-workspace/users/group-memberships
Discovery:    groups.list(userKey=<canonical immutable user ID>)
Ownership:    groups.list(customer=<verified customerId>, query=email=<candidate primary email>)
Direct role:  members.get(groupKey=<verified group ID>, memberKey=<canonical user ID>)
Page sizes:   10 or 25 candidates
Scopes:       admin.directory.user.readonly + admin.directory.group.readonly
```

Google does not allow `userKey` and `customer` in the same `groups.list` call. Candidate discovery
therefore is not treated as tenant or direct-membership proof. WGASuite first resolves the user
through the existing tenant-authorized exact lookup and compares its `customerId`; it then requires
each candidate's immutable ID and primary email to match an exact customer-scoped group result.
Email-domain suffixes are never ownership evidence. Only after that check does `members.get`
establish a direct `MEMBER`, `MANAGER` or `OWNER` role and optional status.

External groups and candidates for which no direct member exists are omitted from the primary list,
with page-level omitted counts. Nested/transitive membership is not represented as direct;
comprehensive transitive relationships may require a future Cloud Identity implementation. The
Google continuation token is preserved even if all candidates on a page are filtered, and the UI
supports that empty-page continuation. No total is invented.

Each page is bounded to 25 candidates and 50 ownership/member verification calls, with
`num_retries=0`; oversized or unsafe work returns an actionable budget error. Rate limits,
expired tokens, permissions, timeouts and outages use the connector's sanitized error mapping.
No profile, membership, query or token is persisted, and audits record only match type, safe
counts, page shape and outcome. Opening a membership reuses the existing customer-verified Groups
screen and its existing authorization. This read path has no access to `members.insert` or
`members.delete`.

## User suspension and reactivation

The central user detail provides guarded suspend/reactivate preview, mutation and reconciliation
endpoints under:

```text
POST /api/v1/organizations/{organization_id}/google-workspace/users/{suspend|reactivate}/preview
POST /api/v1/organizations/{organization_id}/google-workspace/users/{suspend|reactivate}
POST /api/v1/organizations/{organization_id}/google-workspace/users/{suspend|reactivate}/reconcile
```

Only a platform administrator or active customer administrator may use these endpoints. Before
preview and again immediately before a write, WGASuite resolves the configured DWD administrator
and requested user through Directory, compares Google's opaque `customerId`, canonicalizes aliases
and binds the operation to the immutable Google user ID. It never trusts an email suffix or a
browser-supplied customer identifier.

Super administrators, delegated administrators, the configured DWD administrator, an identifiable
acting administrator, the configured service identity, archived/deleted users and accounts already
in the requested state are blocked. Reactivation is available only when Google reports a suspended
account with `suspensionReason=ADMIN`; missing, abuse/security/Terms-of-Service and other reasons
fail closed and must be handled in Google Admin. Administrator accounts remain protected for both
directions in this release.

Preview stores only safe binding data and a SHA-256 confirmation-token digest in
`google_workspace_user_status_confirmations`. The five-minute token is bound to actor, local
customer, organization, connector, Google customer, immutable user, operation and expected state.
Consumption is atomic and single-use. After revalidation the write client uses only
`admin.directory.user` and makes exactly one request with no automatic retries:

```text
users.update(userKey=<immutable user ID>, body={"suspended": true|false})
```

No full profile, alias, name, organizational unit, password, role or membership is submitted.
Suspension restricts access to Google Workspace services but does not delete the user's data;
license charges may continue. Reactivation removes an eligible administrator-controlled suspension
and is not deleted-user recovery (`users.undelete` is never called).

Timeouts, transport interruptions and ambiguous Google 5xx responses move the consumed operation
to `unknown`; the write is never retried. Reconciliation uses only
`admin.directory.user.readonly`, performs at most four `users.get` calls by immutable ID with a
0/0.5/1/2-second backoff, five-second read timeout and 20-second total ceiling, and verifies tenant
and current suspension state. That observation does not prove which request caused the state.
Unknown outcomes remain visible with a **Check status** action.

Mutation and reconciliation audits are separate. They retain actor, organization/customer,
immutable target ID, previous/requested state, sanitized outcome/reason, and safe correlation data;
they never store confirmation tokens, credentials, OAuth tokens, raw Google responses or full user
profiles. No live user write is part of automated tests or routine QA.

## Gmail mailbox delegation

After an administrator resolves a Directory user, the **Mailbox Delegates** section lists that
mailbox's delegates and verification states. These POST endpoints keep private addresses out of
logged URL paths:

```text
POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/list
POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/create/preview
POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/create
POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/create/reconcile
POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/remove/preview
POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/remove
POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/remove/reconcile
```

The backend first authenticates the actor and requires platform-admin or active customer-admin
access. It resolves the configured administrator, mailbox owner, and delegate with Directory API
and compares Google's `customerId`; matching email suffixes are never treated as tenant proof.
Aliases are converted to canonical primary emails. Suspended, archived, non-Gmail, self-delegate,
cross-tenant, duplicate-create, and missing-remove targets are rejected before a write.

Gmail DWD credentials impersonate the canonical primary email of the mailbox owner. Calls then use
`userId=me`. The connector's configured administrator subject remains unchanged and continues to
be used for Directory resolution only. The restricted factory accepts only one exact delegate
scope at a time and cannot construct a generic arbitrary-subject Gmail client.

Create and remove require a preview that records canonical identities and issues an opaque,
five-minute confirmation. Only its actor, organization, operation and exact identities may consume
it. Consumption is atomic and one-time before the Google write, so double clicks and replay cannot
repeat a change. Directory identities and the current relationship are revalidated immediately
before consumption. Google requests use bounded timeouts and `num_retries=0`; an ambiguous network
failure is never retried automatically.

The Gmail HTTP transport uses the configured 20-second timeout by default. A timeout proves only
that a response did not arrive in time; Google can still finish the operation. On a timeout,
network interruption or ambiguous Google 5xx response, the consumed confirmation moves to an
explicit `unknown` state and the API returns a safe correlation ID. The UI automatically invokes
the matching reconciliation endpoint and also exposes **Check status** while the outcome remains
unknown.

Reconciliation accepts only the original opaque confirmation token and rebinds it to the original
actor, organization, operation, canonical owner and canonical delegate. It revalidates Directory
identities, then performs at most four `delegates.list` calls using only
`gmail.settings.basic`, a 0/0.5/1/2-second backoff, five-second per-read timeouts and a 20-second
overall ceiling. Create is verified only when the canonical delegate is visible as `Accepted`;
delete is verified only when that delegate is absent. Otherwise the status remains `unknown`.
Observed state verifies the current state, not that the original request caused it. Reconciliation
has no code path to `delegates.create` or `delegates.delete`.

Google requires a delegate's primary email and may take approximately one minute to make new
access usable. Delegate/delegator limits vary by organization; Google documents general limits,
but WGASuite does not encode an approximate number as a universal constant. Google enforces the
applicable tenant limit. Delegates can read, send and delete messages through Gmail, but WGASuite
does not expose Gmail message or contact APIs.

Successful and failed/rejected administrative operations are audited with actor, customer,
organization, operation, outcome, safe reason and the minimal canonical mailbox identities needed
for investigation. An ambiguous mutation retains its original failure audit with a safe correlation
ID and timeout flag; each reconciliation records attempt count plus verified or unknown final state
as a separate event. Confirmation tokens, credentials, OAuth tokens, authorization headers, raw
Google responses and full profiles are never stored in audit metadata.

## Google Groups and direct memberships

The **Groups** tab provides these organization-scoped POST endpoints, keeping addresses and Google
page tokens out of URL paths:

```text
POST /api/v1/organizations/{organization_id}/google-workspace/groups/search
POST /api/v1/organizations/{organization_id}/google-workspace/groups/get
POST /api/v1/organizations/{organization_id}/google-workspace/groups/members/list
POST /api/v1/organizations/{organization_id}/google-workspace/groups/members/add/preview
POST /api/v1/organizations/{organization_id}/google-workspace/groups/members/add
POST /api/v1/organizations/{organization_id}/google-workspace/groups/members/add/reconcile
POST /api/v1/organizations/{organization_id}/google-workspace/groups/members/remove/preview
POST /api/v1/organizations/{organization_id}/google-workspace/groups/members/remove
POST /api/v1/organizations/{organization_id}/google-workspace/groups/members/remove/reconcile
```

The service resolves the configured delegated administrator with Directory user lookup and takes
Google's returned `customerId` as the tenant boundary. Search always calls
`groups.list(customer=<verified customerId>)`; it never substitutes the configured domain. A group
selected by primary address or alias is canonicalized with `groups.get` and its group ID must also
appear in an exact customer-scoped list response before details or members are used. This supports
multi-domain customers without treating matching email suffixes as ownership proof.

Group results include primary email, aliases, description and Google's direct-member count when
available. Direct members are retrieved with `includeDerivedMembership=false` and paginated with
Google page tokens. User, nested group, customer-wide and external/unknown member types remain
distinct in the UI; an empty page is a successful read.

Add supports only an existing internal Directory user. User aliases resolve to a canonical primary
email and the user's `customerId` must match the verified group customer. New memberships always
use role `MEMBER`; role changes are not available. Remove supports only an existing direct internal
user membership. Owner memberships are conservatively protected from all removal in this release,
which also prevents last-owner removal. Nested groups, external/customer-wide identities and
recognized dynamic/special groups are read-only. If Google reports that a group cannot be changed
through Directory API, the operation returns `group_membership_unsupported` rather than trying a
different API or broader scope.

Both mutations require a five-minute, actor/organization/operation/group/user-bound confirmation.
The server stores only a SHA-256 token digest, revalidates the canonical group, user and current
direct relationship, then atomically consumes the confirmation before one write with
`num_retries=0`. A timeout, network interruption or ambiguous Google 5xx never triggers another
write. Reconciliation rebinds the original identities and performs at most four direct-member list
polls with the same 0/0.5/1/2-second backoff, five-second read timeout and 20-second overall ceiling.
Presence verifies add state and absence verifies remove state; neither proves which request caused
the observed state. The original failure audit remains separate from every reconciliation audit.

Connector operators may use group discovery and direct-member reads. Membership preview, execute
and reconciliation endpoints require platform-admin or active customer-admin access. Backend role
and tenant checks always occur before credential material is loaded. Group creation/deletion,
aliases, role changes, settings, dynamic membership rules and bulk operations remain out of scope.

## Credential security and authorization

The database stores the provider selection plus safe service-account email and numeric client ID.
It never stores the JSON, private key, private key ID, access token, or refresh token. API responses
never contain those values or the opaque `credential_ref`, and no download endpoint exists. Audit
events contain only actor and tenant context, outcome, safe error code, and provider name—never an
upload body, reference, email, client ID, key ID, token, or internal path.

Credential mutation is a customer-admin-only operation. A platform administrator or active
`customer_admin` membership for the connector's customer is required. Customer users, viewers,
platform support, inactive memberships, and actors from another tenant are denied before the body
is processed. Existing connector-operation roles remain unchanged for the manual connection test.

The browser sends an explicit bearer token rather than relying on ambient cookie authority, and the
backend restricts CORS origins. Thus a cross-site form cannot silently authorize an upload;
authorization and tenant scoping remain the primary controls.

### Managed upload (recommended)

`PUT /api/v1/connector-configs/{id}/credentials` accepts a raw JSON body only. The strict 64 KiB
default is configured by `GOOGLE_WORKSPACE_CREDENTIAL_MAX_BYTES`. Validation rejects malformed or
duplicate JSON fields, non-service-account credentials, missing Google fields, nonnumeric client
IDs, unexpected token endpoints, invalid service-account emails, and invalid private keys. Browser
file names and paths are never accepted.

Validated JSON is atomically written beneath:

```text
${GOOGLE_WORKSPACE_MANAGED_CREDENTIALS_DIRECTORY}/<organization-uuid>/service-account.json
```

Directories use `0700`; files use `0600`. Temporary files use exclusive no-follow creation, are
flushed before atomic replacement, and are removed after failures. Every tenant has a fixed
directory and filename. Previous connection success is invalidated before replacement and again
after selection, so a stale in-flight test cannot leave changed credentials marked verified.

Docker Compose runs the backend as unprivileged UID/GID `10001` and mounts a backend-only named
volume at `/var/lib/wgasuite/google-credentials`. It survives container recreation and is not
mounted into the frontend, database, or another service. In production, mount an encrypted,
backend-exclusive persistent volume or deployment-specific secret store at the configured path;
make UID/GID `10001` its owner and restrict host and snapshot access.

Back up the encrypted credential volume together with the database. Recovery requires both, then
migrations and a manual test of every restored connector. A database-only restore cannot reconnect.
For rotation, create a new Google key, upload it, update DWD if its numeric client ID changed, test,
and only then revoke the old key. Upload automatically clears the old verified state.

### Operator-provisioned file

The alternative `file` provider resolves an opaque reference only beneath:

```text
${GOOGLE_WORKSPACE_CREDENTIALS_DIRECTORY}/<organization-uuid>/<credential-ref>.json
```

Path separators, traversal, and symlinked credential files are rejected. Docker mounts
`./secrets/google` read-only at `/run/secrets/wgasuite/google`; the host directory is ignored by
Git. The wizard validates the file and records only safe metadata. This option supports deployment
tools that inject credentials outside WGASuite. Rotate it by atomically replacing the file,
reselecting the reference, and testing again.

Never put real credentials in source control, `.env`, connector metadata, logs, issues, pull
requests, screenshots, or ordinary backups. Limit Google Cloud access to key administrators and
remove old keys promptly after verified rotation.

## Connector API compatibility

The wizard is preferred. A trusted admin may still configure an external opaque reference through
the organization-scoped connector API; it is a reference, not a filesystem path:

```json
{
  "display_name": "Example Google Workspace",
  "primary_domain": "example.invalid",
  "admin_subject_email": "admin@example.invalid",
  "auth_method": "service_account_domain_wide_delegation",
  "credential_provider": "file",
  "credential_ref": "example-workspace",
  "notes": "Read-only Directory connection"
}
```

A configured credential is unverified. Changing the authentication method, subject, provider,
reference, or credential file resets status to `configured` and clears the prior test timestamp and
error. Connection status becomes `connected` only after a new real probe succeeds.

## Troubleshooting

The test persists `last_tested_at`, `connected` or `connection_failed`, a safe error code, and an
optional sanitized message. Common codes include:

| Error code | Check |
| --- | --- |
| `credential_reference_missing` | Configure a credential in wizard step 2. |
| `credentials_not_found` | Check organization UUID, mount, filename, and backend permissions. |
| `invalid_credentials` | Confirm valid service-account JSON and a nonsymlink file. |
| `invalid_admin_subject` | Configure a complete administrator email address. |
| `delegation_rejected` | Verify DWD, numeric client ID, exact scope, and subject. |
| `google_unauthorized` | Verify that the key is active and delegated credentials are correct. |
| `google_subject_not_found` | Verify the administrator account exists and is active. |
| `google_user_not_found` | No exact Directory user or user alias matched; check Groups separately. |
| `google_user_lookup_mismatch` | Google returned an unexpected identity; retry and investigate safely. |
| `google_tenant_mismatch` | Confirm both canonical users belong to the connector's Google customer. |
| `google_group_not_found` | Confirm the group exists in the verified Workspace customer. |
| `google_group_lookup_mismatch` | Google returned a group unrelated to the requested primary address or alias. |
| `group_member_already_exists` / `group_member_not_found` | Refresh direct members before another change. |
| `group_member_unsupported` | External, nested, customer-wide and unknown member types are read-only. |
| `group_owner_protected` | Assign and verify ownership in Google Admin; WGASuite does not remove owners. |
| `group_membership_unsupported` | Manage this dynamic/special group in Google Admin or its owning service. |
| `group_confirmation_invalid` / `group_confirmation_expired` / `group_confirmation_used` | Preview the exact membership change again. |
| `group_reconciliation_not_available` / `group_reconciliation_expired` | Refresh; only the original ambiguous write can be checked within five minutes. |
| `gmail_api_unavailable` | Enable Gmail API in the credential's Cloud project. |
| `gmail_scope_missing` | Add the required Gmail read or sharing DWD scope. |
| `gmail_mailbox_not_configured` | Select an active user with Gmail enabled. |
| `gmail_user_ineligible` | Use active, non-archived, Gmail-enabled accounts. |
| `gmail_delegate_already_exists` | Refresh; the delegate already has access. |
| `gmail_delegate_not_found` | Refresh; the delegation no longer exists. |
| `gmail_confirmation_invalid` / `gmail_confirmation_expired` / `gmail_confirmation_used` | Preview the exact operation again. |
| `gmail_reconciliation_not_available` | Refresh; only the original ambiguous mutation can be reconciled. |
| `gmail_reconciliation_expired` | The five-minute confirmation/reconciliation window ended; refresh the list. |
| `google_forbidden` | Check DWD, scope, API access, and administrator privilege. |
| `missing_scope_or_permission` | Google reported insufficient permission. |
| `google_api_unavailable` | Enable Admin SDK in the credential's Cloud project. |
| `google_rate_limited` | Wait before manually retrying. |
| `google_service_unavailable` | Retry after a transient Google 5xx failure. |
| `google_timeout` / `google_network_error` | Do not resubmit a Gmail or Groups mutation; use **Check current state**. For reads, check outbound HTTPS, DNS, proxy and firewall. |

Raw upstream bodies, stack traces, credentials, internal paths, and Google profiles are never
returned. A generic 403 is intentionally not presented as one specific DWD problem.

## Reproducible live verification

1. Sign in as a platform or customer admin and select the target organization.
2. Complete wizard steps 1–4 with a real JSON key or already provisioned file.
3. Complete Google DWD using the displayed client ID and exact read-only scope.
4. Start the stack and apply migrations with `make docker-up` and `make db-upgrade`.
5. Open step 5 and click **Test connection**.
6. Confirm **connected**, a current timestamp, and no error; refresh and confirm it remains.
7. Review `connector_config.tested` and credential-change audit events for safe metadata only.
8. Recreate only the backend container, reopen the organization, and retest to verify persistence.
9. In **User & alias lookup**, search the delegated administrator's primary email and confirm the
   canonical Directory account appears.
10. If an existing user alias is safely known, search it and confirm it resolves to the same
    canonical primary email. Do not create or modify an alias merely for this test.
11. Enable Gmail API and authorize both Gmail scopes shown by the connection-management panel.
12. Select a known Gmail-enabled mailbox owner and load **Mailbox Delegates**. An empty genuine
    Google result is a successful read verification.
13. Do not confirm **Grant access** or **Revoke access** during verification unless a separately
    approved change identifies the owner and delegate. Automated tests mock every Gmail write.
14. Authorize both Groups scopes shown by the connection-management panel, open **Groups**, and
    search a known group name or full address. A genuine empty customer result is also a valid read.
15. Open a known group and confirm primary address, aliases and direct members. Do not click a final
    add/remove confirmation during verification. Automated tests mock every Groups write, and live
    membership mutation requires separate explicit approval.

`docker compose down` preserves named volumes. `docker compose down --volumes` is destructive and
removes the credential volume. If real credentials and DWD are unavailable, run automated mocked
tests and record live tenant verification as outstanding—never paste a credential into a ticket,
commit, pull request, or log.
