from __future__ import annotations

from tools.signalcloud_studio.context import ToolContext
from tools.signalcloud_studio.plugin_api import ToolPlugin


class ShowcasePlugin(ToolPlugin):
    key = "showcase-physics"
    display_name = "3D Environment & Physics Showcase"
    category = "Authoring"
    description = "Safely import point, mesh, image, and metadata sources; test bounded physics; export managed PCP3 assets."

    def launch(self, context: ToolContext) -> int:
        from tools.signalcloud_showcase.app import main

        active = context.document_context.active_document
        argv: list[str] = ["--root", str(context.project_root)]
        if active is not None and active.suffix.lower() in {".pcp3", ".pcp3cloud", ".ply", ".obj", ".png", ".bmp", ".udata", ".script"}:
            argv.append(str(active))
        return int(main(argv=argv))
