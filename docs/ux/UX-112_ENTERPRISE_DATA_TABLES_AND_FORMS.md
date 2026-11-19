# UX-112: Enterprise data tables and administration forms

Status: **implemented foundation and selective adoption**

Baseline: UX-109 at `7d7896efd23fbdc90cf2d4cb48d67ce7c577839e`

UX-112 standardizes the presentation and accessibility of bounded administration data without
changing WGASuite authorization, tenant scoping, Google API contracts, mutation confirmations,
auditing, retry behavior, or reconciliation.

## Pre-change inventory and migration scope

The Users directory, Groups overview, group-member list, and user-detail membership list each
owned separate table markup and near-duplicate borders, header, row-density, overflow, and action
styles. Users already supported server-side filters, three server-supported sort fields, opaque
page tokens, and bounded page sizes. Groups and membership lists supported server-provided opaque
pagination only; they did not support sorting. None of these data sources provides a trustworthy
total count.

Forms mixed native labels and inputs with the UX-103 `Input` and `Select` primitives. Field errors
were associated correctly, but help text disappeared when an error was present, required fields
had no consistent visible indicator, and there was no shared textarea.

The accepted migration scope was therefore:

1. Add a typed, presentational `DataTable` and controlled `DataTablePagination` foundation.
2. Migrate the Users directory, Groups overview, direct group-member list, and user-detail direct
   membership list without moving their request or business state into the shared component.
3. Normalize Users filters and OU create/description fields with shared form controls.
4. Keep all protected dialogs, confirmation tokens, mutation execution, and reconciliation in
   their existing domain components.

## Shared table contract

`frontend/src/components/ui/DataTable.tsx` provides:

- generic typed column definitions and stable caller-provided row keys;
- native table, caption, column-header, row, and cell semantics;
- optional controlled sorting with `aria-sort`; callers retain server/client data ownership;
- reusable loading, empty, recoverable error, and pagination presentations;
- an explicitly labeled keyboard-scrollable overflow region;
- optional sticky final action columns;
- UX-102 semantic tokens and UX-105 density values for all themes and densities.

The component never sorts, filters, paginates, counts, or fetches records by itself. This prevents
the loaded page from being presented as a complete dataset and prevents client operations from
being mistaken for server-wide operations. Pagination appears only when a caller supplies a real
data-source continuation flow.

## Shared form contract

`FormControls.tsx` now includes `Textarea`, a consistent required indicator, an optional label,
and simultaneous hint/error associations. Native `required`, `disabled`, input type, length, and
browser keyboard behavior remain authoritative. Errors use an alert relationship, while both help
and error IDs are retained in `aria-describedby`.

## Adopted screens

| Screen | Shared behavior adopted | Domain behavior retained |
| --- | --- | --- |
| Users directory | Table, sortable headers, sticky actions, filters, states, pagination | Server filters/sort, opaque tokens, cancellation, stale-response rejection |
| Groups overview | Table, states, responsive containment, pagination | Google search semantics and opaque tokens |
| Group detail | Direct-members table, roles/statuses, states, pagination | Protected add/remove preview, confirmation, no-retry, reconciliation |
| User detail | Direct-membership table, roles/statuses, states, pagination | Customer-bound verification, omissions and continuation semantics |
| OU creation/description | Shared labeled input/textarea presentation | Existing dialog, preview, single-use confirmation, execution and reconciliation |

## Deliberately deferred migrations

- Platform Customers and Organizations tables remain in `App.tsx`. They combine role-specific
  CRUD forms, membership administration, and platform controls in one legacy surface; migrating
  them safely requires a focused administration-route extraction rather than widening UX-112.
- Assessment/report tables remain mock or assessment-domain surfaces and are outside the Workspace
  administration goal.
- The Organizational Unit hierarchy remains a tree, not a table. Converting it would weaken its
  parent/child semantics.
- Gmail delegation and user-status mutation dialogs retain their established protected workflow.
- Bulk selection is not implemented because no accepted backend operation requires it.

## Accessibility and truthfulness rules

- Sort buttons are native buttons inside scoped column headers and expose current `aria-sort`.
- Row actions remain keyboard-operable native buttons with visible focus.
- Long emails and OU paths wrap inside cells; the table viewport scrolls horizontally without
  causing page-level overflow.
- Loading and error states announce through status/alert semantics.
- Theme and density behavior comes only from semantic tokens; component code does not branch on a
  theme or density name.
- Page labels explicitly avoid total-result claims when Google does not provide a total.
