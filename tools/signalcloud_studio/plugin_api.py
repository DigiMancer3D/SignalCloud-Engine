from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable

from .context import ToolContext


class ToolPlugin(ABC):
    """Canonical Studio tool contract.

    Shipped tools may initially open in their own top-level window while the
    canonical Studio host owns tool discovery, shared document context, and
    switching.  ``can_embed`` is the forward-compatible handoff point for A2
    SCUI/docked work areas. Runtime content remains data-only; this trusted
    Python plugin API is never an automatic native-mod loader.
    """

    key: str
    display_name: str
    description: str = ""
    category: str = "Authoring"
    can_embed: bool = False
    standalone_ready: bool = True

    @abstractmethod
    def launch(self, context: ToolContext) -> int:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class PluginInfo:
    key: str
    display_name: str
    description: str
    category: str = "Authoring"
    can_embed: bool = False
    standalone_ready: bool = True


class PluginCatalog:
    def __init__(self, plugins: Iterable[ToolPlugin] = ()) -> None:
        self._plugins: dict[str, ToolPlugin] = {}
        for plugin in plugins:
            self.register(plugin)

    def register(self, plugin: ToolPlugin) -> None:
        key = plugin.key.strip()
        if not key:
            raise ValueError("plugin key cannot be empty")
        if key in self._plugins:
            raise ValueError(f"plugin already registered: {key}")
        self._plugins[key] = plugin

    def get(self, key: str) -> ToolPlugin:
        try:
            return self._plugins[key]
        except KeyError as exc:
            raise KeyError(f"unknown Studio plugin: {key}") from exc

    def infos(self) -> tuple[PluginInfo, ...]:
        return tuple(
            PluginInfo(
                p.key,
                p.display_name,
                p.description,
                p.category,
                bool(p.can_embed),
                bool(p.standalone_ready),
            )
            for p in sorted(self._plugins.values(), key=lambda item: (item.category, item.display_name, item.key))
        )
