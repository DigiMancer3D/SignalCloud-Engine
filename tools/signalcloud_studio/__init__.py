"""SignalCloud Studio canonical tool-shell package."""

from .context import ToolContext
from .plugin_api import ToolPlugin, PluginCatalog, PluginInfo
from .commands import CommandRegistry, CommandDispatchError
from .workspace import PaneState, WorkspaceLayoutStore
from .scui import ScuiPanel, ScuiPanelEvent, ScuiPanelState, ScuiTkRenderer
from .documents import (
    DocumentContextBus,
    DocumentContextStore,
    StudioDocumentContext,
    StudioSelection,
)

__all__ = [
    "ToolContext",
    "ToolPlugin",
    "PluginCatalog",
    "PluginInfo",
    "CommandRegistry",
    "CommandDispatchError",
    "PaneState",
    "WorkspaceLayoutStore",
    "DocumentContextBus",
    "DocumentContextStore",
    "StudioDocumentContext",
    "StudioSelection",
    "ScuiPanel",
    "ScuiPanelEvent",
    "ScuiPanelState",
    "ScuiTkRenderer",
]
