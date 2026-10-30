# Frozen upstream baselines

Retrieval date: **2026-10-30** (Europe/Amsterdam).

| Upstream | Frozen version | Immutable commit | Release evidence |
|---|---|---|---|
| PSGSuite | GitHub v3.0.1 / PowerShell Gallery 3.0.1-beta | `f95943c09141a05adbf73222914c24474b54d0b5` | [GitHub release](https://github.com/SCRT-HQ/PSGSuite/releases/tag/v3.0.1), [PowerShell Gallery](https://www.powershellgallery.com/packages/PSGSuite/3.0.1-beta) |
| GAM7 | v7.49.05 | `d17979b02a92333d5199f75eaa79c5786b60f41b` | [GitHub release](https://github.com/GAM-team/GAM/releases/tag/v7.49.05) |
| GAMADV-XTD3 | v7.05.08 | `f34ea0eb6281849edae18ac8eea331c490fae5df` | [GitHub release](https://github.com/taers232c/GAMADV-XTD3/releases/tag/v7.05.08) |
| WGASuite | `main` before PAR-001 | `206b546b170191c7e7f9628befe8ba599fe2d446` | [repository tree](https://github.com/erwin-wq/wgasuite/tree/206b546b170191c7e7f9628befe8ba599fe2d446) |

The historical Asana references to GAM7 v7.48.18 and the earlier immutable
v7.48.11 correction are superseded for this baseline. On the retrieval date,
GitHub's immutable latest release was v7.49.05, published 2026-10-29. The
separate GAMADV-XTD3 repository remains frozen at v7.05.08; GAM7 is its current
successor, but the legacy grammar is retained to detect materially different
capabilities.

## Reproducibility manifest

| Artifact | Inventory result | SHA-256 |
|---|---:|---|
| PSGSuite `PSGSuite/Public/**/*.ps1` sorted file-hash manifest | 232 public functions | `bbb51a0a918a8e51837e1c4fa4238aaca7eca797b71686dfdd1f7070a324d989` |
| GAM7 `src/GamCommands.txt` | 9,162 lines; 1,052 command variants | `4003533cffaeb1a3c1cf4f361837b5f0929d0de406caa5b655bffc3b97bc20fc` |
| GAMADV-XTD3 `src/GamCommands.txt` | 8,447 lines; 967 command variants | `ba46794c73812ec27b550d1a0d613e89018dd82491507abe08d3d355116d0d89` |

Each inventory item in `capabilities.yaml` includes its immutable source URL,
source line (for GAM) or exported function name (for PSGSuite), disposition and
capability mapping. This lets the validator prove 100% accounting without
vendoring upstream source code.

## Official API evidence

API and scope mappings use the pinned upstream implementations together with
Google's official [OAuth scope registry](https://developers.google.com/identity/protocols/oauth2/scopes)
and service references, including the [Admin SDK Directory API](https://developers.google.com/workspace/admin/directory/reference/rest),
[Gmail API](https://developers.google.com/workspace/gmail/api/reference/rest),
[Drive API](https://developers.google.com/workspace/drive/api/reference/rest/v3),
[Calendar API](https://developers.google.com/workspace/calendar/api/v3/reference),
[Classroom API](https://developers.google.com/workspace/classroom/reference/rest),
[Chat API](https://developers.google.com/workspace/chat/api/reference/rest),
[Reports API](https://developers.google.com/workspace/admin/reports/reference/rest),
[Data Transfer API](https://developers.google.com/workspace/admin/data-transfer/reference/rest)
and [License Manager API](https://developers.google.com/workspace/admin/licensing/reference/rest).

An upstream CLI result whose exact current method/scope could not be proven is
classified `unknown` with a PAR-003 limitation. It is not presented as a
confirmed API design.
