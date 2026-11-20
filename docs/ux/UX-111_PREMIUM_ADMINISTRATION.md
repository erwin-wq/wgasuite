# UX-111: Premium connections and administration

UX-111 applies the shared WGASuite design system to Connections, Customers, Organizations, and
Platform Administration. It changes presentation and interaction structure only. Existing API
contracts, role checks, customer scoping, connector behavior, and mutation safeguards remain the
source of truth.

## Migration map

| Route | Previous presentation | UX-111 presentation | Authoritative context and access |
| --- | --- | --- | --- |
| `/settings/connections` | Connector wizard and authorization guidance dominated every state | Verified connector summary first; setup remains prominent only when genuinely required; advanced configuration and authorization guidance use disclosures | Active organization from AppShell; existing connector read/manage permissions |
| `/administration/customers` | Inline creation form, duplicate customer selector, and bespoke list | Shared DataTable with relationship count and contextual row action; creation uses an accessible modal | Global customer selector; platform administrators only |
| `/administration/organizations` | Inline creation form and duplicate organization selector | Selected-customer notice, shared DataTable, contextual row action, and permission-aware creation modal | Global customer and organization selectors; existing customer membership rules |
| `/platform` | Bespoke hero, KPI cards, and HTML tables | Compact real-data summary plus shared DataTables for customers, connectors, optional demo scans, and audit events | Platform admin/support route authorization and existing backend endpoint |

No search or filtering was added because the current APIs do not expose server-side search for
these administration lists. No health score, synchronization timestamp, quota, permission claim,
or other unsupported connector metric is inferred.

## Connection states

- Connected and failed configurations show persisted connector identity, primary domain,
  delegated administrator, credential presence, and the persisted test timestamp.
- A failed connection retains the sanitized persisted error and recovery entry points.
- A successful empty configuration response opens the existing guided setup.
- An API error is labeled unavailable and is never interpreted as an unconfigured connector.
- Initial loading uses a skeleton. A background connection test preserves an already open setup
  flow and its feedback.
- Credential values and service-account private material are never rendered.

## Authorization and tenant isolation

The AppShell customer and organization selectors remain authoritative; the redesigned pages do
not introduce parallel selectors. Existing context-change handlers invalidate tenant-scoped
state, advance the tenant epoch, and reject stale connector responses. Route authorization still
runs for direct URLs, including `/platform`, before the protected view or platform overview request
is exposed. Creation controls reflect existing role checks and do not broaden backend privileges.

## Shared component and responsive behavior

UX-111 reuses `Button`, `Badge`, `Alert`, `ErrorState`, `Skeleton`, `DataTable`, shared form
controls, and `Modal`. Semantic theme and density tokens drive spacing, surfaces, borders, focus,
and status presentation across all three themes and both density modes. Wide administration
tables scroll within their labeled table regions instead of forcing page-level horizontal
overflow. Toolbars and summary facts collapse at tablet and mobile breakpoints.

## Explicit non-goals

- No Google Workspace capability, OAuth scope, or Domain-Wide Delegation change.
- No connector credential update or new sensitive metadata.
- No backend authorization, audit, confirmation, no-retry, or reconciliation change.
- No assessment/reporting redesign and no change to DIR-003.4 acceptance state.
