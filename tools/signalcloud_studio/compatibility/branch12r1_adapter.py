from __future__ import annotations

from pathlib import Path

from tools.signalcloud_studio.context import ToolContext


def launch_branch12r1(context: ToolContext) -> int:
    """Launch the accepted Branch 12 R1 editor behind the canonical API.

    The historical import is intentionally isolated here. A1 will progressively
    replace this adapter with flattened capability modules while the public entry
    point and plugin contract remain stable.
    """

    from tools.signalcloud_studio.compatibility.pcp3_document_bridge import (
        launch_bridged_branch12r1,
    )

    return int(launch_bridged_branch12r1(context))
