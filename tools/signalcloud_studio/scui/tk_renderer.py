from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable

from ..commands import CommandRegistry
from ..ui.tooltips import ToolTip
from .codec import load_scui
from .dispatch import ScuiDispatcher
from .model import ScuiControl, ScuiPanel, ScuiPanelEvent, ScuiPanelState


class ScuiTkRenderer:
    """Render a validated SCUI panel with ordinary Tk/ttk widgets."""

    SUPPORTED_TYPES = frozenset({"label", "button", "toggle", "radio", "dropdown", "number", "slider", "color", "list", "tree", "progress", "graph-inspector", "confirmation"})

    def __init__(
        self,
        parent: tk.Misc,
        panel: ScuiPanel,
        *,
        state: ScuiPanelState | None = None,
        registry: CommandRegistry | None = None,
        on_event: Callable[[ScuiPanelEvent], None] | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        self.parent = parent
        self.panel = panel
        self.state = state or ScuiPanelState(values=dict(panel.initial_values))
        for key, value in panel.initial_values.items():
            self.state.values.setdefault(key, value)
        self.registry = registry or CommandRegistry()
        self.on_event = on_event
        self.on_status = on_status
        self.dispatcher = ScuiDispatcher(self.registry, self.state, telemetry=self._blocked)
        self.variables: dict[str, tk.Variable] = {}
        self.widgets: dict[str, tk.Widget] = {}
        self.value_labels: dict[str, ttk.Label] = {}
        self._ready = False
        self._wrap_labels: list[ttk.Label] = []
        self.frame = ttk.Frame(parent, padding=10)
        self._build()
        self.frame.bind("<Configure>", self._update_wrap_lengths, add="+")
        self.frame.after_idle(self._update_wrap_lengths)
        self._ready = True

    def _blocked(self, event: ScuiPanelEvent, reason: str) -> None:
        if self.on_status is not None:
            self.on_status(f"Blocked {event.command_id}: {reason}")

    def _initial(self, control: ScuiControl, default: Any = "") -> Any:
        if control.value_binding:
            return self.state.values.get(control.value_binding, default)
        return default

    def _emit(self, control: ScuiControl, value: Any) -> None:
        if not self._ready:
            return
        if control.value_binding:
            self.state.values[control.value_binding] = value
            self.state.dirty = True
        event = self.dispatcher.emit(
            panel_id=self.panel.panel_id,
            control_id=control.control_id,
            command_id=control.command_id,
            payload={"value": value, "binding": control.value_binding},
        )
        if self.on_event is not None:
            self.on_event(event)
        if self.on_status is not None and control.command_id and event not in self.state.blocked_events:
            self.on_status(f"{control.label or control.control_id}: {value}")

    def _variable(self, control: ScuiControl) -> tk.Variable:
        initial = self._initial(control)
        if control.control_type == "toggle":
            variable: tk.Variable = tk.BooleanVar(self.frame, value=bool(initial))
        elif control.control_type in {"slider", "number", "progress"}:
            try:
                numeric = float(initial)
            except (TypeError, ValueError):
                numeric = control.minimum or 0.0
            variable = tk.DoubleVar(self.frame, value=numeric)
        else:
            variable = tk.StringVar(self.frame, value=str(initial if initial is not None else ""))
        self.variables[control.control_id] = variable
        return variable

    def _set_state(self, widget: tk.Widget, control: ScuiControl) -> None:
        if not control.enabled:
            try:
                widget.configure(state="disabled")
            except tk.TclError:
                pass
        if control.tooltip:
            ToolTip(widget, control.tooltip)

    def _build(self) -> None:
        title = ttk.Label(self.frame, text=self.panel.title, font=("Sans", 13, "bold"))
        title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        row = 1
        for control in self.panel.controls:
            if not control.visible:
                continue
            if control.control_type not in self.SUPPORTED_TYPES:
                placeholder = ttk.Label(
                    self.frame,
                    text=f"{control.label or control.control_id} — unsupported control: {control.control_type}",
                    justify="left",
                    anchor="w",
                )
                placeholder.grid(row=row, column=0, columnspan=3, sticky="ew", pady=3)
                self._wrap_labels.append(placeholder)
                self.widgets[control.control_id] = placeholder
                row += 1
                continue
            if control.control_type == "label":
                widget = ttk.Label(
                    self.frame, text=control.label, justify="left", anchor="w"
                )
                widget.grid(row=row, column=0, columnspan=3, sticky="ew", pady=3)
                self._wrap_labels.append(widget)
            elif control.control_type == "button":
                widget = ttk.Button(
                    self.frame,
                    text=control.label or control.control_id,
                    command=lambda item=control: self._emit(item, True),
                )
                widget.grid(row=row, column=0, columnspan=3, sticky="w", pady=3)
            elif control.control_type == "confirmation":
                widget = ttk.Button(
                    self.frame,
                    text=control.label or "Confirm",
                    command=lambda item=control: self._emit(item, "confirmed"),
                )
                widget.grid(row=row, column=0, columnspan=3, sticky="w", pady=3)
            elif control.control_type == "toggle":
                variable = self._variable(control)
                widget = ttk.Checkbutton(
                    self.frame,
                    text=control.label,
                    variable=variable,
                    command=lambda item=control, var=variable: self._emit(item, bool(var.get())),
                )
                widget.grid(row=row, column=0, columnspan=3, sticky="w", pady=3)
            elif control.control_type == "radio":
                ttk.Label(self.frame, text=control.label).grid(row=row, column=0, sticky="w", pady=3)
                variable = self._variable(control)
                holder = ttk.Frame(self.frame)
                holder.grid(row=row, column=1, columnspan=2, sticky="w")
                for choice in control.choices:
                    ttk.Radiobutton(
                        holder,
                        text=choice,
                        value=choice,
                        variable=variable,
                        command=lambda item=control, var=variable: self._emit(item, var.get()),
                    ).pack(side="left", padx=(0, 6))
                widget = holder
            elif control.control_type == "dropdown":
                ttk.Label(self.frame, text=control.label).grid(row=row, column=0, sticky="w", pady=3)
                variable = self._variable(control)
                combo = ttk.Combobox(self.frame, textvariable=variable, values=control.choices, state="readonly")
                combo.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
                combo.bind("<<ComboboxSelected>>", lambda _event, item=control, var=variable: self._emit(item, var.get()))
                widget = combo
            elif control.control_type == "number":
                ttk.Label(self.frame, text=control.label).grid(row=row, column=0, sticky="w", pady=3)
                variable = self._variable(control)
                spin = ttk.Spinbox(
                    self.frame,
                    textvariable=variable,
                    from_=control.minimum if control.minimum is not None else -1_000_000,
                    to=control.maximum if control.maximum is not None else 1_000_000,
                    increment=control.step if control.step is not None else 1,
                    command=lambda item=control, var=variable: self._emit(item, float(var.get())),
                )
                spin.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
                spin.bind("<Return>", lambda _event, item=control, var=variable: self._emit(item, float(var.get())))
                widget = spin
            elif control.control_type == "slider":
                ttk.Label(self.frame, text=control.label).grid(row=row, column=0, sticky="w", pady=3)
                variable = self._variable(control)
                scale = ttk.Scale(
                    self.frame,
                    variable=variable,
                    from_=control.minimum if control.minimum is not None else 0.0,
                    to=control.maximum if control.maximum is not None else 100.0,
                    command=lambda raw, item=control: self._slider_changed(item, raw),
                )
                scale.grid(row=row, column=1, sticky="ew", pady=3)
                value_label = ttk.Label(self.frame, width=12, anchor="e")
                value_label.grid(row=row, column=2, sticky="e")
                self.value_labels[control.control_id] = value_label
                self._update_value_label(control, float(variable.get()))
                widget = scale
            elif control.control_type == "color":
                ttk.Label(self.frame, text=control.label).grid(row=row, column=0, sticky="w", pady=3)
                variable = self._variable(control)
                entry = ttk.Entry(self.frame, textvariable=variable)
                entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
                entry.bind("<Return>", lambda _event, item=control, var=variable: self._emit(item, var.get()))
                widget = entry
            elif control.control_type in {"list", "tree", "graph-inspector"}:
                ttk.Label(self.frame, text=control.label).grid(row=row, column=0, sticky="nw", pady=3)
                tree = ttk.Treeview(self.frame, show="tree", height=min(5, max(2, len(control.choices))))
                for choice in control.choices:
                    tree.insert("", "end", text=choice)
                tree.grid(row=row, column=1, columnspan=2, sticky="nsew", pady=3)
                tree.bind(
                    "<<TreeviewSelect>>",
                    lambda _event, item=control, view=tree: self._emit(
                        item, view.item(view.selection()[0], "text") if view.selection() else ""
                    ),
                )
                widget = tree
            elif control.control_type == "progress":
                ttk.Label(self.frame, text=control.label).grid(row=row, column=0, sticky="w", pady=3)
                variable = self._variable(control)
                progress = ttk.Progressbar(
                    self.frame,
                    variable=variable,
                    maximum=control.maximum if control.maximum is not None else 100.0,
                )
                progress.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
                widget = progress
            else:  # defensive fallback
                widget = ttk.Label(self.frame, text=f"{control.label}: unsupported")
                widget.grid(row=row, column=0, columnspan=3, sticky="w", pady=3)
            self.widgets[control.control_id] = widget
            self._set_state(widget, control)
            row += 1
        self.frame.columnconfigure(1, weight=1)


    def _update_wrap_lengths(self, _event: tk.Event | None = None) -> None:
        width = max(240, min(1400, self.frame.winfo_width() - 28))
        for label in self._wrap_labels:
            try:
                label.configure(wraplength=width)
            except tk.TclError:
                continue

    def _slider_changed(self, control: ScuiControl, raw: str) -> None:
        value = float(raw)
        if control.step:
            value = round(value / control.step) * control.step
        self._update_value_label(control, value)
        self._emit(control, value)

    def _update_value_label(self, control: ScuiControl, value: float) -> None:
        label = self.value_labels.get(control.control_id)
        if label is not None:
            label.configure(text=f"{value:g}")

    def get_value(self, binding: str, default: Any = None) -> Any:
        return self.state.values.get(binding, default)

    def set_value(self, binding: str, value: Any) -> None:
        self.state.values[binding] = value
        for control in self.panel.controls:
            if control.value_binding != binding:
                continue
            variable = self.variables.get(control.control_id)
            if variable is not None:
                variable.set(value)
            if control.control_type == "slider":
                try:
                    self._update_value_label(control, float(value))
                except (TypeError, ValueError):
                    pass


class ScuiPanelWindow(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        panel_path: Path,
        *,
        registry: CommandRegistry | None = None,
    ) -> None:
        super().__init__(parent)
        panel = load_scui(panel_path)
        self.title(f"SCUI Preview — {panel.title}")
        self.geometry("620x520")
        self.status = tk.StringVar(value="Ready")
        renderer = ScuiTkRenderer(self, panel, registry=registry, on_status=self.status.set)
        renderer.frame.pack(fill="both", expand=True)
        ttk.Label(self, textvariable=self.status, padding=(10, 4)).pack(fill="x")
        self.renderer = renderer
