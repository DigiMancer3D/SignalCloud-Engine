from __future__ import annotations

import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from tools.asset_doctor.content_abi import (
    AssetDoctorReport,
    list_quarantine_receipts,
    quarantine_invalid,
    repair_machine_paths,
    restore_quarantine_receipt,
    scan_content,
    write_hot_reload_index,
    write_manifest_v2,
    write_report,
)
from tools.asset_doctor.hot_reload_bridge import read_status_summary, stage_preview_reload
from tools.asset_doctor.manifest_builder import build_manifest

from .context import ToolContext
from .ui import FlowBar, bind_responsive_wrap


@dataclass(slots=True)
class AssetDoctorSession:
    context: ToolContext
    frame: ttk.Frame
    report: AssetDoctorReport
    tree: ttk.Treeview
    summary: tk.StringVar
    hot_reload_summary: tk.StringVar
    quarantine_summary: tk.StringVar

    def refresh_auxiliary_status(self) -> None:
        status_data = read_status_summary(self.context.project_root)
        generated = int(status_data.get("generated_unix", 0) or 0)
        if generated:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(generated))
            self.hot_reload_summary.set(
                f"Latest protected preview stage: {stamp} · tx {status_data.get('transaction_id', '') or 'legacy'} · "
                f"{int(status_data.get('changed_count', 0) or 0)} changed "
                f"(SCUI {int(status_data.get('changed_scui_count', 0) or 0)}, "
                f"lights {int(status_data.get('changed_light_count', 0) or 0)}, "
                f"PCP3 {int(status_data.get('changed_pcp3_count', 0) or 0)}) · "
                f"{int(status_data.get('invalid_count', 0) or 0)} invalid"
            )
        else:
            self.hot_reload_summary.set("Latest protected preview stage: not created yet")
        receipts = list_quarantine_receipts(self.context.content_root)
        active = [receipt for receipt in receipts if not receipt.restored]
        self.quarantine_summary.set(
            f"Quarantine recovery: {len(active)} active receipt(s) · {len(receipts)} total"
        )

    def refresh(self) -> AssetDoctorReport:
        self.report = scan_content(self.context.content_root)
        self.summary.set(
            f"{len(self.report.records)} assets · {self.report.valid_count} valid · "
            f"{self.report.error_count} errors · {self.report.warning_count} warnings"
        )
        for item in self.tree.get_children():
            self.tree.delete(item)
        for issue in self.report.issues:
            self.tree.insert("", "end", values=(issue.severity.upper(), issue.code, issue.relative_path, issue.message))
        # The shared Studio X/Y viewport owns scrolling. Expand the issue table
        # vertically instead of adding a second dedicated vertical scrollbar.
        self.tree.configure(height=max(7, min(80, len(self.report.issues) + 1)))
        self.refresh_auxiliary_status()
        return self.report

    def write_indexes(self) -> None:
        build_manifest(self.context.content_root)
        write_manifest_v2(self.report, self.context.content_root / "manifest_v2.json")
        write_report(self.report, self.context.project_root / "reports" / "asset_doctor" / "latest.json")
        write_hot_reload_index(
            self.report,
            self.context.project_root,
            self.context.user_data_root / "studio" / "hot_reload_candidates.udata",
        )


