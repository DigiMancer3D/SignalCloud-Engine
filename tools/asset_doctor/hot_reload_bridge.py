#!/usr/bin/env python3
"""Atomic protected preview-reload staging for validated authoring assets."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .content_abi import parse_udata, pcp3_payload_sha256, scan_content, sha256_file
from tools.signalcloud_lighting.compiler import compile_light_document
from tools.signalcloud_materials.compiler import compile_material_runtime
from tools.signalcloud_audio.compiler import compile_audio_interference_runtime

STATUS_SCHEMA = "signalcloud.hot-reload-status"
STATUS_MODE = "protected-authoring-preview"
SUPPORTED_TYPES = {"light_set", "scui", "pcp3_project", "jitter_map", "texture_graph", "audio_interference_profile", "signalcloud_font"}
SAFE_ID = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass(frozen=True, slots=True)
class HotReloadStageResult:
    status_path: Path
    candidate_count: int
    changed_count: int
    invalid_count: int
    generated_unix: int
    transaction_id: str
    changed_light_count: int = 0
    changed_scui_count: int = 0
    changed_pcp3_count: int = 0
    changed_material_count: int = 0
    changed_audio_count: int = 0
    changed_font_count: int = 0


def _safe_project_path(project_root: Path, value: str) -> Path:
    root = project_root.resolve()
    path = (root / value).resolve()
    path.relative_to(root)
    return path


def _safe_companion_path(asset_path: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("companion path must remain beside the PCP3 project")
    candidate = (asset_path.parent / relative).resolve()
    candidate.relative_to(asset_path.parent.resolve())
    return candidate


def _light_state(payload: dict[str, Any]) -> dict[str, Any]:
    lights = payload.get("lights") if isinstance(payload.get("lights"), list) else []
    light = lights[0] if lights and isinstance(lights[0], dict) else {}
    day_night = payload.get("day_night") if isinstance(payload.get("day_night"), dict) else {}
    return {
        "light_scope": str(light.get("scope", "local")),
        "light_i": float(light.get("illuminosity_percent", 72.0)),
        "light_radius": float(light.get("radius", 10.0)),
        "day_i": float(day_night.get("day_illuminosity_percent", 95.0)),
        "night_i": float(day_night.get("night_illuminosity_percent", 18.0)),
        "time_of_day": float(day_night.get("time_of_day", 0.35)),
    }


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _write_light_overlay(path: Path, source_document: str, values: dict[str, Any]) -> None:
    lines = [
        "@udata 1", "", "[panel]",
        'panel_id: "light_lab.control_surface";',
        f"source_document: {json.dumps(source_document)};",
        'mode: "protected-hot-reload-preview";',
        "", "[state]",
    ]
    for key in ("light_scope", "light_i", "light_radius", "day_i", "night_i", "time_of_day"):
        lines.append(f"{key}: {json.dumps(values[key])};")
    lines.append("")
    _atomic_text(path, "\n".join(lines))


def _write_pcp3_stage(
    path: Path,
    *,
    asset_id: str,
    source_document: str,
    cloud_path: str,
    project_sha256: str,
    cloud_sha256: str,
    point_count: int,
    generated_unix: int,
) -> None:
    lines = [
        "@udata 1", "", "[preview]",
        'schema_name: "signalcloud.pcp3-protected-preview";',
        "schema_major: 1;", "schema_minor: 0;",
        f"asset_id: {json.dumps(asset_id)};",
        f"source_document: {json.dumps(source_document)};",
        f"cloud_path: {json.dumps(cloud_path)};",
        f"project_sha256: {json.dumps(project_sha256)};",
        f"cloud_sha256: {json.dumps(cloud_sha256)};",
        f"point_count: {int(point_count)};",
        f"generated_unix: {generated_unix};",
        'mode: "protected-authoring-preview";',
        "",
    ]
    _atomic_text(path, "\n".join(lines))


def _stage_pcp3(root: Path, path: Path, relative: str, asset_id: str, generated: int) -> tuple[Path, str, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("PCP3 project must be a JSON object")
    cloud_name = str(payload.get("cloud_file", path.with_suffix(".pcp3cloud").name))
    cloud = _safe_companion_path(path, cloud_name)
    if not cloud.is_file():
        raise ValueError(f"required PCP3 cloud companion is missing: {cloud_name}")
    observed_cloud = pcp3_payload_sha256(cloud)
    declared_cloud = str(payload.get("cloud_sha256", ""))
    if declared_cloud and declared_cloud != observed_cloud:
        raise ValueError("PCP3 cloud_sha256 does not match the binary companion")
    safe_id = SAFE_ID.sub("-", asset_id).strip("-.") or "pcp3-preview"
    stage_path = root / "user_data" / "studio" / "hot_reload" / "pcp3" / f"{safe_id}.udata"
    _write_pcp3_stage(
        stage_path,
        asset_id=asset_id,
        source_document=relative,
        cloud_path=cloud.relative_to(root).as_posix(),
        project_sha256=sha256_file(path),
        cloud_sha256=observed_cloud,
        point_count=int(payload.get("point_count", 0) or 0),
        generated_unix=generated,
    )
    return stage_path, observed_cloud, int(payload.get("point_count", 0) or 0)


def stage_preview_reload(project_root: Path) -> HotReloadStageResult:
    root = Path(project_root).resolve()
    index_path = root / "user_data" / "studio" / "hot_reload_candidates.udata"
    sections, warnings = parse_udata(index_path)
    index = sections.get("index", {})
    if str(index.get("schema_name", "")) != "signalcloud.hot-reload-index":
        raise ValueError("protected hot-reload index is missing or invalid")
    if str(index.get("mode", "")) != "protected-authoring-only":
        raise ValueError("hot-reload index is not protected-authoring-only")

    report = scan_content(root / "content")
    valid_by_relative = {
        "content/" + record.relative_path: record
        for record in report.records
        if record.enabled and record.status == "valid"
    }
    generated = int(time.time())
    entries: list[dict[str, Any]] = []
    light_overlay = root / "user_data" / "studio" / "hot_reload" / "light_lab_preview_state.udata"
    invalid_count = 0
    changed_count = 0
    type_counts = {"light_set": 0, "scui": 0, "pcp3_project": 0, "material": 0, "audio": 0, "font": 0}
    for section_name, section in sorted(sections.items()):
        if not section_name.startswith("asset."):
            continue
        relative = str(section.get("relative_path", ""))
        asset_type = str(section.get("asset_type", ""))
        if asset_type not in SUPPORTED_TYPES:
            continue
        entry: dict[str, Any] = {
            "asset_id": str(section.get("asset_id", "")),
            "relative_path": relative,
            "asset_type": asset_type,
            "indexed_sha256": str(section.get("sha256", "")),
            "observed_sha256": "",
            "status": "invalid",
            "staged_state_path": "",
            "compiled_runtime_path": "",
            "companion_sha256": "",
            "point_count": 0,
        }
        try:
            path = _safe_project_path(root, relative)
            if relative not in valid_by_relative or not path.is_file():
                raise ValueError("asset is no longer validated")
            observed = sha256_file(path)
            entry["observed_sha256"] = observed
            entry["status"] = "changed" if observed != entry["indexed_sha256"] else "unchanged"
            if entry["status"] == "changed":
                changed_count += 1
                if asset_type in {"jitter_map", "texture_graph"}:
                    type_counts["material"] += 1
                elif asset_type == "audio_interference_profile":
                    type_counts["audio"] += 1
                elif asset_type == "signalcloud_font":
                    type_counts["font"] += 1
                else:
                    type_counts[asset_type] += 1
                if asset_type == "light_set":
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError("light set must be a JSON object")
                    _write_light_overlay(light_overlay, relative, _light_state(payload))
                    entry["staged_state_path"] = light_overlay.relative_to(root).as_posix()
                    safe_id = SAFE_ID.sub("-", entry["asset_id"]).strip("-.") or "light-preview"
                    compiled_path = root / "user_data" / "studio" / "hot_reload" / "illuminosity" / f"{safe_id}.udata"
                    compile_report = root / "user_data" / "studio" / "hot_reload" / "illuminosity" / f"{safe_id}.json"
                    compile_light_document(
                        root, source=path, output=compiled_path, report=compile_report
                    )
                    entry["compiled_runtime_path"] = compiled_path.relative_to(root).as_posix()
                elif asset_type == "pcp3_project":
                    staged, cloud_hash, point_count = _stage_pcp3(
                        root, path, relative, entry["asset_id"], generated
                    )
                    entry["staged_state_path"] = staged.relative_to(root).as_posix()
                    entry["companion_sha256"] = cloud_hash
                    entry["point_count"] = point_count
                elif asset_type in {"jitter_map", "texture_graph"}:
                    safe_id = SAFE_ID.sub("-", entry["asset_id"]).strip("-.") or "material-preview"
                    compiled_path = root / "user_data" / "studio" / "hot_reload" / "materials" / f"{safe_id}.udata"
                    compile_material_runtime(root, output_relative=compiled_path.relative_to(root).as_posix())
                    entry["compiled_runtime_path"] = compiled_path.relative_to(root).as_posix()
                elif asset_type == "audio_interference_profile":
                    safe_id = SAFE_ID.sub("-", entry["asset_id"]).strip("-.") or "audio-preview"
                    compiled_path = root / "user_data" / "studio" / "hot_reload" / "audio" / f"{safe_id}.udata"
                    compile_audio_interference_runtime(
                        root, source_relative=relative,
                        output_relative=compiled_path.relative_to(root).as_posix(),
                    )
                    entry["compiled_runtime_path"] = compiled_path.relative_to(root).as_posix()
                elif asset_type == "signalcloud_font":
                    # Asset Doctor already ran the bounded SCFONT validator. The
                    # protected transaction references the validated project-relative
                    # source directly; no compiled companion is required.
                    entry["staged_state_path"] = relative
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            if entry["status"] == "changed":
                changed_count -= 1
                if asset_type in {"jitter_map", "texture_graph"}:
                    type_counts["material"] = max(0, type_counts["material"] - 1)
                elif asset_type == "audio_interference_profile":
                    type_counts["audio"] = max(0, type_counts["audio"] - 1)
                elif asset_type == "signalcloud_font":
                    type_counts["font"] = max(0, type_counts["font"] - 1)
                else:
                    type_counts[asset_type] = max(0, type_counts[asset_type] - 1)
            entry["status"] = "invalid"
            entry["error"] = str(exc)
            invalid_count += 1
        entries.append(entry)

    digest_source = "|".join(
        f"{entry['asset_id']}:{entry['observed_sha256']}:{entry['status']}" for entry in entries
    )
    transaction_id = hashlib.sha256(f"{generated}|{digest_source}".encode("utf-8")).hexdigest()[:16]
    status_path = root / "user_data" / "studio" / "hot_reload_latest.udata"
    lines = [
        "@udata 1", "", "[status]",
        f"schema_name: {json.dumps(STATUS_SCHEMA)};",
        "schema_major: 1;", "schema_minor: 4;",
        f"mode: {json.dumps(STATUS_MODE)};",
        f"transaction_id: {json.dumps(transaction_id)};",
        f"generated_unix: {generated};",
        f"candidate_count: {len(entries)};",
        f"changed_count: {changed_count};",
        f"invalid_count: {invalid_count};",
        f"changed_light_count: {type_counts['light_set']};",
        f"changed_scui_count: {type_counts['scui']};",
        f"changed_pcp3_count: {type_counts['pcp3_project']};",
        f"changed_material_count: {type_counts['material']};",
        f"changed_audio_count: {type_counts['audio']};",
        f"changed_font_count: {type_counts['font']};",
        f"warning_count: {len(warnings)};",
        "",
    ]
    for index_value, entry in enumerate(entries):
        lines.append(f"[asset.{index_value}]")
        for key in (
            "asset_id", "relative_path", "asset_type", "indexed_sha256",
            "observed_sha256", "status", "staged_state_path", "compiled_runtime_path", "companion_sha256",
        ):
            lines.append(f"{key}: {json.dumps(entry.get(key, ''))};")
        lines.append(f"point_count: {int(entry.get('point_count', 0) or 0)};")
        if entry.get("error"):
            lines.append(f"error: {json.dumps(entry['error'])};")
        lines.append("")
    _atomic_text(status_path, "\n".join(lines))
    return HotReloadStageResult(
        status_path, len(entries), changed_count, invalid_count, generated,
        transaction_id, type_counts["light_set"], type_counts["scui"], type_counts["pcp3_project"],
        type_counts["material"], type_counts["audio"], type_counts["font"],
    )


def read_status_summary(project_root: Path) -> dict[str, Any]:
    path = Path(project_root).resolve() / "user_data" / "studio" / "hot_reload_latest.udata"
    sections, _warnings = parse_udata(path)
    return dict(sections.get("status", {}))


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage validated SignalCloud authoring assets for protected native preview reload")
    parser.add_argument("project_root", nargs="?", default=".")
    args = parser.parse_args()
    result = stage_preview_reload(Path(args.project_root))
    print(
        f"Protected preview stage: {result.candidate_count} supported candidates | "
        f"{result.changed_count} changed | {result.invalid_count} invalid | tx {result.transaction_id}"
    )
    print(
        f"Changed types: lights {result.changed_light_count} | SCUI {result.changed_scui_count} | "
        f"PCP3 {result.changed_pcp3_count} | materials {result.changed_material_count} | "
        f"audio {result.changed_audio_count} | fonts {result.changed_font_count}"
    )
    print(result.status_path)
    return 1 if result.invalid_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
