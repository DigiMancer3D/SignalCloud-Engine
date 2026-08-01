from __future__ import annotations

from tools.signalcloud_studio.context import ToolContext
from tools.signalcloud_studio.plugin_api import ToolPlugin


class JitterTexturePlugin(ToolPlugin):
    key = "jitter-texture-lab"
    display_name = "Jitter & Material Lab"
    category = "Authoring"
    description = "Preview SignalCloud jG/jL/jC/jS displacement, material layers, opacity, and palette response."

    def launch(self, context: ToolContext) -> int:
        from tools.jitter_texture_lab import main as jitter_lab_main

        return int(jitter_lab_main(root_path=context.project_root, context=context.with_tool(self.key)))
