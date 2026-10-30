#!/usr/bin/env python3
"""Validate the canonical parity catalog and render its Markdown view.

The ``.yaml`` catalog intentionally uses the JSON subset of YAML 1.2 so this
validator needs only Python's standard library in developer workstations and CI.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "docs" / "parity" / "capabilities.yaml"
MATRIX_PATH = ROOT / "docs" / "parity" / "capability-matrix.md"

CAPABILITY_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
SOURCE_ID = re.compile(r"^(psgsuite|gam7|gamadv):[a-z0-9._-]+$")
URL = re.compile(r"^https://")

ACCESS = {"read", "write", "destructive"}
FEASIBILITY = {"direct", "composed", "no-public-api", "deprecated", "unknown"}
IMPLEMENTATION = {"missing", "mocked", "partial", "implemented", "verified"}
PARITY = {
    "equivalent",
    "partial",
    "missing",
    "blocked",
    "deprecated-upstream",
    "not-applicable",
}
SOURCE_DISPOSITIONS = {
    "mapped",
    "non-product",
    "deprecated",
    "covered-by-gam7",
    "gamadv-specific",
}


class ValidationError(Exception):
    """One or more catalog invariants failed."""


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(f"catalog not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"{path}:{exc.lineno}:{exc.colno}: invalid JSON-compatible YAML: {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise ValidationError("catalog root must be an object")
    return value


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate(catalog: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    require(catalog.get("schema_version") == "1.0", "schema_version must be 1.0", errors)
    require(catalog.get("catalog_version"), "catalog_version is required", errors)
    require(catalog.get("retrieved_on"), "retrieved_on is required", errors)

    baselines = catalog.get("baselines")
    require(isinstance(baselines, dict), "baselines must be an object", errors)
    if isinstance(baselines, dict):
        for key in ("psgsuite", "gam7", "gamadv_xtd3", "wgasuite"):
            baseline = baselines.get(key)
            require(isinstance(baseline, dict), f"baseline {key} is required", errors)
            if not isinstance(baseline, dict):
                continue
            for field in ("version", "commit", "retrieved_on", "source_url"):
                require(bool(baseline.get(field)), f"baseline {key}.{field} is required", errors)
            require(
                isinstance(baseline.get("source_url"), str)
                and bool(URL.match(baseline["source_url"])),
                f"baseline {key}.source_url must be HTTPS",
                errors,
            )

    evidence = catalog.get("evidence")
    require(isinstance(evidence, dict) and evidence, "evidence must be a non-empty object", errors)
    if not isinstance(evidence, dict):
        evidence = {}
    for evidence_id, item in evidence.items():
        require(bool(CAPABILITY_ID.match(evidence_id)), f"invalid evidence id {evidence_id}", errors)
        require(isinstance(item, dict), f"evidence {evidence_id} must be an object", errors)
        if not isinstance(item, dict):
            continue
        require(bool(item.get("title")), f"evidence {evidence_id}.title is required", errors)
        require(
            isinstance(item.get("url"), str) and bool(URL.match(item["url"])),
            f"evidence {evidence_id}.url must be HTTPS",
            errors,
        )

    capabilities = catalog.get("capabilities")
    require(isinstance(capabilities, list) and capabilities, "capabilities must be non-empty", errors)
    if not isinstance(capabilities, list):
        capabilities = []

    capability_ids: set[str] = set()
    for index, capability in enumerate(capabilities):
        where = f"capabilities[{index}]"
        require(isinstance(capability, dict), f"{where} must be an object", errors)
        if not isinstance(capability, dict):
            continue
        capability_id = capability.get("capability_id")
        require(
            isinstance(capability_id, str) and bool(CAPABILITY_ID.match(capability_id)),
            f"{where}.capability_id is invalid",
            errors,
        )
        if not isinstance(capability_id, str):
            continue
        require(capability_id not in capability_ids, f"duplicate capability_id {capability_id}", errors)
        capability_ids.add(capability_id)
        prefix = capability_id
        for field in ("service", "object", "action", "description"):
            require(bool(capability.get(field)), f"{prefix}.{field} is required", errors)
        require(capability.get("access") in ACCESS, f"{prefix}.access is invalid", errors)

        upstream = capability.get("upstream")
        require(isinstance(upstream, dict), f"{prefix}.upstream is required", errors)
        if isinstance(upstream, dict):
            source_ids = upstream.get("source_ids")
            require(
                isinstance(source_ids, list) and bool(source_ids),
                f"{prefix}.upstream.source_ids must be non-empty",
                errors,
            )

        google = capability.get("google")
        require(isinstance(google, dict), f"{prefix}.google is required", errors)
        if isinstance(google, dict):
            feasibility = google.get("feasibility")
            require(feasibility in FEASIBILITY, f"{prefix}.google.feasibility is invalid", errors)
            require(bool(google.get("auth_context")), f"{prefix}.google.auth_context is required", errors)
            if feasibility in {"direct", "composed"}:
                for field in ("api", "methods", "scopes"):
                    value = google.get(field)
                    require(bool(value), f"{prefix}.google.{field} is required", errors)
                scopes = google.get("scopes", [])
                require(
                    isinstance(scopes, list)
                    and all(isinstance(scope, str) and scope.startswith("https://") for scope in scopes),
                    f"{prefix}.google.scopes must contain HTTPS scope URLs",
                    errors,
                )
            else:
                require(bool(google.get("limitation")), f"{prefix}.google.limitation is required", errors)

        execution = capability.get("execution")
        require(isinstance(execution, dict), f"{prefix}.execution is required", errors)
        if isinstance(execution, dict):
            for field in ("single", "bulk", "selectors", "filters", "csv"):
                require(field in execution, f"{prefix}.execution.{field} is required", errors)
            for field in ("single", "bulk", "filters", "csv"):
                require(
                    isinstance(execution.get(field), bool),
                    f"{prefix}.execution.{field} must be boolean",
                    errors,
                )
            require(
                isinstance(execution.get("selectors"), list),
                f"{prefix}.execution.selectors must be a list",
                errors,
            )
            require(
                isinstance(execution.get("semantics"), list)
                and bool(execution.get("semantics")),
                f"{prefix}.execution.semantics must be a non-empty list",
                errors,
            )

        wgasuite = capability.get("wgasuite")
        require(isinstance(wgasuite, dict), f"{prefix}.wgasuite is required", errors)
        if isinstance(wgasuite, dict):
            require(wgasuite.get("status") in IMPLEMENTATION, f"{prefix}.wgasuite.status is invalid", errors)
            require(wgasuite.get("parity") in PARITY, f"{prefix}.wgasuite.parity is invalid", errors)
            require(isinstance(wgasuite.get("evidence_refs"), list), f"{prefix}.wgasuite.evidence_refs must be a list", errors)
            if wgasuite.get("status") == "verified":
                require(bool(wgasuite.get("evidence_refs")), f"{prefix} verified status needs evidence", errors)

        roadmap = capability.get("roadmap")
        require(isinstance(roadmap, dict), f"{prefix}.roadmap is required", errors)
        if isinstance(roadmap, dict):
            for field in ("epic", "release", "task_url"):
                require(bool(roadmap.get(field)), f"{prefix}.roadmap.{field} is required", errors)
            require(
                isinstance(roadmap.get("task_url"), str) and bool(URL.match(roadmap["task_url"])),
                f"{prefix}.roadmap.task_url must be HTTPS",
                errors,
            )
        require(isinstance(capability.get("verification"), dict), f"{prefix}.verification is required", errors)
        refs = capability.get("evidence_refs")
        require(isinstance(refs, list) and refs, f"{prefix}.evidence_refs must be non-empty", errors)
        if isinstance(refs, list):
            for ref in refs:
                require(ref in evidence, f"{prefix} references unknown evidence {ref}", errors)

    inventories = catalog.get("source_inventory")
    require(isinstance(inventories, dict), "source_inventory must be an object", errors)
    seen_source_ids: set[str] = set()
    mapped_source_ids: set[str] = set()
    if isinstance(inventories, dict):
        declared = catalog.get("inventory_counts", {})
        for inventory_name in ("psgsuite", "gam7", "gamadv_xtd3"):
            items = inventories.get(inventory_name)
            require(isinstance(items, list), f"source_inventory.{inventory_name} must be a list", errors)
            if not isinstance(items, list):
                continue
            require(
                declared.get(inventory_name) == len(items),
                f"inventory_counts.{inventory_name} must equal {len(items)}",
                errors,
            )
            for index, item in enumerate(items):
                where = f"source_inventory.{inventory_name}[{index}]"
                require(isinstance(item, dict), f"{where} must be an object", errors)
                if not isinstance(item, dict):
                    continue
                source_id = item.get("source_id")
                require(
                    isinstance(source_id, str) and bool(SOURCE_ID.match(source_id)),
                    f"{where}.source_id is invalid",
                    errors,
                )
                if not isinstance(source_id, str):
                    continue
                require(source_id not in seen_source_ids, f"duplicate source_id {source_id}", errors)
                seen_source_ids.add(source_id)
                disposition = item.get("disposition")
                require(disposition in SOURCE_DISPOSITIONS, f"{source_id}.disposition is invalid", errors)
                for field in ("command", "family", "source_url"):
                    require(bool(item.get(field)), f"{source_id}.{field} is required", errors)
                require(
                    isinstance(item.get("source_url"), str)
                    and bool(URL.match(item["source_url"])),
                    f"{source_id}.source_url must be HTTPS",
                    errors,
                )
                ids = item.get("capability_ids", [])
                require(isinstance(ids, list), f"{source_id}.capability_ids must be a list", errors)
                if disposition in {"mapped", "gamadv-specific"}:
                    require(bool(ids), f"{source_id} must map to a capability", errors)
                if isinstance(ids, list):
                    for capability_id in ids:
                        require(capability_id in capability_ids, f"{source_id} maps to unknown {capability_id}", errors)
                    if ids:
                        mapped_source_ids.add(source_id)

        if isinstance(baselines, dict):
            psg_counts = Counter(
                item.get("disposition") for item in inventories.get("psgsuite", [])
            )
            gam_counts = Counter(
                item.get("disposition") for item in inventories.get("gam7", [])
            )
            gamadv_counts = Counter(
                item.get("disposition") for item in inventories.get("gamadv_xtd3", [])
            )
            psg_baseline = baselines.get("psgsuite", {})
            gam_baseline = baselines.get("gam7", {})
            gamadv_baseline = baselines.get("gamadv_xtd3", {})
            require(
                psg_baseline.get("public_cmdlets") == len(inventories.get("psgsuite", [])),
                "PSGSuite public_cmdlets does not match inventory",
                errors,
            )
            require(
                psg_baseline.get("product_cmdlets") == psg_counts["mapped"],
                "PSGSuite product_cmdlets does not match mapped inventory",
                errors,
            )
            require(
                psg_baseline.get("non_product_cmdlets") == psg_counts["non-product"],
                "PSGSuite non_product_cmdlets does not match inventory",
                errors,
            )
            require(
                gam_baseline.get("documented_command_variants")
                == len(inventories.get("gam7", [])),
                "GAM7 documented_command_variants does not match inventory",
                errors,
            )
            require(
                gam_baseline.get("administrative_variants") == gam_counts["mapped"],
                "GAM7 administrative_variants does not match mapped inventory",
                errors,
            )
            require(
                gam_baseline.get("non_product_variants") == gam_counts["non-product"],
                "GAM7 non_product_variants does not match inventory",
                errors,
            )
            require(
                gamadv_baseline.get("legacy_only_variants_reviewed")
                == len(inventories.get("gamadv_xtd3", [])),
                "GAMADV legacy_only_variants_reviewed does not match inventory",
                errors,
            )
            require(
                gamadv_baseline.get("covered_by_gam7_variants")
                == gamadv_counts["covered-by-gam7"],
                "GAMADV covered_by_gam7_variants does not match inventory",
                errors,
            )
            require(
                gamadv_baseline.get("specific_variants")
                == gamadv_counts["gamadv-specific"],
                "GAMADV specific_variants does not match inventory",
                errors,
            )

    for capability in capabilities:
        if not isinstance(capability, dict):
            continue
        for source_id in capability.get("upstream", {}).get("source_ids", []):
            require(source_id in seen_source_ids, f"{capability.get('capability_id')} uses unknown source {source_id}", errors)
            require(source_id in mapped_source_ids, f"{source_id} is not mapped in source_inventory", errors)

    return errors


def _table(counter: Counter[str], first_header: str) -> list[str]:
    rows = [f"| {first_header} | Count |", "|---|---:|"]
    rows.extend(f"| {key} | {value} |" for key, value in sorted(counter.items()))
    return rows


def render_matrix(catalog: dict[str, Any]) -> str:
    capabilities = sorted(catalog["capabilities"], key=lambda item: item["capability_id"])
    inventory = catalog["source_inventory"]
    implementation = Counter(item["wgasuite"]["status"] for item in capabilities)
    parity = Counter(item["wgasuite"]["parity"] for item in capabilities)
    service = Counter(item["service"] for item in capabilities)
    action = Counter(item["action"] for item in capabilities)
    access = Counter(item["access"] for item in capabilities)
    release = Counter(item["roadmap"]["release"] for item in capabilities)

    lines = [
        "<!-- Generated by scripts/parity/validate_parity.py; do not edit directly. -->",
        "# Capability matrix",
        "",
        f"Catalog `{catalog['catalog_version']}`; retrieved `{catalog['retrieved_on']}`; "
        f"WGASuite baseline `{catalog['baselines']['wgasuite']['commit']}`.",
        "",
        "The canonical source is [`capabilities.yaml`](capabilities.yaml). "
        "Run `python scripts/parity/validate_parity.py --write-matrix` after changing it.",
        "",
        "## Coverage summary",
        "",
        f"- Canonical capabilities: **{len(capabilities)}**",
        f"- PSGSuite public cmdlets inventoried: **{len(inventory['psgsuite'])}**",
        f"- GAM7 documented command variants inventoried: **{len(inventory['gam7'])}**",
        f"- GAMADV-XTD3 legacy-only syntax variants reviewed: **{len(inventory['gamadv_xtd3'])}**",
        "",
        "### WGASuite implementation status",
        "",
        *_table(implementation, "Status"),
        "",
        "### Functional parity status",
        "",
        *_table(parity, "Parity"),
        "",
        "### Access classification",
        "",
        *_table(access, "Access"),
        "",
        "### Action coverage",
        "",
        *_table(action, "Action"),
        "",
        "### Roadmap release",
        "",
        *_table(release, "Release"),
        "",
        "### Service coverage",
        "",
        *_table(service, "Service"),
        "",
        "## Capabilities",
        "",
        "| Capability | Service | Action | Access | API feasibility | WGASuite | Parity | Roadmap |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in capabilities:
        google = item["google"]
        wg = item["wgasuite"]
        roadmap = item["roadmap"]
        lines.append(
            "| `{}` | {} | `{}` | {} | {} | {} | {} | [{}]({}) |".format(
                item["capability_id"],
                item["service"],
                item["action"],
                item["access"],
                google["feasibility"],
                wg["status"],
                wg["parity"],
                roadmap["epic"],
                roadmap["task_url"],
            )
        )
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-matrix",
        action="store_true",
        help="replace capability-matrix.md with the deterministic render",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        catalog = load_catalog()
        errors = validate(catalog)
    except ValidationError as exc:
        print(f"parity validation failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("parity validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    rendered = render_matrix(catalog)
    if args.write_matrix:
        MATRIX_PATH.write_text(rendered, encoding="utf-8")
    else:
        try:
            current = MATRIX_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            current = ""
        if current != rendered:
            print(
                "capability-matrix.md is stale; run "
                "`python scripts/parity/validate_parity.py --write-matrix`",
                file=sys.stderr,
            )
            return 1

    print(
        "Parity catalog valid: "
        f"{len(catalog['capabilities'])} capabilities, "
        f"{len(catalog['source_inventory']['psgsuite'])} PSGSuite cmdlets, "
        f"{len(catalog['source_inventory']['gam7'])} GAM7 variants, "
        f"{len(catalog['source_inventory']['gamadv_xtd3'])} GAMADV-XTD3 variants."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
