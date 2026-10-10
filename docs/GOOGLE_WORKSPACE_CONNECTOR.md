# Google Workspace connector

WGASuite provides a five-step wizard, a real read-only connection test, exact Directory user
lookup by primary email or user alias, and guarded Gmail mailbox delegate management using a
service account with Domain-Wide Delegation (DWD). The security-check catalog remains mock-only as
documented in the README.

## Wizard setup flow

Select a customer organization and open **Google Workspace**. For a connected organization, select
**Manage connection** to expand the existing wizard; unconfigured organizations show it
automatically:

1. Follow the official links to select a Google Cloud project, enable Admin SDK, create a service
   account, enable DWD, and download a JSON key. WGASuite does not automate Google Cloud.
2. Upload that JSON key (recommended) or select an operator-provisioned server-file reference.
3. In Google Admin, authorize the numeric client ID shown by the wizard with the exact scope shown
   below. Both values have copy buttons.
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
   Delegation**, add that client ID, and authorize exactly:

   ```text
   https://www.googleapis.com/auth/admin.directory.user.readonly
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

See Google's official [service-account credential guide](https://developers.google.com/workspace/guides/create-credentials#service-account),
[API enablement guide](https://developers.google.com/workspace/guides/enable-apis), and
[DWD guide](https://support.google.com/a/answer/162106). The Directory connection test itself still
uses only its read-only Directory scope. Google Admin changes can take time to propagate.

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
            archived,orgUnitPath,isMailboxSetup
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

## Gmail mailbox delegation

After an administrator resolves a Directory user, the **Mailbox Delegates** section lists that
mailbox's delegates and verification states. These POST endpoints keep private addresses out of
logged URL paths:

```text
POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/list
POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/create/preview
POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/create
POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/remove/preview
POST /api/v1/organizations/{organization_id}/google-workspace/gmail-delegates/remove
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
failure is never retried automatically. Refresh the list before planning another change.

Google requires a delegate's primary email and may take approximately one minute to make new
access usable. Delegate/delegator limits vary by organization; Google documents general limits,
but WGASuite does not encode an approximate number as a universal constant. Google enforces the
applicable tenant limit. Delegates can read, send and delete messages through Gmail, but WGASuite
does not expose Gmail message or contact APIs.

Successful and failed/rejected administrative operations are audited with actor, customer,
organization, operation, outcome, safe reason and the minimal canonical mailbox identities needed
for investigation. Confirmation tokens, credentials, OAuth tokens, authorization headers, raw
Google responses and full profiles are never stored in audit metadata.

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
| `gmail_api_unavailable` | Enable Gmail API in the credential's Cloud project. |
| `gmail_scope_missing` | Add the required Gmail read or sharing DWD scope. |
| `gmail_mailbox_not_configured` | Select an active user with Gmail enabled. |
| `gmail_user_ineligible` | Use active, non-archived, Gmail-enabled accounts. |
| `gmail_delegate_already_exists` | Refresh; the delegate already has access. |
| `gmail_delegate_not_found` | Refresh; the delegation no longer exists. |
| `gmail_confirmation_invalid` / `gmail_confirmation_expired` / `gmail_confirmation_used` | Preview the exact operation again. |
| `google_forbidden` | Check DWD, scope, API access, and administrator privilege. |
| `missing_scope_or_permission` | Google reported insufficient permission. |
| `google_api_unavailable` | Enable Admin SDK in the credential's Cloud project. |
| `google_rate_limited` | Wait before manually retrying. |
| `google_service_unavailable` | Retry after a transient Google 5xx failure. |
| `google_timeout` / `google_network_error` | Check outbound HTTPS, DNS, proxy, and firewall. |

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

`docker compose down` preserves named volumes. `docker compose down --volumes` is destructive and
removes the credential volume. If real credentials and DWD are unavailable, run automated mocked
tests and record live tenant verification as outstanding—never paste a credential into a ticket,
commit, pull request, or log.
