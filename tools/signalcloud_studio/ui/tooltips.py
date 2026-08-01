from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ToolTip:
    """Small reusable tooltip shared by trusted Studio tools.

    The widget owns only presentation behavior. Tool commands remain registered
    separately through the allowlisted Studio command registry.
    """

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.popup: tk.Toplevel | None = None
        widget.bind("<Enter>", self.show, add=True)
        widget.bind("<Leave>", self.hide, add=True)

    def show(self, _event: tk.Event | None = None) -> None:
        if self.popup is not None:
            return
        self.popup = tk.Toplevel(self.widget)
        self.popup.overrideredirect(True)
        self.popup.attributes("-topmost", True)
        x = self.widget.winfo_rootx() + 18
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.popup.geometry(f"+{x}+{y}")
        ttk.Label(self.popup, text=self.text, padding=6, relief="solid").pack()

    def hide(self, _event: tk.Event | None = None) -> None:
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None
