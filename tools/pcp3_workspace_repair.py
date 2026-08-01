#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.pcp3.editor_branch2r3r1 import sanitize_workspace_data


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair or reset Point Cloud Paint++ viewport memory.")
    parser.add_argument("root", type=Path)
    parser.add_argument("--reset", action="store_true", help="Archive and remove all workspace memory.")
    args = parser.parse_args()
    root = args.root.resolve()
    path = root / "config" / "pcp3_workspace.json"
    archive = root / "user_data" / "pcp3" / "workspace_archive"
    archive.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    if not path.exists():
        print("No PCP3 workspace file exists; clean defaults will be used.")
        return 0
    backup = archive / f"pcp3_workspace_{'reset' if args.reset else 'repair'}_{timestamp}.json"
    backup.write_bytes(path.read_bytes())
    if args.reset:
        path.unlink(missing_ok=True)
        print(f"Archived workspace to: {backup}")
        print("Workspace memory reset. The next launch will use safe defaults.")
        return 0
    try:
        original = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        original = {}
    repaired, reasons = sanitize_workspace_data(original)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(repaired, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    print(f"Archived workspace to: {backup}")
    if reasons:
        print("Repaired unsafe viewport memory:")
        for reason in reasons:
            print(f"  - {reason}")
    else:
        print("Workspace values were already within safety bounds; schema metadata was refreshed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
