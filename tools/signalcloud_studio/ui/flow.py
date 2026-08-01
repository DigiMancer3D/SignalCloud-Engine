from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def wrapped_row_assignments(widths: list[int], available: int) -> list[tuple[int, int]]:
    """Return deterministic row/column positions for responsive controls."""

    available = max(1, int(available))
    row = 0
    column = 0
    used = 0
    result: list[tuple[int, int]] = []
    for raw_width in widths:
        width = max(1, int(raw_width))
        if column and used + width > available:
            row += 1
            column = 0
            used = 0
        result.append((row, column))
        used += width
        column += 1
    return result


class FlowBar(ttk.Frame):
    """Responsive Studio toolbar that wraps complete control groups."""

    def __init__(self, master: tk.Misc, *, padding: tuple[int, int] = (8, 5)) -> None:
        super().__init__(master, padding=padding)
        self.items: list[ttk.Frame] = []
        self._reflow_after: str | None = None
        self.bind("<Configure>", self._schedule_reflow)

    def group(self) -> ttk.Frame:
        frame = ttk.Frame(self)
        self.items.append(frame)
        self._schedule_reflow()
        return frame

    def clear(self) -> None:
        """Destroy all groups so a dynamic action row can be rebuilt safely."""
        for item in self.items:
            item.destroy()
        self.items.clear()
        self._schedule_reflow()

    def _schedule_reflow(self, _event: tk.Event | None = None) -> None:
        if self._reflow_after is None:
            self._reflow_after = self.after_idle(self._reflow)

    def _reflow(self) -> None:
        self._reflow_after = None
        available = max(260, self.winfo_width() - 8)
        widths: list[int] = []
        for item in self.items:
            item.update_idletasks()
            widths.append(max(20, item.winfo_reqwidth() + 6))
        positions = wrapped_row_assignments(widths, available)
        for item, (row, column) in zip(self.items, positions):
            item.grid(row=row, column=column, sticky="w", padx=2, pady=2)
        for index in range(max(1, len(self.items))):
            self.columnconfigure(index, weight=0)
