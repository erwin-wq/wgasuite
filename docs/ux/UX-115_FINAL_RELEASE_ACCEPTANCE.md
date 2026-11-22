# UX-115: Premium UX release gate

Verdict: **PASS WITH LIMITATIONS**

Baseline: `63aa77591af4ba1ac6ace6da94384201e6243c70`

Assessment finalized: 2026-11-22

UX-115 evaluates the UX-101 through UX-114 and UX-118 work as one product. It introduces a
reproducible browser release suite and consolidates documentation; it does not redesign a route,
change an API, alter authorization or perform a Google Workspace mutation.

## Acceptance policy and evidence

The committed Playwright suite uses installed Chrome and fictional `.invalid` tenant data. Every
API call is locally intercepted and mutation endpoints fail closed. It covers the three production
viewports (1440x1000, 1280x800 and 390x844), rotates all three themes and both densities across
every route, rejects document overflow and console errors, and verifies that sensitive identities
do not enter URLs or preference storage. Route-specific desktop flows cover authentication,
session expiry, history/reload, account preference isolation, tenant invalidation, role guards,
connector status, alias lookup, Groups, Gmail Delegations and loading/empty/error states.

The suite supplements, rather than replaces, the existing component and domain tests. The UX-113
WCAG 2 A/AA, WCAG 2.1 AA and WCAG 2.2 AA axe review and keyboard inspection remain the detailed
accessibility baseline. Browser automation is evidence of the tested contracts, not a claim of
complete assistive-technology or WCAG conformance.

## Route acceptance matrix

Legend: `PA` platform administrator, `PS` platform support, `CA` active customer administrator,
`CU` active customer user, and `CR` an active customer-readable membership. Backend policy is
authoritative even when a presentation guard hides or redirects a route.

| Route | Supported production capability | States | Authorization and tenant switch | Keyboard/accessibility | Theme, density and responsive evidence | Result |
| --- | --- | --- | --- | --- | --- | --- |
| `/login` | Development login and authenticated redirect | Session loading, validation, API error | Anonymous entry; authenticated users redirect; expired sessions clear the token | Native labelled form, logical tab/submit order, alert semantics | UX-113 desktop/mobile; auth E2E | Accepted |
| `/overview` | Real connector readiness and links to existing tools | Loading, connected, disconnected, unconfigured, error | Authenticated; selected context is global and tenant-scoped requests are invalidated | Landmarks and descriptive task links | All themes/densities at three viewports | Accepted |
| `/directory/users` | Live paginated directory, filters and supported sorting | Loading, empty, recoverable error, content | Tenant operator; switch cancels old results and renders only the new tenant | Labelled filters, table region, pagination and focus-visible controls | All themes/densities at three viewports; state E2E | Accepted |
| `/directory/users/lookup` | Exact primary-email or alias lookup and central user detail | Idle, loading, not found/error, result | Tenant operator; lookup value remains ephemeral and is reset with tenant context | Labelled search, result article and existing user-detail action semantics | All themes/densities at three viewports; alias E2E | Accepted |
| `/directory/groups` | Group search, detail, direct members and existing guarded membership workflow | Loading, empty, error, group/member results | Tenant operator; selected group is route-local and invalidated on switch | Search, data regions, focused detail, modal confirmation contracts | All themes/densities at three viewports; detail E2E | Accepted |
| `/directory/org-units` | Hierarchy, detail and existing guarded OU actions | Loading, empty, error, hierarchy/detail | Tenant operator; hierarchy is tenant-scoped and selection resets | Semantic tree, keyboard navigation, mobile hierarchy/details switch | All themes/densities at three viewports; UX-118/113 evidence | Accepted |
| `/gmail/delegations` | Exact mailbox lookup, delegate list and existing guarded add/remove | Idle, loading, empty, error, result | Tenant operator; owner identity stays out of URL and resets on switch | Search-first flow, labelled data region and modal confirmation contracts | All themes/densities at three viewports; empty-result E2E | Accepted |
| `/settings/connections` | Actual connector status, configuration and authorization guidance | Loading, missing, connected, failed | Customer-readable status; management remains backend and role guarded | Disclosures, labelled status, forms and credential safety guidance | All themes/densities at three viewports; connected E2E | Accepted |
| `/administration/customers` | Customer inventory and platform-admin creation | Loading, empty, error, content | PA only; direct unauthorized navigation cannot expose data | Shared table and accessible creation modal | All themes/densities at three viewports | Accepted |
| `/administration/organizations` | Tenant-scoped organization inventory and authorized creation | Loading, empty, error, content | Existing membership rules; customer switch resets organization selection | Shared table, explicit context and accessible creation modal | All themes/densities at three viewports | Accepted |
| `/platform` | Read-only support overview from actual backend data | Loading, empty, error, content | PA/PS only; denied direct URL safely falls back before the endpoint loads | Shared tables and labelled support regions | All themes/densities at three viewports; role-guard E2E | Accepted |

