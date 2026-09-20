# Roadmap

WGASuite is in early development. This roadmap describes direction, not delivery dates or
commitments. The README is authoritative for current capabilities.

## Foundations available today

- React/TypeScript frontend and FastAPI/PostgreSQL backend
- Alembic migration chain
- development authentication and role foundations
- customers, organizations and customer memberships
- backend customer data scoping
- assessments, assets, findings and DREAD scoring
- report view and browser/PDF printing flow
- selected support-access audit events
- read-only Platform Admin overview
- connector configuration metadata
- Google Workspace check catalog and mock scans

## v0.2.0 — Directory integration foundation

The objective for `v0.2.0` is to prove WGASuite's production-oriented Google integration
architecture with a real, tenant-scoped Directory API workflow. This is a focused direction, not a
promise of broad Google Workspace administration coverage. The architecture decision and product
principles are documented in [PRODUCT_STRATEGY.md](PRODUCT_STRATEGY.md).

### 1. Production identity foundation

- define and implement the production OIDC direction;
- add revocable server-side session behavior;
- preserve a clear boundary between local development authentication and deployed identity.

### 2. Secure Google connector credentials

- store credentials through an encrypted or external secret-provider boundary rather than ordinary
  connector metadata;
- define the service-account and Domain-Wide Delegation model where required;
- support credential rotation and deletion without returning secrets through the API or UI;
- preserve a path to keyless deployment where the hosting environment supports it.

### 3. Real connector validation

- validate credentials and the delegated administrator identity;
- verify the intended tenant/domain, required scopes and API access;
- return structured, actionable failure states without exposing sensitive values.

### 4. Direct Directory API foundation

- introduce a tenant-bound abstraction for official Admin SDK Directory API access;
- define pagination, quota handling, error classification and test boundaries;
- keep read-only and mutation scopes separable.

### 5. User directory inventory

- list and search Workspace users;
- show a selected user's relevant directory details;
- expose freshness, loading and structured error states clearly.

### 6. Group membership context

- retrieve and show relevant group memberships for a selected user;
- document API limitations such as nested membership behavior;
- avoid unbounded per-user fan-out.

### 7. Audited, guarded suspend and restore

This mutation follows the proven read workflow; it is not a prerequisite for initial connector
validation or inventory.

- authorize and revalidate the operation in the correct customer/organization context;
- show an explicit preview and require confirmation;
- behave idempotently where possible;
- record structured success and failure audit events;
- return a structured operation result or error.

### 8. Evidence-based Workspace checks

- replace a small, selected subset of mock checks with evidence retrieved from Google APIs;
- record evidence source, freshness and check version;
- keep unsupported checks clearly marked as mock or planned rather than implying broad coverage.

## Later themes

The following themes remain directional and are not release commitments:

- frontend automated tests and broader production hardening;
- bulk operations and CSV planning;
- durable background jobs with retries, progress, cancellation and per-target results;
- approval and separation-of-duty workflows;
- ChromeOS, mobile and endpoint inventory and administration;
- Gmail, Drive, organizational-unit, admin-role and license administration;
- expanded security posture, audit-event and remediation workflows;
- just-in-time administration;
- notifications, automation and scheduling;
- broader delegated MSP workflows;
- production deployment, backup, monitoring and recovery guidance.

WGASuite is an independent open-source project and is not affiliated with or endorsed by Google.
