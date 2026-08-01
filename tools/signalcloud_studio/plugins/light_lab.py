from __future__ import annotations

from tools.signalcloud_studio.context import ToolContext
from tools.signalcloud_studio.plugin_api import ToolPlugin


class LightLabPlugin(ToolPlugin):
    key = "light-lab"
    display_name = "Illuminosity Light Lab"
    category = "Authoring"
    description = "Create and inspect SignalCloud light sets with shared Studio document context."

    def launch(self, context: ToolContext) -> int:
        from tools.light_lab_gui import main as light_lab_main

        return int(light_lab_main(root_path=context.project_root, context=context.with_tool(self.key)))
