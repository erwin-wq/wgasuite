# WGASuite Product Strategy

## Purpose

WGASuite aims to become an open-source, self-hosted Google Workspace administration and security
platform. The long-term goal is to give teams a shared web interface for administering Workspace,
assessing security posture and recording operational evidence without requiring every workflow to
be built from one-off scripts.

WGASuite `v0.1.0` is an early foundation, not the completed platform. It must not be treated as a
production Google Workspace management system.

## Current state

The current release provides:

- platform roles, customer memberships and backend-enforced customer scoping;
- customer and organization records;
- assessments, assets, findings and DREAD risk scoring;
- assessment reports and selected structured audit events;
- connector configuration metadata, a Workspace check catalog and mock scan history.

Current Google Workspace scans and findings are mock/demo functionality. WGASuite does not yet
connect to Google APIs, manage Google users or groups, store connector credentials, or provide a
production identity and session model. The [README](../README.md) remains authoritative for the
detailed current capability boundary.

## Product principles

### Direct APIs first

Google Workspace functionality should use official Google APIs wherever practical. Product
workflows should operate on structured domain data and structured API results rather than depend on
command-line output parsing.

### Least privilege

Each connector feature should declare and request only the Google scopes it needs. Read-only and
write capabilities should be separable so deployments do not need to grant mutation authority to
use inventory or assessment features.

### Tenant isolation

Every connector, operation, job and audit record must remain explicitly bound to a customer and
organization. Client-provided identifiers must never be sufficient to cross those boundaries.

### Auditable operations

Operationally meaningful reads and writes should produce structured evidence that records the
actor, tenant, action, target, outcome and relevant configuration version without storing secrets.
Audit coverage for real Google operations is a target requirement; it is not complete today.

### Safe mutations

Mutating workflows should apply controls appropriate to their risk, including:

- an understandable preview of the intended change;
- explicit authorization and confirmation;
- idempotent behavior where the external API permits it;
- structured success, failure and partial-result reporting;
- audit events for both successful and failed execution.

Approval, retry, cancellation and compensation controls should be added when an operation's impact
or execution model requires them. These controls describe the intended architecture and are not all
implemented in `v0.1.0`.

### Self-hosted and open

WGASuite should remain inspectable, self-hostable and useful without a mandatory WGASuite-operated
service. Deployment documentation must make the security and operational responsibilities of
self-hosting clear.

## Architecture strategy

The project considered direct API integration, GAM as the execution engine and a hybrid model. The
decision is to use direct Google APIs for WGASuite's core functionality.

### Direct Google APIs — selected

Direct integration best fits WGASuite's intended product boundaries because it enables:

- feature-specific, least-privilege scope design;
- typed domain data and structured Google API errors;
- explicit customer and organization routing;
- semantic audit records instead of command transcripts alone;
- policy-controlled mutations with predictable inputs and results;
- a consistent path toward background work, retries and observability.

This choice has a cost: WGASuite must implement and maintain authentication, pagination, quotas,
error classification, API evolution and tests for each supported domain. The roadmap therefore
prioritizes narrow end-to-end workflows rather than broad API coverage.

### GAM execution engine — not selected for the core architecture

[GAM](https://github.com/GAM-team/GAM) is a mature project with exceptional Google Workspace API
coverage and remains an important feature and behavior benchmark. Using GAM as WGASuite's primary
execution layer, however, would add product-specific work around command construction, subprocess
execution, output parsing, execution isolation, credential and scope modeling, and version
compatibility.

That trade-off is valid for tools designed as GAM interfaces. It is less aligned with WGASuite's
goal of a structured, tenant-scoped administration and security control plane. WGASuite does not
intend to compete with GAM on command breadth in the short term.

### Hybrid or optional GAM adapter — a future possibility

An isolated, opt-in GAM adapter may be reconsidered if direct API support for valuable long-tail
operations becomes disproportionately expensive. Any such adapter would need explicit credential
separation, command policy, execution isolation and semantic audit boundaries.

No GAM adapter is part of the current architecture or `v0.2.0` roadmap.

## Competitive position

WGASuite's current differentiators are its combination of:

- a multi-customer web data model with backend-enforced memberships and scoping;
- an assessment, finding, asset and DREAD risk workflow;
- platform and customer administration foundations;
- a structured API and PostgreSQL persistence layer.

These are useful foundations, but they do not yet make WGASuite a functioning Google Workspace
administration platform.

The target differentiation is the combination of multi-customer administration, security
assessments, tenant-scoped authorization, structured auditability, safe web workflows and direct
Google API integration. That target must be earned through working integrations and production
security controls rather than treated as a current claim.

## First integration vertical: Google Workspace User Directory

The first direct integration will prove the read path before introducing a mutation:

1. validate a real connector and report structured setup failures;
2. list and search users through the Admin SDK Directory API;
3. inspect a selected user's details;
4. retrieve relevant group memberships for that user;
5. enforce customer and organization scoping on every request;
6. record meaningful, secret-free audit events;
7. expose structured Google API errors to the product without leaking sensitive data.

Once the read-only integration is proven, guarded user suspension and restoration are the intended
follow-up mutation. They must not be enabled merely because user reads work; the authorization,
preview, confirmation, idempotency and audit requirements must be implemented first.

## v0.2.0 objective

> Prove WGASuite's production-oriented Google integration architecture with a real,
> tenant-scoped Directory API workflow.

The focused release plan is maintained in the [roadmap](ROADMAP.md).

## Non-goals for v0.2.0

The following remain possible future areas, not `v0.2.0` commitments:

- broad GAM-equivalent command or feature coverage;
- a GAM wrapper or embedded command terminal;
- Gmail or Drive administration;
- ChromeOS, mobile or endpoint administration;
- license administration;
- a generic automation or scheduling engine;
- broad bulk operations and full MSP workflow coverage;
- production support for every Google Workspace API.

## Research basis

This direction was selected after a competitive and product-gap review completed on 2026-09-19.
The review considered GAM, several GAM interfaces, direct-API desktop and CLI tools, and a focused
just-in-time administration application. Time-sensitive repository statistics and the raw research
notes are intentionally not copied into this durable strategy document.
