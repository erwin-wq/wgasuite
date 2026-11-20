# UX-110: Premium Gmail delegation management

Status: **implemented; live capability unchanged**

Baseline: UX-112 at `4704e50e21b0fb368bcfe28346bb3ba6387442f3`

UX-110 modernizes the existing Gmail delegation workflow without changing Google API contracts,
authorization, mutation confirmations, audit events, retry behavior, or reconciliation semantics.

## Before and migration scope

The standalone `/gmail/delegations` route previously rendered the complete exact-user lookup and
user-detail screen. Operators had to pass identity, groups, status, and organizational-unit
sections before reaching delegation controls. `MailboxDelegates` used a custom delegate list,
form, status messages, and confirmation overlay despite equivalent UX-103 and UX-112 primitives.

The accepted migration scope is:

1. Give the standalone route a mailbox-first hierarchy: exact lookup, selected identity, current
   delegates, supported administration action, and protected feedback.
2. Keep primary email and aliases in ephemeral tenant-scoped component state; they never enter the
   URL.
3. Continue rendering the same `MailboxDelegates` domain component in the standalone route and
   exact User Detail.
4. Migrate presentation to shared `DataTable`, `Input`, `Button`, `Badge`, `Alert`, `EmptyState`,
   and `Modal` components.
5. Preserve every protected write and reconciliation branch in the existing component.

## Supported capabilities

WGASuite supports one exact mailbox-owner lookup by complete primary email or user alias. For a
resolved internal user it can list direct Gmail delegates and display Google's verification status.
Authorized administrators can preview and explicitly confirm one delegate grant or removal.

Unsupported capabilities remain absent: partial-name search, wildcards, bulk lookup, bulk
mutations, external-user discovery, invented timestamps or roles, mailbox message access, and
delegation-policy administration.

## Safety contract

- Tenant changes abort reads, invalidate selected owners, and reject stale responses.
- Lookup and delegate list failures use sanitized application messages.
- Preview responses remain authoritative for canonical owner, delegate, effect, confirmation
  token, and expiry.
- The confirmation remains expiring, digest-backed, atomic, and single-use on the backend.
- Mutation submission remains guarded against duplicate clicks and automatic retries.
- Timeout, network, and service-unavailable outcomes remain ambiguous rather than successful.
- Ambiguous outcomes run the existing bounded read-only reconciliation and never repeat a write.
- Definitive failures never offer reconciliation.
- Confirmation tokens are never rendered, logged, stored in URLs, or added to audit metadata by
  the frontend.

## Presentation and accessibility

The standalone page uses a compact mailbox lookup band, one identity summary, a truthful delegate
table, and a distinct grant-access section. User Detail reuses the same delegate table, action,
feedback, and dialog presentation without duplicating mutation logic.

Native field and table semantics provide labels, descriptions, column headers, and keyboard row
actions. The shared modal traps focus, closes with Escape when safe, and restores focus to the
invoking Review or Remove button. Statuses combine text with semantic styling. Long addresses wrap
inside identity fields and remain contained by the table's keyboard-scrollable region. Themes and
density modes are token-driven and do not remount or reset active forms.

## Visual reference

The UX-110 desktop and mobile references are private design artifacts generated for implementation
review. They are not production assets and are not committed. The implementation uses code-native
WGASuite controls and existing Lucide icons exclusively.
