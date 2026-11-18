# UX-107 Premium Workspace Dashboard

## Purpose

The `/overview` route is the task-oriented starting point for Google Workspace administration. It
summarizes connection readiness and links to existing workflows without duplicating the global
Workspace selector or presenting unsupported metrics.

## Information model

The dashboard uses only application state already loaded for the authenticated user:

- selected customer and organization from the AppShell Workspace selector;
- the tenant-scoped connector configuration returned by
  `GET /api/v1/organizations/{organization_id}/connector-configs`;
- route authorization derived from the authenticated role and selected tenant.

Connector status, the latest verified time, and configuration availability come directly from the
connector record. The page does not infer user or group totals, security scores, synchronization
times, audit activity, assessments, or report results. Missing values are labeled as unavailable.

## States and navigation

The connection band distinguishes loading, missing customer, missing organization, not configured,
configured but unverified (disconnected), connected, and failed states. Connector loading has its own request state
so tenant changes cannot temporarily present an empty response as “not configured.” Existing request
sequence guards continue to reject stale tenant responses. A connector-config API failure renders a
separate “Status unavailable” state and therefore cannot be mistaken for missing configuration.

Authorized tenant operators receive typed-route links to user lookup, Groups, Organizational Units,
and Gmail Delegations. Users who can read tenant configuration can open Connection settings. Other
roles receive an explicit unavailable state rather than controls they cannot use.

## Design and accessibility

The layout uses UX-102 semantic color and density tokens plus UX-103 Card, Badge, and Skeleton
components. It supports all UX-104 themes and both UX-105 density modes. Links retain native keyboard
behavior and visible focus treatment; status meaning is communicated with text and icons in addition
to color. At narrow widths, the connection band and task layout become a single column without
hiding controls or using global overflow suppression.

## Security boundary

UX-107 adds no backend action, OAuth scope, Google API call, mutation, confirmation, audit event, or
database schema. Existing route authorization, customer scoping, tenant-switch cancellation, and
mutation safety behavior remain unchanged.
