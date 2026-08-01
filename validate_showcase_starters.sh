#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
ROOT="$SC_PROJECT_ROOT"
PYTHON="$SC_PYTHON"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
cd "$ROOT"
exec "$PYTHON" - "$ROOT" <<'PY'
from pathlib import Path
import sys

from tools.asset_doctor.content_abi import scan_content
from tools.pcp3.io import read_cloud
from tools.signalcloud_showcase.catalog import scan_catalog
from tools.signalcloud_showcase.model import PhysicsProfile, VisualizationProfile
from tools.signalcloud_showcase.simulation import run_test

root = Path(sys.argv[1]).resolve()
entries = [entry for entry in scan_catalog(root) if entry.pack == "starter"]
if len(entries) != 10:
    raise SystemExit(f"Expected 10 A7a2 Showcase starters, found {len(entries)}")
counts = {"architecture": 0, "systems": 0}
all_tests = ("drop", "bounce", "slide", "throw", "break")
for entry in entries:
    counts[entry.category] = counts.get(entry.category, 0) + 1
    directory = entry.directory
    cloud = directory / f"{entry.asset_id}.pcp3cloud"
    physics = directory / f"{entry.asset_id}.scphysics"
    visualization = directory / f"{entry.asset_id}.scshowcase"
    if not cloud.is_file() or not physics.is_file() or not visualization.is_file():
        raise SystemExit(f"Missing A7a2 starter files for {entry.asset_id}")
    points, digest = read_cloud(cloud)
    if not points or not digest:
        raise SystemExit(f"Empty or invalid starter cloud: {cloud}")
    profile = PhysicsProfile.load(physics)
    view = VisualizationProfile.load(visualization)
    signatures = {run_test(profile, name).signature for name in all_tests}
    if len(signatures) != len(all_tests):
        raise SystemExit(f"Non-distinct deterministic Showcase results for {entry.asset_id}")
    if min(profile.collision_half_x, profile.collision_half_y, profile.collision_half_z) <= 0.01:
        raise SystemExit(f"Invalid fitted collision bounds for {entry.asset_id}")
    print(
        f"Showcase starter: {entry.asset_id} | pack {entry.category} | points {len(points)} | "
        f"shape {profile.shape} | view {view.view_mode} | tests {len(all_tests)} | PASS"
    )
if counts.get("architecture") != 5 or counts.get("systems") != 5:
    raise SystemExit(f"Starter catalog split mismatch: {counts}")
report = scan_content(root / "content" / "starter")
if (len(report.records), report.valid_count, report.error_count, report.warning_count) != (80, 80, 0, 0):
    raise SystemExit(
        f"Starter Asset Doctor mismatch: records {len(report.records)} valid {report.valid_count} "
        f"errors {report.error_count} warnings {report.warning_count}"
    )
print("SignalCloud A7 Showcase catalog plus A8 Tupd starter content validation PASS")
PY
