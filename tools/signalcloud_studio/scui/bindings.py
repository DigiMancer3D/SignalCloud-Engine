from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .model import ScuiControl, ScuiPanel, ScuiPanelState


def safe_project_path(project_root: Path, value: str | Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    candidate = Path(value).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("SCUI document binding must remain inside the SignalCloud project root") from exc
    return resolved


def _parts(path: str) -> tuple[str | int, ...]:
    result: list[str | int] = []
    for part in path.split("."):
        cleaned = part.strip()
        if not cleaned:
            raise ValueError("document binding contains an empty path component")
        result.append(int(cleaned) if cleaned.isdigit() else cleaned)
    return tuple(result)


def get_json_path(document: Any, path: str, default: Any = None) -> Any:
    current = document
    try:
        for part in _parts(path):
            if isinstance(part, int):
                if not isinstance(current, list):
                    return default
                current = current[part]
            else:
                if not isinstance(current, dict):
                    return default
                current = current[part]
        return current
    except (IndexError, KeyError, TypeError, ValueError):
        return default


def set_json_path(document: dict[str, Any], path: str, value: Any) -> None:
    parts = _parts(path)
    if not parts:
        raise ValueError("document binding is empty")
    current: Any = document
    for index, part in enumerate(parts[:-1]):
        next_part = parts[index + 1]
        if isinstance(part, int):
            if not isinstance(current, list):
                raise ValueError(f"expected a list at path component {part}")
            while len(current) <= part:
                current.append({} if isinstance(next_part, str) else [])
            if not isinstance(current[part], (dict, list)):
                current[part] = {} if isinstance(next_part, str) else []
            current = current[part]
        else:
            if not isinstance(current, dict):
                raise ValueError(f"expected an object at path component {part}")
            if part not in current or not isinstance(current[part], (dict, list)):
                current[part] = {} if isinstance(next_part, str) else []
            current = current[part]
    final = parts[-1]
    if isinstance(final, int):
        if not isinstance(current, list):
            raise ValueError(f"expected a list at final path component {final}")
        while len(current) <= final:
            current.append(None)
        current[final] = value
    else:
        if not isinstance(current, dict):
            raise ValueError(f"expected an object at final path component {final}")
        current[final] = value


def _parse_udata_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def read_native_state_overlay(path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    section = ""
    for line in lines:
        cleaned = line.strip()
        if not cleaned or cleaned.startswith(("#", "//", "@udata")):
            continue
        if cleaned.startswith("[") and cleaned.endswith("]"):
            section = cleaned[1:-1].strip()
            continue
        if section != "state" or not cleaned.endswith(";") or ":" not in cleaned:
            continue
        key, raw = cleaned[:-1].split(":", 1)
        key = key.strip()
        value = _parse_udata_value(raw.strip())
        if key and value is not None:
            values[key] = value
    return values


def write_native_state_overlay(
    path: Path,
    *,
    panel_id: str,
    source_document: str,
    values: dict[str, Any],
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    backup = destination.with_suffix(destination.suffix + ".bak")
    lines = [
        "@udata 1",
        "",
        "[panel]",
        f"panel_id: {json.dumps(panel_id)};",
        f"source_document: {json.dumps(source_document)};",
        'mode: "desktop-synchronized-overlay";',
        "",
        "[state]",
    ]
    for key in sorted(values):
        value = values[key]
        if isinstance(value, (bool, int, float, str)) and not isinstance(value, complex):
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)};")
    lines.append("")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    if destination.exists():
        backup.unlink(missing_ok=True)
        os.replace(destination, backup)
    os.replace(temporary, destination)


@dataclass(slots=True)
class JsonDocumentBinding:
    project_root: Path
    source_path: Path
    output_path: Path
    data: dict[str, Any]
    dirty: bool = False

    @classmethod
    def open(cls, project_root: Path, source: str | Path, output: str | Path | None = None) -> "JsonDocumentBinding":
        source_path = safe_project_path(project_root, source)
        output_path = safe_project_path(project_root, output or source)
        raw = json.loads(source_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("managed SCUI JSON document must contain a top-level object")
        return cls(Path(project_root).resolve(), source_path, output_path, raw)

    def hydrate(self, panel: ScuiPanel, state: ScuiPanelState, *, overlay: dict[str, Any] | None = None) -> None:
        for control in panel.controls:
            if not control.value_binding:
                continue
            value = None
            found = False
            if control.document_binding:
                marker = object()
                value = get_json_path(self.data, control.document_binding, marker)
                found = value is not marker
            if not found:
                value = state.values.get(control.value_binding, panel.initial_values.get(control.value_binding))
            state.values[control.value_binding] = value
        for key, value in (overlay or {}).items():
            if key in state.values:
                state.values[key] = value

    def apply(self, control: ScuiControl, value: Any) -> bool:
        if not control.document_binding:
            return False
        set_json_path(self.data, control.document_binding, value)
        self.dirty = True
        return True

    def reload(self) -> None:
        raw = json.loads(self.source_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("managed SCUI JSON document must contain a top-level object")
        self.data = raw
        self.dirty = False

    def save_atomic(self) -> Path:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.output_path.with_suffix(self.output_path.suffix + ".tmp")
        backup = self.output_path.with_suffix(self.output_path.suffix + ".bak")
        temporary.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        check = json.loads(temporary.read_text(encoding="utf-8"))
        if not isinstance(check, dict):
            temporary.unlink(missing_ok=True)
            raise ValueError("temporary managed document failed validation")
        if self.output_path.exists():
            backup.unlink(missing_ok=True)
            os.replace(self.output_path, backup)
        os.replace(temporary, self.output_path)
        try:
            content_root = self.project_root / "content"
            self.output_path.relative_to(content_root)
            if self.output_path.suffix.lower() in {".slight", ".sclight", ".scui", ".pcp3"}:
                from tools.asset_doctor.content_abi import write_asset_envelope
                write_asset_envelope(content_root, self.output_path)
        except ValueError:
            pass
        self.source_path = self.output_path
        self.dirty = False
        return self.output_path


def panel_path_field(panel: ScuiPanel, key: str) -> str:
    value = panel.raw_sections.get("panel", {}).get(key, "")
    return value if isinstance(value, str) else ""


def binding_controls(panel: ScuiPanel) -> tuple[ScuiControl, ...]:
    return tuple(control for control in panel.controls if control.document_binding)
