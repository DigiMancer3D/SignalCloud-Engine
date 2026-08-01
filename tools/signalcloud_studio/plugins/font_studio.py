from __future__ import annotations

from tools.signalcloud_studio.context import ToolContext
from tools.signalcloud_studio.plugin_api import ToolPlugin


class FontStudioPlugin(ToolPlugin):
    key = "font-studio"
    display_name = "SignalCloud Font Studio (+SCFS+)"
    category = "Authoring"
    description = "Author layered .scfont assets with Rich and Simple SignalCloud previews."

    def launch(self, context: ToolContext) -> int:
        from tools.scfs.editor import launch

        launch(context.project_root)
        return 0
