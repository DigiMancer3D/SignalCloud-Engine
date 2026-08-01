from __future__ import annotations

import json
import math
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from tools.pcp3.io import atomic_write_text
from tools.pcp3.model import PCPDocument, PCPPoint

SCHEMA = "pcp3_streaming_runtime_v1"
PROFILES = ("adaptive_8m", "quality", "balanced", "low_memory", "custom")
LOD_POLICIES = ("distance", "distance_semantic", "fixed")

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "game_enabled": False,
    "stress_enabled": True,
    "profile": "adaptive_8m",
    "lod_policy": "distance_semantic",
    "chunk_edge": 8.0,
    "chunk_point_target": 65_536,
    "near_distance": 16.0,
    "mid_distance": 48.0,
    "far_distance": 120.0,
    "near_ratio": 1.0,
    "mid_ratio": 0.55,
    "far_ratio": 0.22,
    "very_far_ratio": 0.06,
    "minimum_points": 512,
    "maximum_points": 500_000,
    "max_resident_chunks": 64,
    "background_loading": True,
    "preload_adjacent": True,
    "preserve_semantic_points": True,
    "semantic_reserve_ratio": 0.12,
    "frame_upload_budget_points": 100_000,
    "stability_hysteresis": 0.12,
    "show_debug": False,
    "future_attributes": {},
}

PROFILE_PRESETS: dict[str, dict[str, Any]] = {
    "adaptive_8m": {
        "chunk_edge": 8.0,
        "chunk_point_target": 65_536,
        "near_distance": 18.0,
        "mid_distance": 56.0,
        "far_distance": 140.0,
        "near_ratio": 1.0,
        "mid_ratio": 0.60,
        "far_ratio": 0.25,
        "very_far_ratio": 0.07,
        "minimum_points": 768,
        "maximum_points": 500_000,
        "max_resident_chunks": 72,
        "frame_upload_budget_points": 120_000,
    },
    "quality": {
        "chunk_edge": 6.0,
        "chunk_point_target": 98_304,
        "near_distance": 24.0,
        "mid_distance": 72.0,
        "far_distance": 180.0,
        "near_ratio": 1.0,
        "mid_ratio": 0.78,
        "far_ratio": 0.42,
        "very_far_ratio": 0.12,
        "minimum_points": 1_024,
        "maximum_points": 500_000,
        "max_resident_chunks": 96,
        "frame_upload_budget_points": 180_000,
    },
    "balanced": {
        "chunk_edge": 10.0,
        "chunk_point_target": 49_152,
        "near_distance": 15.0,
        "mid_distance": 44.0,
        "far_distance": 110.0,
        "near_ratio": 1.0,
        "mid_ratio": 0.50,
        "far_ratio": 0.18,
        "very_far_ratio": 0.05,
        "minimum_points": 512,
        "maximum_points": 350_000,
        "max_resident_chunks": 56,
        "frame_upload_budget_points": 80_000,
    },
    "low_memory": {
        "chunk_edge": 14.0,
        "chunk_point_target": 32_768,
        "near_distance": 12.0,
        "mid_distance": 32.0,
        "far_distance": 84.0,
        "near_ratio": 0.80,
        "mid_ratio": 0.34,
        "far_ratio": 0.10,
        "very_far_ratio": 0.025,
        "minimum_points": 256,
        "maximum_points": 180_000,
        "max_resident_chunks": 32,
        "frame_upload_budget_points": 45_000,
    },
}

IMPORTANT_FLAGS = {
    2,   # wall
    4,   # floor
    8,   # ceiling
    16,  # portal/opening family in current semantic table
    32,  # light
    64,  # water surface
    128, # water volume / trigger depending on inherited table
}


def ensure_streaming_runtime(document: PCPDocument) -> dict[str, Any]:
    runtime = document.metadata.setdefault("streaming_runtime", {})
    if not isinstance(runtime, dict):
        runtime = {}
        document.metadata["streaming_runtime"] = runtime
    for key, value in DEFAULTS.items():
        runtime.setdefault(key, deepcopy(value))
    profile = str(runtime.get("profile", "adaptive_8m"))
    if profile not in PROFILES:
        runtime["profile"] = "adaptive_8m"
    if str(runtime.get("lod_policy", "distance_semantic")) not in LOD_POLICIES:
        runtime["lod_policy"] = "distance_semantic"
    return runtime


