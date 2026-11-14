# UX-103: Reusable enterprise UI components

Status: **implemented component foundation**

Baseline: UX-102 at `866f91051f06bab0e1ed743231c96372d412501f`

WGASuite's reusable UI components live in `frontend/src/components/ui`. They use the semantic
tokens from `frontend/src/styles/tokens.css`, native HTML behavior, React, and the existing Lucide
icon dependency. No additional UI framework or runtime dependency is required.

This layer controls presentation and interaction semantics only. Backend authorization,
tenant-scoped routing, API contracts, mutation previews, single-use confirmations, audit logging,
no-retry guarantees, and read-only reconciliation remain domain responsibilities.

## Public components

Import components directly from their files. Direct imports keep ownership clear and avoid a
large barrel that can hide bundle boundaries.

| Component | File | Main API and variants |
| --- | --- | --- |
| `PageHeader` | `PageHeader.tsx` | `title`, optional `description`, `breadcrumbs`, `eyebrow`, and `actions` |
| `Card` | `Card.tsx` | semantic element via `as`; `padding=none|sm|md|lg`; `elevation=flat|raised` |
| `Tabs` | `Tabs.tsx` | controlled `activeId`, items, `onChange`, and required accessible label |
| `Button` | `Button.tsx` | `primary|secondary|danger|ghost`, `sm|md|lg`, disabled and loading states |
| `IconButton` | `Button.tsx` | required `label` and `icon`; inherits button variants and sizes |
| `Dropdown` | `Dropdown.tsx` | labeled action menu, start/end alignment, disabled/destructive items |
| `Tooltip` | `Tooltip.tsx` | top/bottom content linked to one interactive child with `aria-describedby` |
| `Input` | `FormControls.tsx` | required label, optional hint/error, leading icon, native input attributes |
| `Select` | `FormControls.tsx` | required label, typed option list, optional hint/error, native select attributes |
| `SearchField` | `FormControls.tsx` | search input semantics, search icon, optional accessible clear action |
| `Badge` | `Feedback.tsx` | `neutral|info|success|warning|danger`, optional supporting icon |
| `Alert` | `Feedback.tsx` | semantic variant, optional title/icon, status or alert live-region behavior |
| `Toast` | `Feedback.tsx` | semantic notification with optional dismiss action; use inside `ToastRegion` |
| `Modal` | `Modal.tsx` | controlled open state, title/description, footer, initial focus, close lock |
| `Skeleton` | `Feedback.tsx` | one or more non-semantic loading placeholders with reduced-motion support |
| `EmptyState` | `Feedback.tsx` | title, explanation, icon, and optional secondary recovery action |
| `ErrorState` | `Feedback.tsx` | alert landmark, error icon, explanation, and optional recovery action |

## API conventions

- Components accept normal native attributes wherever practical. Buttons remain buttons, selects
  remain selects, and field labels use `for`/`id` relationships.
- Size values are consistently `sm`, `md`, and `lg`. Semantic variants describe intent rather
  than a raw color.
- A loading `Button` is disabled, exposes `aria-busy`, and accepts a screen-reader loading label.
- `IconButton` requires a text label even when only its Lucide icon is visible.
- Field validation sets `aria-invalid` and connects hint or error text with `aria-describedby`.
- `Tabs` implement the ARIA tab pattern with roving tab stops plus Arrow, Home, and End navigation.
- `Dropdown` exposes menu semantics, Arrow navigation, Escape closing, outside-click closing, and
  focus restoration.
- `Modal` moves focus inside on open, traps Tab within the dialog, supports Escape and backdrop
  closing when permitted, and restores focus to the previous control.
- Status components always include text. Color is a supporting signal, never the only signal.
- Motion uses UX-102 timing tokens and stops for `prefers-reduced-motion`.

## Recommended usage

```tsx
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/FormControls";
import { PageHeader } from "../../components/ui/PageHeader";

<PageHeader
  breadcrumbs={["Directory", "Users"]}
  title="User directory"
  description="Browse users in the active Workspace tenant."
  actions={<Button onClick={refresh}>Refresh</Button>}
/>

<Input
  label="Display name"
  value={name}
  error={nameError}
  onChange={(event) => setName(event.target.value)}
/>
```

Use `Card` for one meaningful content boundary, not for every nested subsection. Use `Alert` for
inline contextual feedback and `Toast` for short-lived global outcomes. A destructive action must
use the danger variant and retain the domain workflow's explicit confirmation language.

## Incremental adoption completed in UX-103

- AppShell mobile controls, sidebar collapse, logout, Workspace switcher trigger, tenant selects,
  connection status, route PageHeader, and unavailable-route EmptyState.
- Development login Card, Input, Button, loading state, and Alert.
- Global request feedback through Alert.
- Dashboard content boundaries through Card and Button.
- The legacy User Directory/Exact Lookup switcher through keyboard-aware Tabs.

These migrations reuse the existing callbacks and state. They do not change route authorization,
tenant invalidation, connector behavior, or domain API calls.

## Deliberately deferred migration

Users, Groups, Gmail Delegations, and Organizational Units contain protected mutation dialogs and
ambiguous-outcome recovery states. UX-103 provides a tested `Modal` foundation but does not replace
those dialogs merely for visual consistency. Each later migration must preserve:

- exact preview and confirmation content;
- confirmation expiry and atomic single use;
- disabled state throughout the one permitted write;
- no automatic retries;
- reconciliation actions that cannot replay the write;
- focus restoration and error/audit evidence.

Feature-specific tables, tree controls, pagination, and complex pickers also remain domain-owned.
They can adopt the simple primitives independently without becoming a generic framework.

## Accessibility requirements

- Every field and icon-only action needs an accessible name.
- Focus must remain visible against light surfaces and the navy navigation.
- Dialogs require an explicit title and controlled close behavior.
- Errors require text, an alert relationship where urgent, and an associated field message where
  applicable.
- Tooltips supplement an existing accessible name; they never provide the only name.
- Touch controls use UX-102 control-height tokens, and responsive layouts must remain usable from
  320px upward.
- Automated interaction tests cover loading, validation, labels, keyboard tabs, dropdown focus,
  tooltip relationships, modal Escape/focus restoration, semantic states, and landmarks.

## UX-102 and UX-104 relationship

`ui.css` consumes semantic tokens only. UX-104 can implement Navy & Teal, Cobalt & Ice, and
Graphite & Copper mappings by overriding the semantic token layer; component code must not branch
on a theme name. Success, warning, error, danger, disabled, focus, and inverse meanings remain
stable across themes.

Before UX-104 exposes density selection, component-specific fixed dimensions should continue to
migrate toward `--control-height-*`, `--density-panel-padding`, and `--density-row-height`. Theme
and density persistence remain UX-104 decisions.
