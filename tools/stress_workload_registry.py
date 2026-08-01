#!/usr/bin/env python3
"""Build a deterministic, data-only registry of stress-test workload categories."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

try:
    from tools.stress_content_catalog import build_catalog
except ModuleNotFoundError:  # direct tools/ script launch
    from stress_content_catalog import build_catalog


def _feature_channel(record) -> str:
    path = record.relative_path.lower()
    kind = record.asset_type.lower()
    family = record.family.lower()
    joined = " ".join((path, kind, family, record.category.lower()))
    for token, channel in (
        ("light", "lights"),
        ("material", "materials"),
        ("jmap", "materials"),
        ("texgraph", "materials"),
        ("audio", "sound_ripples"),
        ("playbook", "playbook_evaluations"),
        ("tupd", "tupd_test_objects"),
        ("scui", "scui_panels"),
        ("showcase", "showcase_objects"),
        ("pcp3", "pcp3_assets"),
        ("font", "font_glyph_workloads"),
    ):
        if token in joined:
            return channel
    return f"content.{record.category}"


def build_registry(root: Path) -> dict:
    records, warnings = build_catalog(root)
    enabled = [record for record in records if record.enabled]
    categories = Counter(record.category for record in enabled)
    channels = Counter(_feature_channel(record) for record in enabled)
    payload = {
        "schema": "signalcloud_stress_workload_registry_v1",
        "ruleset_id": "signalcloud-alpha-a9-ruleset-1",
        "project_root": "<PROJECT_ROOT>",
        "manifest": "content/manifest.csv",
        "enabled_asset_count": len(enabled),
        "category_counts": dict(sorted(categories.items())),
        "feature_channels": dict(sorted(channels.items())),
        "warnings": warnings,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["registry_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def write_registry(root: Path) -> tuple[Path, Path]:
    payload = build_registry(root)
    report = root / "reports" / "stress_workload_registry.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    profile = root / "user_data" / "machine_profiles" / "workload_registry.udata"
    profile.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "@udata 1", "", "[header]",
        'schema_name: "signalcloud_stress_workload_registry";',
        "schema_major: 1;",
        'ruleset_id: "signalcloud-alpha-a9-ruleset-1";',
        f'registry_sha256: "{payload["registry_sha256"]}";',
        f'enabled_asset_count: {payload["enabled_asset_count"]};',
        "", "[feature_channels]",
    ]
    for name, count in payload["feature_channels"].items():
        safe = name.replace(".", "_").replace("-", "_")
        lines.append(f"{safe}: {count};")
    lines += ["", "[content_categories]"]
    for name, count in payload["category_counts"].items():
        safe = name.replace(".", "_").replace("-", "_")
        lines.append(f"{safe}: {count};")
    lines += ["", "[privacy]", "contains_private_paths: false;", 'project_root: "<PROJECT_ROOT>";', ""]
    temporary = profile.with_suffix(profile.suffix + ".tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    temporary.replace(profile)
    return report, profile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    report, profile = write_registry(Path(args.root).resolve())
    print(report)
    print(profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
