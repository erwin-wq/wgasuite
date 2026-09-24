# Google Workspace connector foundation

GW-001 provides the reusable authentication and Google API client boundary. It does not test a
real connection and does not implement user search, Gmail delegates, or any other administrative
operation.

## Supported authentication

The first supported method is a Google service account with Domain-Wide Delegation (DWD). A
connector identifies a delegated administrator subject such as `admin@example.com`. Each future
feature must provide its own exact OAuth scopes; the foundation has no global or all-purpose scope
list.

The client creation path is:

```text
authorized actor and organization
  -> Google Workspace connector metadata
  -> organization-scoped credential provider
  -> service-account credentials
  -> requested OAuth scopes
  -> delegated administrator subject
  -> Google discovery API client
```

The factory does not cache credentials or clients. This keeps organization, connector, admin
subject and scope boundaries explicit. If caching is introduced later, all four must be included in
the cache identity.

## Google setup

In a non-development Google environment, an administrator must conceptually:

1. Create a dedicated Google Cloud service account.
2. Enable Domain-Wide Delegation for that service account.
3. Enable only the Google APIs required by the WGASuite features being deployed.
4. Authorize only those feature-specific OAuth scopes in Google Admin.
5. Select a delegated administrator subject with the required Google privileges.
6. Make the service-account JSON available to WGASuite through the configured credential provider.

GW-001 does not verify this setup. GW-002 is the planned real connection-test flow.

## Credential security model

Connector metadata and credential material are separate concerns:

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

The database and API never contain or return the service-account JSON, private key, access token or
refresh token. API responses expose `credential_provider` and `credentials_configured`, but not
`credential_ref`. Audit records say whether a credential reference changed without recording its
value.

The `file` provider resolves an opaque reference only under the active organization directory:

```text
${GOOGLE_WORKSPACE_CREDENTIALS_DIRECTORY}/<organization-uuid>/<credential-ref>.json
```

Path separators and traversal references are rejected. The Docker development configuration mounts
`./secrets/google` read-only at `/run/secrets/wgasuite/google`; the host directory is ignored by
Git. Protect it with host filesystem permissions and never place a real credential in the
repository.

## Development example

Use placeholders only in documentation and configuration committed to Git. Given an organization
ID `00000000-0000-0000-0000-000000000001`, a metadata request can look like:

```json
{
  "display_name": "Example Google Workspace",
  "primary_domain": "example.invalid",
  "admin_subject_email": "admin@example.invalid",
  "auth_method": "service_account_domain_wide_delegation",
  "credential_provider": "file",
  "credential_ref": "example-workspace",
  "status": "configured"
}
```

At runtime only, the corresponding file location is:

```text
./secrets/google/00000000-0000-0000-0000-000000000001/example-workspace.json
```

Do not copy credential content into `.env`, connector notes, API payload fields other than the
opaque reference, logs, test fixtures, or source control. A configured reference only means that
metadata exists; it is not proof that the file or Google delegation is valid.

## Error boundary

The connector raises typed, secret-safe errors for missing configuration or credentials, malformed
credentials, invalid admin subjects, delegation failures, insufficient permission, authorization,
rate limits, service availability and other Google API failures. Raw Google response bodies and
credential data are not included in these messages.
