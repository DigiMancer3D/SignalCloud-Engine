from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable

from tools.pcp3 import editor_branch10 as branch10
from tools.signalcloud_studio.ui import FlowBar, WrappedNotebookBar, wrapped_row_assignments
from tools.signalcloud_studio.workspace import WorkspaceLayoutStore

SIDEBAR_ACTIONS = ("Template", "Validate", "Studio")
REMOVED_TOPBAR_COMMANDS = (
    "Mode Template",
    "Validate",
    "Authoring Studio",
    "Runtime Playback",
    "Runtime Factory",
    "Interaction Runtime",
    "Entity Runtime",
    "World Assembly",
    "Encounter Runtime",
)
AUTHORING_SUBTAB_LABELS = (
    "Rig", "Timeline", "Gameplay", "Placement", "Flow/Theme", "Playback",
    "Factory", "Interaction", "Entity", "World", "Encounter",
)


class PCP3Editor(branch10.PCP3Editor):
    """Branch 10 R1: sidebar-first navigation and shared overflow controls."""

    def __init__(self, root_path: Path) -> None:
        self.sidebar_scroll_axis: tk.StringVar | None = None
        self.sidebar_subtab_locked: tk.BooleanVar | None = None
        self.sidebar_shared_scroll: ttk.Scrollbar | None = None
        self.sidebar_content_viewport: ttk.Frame | None = None
        self.sidebar_main_tabs: WrappedNotebookBar | None = None
        self.authoring_wrapped_tabs: WrappedNotebookBar | None = None
        self._sidebar_offset_x = 0.0
        self._sidebar_offset_y = 0.0
        self._sidebar_content_width = 1
        self._sidebar_content_height = 1
        self._sidebar_last_tab = ""
        self._sidebar_saved_offsets: dict[str, tuple[float, float]] = {}
        super().__init__(root_path)
        self.document.metadata["editor_branch"] = "ISL_plus_branch10_R1"
        self.document.metadata["sidebar_navigation"] = "shared_overflow_v1"
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 10 R1 Sidebar Navigation Repair")
        self.update_status(
            "Branch 10 R1 active · sidebar action header · shared X/Y overflow · lockable Sub-Tab navigation"
        )

    # ---------- clean top command row ----------
    def _build_toolbar(self) -> None:
        super()._build_toolbar()
        shell = getattr(self, "command_toolbar", None)
        if shell is None:
            return
        for child in list(shell.winfo_children()):
            try:
                if int(child.grid_info().get("row", -1)) == 0:
                    child.destroy()
            except (tk.TclError, TypeError, ValueError):
                continue

        row = FlowBar(shell, padding=(0, 0))
        row.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        def button(text: str, command: Callable[[], Any]) -> None:
            group = row.group()
            ttk.Button(group, text=text, command=command).pack()

        button("New", self.new_document)
        button("Open", self.open_project)
        button("Save", self.save)
        button("Export Asset", self.export_to_database)
        button("Undo", self.undo)
        button("Redo", self.redo)
        divider = row.group()
        ttk.Label(divider, text=" |:| ").pack()
        button("Native Preview", self.launch_native_preview)
        divider = row.group()
        ttk.Label(divider, text=" |:| ").pack()
        button("Brush Editor", self.open_brush_editor)
        button("Tools Help", self.show_tools_help)

    # ---------- sidebar installation ----------
    def _build_workspace(self) -> None:
        super()._build_workspace()
        self._install_sidebar_navigation()

    def _install_sidebar_navigation(self) -> None:
        notebook = getattr(self, "right_notebook", None)
        if notebook is None:
            return
        parent = notebook.master
        notebook.pack_forget()

        axis = str(getattr(self, "layout_data", {}).get("sidebar_scroll_axis", self.layer_scroll_axis.get()))
        if axis not in {"x", "y"}:
            axis = "x"
        self.sidebar_scroll_axis = tk.StringVar(master=self, value=axis)
        self.layer_scroll_axis.set(axis)
        self.sidebar_subtab_locked = tk.BooleanVar(
            master=self,
            value=bool(getattr(self, "layout_data", {}).get("sidebar_subtab_locked", False)),
        )

        self._remove_legacy_layer_scroll_controls()
        self._make_notebook_tabless(notebook, "PCP3SidebarContent.TNotebook")
        self._install_authoring_wrapped_tabs()

        action_header = FlowBar(parent, padding=(0, 0))
        action_header.pack(fill="x", pady=(0, 3))
        action_commands = (self.prompt_apply_mode_template, self.validate_mode_asset, self.show_authoring_studio)
        for text, command in zip(SIDEBAR_ACTIONS, action_commands):
            group = action_header.group()
            ttk.Button(group, text=text, command=command).pack(fill="x", expand=True)
        self.sidebar_action_header = action_header

        scroll_block = ttk.Frame(parent)
        scroll_block.pack(fill="x", pady=(0, 3))
        scroll_controls = ttk.Frame(scroll_block)
        scroll_controls.pack(fill="x")
        ttk.Label(scroll_controls, text="Scroll direction:").pack(side="left")
        ttk.Radiobutton(
            scroll_controls,
            text="X",
            value="x",
            variable=self.sidebar_scroll_axis,
            command=self._sidebar_axis_changed,
        ).pack(side="left", padx=(3, 0))
        ttk.Radiobutton(
            scroll_controls,
            text="Y",
            value="y",
            variable=self.sidebar_scroll_axis,
            command=self._sidebar_axis_changed,
        ).pack(side="left")
        ttk.Separator(scroll_controls, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Checkbutton(
            scroll_controls,
            text="Sub-Tab",
            variable=self.sidebar_subtab_locked,
            command=self._sidebar_subtab_changed,
        ).pack(side="left")
        self.sidebar_scroll_target_text = tk.StringVar(master=self, value="Active tab content")
        ttk.Label(scroll_controls, textvariable=self.sidebar_scroll_target_text).pack(side="right")

        self.sidebar_shared_scroll = ttk.Scrollbar(
            scroll_block,
            orient="horizontal",
            command=self._sidebar_shared_scroll_command,
        )
        self.sidebar_shared_scroll.pack(fill="x", pady=(2, 0))

        self.sidebar_main_tabs = WrappedNotebookBar(
            parent,
            notebook,
            max_visible_rows=3,
            on_selected=self._sidebar_notebook_changed,
        )
        self.sidebar_main_tabs.pack(fill="x", pady=(0, 3))

        self.sidebar_content_viewport = ttk.Frame(parent)
        self.sidebar_content_viewport.pack(fill="both", expand=True)
        self.sidebar_content_viewport.bind("<Configure>", self._sidebar_viewport_configured, add=True)
        notebook.bind("<<NotebookTabChanged>>", self._sidebar_notebook_changed, add=True)
        notebook.place(in_=self.sidebar_content_viewport, x=0, y=0)

        self.after_idle(self._sidebar_notebook_changed)
        self.after_idle(self._apply_sidebar_scroll_target)

    def _remove_legacy_layer_scroll_controls(self) -> None:
        old_scroll = getattr(self, "layer_shared_scroll", None)
        if old_scroll is None:
            return
        frame = old_scroll.master
        try:
            old_scroll.destroy()
        except tk.TclError:
            pass
        for widget in list(frame.grid_slaves(row=1)):
            try:
                widget.destroy()
            except tk.TclError:
                pass
        try:
            self.layer_tree.configure(xscrollcommand="", yscrollcommand="")
        except tk.TclError:
            pass

    def _make_notebook_tabless(self, notebook: ttk.Notebook, style_name: str) -> None:
        style = ttk.Style(self)
        try:
            style.layout(style_name, [("Notebook.client", {"sticky": "nswe"})])
            notebook.configure(style=style_name)
        except tk.TclError:
            # The external navigation still works if a very unusual theme rejects
            # the custom layout; only the original strip remains visible.
            pass

    def _install_authoring_wrapped_tabs(self) -> None:
        notebook = getattr(self, "authoring_notebook", None)
        tab = getattr(self, "authoring_tab", None)
        if notebook is None or tab is None:
            return
        self._make_notebook_tabless(notebook, "PCP3AuthoringContent.TNotebook")
        children = list(tab.winfo_children())
        bottom = children[-1] if children else None
        try:
            notebook.pack_forget()
        except tk.TclError:
            return
        bar = WrappedNotebookBar(
            tab,
            notebook,
            max_visible_rows=2,
            on_selected=self._authoring_subtab_changed,
            width_provider=lambda: self.sidebar_content_viewport.winfo_width() if self.sidebar_content_viewport is not None else 0,
        )
        if bottom is not None:
            bar.pack(fill="x", pady=(0, 4), before=bottom)
            notebook.pack(fill="both", expand=True, before=bottom)
        else:
            bar.pack(fill="x", pady=(0, 4))
            notebook.pack(fill="both", expand=True)
        self.authoring_wrapped_tabs = bar

    # ---------- shared scrollbar ----------
    def _current_main_tab_key(self) -> str:
        notebook = getattr(self, "right_notebook", None)
        if notebook is None:
            return ""
        try:
            selected = notebook.select()
            return str(notebook.tab(selected, "text"))
        except tk.TclError:
            return ""

    def _sidebar_notebook_changed(self, _event: tk.Event | None = None) -> None:
        current = self._current_main_tab_key()
        if self._sidebar_last_tab:
            self._sidebar_saved_offsets[self._sidebar_last_tab] = (
                self._sidebar_offset_x,
                self._sidebar_offset_y,
            )
        self._sidebar_last_tab = current
        self._sidebar_offset_x, self._sidebar_offset_y = self._sidebar_saved_offsets.get(current, (0.0, 0.0))
        if self.sidebar_main_tabs is not None:
            self.sidebar_main_tabs._sync_selection()
        self.after_idle(self._layout_sidebar_content)
        self.after_idle(self._apply_sidebar_scroll_target)

    def _authoring_subtab_changed(self) -> None:
        self.after_idle(self._layout_sidebar_content)
        self.after_idle(self._apply_sidebar_scroll_target)

    def _sidebar_viewport_configured(self, _event: tk.Event | None = None) -> None:
        self._layout_sidebar_content()

    def _layout_sidebar_content(self) -> None:
        notebook = getattr(self, "right_notebook", None)
        viewport = self.sidebar_content_viewport
        if notebook is None or viewport is None or not viewport.winfo_exists():
            return
        viewport.update_idletasks()
        view_width = max(1, viewport.winfo_width())
        view_height = max(1, viewport.winfo_height())
        try:
            selected = notebook.select()
            page = self.nametowidget(selected)
            page.update_idletasks()
            requested_width = page.winfo_reqwidth() + 8
            requested_height = page.winfo_reqheight() + 8
        except (tk.TclError, KeyError):
            requested_width = notebook.winfo_reqwidth()
            requested_height = notebook.winfo_reqheight()
        self._sidebar_content_width = max(view_width, int(requested_width))
        self._sidebar_content_height = max(view_height, int(requested_height))
        max_x = max(0.0, float(self._sidebar_content_width - view_width))
        max_y = max(0.0, float(self._sidebar_content_height - view_height))
        self._sidebar_offset_x = max(0.0, min(max_x, self._sidebar_offset_x))
        self._sidebar_offset_y = max(0.0, min(max_y, self._sidebar_offset_y))
        notebook.place(
            in_=viewport,
            x=-int(round(self._sidebar_offset_x)),
            y=-int(round(self._sidebar_offset_y)),
            width=self._sidebar_content_width,
            height=self._sidebar_content_height,
        )
        self._update_shared_scroll_thumb()

    def _sidebar_axis_changed(self) -> None:
        if self.sidebar_scroll_axis is None:
            return
        axis = "y" if self.sidebar_scroll_axis.get() == "y" else "x"
        self.sidebar_scroll_axis.set(axis)
        self.layer_scroll_axis.set(axis)
        self._apply_sidebar_scroll_target()
        self.schedule_layout_save()

    def _sidebar_subtab_changed(self) -> None:
        if self.sidebar_subtab_locked is not None and self.sidebar_subtab_locked.get():
            self.show_authoring_studio()
        self._apply_sidebar_scroll_target()
        self.schedule_layout_save()

    def _using_subtab_scroll(self) -> bool:
        return bool(
            self.sidebar_subtab_locked is not None
            and self.sidebar_subtab_locked.get()
            and self._current_main_tab_key() == "Authoring"
            and self.authoring_wrapped_tabs is not None
        )

    def _apply_sidebar_scroll_target(self) -> None:
        scrollbar = self.sidebar_shared_scroll
        if scrollbar is None:
            return
        axis = "y" if self.sidebar_scroll_axis is not None and self.sidebar_scroll_axis.get() == "y" else "x"
        if self.authoring_wrapped_tabs is not None:
            self.authoring_wrapped_tabs.clear_external_scrollcommand()
        if self._using_subtab_scroll() and self.authoring_wrapped_tabs is not None:
            self.sidebar_scroll_target_text.set("Authoring sub-tabs")
            self.authoring_wrapped_tabs.set_external_scrollcommand(axis, scrollbar.set)
            if axis == "y":
                first, last = self.authoring_wrapped_tabs.canvas.yview()
            else:
                first, last = self.authoring_wrapped_tabs.canvas.xview()
            scrollbar.set(first, last)
        else:
            self.sidebar_scroll_target_text.set("Active tab content")
            self._update_shared_scroll_thumb()

    def _sidebar_shared_scroll_command(self, *args: Any) -> None:
        axis = "y" if self.sidebar_scroll_axis is not None and self.sidebar_scroll_axis.get() == "y" else "x"
        if self._using_subtab_scroll() and self.authoring_wrapped_tabs is not None:
            self.authoring_wrapped_tabs.view(axis, *args)
            return
        viewport = self.sidebar_content_viewport
        if viewport is None:
            return
        view_extent = float(max(1, viewport.winfo_height() if axis == "y" else viewport.winfo_width()))
        content_extent = float(self._sidebar_content_height if axis == "y" else self._sidebar_content_width)
        maximum = max(0.0, content_extent - view_extent)
        current = self._sidebar_offset_y if axis == "y" else self._sidebar_offset_x
        if args and str(args[0]) == "moveto" and len(args) >= 2:
            try:
                current = float(args[1]) * maximum
            except (TypeError, ValueError):
                return
        elif args and str(args[0]) == "scroll" and len(args) >= 3:
            try:
                amount = int(args[1])
            except (TypeError, ValueError):
                return
            step = view_extent * 0.85 if str(args[2]) == "pages" else 24.0
            current += amount * step
        current = max(0.0, min(maximum, current))
        if axis == "y":
            self._sidebar_offset_y = current
        else:
            self._sidebar_offset_x = current
        self._layout_sidebar_content()

    def _update_shared_scroll_thumb(self) -> None:
        scrollbar = self.sidebar_shared_scroll
        viewport = self.sidebar_content_viewport
        if scrollbar is None or viewport is None or self._using_subtab_scroll():
            return
        axis = "y" if self.sidebar_scroll_axis is not None and self.sidebar_scroll_axis.get() == "y" else "x"
        view_extent = float(max(1, viewport.winfo_height() if axis == "y" else viewport.winfo_width()))
        content_extent = float(max(1, self._sidebar_content_height if axis == "y" else self._sidebar_content_width))
        current = self._sidebar_offset_y if axis == "y" else self._sidebar_offset_x
        first = max(0.0, min(1.0, current / content_extent))
        last = max(first, min(1.0, (current + view_extent) / content_extent))
        scrollbar.set(first, last)

    # Backward-compatible entry points used by the accepted R2 layer-tree code.
    def set_layer_scroll_axis(self, axis: str) -> None:
        if self.sidebar_scroll_axis is None:
            super().set_layer_scroll_axis(axis)
            return
        self.sidebar_scroll_axis.set("y" if axis == "y" else "x")
        self._sidebar_axis_changed()

    def apply_layer_scroll_axis(self) -> None:
        if self.sidebar_scroll_axis is None:
            super().apply_layer_scroll_axis()
            return
        self._apply_sidebar_scroll_target()

    # ---------- persistence ----------
    def save_workspace_layout(self) -> None:
        super().save_workspace_layout()
        updates: dict[str, Any] = {
            "sidebar_scroll_axis": (
                self.sidebar_scroll_axis.get() if self.sidebar_scroll_axis is not None else self.layer_scroll_axis.get()
            ),
            "sidebar_subtab_locked": bool(
                self.sidebar_subtab_locked.get() if self.sidebar_subtab_locked is not None else False
            ),
            "sidebar_main_tab": self._current_main_tab_key(),
        }
        if getattr(self, "authoring_notebook", None) is not None:
            try:
                selected = self.authoring_notebook.select()
                updates["sidebar_authoring_tab"] = str(self.authoring_notebook.tab(selected, "text"))
            except tk.TclError:
                pass
        try:
            WorkspaceLayoutStore(self.layout_path()).merge(updates)
        except OSError:
            pass

    def _restore_main_sashes(self) -> None:
        super()._restore_main_sashes()
        self.after_idle(self._restore_sidebar_selection)

    def _restore_sidebar_selection(self) -> None:
        layout = getattr(self, "layout_data", {})
        main_name = str(layout.get("sidebar_main_tab", ""))
        notebook = getattr(self, "right_notebook", None)
        if notebook is not None and main_name:
            for index in range(int(notebook.index("end"))):
                if str(notebook.tab(index, "text")) == main_name:
                    notebook.select(index)
                    break
        sub_name = str(layout.get("sidebar_authoring_tab", ""))
        authoring = getattr(self, "authoring_notebook", None)
        if authoring is not None and sub_name:
            for index in range(int(authoring.index("end"))):
                if str(authoring.tab(index, "text")) == sub_name:
                    authoring.select(index)
                    break
        if self.sidebar_main_tabs is not None:
            self.sidebar_main_tabs.refresh()
        if self.authoring_wrapped_tabs is not None:
            self.authoring_wrapped_tabs.refresh()
        self._sidebar_notebook_changed()


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
