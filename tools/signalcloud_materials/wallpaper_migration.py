#!/usr/bin/env python3
"""Migrate only untouched A5a2 managed wallpaper defaults to A5a2r2."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from tools.asset_doctor.content_abi import write_asset_envelope

OLD_PATTERN = {
    "mode": "wallpaper_breakup",
    "primary_spacing": 3.4,
    "secondary_spacing": 2.2,
    "breakup_scale": 4.6,
    "breakup_strength": 0.44,
    "displacement_weight": 0.035,
    "color_weight": 0.48,
    "line_width": 0.12,
}
USER_WALL = Path("content/user/materials/reception_tape/office_wallpaper.jmap")
CORE_WALL = Path("content/core/materials/office_wallpaper.jmap")


def _same_default(value: Any, expected: Any) -> bool:
    if isinstance(expected, float):
        try:
            return abs(float(value) - expected) <= 1e-6
        except (TypeError, ValueError):
            return False
    return value == expected


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def migrate_managed_wallpaper(project_root: Path) -> str:
    root = Path(project_root).resolve()
    user_path = root / USER_WALL
    if not user_path.is_file():
        return "absent"
    payload = json.loads(user_path.read_text(encoding="utf-8"))
    pattern = payload.get("pattern")
    if not isinstance(pattern, dict) or not all(_same_default(pattern.get(key), value) for key, value in OLD_PATTERN.items()):
        return "preserved-custom"

    core = json.loads((root / CORE_WALL).read_text(encoding="utf-8"))
    payload["pattern"] = dict(core["pattern"])
    payload.setdefault("jitter", {})["runtime_amplitude"] = core["jitter"]["runtime_amplitude"]
    payload.setdefault("palette", {})["variation"] = core["palette"]["variation"]
    extensions = payload.setdefault("extensions", {})
    extensions["a5a2r2_migrated_from"] = "untouched-a5a2-default"
    extensions["surface_intent"] = core["extensions"]["surface_intent"]
    extensions["wallpaper_variant"] = core["extensions"]["wallpaper_variant"]
    _atomic_json(user_path, payload)
    write_asset_envelope(
        root / "content",
        user_path,
        asset_id=str(payload["asset_id"]),
        asset_type="jitter_map",
        family="materials",
        pack="user",
        license_id="LicenseRef-SignalCloud-User-Authored",
        hot_reload="authoring-only",
    )
    return "migrated"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root", nargs="?", default=".")
    args = parser.parse_args()
    result = migrate_managed_wallpaper(Path(args.project_root))
    if result == "migrated":
        print("Migrated untouched managed wallpaper from A5a2 bands to A5a2r2 legacy grain.")
    elif result == "preserved-custom":
        print("Preserved custom managed wallpaper settings.")
    else:
        print("Managed wallpaper migration: no user wallpaper copy present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
