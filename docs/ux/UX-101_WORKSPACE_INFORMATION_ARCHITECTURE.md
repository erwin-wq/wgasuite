# UX-101: Workspace redesign audit and information architecture

Status: **approved information architecture**

Audit date: 2026-11-14

Repository baseline: `acf81b14fcca911cc96239620ac91c150d9669f3`

This document audits the current React interface and proposes a task-oriented information
architecture. The operator approved the navigation, tenant-context, privacy, visual, and first-PR
boundaries on 2026-11-14. This document does not authorize implementation, change product
capabilities, or replace backend authorization.

## Executive recommendation

Replace the single, state-switched Google Workspace screen with a route-aware application shell and
dedicated pages for Users, Groups, Organizational Units, Gmail Delegations, and Connection. Keep
the selected customer and organization in one header-level tenant selector. Use page headers and
contextual actions for the current task instead of repeating customer, organization, connector,
and navigation controls inside every panel.

The default visual signature should combine the existing directions rather than treat them as
unrelated styles:

- **Navy & Teal**: navigation chrome and primary actions.
- **Cobalt & Ice**: page background, selection, and informational emphasis.
- **Graphite & Copper**: typography and borders, with copper reserved for sparse supporting detail.

The three theme families can still become selectable in UX-104. Semantic success, warning, error,
and destructive colors must not change meaning between themes.

## Evidence and method

The audit reviewed:

- `frontend/src/App.tsx` (2,286 lines), including authentication, role-derived UI gates, tenant
  selection, global feedback, and all top-level screen composition;
- `frontend/src/app.css` (4,663 lines), including current tokens, layouts, component-specific rules,
  and responsive breakpoints;
- every component and test under `frontend/src/features/`;
- the frontend API client and corresponding backend authorization dependencies;
- the capability boundaries in `README.md` and `docs/DEVELOPMENT_RULES.md`;
- UX-101 and the parent UX-EPIC in Asana.

A read-only rendered inspection used the existing local stack and installed Chrome through a
temporary Playwright-Core harness outside the repository. The Browser plugin was not available.
At 1440x1000 and 390x844 there was no document-level horizontal overflow and no browser console
warning or error. The inspection opened Dashboard, Google Workspace, Groups, and Organizational
Units without submitting any form or opening a mutation confirmation. Screenshots were kept
outside the repository because the running UI contains private tenant labels.

The current frontend test suite also passed: 16 files and 109 tests.

## Current experience audit

### Navigation and routing

`AppNavigation.tsx` offers Dashboard, Customer Context, Organizations, Google Workspace, and a
role-gated Platform Admin item. Assessment Workspace and Reports are development-only entries when
`VITE_ENABLE_DEMO_FEATURES=true`.

There are no URL-backed application routes. `App.tsx` stores an `ActiveSection` union in component
state and changes visibility with CSS. Consequences:

- browser back/forward and deep links cannot represent the current task;
- reload always returns to Dashboard;
- a user must traverse the same composite screen to reach a specific Workspace tool;
- top-level state, domain state, and screen composition are concentrated in one component.

Frontend visibility is not the security boundary. The backend already applies platform,
customer-read, customer-write, customer-admin, and connector-operation dependencies. Any new
router must preserve those backend checks and independently handle unauthorized direct URLs.

### Information-density and duplication findings

1. **Tenant context is repeated.** On desktop the active customer or organization appears in the
   sidebar context block, top bar, content header, and connection-status panel.
2. **The Workspace screen has three navigation layers.** Global navigation leads to Workspace
   tool tabs; Users then adds Directory/Exact Lookup tabs. A selected user expands status, OU move,
   direct groups, and mailbox delegates into one long result.
3. **Connection setup competes with daily administration.** Status, setup wizard, DWD instructions,
   and Gmail authorization share the same surface as users, groups, and OUs.
4. **Mobile requires too much pre-content scrolling.** The collapsed shell works and does not
   overflow, but the connection summary and vertically stacked Workspace tool navigation consume
   most of the initial 390x844 viewport before task content appears.
5. **Page hierarchy is visually repetitive.** Top-level headers, panel headings, eyebrow labels,
   nested cards, and multiple status blocks often restate the same task.
