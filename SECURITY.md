# Security Policy

## Supported status

WGASuite is an early-development, pre-release project. There are no supported production releases
yet. Security fixes are handled on a best-effort basis in the active development branch.

The current bearer-token authentication and environment-configured development administrator are
development foundations. They are not a production identity or session-management solution.

## Reporting a vulnerability

Do not open a public issue containing an active vulnerability, exploit details, credentials,
tokens, private keys, customer data or sensitive Google Workspace information.

Use the repository's **Security → Report a vulnerability** flow. GitHub Private Vulnerability
Reporting is enabled for this repository.

If that flow is temporarily unavailable, do not publish vulnerability details in an issue. Contact
the repository owner through a non-sensitive channel to request a private reporting path.

Include only the information needed to reproduce and assess the issue:

- affected component and revision;
- impact and expected security boundary;
- minimal reproduction steps or proof of concept;
- suggested remediation, if known.

Use synthetic data. Remove secrets and real tenant/customer information from logs, requests,
screenshots and attachments.

## Response and disclosure

Because the project is pre-release, no response-time SLA is currently offered. Maintainers should
acknowledge valid private reports, assess impact, coordinate a fix and agree on disclosure timing
before public details are released.

## Deployment responsibility

Do not deploy the current development authentication model as production identity management. A
production deployment needs, at minimum, hardened authentication and authorization, secure secret
storage and rotation, rate limiting, session policy, monitoring, backups and reviewed deployment
guidance.
