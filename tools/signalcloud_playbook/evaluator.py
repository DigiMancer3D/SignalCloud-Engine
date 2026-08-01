from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .model import Edge, Playbook


@dataclass(frozen=True, slots=True)
class EvaluationStep:
    node_id: str
    kind: str
    operation: str
    target: str


def _condition_true(name: str, context: Mapping[str, object]) -> bool:
    if name == "always":
        return True
    return bool(context.get(name, False))


def _edge_true(edge: Edge, context: Mapping[str, object]) -> bool:
    if edge.branch in {"always", "complete"}:
        return True
    if edge.branch == "timeout":
        return bool(context.get("timer.expired", False))
    if edge.branch == "condition":
        return _condition_true(edge.condition, context)
    if edge.branch == "event":
        return str(context.get("event", "")) == edge.condition
    return False


def evaluate_playbook(
    playbook: Playbook,
    context: Mapping[str, object] | None = None,
    *,
    maximum_steps: int | None = None,
) -> list[EvaluationStep]:
    values: Mapping[str, object] = context or {}
    by_id = {node.node_id: node for node in playbook.nodes}
    outgoing: dict[str, list[Edge]] = {node_id: [] for node_id in by_id}
    for edge in playbook.edges:
        outgoing[edge.source].append(edge)
    for edges in outgoing.values():
        edges.sort(key=lambda edge: (edge.priority, edge.destination, edge.branch, edge.condition))

    limit = min(playbook.max_steps, maximum_steps or playbook.max_steps)
    current = playbook.entry
    result: list[EvaluationStep] = []
    for _ in range(max(0, limit)):
        node = by_id.get(current)
        if node is None:
            break
        result.append(EvaluationStep(node.node_id, node.kind, node.operation, node.target))
        selected = next((edge for edge in outgoing.get(current, []) if _edge_true(edge, values)), None)
        if selected is None:
            break
        current = selected.destination
    return result
