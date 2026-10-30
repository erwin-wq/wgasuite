# Workspace capability parity

This directory freezes an evidence-backed comparison between PSGSuite, GAM7,
GAMADV-XTD3 and WGASuite. It is a product-roadmap baseline, not a claim that
WGASuite already reproduces every upstream command.

The canonical source is [`capabilities.yaml`](capabilities.yaml). It uses the
JSON subset of YAML 1.2 so the validator has no non-standard Python dependency.
[`capability-matrix.md`](capability-matrix.md) is generated and must not be
edited directly.

## Frozen baseline

- PSGSuite v3.0.1 at `f95943c09141a05adbf73222914c24474b54d0b5`:
  232 public functions, comprising 196 product/API-facing functions and 36
  runtime, configuration or builder helpers.
- GAM7 v7.49.05 at `d17979b02a92333d5199f75eaa79c5786b60f41b`:
  1,052 documented command variants. Of these, 1,000 variants in 84
  administrative families map to capabilities; 52 variants are explicitly
  classified as local runtime, bootstrap, authorization or bulk plumbing.
- GAMADV-XTD3 v7.05.08 at
  `f34ea0eb6281849edae18ac8eea331c490fae5df`: 61 command syntaxes absent
  verbatim from the GAM7 grammar were reviewed. Forty normalize to a GAM7
  result and 21 retain a materially distinct legacy result.
- WGASuite `main` at
  `206b546b170191c7e7f9628befe8ba599fe2d446`.

See [`baselines.md`](baselines.md) for release dates, hashes and source links.

## Model and definitions

A capability is one stable administrative result. `print` versus `show`, CLI
aliases, singular versus selector-based syntax, and CSV invocation do not
create separate capability rows. Those variants remain individually traceable
in `source_inventory` and point to their normalized capability IDs.

WGASuite implementation status means:

- `missing`: no matching application workflow;
- `mocked`: only synthetic behavior exists;
- `partial`: real code exists, but it does not deliver the complete result;
- `implemented`: the real workflow exists and is covered by repository tests;
- `verified`: implementation plus independent live-tenant acceptance evidence.

Parity is separate from implementation. A capability can be `verified` but
still have `partial` parity when GAM/PSGSuite support selectors, bulk/CSV,
external targets, role changes or execution semantics WGASuite does not.

Google API feasibility means:

- `direct`: pinned source exposes a concrete API method and OAuth scope, or the
  current WGASuite implementation supplies the reviewed mapping;
- `composed`: multiple documented API calls are required;
- `no-public-api`, `deprecated`, or `unknown`: the limitation is explicit and
  must be resolved before implementation.

Live acceptance is never inferred from unit-test coverage. The `verified`
rows reference the completed connector, Gmail delegation, Groups membership
or user-status acceptance tasks.

## Current coverage

The catalog contains 709 canonical capabilities:

| WGASuite status | Count |
|---|---:|
| verified | 12 |
| partial | 2 |
| implemented | 2 |
| mocked | 0 |
| missing | 693 |

All 16 non-missing capabilities have partial, rather than equivalent, parity
because WGASuite intentionally lacks upstream bulk selectors/CSV behavior or
supports a narrower guarded operation. There are 317 read, 281 write and 111
destructive capabilities. The roadmap maps 139 capabilities to v0.3 Directory
& Identity and 570 to later existing epics.

The API mapping is deliberately conservative: 202 capabilities have direct
method/scope evidence and 507 are explicitly `unknown`. The latter are not
silently treated as feasible; PAR-003 must confirm their current Google API,
least-privilege scope and authentication context before implementation.

## Validation and generation

Run:

```sh
python scripts/parity/validate_parity.py
```

After an intentional catalog change, regenerate the Markdown view and then
validate it:

```sh
python scripts/parity/validate_parity.py --write-matrix
python scripts/parity/validate_parity.py
```

The validator checks schema version, enums, unique capability and source IDs,
required evidence, roadmap links, bidirectional source mappings, frozen
inventory counts and deterministic Markdown output.

## v0.3 starting recommendations

The first five next capabilities should stay inside the existing Directory &
Identity epics and build outward from the verified read and mutation-safety
foundation:

1. `directory.users.move_orgunit` — add a guarded single-user move after OU
   ownership and target validation.
2. `directory.users.create` — guarded creation with explicit initial-password
   and recovery-data handling.
3. `directory.users.update` — complete profile/identity updates beyond the
   already verified suspend/reactivate subset.
4. `directory.users.aliases.add` — introduce safe alias lifecycle management;
   removal remains a separately guarded capability.
5. `directory.orgunits.create` — add guarded OU creation only after shared
   mutation previews and exact parent/customer protections are designed.

These recommendations do not authorize implementation or live Workspace
mutations as part of PAR-001.
