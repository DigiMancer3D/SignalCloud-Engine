from __future__ import annotations

from tools.signalcloud_studio.context import ToolContext
from tools.signalcloud_studio.plugin_api import ToolPlugin


class PlaybookPlugin(ToolPlugin):
    key = "universal-playbook-lab"
    display_name = "Universal Playbook Lab"
    category = "Authoring"
    description = "Author bounded data-only behavior and effect graphs for every SignalCloud subject class."

    def launch(self, context: ToolContext) -> int:
        from tools.playbook_editor import main

        active = context.document_context.active_document
        argv = ["--root", str(context.project_root)]
        if active is not None and active.suffix.lower() == ".playbook":
            argv.append(str(active))
        return int(main(argv=argv))
