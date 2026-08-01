from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from tools.asset_doctor.pack_manager import (
    PackInspectionResult,
    PackInstallResult,
    inspect_pack,
    install_pack,
)

from .context import ToolContext
from .ui import FlowBar, bind_responsive_wrap


@dataclass(slots=True)
class PackManagerSession:
    context: ToolContext
    frame: ttk.Frame
    archive: tk.StringVar
    summary: tk.StringVar
    tree: ttk.Treeview
    last_inspection: PackInspectionResult | None = None
    last_install: PackInstallResult | None = None


def mount_pack_manager_panel(
    parent: ttk.Frame,
    context: ToolContext,
    status: Callable[[str], None],
) -> PackManagerSession:
    frame = ttk.Frame(parent, padding=12)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="SIGNALCLOUD PACK INSPECTOR / INSTALLER", font=("Sans", 14, "bold")).grid(
        row=0, column=0, columnspan=3, sticky="w"
    )
    description = ttk.Label(
        frame,
        text=(
            "Inspect a data-only .scpack.zip without extracting it, resolve asset dependencies and "
            "license declarations, verify every checksum, then install atomically into content/mods. "
            "Unsafe paths, scripts, symlinks, duplicate IDs, and unresolved dependencies are blocked."
        ),
        justify="left",
        anchor="w",
    )
    description.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(2, 10))
    bind_responsive_wrap(description, frame, horizontal_margin=28, minimum=280)

    archive = tk.StringVar(value="exports/packs")
    summary = tk.StringVar(value="Choose a .scpack.zip to inspect.")
    ttk.Label(frame, text="Pack archive").grid(row=2, column=0, sticky="w")
    ttk.Entry(frame, textvariable=archive).grid(row=2, column=1, sticky="ew", padx=(10, 6))

    def browse() -> None:
        selected = filedialog.askopenfilename(
            parent=frame.winfo_toplevel(),
            title="Choose SignalCloud content pack",
            initialdir=str(context.project_root / "exports" / "packs"),
            filetypes=(("SignalCloud content packs", "*.scpack.zip"), ("ZIP archives", "*.zip"), ("All files", "*")),
        )
        if selected:
            try:
                archive.set(str(Path(selected).resolve().relative_to(context.project_root)))
            except ValueError:
                archive.set(selected)

    ttk.Button(frame, text="Browse…", command=browse).grid(row=2, column=2, sticky="e")
    summary_label = ttk.Label(frame, textvariable=summary, justify="left", anchor="w")
    summary_label.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 6))
    bind_responsive_wrap(summary_label, frame, horizontal_margin=28, minimum=280)

    tree = ttk.Treeview(frame, columns=("severity", "code", "path", "finding"), show="headings", height=10)
    for key, title, width in (
        ("severity", "Severity", 80),
        ("code", "Code", 190),
        ("path", "Pack path", 300),
        ("finding", "Finding", 430),
    ):
        tree.heading(key, text=title)
        tree.column(key, width=width, stretch=key in {"path", "finding"})
    tree.grid(row=4, column=0, columnspan=3, sticky="nsew")

    session = PackManagerSession(context, frame, archive, summary, tree)

    def render(result: PackInspectionResult) -> None:
        for item in tree.get_children():
            tree.delete(item)
        for finding in result.findings:
            tree.insert("", "end", values=(finding.severity.upper(), finding.code, finding.path, finding.message))
        tree.configure(height=max(8, min(60, len(result.findings) + 2)))
        state = "INSTALLABLE" if result.installable else "BLOCKED"
        summary.set(
            f"{state}: {result.pack_id or '<unknown>'} {result.version} · "
            f"{result.asset_count} assets · {result.file_count} files · "
            f"{result.error_count} errors · {result.warning_count} warnings · "
            f"SHA-256 {result.archive_sha256[:16]}…"
        )

    def inspect() -> None:
        result = inspect_pack(context.project_root, archive.get().strip())
        session.last_inspection = result
        render(result)
        status(
            f"Pack inspection: {result.pack_id or '<unknown>'} · "
            f"{result.error_count} errors · {result.warning_count} warnings"
        )

    def install() -> None:
        result = inspect_pack(context.project_root, archive.get().strip())
        session.last_inspection = result
        render(result)
        if not result.installable:
            messagebox.showerror(
                "Pack installation blocked",
                "The pack did not pass inspection. Review the findings before installing.",
                parent=frame.winfo_toplevel(),
            )
            return
        if not messagebox.askyesno(
            "Install content pack",
            f"Install {result.display_name or result.pack_id} {result.version} into content/mods?\n\n"
            f"License: {result.license_id}\nAssets: {result.asset_count}\n"
            "The install is staged and rolled back if Content ABI validation fails.",
            parent=frame.winfo_toplevel(),
        ):
            return
        try:
            installed = install_pack(context.project_root, result.archive_path)
        except Exception as exc:
            messagebox.showerror("Pack installation", str(exc), parent=frame.winfo_toplevel())
            status(f"Pack installation blocked: {exc}")
            return
        session.last_install = installed
        summary.set(
            f"INSTALLED: {installed.pack_id} {installed.version} · {installed.installed_assets} assets · "
            f"transaction {installed.transaction_id} · {installed.target_path.relative_to(context.project_root)}"
        )
        status(f"Installed content pack {installed.pack_id} {installed.version}")
        messagebox.showinfo(
            "Pack installed",
            f"Installed to:\n{installed.target_path}\n\nReceipt:\n{installed.receipt_path}",
            parent=frame.winfo_toplevel(),
        )

    actions = FlowBar(frame, padding=(0, 5))
    actions.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 0))
    inspect_group = actions.group()
    ttk.Button(inspect_group, text="Inspect pack", command=inspect).pack()
    install_group = actions.group()
    ttk.Button(install_group, text="Install validated pack", command=install).pack()
    hint_group = actions.group()
    ttk.Label(hint_group, text="Install root: content/mods/<pack-id>/<version>").pack()

    frame.columnconfigure(1, weight=1)
    frame.rowconfigure(4, weight=1)
    return session
