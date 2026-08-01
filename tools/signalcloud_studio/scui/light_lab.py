from __future__ import annotations

import json
import os
from pathlib import Path
from tkinter import ttk
from typing import Callable

from ..commands import CommandRegistry
from ..context import ToolContext
from ..documents import StudioDocumentContext
from .bindings import (
    JsonDocumentBinding,
    panel_path_field,
    read_native_state_overlay,
    write_native_state_overlay,
    safe_project_path,
    set_json_path,
)
from .codec import load_scui
from .model import ScuiPanelEvent, ScuiPanelState
from .tk_renderer import ScuiTkRenderer


LIGHT_COMMANDS = (
    "light.scope.set",
    "light.illuminosity.set",
    "light.radius.set",
    "light.day_illuminosity.set",
    "light.night_illuminosity.set",
    "light.time_of_day.set",
    "light.timeline.play",
    "light.timeline.pause",
    "light.timeline.stop",
    "light.probe.sample",
    "light.diagnostics.bake",
    "light.document.reload",
    "light.document.save",
)


def light_panel_path(project_root: Path) -> Path:
    return Path(project_root) / "content" / "core" / "ui" / "light_lab_control_surface.scui"


class LightLabScuiSession:
    def __init__(self, context: ToolContext, status: Callable[[str], None]) -> None:
        self.context = context
        self.status = status
        self.panel = load_scui(light_panel_path(context.project_root))
        self.state = ScuiPanelState(values=dict(self.panel.initial_values))
        self.binding = self._open_binding()
        overlay_path = panel_path_field(self.panel, "native_state_path")
        overlay = read_native_state_overlay(safe_project_path(context.project_root, overlay_path)) if overlay_path else {}
        self.binding.hydrate(self.panel, self.state, overlay=overlay)
        self.renderer: ScuiTkRenderer | None = None

    def _open_binding(self) -> JsonDocumentBinding:
        shared = self.context.document_context
        if shared is None and self.context.document_store is not None:
            shared = self.context.document_store.read()
            self.context.document_context = shared
        default_document = panel_path_field(self.panel, "default_document")
        managed_output = panel_path_field(self.panel, "managed_output")
        source = default_document
        output = managed_output or default_document
        if shared is not None and shared.active_document and shared.document_kind == "light_set":
            source = shared.active_document
            output = shared.active_document
        if not source:
            raise ValueError("Light Lab SCUI panel is missing default_document")
        return JsonDocumentBinding.open(self.context.project_root, source, output)

    def _publish(self, path: Path, *, dirty: bool) -> None:
        if self.context.document_store is None:
            return
        updated = self.context.document_store.publish(
            self.context.document_context,
            active_document=path,
            document_kind="light_set",
            owner_tool="light-lab-scui",
            dirty=dirty,
            metadata={
                "panel_id": self.panel.panel_id,
                "source": "scui-managed-binding",
            },
        )
        self.context.document_context = updated
        if self.context.document_bus is not None:
            self.context.document_bus.publish(updated)

    def registry(self) -> CommandRegistry:
        registry = CommandRegistry()

        def apply(event: ScuiPanelEvent) -> None:
            control = self.panel.control(event.control_id)
            if self.binding.apply(control, event.payload.get("value")):
                self.state.dirty = True
                self._publish(self.binding.output_path, dirty=True)
                self.status(f"Light preview changed: {control.label}")

        for command in LIGHT_COMMANDS:
            if command not in {"light.timeline.play", "light.timeline.pause", "light.timeline.stop", "light.probe.sample", "light.diagnostics.bake", "light.document.reload", "light.document.save"}:
                registry.register(command, apply, description=f"Apply {command} to managed light document")

        def reload_document(_event: ScuiPanelEvent) -> None:
            self.binding.reload()
            self.binding.hydrate(self.panel, self.state)
            if self.renderer is not None:
                for control in self.panel.controls:
                    if control.value_binding:
                        self.renderer.set_value(control.value_binding, self.state.values.get(control.value_binding))
            self.state.dirty = False
            self.status(f"Reloaded {self.binding.source_path.name}")

        def save_document(_event: ScuiPanelEvent) -> None:
            path = self.binding.save_atomic()
            overlay_value = panel_path_field(self.panel, "native_state_path")
            if overlay_value:
                overlay_path = safe_project_path(self.context.project_root, overlay_value)
                write_native_state_overlay(
                    overlay_path,
                    panel_id=self.panel.panel_id,
                    source_document=path.relative_to(self.context.project_root).as_posix(),
                    values=dict(self.state.values),
                )
            self.state.dirty = False
            self._publish(path, dirty=False)
            self.status(f"Saved managed light set and synchronized native overlay: {path.name}")

        def timeline_play(_event: ScuiPanelEvent) -> None:
            set_json_path(self.binding.data, "day_night.playing", True)
            set_json_path(self.binding.data, "day_night.paused", False)
            self.binding.dirty = True
            self.state.dirty = True
            self.status("Day/night timeline playing in the managed document")

        def timeline_pause(_event: ScuiPanelEvent) -> None:
            set_json_path(self.binding.data, "day_night.playing", True)
            set_json_path(self.binding.data, "day_night.paused", True)
            self.binding.dirty = True
            self.state.dirty = True
            self.status("Day/night timeline paused")

        def timeline_stop(_event: ScuiPanelEvent) -> None:
            set_json_path(self.binding.data, "day_night.playing", False)
            set_json_path(self.binding.data, "day_night.paused", False)
            set_json_path(self.binding.data, "day_night.time_of_day", 0.35)
            self.state.values["time_of_day"] = 0.35
            if self.renderer is not None:
                self.renderer.set_value("time_of_day", 0.35)
            self.binding.dirty = True
            self.state.dirty = True
            self.status("Day/night timeline stopped and reset to 0.35")

        def probe_surface(_event: ScuiPanelEvent) -> None:
            time_of_day = float(self.state.values.get("time_of_day", 0.35))
            day_i = float(self.state.values.get("day_i", 95.0))
            night_i = float(self.state.values.get("night_i", 18.0))
            light_i = float(self.state.values.get("light_i", 72.0))
            night_weight = max(0.0, min(1.0, (0.25 - time_of_day) * 4.0 if time_of_day < 0.25 else (time_of_day - 0.75) * 4.0 if time_of_day > 0.75 else 0.0))
            effective = day_i * (1.0 - night_weight) + night_i * night_weight + light_i * 0.55
            quality = "DARKNESS" if effective <= 3 else "OUTLINES" if effective <= 29 else "LOW" if effective <= 65 else "GOOD" if effective <= 77 else "GREAT" if effective <= 89 else "BEST" if effective <= 110 else "BOOSTED"
            self.status(f"Surface probe: {effective:.1f} i% · {quality}")

        def bake_diagnostics(_event: ScuiPanelEvent) -> None:
            report = safe_project_path(self.context.project_root, "reports/illuminosity_scui_bake.json")
            report.parent.mkdir(parents=True, exist_ok=True)
            temporary = report.with_suffix(report.suffix + ".tmp")
            payload = {
                "schema": "signalcloud_illuminosity_scui_bake_v1",
                "panel_id": self.panel.panel_id,
                "source_document": self.binding.source_path.relative_to(self.context.project_root).as_posix(),
                "state": dict(sorted(self.state.values.items())),
                "data_only": True,
            }
            temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(temporary, report)
            self.status(f"Baked bounded SCUI diagnostic snapshot: {report.name}")

        registry.register("light.timeline.play", timeline_play, description="Play managed day/night timeline")
        registry.register("light.timeline.pause", timeline_pause, description="Pause managed day/night timeline")
        registry.register("light.timeline.stop", timeline_stop, description="Stop managed day/night timeline")
        registry.register("light.probe.sample", probe_surface, description="Probe managed light quality")
        registry.register("light.diagnostics.bake", bake_diagnostics, description="Bake managed light diagnostics")
        registry.register("light.document.reload", reload_document, description="Reload managed light document")
        registry.register("light.document.save", save_document, description="Save managed light document")
        return registry


def mount_light_lab_panel(parent: ttk.Frame, context: ToolContext, status: Callable[[str], None]) -> LightLabScuiSession:
    session = LightLabScuiSession(context, status)
    renderer = ScuiTkRenderer(
        parent,
        session.panel,
        state=session.state,
        registry=session.registry(),
        on_status=status,
    )
    renderer.frame.pack(fill="both", expand=True)
    session.renderer = renderer
    status(
        f"Mounted Light Lab SCUI · source {session.binding.source_path.name} · save target {session.binding.output_path.name}"
    )
    return session
