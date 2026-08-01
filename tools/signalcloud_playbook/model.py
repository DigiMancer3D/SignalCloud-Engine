from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA = "signalcloud_playbook_v1"
VERSION = 1
MAX_NODES = 64
MAX_EDGES = 96
MAX_DEPTH = 16
MAX_STEPS = 64

SUBJECT_KINDS = {
    "local_user", "remote_user", "enemy", "mini_boss", "boss", "friendly",
    "companion", "npc", "raid_party", "pickup", "kiosk", "door", "trap",
    "object", "weapon", "projectile", "ability", "environmental_effect",
}
TARGET_SCOPES = {
    "self", "event_origin", "entity", "entities", "object", "surface",
    "area", "room", "world",
}
NODE_KINDS = {"trigger", "action", "effect", "condition", "reset"}
MODES = {"extend", "replace", "layer"}
BRANCH_KINDS = {"always", "complete", "timeout", "condition", "event"}

TRIGGERS = {
    "event.sound_heard", "event.bark", "event.gunshot", "event.splash",
    "event.hit", "event.timer", "event.enter_room", "event.interact",
    "event.threshold", "event.effect_received",
}
ACTIONS = {
    "flow.idle", "flow.search", "flow.reset", "move.investigate",
    "move.guard", "move.flank", "move.retreat", "move.threshold_pursuit",
    "stance.guard", "attack.primary", "effect.dispatch",
}
EFFECTS = {
    "signal.ripple", "signal.pressure_wave", "sound.low_band", "water.splash",
    "light.pulse", "material.jitter", "status.alert",
}
CONDITIONS = {
    "always", "target.visible", "target.lost", "timer.expired", "health.low",
    "path.available", "room.safe", "effect.active",
}


class PlaybookValidationError(ValueError):
    pass


@dataclass(slots=True)
class Node:
    node_id: str
    kind: str
    operation: str
    target: str
    timeout_seconds: float = 0.0
    cooldown_seconds: float = 0.0
    bone: str = ""
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Edge:
    source: str
    destination: str
    branch: str
    condition: str = "always"
    priority: int = 0
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Playbook:
    playbook_id: str
    name: str
    mode: str
    subject_kind: str
    subject_archetype: str
    entry: str
    max_steps: int
    max_depth: int
    point_budget_cost: int
    nodes: list[Node]
    edges: list[Edge]
    raw: dict[str, Any] = field(default_factory=dict)
