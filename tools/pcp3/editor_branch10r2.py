from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from tools.pcp3 import editor_branch10r1 as branch10r1


class PCP3Editor(branch10r1.PCP3Editor):
    """Branch 10 R2: visible clipped tab content and reserved status bar.

    Branch 10 R1 placed the existing notebook relative to a later-created
    opaque viewport frame.  Because that frame sat above the notebook in Tk's
    stacking order, the active page was technically present but almost fully
    covered.  R2 keeps the accepted shared-scroll design, places the notebook
    above the viewport, and uses a raised header mask to preserve clipping
    while scrolling.
    """

    def __init__(self, root_path: Path) -> None:
        self.sidebar_header_mask: tk.Frame | None = None
        self.status_bar_frame: ttk.Frame | None = None
        self.workspace_paned: ttk.Panedwindow | None = None
        super().__init__(root_path)
        self.document.metadata["editor_branch"] = "ISL_plus_branch10_R2"
        self.document.metadata["sidebar_navigation"] = "shared_overflow_visible_v2"
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 10 R2 Sidebar Content Repair")
        self.update_status(
            "Branch 10 R2 active · visible clipped tab content · shared X/Y scrolling · reserved status bar"
        )

    def _build_workspace(self) -> None:
        super()._build_workspace()
        self._reserve_bottom_status_bar()

    def _make_notebook_tabless(self, notebook: ttk.Notebook, style_name: str) -> None:
        # The notebook body owns the tab pages, while the full-label external
        # bars own navigation.  Hiding only Notebook.client does not suppress
        # native tabs on every KDE/Tk theme, so explicitly remove the Tab
        # substyle as well.
        super()._make_notebook_tabless(notebook, style_name)
        style = ttk.Style(self)
        try:
            style.layout(f"{style_name}.Tab", [])
            notebook.configure(style=style_name)
        except tk.TclError:
            pass

    def _install_sidebar_navigation(self) -> None:
        super()._install_sidebar_navigation()
        notebook = getattr(self, "right_notebook", None)
        viewport = self.sidebar_content_viewport
        if notebook is None or viewport is None:
            return
        parent = notebook.master
        style = ttk.Style(self)
        background = style.lookup("TFrame", "background") or "#d9d9d9"
        self.sidebar_header_mask = tk.Frame(
            parent,
            background=background,
            borderwidth=0,
            highlightthickness=0,
            takefocus=False,
        )
        parent.bind("<Configure>", self._sidebar_parent_configured, add=True)
        viewport.bind("<Configure>", self._sidebar_parent_configured, add=True)
        self.after_idle(self._restack_sidebar_content)

    def _reserve_bottom_status_bar(self) -> None:
        """Reserve the accepted bottom status row at ordinary window sizes."""
        paned: ttk.Panedwindow | None = None
        status_frame: ttk.Frame | None = None
        status_variable = str(getattr(self, "status", ""))
        for widget in self.winfo_children():
            if isinstance(widget, ttk.Panedwindow):
                paned = widget
            elif isinstance(widget, ttk.Frame):
                labels = [child for child in widget.winfo_children() if isinstance(child, ttk.Label)]
                if any(str(label.cget("textvariable")) == status_variable for label in labels):
                    status_frame = widget
        if paned is None or status_frame is None:
            return
        self.workspace_paned = paned
        self.status_bar_frame = status_frame
        try:
            status_frame.pack_forget()
            paned.pack_forget()
            status_frame.pack(side="bottom", fill="x")
            paned.pack(side="top", fill="both", expand=True, padx=8)
        except tk.TclError:
            return

    def _sidebar_parent_configured(self, _event: tk.Event | None = None) -> None:
        self.after_idle(self._restack_sidebar_content)

    def _restack_sidebar_content(self) -> None:
        notebook = getattr(self, "right_notebook", None)
        viewport = self.sidebar_content_viewport
        mask = self.sidebar_header_mask
        if notebook is None or viewport is None or mask is None:
            return
        if not notebook.winfo_exists() or not viewport.winfo_exists() or not mask.winfo_exists():
            return
        try:
            viewport.update_idletasks()
            header_height = max(0, int(viewport.winfo_y()))
            mask.place(x=0, y=0, relwidth=1.0, height=header_height)
            # The viewport remains behind the notebook.  The header mask sits
            # above scrolled content, and the real controls sit above the mask.
            notebook.lift(viewport)
            mask.lift(notebook)
            header_widgets = [
                getattr(self, "sidebar_action_header", None),
                self.sidebar_shared_scroll.master if self.sidebar_shared_scroll is not None else None,
                self.sidebar_main_tabs,
            ]
            for widget in header_widgets:
                if widget is not None and widget.winfo_exists():
                    widget.lift(mask)
        except tk.TclError:
            return

    def _layout_sidebar_content(self) -> None:
        super()._layout_sidebar_content()
        self._restack_sidebar_content()

    def _sidebar_notebook_changed(self, _event: tk.Event | None = None) -> None:
        super()._sidebar_notebook_changed(_event)
        self.after_idle(self._restack_sidebar_content)

    def _authoring_subtab_changed(self) -> None:
        super()._authoring_subtab_changed()
        self.after_idle(self._restack_sidebar_content)


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
