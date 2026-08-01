from __future__ import annotations

import tkinter as tk


def bind_responsive_wrap(
    label: tk.Widget,
    container: tk.Misc,
    *,
    horizontal_margin: int = 36,
    minimum: int = 220,
    maximum: int = 1400,
) -> None:
    """Keep a label's wrap length aligned with its live container width."""

    def update(_event: tk.Event | None = None) -> None:
        try:
            width = int(container.winfo_width()) - int(horizontal_margin)
            label.configure(wraplength=max(minimum, min(maximum, width)))
        except (tk.TclError, AttributeError):
            return

    container.bind("<Configure>", update, add="+")
    container.after_idle(update)
