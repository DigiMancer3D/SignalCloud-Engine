from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from .flow import wrapped_row_assignments


class WrappedNotebookBar(ttk.Frame):
    """Full-label notebook navigation with responsive multi-row wrapping."""

    def __init__(
        self,
        master: tk.Misc,
        notebook: ttk.Notebook,
        *,
        max_visible_rows: int = 99,
        on_selected: Callable[[], None] | None = None,
        width_provider: Callable[[], int] | None = None,
        padding: tuple[int, int] = (0, 0),
    ) -> None:
        super().__init__(master, padding=padding)
        self.notebook = notebook
        self.max_visible_rows = max(1, int(max_visible_rows))
        self.on_selected = on_selected
        self.width_provider = width_provider
        self.selection = tk.StringVar(master=self, value="0")
        self.buttons: list[ttk.Radiobutton] = []
        self._reflow_after: str | None = None

        style = ttk.Style(self)
        background = style.lookup("TFrame", "background") or "#d9d9d9"
        self.canvas = tk.Canvas(
            self,
            height=28,
            highlightthickness=0,
            borderwidth=0,
            background=background,
            takefocus=False,
        )
        self.canvas.pack(fill="x", expand=True)
        self.inner = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window(0, 0, anchor="nw", window=self.inner)

        self.canvas.bind("<Configure>", self._schedule_reflow, add=True)
        self.inner.bind("<Configure>", self._inner_configured, add=True)
        self.notebook.bind("<<NotebookTabChanged>>", self._notebook_changed, add=True)
        self.refresh()

    def tab_count(self) -> int:
        try:
            return int(self.notebook.index("end"))
        except (tk.TclError, TypeError, ValueError):
            return 0

    def refresh(self) -> None:
        for button in self.buttons:
            button.destroy()
        self.buttons.clear()
        for index in range(self.tab_count()):
            text = str(self.notebook.tab(index, "text"))
            button = ttk.Radiobutton(
                self.inner,
                text=text,
                value=str(index),
                variable=self.selection,
                style="Toolbutton",
                command=lambda selected=index: self.select(selected),
            )
            self.buttons.append(button)
        self._sync_selection()
        self._schedule_reflow()

    def select(self, index: int) -> None:
        try:
            self.notebook.select(index)
        except tk.TclError:
            return
        self._sync_selection()
        if self.on_selected is not None:
            self.on_selected()

    def _notebook_changed(self, _event: tk.Event | None = None) -> None:
        self._sync_selection()
        self._schedule_reflow()
        if self.on_selected is not None:
            self.on_selected()

    def _sync_selection(self) -> None:
        try:
            selected = self.notebook.select()
            index = int(self.notebook.index(selected))
        except (tk.TclError, TypeError, ValueError):
            index = 0
        self.selection.set(str(index))
        self.after_idle(self.ensure_selected_visible)

    def _schedule_reflow(self, _event: tk.Event | None = None) -> None:
        if self._reflow_after is None:
            self._reflow_after = self.after_idle(self._reflow)

    def _reflow(self) -> None:
        self._reflow_after = None
        if not self.buttons:
            self.canvas.configure(height=1, scrollregion=(0, 0, 1, 1))
            return
        canvas_width = max(1, self.canvas.winfo_width())
        if self.width_provider is not None:
            try:
                provided = int(self.width_provider())
            except (TypeError, ValueError, tk.TclError):
                provided = 0
            if provided > 20:
                canvas_width = min(canvas_width, provided)
        available = max(120, canvas_width - 4)
        widths: list[int] = []
        row_height = 26
        for button in self.buttons:
            button.update_idletasks()
            widths.append(max(45, button.winfo_reqwidth() + 4))
            row_height = max(row_height, max(24, button.winfo_reqheight() + 2))
        positions = wrapped_row_assignments(widths, available)
        row_widths: dict[int, int] = {}
        for button, width, (row, column) in zip(self.buttons, widths, positions):
            button.grid(row=row, column=column, sticky="w", padx=1, pady=1)
            row_widths[row] = row_widths.get(row, 0) + width
        widest_row = max([available, *row_widths.values()])
        total_rows = max((row for row, _column in positions), default=0) + 1
        total_height = total_rows * (row_height + 2)
        visible_rows = min(total_rows, self.max_visible_rows)
        visible_height = max(row_height + 2, visible_rows * (row_height + 2))
        self.canvas.itemconfigure(self.window_id, width=widest_row)
        self.canvas.configure(height=visible_height)
        self.inner.update_idletasks()
        self.canvas.configure(scrollregion=(0, 0, widest_row, max(total_height, visible_height)))
        self.after_idle(self.ensure_selected_visible)

    def _inner_configured(self, _event: tk.Event | None = None) -> None:
        bbox = self.canvas.bbox(self.window_id)
        if bbox is not None:
            self.canvas.configure(scrollregion=bbox)

    def ensure_selected_visible(self) -> None:
        if not self.buttons:
            return
        try:
            index = int(self.selection.get())
            button = self.buttons[index]
        except (ValueError, IndexError):
            return
        self.update_idletasks()
        canvas_height = max(1, self.canvas.winfo_height())
        content_height = max(canvas_height, self.inner.winfo_reqheight())
        if content_height <= canvas_height:
            self.canvas.yview_moveto(0.0)
            return
        top = self.canvas.canvasy(0)
        bottom = top + canvas_height
        button_top = float(button.winfo_y())
        button_bottom = button_top + float(button.winfo_height())
        if button_top < top:
            self.canvas.yview_moveto(max(0.0, button_top / content_height))
        elif button_bottom > bottom:
            target = max(0.0, button_bottom - canvas_height)
            self.canvas.yview_moveto(min(1.0, target / content_height))

    def set_external_scrollcommand(self, axis: str, callback: Callable[[float, float], None] | str) -> None:
        if axis == "y":
            self.canvas.configure(xscrollcommand="", yscrollcommand=callback)
        else:
            self.canvas.configure(xscrollcommand=callback, yscrollcommand="")

    def clear_external_scrollcommand(self) -> None:
        self.canvas.configure(xscrollcommand="", yscrollcommand="")

    def view(self, axis: str, *args: Any) -> None:
        if axis == "y":
            self.canvas.yview(*args)
        else:
            self.canvas.xview(*args)
