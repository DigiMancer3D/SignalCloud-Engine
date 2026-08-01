from __future__ import annotations

from tools.signalcloud_studio.compatibility.branch12r1_adapter import launch_branch12r1
from tools.signalcloud_studio.context import ToolContext
from tools.signalcloud_studio.plugin_api import ToolPlugin


class PCP3Plugin(ToolPlugin):
    key = "pcp3"
    display_name = "Point Cloud Paint++"
    category = "Authoring"
    description = "SignalCloud point, entity, environment, and world authoring."

    def launch(self, context: ToolContext) -> int:
        return launch_branch12r1(context.with_tool(self.key))
