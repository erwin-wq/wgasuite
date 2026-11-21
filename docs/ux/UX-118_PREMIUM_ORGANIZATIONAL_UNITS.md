# UX-118: Premium Organizational Units management

Status: **implemented; Google Workspace capabilities unchanged**

Baseline: UX-111 administration experience at
`00109e61a1d9f2331db72f43e7a44928e2cee232`

UX-118 modernizes `/directory/org-units` without changing Google API contracts,
tenant authorization, confirmation records, audit events, retry behavior, reconciliation, OAuth
scopes or Domain-Wide Delegation.

## Information architecture

The route preserves the Google Directory hierarchy as a semantic tree rather than flattening it
into a table. The desktop layout uses a hierarchy rail beside the selected-unit workspace. Narrow
screens use an explicit Hierarchy/Details switch; selecting a tree item opens its details and Back
to hierarchy restores the tree without losing selection.

The explorer distinguishes the root unit and the protected Workspace Guests subtree, supports
expand/collapse and standard tree keyboard navigation, contains long names and paths, and retains
tenant-switch request cancellation and stale-response rejection. Loading, empty, disconnected,
unauthorized and recoverable error states continue to use the existing sanitized API behavior.

## Factual detail boundary

Selected-unit details show only data returned by the tenant-scoped hierarchy API:

- name, immutable ID, full path, parent and description;
- direct children from the returned node and their authoritative direct count;
- whether the current actor receives read-only or guarded-administration presentation.

The UI explicitly states that effective inherited policy configuration is unknown. It does not
invent applied policies, user totals, timestamps, device totals or indirect descendants.

## Supported and unsupported administration

Existing guarded entry points remain available for child-OU creation and description editing when
the current role and selected unit permit them. Their preview, expiring single-use confirmation,
atomic consumption, stale-state checks, no-retry execution, sanitized audit trail and bounded
read-only reconciliation remain owned by the existing domain components and backend safety kernel.

Single-user OU relocation remains available from User Detail, where an exact user supplies the
required source identity. It is intentionally not duplicated in the hierarchy explorer.

Rename, reparent, delete, bulk operations, device movement and policy administration remain
unsupported. The root description and Workspace Guests subtree protections remain unchanged.

## Accessibility and responsive behavior

- Tree items expose `treeitem`, level, expansion and selection semantics with roving focus.
- Arrow keys, Home and End navigate visible nodes; right/left expand, descend, collapse or return
  to a parent.
- The selected state, root identity and protected identity use text and icon cues in addition to
  color.
- Mobile view controls are native buttons with pressed state and preserve the selected unit.
- Long paths wrap, tree labels truncate with their full value retained in the accessible name, and
  the page does not suppress global overflow to mask defects.
- Existing mutation dialogs retain focus trapping, Escape handling and trigger focus restoration.
- All presentation consumes UX-102 tokens and therefore supports the three UX-104 themes and both
  UX-105 density modes without remounting workflow state.

## Visual QA boundary

Private Image Gen references guided hierarchy, detail and mobile composition; they are not shipped
as product assets. Rendered browser QA uses fictional intercepted customers, organizations,
connectors and Organizational Units. All Google-backed calls are intercepted and non-read-only
requests fail closed, so visual acceptance performs no live Workspace mutation.