def apply_profile(settings: dict[str, Any], profile: str) -> dict[str, Any]:
    profile = profile if profile in PROFILES else "adaptive_8m"
    settings["profile"] = profile
    if profile != "custom":
        settings.update(deepcopy(PROFILE_PRESETS[profile]))
    return settings


def _float(settings: dict[str, Any], key: str, default: float, low: float, high: float) -> float:
    try:
        value = float(settings.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _int(settings: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(settings.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def normalized_streaming_runtime(document: PCPDocument) -> dict[str, Any]:
    raw = deepcopy(ensure_streaming_runtime(document))
    profile = str(raw.get("profile", "adaptive_8m"))
    if profile not in PROFILES:
        profile = "adaptive_8m"
    raw["profile"] = profile
    raw["lod_policy"] = str(raw.get("lod_policy", "distance_semantic"))
    if raw["lod_policy"] not in LOD_POLICIES:
        raw["lod_policy"] = "distance_semantic"
    for key in ("enabled", "game_enabled", "stress_enabled", "background_loading", "preload_adjacent", "preserve_semantic_points", "show_debug"):
        raw[key] = bool(raw.get(key, DEFAULTS[key]))
    raw["chunk_edge"] = _float(raw, "chunk_edge", 8.0, 1.0, 128.0)
    raw["chunk_point_target"] = _int(raw, "chunk_point_target", 65_536, 1_024, 500_000)
    raw["near_distance"] = _float(raw, "near_distance", 16.0, 0.1, 10_000.0)
    raw["mid_distance"] = _float(raw, "mid_distance", 48.0, raw["near_distance"], 20_000.0)
    raw["far_distance"] = _float(raw, "far_distance", 120.0, raw["mid_distance"], 50_000.0)
    for key, default in (("near_ratio", 1.0), ("mid_ratio", 0.55), ("far_ratio", 0.22), ("very_far_ratio", 0.06), ("semantic_reserve_ratio", 0.12), ("stability_hysteresis", 0.12)):
        raw[key] = _float(raw, key, default, 0.0, 1.0)
    raw["minimum_points"] = _int(raw, "minimum_points", 512, 1, 500_000)
    raw["maximum_points"] = _int(raw, "maximum_points", 500_000, raw["minimum_points"], 500_000)
    raw["max_resident_chunks"] = _int(raw, "max_resident_chunks", 64, 1, 4_096)
    raw["frame_upload_budget_points"] = _int(raw, "frame_upload_budget_points", 100_000, 1_000, 2_000_000)
    if not isinstance(raw.get("future_attributes"), dict):
        raw["future_attributes"] = {}
    return raw


def validate_streaming_runtime(document: PCPDocument) -> list[dict[str, str]]:
    cfg = normalized_streaming_runtime(document)
    findings: list[dict[str, str]] = []
    if not cfg["enabled"]:
        findings.append({"severity": "info", "message": "Streaming Runtime is disabled; inherited full-detail behavior remains unchanged."})
    if cfg["enabled"] and not (cfg["game_enabled"] or cfg["stress_enabled"]):
        findings.append({"severity": "warning", "message": "Streaming Runtime is enabled but has no execution target."})
    if not (cfg["near_distance"] <= cfg["mid_distance"] <= cfg["far_distance"]):
        findings.append({"severity": "error", "message": "LOD distances must be ordered near ≤ mid ≤ far."})
    ratios = [cfg["near_ratio"], cfg["mid_ratio"], cfg["far_ratio"], cfg["very_far_ratio"]]
    if any(a < b for a, b in zip(ratios, ratios[1:])):
        findings.append({"severity": "warning", "message": "LOD ratios normally descend from near to very-far."})
    if cfg["minimum_points"] > cfg["maximum_points"]:
        findings.append({"severity": "error", "message": "Minimum points exceeds maximum points."})
    if cfg["chunk_point_target"] > cfg["maximum_points"]:
        findings.append({"severity": "info", "message": "A single chunk target exceeds the per-asset runtime maximum; runtime sampling will clamp it."})
    estimated_chunks = max(1, math.ceil(max(1, len(document.points)) / cfg["chunk_point_target"]))
    if estimated_chunks > cfg["max_resident_chunks"] * 4:
        findings.append({"severity": "warning", "message": f"Estimated {estimated_chunks} chunks greatly exceeds the resident cap {cfg['max_resident_chunks']}; verify pop-in during live testing."})
    if cfg["preserve_semantic_points"] and cfg["semantic_reserve_ratio"] <= 0.0:
        findings.append({"severity": "warning", "message": "Semantic preservation is enabled with a zero reserve ratio."})
    if not any(item["severity"] == "error" for item in findings):
        findings.append({"severity": "pass", "message": "Streaming configuration is bounded and can be compiled without modifying source geometry."})
    return findings


def _chunk_key(point: PCPPoint, edge: float) -> tuple[int, int, int]:
    return (
        math.floor(point.x / edge),
        math.floor(point.y / edge),
        math.floor(point.z / edge),
    )


def _important(point: PCPPoint) -> bool:
    return int(point.flags) != 0


def build_chunk_manifest(document: PCPDocument, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = normalized_streaming_runtime(document) if settings is None else deepcopy(settings)
    edge = max(1.0, float(cfg["chunk_edge"]))
    buckets: dict[tuple[int, int, int], list[PCPPoint]] = defaultdict(list)
    for point in document.points:
        buckets[_chunk_key(point, edge)].append(point)

    chunks: list[dict[str, Any]] = []
    total_important = 0
    for index, (key, points) in enumerate(sorted(buckets.items())):
        xs = [p.x for p in points]
        ys = [p.y for p in points]
        zs = [p.z for p in points]
        important = sum(1 for point in points if _important(point))
        total_important += important
        center = [sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs)]
        radius = max(math.dist((p.x, p.y, p.z), center) for p in points) if points else 0.0
        chunks.append({
            "id": f"chunk_{index:05d}",
            "grid": list(key),
            "center": [round(value, 6) for value in center],
            "radius": round(radius, 6),
            "point_count": len(points),
            "important_points": important,
            "lod_counts": {
                "near": min(len(points), max(1, math.ceil(len(points) * cfg["near_ratio"]))),
                "mid": min(len(points), max(1, math.ceil(len(points) * cfg["mid_ratio"]))),
                "far": min(len(points), max(1, math.ceil(len(points) * cfg["far_ratio"]))),
                "very_far": min(len(points), max(1, math.ceil(len(points) * cfg["very_far_ratio"]))),
            },
        })
    return {
        "schema": "pcp3_stream_chunk_manifest_v1",
        "asset_id": document.asset_id,
        "project_id": document.project_id,
        "source_point_count": len(document.points),
        "chunk_edge": edge,
        "chunk_count": len(chunks),
        "important_point_count": total_important,
        "chunks": chunks,
    }


def ratio_for_distance(settings: dict[str, Any], distance: float) -> float:
    distance = max(0.0, float(distance))
    if settings["lod_policy"] == "fixed":
        return float(settings["near_ratio"])
    if distance <= settings["near_distance"]:
        return float(settings["near_ratio"])
    if distance <= settings["mid_distance"]:
        return float(settings["mid_ratio"])
    if distance <= settings["far_distance"]:
        return float(settings["far_ratio"])
    return float(settings["very_far_ratio"])


def planned_point_count(document: PCPDocument, distance: float, settings: dict[str, Any] | None = None) -> int:
    cfg = normalized_streaming_runtime(document) if settings is None else settings
    available = len(document.points)
    if available == 0:
        return 0
    requested = math.ceil(available * ratio_for_distance(cfg, distance))
    return min(available, cfg["maximum_points"], max(min(available, cfg["minimum_points"]), requested))


def compile_streaming_runtime(document: PCPDocument) -> dict[str, Any]:
    cfg = normalized_streaming_runtime(document)
    manifest = build_chunk_manifest(document, cfg)
    findings = validate_streaming_runtime(document)
    samples = []
    for label, distance in (
        ("near", 0.0),
        ("mid", cfg["near_distance"] + 0.001),
        ("far", cfg["mid_distance"] + 0.001),
        ("very_far", cfg["far_distance"] + 0.001),
    ):
        samples.append({
            "tier": label,
            "distance": round(distance, 6),
            "ratio": ratio_for_distance(cfg, distance),
            "planned_points": planned_point_count(document, distance, cfg),
        })
    return {
        "schema": SCHEMA,
        "asset_id": document.asset_id,
        "project_id": document.project_id,
        "enabled": cfg["enabled"],
        "targets": {"game": cfg["game_enabled"], "stress": cfg["stress_enabled"]},
        "profile": cfg["profile"],
        "lod_policy": cfg["lod_policy"],
        "chunking": {
            "edge": cfg["chunk_edge"],
            "point_target": cfg["chunk_point_target"],
            "max_resident_chunks": cfg["max_resident_chunks"],
            "background_loading": cfg["background_loading"],
            "preload_adjacent": cfg["preload_adjacent"],
        },
        "distances": {
            "near": cfg["near_distance"],
            "mid": cfg["mid_distance"],
            "far": cfg["far_distance"],
        },
        "ratios": {
            "near": cfg["near_ratio"],
            "mid": cfg["mid_ratio"],
            "far": cfg["far_ratio"],
            "very_far": cfg["very_far_ratio"],
        },
        "limits": {
            "minimum_points": cfg["minimum_points"],
            "maximum_points": cfg["maximum_points"],
            "frame_upload_budget_points": cfg["frame_upload_budget_points"],
        },
        "semantic_priority": {
            "enabled": cfg["preserve_semantic_points"],
            "reserve_ratio": cfg["semantic_reserve_ratio"],
        },
        "stability_hysteresis": cfg["stability_hysteresis"],
        "show_debug": cfg["show_debug"],
        "source_point_count": len(document.points),
        "chunk_count": manifest["chunk_count"],
        "important_point_count": manifest["important_point_count"],
        "lod_samples": samples,
        "findings": findings,
        "runtime_policy": {
            "source_geometry_mutation": False,
            "save_mutation": False,
            "background_loader_status": "bounded_intent_and_manifest",
            "current_execution": "distance_lod_and_semantic_reserve",
        },
        "future_attributes": deepcopy(cfg.get("future_attributes", {})),
    }


def _q(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def streaming_runtime_udata(payload: dict[str, Any]) -> str:
    targets = payload["targets"]
    chunk = payload["chunking"]
    distances = payload["distances"]
    ratios = payload["ratios"]
    limits = payload["limits"]
    semantic = payload["semantic_priority"]
    lines = [
        "@format: udata;",
        f"@schema: {_q(SCHEMA)};",
        "",
        "[streaming]",
        f"enabled: {_q(bool(payload['enabled']))};",
        f"game_enabled: {_q(bool(targets['game']))};",
        f"stress_enabled: {_q(bool(targets['stress']))};",
        f"profile: {_q(payload['profile'])};",
        f"lod_policy: {_q(payload['lod_policy'])};",
        f"chunk_edge: {float(chunk['edge']):.6f};",
        f"chunk_point_target: {int(chunk['point_target'])};",
        f"max_resident_chunks: {int(chunk['max_resident_chunks'])};",
        f"background_loading: {_q(bool(chunk['background_loading']))};",
        f"preload_adjacent: {_q(bool(chunk['preload_adjacent']))};",
        f"near_distance: {float(distances['near']):.6f};",
        f"mid_distance: {float(distances['mid']):.6f};",
        f"far_distance: {float(distances['far']):.6f};",
        f"near_ratio: {float(ratios['near']):.6f};",
        f"mid_ratio: {float(ratios['mid']):.6f};",
        f"far_ratio: {float(ratios['far']):.6f};",
        f"very_far_ratio: {float(ratios['very_far']):.6f};",
        f"minimum_points: {int(limits['minimum_points'])};",
        f"maximum_points: {int(limits['maximum_points'])};",
        f"frame_upload_budget_points: {int(limits['frame_upload_budget_points'])};",
        f"preserve_semantic_points: {_q(bool(semantic['enabled']))};",
        f"semantic_reserve_ratio: {float(semantic['reserve_ratio']):.6f};",
        f"stability_hysteresis: {float(payload['stability_hysteresis']):.6f};",
        f"show_debug: {_q(bool(payload['show_debug']))};",
        f"source_point_count: {int(payload['source_point_count'])};",
        f"chunk_count: {int(payload['chunk_count'])};",
        "",
    ]
    return "\n".join(lines)


def write_streaming_runtime_files(asset_dir: Path, document: PCPDocument) -> dict[str, Path]:
    payload = compile_streaming_runtime(document)
    manifest = build_chunk_manifest(document)
    asset_name = document.asset_id.strip() or "untitled_asset"
    json_path = asset_dir / f"{asset_name}.pcp3stream.json"
    udata_path = asset_dir / f"{asset_name}.pcp3stream.udata"
    chunks_path = asset_dir / f"{asset_name}.pcp3chunks.json"
    atomic_write_text(json_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    atomic_write_text(udata_path, streaming_runtime_udata(payload))
    atomic_write_text(chunks_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {"json": json_path, "udata": udata_path, "chunks": chunks_path}
