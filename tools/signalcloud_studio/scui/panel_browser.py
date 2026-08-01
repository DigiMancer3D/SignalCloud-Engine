from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..context import ToolContext
from ..ui import FlowBar, bind_responsive_wrap
from .codec import load_scui
from .light_lab import mount_light_lab_panel
from .proof import mount_proof_panel
from .registry import ScuiPanelRegistry
from .tk_renderer import ScuiTkRenderer


class ScuiRegistryBrowser:
    def __init__(self, parent: ttk.Frame, context: ToolContext, status: Callable[[str], None]) -> None:
        self.parent = parent
        self.context = context
        self.status = status
        self.registry = ScuiPanelRegistry.load(context.project_root)
        self.frame = ttk.Frame(parent, padding=10)
        self.selection = tk.StringVar(value=self.registry.default_panel or (self.registry.keys()[0] if self.registry.keys() else ""))
        self.panel_host = ttk.LabelFrame(self.frame, text="Registered panel", padding=8)
        self._build()

    def _build(self) -> None:
        ttk.Label(self.frame, text="Authoring Lab Panel Registry", font=("Sans", 13, "bold")).pack(anchor="w")
        description = ttk.Label(
            self.frame,
            text="Select a trusted shipped SCUI surface. Registry paths remain inside the project root.",
            justify="left",
            anchor="w",
        )
        description.pack(fill="x", anchor="w", pady=(2, 8))
        bind_responsive_wrap(description, self.frame, horizontal_margin=28, minimum=280)
        row = ttk.Frame(self.frame)
        row.pack(fill="x")
        self.combo = ttk.Combobox(row, textvariable=self.selection, values=self.registry.keys(), state="readonly")
        self.combo.pack(fill="x", expand=True)
        actions = FlowBar(row, padding=(0, 4))
        actions.pack(fill="x")
        for label, command in (("Open selected", self.open_selected), ("Reload registry", self.reload)):
            group = actions.group()
            ttk.Button(group, text=label, command=command).pack()
        self.panel_host.pack(fill="both", expand=True, pady=(10, 0))
        if not self.registry.valid:
            self.status("SCUI registry has validation issues")

    def _clear(self) -> None:
        for child in self.panel_host.winfo_children():
            child.destroy()

    def reload(self) -> None:
        previous = self.selection.get()
        self.registry = ScuiPanelRegistry.load(self.context.project_root)
        keys = self.registry.keys()
        self.combo.configure(values=keys)
        self.selection.set(previous if previous in keys else (self.registry.default_panel or (keys[0] if keys else "")))
        self.status(f"Reloaded SCUI panel registry · {len(keys)} validated panels")

    def open_selected(self) -> None:
        key = self.selection.get()
        try:
            entry = self.registry.get(key)
        except KeyError:
            self.status(f"Unknown SCUI registry entry: {key}")
            return
        self._clear()
        if entry.panel_id == "light_lab.control_surface":
            mount_light_lab_panel(self.panel_host, self.context, self.status)
        elif entry.panel_id == "authoring_lab.project_selector":
            mount_proof_panel(self.panel_host, self.context.project_root, self.status)
        else:
            panel = load_scui(self.context.project_root / entry.relative_path)
            renderer = ScuiTkRenderer(self.panel_host, panel, on_status=self.status)
            renderer.frame.pack(fill="both", expand=True)
        self.status(f"Opened registered SCUI panel: {entry.label}")


def mount_registry_browser(parent: ttk.Frame, context: ToolContext, status: Callable[[str], None]) -> ScuiRegistryBrowser:
    browser = ScuiRegistryBrowser(parent, context, status)
    browser.frame.pack(fill="both", expand=True)
    return browser
