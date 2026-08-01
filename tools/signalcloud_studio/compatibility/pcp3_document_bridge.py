from __future__ import annotations

import subprocess
import tkinter as tk
from pathlib import Path
from typing import Any

from tools.signalcloud_studio.context import ToolContext
from tools.signalcloud_studio.documents import StudioSelection


def _find_cascade_menu(menu: Any, label: str) -> Any | None:
    """Return a named submenu while safely skipping Tk tear-off entries.

    Tk menus expose a tear-off item at index zero unless tearoff is disabled.
    That entry has no ``label`` option, so menu scanners must handle each item
    independently instead of abandoning the whole scan on the first TclError.
    """

    try:
        end = menu.index("end")
    except (tk.TclError, AttributeError):
        return None
    if end is None:
        return None
    for index in range(int(end) + 1):
        try:
            if str(menu.type(index)) != "cascade":
                continue
            if str(menu.entrycget(index, "label")) != label:
                continue
            return menu.nametowidget(menu.entrycget(index, "menu"))
        except (tk.TclError, AttributeError, TypeError, ValueError):
            continue
    return None


def _menu_has_label(menu: Any, label: str) -> bool:
    try:
        end = menu.index("end")
    except (tk.TclError, AttributeError):
        return False
    if end is None:
        return False
    for index in range(int(end) + 1):
        try:
            if str(menu.entrycget(index, "label")) == label:
                return True
        except (tk.TclError, AttributeError, TypeError, ValueError):
            continue
    return False


def publish_pcp3_document(
    context: ToolContext,
    project_path: Path | None,
    document: Any,
) -> None:
    if project_path is None or context.document_store is None:
        return
    selected = tuple(
        f"point:{index}"
        for index in sorted(getattr(document, "selected_indices", ()))[:512]
    )
    previous = context.document_context
    linked_documents = previous.linked_documents if previous is not None else ()
    updated = context.document_store.publish(
        previous,
        active_document=project_path,
        document_kind="pcp3_project",
        owner_tool="pcp3",
        dirty=bool(getattr(document, "dirty", False)),
        selection=StudioSelection(
            asset_id=str(getattr(document, "asset_id", "")) or None,
            node_ids=selected,
            metadata={"selection_kind": "pcp3_points"},
        ),
        linked_documents=linked_documents,
        metadata={
            "project_id": str(getattr(document, "project_id", "")),
            "environment_type": str(getattr(document, "environment_type", "")),
            "point_count": len(getattr(document, "points", ())),
            "format": "pcp3",
        },
    )
    context.document_context = updated
    if context.document_bus is not None:
        context.document_bus.publish(updated)


def launch_bridged_branch12r1(context: ToolContext) -> int:
    """Launch accepted Branch 12 R1 with shared document and Light Lab hooks."""

    from tools.pcp3.editor_branch12r1 import PCP3Editor as AcceptedPCP3Editor

    class StudioPCP3Editor(AcceptedPCP3Editor):
        def __init__(self, root_path: Path) -> None:
            self._studio_tool_context = context
            super().__init__(root_path)

        def _publish_studio_document(self) -> None:
            publish_pcp3_document(
                self._studio_tool_context,
                self.project_path,
                self.document,
            )

        def _build_menu(self) -> None:
            super()._build_menu()
            try:
                menu = self.nametowidget(self.cget("menu"))
            except tk.TclError:
                return
            tools_menu = _find_cascade_menu(menu, "Tools")
            if tools_menu is None:
                return
            label = "Open linked Illuminosity Light Lab…"
            if _menu_has_label(tools_menu, label):
                return
            # Put the cross-tool action at the top so it remains visible even
            # when the PCP3 tool list grows.
            tools_menu.insert_command(
                0,
                label=label,
                command=self._launch_linked_light_lab,
            )
            tools_menu.insert_separator(1)

        def _launch_linked_light_lab(self) -> None:
            self._publish_studio_document()
            subprocess.Popen(
                [str(self.root_path / "scripts" / "launch_light_lab.sh")],
                cwd=self.root_path,
            )
            self.update_status(
                "Opened Light Lab with the current saved PCP3 document as shared context"
            )

        def open_project(self) -> None:
            super().open_project()
            self._publish_studio_document()

        def _save_to(self, path: Path) -> bool:
            saved = bool(super()._save_to(path))
            if saved:
                self._publish_studio_document()
            return saved

        def finish_edit(self, message: str) -> None:
            super().finish_edit(message)
            self._publish_studio_document()

        def on_close(self) -> None:
            self._publish_studio_document()
            super().on_close()

    app = StudioPCP3Editor(Path(context.project_root))
    app.mainloop()
    return 0
