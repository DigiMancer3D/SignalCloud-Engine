from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from ..commands import CommandDispatchError, CommandRegistry
from .model import ScuiPanelEvent, ScuiPanelState


class ScuiDispatcher:
    """Safe SCUI dispatcher.

    Unknown commands are recorded as telemetry-only blocked events. SCUI data
    never maps to eval, imports, subprocesses, or arbitrary Python attributes.
    """

    def __init__(
        self,
        registry: CommandRegistry,
        state: ScuiPanelState,
        *,
        telemetry: Callable[[ScuiPanelEvent, str], None] | None = None,
    ) -> None:
        self.registry = registry
        self.state = state
        self.telemetry = telemetry

    def emit(
        self,
        *,
        panel_id: str,
        control_id: str,
        command_id: str,
        payload: dict[str, Any],
    ) -> ScuiPanelEvent:
        event = ScuiPanelEvent(
            panel_id=panel_id,
            control_id=control_id,
            command_id=command_id,
            payload=dict(payload),
            transaction_id=uuid.uuid4().hex,
        )
        if not command_id:
            return event
        try:
            self.registry.dispatch(command_id, event)
        except CommandDispatchError as exc:
            self.state.blocked_events.append(event)
            self.state.validation.append(str(exc))
            if self.telemetry is not None:
                self.telemetry(event, str(exc))
        return event