6. **Interaction patterns are duplicated.** Mutation features repeatedly implement backdrops,
   identity summaries, confirmation actions, async feedback, and ambiguous-result recovery.
7. **Permission names are too feature-specific.** `canManageConnectorCredentials` is passed as
   permission for user lookup, Gmail mutations, user status, and OU moves. The behavior is guarded,
   but the name obscures the actual capability and makes future composition harder to review.
8. **CSS ownership is broad.** A single stylesheet contains global tokens plus every feature's
   structural and responsive rules. Current tokens are a useful starting point, but component
   boundaries are not reflected in stylesheet ownership. A few rules also reference
   `--color-border`, while the root token is named `--color-line`; this should be resolved during
   design-token work rather than patched incidentally in the IA phase.

### Current capability inventory

| Surface | Current UI and behavior | Status in the new IA |
| --- | --- | --- |
| Dashboard | Active context, connector status, truthful “not assessed” state, next action | Keep as Overview; use only real status and one next action |
| Customer Context | Customer list/selection and creation | Move to role-aware Administration; selection belongs in the global tenant switcher |
| Organizations | Organization list/selection and creation | Move to Administration; selection belongs in the tenant switcher |
| Connection | Metadata, credential upload/reference, DWD instructions, delegated admin, real test | Dedicated Connection page; credentials remain server-side |
| Users | Paginated Directory with filters/sort and exact user-or-alias lookup | Dedicated Users index and User Detail routes |
| User Detail | Identity, aliases, account state, OU, mailbox state | Dedicated detail page with contextual subnavigation |
| User status | Guarded suspend/reactivate with preview, single-use confirmation, reconciliation | Account action on User Detail; keep all safety behavior |
| User OU move | Guarded single-user move with preview, confirmation, reconciliation | OU action on User Detail; keep all protections |
| Direct groups for user | Read-only verified memberships and link to group | “Groups” section on User Detail; link to Group Detail |
| Gmail Delegations | Read delegates and guarded add/remove for an exact mailbox owner | Dedicated search-first Delegations page plus User Detail link |
| Groups | Customer-scoped search, details, direct members, guarded add/remove | Dedicated Groups index and Group Detail routes |
| Organizational Units | Read-only hierarchy/details; guarded child creation and description editing | Dedicated split-view OUs page |
| Platform Admin | Role-gated read-only support overview | Keep separate and conditional |
| Assessments/reports/mock scans | Local development foundations, hidden in production by default | Exclude from Workspace IA; label Demo if deliberately exposed |

Implemented UI is not the same as independently verified live behavior. The new interface must
continue to describe live, mocked, and unavailable states using backend evidence and the parity
catalog; visual polish must never promote a mocked capability to live.

### Production component map

| Owner/component | Current responsibility | Recommended boundary |
| --- | --- | --- |
| `App` | Session, tenant state, all top-level data and screen composition | Bootstrap providers and route outlet only |
| `AppNavigation` | State-based primary navigation and Platform Admin visibility | Render a typed, role-filtered route registry |
| `DashboardOverview` | Current context, connector state, next step | Overview page body |
| `GoogleWorkspaceAdministration` | Connection summary/setup plus three Workspace tool tabs | Remove after dedicated routes reach parity |
| `ConnectionWizard` | Credential, DWD, delegated admin, and connection-test workflow | Connection page body |
| `GmailDelegationAuthorization` | Additional DWD scope instructions | Connection page capability section |
| `UserDirectoryAdministration` | Directory/Exact Lookup tab switch | Replace with Users routes and page action |
| `UserDirectory` | Paginated/filterable live user list | Users index page body |
| `UserLookup` | Exact lookup and composite user result | User Detail loader/composer |
| `UserStatusManagement` | Guarded suspend/reactivate | User Detail account section |
| `UserOrgUnitMove` | Guarded OU move | User Detail organization section |
| `UserGroupMemberships` | Verified direct memberships | User Detail groups section |
| `MailboxDelegates` | Delegate list and guarded add/remove | Delegations owner detail and User Detail link |
| `GroupManagement` | Group search, detail, members, guarded add/remove | Split into Groups index/detail composition |
| `OrganizationalUnits` | Hierarchy, selected OU detail, guarded actions | OUs page body |
| `OrganizationalUnitCreation` | Guarded child creation | Selected-OU contextual dialog |
| `OrganizationalUnitDescription` | Guarded description update | Selected-OU contextual dialog |

