from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


class CommandDispatchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CommandSpec:
    command_id: str
    handler: Callable[..., Any]
    destructive: bool = False
    description: str = ""


class CommandRegistry:
    """Allowlisted command dispatcher shared by desktop tools and future SCUI.

    Registration is explicit. Unknown command IDs never fall through to eval,
    arbitrary imports, shell execution, or attribute lookup.
    """

    def __init__(self) -> None:
        self._commands: dict[str, CommandSpec] = {}

    def register(
        self,
        command_id: str,
        handler: Callable[..., Any],
        *,
        destructive: bool = False,
        description: str = "",
    ) -> None:
        normalized = command_id.strip()
        if not normalized or any(ch.isspace() for ch in normalized):
            raise ValueError("command_id must be a non-empty token")
        if normalized in self._commands:
            raise ValueError(f"command already registered: {normalized}")
        self._commands[normalized] = CommandSpec(
            normalized, handler, destructive, description
        )

    def contains(self, command_id: str) -> bool:
        return command_id in self._commands

    def specs(self) -> tuple[CommandSpec, ...]:
        return tuple(self._commands[key] for key in sorted(self._commands))

    def dispatch(self, command_id: str, /, *args: Any, **kwargs: Any) -> Any:
        spec = self._commands.get(command_id)
        if spec is None:
            raise CommandDispatchError(f"command is not allowlisted: {command_id}")
        return spec.handler(*args, **kwargs)
