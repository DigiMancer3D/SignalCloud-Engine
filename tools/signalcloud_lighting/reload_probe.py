#!/usr/bin/env python3
"""Deterministically prove a changed .slight stages and compiles without mutating live content."""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from tools.asset_doctor.content_abi import parse_udata, scan_content, write_hot_reload_index
from tools.asset_doctor.hot_reload_bridge import stage_preview_reload


def run_probe(project_root: Path) -> dict[str, object]:
    root = project_root.resolve()
    source = root / "content/core/lights/authoring_lab_default.slight"
    if not source.is_file():
        raise FileNotFoundError(f"missing shipped light document: {source}")

    with tempfile.TemporaryDirectory(prefix="signalcloud-a4a2-light-probe-") as temp_name:
        probe_root = Path(temp_name) / "project"
        shutil.copytree(root / "content", probe_root / "content")
        report = scan_content(probe_root / "content")
        index_path = probe_root / "user_data/studio/hot_reload_candidates.udata"
        write_hot_reload_index(report, probe_root, index_path)

        probe_source = probe_root / "content/core/lights/authoring_lab_default.slight"
        payload = json.loads(probe_source.read_text(encoding="utf-8"))
        lights = payload.get("lights")
        if not isinstance(lights, list) or not lights or not isinstance(lights[0], dict):
            raise ValueError("shipped light document has no first light for the changed-light probe")
        before_value = float(lights[0].get("illuminosity_percent", 72.0))
        changed_value = before_value + 1.0 if before_value < 159.0 else before_value - 1.0
        lights[0]["illuminosity_percent"] = changed_value
        probe_source.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        result = stage_preview_reload(probe_root)
        sections, warnings = parse_udata(result.status_path)
        changed_entries = [
            section for name, section in sections.items()
            if name.startswith("asset.") and section.get("status") == "changed"
            and section.get("asset_type") == "light_set"
        ]
        if result.changed_light_count != 1 or len(changed_entries) != 1:
            raise AssertionError(
                f"expected exactly one changed light, got {result.changed_light_count} and {len(changed_entries)} entries"
            )
        compiled_relative = str(changed_entries[0].get("compiled_runtime_path", ""))
        compiled = (probe_root / compiled_relative).resolve()
        compiled.relative_to(probe_root.resolve())
        if not compiled.is_file():
            raise AssertionError("changed-light probe did not produce a compiled native runtime")
        compiled_text = compiled.read_text(encoding="utf-8")
        expected_line = f"illuminosity_percent: {json.dumps(changed_value)};"
        if expected_line not in compiled_text:
            raise AssertionError("compiled changed-light runtime did not contain the changed Illuminosity value")

        return {
            "schema": "signalcloud_a4a2_changed_light_probe_v1",
            "status": "PASS",
            "transaction_id": result.transaction_id,
            "changed_light_count": result.changed_light_count,
            "changed_scui_count": result.changed_scui_count,
            "changed_pcp3_count": result.changed_pcp3_count,
            "invalid_count": result.invalid_count,
            "before_illuminosity_percent": before_value,
            "changed_illuminosity_percent": changed_value,
            "compiled_runtime_path": compiled_relative,
            "parse_warning_count": len(warnings),
            "live_content_modified": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--report", type=Path, default=Path("reports/a4a2_changed_light_probe.json"))
    args = parser.parse_args()
    root = args.project_root.resolve()
    result = run_probe(root)
    report_path = args.report if args.report.is_absolute() else root / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "A4a2 changed-light probe: PASS | "
        f"lights {result['changed_light_count']} | invalid {result['invalid_count']} | "
        f"tx {result['transaction_id']} | live content unchanged"
    )
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
