from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field

from .model import TupdRecipe


@dataclass(frozen=True, slots=True)
class PartCatalogEntry:
    item_id: str
    label: str
    interface_id: str
    kind: str
    suggested_sockets: tuple[str, ...]
    retain_default: bool = False
    forceable: bool = False


PART_CATALOG: tuple[PartCatalogEntry, ...] = (
    PartCatalogEntry("weapon.service-pistol", "Service Pistol", "weapon.base", "base weapon", ("body",), True),
    PartCatalogEntry("weapon.service-pistol.duplicate", "Matching Service Pistol", "weapon.duplicate.match", "repair donor", ("duplicate", "body"), False),
    PartCatalogEntry("weapon.prybar", "Prybar", "tool.base", "base tool", ("body",), True),
    PartCatalogEntry("part.signal-grip", "Signal Grip", "socket.grip", "compatible part", ("grip", "body"), False),
    PartCatalogEntry("part.office-bracket", "Office Bracket", "object.office", "improvised part", ("body", "mount"), False, True),
    PartCatalogEntry("part.upgrade-stabilizer", "Stability Upgrade", "upgrade.stability", "upgrade part", ("signal", "body"), False),
    PartCatalogEntry("part.wall-panel", "Wall Panel", "object.barrier", "assembly panel", ("anchor", "mount"), False),
    PartCatalogEntry("part.mount-bracket", "Universal Mount Bracket", "socket.body", "assembly bracket", ("mount", "body", "anchor"), False),
    PartCatalogEntry("consumable.tupd-tape", "Tupd Tape", "tupd.tape", "transaction consumable", (), False),
)

PART_BY_ID = {entry.item_id: entry for entry in PART_CATALOG}


@dataclass(slots=True)
class GraphIssue:
    severity: str
    code: str
    message: str
    node_id: str = ""
    connection: str = ""


@dataclass(slots=True)
class ParsedConnection:
    encoded: str
    source: str
    target: str
    socket: str
    forced: bool


@dataclass(slots=True)
class GraphReport:
    valid: bool = False
    issues: list[GraphIssue] = field(default_factory=list)
    parsed_connections: list[ParsedConnection] = field(default_factory=list)
    connected_nodes: set[str] = field(default_factory=set)
    orphan_nodes: list[str] = field(default_factory=list)
    cycle_nodes: list[str] = field(default_factory=list)
    suggested_connections: list[str] = field(default_factory=list)
    signature: str = ""

    @property
    def error_count(self) -> int:
        return sum(issue.severity == "error" for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.severity == "warning" for issue in self.issues)

    @property
    def info_count(self) -> int:
        return sum(issue.severity == "info" for issue in self.issues)


def parse_connection(encoded: str, *, forced: bool = False) -> ParsedConnection | None:
    source, separator, remainder = encoded.partition(">")
    target, socket_separator, socket = remainder.partition("@")
    source = source.strip()
    target = target.strip()
    socket = socket.strip()
    if not separator or not socket_separator or not source or not target or not socket:
        return None
    return ParsedConnection(encoded=encoded, source=source, target=target, socket=socket, forced=forced)


def _signature(payload: object) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _detect_cycle(nodes: list[str], connections: list[ParsedConnection]) -> list[str]:
    adjacency: dict[str, list[str]] = {node: [] for node in nodes}
    for edge in connections:
        if edge.source in adjacency and edge.target in adjacency:
            adjacency[edge.source].append(edge.target)
    state: dict[str, int] = {node: 0 for node in nodes}
    stack: list[str] = []
    cycle: list[str] = []

    def visit(node: str) -> bool:
        nonlocal cycle
        state[node] = 1
        stack.append(node)
        for target in adjacency[node]:
            if state[target] == 0 and visit(target):
                return True
            if state[target] == 1:
                start = stack.index(target)
                cycle = stack[start:] + [target]
                return True
        stack.pop()
        state[node] = 2
        return False

    for node in nodes:
        if state[node] == 0 and visit(node):
            break
    return cycle


