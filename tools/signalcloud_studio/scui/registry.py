from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .bindings import safe_project_path
from .codec import load_scui

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


@dataclass(frozen=True, slots=True)
class ScuiRegistryIssue:
    severity: str
    location: str
    message: str


@dataclass(slots=True)
class ScuiRegistryEntry:
    key: str
    panel_id: str
    label: str
    relative_path: str
    safe_room_only: bool = True
    shortcut: str = ""
    commands: tuple[str, ...] = ()
    native_state_path: str = ""
    default_document: str = ""
    preview_kind: str = ""
    unknown_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScuiPanelRegistry:
    project_root: Path
    registry_path: Path
    default_panel: str = ""
    selector_panel: str = ""
    entries: list[ScuiRegistryEntry] = field(default_factory=list)
    issues: list[ScuiRegistryIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return bool(self.entries) and not any(issue.severity == "error" for issue in self.issues)

    def get(self, key: str) -> ScuiRegistryEntry:
        for entry in self.entries:
            if entry.key == key:
                return entry
        raise KeyError(key)

    def keys(self) -> tuple[str, ...]:
        return tuple(entry.key for entry in self.entries)

    @classmethod
    def load(cls, project_root: Path, registry_path: str | Path = "content/core/ui/scui_panel_registry.udata") -> "ScuiPanelRegistry":
        root = Path(project_root).expanduser().resolve()
        path = safe_project_path(root, registry_path)
        registry = cls(root, path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            registry.issues.append(ScuiRegistryIssue("error", str(path), str(exc)))
            return registry

        sections: dict[str, dict[str, Any]] = {}
        current = ""
        for line_number, line in enumerate(text.splitlines(), start=1):
            cleaned = line.strip()
            if not cleaned or cleaned.startswith(("#", "//", "@udata")):
                continue
            if cleaned.startswith("[") and cleaned.endswith("]"):
                current = cleaned[1:-1].strip()
                if not _IDENTIFIER.match(current):
                    registry.issues.append(ScuiRegistryIssue("error", f"line {line_number}", "invalid section name"))
                    current = ""
                else:
                    sections.setdefault(current, {})
                continue
            if not current or not cleaned.endswith(";") or ":" not in cleaned:
                registry.issues.append(ScuiRegistryIssue("warning", f"line {line_number}", "malformed entry skipped"))
                continue
            key, raw = (part.strip() for part in cleaned[:-1].split(":", 1))
            try:
                sections[current][key] = json.loads(raw)
            except json.JSONDecodeError:
                registry.issues.append(ScuiRegistryIssue("warning", f"line {line_number}", f"invalid JSON for {key}"))

        meta = sections.get("registry", {})
        if meta.get("schema_name") != "signalcloud.scui.registry":
            registry.issues.append(ScuiRegistryIssue("error", "registry.schema_name", "invalid registry schema"))
        if meta.get("schema_major") != 1:
            registry.issues.append(ScuiRegistryIssue("error", "registry.schema_major", "unsupported registry version"))
        registry.default_panel = meta.get("default_panel") if isinstance(meta.get("default_panel"), str) else ""
        registry.selector_panel = meta.get("selector_panel") if isinstance(meta.get("selector_panel"), str) else ""

        seen_ids: set[str] = set()
        for section, fields in sections.items():
            if not section.startswith("panel."):
                continue
            key = section.removeprefix("panel.")
            panel_id = fields.get("panel_id")
            label = fields.get("label")
            relative_path = fields.get("path")
            if not all(isinstance(value, str) and value for value in (key, panel_id, relative_path)):
                registry.issues.append(ScuiRegistryIssue("warning", section, "missing key, panel_id, or path"))
                continue
            try:
                panel_path = safe_project_path(root, relative_path)
            except ValueError:
                registry.issues.append(ScuiRegistryIssue("warning", f"{section}.path", "path escapes project root"))
                continue
            panel = load_scui(panel_path)
            if not panel.valid or panel.panel_id != panel_id:
                registry.issues.append(ScuiRegistryIssue("warning", section, "panel validation or panel_id match failed"))
                continue
            if panel_id in seen_ids:
                registry.issues.append(ScuiRegistryIssue("warning", section, "duplicate panel_id"))
                continue
            seen_ids.add(panel_id)
            commands_raw = fields.get("commands", [])
            commands = tuple(value for value in commands_raw if isinstance(value, str)) if isinstance(commands_raw, list) else ()
            known = {
                "panel_id", "label", "path", "safe_room_only", "shortcut", "commands",
                "native_state_path", "default_document", "preview_kind",
            }
            registry.entries.append(
                ScuiRegistryEntry(
                    key=key,
                    panel_id=panel_id,
                    label=label if isinstance(label, str) and label else key,
                    relative_path=relative_path,
                    safe_room_only=fields.get("safe_room_only") if isinstance(fields.get("safe_room_only"), bool) else True,
                    shortcut=fields.get("shortcut") if isinstance(fields.get("shortcut"), str) else "",
                    commands=commands,
                    native_state_path=fields.get("native_state_path") if isinstance(fields.get("native_state_path"), str) else "",
                    default_document=fields.get("default_document") if isinstance(fields.get("default_document"), str) else "",
                    preview_kind=fields.get("preview_kind") if isinstance(fields.get("preview_kind"), str) else "",
                    unknown_fields={name: value for name, value in fields.items() if name not in known},
                )
            )
        registry.entries.sort(key=lambda entry: entry.key)
        if registry.default_panel and registry.default_panel not in registry.keys():
            registry.issues.append(ScuiRegistryIssue("warning", "registry.default_panel", "default panel missing"))
        return registry
