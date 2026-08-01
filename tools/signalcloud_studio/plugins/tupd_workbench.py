from __future__ import annotations

from tools.signalcloud_studio.context import ToolContext
from tools.signalcloud_studio.plugin_api import ToolPlugin


class TupdWorkbenchPlugin(ToolPlugin):
    key = "tupd-workbench"
    display_name = "Tupd Authoring Workbench"
    category = "Authoring"
    description = "Author revisioned .tupd recipes, compare results, commit isolated instances, equip or spawn them for declared tests, and export managed recipes and .tupdinstance results."

    def launch(self, context: ToolContext) -> int:
        from tools.signalcloud_tupd.app import main

        active = context.document_context.active_document
        argv: list[str] = ["--root", str(context.project_root)]
        if active is not None and active.suffix.lower() == ".tupd":
            argv.append(str(active))
        return int(main(argv=argv))
