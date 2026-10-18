# Synthetic smoke-test isolation and cleanup review

Older versions of `make smoke-api` sent fixture-writing requests to the normal development API.
They created customers, organizations, connector metadata, assessments, assets, findings, DREAD
scores, mock scan runs and related audit history without removing them. A synthetic-looking name is
never, by itself, permission to delete data.

No tool described here can perform a committed cleanup. Existing records, Google Workspace
connectors, credential files and audit history must remain unchanged until a separately reviewed
cleanup implementation and exact allowlist are explicitly approved.

## Isolated smoke tests

Run the normal target:

```sh
make smoke-api
```

The target now uses `docker-compose.qa-isolated.yml` in a random, dedicated Compose project. It:

- creates a project-scoped PostgreSQL volume and never publishes the PostgreSQL port;
- builds a separate backend and publishes it only on a random loopback port;
- generates temporary database, signing and development-login secrets;
- mounts empty `tmpfs` directories where Google credentials would otherwise be available;
- disables the Google Workspace connector rollout setting;
- invokes no Google Workspace mutation endpoint;
- removes the isolated containers, network and database volume after success, failure or a handled
  interruption; and
- never runs `down --volumes` against the normal WGASuite Compose project.

The fixture-writing check script refuses direct execution unless the isolated runner supplies its
project guard, and it refuses the normal `127.0.0.1:8000` backend. If the isolated project, random
loopback binding or required tools cannot be established, the smoke test fails closed. The normal
WGASuite stack may remain running throughout.

## Aggregate read-only inventory

With the development stack running, execute:

```sh
docker compose exec -T backend python -m app.maintenance.synthetic_record_inventory
```

The command changes its PostgreSQL transaction to read-only. It reports aggregate candidate,
association and blocker counts only; it never prints names, UUIDs, contact details, domains,
delegated administrators, credential references or Google user data. `safe_to_delete_now` remains
`false` in every result.

Selection is stricter than a name prefix. The generated timestamp/PID token must match exactly
across the customer name, customer slug, organization name, assessment, manually created asset and
finding. Connector metadata, the mock asset, all seven catalog findings, DREAD scores and the mock
scan run must have the exact shapes produced by `scripts/dev/smoke_api.sh`. Each customer must own
only its one matching organization.

The analysis also checks connector-account and credential metadata, customer memberships, Gmail
delegate confirmations, Groups membership confirmations, user-status confirmations and findings
whose asset and assessment cross organization boundaries. Credential references, unexpected
records, unmatched tokens or mixed customer data are blockers.

## Private exact-identifier manifest

Generate a private manifest from the normal database with:

```sh
make synthetic-cleanup-dry-run
```

The database transaction is read-only. Exact UUIDs are written beneath
`backend/app/maintenance/.private/`, which is excluded from Git. The directory is mode `0700`; the
manifest and checksum sidecar are mode `0600`. The directory is also excluded from the backend
Docker build context. Standard output contains only aggregate counts, the manifest filename and its
SHA-256 checksum, so that summary can be shared without exposing the identifier allowlist.

The tool refuses to create a manifest when any candidate is ambiguous or mixed. Connector
credential reference values are never copied into the manifest; it records only whether credential
or service-account metadata is present. Keep the manifest private and never attach it to an issue,
commit or pull request.

The manifest distinguishes records that a future, separately approved cleanup would target from
audit rows that must remain:

- candidate organizations would need explicit deletion because deleting a customer alone sets the
  organization's `customer_id` to null;
- organization deletion cascades to assessments, assets, connector accounts, connector configs and
  Google mutation confirmations;
- assessment deletion cascades to findings, DREAD scores and scan runs;
- customer deletion cascades to memberships; and
- audit events remain stored while their customer reference is detached by `ON DELETE SET NULL`.

## Rollback-only cascade validation on a restored backup

To validate those foreign-key effects, use a private PostgreSQL custom-format backup outside the
repository:

```sh
make synthetic-cleanup-validate-restore BACKUP_PATH=/absolute/private/path/backup.dump
```

The backup must have mode `0600`. The wrapper restores it into a new non-published PostgreSQL
service in a random Compose project and creates a one-time sentinel. Only when the exact isolated
database name, validation mode and sentinel nonce all match can the validator exercise the
candidate deletes. It checks that dependent candidates disappear, audit rows remain with detached
customer references, then unconditionally rolls the transaction back and verifies that every row
returned. The disposable database volume is removed afterward. No Google credential archive or
credential volume is mounted.

There is deliberately no commit option and no production cleanup execution mode.

## Future cleanup procedure (separate approval required)

1. Review the aggregate summary, private manifest, checksum and rollback-validation result.
2. Verify database and credential backups through isolated recovery tests.
3. Obtain explicit approval for the exact UUID allowlist, cascade impact and audit handling.
4. Implement and review a separate cleanup mechanism limited to that allowlist.
5. Coordinate any approved credential-file handling separately and recoverably.
6. Verify foreign-key integrity, tenant scoping, connector status, audit retention and application
   behavior before retiring backups.

This remains a plan, not deletion authorization. Do not run `DELETE`, `TRUNCATE`, database resets,
global Docker volume pruning, `docker compose down --volumes` for the normal WGASuite project, or
credential-volume removal as part of inventory or dry-run work.
