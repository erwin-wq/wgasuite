# UX-104: Premium themes and preference persistence

Status: **implemented**

Baseline: UX-103 reusable components at `6548ee211b79ed46ee4d41c1c3cc10fba1c84e20`

UX-104 adds three selectable presentation themes without changing routes, authorization, tenant
state, domain workflows, mutation safeguards, audit behavior, or Google Workspace capabilities.

## Theme families

| Stable ID | Display name | Character |
| --- | --- | --- |
| `navy-teal` | Navy & Teal | Default navy application frame, teal actions, ice canvas and restrained copper detail. |
| `cobalt-ice` | Cobalt & Ice | Light navigation, cobalt actions, cool white surfaces and graphite typography. |
| `graphite-copper` | Graphite & Copper | Dark graphite canvas, elevated dark surfaces and muted copper interaction accents. |

Success, warning, error and destructive meanings retain dedicated semantic colors in every theme.
Copper remains decorative or interactive and never substitutes for warning or error.

## Architecture

The document root owns one `data-theme` attribute. `tokens.css` remains the canonical token
source: theme selectors override only semantic color and elevation tokens, while spacing,
typography, component sizing, motion and the future density contract remain shared. Components
continue consuming semantic tokens; the application does not maintain three CSS copies.

The account menu exposes radio-style theme options with an explicit selected state. A selection
updates the root attribute immediately, so React routes and domain components are not remounted and
in-progress form state is preserved.

## Preference privacy and startup

Preferences use namespaced browser storage because WGASuite does not otherwise provide a user
preference API. Storage records contain only a schema version, an opaque short hash derived
from the opaque authenticated user ID, and the stable theme ID. Email addresses, names, tokens,
tenant IDs and credentials are never included.

Each account has a separate preference record. A small inline bootstrap in `index.html` applies the
last active authenticated account's validated theme before application CSS loads, preventing a
wrong-theme flash on reload. Logout removes only the active-account pointer and restores Navy &
Teal; a later login restores that account's private preference. Invalid JSON, unknown themes and
unavailable storage fail closed to Navy & Teal without blocking the application.

## Accessibility contract

- Theme choices use `menuitemradio` and `aria-checked`, and support Arrow, Home, End, Enter and
  Escape keyboard behavior with focus restoration.
- Representative normal text targets 4.5:1 contrast; controls, borders and focus indicators target
  3:1 where applicable.
- Selected states combine surface, text and a check icon. Status meaning remains textual and does
  not rely on color alone.
- Shared focus and reduced-motion tokens remain authoritative in all themes.

## UX-105 boundary

UX-104 does not expose comfortable/compact density selection. Existing `data-density` tokens remain
unchanged for UX-105, which may reuse the same account-scoped preference architecture with an
independent schema field after its interaction and migration behavior are reviewed.
