from __future__ import annotations

import json
import os
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

from .model import ALPHA_CONTROL_TYPES, ScuiControl, ScuiIssue, ScuiPanel

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_COMMAND = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]*$")


def _parse_sections(text: str) -> tuple[OrderedDict[str, OrderedDict[str, Any]], list[ScuiIssue]]:
    sections: OrderedDict[str, OrderedDict[str, Any]] = OrderedDict()
    issues: list[ScuiIssue] = []
    current: str | None = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#") or cleaned.startswith("//") or cleaned.startswith("@udata"):
            continue
        if cleaned.startswith("[") and cleaned.endswith("]"):
            name = cleaned[1:-1].strip()
            if not _IDENTIFIER.match(name):
                issues.append(ScuiIssue("error", f"line {line_number}", f"invalid section name: {name}"))
                current = None
                continue
            current = name
            sections.setdefault(name, OrderedDict())
            continue
        if current is None:
            issues.append(ScuiIssue("warning", f"line {line_number}", "entry before a valid section was skipped"))
            continue
        if not cleaned.endswith(";"):
            issues.append(ScuiIssue("warning", f"line {line_number}", "entry missing semicolon was skipped"))
            continue
        body = cleaned[:-1].strip()
        if ":" not in body:
            issues.append(ScuiIssue("warning", f"line {line_number}", "entry missing ':' was skipped"))
            continue
        key, raw = (part.strip() for part in body.split(":", 1))
        if not _IDENTIFIER.match(key):
            issues.append(ScuiIssue("warning", f"line {line_number}", f"invalid key was skipped: {key}"))
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            issues.append(ScuiIssue("warning", f"line {line_number}", f"invalid JSON value for {key}: {exc.msg}"))
            continue
        if key in sections[current]:
            issues.append(ScuiIssue("warning", f"line {line_number}", f"duplicate key; last valid value wins: {key}"))
        sections[current][key] = value
    return sections, issues


