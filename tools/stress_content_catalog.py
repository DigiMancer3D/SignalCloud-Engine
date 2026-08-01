#!/usr/bin/env python3
"""Build a forgiving StressLab content catalog from the real game manifest.

The catalog does not execute content. It records what the engine can instantiate
natively today and what the stress tester may represent with a safe proxy until
an engine factory for that category exists.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ENTRY_RE = re.compile(r"^([A-Za-z0-9_.-]+)\s*:\s*(\{.*\})\s*;\s*$")

NATIVE_ENTITY_IDS = {"hash_dog", "formless_shadow"}
NATIVE_WORLD_IDS = {
    "pivot_room", "pivot2_liminal_slice", "pivot3_portal_graph", "pivot5_lab",
    "pivot6_room_complex", "pivot7_threshold_gallery",
    "pivot8_submerged_boundary_lab", "pivot9_signal_range",
    "pivot11_scavenger_exchange",
}
NATIVE_KIOSK_IDS = {"pivot11_scavenger_exchange", "pivot13_ammo_tablet"}
NATIVE_WEAPON_IDS = {"service_pistol", "signal_prybar"}


@dataclass
class CatalogRecord:
    asset_id: str
    asset_type: str
    family: str
    pack: str
    relative_path: str
    category: str
    subtype: str
    representation: str
    runtime_support: str
    stress_spawn_policy: str
    enabled: bool
    sha256: str
    notes: str


def parse_udata(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    section = ""
    if not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("@"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            result.setdefault(section, {})
            continue
        match = ENTRY_RE.match(line)
        if not match:
            continue
        key, payload = match.groups()
        try:
            value = json.loads(payload)
        except json.JSONDecodeError:
            value = {"raw": payload}
        result.setdefault(section, {})[key] = value
    return result


def scalar(doc: dict[str, dict[str, Any]], *keys: tuple[str, str], default: str = "") -> str:
    for section, key in keys:
        value = doc.get(section, {}).get(key)
        if isinstance(value, dict):
            if "value" in value:
                return str(value["value"])
            if "name" in value:
                return str(value["name"])
    return default


def classify(row: dict[str, str], doc: dict[str, dict[str, Any]]) -> tuple[str, str, str, str, str, str]:
    asset_id = row.get("asset_id", "").strip()
    asset_type = row.get("asset_type", "").strip().lower()
    family = row.get("family", "").strip().lower()
    data_type = scalar(doc, ("header", "data_type"), default="").lower()
    asset_kind = scalar(doc, ("header", "asset_kind"), default="").lower()
    representation = scalar(doc, ("body", "representation"), default="")
    joined = " ".join((asset_id.lower(), asset_type, family, data_type, asset_kind, representation.lower()))

    if data_type == "pcp3_asset":
        pcp_kind = asset_kind or asset_type
        category_map = {
            "enemy": "enemy", "boss": "boss", "mini_boss": "mini_boss",
            "raid": "raid", "friendly": "friendly",
            "environment_object": "environment_object",
            "environment_theme": "environment_theme",
            "room": "room_set", "liquid": "water",
        }
        category = category_map.get(pcp_kind, "pcp3_asset")
        subtype = pcp_kind or asset_id
        support = "native_point_runtime"
        policy = "load_pcp3_layered_point_asset"
        notes = (
            "Loaded through the forgiving PCP3 cloud loader in the game, native stress tester, "
            "and native preview. Behavior, animation, and simulation attributes remain staged "
            "until a matching engine factory consumes them."
        )
        return category, subtype, representation, support, policy, notes

    # Manifest type is authoritative. Name tokens refine a type but do not
    # override renderer/rule records merely because they contain words such as
    # "pool" or "world".
    if asset_type == "renderer":
        category, subtype = "renderer_feature", asset_id
    elif asset_type == "rules":
        category, subtype = "rule", asset_id
    elif asset_type in {"entities", "entity", "enemy", "hostile"} or data_type == "combat_entity":
        if any(token in joined for token in ("mini_boss", "miniboss")):
            category = "mini_boss"
        elif re.search(r"(^|[_ -])boss($|[_ -])", joined):
            category = "boss"
        elif any(token in joined for token in ("friendly", "companion")):
            category = "friendly"
        else:
            category = "enemy"
        subtype = asset_id
    elif asset_type in {"world", "room", "rooms", "level"} or "world" in data_type:
        category, subtype = "room_set", asset_id
    elif asset_type in {"weapons", "weapon"}:
        category, subtype = "weapon", asset_id
    elif asset_type in {"economy", "proofs", "item", "items"}:
        if any(token in joined for token in ("kiosk", "tablet", "vendor", "exchange")):
            category = "kiosk"
        else:
            category = "item_or_economy"
        subtype = asset_id
    elif any(token in joined for token in ("portal", "threshold", "doorway")):
        category, subtype = "portal_or_threshold", asset_id
    elif any(token in joined for token in ("water", "flood", "poolroom")):
        category, subtype = "water", asset_id
    elif any(token in joined for token in ("kiosk", "tablet", "vendor", "exchange")):
        category, subtype = "kiosk", asset_id
    elif any(token in joined for token in ("pistol", "prybar", "rifle", "shotgun")):
        category, subtype = "weapon", asset_id
    else:
        category, subtype = "other", asset_id

    if category == "enemy" and asset_id in NATIVE_ENTITY_IDS:
        support = "native_runtime"
        policy = "spawn_real_engine_entity"
        notes = "Uses CombatSystem native entity kind and actual visual points."
    elif category == "room_set" and asset_id in NATIVE_WORLD_IDS:
        support = "native_runtime"
        policy = "build_real_liminal_level"
        notes = "Uses the current LiminalLevel/PointCloud implementation."
    elif category == "kiosk" and asset_id in NATIVE_KIOSK_IDS:
        support = "native_runtime"
        policy = "spawn_real_economy_visual"
        notes = "Uses current EconomySystem kiosk/pickup visuals."
    elif category == "weapon" and asset_id in NATIVE_WEAPON_IDS:
        support = "native_runtime"
        policy = "spawn_real_viewmodel_or_world_proxy"
        notes = "Uses current CombatSystem weapon/viewmodel implementation."
    elif category in {"renderer_feature", "rule", "portal_or_threshold", "water", "item_or_economy"}:
        support = "data_driven_ready"
        policy = "exercise_shared_system_when_referenced"
        notes = "Loaded by shared systems when the active room/scenario references it."
    elif category in {"enemy", "mini_boss", "boss", "friendly", "room_set", "kiosk", "weapon"}:
        support = "discovered_proxy_until_factory"
        policy = "safe_stress_proxy"
        notes = "Discovered automatically; full native behavior requires a registered engine factory."
    else:
        support = "catalog_only"
        policy = "measure_manifest_and_memory_only"
        notes = "Cataloged without execution."

    return category, subtype, representation, support, policy, notes


def build_catalog(root: Path) -> tuple[list[CatalogRecord], list[str]]:
    manifest = root / "content" / "manifest.csv"
    if not manifest.is_file():
        raise FileNotFoundError(f"Missing manifest: {manifest}")
    records: list[CatalogRecord] = []
    warnings: list[str] = []
    with manifest.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            enabled = row.get("enabled", "true").strip().lower() == "true"
            rel = row.get("relative_path", "").strip()
            doc = parse_udata(root / "content" / rel)
            category, subtype, representation, support, policy, notes = classify(row, doc)
            if not rel:
                warnings.append(f"Record {row.get('asset_id', '<unknown>')} has no relative_path")
            records.append(CatalogRecord(
                asset_id=row.get("asset_id", "").strip(),
                asset_type=row.get("asset_type", "").strip(),
                family=row.get("family", "").strip(),
                pack=row.get("pack", "").strip(),
                relative_path=rel,
                category=category,
                subtype=subtype,
                representation=representation,
                runtime_support=support,
                stress_spawn_policy=policy,
                enabled=enabled,
                sha256=row.get("sha256", "").strip(),
                notes=notes,
            ))
    return records, warnings


def write_catalog(root: Path, output_prefix: Path) -> None:
    records, warnings = build_catalog(root)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "signalcloud_stress_content_catalog_v1",
        "game_root": "<PROJECT_ROOT>",
        "manifest": "content/manifest.csv",
        "records": [asdict(record) for record in records],
        "warnings": warnings,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["catalog_sha256"] = hashlib.sha256(canonical).hexdigest()
    output_prefix.with_suffix(".json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with output_prefix.with_suffix(".csv").open("w", newline="", encoding="utf-8") as handle:
        fieldnames = list(asdict(records[0]).keys()) if records else ["asset_id"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))

    categories = Counter(record.category for record in records if record.enabled)
    support = Counter(record.runtime_support for record in records if record.enabled)
    lines = [
        "# SignalCloud Stress Content Catalog", "",
        f"Catalog hash: `{payload['catalog_sha256']}`", "",
        "## Enabled categories", "",
        "| Category | Count |", "|---|---:|",
    ]
    lines.extend(f"| {name} | {count} |" for name, count in sorted(categories.items()))
    lines += ["", "## Runtime support", "", "| Support | Count |", "|---|---:|"]
    lines.extend(f"| {name} | {count} |" for name, count in sorted(support.items()))
    lines += ["", "## Records", "", "| Asset | Category | Runtime support | Stress policy |", "|---|---|---|---|"]
    for record in records:
        if record.enabled:
            lines.append(f"| `{record.asset_id}` | {record.category} | {record.runtime_support} | {record.stress_spawn_policy} |")
    if warnings:
        lines += ["", "## Warnings", ""] + [f"- {warning}" for warning in warnings]
    output_prefix.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--output-prefix", default="reports/stress_content_catalog")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output_prefix)
    if not output.is_absolute():
        output = root / output
    write_catalog(root, output)
    print(output.with_suffix('.json'))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
