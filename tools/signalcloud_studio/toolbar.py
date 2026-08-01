from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .ui.flow import wrapped_row_assignments


@dataclass(frozen=True, slots=True)
class ToolbarGroupSpec:
    key: str
    requested_width: int
    priority: int = 100


@dataclass(frozen=True, slots=True)
class ToolbarPlacement:
    key: str
    row: int
    column: int


def plan_toolbar(groups: Iterable[ToolbarGroupSpec], available_width: int) -> tuple[ToolbarPlacement, ...]:
    """Create a deterministic responsive placement plan without touching Tk."""

    ordered = tuple(sorted(groups, key=lambda item: (item.priority, item.key)))
    positions = wrapped_row_assignments(
        [max(1, group.requested_width) for group in ordered],
        max(1, available_width),
    )
    return tuple(
        ToolbarPlacement(group.key, row, column)
        for group, (row, column) in zip(ordered, positions)
    )