def analyze_recipe_graph(recipe: TupdRecipe) -> GraphReport:
    recipe = copy.deepcopy(recipe)
    recipe.normalize()
    report = GraphReport()
    nodes = list(recipe.inputs)
    node_set = set(nodes)

    def issue(severity: str, code: str, message: str, *, node_id: str = "", connection: str = "") -> None:
        report.issues.append(GraphIssue(severity, code, message, node_id, connection))

    if recipe.mode != "assembly" and recipe.base_item_id not in node_set:
        issue("error", "base.missing", f"Base item is not present in the input graph: {recipe.base_item_id}", node_id=recipe.base_item_id)
    if "consumable.tupd-tape" not in node_set:
        issue("error", "tape.missing", "Every A8 recipe requires Tupd Tape in the input graph.", node_id="consumable.tupd-tape")
    elif "consumable.tupd-tape" not in recipe.consumed_inputs:
        issue("error", "tape.not-consumed", "Tupd Tape must be marked consumed before commit.", node_id="consumable.tupd-tape")

    for consumed in recipe.consumed_inputs:
        if consumed not in node_set:
            issue("error", "consumed.not-input", f"Consumed input is not present in inputs: {consumed}", node_id=consumed)
    if recipe.base_item_id in recipe.consumed_inputs and recipe.mode not in {"repair_full", "assembly"}:
        issue("warning", "base.consumed", "The base item is marked consumed. Most modifications should retain the base item.", node_id=recipe.base_item_id)

    seen: set[tuple[str, str, str]] = set()
    parsed: list[ParsedConnection] = []
    for forced, values in ((False, recipe.connections), (True, recipe.forced_connections)):
        for encoded in values:
            edge = parse_connection(encoded, forced=forced)
            if edge is None:
                issue("error", "connection.malformed", f"Malformed connection: {encoded}", connection=encoded)
                continue
            parsed.append(edge)
            report.parsed_connections.append(edge)
            key = (edge.source, edge.target, edge.socket)
            if key in seen:
                issue("error", "connection.duplicate", f"Duplicate connection: {encoded}", connection=encoded)
            seen.add(key)
            if edge.source not in node_set:
                issue("error", "connection.source-missing", f"Connection source is not an input: {edge.source}", node_id=edge.source, connection=encoded)
            if edge.target not in node_set:
                issue("error", "connection.target-missing", f"Connection target is not an input: {edge.target}", node_id=edge.target, connection=encoded)
            if edge.source == edge.target:
                issue("error", "connection.self", "A node cannot connect to itself.", node_id=edge.source, connection=encoded)
            source_def = PART_BY_ID.get(edge.source)
            if source_def and source_def.suggested_sockets and edge.socket not in source_def.suggested_sockets:
                if edge.forced and source_def.forceable:
                    issue("warning", "connection.forced", f"Forced connection accepted with penalties: {edge.source} -> {edge.socket}", node_id=edge.source, connection=encoded)
                elif edge.forced:
                    issue("warning", "connection.forced-unknown", f"Forced connection is outside the starter compatibility guide: {encoded}", node_id=edge.source, connection=encoded)
                else:
                    issue("error", "connection.incompatible", f"{edge.source} does not normally fit socket {edge.socket}; use a compatible socket or explicitly force it.", node_id=edge.source, connection=encoded)
            elif edge.forced:
                issue("warning", "connection.forced", f"Forced connection accepted with declared penalties: {encoded}", node_id=edge.source, connection=encoded)
            report.connected_nodes.update((edge.source, edge.target))

    report.cycle_nodes = _detect_cycle(nodes, parsed)
    if report.cycle_nodes:
        issue("error", "graph.cycle", "Assembly graph contains a connection cycle: " + " -> ".join(report.cycle_nodes))

    ignored_orphan_kinds = {"transaction consumable", "repair donor"}
    for node in nodes:
        definition = PART_BY_ID.get(node)
        if node == recipe.base_item_id or node in report.connected_nodes:
            continue
        if definition and definition.kind in ignored_orphan_kinds:
            continue
        if recipe.mode in {"repair_small", "repair_full"} and node.startswith(("weapon.", "consumable.")):
            continue
        report.orphan_nodes.append(node)
        issue("warning", "graph.orphan", f"Input is not connected to the result graph: {node}", node_id=node)

    for node in report.orphan_nodes:
        definition = PART_BY_ID.get(node)
        target = recipe.base_item_id if recipe.base_item_id in node_set else next((value for value in nodes if value != node), "")
        if not definition or not target or not definition.suggested_sockets:
            continue
        report.suggested_connections.append(f"{node}>{target}@{definition.suggested_sockets[0]}")

    if recipe.forced_connections:
        if "allow_forced_connection" not in recipe.validation_rules:
            issue("error", "forced.rule-missing", "Forced connections require the allow_forced_connection validation rule.")
        if recipe.stability_penalty < 1.0 and recipe.weight_penalty <= 0.0:
            issue("error", "forced.penalty-missing", "Forced connections require a visible stability or weight penalty.")
    if not recipe.test_actions:
        issue("error", "tests.empty", "Declare at least one bounded result test.")
    if not recipe.result.sockets:
        issue("warning", "result.sockets-empty", "Result exposes no sockets for later revisions or Pivot 14 consumers.")
    if not recipe.result.tags:
        issue("warning", "result.tags-empty", "Result has no discovery tags.")

    if not report.issues:
        issue("info", "graph.clean", "Graph is connected, bounded, and ready for sandbox preview.")
    report.valid = report.error_count == 0
    report.signature = _signature({
        "recipe_id": recipe.recipe_id,
        "revision": recipe.recipe_revision,
        "nodes": nodes,
        "consumed": recipe.consumed_inputs,
        "connections": recipe.connections,
        "forced_connections": recipe.forced_connections,
        "issues": [(value.severity, value.code, value.node_id, value.connection) for value in report.issues],
    })
    return report


def apply_suggested_connections(recipe: TupdRecipe) -> tuple[TupdRecipe, GraphReport]:
    result = copy.deepcopy(recipe)
    report = analyze_recipe_graph(result)
    for encoded in report.suggested_connections:
        if encoded not in result.connections and encoded not in result.forced_connections:
            result.connections.append(encoded)
    result.normalize()
    return result, analyze_recipe_graph(result)


def duplicate_recipe(recipe: TupdRecipe, recipe_id: str, label: str) -> TupdRecipe:
    result = copy.deepcopy(recipe)
    parent_id = result.recipe_id
    result.recipe_id = recipe_id.strip() or f"user.{parent_id}"
    result.label = label.strip() or f"{result.label} Copy"
    result.recipe_revision = 1
    result.result.result_id = f"{result.recipe_id}.result"
    result.result.display_name = f"{result.label} Result"
    result.extensions = dict(result.extensions)
    result.extensions["authoring_parent_recipe"] = parent_id
    result.extensions["authoring_track"] = "A8a3"
    result.normalize()
    return result


def bump_recipe_revision(recipe: TupdRecipe) -> TupdRecipe:
    result = copy.deepcopy(recipe)
    result.recipe_revision = min(9999, max(1, result.recipe_revision) + 1)
    result.extensions = dict(result.extensions)
    result.extensions["authoring_track"] = "A8a3"
    result.extensions["authoring_previous_revision"] = result.recipe_revision - 1
    result.normalize()
    return result