## Cross-product regression result

- Direct routes, browser back/forward, reload and route-derived breadcrumbs retain the current
  task; `/` and unsafe role transitions use the documented safe fallback.
- Login, logout and session expiry preserve no usable stale authentication token.
- The sidebar, mobile drawer, active-route state and global Workspace selector remain a single
  navigation/context system. Customer and organization identifiers are not encoded into URLs.
- Tenant switching invalidates old Directory data before showing the new tenant. Route-local user,
  group, mailbox and OU selections follow the existing invalidation boundary.
- Theme and density update without remounting workflows, survive reload, are independently stored
  per opaque account hash, and do not persist email/customer/organization identifiers.
- Existing preview, digest-only single-use confirmation, replay prevention, audit, no-retry and
  bounded reconciliation behavior remains domain-owned and covered by backend/frontend regression
  tests. UX-115 executes no mutation path.
- Production navigation contains only implemented administration surfaces. Mock assessments,
  mock scans and report foundations remain behind `VITE_ENABLE_DEMO_FEATURES=true`; they are not
  represented as Workspace security findings or live operational data.

## Documentation consolidation

The directory [index](README.md) identifies the canonical owners for information architecture,
tokens, components, themes, density, responsive/accessibility and motion. UX-102 tokens and UX-103
component APIs are the extension boundary. UX-104 defines the complete theme contract; adding a
theme means supplying every semantic token without changing status meaning, focus visibility,
reduced-motion behavior or density compatibility.

## Local validation record

The final branch state passed:

- 500 backend tests, Ruff, Python compilation, parity validation and whitespace checks (one
  upstream Starlette/httpx deprecation warning);
- 193 frontend component/domain tests, ESLint, TypeScript (including the E2E project) and the
  production Vite build;
- 36 Playwright checks in installed Chrome, with 12 intentional skips where six desktop-only
  behavioral contracts are not repeated in the laptop and mobile projects;
- 30 route/theme/density/viewport combinations with zero axe WCAG 2 A/AA, WCAG 2.1 AA or WCAG
  2.2 AA violations, no document overflow and no browser console errors;
- both complete and production-only npm audits with zero vulnerabilities;
- the 709-capability parity catalog and the isolated API smoke environment through Alembic 0018;
- the running backend, frontend and PostgreSQL services, with PostgreSQL healthy and the live
  schema at `0018_google_orgunit_description`;
- five managed Google credential files unchanged from the prior private checksum snapshot; their
  directory remains owned by UID/GID 10001 with mode 0700.

Fresh visual review covered Navy & Teal at 1440x1000 comfortable density, Cobalt & Ice at 1280x800
compact density and Graphite & Copper at 390x844 compact density. No clipping or layout regression
was observed. The review initially found insufficient contrast in the Overview connection link and
three OU text states. Replacing action/hard-coded colors with the existing semantic link, secondary
text and warning tokens resolved those findings, and the complete automated matrix then passed.
Screenshots and machine-readable visual results remained under `/tmp` and are not repository or PR
artifacts because production browser captures can contain tenant context.

Protected Backend and Frontend CI passed on PR #43 at commit
`55612a95f935046a26792cd85d06257a44915a5d`. A documentation/test-fixture hardening follow-up
requires those checks to pass again on the final pull-request head before merge.

## Release decision and limitations

The gate is **PASS WITH LIMITATIONS** because every mandatory automated, rendered and security
boundary check passed and the identified contrast defects were corrected, while manual validation
with NVDA, JAWS, VoiceOver, TalkBack and Windows High Contrast was not performed. That limitation
prevents a formal accessibility-conformance claim but does not block this release under the
approved acceptance criteria. Protected Backend and Frontend CI must pass on the exact final
pull-request head before merge.

Known limitations do not block this presentation release:

- development login is explicitly not production SSO;
- automated axe and keyboard checks do not replace manual NVDA, JAWS, VoiceOver, TalkBack,
  Windows High Contrast or disabled-user research;
- the browser harness proves product integration against deterministic contracts, while prior
  feature acceptance records and the parity catalog remain the source for live Google verification;
- no UX release test submits a Google Workspace write.
