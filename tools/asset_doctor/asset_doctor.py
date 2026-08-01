#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.asset_doctor.content_abi import (
    list_quarantine_receipts,
    quarantine_invalid,
    repair_machine_paths,
    restore_quarantine_receipt,
    scan_content,
    write_hot_reload_index,
    write_manifest_v2,
    write_report,
)
from tools.asset_doctor.manifest_builder import build_manifest


def run(
    project_root: Path,
    *,
    quarantine: bool = False,
    repair_paths: bool = False,
    restore_receipt: str = "",
) -> int:
    root = project_root.resolve()
    content = root / "content"
    if repair_paths:
        repaired = repair_machine_paths(content)
        print(f"Portable path repair: {len(repaired)} asset(s)")
        for relative in repaired:
            print(f"  repaired: {relative}")
    if restore_receipt:
        receipt = Path(restore_receipt)
        if not receipt.is_absolute():
            receipt = content / "quarantine" / receipt
        restored = restore_quarantine_receipt(content, receipt)
        print(f"Restored from quarantine: {len(restored)} asset(s)")
        for relative in restored:
            print(f"  restored: {relative}")

    report = scan_content(content)
    if quarantine:
        quarantine_invalid(report, content)
        report = scan_content(content)
    build_manifest(content)
    write_manifest_v2(report, content / "manifest_v2.json")
    write_report(report, root / "reports" / "asset_doctor" / "latest.json")
    write_hot_reload_index(report, root, root / "user_data" / "studio" / "hot_reload_candidates.udata")
    print(
        f"Asset Doctor: {len(report.records)} assets | {report.valid_count} valid | "
        f"{report.error_count} errors | {report.warning_count} warnings"
    )
    if quarantine:
        print(f"Quarantined: {len(report.quarantined)}")
    receipts = list_quarantine_receipts(content)
    active = sum(not receipt.restored for receipt in receipts)
    if receipts:
        print(f"Quarantine receipts: {len(receipts)} total | {active} active")
    return 1 if report.error_count else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SignalCloud Content ABI / Asset Doctor")
    parser.add_argument("project_root", nargs="?", default=".")
    parser.add_argument("--quarantine", action="store_true", help="move invalid user/mod assets into content/quarantine")
    parser.add_argument("--repair-paths", action="store_true", help="replace machine-specific paths with portable project references")
    parser.add_argument("--restore-receipt", default="", help="restore a quarantine receipt path relative to content/quarantine")
    parser.add_argument("--allow-errors", action="store_true", help="report errors without returning a failing status")
    args = parser.parse_args()
    code = run(
        Path(args.project_root),
        quarantine=args.quarantine,
        repair_paths=args.repair_paths,
        restore_receipt=args.restore_receipt,
    )
    return 0 if args.allow_errors else code


if __name__ == "__main__":
    raise SystemExit(main())
