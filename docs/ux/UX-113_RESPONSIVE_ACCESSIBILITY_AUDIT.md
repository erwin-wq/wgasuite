# UX-113 Responsive and Accessibility Audit

## Scope and method

UX-113 is an application-wide hardening pass, not a visual redesign. The audit covered the production routes for login, Overview, Users, exact user lookup/detail, Groups, Organizational Units, Gmail Delegations, Connections, Customers, Organizations, and Platform Administration, together with the shared AppShell and UI primitives.

Rendered checks used Chrome through Playwright because the browser plugin was unavailable. All Workspace responses were fictional, locally intercepted fixtures; the harness rejected mutation requests. Temporary screenshots and machine-readable results were written under `/tmp` and were not added to the repository. No Google Workspace, credential, database, or migration state was changed.

Automated checks used axe-core 4.10.3 with WCAG 2 A/AA, WCAG 2.1 AA, and WCAG 2.2 AA tags. Manual keyboard checks covered navigation drawers, menus, tenant controls, dialogs, tree navigation, focus order, focus restoration, and visible focus. Automated output is supporting evidence, not a claim of complete WCAG conformance.

## Coverage matrix

| Area | Desktop | Mobile | Keyboard and semantics | States reviewed |
| --- | --- | --- | --- | --- |
| Login | 1440 × 1000 | 390 × 844 | Labels, alert, tab order, focus visibility | Default and validation surface |
| AppShell and Overview | 1920, 1440, 1280, 1024 | 768, 390, 320 | Drawer containment, Escape, menus, workspace switcher, landmarks | Three themes, both densities, reduced motion, 200% text |
| Users and exact lookup/detail | 1440 × 1000 | 390 × 844 | Form labels, tabs, data table region, action order | Connected directory fixture and empty detail start |
| Groups | 1440 × 1000 | 390 × 844 | Search form, results table, interactive names | Connected group fixture |
| Organizational Units | 1440 × 1000 | 390 × 844 | Tree ownership, arrow keys, selection, action dialogs | Root, ordinary child, protected child |
| Gmail Delegations | 1440 × 1000 | 390 × 844 | Lookup form and workflow region | Connected, no mailbox selected |
| Connections | 1440 × 1000 | 390 × 844 | Disclosures and action order | Connected fixture |
| Customer, organization, platform administration | 1440 × 1000 | 390 × 844 | Tables, modal focus and restoration, route authorization | Platform administrator fixture |

The shell was additionally checked at 1920 × 1080, 1280 × 800, 1024 × 768, 768 × 1024, and 320 × 640. A 390 × 844 run with the root font size doubled exercised 200% text resizing. The 320 CSS-pixel viewport is also the reflow equivalent of a 1280-pixel viewport at 400% zoom. This is a reflow check, not a substitute for assistive-technology zoom testing.

Theme and density coverage was rotated across the full route matrix so that Navy & Teal, Cobalt & Ice, and Graphite & Copper were each exercised with Comfortable and Compact modes. Narrow-screen Compact mode retains the mobile usability rules rather than shrinking controls below the shared minimums.

## Findings and remediation

| ID | Severity | WCAG relationship | Reproduction | Resolution |
| --- | --- | --- | --- | --- |
| UX-113-01 | Critical | 1.3.1, 4.1.2 | Load Organizational Units and inspect the hierarchy with axe. The `tree` owned generic rows and unrelated buttons instead of direct `treeitem` children. | Rows now own the `treeitem` role, level, selection, expansion, focus, and keyboard behavior. Expand controls remain pointer-accessible while arrow keys operate the focused tree item. |
| UX-113-02 | High | 2.1.1, 2.4.3 | Open mobile navigation and press Shift+Tab from Close, or dismiss it with the backdrop. Focus could leave the drawer or was not restored. | The drawer now contains forward/reverse Tab movement and restores focus for Escape, Close, backdrop, and route selection. |
| UX-113-03 | Medium | 2.4.3 | Open the workspace selector, focus a select, and press Escape or choose an organization. Focus was left on a removed control. | Both close paths restore focus to the disclosure trigger. |
| UX-113-04 | High | 1.4.4, 1.4.10 | At 390 × 844 with 200% text, the “View organizational units” quick action extended the document to 413 pixels. | Mobile header controls reflow onto stable rows and long quick-action labels may wrap at safe character boundaries. No global overflow hiding was added. |

Regression tests cover tree ownership, drawer focus wrapping/restoration, and workspace-switcher restoration. The rendered matrix verifies document width and reruns axe after remediation.

## Shared component assessment

- `Modal` already traps focus, supports Escape, labels the dialog, and restores the opener.
- `Dropdown` and the account/appearance menu already implement menu roles, arrow navigation, Escape, and trigger restoration.
- `DataTable` uses native table semantics, captions, sort state, and a keyboard-focusable horizontal scroll region.
- Form controls retain programmatic labels, descriptions, errors, and disabled states.
- Status and alert components use live-region semantics without relying on color alone.
- Existing reduced-motion rules suppress nonessential transitions and animation.
- Shared button sizing remains at least 24 CSS pixels; mobile layout continues to favor the larger comfortable targets.

## Residual limits

No NVDA, JAWS, VoiceOver, TalkBack, Windows High Contrast, or browser text-only zoom session was available. Consequently, UX-113 records automated semantics, Chrome accessibility behavior, keyboard operation, contrast-token review, and rendered reflow evidence, but does not claim certification or exhaustive WCAG 2.2 AA conformance. Live Google mutation confirmations were not opened because this task forbids Workspace writes; their shared modal primitive and automated component tests were reviewed instead.

Future audits should add at least one Windows screen-reader pass and one mobile screen-reader pass before a formal accessibility conformance statement is considered.
