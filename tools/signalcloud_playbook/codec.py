from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .model import (
    ACTIONS,
    BRANCH_KINDS,
    CONDITIONS,
    EFFECTS,
    MAX_DEPTH,
    MAX_EDGES,
    MAX_NODES,
    MAX_STEPS,
    MODES,
    NODE_KINDS,
    SCHEMA,
    SUBJECT_KINDS,
    TARGET_SCOPES,
    TRIGGERS,
    VERSION,
    Edge,
    Node,
    Playbook,
    PlaybookValidationError,
)

_TOKEN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")


def _token(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not _TOKEN.fullmatch(text):
        raise PlaybookValidationError(f"{field} must be a bounded lowercase token")
    return text


def _number(value: Any, field: str, *, low: float, high: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise PlaybookValidationError(f"{field} must be numeric") from exc
    if not low <= result <= high:
        raise PlaybookValidationError(f"{field} must be between {low} and {high}")
    return result


def _integer(value: Any, field: str, *, low: int, high: int) -> int:
    if isinstance(value, bool):
        raise PlaybookValidationError(f"{field} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise PlaybookValidationError(f"{field} must be an integer") from exc
    if result != value and not isinstance(value, str):
        raise PlaybookValidationError(f"{field} must be an integer")
    if not low <= result <= high:
        raise PlaybookValidationError(f"{field} must be between {low} and {high}")
    return result


def _operation_for(kind: str, record: dict[str, Any]) -> str:
    field = {
        "trigger": "trigger",
        "action": "action",
        "effect": "effect",
        "condition": "condition",
        "reset": "action",
    }[kind]
    operation = _token(record.get(field), f"node.{field}")
    allowed = {
        "trigger": TRIGGERS,
        "action": ACTIONS,
        "effect": EFFECTS,
        "condition": CONDITIONS,
        "reset": ACTIONS,
    }[kind]
    if operation not in allowed:
        raise PlaybookValidationError(f"unsupported {kind} operation: {operation}")
    if kind == "reset" and operation != "flow.reset":
        raise PlaybookValidationError("reset nodes must use flow.reset")
    return operation


def _cycle_has_bound(playbook: Playbook, members: set[str]) -> bool:
    by_id = {node.node_id: node for node in playbook.nodes}
    return any(
        by_id[node_id].timeout_seconds > 0.0 or by_id[node_id].cooldown_seconds > 0.0
        for node_id in members
        if node_id in by_id
    )


def _validate_cycles(playbook: Playbook) -> None:
    adjacency: dict[str, list[str]] = {node.node_id: [] for node in playbook.nodes}
    for edge in playbook.edges:
        adjacency[edge.source].append(edge.destination)
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node_id: str) -> None:
        state[node_id] = 1
        stack.append(node_id)
        for destination in adjacency.get(node_id, []):
            if state.get(destination, 0) == 0:
                visit(destination)
            elif state.get(destination) == 1:
                start = stack.index(destination)
                members = set(stack[start:])
                if not _cycle_has_bound(playbook, members):
                    joined = ", ".join(sorted(members))
                    raise PlaybookValidationError(
                        f"unbounded cycle has no timeout or cooldown: {joined}"
                    )
        stack.pop()
        state[node_id] = 2

    for node_id in adjacency:
        if state.get(node_id, 0) == 0:
            visit(node_id)


def validate_playbook(payload: dict[str, Any]) -> Playbook:
    if not isinstance(payload, dict):
        raise PlaybookValidationError("playbook root must be an object")
    if payload.get("schema") != SCHEMA or payload.get("version") != VERSION:
        raise PlaybookValidationError(f"expected {SCHEMA} version {VERSION}")

    playbook_id = _token(payload.get("playbook_id"), "playbook_id")
    name = str(payload.get("name") or playbook_id).strip()[:160]
    mode = _token(payload.get("mode", "extend"), "mode")
    if mode not in MODES:
        raise PlaybookValidationError(f"unsupported mode: {mode}")

    subject = payload.get("subject")
    if not isinstance(subject, dict):
        raise PlaybookValidationError("subject must be an object")
    subject_kind = _token(subject.get("kind"), "subject.kind")
    if subject_kind not in SUBJECT_KINDS:
        raise PlaybookValidationError(f"unsupported subject kind: {subject_kind}")
    subject_archetype = _token(subject.get("archetype", "generic"), "subject.archetype")

    limits = payload.get("limits") or {}
    if not isinstance(limits, dict):
        raise PlaybookValidationError("limits must be an object")
    max_steps = _integer(limits.get("max_steps", 24), "limits.max_steps", low=1, high=MAX_STEPS)
    max_depth = _integer(limits.get("max_depth", 8), "limits.max_depth", low=1, high=MAX_DEPTH)
    point_budget_cost = _integer(
        limits.get("point_budget_cost", 0), "limits.point_budget_cost", low=0, high=65_535
    )

    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise PlaybookValidationError("nodes must be a non-empty array")
    if len(raw_nodes) > MAX_NODES:
        raise PlaybookValidationError(f"node count exceeds {MAX_NODES}")
    nodes: list[Node] = []
    node_ids: set[str] = set()
    for index, record in enumerate(raw_nodes):
        if not isinstance(record, dict):
            raise PlaybookValidationError(f"nodes[{index}] must be an object")
        node_id = _token(record.get("id"), f"nodes[{index}].id")
        if node_id in node_ids:
            raise PlaybookValidationError(f"duplicate node id: {node_id}")
        node_ids.add(node_id)
        kind = _token(record.get("kind"), f"nodes[{index}].kind")
        if kind not in NODE_KINDS:
            raise PlaybookValidationError(f"unsupported node kind: {kind}")
        operation = _operation_for(kind, record)
        target = _token(record.get("target", "self"), f"nodes[{index}].target")
        if target not in TARGET_SCOPES:
            raise PlaybookValidationError(f"unsupported target scope: {target}")
        timeout = _number(
            record.get("timeout_seconds", 0.0), f"nodes[{index}].timeout_seconds", low=0.0, high=60.0
        )
        cooldown = _number(
            record.get("cooldown_seconds", 0.0), f"nodes[{index}].cooldown_seconds", low=0.0, high=120.0
        )
        bone = str(record.get("bone") or "").strip()[:48]
        known = {
            "id", "kind", "trigger", "action", "effect", "condition", "target",
            "timeout_seconds", "cooldown_seconds", "bone",
        }
        nodes.append(Node(
            node_id=node_id,
            kind=kind,
            operation=operation,
            target=target,
            timeout_seconds=timeout,
            cooldown_seconds=cooldown,
            bone=bone,
            extensions={key: value for key, value in record.items() if key not in known},
        ))

    entry = _token(payload.get("entry"), "entry")
    if entry not in node_ids:
        raise PlaybookValidationError("entry must reference an existing node")

    raw_edges = payload.get("edges", [])
    if not isinstance(raw_edges, list):
        raise PlaybookValidationError("edges must be an array")
    if len(raw_edges) > MAX_EDGES:
        raise PlaybookValidationError(f"edge count exceeds {MAX_EDGES}")
    edges: list[Edge] = []
    seen_edges: set[tuple[str, str, str, str, int]] = set()
    for index, record in enumerate(raw_edges):
        if not isinstance(record, dict):
            raise PlaybookValidationError(f"edges[{index}] must be an object")
        source = _token(record.get("from"), f"edges[{index}].from")
        destination = _token(record.get("to"), f"edges[{index}].to")
        if source not in node_ids or destination not in node_ids:
            raise PlaybookValidationError(f"edge {source}->{destination} references a missing node")
        branch = _token(record.get("branch", "always"), f"edges[{index}].branch")
        if branch not in BRANCH_KINDS:
            raise PlaybookValidationError(f"unsupported branch kind: {branch}")
        condition = _token(record.get("condition", "always"), f"edges[{index}].condition")
        if branch == "condition" and condition not in CONDITIONS:
            raise PlaybookValidationError(f"unsupported edge condition: {condition}")
        if branch == "event" and condition not in TRIGGERS:
            raise PlaybookValidationError(f"unsupported edge event: {condition}")
        if branch not in {"condition", "event"}:
            condition = "always"
        priority = _integer(record.get("priority", 0), f"edges[{index}].priority", low=0, high=255)
        identity = (source, destination, branch, condition, priority)
        if identity in seen_edges:
            raise PlaybookValidationError(f"duplicate edge: {source}->{destination}")
        seen_edges.add(identity)
        known = {"from", "to", "branch", "condition", "priority"}
        edges.append(Edge(
            source=source,
            destination=destination,
            branch=branch,
            condition=condition,
            priority=priority,
            extensions={key: value for key, value in record.items() if key not in known},
        ))

    playbook = Playbook(
        playbook_id=playbook_id,
        name=name,
        mode=mode,
        subject_kind=subject_kind,
        subject_archetype=subject_archetype,
        entry=entry,
        max_steps=max_steps,
        max_depth=max_depth,
        point_budget_cost=point_budget_cost,
        nodes=nodes,
        edges=edges,
        raw=json.loads(json.dumps(payload)),
    )
    _validate_cycles(playbook)
    return playbook


def load_playbook(path: Path) -> Playbook:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PlaybookValidationError(str(exc)) from exc
    return validate_playbook(payload)


def save_playbook(path: Path, payload: dict[str, Any]) -> Playbook:
    validated = validate_playbook(payload)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, destination)
    return validated
