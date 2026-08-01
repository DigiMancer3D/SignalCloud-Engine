from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from .asset_doctor_panel import mount_asset_doctor_panel
from .context import ToolContext
from .documents import DocumentContextStore, StudioDocumentContext
from .pack_builder_panel import mount_pack_builder_panel
from .pack_manager_panel import mount_pack_manager_panel
from .plugin_api import PluginCatalog, PluginInfo
from .scui.light_lab import mount_light_lab_panel
from .scui.panel_browser import mount_registry_browser
from .scui.proof import mount_proof_panel
from .ui import AxisSwitchViewport, FlowBar, bind_responsive_wrap


@dataclass(frozen=True, slots=True)
class HostToolRow:
    key: str
    display_name: str
    category: str
    description: str
    state_text: str


class StudioHostModel:
    """Display-only model kept independent from Tk for deterministic tests."""

    def __init__(self, catalog: PluginCatalog) -> None:
        self.catalog = catalog

    def rows(self) -> tuple[HostToolRow, ...]:
        return tuple(
            HostToolRow(
                info.key,
                info.display_name,
                info.category,
                info.description,
                "Dock-ready" if info.can_embed else "Standalone bridge",
            )
            for info in self.catalog.infos()
        )

    @staticmethod
    def context_summary(context: StudioDocumentContext) -> str:
        if not context.active_document:
            return "No shared document selected"
        owner = context.owner_tool or "unowned"
        dirty = " · unsaved changes" if context.dirty else ""
        return f"{context.active_document} · {owner} · revision {context.revision}{dirty}"


