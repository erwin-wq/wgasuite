# Google Workspace connector

WGASuite supports a real, read-only Google Workspace connection test using a service account with
Domain-Wide Delegation (DWD). User search, Gmail delegate administration, and the security-check
catalog remain unimplemented or mock-only as documented in the README.

## What the connection test does

After WGASuite authorizes the actor and resolves the organization-scoped connector configuration,
the test constructs fresh delegated credentials and an Admin SDK Directory API client. It performs
exactly this probe:

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

The request runs once with no automatic retries and a bounded transport timeout (20 seconds by
default, configurable with `GOOGLE_WORKSPACE_REQUEST_TIMEOUT_SECONDS`). The returned profile is
not exposed by the API or stored. WGASuite only verifies that the returned primary account matches
the configured subject. It does not compare the email suffix with `primary_domain`, because a
Workspace customer may use multiple domains. No expected Google customer ID is currently stored,
so a successful test does not claim an independent tenant-identity check.

A successful test proves that Google accepted the delegated credentials and allowed this one
Directory user read. It does not prove that Gmail delegate scopes, Gmail access, future write
operations, or any mock security check is authorized.

See Google's official [`users.get` reference](https://developers.google.com/workspace/admin/directory/reference/rest/v1/users/get)
for the method parameters and authorization scope.

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
6. Configure that email as `admin_subject_email` on the organization connector.

Google's [Domain-Wide Delegation guide](https://developers.google.com/identity/protocols/oauth2/service-account#delegatingauthority)
describes the service-account and Admin console authorization flow.

Do not authorize a write-enabled Directory scope for this test. Google Admin changes can take time
to propagate; retry only after checking the client ID, exact scope, delegated subject, and Admin SDK
API status.

## Credential security model

Connector metadata and credential material remain separate:

```text
connector_configs row                     read-only secret file
---------------------                     ---------------------
organization_id                           private_key
auth_method                               private_key_id
credential_provider                       client_email
credential_ref             !=             service-account JSON
admin_subject_email
primary_domain
```

The database and API never contain or return service-account JSON, private keys, access tokens, or
refresh tokens. API responses expose `credential_provider` and `credentials_configured`, but not
`credential_ref`. Audit records record only the connector ID, actor, organization/customer context,
outcome, safe error code, and whether the result was persisted.

The `file` provider resolves an opaque reference only under the active organization directory:

```text
${GOOGLE_WORKSPACE_CREDENTIALS_DIRECTORY}/<organization-uuid>/<credential-ref>.json
```

Path separators, traversal references, and symlinked credential files are rejected. Docker mounts
`./secrets/google` read-only at `/run/secrets/wgasuite/google`; the host directory is ignored by
Git. Restrict its filesystem permissions and never place a real credential in the repository,
ordinary connector metadata, logs, issues, pull requests, or screenshots.

## Configure the connector

The UI edits non-secret metadata. Supply the opaque `credential_ref` through the organization-
scoped connector API or another trusted deployment workflow; callers cannot provide a filesystem
path. Example placeholders:

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

For organization `00000000-0000-0000-0000-000000000001`, the runtime file would be:

```text
./secrets/google/00000000-0000-0000-0000-000000000001/example-workspace.json
```

A configured reference means only that metadata exists. Connection status becomes `connected`
only after the real probe succeeds. Changing the authentication method, delegated subject,
credential provider, or credential reference immediately invalidates the previous result.

## Results and troubleshooting

The endpoint persists `last_tested_at`, `connected` or `connection_failed`, a safe error code, and
an optional sanitized message. Configuration errors are distinguished from Google and network
errors. Common codes include:

| Error code | Check |
| --- | --- |
| `credential_reference_missing` | Configure an opaque credential reference. |
| `credentials_not_found` | Confirm the organization UUID, secret mount, filename, and permissions. |
| `invalid_credentials` | Confirm the file is valid service-account JSON and is not a symlink. |
| `invalid_admin_subject` | Configure a complete administrator email address. |
| `delegation_rejected` | Verify DWD, numeric client ID, exact scope, and delegated subject. |
| `google_unauthorized` | Google returned HTTP 401; verify the delegated credentials. |
| `google_subject_not_found` | Verify that the delegated administrator account exists and is active. |
| `google_forbidden` | Google returned HTTP 403; check DWD, scope, API access, and admin privilege. |
| `missing_scope_or_permission` | Google explicitly reported insufficient permission. |
| `google_api_unavailable` | Google explicitly reported the API as unavailable/not configured. |
| `google_rate_limited` | Wait before retrying; the probe does not retry automatically. |
| `google_service_unavailable` | Retry after a transient Google 5xx failure. |
| `google_timeout` / `google_network_error` | Check outbound HTTPS, DNS, proxy, and firewall access. |

Raw upstream bodies, stack traces, credentials, internal credential paths, and Google profiles are
never returned. A generic 403 is intentionally not presented as one specific DWD problem because
several configurations can produce it.

## Reproducible live verification

1. Put the service-account JSON in the organization-specific secret directory and make it readable
   by the backend runtime without committing it.
2. Configure the connector metadata and opaque reference for the same organization.
3. Complete the Google DWD setup above with the exact read-only scope.
4. Start the stack and apply migrations with `make docker-up` and `make db-upgrade`.
5. Sign in as an actor authorized to operate that customer's connector.
6. Select the organization, open **Google Workspace connector**, and click **Test connection**.
7. Confirm the UI shows **connected**, a current timestamp, and no error code. Refresh and confirm
   the state remains visible.
8. Review the `connector_config.tested` audit event and confirm it contains no credential reference,
   token, profile, or raw Google response.

If real credentials and DWD authorization are unavailable, run the automated mocked tests and
record live tenant verification as outstanding. Never paste a credential into a ticket, commit,
pull request, or log to make live testing possible.
