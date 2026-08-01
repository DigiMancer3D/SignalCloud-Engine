from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .documents import DocumentContextBus, DocumentContextStore, StudioDocumentContext


@dataclass(slots=True)
class ToolContext:
    """Shared project/selection context passed to every Studio tool.

    The object intentionally contains data and paths only.  It does not import
    Tkinter and can later be mirrored by native SCUI and IPC adapters.
    """

    project_root: Path
    content_root: Path | None = None
    user_data_root: Path | None = None
    active_project: Path | None = None
    selected_asset_id: str | None = None
    selected_entity_ids: tuple[str, ...] = ()
    active_tool_key: str = "pcp3"
    metadata: dict[str, Any] = field(default_factory=dict)
    document_context: StudioDocumentContext | None = None
    document_store: DocumentContextStore | None = None
    document_bus: DocumentContextBus | None = None

    def __post_init__(self) -> None:
        self.project_root = self.project_root.expanduser().resolve()
        if self.content_root is None:
            self.content_root = self.project_root / "content"
        else:
            self.content_root = self.content_root.expanduser().resolve()
        if self.user_data_root is None:
            self.user_data_root = self.project_root / "user_data"
        else:
            self.user_data_root = self.user_data_root.expanduser().resolve()
        if self.active_project is not None:
            self.active_project = self.active_project.expanduser().resolve()

    def with_tool(self, tool_key: str) -> "ToolContext":
        return ToolContext(
            project_root=self.project_root,
            content_root=self.content_root,
            user_data_root=self.user_data_root,
            active_project=self.active_project,
            selected_asset_id=self.selected_asset_id,
            selected_entity_ids=self.selected_entity_ids,
            active_tool_key=tool_key,
            metadata=dict(self.metadata),
            document_context=self.document_context,
            document_store=self.document_store,
            document_bus=self.document_bus,
        )

    def publish_document(self, context: StudioDocumentContext) -> StudioDocumentContext:
        self.document_context = context
        if self.document_store is not None:
            self.document_store.write(context)
        if self.document_bus is not None:
            self.document_bus.publish(context)
        return context