### Current role and route-guard behavior

| Actor | Current visible/usable boundary |
| --- | --- |
| `platform_admin` | Platform overview, all customer contexts, connector credentials, reads, and guarded mutations |
| `platform_support` | Platform overview and connector-operation reads; no credential or Workspace mutation administration |
| active `customer_admin` membership | Selected-customer connector credentials and guarded Workspace administration |
| active `customer_user` membership | Selected-customer connector-operation reads where the UI uses `canOperateConnector` |
| active `customer_viewer` membership | Selected-customer read context only; no connector operations or writes |
| no active matching membership | No backend customer access; stale or forged organization IDs must fail |

The frontend currently derives only three broad gates in `App.tsx`:
`canViewPlatformAdmin`, `canManageConnectorCredentials`, and `canOperateConnector`. The backend is
more granular and remains authoritative. The IA migration should add named presentation
capabilities without duplicating backend policy. It should also correct visibility inconsistencies:
for example, customer creation is rendered based on form validity even though the API is
platform-admin-only, while Users is gated with the credential-management flag and Groups/OUs use
the broader connector-operation flag.

### Explicitly future or unavailable

Do not render these as enabled navigation or actions until their backend capability exists:

- user creation/deletion, deleted-user recovery, alias editing, and bulk user operations;
- group creation/deletion, role changes, external or nested membership mutations, and bulk changes;
- Gmail message access or broader Gmail settings;
- OU rename, reparent, deletion, device movement, and bulk OU operations;
- license, ChromeOS/device, Drive, Calendar, or broad security administration;
- production SSO/account recovery and evidence-based security assessment.

## Approved sitemap

```text
WGASuite
├── Overview                                      /overview
├── Directory
│   ├── Users                                     /directory/users
│   │   └── Exact lookup/detail                   /directory/users/lookup
│   ├── Groups                                    /directory/groups
│   │   └── Selected group                        route-local tenant-scoped state
│   └── Organizational Units                      /directory/org-units
├── Gmail
│   └── Delegations                               /gmail/delegations
├── Workspace settings
│   └── Connections                               /settings/connections
├── Administration                               role-aware
│   ├── Customers                                 /administration/customers
│   └── Organizations                             /administration/organizations
└── Platform Admin                                platform roles only
    └── Support overview                          /platform
```

Route identifiers are navigation references, never authorization. The approved first routing
phase uses screen-level routes only. Primary email addresses, aliases, Google entity identifiers,
credential references, access tokens, confirmation tokens, and other sensitive values must not
appear in URLs, analytics, breadcrumbs, document titles, or route-error messages. Selected users,
groups, OUs, and mailbox owners remain ephemeral tenant-scoped state. If a future requirement adds
entity deep links, it must first introduce an application-owned opaque reference, server-side
tenant reauthorization, expiry/revocation behavior, and privacy review.

The old `/` entry should redirect to `/overview`. During migration, old state-based navigation can
adapt to the new route registry until each domain page is extracted.

### Concrete route registry

| Route | Sidebar/breadcrumb label | Context | Presentation gate | First-PR content |
| --- | --- | --- | --- | --- |
| `/login` | Sign in | Global | Anonymous only; authenticated users redirect to Overview | Existing development login |
| `/overview` | Overview | Active Workspace optional | Authenticated | Existing truthful dashboard |
| `/directory/users` | Directory / Users | Active Workspace required | Existing user-directory UI capability | Existing `UserDirectory` |
| `/directory/users/lookup` | Directory / Exact user lookup | Active Workspace required | Existing user-lookup UI capability | Existing `UserLookup`; lookup value never enters URL |
| `/directory/groups` | Directory / Groups | Active Workspace required | Connector-operation access | Existing `GroupManagement` |
| `/directory/org-units` | Directory / Organizational Units | Active Workspace required | Connector-operation access | Existing `OrganizationalUnits` |
| `/gmail/delegations` | Gmail / Delegations | Active Workspace required | Existing user-lookup/delegation UI capability | Search-first owner selection using existing components |
| `/settings/connections` | Workspace settings / Connections | Active Workspace required | Read status for permitted users; configuration actions remain customer-admin-only | Existing status, `ConnectionWizard`, and DWD guidance |
| `/administration/customers` | Administration / Customers | Global/customer context | Role-aware read; creation remains platform-admin-only | Existing customer panel with corrected action visibility |
| `/administration/organizations` | Administration / Organizations | Active customer | Customer read/write rules | Existing organization panel |
| `/platform` | Platform Admin | Global | `platform_admin` or `platform_support` for current read-only overview | Existing Platform Admin overview |
| `*` | Not found | Global | Authenticated or anonymous | Safe 404 with no tenant/entity disclosure |

