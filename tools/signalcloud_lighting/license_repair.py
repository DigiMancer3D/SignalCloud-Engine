#!/usr/bin/env python3
"""Repair deterministic ABI envelopes for user-authored SignalCloud light exports."""
from __future__ import annotations

import argparse
from pathlib import Path

from tools.asset_doctor.content_abi import write_asset_envelope
from tools.signalcloud_lighting.exporter import USER_EXPORT_LICENSE


def repair_user_light_envelopes(root: Path) -> list[Path]:
    root = root.resolve()
    content_root = root / "content"
    repaired: list[Path] = []
    user_lights = content_root / "user" / "lights"
    if not user_lights.is_dir():
        return repaired
    for asset in sorted(user_lights.glob("*.sclight")):
        envelope = write_asset_envelope(
            content_root,
            asset,
            license_id=USER_EXPORT_LICENSE,
            pack="user",
            hot_reload="authoring-only",
        )
        repaired.append(envelope)
    return repaired


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    args = parser.parse_args()
    repaired = repair_user_light_envelopes(args.root)
    if repaired:
        for path in repaired:
            print(f"Repaired user light envelope: {path}")
    else:
        print("User light envelope repair: no exported .sclight files found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
