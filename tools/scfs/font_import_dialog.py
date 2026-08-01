from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .font_importer import (
    FontProbe, choose_codepoints, import_outline_font,
)
from .model import FontDocument


class FontImportDialog(tk.Toplevel):
    PRESETS = ("Basic Latin", "Latin-1", "All mapped glyphs", "Text characters")

    def __init__(self, master: tk.Misc, probe: FontProbe, color: str) -> None:
        super().__init__(master)
        self.title("+SCFS+ Import Outline Font")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.probe, self.color = probe, color
        self.result: FontDocument | None = None
        self.height, self.threshold = tk.IntVar(value=16), tk.IntVar(value=72)
        self.preset = tk.StringVar(value="Basic Latin")
        self.alpha = tk.BooleanVar(value=True)
        self.sample = tk.StringVar(value="ALMOND SIGNAL 0123!?")
        self.summary = tk.StringVar()
        self._build()
        self._refresh_summary()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"{self.probe.family} — {self.probe.style or self.probe.format}",
                  font=("Sans", 13, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text=str(self.probe.path), foreground="#78929b").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(body, text="SignalCloud grid height").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(body, from_=5, to=64, textvariable=self.height, width=9,
                    command=self._refresh_summary).grid(row=2, column=1, sticky="w")
        ttk.Label(body, text="Filled-point threshold").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Spinbox(body, from_=1, to=254, textvariable=self.threshold, width=9).grid(
            row=3, column=1, sticky="w", pady=4)
        ttk.Label(body, text="Characters").grid(row=4, column=0, sticky="w")
        combo = ttk.Combobox(body, values=self.PRESETS, textvariable=self.preset,
                             state="readonly", style="SCFS.TCombobox", width=22)
        combo.grid(row=4, column=1, sticky="w")
        combo.bind("<<ComboboxSelected>>", lambda _e: self._preset_changed())
        ttk.Label(body, text="Text character source").grid(row=5, column=0, sticky="w", pady=4)
        self.sample_entry = ttk.Entry(body, textvariable=self.sample, width=28, state="disabled")
        self.sample_entry.grid(row=5, column=1, sticky="w", pady=4)
        ttk.Checkbutton(body, text="Use outline coverage as point alpha",
                        variable=self.alpha).grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 8))
        ttk.Label(body, textvariable=self.summary, foreground="#45d8ef", wraplength=430).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(0, 10))
        buttons = ttk.Frame(body)
        buttons.grid(row=8, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Import", command=self._import).pack(side="right", padx=5)
        for variable in (self.height, self.preset, self.sample):
            variable.trace_add("write", lambda *_: self._refresh_summary())

    def _preset_changed(self) -> None:
        self.sample_entry.configure(
            state="normal" if self.preset.get() == "Text characters" else "disabled")
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        try:
            codes = choose_codepoints(self.probe, self.preset.get(), self.sample.get())
            mapped = len(self.probe.codepoints)
            self.summary.set(
                f"{len(codes)} glyphs will be converted"
                + (f" from {mapped} mapped Unicode glyphs." if mapped else ".")
                + " Higher grids preserve more shape but use more SignalCloud points.")
        except Exception as exc:
            self.summary.set(str(exc))

    def _import(self) -> None:
        try:
            codes = choose_codepoints(self.probe, self.preset.get(), self.sample.get())
            self.result = import_outline_font(
                self.probe.path, grid_height=self.height.get(), threshold=self.threshold.get(),
                codepoints=codes, color=self.color, preserve_alpha=self.alpha.get())
        except Exception as exc:
            messagebox.showerror("+SCFS+ Font Import", str(exc), parent=self)
            return
        self.destroy()
