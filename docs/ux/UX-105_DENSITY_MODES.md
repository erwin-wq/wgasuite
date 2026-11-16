# UX-105: Comfortable and compact density modes

Status: **implemented**

Baseline: UX-104 premium themes at `2c6cf7ad26018908e3a0ab1fc8d2c51c4a93f241`

UX-105 adds two selectable presentation densities without changing routes, authorization, tenant
state, domain workflows, mutation safeguards, auditing or Google Workspace capabilities.

## Modes and token contract

| Stable ID | Purpose |
| --- | --- |
| `comfortable` | Default spacing and control sizing for general use. |
| `compact` | Denser administration layout for long tables, lists and forms. |

The document root owns one `data-density` attribute. Components consume centralized UX-102 tokens
for control heights, page gutters, panel and dialog padding, inline and section gaps, navigation
rows, table cells and data rows. Theme selectors remain independent and never branch on density.
Domain components are not duplicated.

Compact mode reduces vertical whitespace on desktop while retaining readable typography and visible
focus indicators. At viewports up to 600px, compact mode restores practical control, row and
navigation touch heights; mobile usability takes priority over maximum information density.

## Preference behavior

Theme and density share the private, account-isolated UX-104 storage envelope but are independently
selectable. Version 2 records contain only a schema version, opaque account hash, stable theme ID
and stable density ID. Existing version 1 theme-only records migrate by retaining the theme and
defaulting density to `comfortable`.

Selection applies immediately to the root attribute. It does not reload routes, remount active
workflows, reset form state or invalidate tenant state. Account changes load that account's own
appearance pair. Logout clears the active pointer and returns the unauthenticated document to Navy
& Teal with comfortable density while retaining each private account preference. Corrupt or
unknown values fail closed to safe defaults.

The inline startup bootstrap validates both values before React mounts, preventing a density flash
on reload. Email addresses, names, customer IDs, organization IDs, access tokens and credentials
are never written to browser preference storage.

## Component coverage

Shared tokens drive the AppShell, sidebar navigation, global header, route headings, cards and
panels, buttons, form fields, tabs, tables, list-like rows, dialogs, alerts, toasts and workspace
selectors. Legacy domain surfaces consume the same table-cell and panel tokens where they have not
yet migrated to UX-103 primitives.

## Accessibility requirements

- Both modes retain the existing focus outline and halo.
- Density is exposed as a radio-style menu group with text labels, descriptions, selected icons and
  `aria-checked`; it does not rely on spacing alone.
- Keyboard Arrow, Home, End, Enter and Escape behavior is shared with theme selection.
- Compact mode does not reduce font sizes or semantic status information.
- Narrow screens preserve practical touch targets and horizontally scroll wide data tables inside
  their existing containers.

## Extension guidance

New shared components should consume density tokens rather than inspect the density ID. Feature
styles should introduce a semantic token only when an existing one cannot express the need; avoid
page-specific compact selectors. Future server-side preference storage can replace the browser
adapter without changing the root attributes or component contract.
