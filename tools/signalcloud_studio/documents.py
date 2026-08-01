from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping


DOCUMENT_CONTEXT_SCHEMA = "signalcloud_studio_document_context_v1"


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _safe_relative_document(project_root: Path, value: str | Path | None) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    root = Path(project_root).expanduser().resolve()
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (root / candidate).resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("document path must remain inside the SignalCloud project root") from exc
    return relative.as_posix()


@dataclass(slots=True)
class StudioSelection:
    asset_id: str | None = None
    entity_ids: tuple[str, ...] = ()
    node_ids: tuple[str, ...] = ()
    surface_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, value: Any) -> "StudioSelection":
        if not isinstance(value, dict):
            return cls()
        metadata = value.get("metadata", {})
        return cls(
            asset_id=str(value["asset_id"]) if value.get("asset_id") not in (None, "") else None,
            entity_ids=_string_tuple(value.get("entity_ids")),
            node_ids=_string_tuple(value.get("node_ids")),
            surface_ids=_string_tuple(value.get("surface_ids")),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "entity_ids": list(self.entity_ids),
            "node_ids": list(self.node_ids),
            "surface_ids": list(self.surface_ids),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class StudioDocumentContext:
    schema: str = DOCUMENT_CONTEXT_SCHEMA
    active_document: str | None = None
    document_kind: str = "none"
    owner_tool: str = ""
    revision: int = 0
    dirty: bool = False
    selection: StudioSelection = field(default_factory=StudioSelection)
    linked_documents: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    unknown_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, value: Any) -> "StudioDocumentContext":
        if not isinstance(value, dict):
            return cls()
        known = {
            "schema",
            "active_document",
            "document_kind",
            "owner_tool",
            "revision",
            "dirty",
            "selection",
            "linked_documents",
            "metadata",
        }
        metadata = value.get("metadata", {})
        return cls(
            schema=str(value.get("schema", DOCUMENT_CONTEXT_SCHEMA)),
            active_document=(
                str(value["active_document"])
                if value.get("active_document") not in (None, "")
                else None
            ),
            document_kind=str(value.get("document_kind", "none")),
            owner_tool=str(value.get("owner_tool", "")),
            revision=max(0, int(value.get("revision", 0))),
            dirty=bool(value.get("dirty", False)),
            selection=StudioSelection.from_json(value.get("selection")),
            linked_documents=_string_tuple(value.get("linked_documents")),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
            unknown_fields={key: item for key, item in value.items() if key not in known},
        )

    def to_json(self) -> dict[str, Any]:
        value = dict(self.unknown_fields)
        value.update(
            {
                "schema": DOCUMENT_CONTEXT_SCHEMA,
                "active_document": self.active_document,
                "document_kind": self.document_kind,
                "owner_tool": self.owner_tool,
                "revision": self.revision,
                "dirty": self.dirty,
                "selection": self.selection.to_json(),
                "linked_documents": list(self.linked_documents),
                "metadata": dict(self.metadata),
            }
        )
        return value

    def updated(self, **changes: Any) -> "StudioDocumentContext":
        changes.setdefault("revision", self.revision + 1)
        return replace(self, **changes)


DocumentListener = Callable[[StudioDocumentContext], None]


class DocumentContextBus:
    """Small in-process publisher used by docked or cooperating Studio tools."""

    def __init__(self, initial: StudioDocumentContext | None = None) -> None:
        self.current = initial or StudioDocumentContext()
        self._listeners: list[DocumentListener] = []

    def subscribe(self, listener: DocumentListener, *, replay: bool = True) -> Callable[[], None]:
        self._listeners.append(listener)
        if replay:
            listener(self.current)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return unsubscribe

    def publish(self, context: StudioDocumentContext) -> None:
        self.current = context
        for listener in tuple(self._listeners):
            listener(context)


class DocumentContextStore:
    """Forgiving, atomic project-local storage for cross-tool document state.

    Paths are persisted relative to the project root, never as developer-specific
    absolute paths. Unknown future fields survive older Studio versions.
    """

    def __init__(self, project_root: Path, path: Path) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.path = Path(path)

    @classmethod
    def for_project(
        cls,
        project_root: Path,
        filename: str = "shared_document_context.json",
    ) -> "DocumentContextStore":
        root = Path(project_root).expanduser().resolve()
        return cls(root, root / "user_data" / "studio" / filename)

    def read(self) -> StudioDocumentContext:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            context = StudioDocumentContext.from_json(raw)
            if context.active_document is not None:
                context.active_document = _safe_relative_document(
                    self.project_root, context.active_document
                )
            context.linked_documents = tuple(
                item
                for item in (
                    _safe_relative_document(self.project_root, value)
                    for value in context.linked_documents
                )
                if item is not None
            )
            return context
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return StudioDocumentContext()

    def write(self, context: StudioDocumentContext) -> None:
        normalized = replace(
            context,
            active_document=_safe_relative_document(
                self.project_root, context.active_document
            ),
            linked_documents=tuple(
                item
                for item in (
                    _safe_relative_document(self.project_root, value)
                    for value in context.linked_documents
                )
                if item is not None
            ),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(normalized.to_json(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def publish(
        self,
        previous: StudioDocumentContext | None = None,
        *,
        active_document: str | Path | None = None,
        document_kind: str | None = None,
        owner_tool: str | None = None,
        dirty: bool | None = None,
        selection: StudioSelection | None = None,
        linked_documents: tuple[str, ...] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> StudioDocumentContext:
        current = previous or self.read()
        merged_metadata = dict(current.metadata)
        if metadata is not None:
            merged_metadata.update(dict(metadata))
        updated = current.updated(
            active_document=(
                _safe_relative_document(self.project_root, active_document)
                if active_document is not None
                else current.active_document
            ),
            document_kind=document_kind if document_kind is not None else current.document_kind,
            owner_tool=owner_tool if owner_tool is not None else current.owner_tool,
            dirty=dirty if dirty is not None else current.dirty,
            selection=selection if selection is not None else current.selection,
            linked_documents=(
                tuple(linked_documents)
                if linked_documents is not None
                else current.linked_documents
            ),
            metadata=merged_metadata,
        )
        self.write(updated)
        return updated

    def resolve_active_path(self, context: StudioDocumentContext | None = None) -> Path | None:
        selected = context or self.read()
        if selected.active_document is None:
            return None
        return (self.project_root / selected.active_document).resolve()
