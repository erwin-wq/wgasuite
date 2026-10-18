# Synthetic smoke-test isolation and cleanup review

Older versions of `make smoke-api` sent fixture-writing requests to the normal development API.
They created customers, organizations, connector metadata, assessments, assets, findings, DREAD
scores, mock scan runs and related audit history without removing them. A synthetic-looking name is
never, by itself, permission to delete data.

The cleanup workflow has two deliberately separate phases. Phase A is a read-only review plan;
creating it is never deletion authorization. Phase B is a narrow PostgreSQL maintenance command,
not an API endpoint or scheduled job. It can commit only after a current plan, exact database
identity, verified backup attestation, separate human approval, exact UUID repetitions and typed
confirmation all agree. Never run Phase B merely because a plan exists.

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

The database transaction is read-only. Exact UUIDs and canonical row-identity hashes are written beneath
`backend/app/maintenance/.private/`, which is excluded from Git. The directory is mode `0700`; the
manifest and checksum sidecar are mode `0600`. The directory is also excluded from the backend
Docker build context. Standard output contains only aggregate counts, the manifest filename and its
SHA-256 checksum, so that summary can be shared without exposing the identifier allowlist.

Plans expire after 30 minutes. They bind the PostgreSQL system identifier, database OID/name/user,
server version and Alembic revision, plus the exact customer/organization/dependent UUID graph,
per-table content hashes, expected counts and retained audit-event contents. Any database drift
requires a new plan and review; do not edit or re-checksum an old plan.

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

## Guarded Phase B execution

Phase B is intentionally not exposed through HTTP, the UI or a Make target. Its private approval
JSON must be created outside the planning command by the approving human and contain:

- `schema_version: 1` and `mode: synthetic_cleanup_human_approval`;
- the exact plan digest and manifest SHA-256;
- the customer and organization UUID lists repeated in manifest order;
- a non-empty approver identity and external approval reference; and
- an approval time and expiry no more than 15 minutes apart and within the plan lifetime.

A separate mode-`0600` backup-attestation JSON must bind the same plan and database-context digest.
It names a backup set and attester, and supplies an absolute path, SHA-256, creation timestamp and
verification reference for both backups. The PostgreSQL backup requires a successful isolated
restore timestamp. The credential archive requires a complete recovery timestamp—not merely a tar
listing or integrity check. Both backup files must be regular, non-symlink, mode-`0600`, owned by
the executing user, checksum-valid and no more than 24 hours old. The attestation must also record a
successful rollback-only cascade validation whose deleted/audit counts exactly match the plan. A prior credential archive that
has only passed integrity inspection is not sufficient.

The executor requires all of these values explicitly and has no wildcard, discovery, force or
all-candidates option:

```sh
python -m app.maintenance.synthetic_cleanup_execution execute \
  --manifest /private/review.json \
  --manifest-sha256 MANIFEST_SHA256 \
  --plan-digest PLAN_DIGEST \
  --approval /private/approval.json \
  --approval-sha256 APPROVAL_SHA256 \
  --backup-attestation /private/backup-attestation.json \
  --backup-attestation-sha256 ATTESTATION_SHA256 \
  --approve-customer EXACT_CUSTOMER_UUID \
  --approve-organization EXACT_ORGANIZATION_UUID \
  --confirmation "DELETE REVIEWED SYNTHETIC RECORDS PLAN_DIGEST"
```

Repeat each UUID option once for every reviewed pair, in manifest order. Avoid placing private
identifiers in shared shell history, logs, tickets or pull requests. The executor rechecks private
file ownership/permissions and checksums before starting. It then opens one `SERIALIZABLE`
transaction, obtains a global transaction-scoped advisory lock, locks every allowlisted row with
`NOWAIT`, runs the strict smoke-fingerprint analysis again, and compares the complete fresh graph
and database identity to the plan. It explicitly deletes only the listed organizations and
customers; database cascades remove only their verified dependants. It verifies every listed row is
gone and every audit event remains content-identical with only `customer_id` detached. A
non-customer audit marker records the plan/checksum references and aggregate impact before commit.

Drift, ambiguity, lock contention, a stale artifact, wrong database, altered content, missing
backup verification, selection mismatch or existing commit marker rolls back/refuses. A plan can
commit once only. If the connection fails during commit, the tool reports an uncertain outcome and
must not be retried. Reconcile it read-only—even after plan expiry—with:

```sh
python -m app.maintenance.synthetic_cleanup_execution reconcile \
  --manifest /private/review.json \
  --manifest-sha256 MANIFEST_SHA256 \
  --plan-digest PLAN_DIGEST
```

Reconciliation returns `committed`, `not_committed` or `unknown_manual_review` and never retries or
modifies data. Keep backups until post-cleanup integrity, tenant-scoping, connector and application
checks are complete.

After a separately approved real cleanup, first run the inventory and reconciliation read-only,
verify unrelated customer/organization/connector aggregates and inspect the credential volume
without changing it. Then use the existing connector screen's read-only connection test for each
unrelated configured Workspace connector whose operator has authorized that Google API access.
Confirm the stored connector status and delegated administrator still match their pre-cleanup
record. Do not upload/rewrite credentials or invoke Gmail, Groups or user-status mutations as a
cleanup verification step. A connector failure is an investigation signal, never a reason to
restore automatically over the main database.

## Isolated committed-path validation

Run the entire guarded path only against a disposable PostgreSQL project with:

```sh
make synthetic-cleanup-test-isolated
```

The harness creates one isolated smoke set and an unrelated control customer, produces and restores
its own PostgreSQL backup, recovers a synthetic secret-free credential archive, verifies drift refusal,
runs competing execution attempts, verifies exactly one commit, refuses replay, reconciles the
result and confirms the control customer remains. It mounts no real Google credential volume and
removes only its randomly named project and volume on exit.

Do not run `DELETE`, `TRUNCATE`, database resets, global Docker volume pruning,
`docker compose down --volumes` for the normal WGASuite project, or credential-volume removal as a
substitute for this workflow.
