from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ALPHA_CONTROL_TYPES = frozenset(
    {
        "label",
        "button",
        "toggle",
        "radio",
        "dropdown",
        "number",
        "slider",
        "color",
        "list",
        "tree",
        "progress",
        "tabs",
        "graph-inspector",
        "confirmation",
    }
)


@dataclass(frozen=True, slots=True)
class ScuiIssue:
    severity: str
    location: str
    message: str


@dataclass(slots=True)
class ScuiControl:
    control_id: str
    control_type: str
    label: str = ""
    value_binding: str = ""
    document_binding: str = ""
    order: int = 0
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    choices: tuple[str, ...] = ()
    command_id: str = ""
    enabled: bool = True
    visible: bool = True
    style_role: str = ""
    tooltip: str = ""
    help_topic: str = ""
    raw_fields: dict[str, Any] = field(default_factory=dict)

    @property
    def supported_alpha_type(self) -> bool:
        return self.control_type in ALPHA_CONTROL_TYPES


@dataclass(slots=True)
class ScuiPanel:
    schema_name: str = "signalcloud.scui"
    schema_major: int = 1
    schema_minor: int = 0
    panel_id: str = ""
    title: str = ""
    layout: str = "stack"
    help_topic: str = ""
    controls: list[ScuiControl] = field(default_factory=list)
    initial_values: dict[str, Any] = field(default_factory=dict)
    raw_sections: dict[str, dict[str, Any]] = field(default_factory=dict)
    issues: list[ScuiIssue] = field(default_factory=list)

    def control(self, control_id: str) -> ScuiControl:
        for control in self.controls:
            if control.control_id == control_id:
                return control
        raise KeyError(control_id)

    @property
    def valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


@dataclass(slots=True)
class ScuiPanelState:
    values: dict[str, Any] = field(default_factory=dict)
    selection: dict[str, Any] = field(default_factory=dict)
    validation: list[str] = field(default_factory=list)
    dirty: bool = False
    preview_status: str = "idle"
    blocked_events: list["ScuiPanelEvent"] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ScuiPanelEvent:
    panel_id: str
    control_id: str
    command_id: str
    payload: dict[str, Any]
    transaction_id: str