Every protected route must distinguish authentication failure, forbidden access, missing tenant,
and not found without leaking whether an inaccessible customer or Google entity exists. Direct
navigation, reload, and back/forward must run the same route and tenant checks as sidebar
navigation. Platform Admin remains a separate protected destination, not a subsection inherited
from customer Administration.

## Navigation hierarchy and interaction rules

### Sidebar

- Keep primary destinations task-oriented: Overview, Users, Groups, Organizational Units,
  Delegations, Connection.
- Group labels visually as Directory, Gmail, and Workspace settings, but do not make group labels
  additional click targets.
- Put Customers and Organizations under Administration for roles that can manage them. The common
  tenant-selection action belongs in the header switcher, not in two primary navigation entries.
- Show Platform Admin only to platform roles, as today.
- Do not show future modules as disabled menu items; use roadmap documentation instead.
- Collapse to icons on medium screens and an accessible drawer on mobile. Preserve visible labels
  in the expanded state and tooltips in the collapsed state.

### Header and tenant selector

The header owns global context once:

- customer and organization selector, presented as one Workspace switcher;
- compact connector state linked to Connection;
- breadcrumb trail derived from the route registry;
- profile, role, theme, density, and logout menu.

Switching tenant must cancel in-flight requests, clear selected Google entities and mutation
previews, then reload only data scoped to the new organization. The selector must show only
customers and organizations returned for the authenticated actor. A URL or stale client state must
never make an unauthorized tenant selectable.

### Page header and contextual actions

Each page has one title, one short evidence-based description, and at most one primary action.
Secondary actions belong in a compact overflow menu or the relevant detail panel.

- Users: primary action “Exact user lookup”.
- Groups: no write action until a group is selected; membership actions remain on Group Detail.
- Organizational Units: “Create child OU” appears only for an eligible selected parent.
- Delegations: search or select the mailbox owner before showing delegate actions.
- Connection: “Test connection” is contextual and never runs on page load.

Mutation previews remain explicit modal dialogs. A shared dialog shell may standardize focus,
identity presentation, destructive styling, busy state, and recovery messaging, but each domain
service retains its existing confirmation token, stale-state validation, audit, no-retry, and
reconciliation contract.

## Workspace shell wireframe

```text
┌──────────────────────┬──────────────────────────────────────────────────────────────┐
│ WGASuite        «    │ [ Acme Workspace ▾ ]  Directory / Users   ● Connected  [Me] │
│                      ├──────────────────────────────────────────────────────────────┤
│ Overview             │ User directory                         [Exact user lookup]  │
│                      │ Find and inspect users in the verified tenant.              │
│ DIRECTORY            ├──────────────────────────────────────────────────────────────┤
│  Users               │ [ Search users…       ] [Status ▾] [Admin ▾] [OU ▾] [Clear]│
│  Groups              ├──────────────────────────────────────────────────────────────┤
│  Organizational Units│ Name        Primary email     OU       State       Action    │
│                      │ User A      user…             /        Active      Open      │
│ GMAIL                │ User B      user…             /QA      Suspended   Open      │
│  Delegations         │ …                                                            │
│                      ├──────────────────────────────────────────────────────────────┤
│ SETTINGS             │ Page 1                                      25 per page ▾   │
│  Connection          │                                                              │
│                      │                                                              │
│ ADMINISTRATION       │                                                              │
│  Customers           │                                                              │
│  Organizations       │                                                              │
│  Platform Admin*     │                                                              │
└──────────────────────┴──────────────────────────────────────────────────────────────┘
* conditional by role
```

