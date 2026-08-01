"""SignalCloud Content ABI, Asset Doctor, Pack Builder, and preview bridge.

Hot-reload bridge symbols are loaded lazily so ``python -m
 tools.asset_doctor.hot_reload_bridge`` does not import the module twice and
emit the runpy RuntimeWarning seen in A3a2.
"""

from .content_abi import (
    AssetDoctorReport,
    AssetIssue,
    AssetRecord,
    QuarantineReceipt,
    ensure_asset_envelope,
    list_quarantine_receipts,
    quarantine_invalid,
    repair_machine_paths,
    restore_quarantine_receipt,
    scan_content,
    write_asset_envelope,
    write_hot_reload_index,
    write_manifest_v2,
    write_report,
)
from .pack_builder import PackBuildResult, build_pack


def __getattr__(name: str):
    if name in {"HotReloadStageResult", "stage_preview_reload"}:
        from .hot_reload_bridge import HotReloadStageResult, stage_preview_reload
        return {
            "HotReloadStageResult": HotReloadStageResult,
            "stage_preview_reload": stage_preview_reload,
        }[name]
    if name in {"PackFinding", "PackInspectionResult", "PackInstallResult", "inspect_pack", "install_pack"}:
        from .pack_manager import (
            PackFinding, PackInspectionResult, PackInstallResult, inspect_pack, install_pack,
        )
        return {
            "PackFinding": PackFinding,
            "PackInspectionResult": PackInspectionResult,
            "PackInstallResult": PackInstallResult,
            "inspect_pack": inspect_pack,
            "install_pack": install_pack,
        }[name]
    raise AttributeError(name)


__all__ = [
    "AssetDoctorReport", "AssetIssue", "AssetRecord", "QuarantineReceipt",
    "ensure_asset_envelope", "list_quarantine_receipts", "quarantine_invalid",
    "repair_machine_paths", "restore_quarantine_receipt", "scan_content",
    "write_asset_envelope", "write_hot_reload_index", "write_manifest_v2", "write_report",
    "HotReloadStageResult", "stage_preview_reload", "PackBuildResult", "build_pack",
    "PackFinding", "PackInspectionResult", "PackInstallResult", "inspect_pack", "install_pack",
]
