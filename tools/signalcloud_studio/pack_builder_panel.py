from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk
from typing import Callable

from tools.asset_doctor.pack_builder import PackBuildResult, build_pack

from .context import ToolContext
from .ui import FlowBar, bind_responsive_wrap


@dataclass(slots=True)
class PackBuilderSession:
    context: ToolContext
    frame: ttk.Frame
    source: tk.StringVar
    pack_id: tk.StringVar
    display_name: tk.StringVar
    version: tk.StringVar
    license_id: tk.StringVar
    summary: tk.StringVar
    last_result: PackBuildResult | None = None


def mount_pack_builder_panel(
    parent: ttk.Frame,
    context: ToolContext,
    status: Callable[[str], None],
) -> PackBuilderSession:
    frame = ttk.Frame(parent, padding=12)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="SIGNALCLOUD PACK BUILDER", font=("Sans", 14, "bold")).grid(
        row=0, column=0, columnspan=3, sticky="w"
    )
    description = ttk.Label(
        frame,
        text=(
            "Build deterministic data-only .scpack.zip archives from validated content/user, "
            "content/mods, or content/starter directories. Executables, symlinks, unsafe paths, "
            "and invalid assets are rejected."
        ),
        justify="left",
        anchor="w",
    )
    description.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(2, 12))
    bind_responsive_wrap(description, frame, horizontal_margin=28, minimum=280)

    source = tk.StringVar(value="content/user")
    pack_id = tk.StringVar(value="user.authoring-pack")
    display_name = tk.StringVar(value="User Authoring Pack")
    version = tk.StringVar(value="0.1.0")
    license_id = tk.StringVar(value="LicenseRef-User-Provided")
    summary = tk.StringVar(value="Ready to validate and build a data-only content pack.")

    fields = (
        ("Source directory", source),
        ("Pack ID", pack_id),
        ("Display name", display_name),
        ("Version", version),
        ("License ID", license_id),
    )
    for row, (label, variable) in enumerate(fields, start=2):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=variable).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=3)

    ttk.Separator(frame).grid(row=7, column=0, columnspan=3, sticky="ew", pady=10)
    summary_label = ttk.Label(frame, textvariable=summary, justify="left", anchor="w")
    summary_label.grid(row=8, column=0, columnspan=3, sticky="ew")
    bind_responsive_wrap(summary_label, frame, horizontal_margin=28, minimum=280)

    session = PackBuilderSession(context, frame, source, pack_id, display_name, version, license_id, summary)

    def build() -> None:
        try:
            result = build_pack(
                context.project_root,
                source.get().strip(),
                pack_id=pack_id.get().strip(),
                display_name=display_name.get().strip(),
                version=version.get().strip(),
                license_id=license_id.get().strip(),
            )
        except Exception as exc:
            summary.set(f"Build blocked: {exc}")
            status(f"Pack Builder blocked: {exc}")
            messagebox.showerror("Pack Builder", str(exc), parent=frame.winfo_toplevel())
            return
        session.last_result = result
        summary.set(
            f"Built {result.output_path.name} · {result.asset_count} assets · "
            f"{result.file_count} files · SHA-256 {result.sha256[:16]}…"
        )
        status(f"Built data-only pack: {result.output_path.relative_to(context.project_root)}")
        messagebox.showinfo(
            "Pack built",
            f"Created:\n{result.output_path}\n\nAssets: {result.asset_count}\nSHA-256: {result.sha256}",
            parent=frame.winfo_toplevel(),
        )

    action_row = FlowBar(frame, padding=(0, 5))
    action_row.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(8, 0))
    build_group = action_row.group()
    ttk.Button(build_group, text="Validate and build pack", command=build).pack()
    output_group = action_row.group()
    ttk.Label(output_group, text="Output: exports/packs/<pack-id>-<version>.scpack.zip").pack()

    frame.columnconfigure(1, weight=1)
    frame.columnconfigure(2, weight=1)
    return session
