from __future__ import annotations

from pathlib import Path
from tkinter import ttk
from typing import Callable

from ..commands import CommandRegistry
from .codec import load_scui
from .model import ScuiPanelEvent, ScuiPanelState
from .tk_renderer import ScuiTkRenderer


def proof_panel_path(project_root: Path) -> Path:
    return Path(project_root) / "content" / "core" / "ui" / "authoring_lab_project_selector.scui"


def build_proof_registry(status: Callable[[str], None] | None = None) -> CommandRegistry:
    registry = CommandRegistry()

    def handled(name: str):
        def handler(event: ScuiPanelEvent) -> None:
            if status is not None:
                status(f"{name}: {event.payload.get('value')}")
        return handler

    registry.register("authoring.project.select", handled("Project selected"), description="Select the authoring-lab project")
    registry.register("authoring.preview.toggle", handled("Safe preview"), description="Toggle non-destructive preview")
    registry.register("authoring.point_budget.set", handled("Point budget"), description="Change preview point budget")
    registry.register("authoring.profile.refresh", handled("Profile refresh"), description="Refresh machine-profile summary")
    return registry


def mount_proof_panel(parent: ttk.Frame, project_root: Path, status: Callable[[str], None]) -> ScuiTkRenderer:
    panel = load_scui(proof_panel_path(project_root))
    state = ScuiPanelState(values=dict(panel.initial_values))
    renderer = ScuiTkRenderer(
        parent,
        panel,
        state=state,
        registry=build_proof_registry(status),
        on_status=status,
    )
    renderer.frame.pack(fill="both", expand=True)
    return renderer
