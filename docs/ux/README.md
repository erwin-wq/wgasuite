# WGASuite premium UX documentation

This directory is the maintained design and acceptance record for the production WGASuite
interface. The documents describe presentation contracts; backend authorization, customer
scoping, Google Workspace mutation safeguards, and the capability catalog remain authoritative.

## Canonical records

| Concern | Canonical document | Implementation owner |
| --- | --- | --- |
| Information architecture, routes, privacy and role boundaries | [UX-101](UX-101_WORKSPACE_INFORMATION_ARCHITECTURE.md) | `frontend/src/features/navigation/routes.ts` and `frontend/src/App.tsx` |
| Semantic tokens, typography, spacing and accessibility rules | [UX-102](UX-102_PREMIUM_DESIGN_SYSTEM.md) | `frontend/src/styles/tokens.css` |
| Reusable component APIs and usage guidance | [UX-103](UX-103_REUSABLE_UI_COMPONENTS.md) | `frontend/src/components/ui/` |
| Theme families and account-isolated persistence | [UX-104](UX-104_THEME_SYSTEM.md) | `frontend/src/features/preferences/` |
| Comfortable and compact density contracts | [UX-105](UX-105_DENSITY_MODES.md) | `data-density` and semantic density tokens |
| Responsive and accessibility baseline | [UX-113](UX-113_RESPONSIVE_ACCESSIBILITY_AUDIT.md) | AppShell, shared components and route-specific layouts |
| Motion and interaction policy | [UX-114](UX-114_PREMIUM_MICRO_INTERACTIONS.md) | shared motion tokens and `prefers-reduced-motion` rules |
| Final cross-route release acceptance | [UX-115](UX-115_FINAL_RELEASE_ACCEPTANCE.md) | CI browser suite and release review |

Route-specific records for Overview, Gmail Delegations, administration, enterprise tables/forms,
and Organizational Units supplement these foundations. When a route record conflicts with a
foundation document, the newer security-preserving implementation and backend policy win; update
the documentation in the same change.

## Extension rules

- Add colors, spacing, sizes and motion through semantic tokens; do not embed a new visual system
  in a feature stylesheet.
- Build common controls from the UX-103 primitives before adding a route-local control.
- New themes must implement the complete semantic token contract and retain status meaning,
  contrast, focus visibility, reduced-motion behavior and both density modes.
- New production routes belong in the typed route registry, must define an access class and
  breadcrumbs, and must be covered at desktop, laptop and mobile widths.
- Never place primary email addresses, Google immutable IDs, credential references, access tokens
  or confirmation tokens in URLs or browser preference storage.
- A polished screen is not evidence that its Google Workspace capability is live verified. Keep
  implementation and verification claims aligned with the parity catalog.

Mock assessments, mock scans and report foundations are deliberately excluded from normal
production navigation. They may only appear behind the explicit development feature flag and
must not be presented as security evidence or current Workspace state.
