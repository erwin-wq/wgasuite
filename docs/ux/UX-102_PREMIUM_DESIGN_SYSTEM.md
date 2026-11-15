# UX-102: Premium design system and visual identity

Status: **implemented foundation**

Baseline: UX-106 AppShell at `02ed3a89df583c1f62c1f2fe39e2cf3f58e1e4c2`

This document defines WGASuite's default visual system. It changes presentation only: backend
authorization, tenant isolation, Google Workspace mutation safety, audit behavior, and capability
status remain authoritative and unchanged.

## Design principles

- **Navy and Teal** provide the stable application frame and primary interaction language.
- **Cobalt and Ice** keep content areas light and distinguish informational emphasis.
- **Graphite and Copper** provide readable text, refined borders, and a deliberately sparse
  decorative accent. Copper never communicates status or destructive intent.
- Information density takes priority over decoration. Surfaces use thin borders, modest radii,
  and low elevation instead of gradients or deeply nested cards.
- A polished state must remain truthful. Visual treatment cannot promote a mocked, partial, or
  unavailable capability to an implemented or verified state.

## Token architecture

[`frontend/src/styles/tokens.css`](../../frontend/src/styles/tokens.css) is the single source for
the design primitives and semantic tokens. Application styles must consume semantic tokens, not
palette primitives. The file has four layers:

1. `--palette-*` contains stable raw colors for the default visual family.
2. Semantic colors such as `--color-surface-primary`, `--color-text-secondary`,
   `--color-action-primary`, and `--color-error-surface` express purpose.
3. Typography, spacing, radius, elevation, component-size, density, motion, and AppShell tokens
   standardize non-color decisions.
4. Compatibility aliases map established names such as `--color-ink` and `--color-line` onto the
   semantic layer. They support incremental migration; new code should use semantic names.

Component styles must not use raw hex values for page-level color decisions. An exception is a
new palette or semantic token definition in the central token file. Alpha colors that depend on a
specific inverse surface also belong in the token file when reused.

### Core semantic examples

| Purpose | Token | Default value or source |
| --- | --- | --- |
| Workspace canvas | `--color-background-canvas` | Ice `#f4f8fc` |
| Primary surface | `--color-surface-primary` | White |
| Primary text | `--color-text-primary` | Graphite `#172433` |
| Secondary text | `--color-text-secondary` | Graphite `#425466` |
| Navigation | `--color-nav-background` | Navy `#071c2c` |
| Primary action | `--color-action-primary` | Teal `#0f766e` |
| Informational emphasis | `--color-highlight-strong` | Cobalt `#315fb5` |
| Decorative accent | `--color-accent-decorative` | Copper `#a9622e` |
| Keyboard focus | `--color-focus-ring` | Cyan-blue `#087fa0` |
| Success | `--color-success-*` | Green-teal text, surface, border trio |
| Warning | `--color-warning-*` | Amber text, surface, border trio |
| Error | `--color-error-*` | Red text, surface, border trio |

Primary actions are flat teal and use hover and active semantic variants. Secondary actions use a
white surface and graphite text. Destructive actions have their own danger tokens; they must not
reuse copper. Disabled controls retain a visible border and readable label while clearly losing
interactive emphasis.

## Typography, spacing, and density

The sans-serif stack prefers locally available Inter or Geist Sans and falls back to native UI
fonts. No runtime font download or new package is required. Geist Mono or system monospace is
reserved for identifiers and code-like values.

Type uses a compact scale from `--font-size-xs` through `--font-size-2xl`, with `--font-size-hero`
retained for the few legacy marketing-style surfaces. Route headings use tight tracking; body text
uses a 1.5 line height. Labels are sentence case unless a navigation-group convention explicitly
uses uppercase.

Spacing follows a 4px base from `--space-1` through `--space-12`. Default control heights are 36,
44, and 50px. Radius tokens are 4, 6, 10, and 14px plus pill. New product panels should normally
use `--radius-md` or `--radius-lg`; pill radii are for badges and compact status only.

The comfortable density is the root default. Applying `data-density="compact"` to a future shell
owner changes control heights, page gutters, panel padding, and row height without changing domain
markup. UX-102 defines this foundation but does not expose a density preference or selector.

## Accessibility requirements

- Normal text and meaningful icons target WCAG 2.2 AA contrast (4.5:1); large text and non-text
  controls target at least 3:1.
- Every interactive control needs a visible `:focus-visible` treatment. The default combines a
  solid focus outline and halo so focus is visible on both light and navy surfaces.
- Hover cannot be the only indicator of interactivity. Active navigation includes text contrast,
  a surface change, and a leading indicator.
- Success, warning, error, connection, and disabled states require text or an icon in addition to
  color. Status wording remains part of the accessible name.
- Reduced-motion preferences set shared transition durations to zero. Feature animation should
  consume the shared motion tokens or provide an equivalent reduction.
- Mobile controls remain usable from 320px upward and should preserve a minimum practical touch
  target through the component-height tokens.

Representative default contrast checks:

| Pair | Intended use | Ratio |
| --- | --- | ---: |
| White on teal `#0f766e` | Primary action | 5.47:1 |
| Graphite `#172433` on white | Primary text | 15.71:1 |
| Graphite `#425466` on white | Secondary text | 7.80:1 |
| White on navy `#071c2c` | Inverse/nav text | 17.33:1 |
| Muted nav `#b8cad6` on navy | Navigation labels | 10.28:1 |

Ratios are rounded and should be recomputed if either token changes.

## Usage examples

```css
.example-panel {
  background: var(--color-surface-primary);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  color: var(--color-text-primary);
  padding: var(--density-panel-padding);
}

.example-help {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}
```

Use the existing Lucide React icon dependency. Icons should reinforce the accessible label, not
replace it unless the control has an explicit accessible name. Avoid mixing filled and outline icon
families in the application shell.

## UX-102 application boundary

The default system is applied to the UX-106 sidebar, global header, Workspace switcher,
breadcrumbs, navigation states, account controls, route canvas, base panels, buttons, form fields,
messages, and common statuses. Existing domain components remain structurally unchanged. This
keeps routing, permissions, tenant invalidation, confirmations, no-retry behavior, reconciliation,
and audit controls intact.

UX-102 deliberately does not normalize every feature-specific component. Existing compatibility
aliases allow those components to inherit the palette safely until UX-103 moves repeated controls
and surfaces into reusable components.

## Follow-on work

### UX-103 reusable components

UX-103 should consume this token source while extracting Button, Field, Select, Panel, Status,
Dialog, Table, EmptyState, and PageHeader primitives. It should migrate compatibility aliases only
after all consumers are identified, preserve accessible names and focus management, and avoid
embedding domain authorization in visual components.

### UX-104 theme families

UX-104 implements complete Navy & Teal, Cobalt & Ice, and Graphite & Copper mappings by overriding
the semantic layer. Success, warning, error, danger, focus, disabled, and contrast meanings remain
consistent across themes. The account-scoped, browser-local persistence and privacy decisions are
documented in [`UX-104_THEME_SYSTEM.md`](UX-104_THEME_SYSTEM.md). Density remains reserved for
UX-105.