def mount_asset_doctor_panel(
    parent: ttk.Frame,
    context: ToolContext,
    status: Callable[[str], None],
) -> AssetDoctorSession:
    frame = ttk.Frame(parent, padding=10)
    frame.pack(fill="both", expand=True)
    summary = tk.StringVar(value="Scanning content…")
    hot_reload_summary = tk.StringVar(value="Latest protected preview stage: checking…")
    quarantine_summary = tk.StringVar(value="Quarantine recovery: checking…")
    ttk.Label(frame, text="SIGNALCLOUD ASSET DOCTOR", font=("Sans", 14, "bold")).pack(anchor="w")
    description = ttk.Label(
        frame,
        text=(
            "Content ABI validation, portable-path repair, duplicate/dependency checks, protected "
            "preview reload, and reversible user/mod quarantine. Core assets are never moved automatically."
        ),
        justify="left",
        anchor="w",
    )
    description.pack(fill="x", anchor="w", pady=(2, 8))
    bind_responsive_wrap(description, frame, horizontal_margin=28, minimum=280)
    ttk.Label(frame, textvariable=summary).pack(anchor="w")
    ttk.Label(frame, textvariable=hot_reload_summary).pack(anchor="w")
    ttk.Label(frame, textvariable=quarantine_summary).pack(anchor="w", pady=(0, 8))

    body = ttk.Frame(frame)
    body.pack(fill="both", expand=True)
    tree = ttk.Treeview(body, columns=("severity", "code", "path", "message"), show="headings")
    for key, title, width in (
        ("severity", "Severity", 78), ("code", "Code", 170),
        ("path", "Asset", 300), ("message", "Finding", 420),
    ):
        tree.heading(key, text=title)
        tree.column(key, width=width, stretch=key in {"path", "message"})
    tree.pack(fill="both", expand=True)

    session = AssetDoctorSession(
        context, frame, AssetDoctorReport(), tree, summary, hot_reload_summary, quarantine_summary
    )

    buttons = FlowBar(frame, padding=(0, 5))
    buttons.pack(fill="x", pady=(8, 0))

    def scan() -> None:
        report = session.refresh()
        status(
            f"Asset Doctor scan: {len(report.records)} assets, "
            f"{report.error_count} errors, {report.warning_count} warnings"
        )

    def rebuild() -> None:
        session.refresh()
        session.write_indexes()
        session.refresh_auxiliary_status()
        status("Manifest v1/v2 and protected hot-reload index rebuilt")

    def repair_paths() -> None:
        warnings = [issue for issue in session.report.issues if issue.code == "asset.absolute-path"]
        if not warnings:
            status("No machine-specific asset paths require repair")
            return
        if not messagebox.askyesno(
            "Repair portable paths",
            f"Replace machine-specific paths in {len(warnings)} asset(s) with project-relative references?\n\n"
            "A normal file backup is not created because this operation writes only validated text assets.",
            parent=frame.winfo_toplevel(),
        ):
            return
        repaired = repair_machine_paths(context.content_root)
        session.refresh()
        session.write_indexes()
        status(f"Portable path repair completed for {len(repaired)} asset(s)")

    def stage_reload() -> None:
        session.refresh()
        result = stage_preview_reload(context.project_root)
        session.refresh_auxiliary_status()
        status(
            f"Protected preview stage {result.transaction_id}: {result.candidate_count} supported, "
            f"{result.changed_count} changed (SCUI {result.changed_scui_count}, "
            f"lights {result.changed_light_count}, PCP3 {result.changed_pcp3_count}), "
            f"{result.invalid_count} invalid"
        )

    def quarantine() -> None:
        invalid = sorted({i.relative_path for i in session.report.issues if i.severity == "error"})
        movable = [p for p in invalid if p.startswith(("user/", "mods/"))]
        if not movable:
            status("No invalid user/mod assets are eligible for quarantine")
            return
        if not messagebox.askyesno(
            "Quarantine invalid assets",
            f"Move {len(movable)} invalid user/mod asset(s) into content/quarantine?\n\n"
            "A recovery receipt will be created.",
            parent=frame.winfo_toplevel(),
        ):
            return
        moved = quarantine_invalid(session.report, context.content_root)
        session.refresh()
        session.write_indexes()
        status(f"Quarantined {len(moved)} invalid user/mod asset(s); recovery receipt created")

    def restore_latest() -> None:
        receipts = [item for item in list_quarantine_receipts(context.content_root) if not item.restored]
        if not receipts:
            status("No active quarantine receipt is available for recovery")
            return
        receipt = receipts[0]
        if not messagebox.askyesno(
            "Restore quarantined assets",
            f"Restore {len(receipt.entries)} asset(s) from the newest quarantine receipt?\n\n"
            "Recovery stops if an original path is already occupied or a stored hash changed.",
            parent=frame.winfo_toplevel(),
        ):
            return
        try:
            restored = restore_quarantine_receipt(context.content_root, receipt.receipt_path)
        except Exception as exc:
            messagebox.showerror("Quarantine recovery", str(exc), parent=frame.winfo_toplevel())
            status(f"Quarantine recovery blocked: {exc}")
            return
        session.refresh()
        session.write_indexes()
        status(f"Restored {len(restored)} quarantined user/mod asset(s)")

    for label, command in (
        ("Scan", scan),
        ("Rebuild manifests + index", rebuild),
        ("Repair portable paths", repair_paths),
        ("Stage preview reload", stage_reload),
        ("Quarantine invalid", quarantine),
        ("Restore newest", restore_latest),
    ):
        group = buttons.group()
        ttk.Button(group, text=label, command=command).pack()
    scan()
    return session
