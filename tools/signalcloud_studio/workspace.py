from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(slots=True)
class PaneState:
    depth: float = 0.0
    zoom: float = 28.0
    pan_x: float = 0.0
    pan_y: float = 0.0

    @classmethod
    def from_json(cls, value: Any) -> "PaneState":
        if not isinstance(value, dict):
            return cls()
        return cls(
            depth=float(value.get("depth", 0.0)),
            zoom=max(2.0, min(400.0, float(value.get("zoom", 28.0)))),
            pan_x=float(value.get("pan_x", 0.0)),
            pan_y=float(value.get("pan_y", 0.0)),
        )

    def to_json(self) -> dict[str, float]:
        return {
            "depth": self.depth,
            "zoom": self.zoom,
            "pan_x": self.pan_x,
            "pan_y": self.pan_y,
        }


class WorkspaceLayoutStore:
    """Forgiving, atomic storage for Studio workspace preferences.

    Unknown keys are retained by ``merge`` so newer or tool-specific layout
    settings survive older editors. Invalid or absent files resolve to an empty
    mapping instead of blocking tool startup.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @classmethod
    def for_project(cls, project_root: Path, filename: str = "pcp3_workspace.json") -> "WorkspaceLayoutStore":
        return cls(Path(project_root).expanduser().resolve() / "config" / filename)

    def read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError, TypeError):
            return {}

    def write(self, data: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(dict(data), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def merge(self, updates: Mapping[str, Any]) -> dict[str, Any]:
        value = self.read()
        value.update(dict(updates))
        self.write(value)
        return value