On mobile, the sidebar becomes a drawer, the tenant selector stays in the header, breadcrumbs
collapse to the current parent and page, filters open in a sheet, and tables use their own
horizontal scroll container or a deliberate row-card representation. Global overflow hiding is
not acceptable.

## Component reuse and extraction recommendations

### Reuse largely as domain content

- `UserDirectory`, `UserLookup`, `GroupManagement`, and `OrganizationalUnits` already isolate
  substantial domain behavior and stale-response handling.
- `ConnectionWizard` remains the setup flow inside the dedicated Connection page.
- `UserStatusManagement`, `UserOrgUnitMove`, `MailboxDelegates`,
  `UserGroupMemberships`, `OrganizationalUnitCreation`, and
  `OrganizationalUnitDescription` remain behavior owners while their layout is composed by pages.
- Existing tests should move with components and remain the regression baseline.

### Extract before broad visual restyling

- `AppShell`: sidebar, mobile drawer, header, content outlet, and global feedback region.
- `RouteDefinition`: path, label, icon, breadcrumb, required UI capability, and demo status.
- `WorkspaceSwitcher`: accessible customer/organization selection and tenant-change reset contract.
- `PageHeader` and `ContextActionBar`: one title/description/action hierarchy.
- `PermissionBoundary`: presentation-only capability checks with explicit names such as
  `canReadDirectory`, `canOperateConnector`, and `canAdministerWorkspace`; backend enforcement
  remains mandatory.
- `MutationDialog`: focus trap, close rules, identity list, confirmation actions, and live region;
  no token persistence and no generic retry button for writes.
- `AsyncState`: shared loading, empty, warning, error, and success presentation.
- `DataTable`, `FilterBar`, and `Pagination`: accessible primitives introduced by UX-112, not a
  one-off rewrite inside every page.

### Decompose the current application owner

Move authentication/session state, tenant state, and domain page state out of `App.tsx` in
separate, reviewable steps. Do not create one global store containing Google results or mutation
confirmations. Live Directory data should remain ephemeral and organization-scoped.

## Migration map

| Current surface | Transitional destination | Final destination | Removal condition |
| --- | --- | --- | --- |
| `ActiveSection` buttons | URL adapters for existing sections | Typed route registry | Back/forward, reload, direct-route guard tests pass |
| Sidebar and repeated context blocks | New AppShell with old content outlet | Sidebar + one Workspace switcher | Role and tenant-switch regression tests pass |
| Google Workspace composite | Route links initially rendering existing children | Dedicated Workspace pages | Every current empty/error/loading/mutation state has parity |
| Users/Exact Lookup inner tabs | Two routes or Users index + lookup action | Users and User Detail | Selected-user flows and stale response tests pass |
| Group navigation request ID | Navigate with immutable group reference | Group Detail route | Cross-user/group navigation and tenant reset tests pass |
| Connection accordion | Existing wizard on its own route | Connection page | Setup, replacement, DWD, and test flows pass |
| User result's stacked tools | Existing components in sections | User Detail contextual sections | Suspend, OU move, groups, and delegates retain safety tests |
| Global `app.css` | Keep during shell extraction | Token, shell, primitive, and feature styles | Visual regression and responsive coverage exist |

Nothing should be deleted solely because a new route exists. Remove an old panel only after its
replacement covers authorization, loading, empty, error, stale-state, confirmation,
reconciliation, audit-safe feedback, keyboard, desktop, and mobile behavior.

## Phased implementation roadmap

### Phase 0 — UX-101 approval

- Completed on 2026-11-14: terminology, sitemap, role visibility, route privacy, mobile behavior,
  Administration placement, visual direction, and the first implementation boundary were approved.
- Publication through the protected documentation PR closes UX-101; implementation proceeds under
  the linked UX-102, UX-103, and UX-106 tasks.

### Phase 1A — visual and primitive foundations