class SignalCloudStudioHost(tk.Tk):
    """Canonical responsive Studio host for standalone and embedded tools."""

    ACTION_GROUPS = (
        ("home", "Home"),
        ("tools", "Tool launch"),
        ("scui", "SCUI pages"),
        ("content", "Content tools"),
    )

    def __init__(
        self,
        context: ToolContext,
        catalog: PluginCatalog,
        *,
        process_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
    ) -> None:
        super().__init__()
        self.context = context
        self.catalog = catalog
        self.model = StudioHostModel(catalog)
        self.process_factory = process_factory
        self.store = context.document_store or DocumentContextStore.for_project(context.project_root)
        self.tool_by_item: dict[str, PluginInfo] = {}
        self.selected_key = tk.StringVar(value="")
        self.context_text = tk.StringVar(value="")
        self.status_text = tk.StringVar(value="Ready")
        self.action_summary = tk.StringVar(
            value="Choose an action tab. Embedded pages stay inside the scrollable work area."
        )
        self.active_embedded = None
        self.active_action_group = "home"
        self.action_tab_buttons: dict[str, ttk.Button] = {}
        self.open_button: ttk.Button | None = None

        self.title("SignalCloud Studio — Tool Host")
        self.geometry("1180x760")
        self.minsize(780, 520)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build_ui()
        self.refresh_context()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(14, 10, 14, 5))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="SIGNALCLOUD STUDIO", font=("Sans", 18, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text="Canonical tool switcher · shared document context · responsive authoring host",
        ).pack(anchor="w")

        context_bar = ttk.LabelFrame(self, text="Shared document", padding=(10, 5))
        context_bar.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 7))
        context_bar.columnconfigure(0, weight=1)
        context_label = ttk.Label(context_bar, textvariable=self.context_text, justify="left")
        context_label.grid(row=0, column=0, sticky="ew")
        bind_responsive_wrap(context_label, context_bar, horizontal_margin=130, minimum=260)
        ttk.Button(context_bar, text="Refresh", command=self.refresh_context).grid(
            row=0, column=1, sticky="e", padx=(8, 0)
        )

        self.main_pane = ttk.Panedwindow(self, orient="horizontal")
        main = self.main_pane
        main.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 7))

        sidebar = ttk.Frame(main, padding=(7, 7, 9, 7))
        work = ttk.Frame(main, padding=(9, 7, 0, 0))
        main.add(sidebar, weight=1)
        main.add(work, weight=4)

        ttk.Label(sidebar, text="Studio tools", font=("Sans", 11, "bold")).pack(anchor="w", pady=(0, 6))
        # A single tree column prevents the old Host-mode column from consuming
        # narrow sidebar space and clipping both headings and tool names.
        self.tree = ttk.Treeview(sidebar, show="tree", height=14)
        self.tree.column("#0", width=220, minwidth=150, stretch=True)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda _event: self.open_selected())

        categories: dict[str, str] = {}
        for row in self.model.rows():
            parent = categories.get(row.category)
            if parent is None:
                parent = self.tree.insert("", "end", text=row.category, open=True)
                categories[row.category] = parent
            item = self.tree.insert(parent, "end", text=row.display_name)
            self.tool_by_item[item] = self.catalog.get(row.key)  # type: ignore[assignment]

        work.columnconfigure(0, weight=1)
        work.rowconfigure(1, weight=1)

        self.action_header = ttk.LabelFrame(work, text="Studio action tabs", padding=(6, 4))
        self.action_header.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        self.tab_bar = FlowBar(self.action_header, padding=(2, 1))
        self.tab_bar.pack(fill="x")
        for key, label in self.ACTION_GROUPS:
            group = self.tab_bar.group()
            button = ttk.Button(group, text=label, command=lambda item=key: self.select_action_group(item))
            button.pack()
            self.action_tab_buttons[key] = button

        summary_label = ttk.Label(
            self.action_header,
            textvariable=self.action_summary,
            justify="left",
            anchor="w",
        )
        summary_label.pack(fill="x", padx=5, pady=(2, 1))
        bind_responsive_wrap(summary_label, self.action_header, horizontal_margin=28, minimum=260)

        self.action_bar = FlowBar(self.action_header, padding=(2, 1))
        self.action_bar.pack(fill="x")

        self.viewport = AxisSwitchViewport(
            work,
            minimum_content_width=760,
            minimum_content_height=430,
        )
        self.viewport.grid(row=1, column=0, sticky="nsew")
        self.viewport.content.columnconfigure(0, weight=1)
        self.viewport.content.rowconfigure(0, weight=1)

        self.host_box = ttk.LabelFrame(self.viewport.content, text="Work area host", padding=12)
        self.host_box.grid(row=0, column=0, sticky="nsew", padx=(0, 2), pady=(0, 2))
        self._show_home_surface()
        self.select_action_group("home")

        # The footer is outside the paned window and outside the scrollable
        # viewport, so mounted content can never displace or hide it.
        self.footer = ttk.Frame(self, padding=(12, 2, 12, 8))
        footer = self.footer
        footer.grid(row=3, column=0, sticky="ew")
        ttk.Separator(footer).pack(fill="x", pady=(0, 4))
        ttk.Label(footer, textvariable=self.status_text, anchor="w").pack(fill="x")

    def _flow_button(self, text: str, command: Callable[[], None], *, enabled: bool = True) -> ttk.Button:
        group = self.action_bar.group()
        button = ttk.Button(group, text=text, command=command, state="normal" if enabled else "disabled")
        button.pack()
        return button

    def select_action_group(self, key: str) -> None:
        labels = dict(self.ACTION_GROUPS)
        if key not in labels:
            raise KeyError(key)
        self.active_action_group = key
        for item_key, button in self.action_tab_buttons.items():
            label = labels[item_key]
            button.configure(text=f"▶ {label}" if item_key == key else label)

        self.action_bar.clear()
        self.open_button = None
        if key == "home":
            self.action_summary.set(
                "Home keeps the work area compact. Use the tabs for launch actions, SCUI pages, or content tools."
            )
            self._flow_button("Show Studio home", self._show_home_surface)
            self._flow_button("Refresh shared document", self.refresh_context)
        elif key == "tools":
            info = self._selected_info()
            self.action_summary.set(
                "Launch inherited authoring tools in managed windows. Select a tool in the sidebar for details."
            )
            self.open_button = self._flow_button(
                "Open selected tool", self.open_selected, enabled=info is not None
            )
            self._flow_button("Open PCP3", lambda: self.open_tool("pcp3"))
            self._flow_button("Open Light Lab", lambda: self.open_tool("light-lab"))
            self._flow_button("Open Jitter & Material Lab", lambda: self.open_tool("jitter-texture-lab"))
        elif key == "scui":
            self.action_summary.set(
                "Open trusted declarative SCUI pages inside the shared Studio viewport."
            )
            self._flow_button("Open SCUI Registry", self.open_scui_registry)
            self._flow_button("Open SCUI Proof", self.open_scui_proof)
            self._flow_button("Open Light Lab SCUI", self.open_light_lab_scui)
        else:
            self.action_summary.set(
                "Inspect Content ABI health or build deterministic data-only content packs."
            )
            self._flow_button("Open Asset Doctor", self.open_asset_doctor)
            self._flow_button("Open Pack Builder", self.open_pack_builder)
            self._flow_button("Inspect / install pack", self.open_pack_manager)
        self.action_bar.after_idle(self.action_bar._schedule_reflow)

    def _clear_host_surface(self, title: str = "Work area host") -> None:
        for child in self.host_box.winfo_children():
            child.destroy()
        self.host_box.configure(text=title)
        self.active_embedded = None
        self.viewport.reset(axis="x")
        self.viewport.after_idle(self.viewport.refresh_layout)

    def _show_home_surface(self) -> None:
        self._clear_host_surface("Studio home")
        home = ttk.Frame(self.host_box, padding=16)
        home.pack(fill="both", expand=True)
        title = ttk.Label(home, text="SignalCloud Studio work area", font=("Sans", 15, "bold"))
        title.pack(anchor="w")
        text = ttk.Label(
            home,
            text=(
                "Choose an action tab above. Embedded SCUI and content pages mount here. "
                "The X/Y controls below use one horizontal scrollbar for either direction, "
                "and the fixed footer remains visible while content scrolls."
            ),
            justify="left",
            anchor="nw",
        )
        text.pack(fill="x", pady=(8, 0))
        bind_responsive_wrap(text, home, horizontal_margin=36, minimum=280)
        self.status_text.set("Studio home ready")

    def open_pack_builder(self) -> None:
        """Mount the deterministic data-only Pack Builder workspace."""
        try:
            self._clear_host_surface("Pack Builder")
            self.active_embedded = mount_pack_builder_panel(
                self.host_box, self.context, self.status_text.set
            )
            self.status_text.set("Mounted data-only SignalCloud Pack Builder")
            self.viewport.after_idle(self.viewport.refresh_layout)
        except Exception as exc:  # defensive UI boundary
            self._show_mount_error("Pack Builder", exc)

    def open_pack_manager(self) -> None:
        """Mount the validated pack inspection and atomic installation workspace."""
        try:
            self._clear_host_surface("Pack Inspector / Installer")
            self.active_embedded = mount_pack_manager_panel(
                self.host_box, self.context, self.status_text.set
            )
            self.status_text.set("Mounted SignalCloud Pack Inspector / Installer")
            self.viewport.after_idle(self.viewport.refresh_layout)
        except Exception as exc:  # defensive UI boundary
            self._show_mount_error("Pack Inspector / Installer", exc)

    def open_asset_doctor(self) -> None:
        """Mount the Content ABI / Asset Doctor workspace."""
        try:
            self._clear_host_surface("Asset Doctor")
            self.active_embedded = mount_asset_doctor_panel(
                self.host_box, self.context, self.status_text.set
            )
            self.status_text.set("Mounted Content ABI / Asset Doctor")
            self.viewport.after_idle(self.viewport.refresh_layout)
        except Exception as exc:  # defensive UI boundary
            self._show_mount_error("Asset Doctor", exc)

    def open_scui_registry(self) -> None:
        """Mount the trusted SCUI registry browser inside the Studio host."""
        try:
            self._clear_host_surface("SCUI panel registry")
            self.active_embedded = mount_registry_browser(
                self.host_box, self.context, self.status_text.set
            )
            self.status_text.set("Mounted trusted SCUI panel registry")
            self.viewport.after_idle(self.viewport.refresh_layout)
        except Exception as exc:  # defensive UI boundary
            self._show_mount_error("SCUI registry", exc)

    def open_scui_proof(self) -> None:
        """Mount the first declarative SCUI panel inside the Studio host."""
        try:
            self._clear_host_surface("Authoring Lab Project Selector")
            self.active_embedded = mount_proof_panel(
                self.host_box, self.context.project_root, self.status_text.set
            )
            self.status_text.set(
                "Mounted SCUI proof panel from content/core/ui/authoring_lab_project_selector.scui"
            )
            self.viewport.after_idle(self.viewport.refresh_layout)
        except Exception as exc:  # defensive UI boundary
            self._show_mount_error("SCUI proof panel", exc)

    def open_light_lab_scui(self) -> None:
        """Mount the managed Light Lab SCUI control surface inside Studio."""
        try:
            self._clear_host_surface("Illuminosity Light Lab SCUI")
            self.active_embedded = mount_light_lab_panel(
                self.host_box, self.context, self.status_text.set
            )
            self.refresh_context()
            self.viewport.after_idle(self.viewport.refresh_layout)
        except Exception as exc:  # defensive UI boundary
            self._show_mount_error("Light Lab SCUI", exc)

    def _show_mount_error(self, title: str, exc: Exception) -> None:
        self._clear_host_surface(f"{title} error")
        label = ttk.Label(
            self.host_box,
            text=f"{title} could not be loaded:\n{exc}",
            justify="left",
        )
        label.pack(fill="both", expand=True)
        bind_responsive_wrap(label, self.host_box, horizontal_margin=40, minimum=280)
        self.status_text.set(f"{title} load failed: {exc}")

    def _selected_info(self) -> PluginInfo | None:
        selected = self.tree.selection()
        if not selected:
            return None
        plugin = self.tool_by_item.get(selected[0])
        if plugin is None:
            return None
        return PluginInfo(
            plugin.key,
            plugin.display_name,
            plugin.description,
            plugin.category,
            plugin.can_embed,
            plugin.standalone_ready,
        )

    def _on_select(self, _event=None) -> None:
        info = self._selected_info()
        if info is None:
            if self.open_button is not None:
                self.open_button.configure(state="disabled")
            return
        self.selected_key.set(info.key)
        mode = "Dock-ready embedded tool" if info.can_embed else "Managed standalone window"
        self.action_summary.set(
            f"{info.display_name} · {info.category} · {mode}. "
            f"{info.description or 'No description provided.'}"
        )
        if self.open_button is not None:
            self.open_button.configure(state="normal")

    def refresh_context(self) -> None:
        try:
            document_context = self.store.read()
            self.context.document_context = document_context
            self.context_text.set(self.model.context_summary(document_context))
            self.status_text.set("Shared document context refreshed")
        except Exception as exc:  # defensive UI boundary
            self.context_text.set("Shared context unavailable")
            self.status_text.set(f"Context refresh failed: {exc}")

    def open_selected(self) -> None:
        info = self._selected_info()
        if info is None:
            self.status_text.set("Select a Studio tool in the sidebar first")
            return
        self.open_tool(info.key)

    def open_tool(self, tool_key: str) -> None:
        try:
            self.catalog.get(tool_key)
        except KeyError as exc:
            messagebox.showerror("Unknown tool", str(exc), parent=self)
            return
        command = [
            sys.executable,
            str(self.context.project_root / "tools" / "signalcloud_studio.py"),
            "--root",
            str(self.context.project_root),
            "--tool",
            tool_key,
        ]
        try:
            self.process_factory(command, cwd=self.context.project_root)
            display = self.catalog.get(tool_key).display_name
            self.status_text.set(f"Opened {display} in a managed Studio window")
        except OSError as exc:
            messagebox.showerror("Tool launch failed", str(exc), parent=self)


def launch_host(context: ToolContext, catalog: PluginCatalog) -> int:
    app = SignalCloudStudioHost(context, catalog)
    app.mainloop()
    return 0
