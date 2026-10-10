# Synthetic smoke-test data inventory and cleanup plan

The development API smoke test creates customers, organizations, connector metadata, assessments,
assets, findings and mock scan runs. Those records exercise persistence and referential behavior;
the smoke test does not delete them. A name that looks synthetic is not, by itself, permission to
delete data.

## Read-only inventory

With the development stack running, execute:

```sh
docker compose exec -T backend python -m app.maintenance.synthetic_record_inventory
```

The command uses strict fingerprints written by `scripts/dev/smoke_api.sh`, changes the PostgreSQL
transaction to read-only and reports aggregate candidate counts only. It does not output record
names, UUIDs, contact details, domains, delegated administrators, credential references or Google
user data. Its association summary covers connector configurations, credential-bearing connector
configurations, connector accounts, assessments, assets, findings, scan runs, memberships and
audit events.

`safe_to_delete_now` is always `false`. `cleanup_eligibility` means only that a group may be
considered during a later private review. Credential-bearing connectors or mixed customer data are
explicit manual-review blockers.

## Deletion impact to review

- Organization deletion cascades to assessments, assets, connector accounts and connector
  configurations.
- Assessment deletion cascades to findings, their DREAD scores and scan runs.
- Customer deletion removes memberships, detaches organizations and detaches the customer reference
  from audit events.
- Credential-bearing connector rows require coordinated credential-store handling. Database
  deletion alone does not safely reconcile stored credential files.

## Future cleanup procedure (separate approval required)

1. Run the aggregate inventory and privately inspect each candidate in the database and UI. Confirm
   its exact smoke-script provenance and verify that no actual customer, connector or audit record
   is included.
2. Back up PostgreSQL and the encrypted Google credential volume together, then verify the backup
   can be restored in an isolated environment.
3. Prepare a transaction-scoped dry-run that selects only explicitly approved UUIDs and reports
   every dependent row. Roll it back and compare counts with the inventory.
4. Obtain explicit approval for the exact UUID allowlist and deletion impact. Never approve a
   prefix, wildcard, customer name or age-based bulk rule.
5. Execute the reviewed transaction against only that allowlist. Coordinate any approved credential
   file removal separately and recoverably.
6. Verify foreign-key integrity, tenant scoping, connector status, audit history expectations and
   application behavior. Retain the backup until verification is complete.

This document is a plan, not authorization. Do not run `DELETE`, `TRUNCATE`, database resets,
`docker compose down --volumes` or credential-volume removal as part of the inventory.