def _as_string(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_bool(value: Any, default: bool = True) -> bool:
    return value if isinstance(value, bool) else default


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return default


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def load_scui(path: Path) -> ScuiPanel:
    return parse_scui(Path(path).read_text(encoding="utf-8"))


def parse_scui(text: str) -> ScuiPanel:
    sections, issues = _parse_sections(text)
    panel_fields = sections.get("panel", OrderedDict())
    panel = ScuiPanel(
        schema_name=_as_string(panel_fields.get("schema_name"), ""),
        schema_major=_as_int(panel_fields.get("schema_major"), 0),
        schema_minor=_as_int(panel_fields.get("schema_minor"), 0),
        panel_id=_as_string(panel_fields.get("panel_id"), ""),
        title=_as_string(panel_fields.get("title"), ""),
        layout=_as_string(panel_fields.get("layout"), "stack"),
        help_topic=_as_string(panel_fields.get("help_topic"), ""),
        initial_values=dict(sections.get("state", {})),
        raw_sections={name: dict(values) for name, values in sections.items()},
        issues=list(issues),
    )

    if panel.schema_name != "signalcloud.scui":
        panel.issues.append(ScuiIssue("error", "panel.schema_name", "schema_name must be signalcloud.scui"))
    if panel.schema_major != 1:
        panel.issues.append(ScuiIssue("error", "panel.schema_major", "unsupported SCUI major version"))
    if not panel.panel_id or not _IDENTIFIER.match(panel.panel_id):
        panel.issues.append(ScuiIssue("error", "panel.panel_id", "panel_id is missing or invalid"))
    if not panel.title:
        panel.issues.append(ScuiIssue("warning", "panel.title", "panel title is empty"))

    seen: set[str] = set()
    for section_name, fields in sections.items():
        if not section_name.startswith("control."):
            continue
        control_id = section_name.removeprefix("control.")
        location = section_name
        if not control_id or not _IDENTIFIER.match(control_id):
            panel.issues.append(ScuiIssue("warning", location, "invalid control id; control skipped"))
            continue
        if control_id in seen:
            panel.issues.append(ScuiIssue("warning", location, "duplicate control id; later section skipped"))
            continue
        seen.add(control_id)
        control_type = _as_string(fields.get("type"), "unsupported")
        choices_value = fields.get("choices", [])
        choices = tuple(item for item in choices_value if isinstance(item, str)) if isinstance(choices_value, list) else ()
        control = ScuiControl(
            control_id=control_id,
            control_type=control_type,
            label=_as_string(fields.get("label")),
            value_binding=_as_string(fields.get("value_binding")),
            document_binding=_as_string(fields.get("document_binding")),
            order=_as_int(fields.get("order"), 0),
            minimum=_as_float(fields.get("minimum")),
            maximum=_as_float(fields.get("maximum")),
            step=_as_float(fields.get("step")),
            choices=choices,
            command_id=_as_string(fields.get("command_id")),
            enabled=_as_bool(fields.get("enabled"), True),
            visible=_as_bool(fields.get("visible"), True),
            style_role=_as_string(fields.get("style_role")),
            tooltip=_as_string(fields.get("tooltip")),
            help_topic=_as_string(fields.get("help_topic")),
            raw_fields=dict(fields),
        )
        if control_type not in ALPHA_CONTROL_TYPES:
            panel.issues.append(ScuiIssue("warning", f"{location}.type", f"unsupported control type: {control_type}"))
        if control.command_id and not _COMMAND.match(control.command_id):
            panel.issues.append(ScuiIssue("warning", f"{location}.command_id", "invalid command id; command blocked"))
            control.command_id = ""
        if control.minimum is not None and control.maximum is not None and control.minimum > control.maximum:
            panel.issues.append(ScuiIssue("warning", location, "minimum exceeds maximum; values were swapped"))
            control.minimum, control.maximum = control.maximum, control.minimum
        if control.step is not None and control.step <= 0:
            panel.issues.append(ScuiIssue("warning", f"{location}.step", "non-positive step ignored"))
            control.step = None
        if control.control_type in {"dropdown", "radio", "list", "tree"} and not control.choices:
            panel.issues.append(ScuiIssue("warning", f"{location}.choices", "choice control has no choices"))
        panel.controls.append(control)

    panel.controls.sort(key=lambda item: (item.order, item.control_id))
    return panel


def _merged_sections(panel: ScuiPanel) -> OrderedDict[str, OrderedDict[str, Any]]:
    merged: OrderedDict[str, OrderedDict[str, Any]] = OrderedDict(
        (name, OrderedDict(values)) for name, values in panel.raw_sections.items()
    )
    panel_section = merged.setdefault("panel", OrderedDict())
    panel_section.update(
        {
            "schema_name": panel.schema_name,
            "schema_major": panel.schema_major,
            "schema_minor": panel.schema_minor,
            "panel_id": panel.panel_id,
            "title": panel.title,
            "layout": panel.layout,
            "help_topic": panel.help_topic,
        }
    )
    state = merged.setdefault("state", OrderedDict())
    state.update(panel.initial_values)
    for control in panel.controls:
        section = merged.setdefault(f"control.{control.control_id}", OrderedDict(control.raw_fields))
        section.update(
            {
                "order": control.order,
                "type": control.control_type,
                "label": control.label,
                "value_binding": control.value_binding,
                "document_binding": control.document_binding,
                "command_id": control.command_id,
                "enabled": control.enabled,
                "visible": control.visible,
                "style_role": control.style_role,
                "tooltip": control.tooltip,
                "help_topic": control.help_topic,
            }
        )
        if control.minimum is not None:
            section["minimum"] = control.minimum
        if control.maximum is not None:
            section["maximum"] = control.maximum
        if control.step is not None:
            section["step"] = control.step
        if control.choices:
            section["choices"] = list(control.choices)
    return merged


def serialize_scui(panel: ScuiPanel) -> str:
    lines = ["@udata 1", ""]
    for section_name, values in _merged_sections(panel).items():
        lines.append(f"[{section_name}]")
        for key, value in values.items():
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False, separators=(',', ':'))};")
        lines.append("")
    return "\n".join(lines)


def save_scui_atomic(panel: ScuiPanel, path: Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".tmp")
    backup = destination.with_suffix(destination.suffix + ".bak")
    temp.write_text(serialize_scui(panel), encoding="utf-8")
    validation = load_scui(temp)
    if not validation.valid:
        temp.unlink(missing_ok=True)
        raise ValueError("temporary SCUI document failed validation")
    if destination.exists():
        backup.unlink(missing_ok=True)
        os.replace(destination, backup)
    os.replace(temp, destination)
    for parent in destination.resolve().parents:
        if parent.name == "content":
            from tools.asset_doctor.content_abi import write_asset_envelope
            write_asset_envelope(parent, destination.resolve())
            break
