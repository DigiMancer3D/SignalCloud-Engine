from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

from .codec import load_playbook
from .model import Playbook

RUNTIME_HEADER = "SCPLAY_RUNTIME 1"


def _graph_signature(playbook: Playbook) -> str:
    digest = hashlib.sha256()
    digest.update(playbook.playbook_id.encode())
    digest.update(playbook.mode.encode())
    digest.update(playbook.subject_kind.encode())
    digest.update(playbook.subject_archetype.encode())
    digest.update(playbook.entry.encode())
    for node in playbook.nodes:
        digest.update(
            f"N|{node.node_id}|{node.kind}|{node.operation}|{node.target}|"
            f"{node.timeout_seconds:.6f}|{node.cooldown_seconds:.6f}|{node.bone}".encode()
        )
    for edge in sorted(
        playbook.edges,
        key=lambda item: (item.source, item.priority, item.destination, item.branch, item.condition),
    ):
        digest.update(
            f"E|{edge.source}|{edge.destination}|{edge.branch}|{edge.condition}|{edge.priority}".encode()
        )
    return digest.hexdigest()[:16]


def _encode(playbooks: list[Playbook], sources: list[str]) -> str:
    lines = [RUNTIME_HEADER, f"SOURCE_COUNT {len(playbooks)}"]
    total_nodes = total_edges = total_cost = 0
    for graph_index, (playbook, source) in enumerate(zip(playbooks, sources, strict=True)):
        by_id = {node.node_id: index for index, node in enumerate(playbook.nodes)}
        signature = _graph_signature(playbook)
        lines.append(
            "GRAPH "
            f"{graph_index} {playbook.playbook_id} 1 {playbook.mode} "
            f"{playbook.subject_kind} {playbook.subject_archetype} {playbook.entry} "
            f"{playbook.max_steps} {playbook.max_depth} {playbook.point_budget_cost} "
            f"{signature} {source}"
        )
        for node_index, node in enumerate(playbook.nodes):
            bone = node.bone or "-"
            lines.append(
                "NODE "
                f"{graph_index} {node_index} {node.node_id} {node.kind} {node.operation} "
                f"{node.target} {round(node.timeout_seconds * 1000.0)} "
                f"{round(node.cooldown_seconds * 1000.0)} {bone}"
            )
        for edge in sorted(
            playbook.edges,
            key=lambda item: (by_id[item.source], item.priority, by_id[item.destination], item.branch, item.condition),
        ):
            lines.append(
                "EDGE "
                f"{graph_index} {by_id[edge.source]} {by_id[edge.destination]} "
                f"{edge.branch} {edge.condition} {edge.priority}"
            )
        lines.append(f"ENDGRAPH {graph_index}")
        total_nodes += len(playbook.nodes)
        total_edges += len(playbook.edges)
        total_cost += playbook.point_budget_cost
    combined = hashlib.sha256("\n".join(lines).encode()).hexdigest()[:16]
    lines.append(
        f"STATS {len(playbooks)} {total_nodes} {total_edges} {total_cost} {combined}"
    )
    lines.append("END")
    return "\n".join(lines) + "\n"


def compile_playbook_runtime(project_root: Path, output: Path | None = None) -> Path:
    root = Path(project_root).resolve()
    source_root = root / "content/core/playbooks"
    paths = sorted(source_root.rglob("*.playbook"))
    if not paths:
        raise ValueError(f"no playbooks found under {source_root}")
    playbooks: list[Playbook] = []
    relative_sources: list[str] = []
    seen: set[str] = set()
    for path in paths:
        playbook = load_playbook(path)
        if playbook.playbook_id in seen:
            raise ValueError(f"duplicate playbook id: {playbook.playbook_id}")
        seen.add(playbook.playbook_id)
        playbooks.append(playbook)
        relative_sources.append(path.relative_to(root).as_posix())
    destination = Path(output) if output is not None else root / "user_data/studio/playbook_runtime.scplayruntime"
    if not destination.is_absolute():
        destination = root / destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(_encode(playbooks, relative_sources), encoding="utf-8")
    os.replace(temporary, destination)
    print(
        f"Playbook runtime: {len(playbooks)} graphs | "
        f"{sum(len(item.nodes) for item in playbooks)} nodes | "
        f"{sum(len(item.edges) for item in playbooks)} edges | "
        f"budget {sum(item.point_budget_cost for item in playbooks)}"
    )
    print(destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile bounded SignalCloud Playbooks")
    parser.add_argument("project_root", nargs="?", default=".")
    parser.add_argument("--output")
    args = parser.parse_args()
    compile_playbook_runtime(Path(args.project_root), Path(args.output) if args.output else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