- [UX-102 — Hybrid visual identity and design tokens](https://app.asana.com/1/1198172217694356/task/1220045285996844): define the semantic Navy/Teal, Cobalt/Ice, and Graphite/Copper token system before page-level styling spreads.
- [UX-103 — Reusable UI components](https://app.asana.com/1/1198172217694356/task/1220045269072398): provide accessible primitives needed by the shell without changing domain behavior.

These may be separate PRs or a tightly ordered token-then-primitives series. They must not delay
security fixes or absorb the domain-page redesign.

### Phase 1B — first implementation PR

- [UX-106 — AppShell, sidebar, header, and tenant switcher](https://app.asana.com/1/1198172217694356/task/1220045286314897): introduce the typed route registry, URL-backed navigation, breadcrumbs, collapsible desktop sidebar, mobile drawer, global header, and single Workspace switcher.
- Embed existing domain components in the approved routes without redesigning their workflows.
- On tenant switch, abort in-flight requests; invalidate tenant-scoped caches; clear selected users,
  groups, OUs, mailbox owners, pagination tokens, mutation previews, reconciliation state, and
  feedback; then revalidate the destination route against the new tenant.
- Cover direct links, reload, back/forward, login redirects, 403/404 handling, role visibility,
  mobile focus management, and tenant-change stale-response rejection.

### Phase 2 — task pages (UX-107 through UX-112)

- Recompose Dashboard from truthful existing data.
- Extract Users/User Detail, Groups/Group Detail, Delegations, Connection, and tenant administration.
- Move OUs directly to the Directory destination using the existing split hierarchy/detail model.
- Adopt shared tables, forms, dialogs, and async-state components incrementally.

### Phase 3 — hardening (UX-113 through UX-115)

- Validate 1440px, laptop, tablet, 390px mobile, keyboard, screen reader, and contrast behavior.
- Add visual regression baselines with synthetic data only.
- Test every role, tenant switch, stale response, and mutation confirmation path.
- Remove transitional state navigation only after parity evidence exists.

### Later/optional

- Full dark variants (UX-116).
- Global search and keyboard command menu (UX-117), only after searchable capabilities and privacy
  behavior are explicitly defined.

## Approved first UI implementation PR boundary

**Proposed PR:** `feat(frontend): add route-aware AppShell and workspace navigation`

Keep it smaller than the full redesign:

1. Add a typed route registry and URL-backed navigation for the existing top-level screens.
2. Introduce `AppShell`, `Sidebar`, `AppHeader`, `Breadcrumbs`, and `WorkspaceSwitcher` using current
   styling tokens.
3. Render existing screen content through route adapters; do not redesign domain components yet.
4. Consolidate repeated customer/organization labels into the switcher while keeping connection
   status as a link to the Connections route.
5. Preserve the development-only flag for Assessment/Reports and the role gate for Platform Admin.
6. Add tests for direct URLs, back/forward, reload, unauthorized Platform Admin navigation, mobile
   drawer focus, login redirect, safe 403/404 states, tenant-change resets, stale-response rejection,
   and no PII, Google identifiers, credentials, access tokens, or confirmation tokens in URLs.

Explicitly out of scope for that PR: new Workspace capabilities, backend endpoints, OAuth scopes,
database changes, mutation changes, theme selection, data-table redesign, or removal of current
domain components.

## Recorded review decisions

1. Overview is the first destination; Users, Groups, Organizational Units, Delegations, and
   Connections are dedicated task routes.
2. Customers, Organizations, and administrative configuration belong under role-aware
   Administration. Platform Admin remains separate and conditionally protected.
3. The global header owns active customer/organization selection. Individual pages repeat context
   only when operationally necessary to prevent an unsafe action.
4. Typed URL routing and route-derived breadcrumbs are approved, with no emails, Google entity
   identifiers, credentials, tokens, or other sensitive values in URLs.
5. Tenant switches abort stale work, clear tenant-scoped state, and reauthorize the route.
6. Navy/Teal is the default identity, Cobalt/Ice supplies clean surfaces, and Graphite/Copper is a
   restrained accent language.
7. Mock assessments, reports, and incomplete features remain outside production navigation.
8. Existing backend authorization, tenant isolation, audit, preview, confirmation, no-retry, and
   reconciliation contracts remain unchanged.
9. The first implementation PR is limited to routing and AppShell composition around existing
   domain components.
