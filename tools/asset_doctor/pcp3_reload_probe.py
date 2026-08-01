#!/usr/bin/env python3
"""Toggle the shipped A3 PCP3 marker and stage a protected native reload proof."""
from __future__ import annotations

import argparse
from pathlib import Path

from tools.asset_doctor.content_abi import scan_content, write_hot_reload_index
from tools.asset_doctor.hot_reload_bridge import stage_preview_reload
from tools.pcp3.io import export_asset, load_project

MARKER_RELATIVE = Path(
    "content/pcp3_assets/environment_object/a3_preview_marker/a3_preview_marker.pcp3"
)


def toggle_marker(project_root: Path) -> tuple[str, str]:
    root = Path(project_root).resolve()
    project = root / MARKER_RELATIVE
    if not project.is_file():
        raise FileNotFoundError(f"A3 preview marker is missing: {MARKER_RELATIVE}")
    document = load_project(project)
    previous = str(document.metadata.get("a3_reload_color", "green"))
    next_color = "cyan" if previous != "cyan" else "green"
    rgba = (0.20, 0.95, 1.0, 0.95) if next_color == "cyan" else (0.28, 1.0, 0.48, 0.95)
    for point in document.points:
        point.r, point.g, point.b, point.a = rgba
    document.metadata["a3_reload_color"] = next_color
    document.metadata["a3_reload_probe"] = "protected-pcp3-preview"
    export_asset(document, root, project_path=project, editor_name="SignalCloud Alpha A3a3 reload probe")
    staged = stage_preview_reload(root)
    if staged.changed_pcp3_count < 1 or staged.invalid_count:
        raise RuntimeError("PCP3 marker changed but could not be staged as a valid protected preview")

    # The acceptance probe is intentionally repeatable. Advance only the
    # protected comparison baseline after the transaction has been staged;
    # the already-written latest status remains available for native F9.
    refreshed = scan_content(root / "content")
    if refreshed.error_count:
        raise RuntimeError("PCP3 marker staged, but the refreshed Content ABI baseline is invalid")
    write_hot_reload_index(
        refreshed, root, root / "user_data/studio/hot_reload_candidates.udata"
    )
    return next_color, staged.transaction_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Toggle and stage the A3 protected PCP3 preview marker")
    parser.add_argument("project_root", nargs="?", default=".")
    args = parser.parse_args()
    color, transaction_id = toggle_marker(Path(args.project_root))
    print(f"A3 PCP3 preview marker changed to {color}")
    print(f"Protected preview transaction: {transaction_id}")
    print("Open an authoring SCUI in Reception Tape and press F9 to apply the staged PCP3 reload.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
