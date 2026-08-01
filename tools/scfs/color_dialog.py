from __future__ import annotations

import json
import re
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk

DEFAULT_C1 = "#45d8ef"
DEFAULT_C2 = "#45c824"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def normalize_color(value: str, fallback: str = DEFAULT_C1) -> str:
    value = str(value).strip()
    if not value.startswith("#"):
        value = "#" + value
    return value.lower() if _HEX.fullmatch(value) else fallback


@dataclass
class ColorSlots:
    c1: str = DEFAULT_C1
    c2: str = DEFAULT_C2

    @classmethod
    def load(cls, path: Path) -> "ColorSlots":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return cls()
        return cls(
            normalize_color(data.get("c1", DEFAULT_C1), DEFAULT_C1),
            normalize_color(data.get("c2", DEFAULT_C2), DEFAULT_C2),
        )

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"c1": self.c1, "c2": self.c2}, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)


class PointColorDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, initial: str, slots_path: Path) -> None:
        super().__init__(master)
        self.title("+SCFS+ Point Color")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.grab_set()
        self.slots_path = Path(slots_path)
        self.slots = ColorSlots.load(self.slots_path)
        initial = normalize_color(initial)
        self.red = tk.IntVar(value=int(initial[1:3], 16))
        self.green = tk.IntVar(value=int(initial[3:5], 16))
        self.blue = tk.IntVar(value=int(initial[5:7], 16))
        self.hex_value = tk.StringVar(value=initial)
        self.result: str | None = None
        self._syncing = False
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda _event: self.cancel())
        self.bind("<Return>", lambda _event: self.accept())
        self.update_idletasks()
        self.geometry(
            f"+{master.winfo_rootx() + 80}+{master.winfo_rooty() + 80}"
        )

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=12)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)
        self.preview = tk.Canvas(frame, width=280, height=58, highlightthickness=1)
        self.preview.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        for row, (label, variable) in enumerate(
            (("Red", self.red), ("Green", self.green), ("Blue", self.blue)), 1
        ):
            ttk.Label(frame, text=label, width=6).grid(row=row, column=0, sticky="w")
            ttk.Scale(
                frame, from_=0, to=255, variable=variable,
                command=lambda _value: self._from_rgb(),
            ).grid(row=row, column=1, sticky="ew", padx=6)
            spin = ttk.Spinbox(frame, from_=0, to=255, width=5, textvariable=variable)
            spin.grid(row=row, column=2)
            spin.bind("<KeyRelease>", lambda _event: self._from_rgb())
        ttk.Label(frame, text="Hex").grid(row=4, column=0, sticky="w", pady=(8, 0))
        entry = ttk.Entry(frame, textvariable=self.hex_value, width=14)
        entry.grid(row=4, column=1, columnspan=2, sticky="ew", pady=(8, 0))
        entry.bind("<KeyRelease>", lambda _event: self._from_hex())

        slots = ttk.LabelFrame(frame, text="Recall / store", padding=8)
        slots.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(12, 8))
        for column in range(4):
            slots.columnconfigure(column, weight=1)
        self.c1_button = ttk.Button(slots, command=lambda: self.recall("c1"))
        self.c1_button.grid(row=0, column=0, sticky="ew")
        ttk.Button(slots, text="Store C1", command=lambda: self.store("c1")).grid(
            row=0, column=1, sticky="ew", padx=(4, 10)
        )
        self.c2_button = ttk.Button(slots, command=lambda: self.recall("c2"))
        self.c2_button.grid(row=0, column=2, sticky="ew")
        ttk.Button(slots, text="Store C2", command=lambda: self.store("c2")).grid(
            row=0, column=3, sticky="ew", padx=(4, 0)
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=3, sticky="e")
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side="right")
        ttk.Button(buttons, text="Use Color", command=self.accept).pack(side="right", padx=5)
        self._refresh()

    def current_color(self) -> str:
        return f"#{self.red.get():02x}{self.green.get():02x}{self.blue.get():02x}"

    def _from_rgb(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            for variable in (self.red, self.green, self.blue):
                variable.set(max(0, min(255, int(float(variable.get())))))
            self.hex_value.set(self.current_color())
        except (ValueError, tk.TclError):
            pass
        finally:
            self._syncing = False
        self._refresh()

    def _from_hex(self) -> None:
        if self._syncing:
            return
        value = normalize_color(self.hex_value.get(), "")
        if not value:
            return
        self._syncing = True
        self.red.set(int(value[1:3], 16))
        self.green.set(int(value[3:5], 16))
        self.blue.set(int(value[5:7], 16))
        self._syncing = False
        self._refresh()

    def _set_color(self, value: str) -> None:
        value = normalize_color(value)
        self._syncing = True
        self.red.set(int(value[1:3], 16))
        self.green.set(int(value[3:5], 16))
        self.blue.set(int(value[5:7], 16))
        self.hex_value.set(value)
        self._syncing = False
        self._refresh()

    def recall(self, slot: str) -> None:
        self._set_color(getattr(self.slots, slot))

    def store(self, slot: str) -> None:
        setattr(self.slots, slot, self.current_color())
        self.slots.save(self.slots_path)
        self._refresh()

    def _refresh(self) -> None:
        color = self.current_color()
        self.preview.delete("all")
        self.preview.create_rectangle(0, 0, 282, 60, fill=color, outline="")
        self.preview.create_text(141, 30, text=color.upper(), fill="#061015")
        self.c1_button.configure(text=f"C1  {self.slots.c1.upper()}")
        self.c2_button.configure(text=f"C2  {self.slots.c2.upper()}")

    def accept(self) -> None:
        self.result = self.current_color()
        self.destroy()

    def cancel(self) -> None:
        self.result = None
        self.destroy()


def ask_point_color(master: tk.Misc, initial: str, slots_path: Path) -> str | None:
    dialog = PointColorDialog(master, initial, slots_path)
    master.wait_window(dialog)
    return dialog.result
