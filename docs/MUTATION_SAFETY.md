# Google Workspace mutation safety

WGASuite exposes three deliberately narrow Google Workspace mutation families: Gmail mailbox
delegate create/remove, direct Google Group member add/remove, and eligible Directory user
suspend/reactivate. They retain separate API scopes and operation-specific eligibility rules, but
share a small safety kernel in `google_workspace_mutation_safety.py`.

## Safety contract

Every mutation follows the same sequence:

1. Authenticate the actor and authorize customer-administrator access to the organization before
   resolving connector credentials.
2. Resolve canonical Google identities with read-only clients, prove Google customer ownership,
   and validate the operation-specific current state and eligibility rules.
3. Return an impact preview with a random five-minute confirmation secret. Persist only its SHA-256
   digest and bindings to the actor, organization, action and canonical targets.
4. On confirmation, repeat tenant, identity, eligibility and expected-state validation. Atomically
   change the unexpired confirmation from `pending` to `executing` before contacting a write API.
5. Send exactly one operation-scoped Google write with client-library retries disabled. A replay,
   concurrent request or expired confirmation cannot acquire the confirmation again.
6. Record a confirmed success, definitive failure, or unknown outcome. Timeouts, network failures
   and upstream 5xx responses are unknown because Google may have accepted the request. HTTP 429
   and explicit API rejections are definitive for that attempt and are never retried automatically.
7. For an unknown outcome, allow only bounded, operation-specific reads. Reconciliation observes
   current state and never claims causation or resubmits the write.
8. Emit separate preview, mutation and reconciliation audit events. Mutation metadata is checked
   for sensitive keys and JSON-safe values; confirmation secrets, credentials, headers, raw Google
   responses and full profiles are forbidden.

The shared kernel owns confirmation issuance/digests/expiry, atomic consumption, safe status
transitions, ambiguous-error classification, bounded reconciliation timing and mutation-audit
metadata validation. Authorization, connector resolution, Google clients, identity checks,
eligibility and the read/write calls remain in the family services. This keeps the common
invariants testable without creating a generic framework that could widen privileges.

## Before/after matrix

| Control | Gmail delegates before | Groups before | User status before | Standardized result |
| --- | --- | --- | --- | --- |
| Actor and tenant authorization | Customer-admin and organization scoped | Customer-admin and organization scoped | Customer-admin plus customer/connector binding | Preserved; checked before credential-backed clients |
| Canonical targets | Directory owner/delegate identities and customer match | Verified group customer plus canonical internal user | Immutable Directory user and customer match | Preserved in each family; never reduced to email suffix checks |
| Least-privilege clients | Separate Gmail read/write scopes and owner subject | Separate group read/member scopes | Separate user read/write scopes | Preserved; no shared broad-scope client |
| Preview validity | Five-minute actor/tenant/action/identity token | Five-minute actor/tenant/action/identity token | Five-minute actor/customer/org/connector/action/state token | One issuer, digest and expiry policy; stronger user-status bindings retained |
| Replay/concurrency | Atomic pending-to-executing transition | Atomic pending-to-executing transition | Atomic pending-to-executing transition | One shared expiry-aware compare-and-set primitive |
| Stale state | Owner/delegate state re-read | Direct membership re-read | User status and protections re-read | Preserved immediately before confirmation consumption |
| Google write | One call, retries disabled | One call, retries disabled | One minimal `users.update`, retries disabled | Preserved; frontend same-tick in-flight locks add defense in depth |
| Error outcome | Timeout/network/5xx unknown | Timeout/network/5xx unknown | Timeout/network/5xx unknown | One classifier; 429 and explicit rejections remain definitive failures |
| Reconciliation | Bounded `delegates.list` only | Bounded direct `members.list` only | Bounded `users.get` only | One timing window; each read-only implementation remains separate |
| Audit privacy | Sanitized family metadata | Sanitized family metadata | Sanitized family metadata | All mutation metadata passes a shared fail-closed validator |

The refactor intentionally does not change endpoint paths, request/response schemas, confirmation
lifetimes, OAuth scopes, supported actions, role rules, frontend workflows or database schema. No
Alembic migration is required.

## Operation-specific protections

- Gmail rejects owner/delegate self-pairs and ineligible, cross-customer or non-mailbox users. The
  write client impersonates the canonical mailbox owner and can only manage delegates.
- Groups proves group ownership through the verified Google customer, supports direct internal
  users only, adds only `MEMBER`, and protects owners, nested/external/customer-wide and special
  groups.
- User status protects super/delegated admins, the DWD subject, identifiable acting admin, service
  identities and archived/deleted users. Reactivation is limited to verified administrator-driven
  suspensions and writes only the `suspended` property.

Automated regression tests use mocked Google clients. Running the test suite does not authorize or
perform live Google Workspace writes.
