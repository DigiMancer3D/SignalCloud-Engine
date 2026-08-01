from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StudioRegionLayout:
    """Named layout contract retained from the accepted Branch 12 R1 UI."""

    context_action_bar: str = "context_action_bar"
    quick_action_toolbar: str = "quick_action_toolbar"
    work_area: str = "work_area"
    inspector: str = "inspector"
    status_bar: str = "status_bar"


DEFAULT_LAYOUT = StudioRegionLayout()
