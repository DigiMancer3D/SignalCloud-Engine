from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class AxisSwitchViewport(ttk.Frame):
    """Scrollable Studio viewport with one horizontal bar for either axis.

    SignalCloud authoring tools intentionally avoid a dedicated vertical bar.
    The X/Y checkboxes are mutually exclusive; X is selected by default. The
    single horizontal scrollbar controls the selected canvas axis while both
    axis positions are preserved when switching.
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        minimum_content_width: int = 760,
        minimum_content_height: int = 440,
    ) -> None:
        super().__init__(master)
        self.minimum_content_width = max(320, int(minimum_content_width))
        self.minimum_content_height = max(240, int(minimum_content_height))
        self.axis_x = tk.BooleanVar(self, value=True)
        self.axis_y = tk.BooleanVar(self, value=False)
        self._active_axis = "x"
        self._x_fraction = (0.0, 1.0)
        self._y_fraction = (0.0, 1.0)
        self._sync_after: str | None = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            self,
            highlightthickness=0,
            borderwidth=0,
            relief="flat",
            takefocus=False,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")

        self.content = ttk.Frame(self.canvas)
        self._window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")

        control = ttk.Frame(self, padding=(4, 5, 4, 2))
        control.grid(row=1, column=0, sticky="ew")
        control.columnconfigure(7, weight=1)
        ttk.Label(control, text="Scroll axis:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        ttk.Label(control, text="X").grid(row=0, column=1, sticky="w")
        self.x_toggle = ttk.Checkbutton(
            control,
            variable=self.axis_x,
            command=lambda: self.select_axis("x"),
            takefocus=True,
        )
        self.x_toggle.grid(row=0, column=2, sticky="w")
        ttk.Label(control, text="|").grid(row=0, column=3, padx=5)
        ttk.Label(control, text="Y").grid(row=0, column=4, sticky="w")
        self.y_toggle = ttk.Checkbutton(
            control,
            variable=self.axis_y,
            command=lambda: self.select_axis("y"),
            takefocus=True,
        )
        self.y_toggle.grid(row=0, column=5, sticky="w")
        ttk.Separator(control, orient="vertical").grid(row=0, column=6, sticky="ns", padx=(8, 8))
        self.scrollbar = ttk.Scrollbar(control, orient="horizontal", command=self._scroll)
        self.scrollbar.grid(row=0, column=7, sticky="ew")

        self.canvas.configure(xscrollcommand=self._set_x, yscrollcommand=self._set_y)
        self.canvas.bind("<Configure>", self._schedule_sync, add="+")
        self.content.bind("<Configure>", self._schedule_sync, add="+")
        self.canvas.bind("<Shift-MouseWheel>", self._wheel_horizontal, add="+")
        self.canvas.bind("<MouseWheel>", self._wheel_active, add="+")
        self.canvas.bind("<Button-4>", lambda _event: self._wheel_units(-3), add="+")
        self.canvas.bind("<Button-5>", lambda _event: self._wheel_units(3), add="+")
        self._schedule_sync()

    @property
    def active_axis(self) -> str:
        return self._active_axis

    def select_axis(self, axis: str) -> None:
        if axis not in {"x", "y"}:
            raise ValueError(f"unsupported scroll axis: {axis}")
        # Clicking the already-active checkbox may attempt to clear it. The
        # contract requires exactly one axis to remain selected.
        self._active_axis = axis
        self.axis_x.set(axis == "x")
        self.axis_y.set(axis == "y")
        self._refresh_thumb()
        self.canvas.focus_set()

    def reset(self, *, axis: str = "x") -> None:
        self.canvas.xview_moveto(0.0)
        self.canvas.yview_moveto(0.0)
        self.select_axis(axis)

    def refresh_layout(self) -> None:
        self._schedule_sync()

    def _set_x(self, first: str, last: str) -> None:
        self._x_fraction = (float(first), float(last))
        if self._active_axis == "x":
            self.scrollbar.set(first, last)

    def _set_y(self, first: str, last: str) -> None:
        self._y_fraction = (float(first), float(last))
        if self._active_axis == "y":
            self.scrollbar.set(first, last)

    def _refresh_thumb(self) -> None:
        fraction = self._x_fraction if self._active_axis == "x" else self._y_fraction
        self.scrollbar.set(*fraction)

    def _scroll(self, *args: str) -> None:
        if self._active_axis == "x":
            self.canvas.xview(*args)
        else:
            self.canvas.yview(*args)

    def _wheel_units(self, units: int) -> str:
        if self._active_axis == "x":
            self.canvas.xview_scroll(units, "units")
        else:
            self.canvas.yview_scroll(units, "units")
        return "break"

    def _wheel_active(self, event: tk.Event) -> str:
        delta = int(getattr(event, "delta", 0))
        units = -3 if delta > 0 else 3
        return self._wheel_units(units)

    def _wheel_horizontal(self, event: tk.Event) -> str:
        delta = int(getattr(event, "delta", 0))
        self.canvas.xview_scroll(-3 if delta > 0 else 3, "units")
        return "break"

    def _schedule_sync(self, _event: tk.Event | None = None) -> None:
        if self._sync_after is None:
            self._sync_after = self.after_idle(self._sync_geometry)

    def _sync_geometry(self) -> None:
        self._sync_after = None
        if not self.winfo_exists():
            return
        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        requested_width = max(self.minimum_content_width, self.content.winfo_reqwidth())
        requested_height = max(self.minimum_content_height, self.content.winfo_reqheight())
        content_width = max(canvas_width, requested_width)
        content_height = max(canvas_height, requested_height)
        self.canvas.itemconfigure(self._window_id, width=content_width, height=content_height)
        self.canvas.configure(scrollregion=(0, 0, content_width, content_height))
        self._refresh_thumb()
