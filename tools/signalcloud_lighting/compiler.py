#!/usr/bin/env python3
"""Compile a managed SignalCloud light document into the native runtime sidecar.

The authored JSON remains the source of truth.  The native game consumes a small,
strict .udata sidecar so the renderer never needs a general-purpose JSON parser.
Unknown source fields remain untouched because this compiler is read-only.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA_NAMES = {"signalcloud_light_set_v1", "signalcloud_light_set_v2", "signalcloud_light_set_v3"}
SCOPES = {"local", "area", "room", "global"}
SHADOW_POLICIES = {"none", "analytic", "portal-aware"}
DAY_NIGHT_BINDINGS = {"none", "global", "multiply"}
DEFAULT_SOURCE = Path("content/core/lights/authoring_lab_default.slight")
MANAGED_SOURCE = Path("content/user/lights/authoring_lab_scui_light.slight")
DEFAULT_OUTPUT = Path("user_data/studio/illuminosity_runtime.udata")
DEFAULT_REPORT = Path("reports/illuminosity_compile_report.json")


@dataclass(frozen=True)
class CompileResult:
    source_path: Path
    output_path: Path
    report_path: Path
    light_count: int
    enabled_count: int
    warning_count: int
    point_budget_cost: int
    used_fallback: bool
    max_active_lights: int
    max_point_budget: int
    selected_light_count: int
    selected_point_budget_cost: int


def _finite_number(value: Any, fallback: float, minimum: float, maximum: float, warnings: list[str], label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        warnings.append(f"{label}: invalid number; defaulted to {fallback}")
        return fallback
    if not math.isfinite(number):
        warnings.append(f"{label}: non-finite number; defaulted to {fallback}")
        return fallback
    if number < minimum or number > maximum:
        clamped = max(minimum, min(maximum, number))
        warnings.append(f"{label}: clamped from {number} to {clamped}")
        return clamped
    return number


def _integer(value: Any, fallback: int, minimum: int, maximum: int, warnings: list[str], label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        warnings.append(f"{label}: invalid integer; defaulted to {fallback}")
        return fallback
    if number < minimum or number > maximum:
        clamped = max(minimum, min(maximum, number))
        warnings.append(f"{label}: clamped from {number} to {clamped}")
        return clamped
    return number


def _vector(value: Any, fallback: tuple[float, float, float], warnings: list[str], label: str, *, color: bool = False) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        warnings.append(f"{label}: invalid vector; defaulted")
        return list(fallback)
    result: list[float] = []
    low, high = ((0.0, 1.0) if color else (-100000.0, 100000.0))
    for index in range(3):
        result.append(_finite_number(value[index], fallback[index], low, high, warnings, f"{label}[{index}]"))
    return result


def _safe_text(value: Any, fallback: str, warnings: list[str], label: str, *, maximum: int = 160) -> str:
    if not isinstance(value, str) or not value.strip():
        warnings.append(f"{label}: invalid text; defaulted to {fallback!r}")
        return fallback
    text = value.strip().replace("\x00", "")
    if len(text) > maximum:
        warnings.append(f"{label}: truncated to {maximum} characters")
        text = text[:maximum]
    return text


def _choice(value: Any, fallback: str, allowed: set[str], warnings: list[str], label: str) -> str:
    text = str(value).strip().lower() if value is not None else ""
    if text not in allowed:
        warnings.append(f"{label}: unsupported value {text!r}; defaulted to {fallback!r}")
        return fallback
    return text


def _bool(value: Any, fallback: bool, warnings: list[str], label: str) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    warnings.append(f"{label}: invalid boolean; defaulted to {fallback}")
    return fallback


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _udata_line(key: str, value: Any) -> str:
    return f"{key}: {_json(value)};"


def resolve_light_source(root: Path, explicit: Path | None = None) -> Path:
    root = root.resolve()
    if explicit is not None:
        candidate = explicit if explicit.is_absolute() else root / explicit
        return candidate.resolve()
    managed = root / MANAGED_SOURCE
    if managed.is_file():
        return managed.resolve()
    return (root / DEFAULT_SOURCE).resolve()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _compile_light(raw: Any, index: int, warnings: list[str]) -> dict[str, Any] | None:
    prefix = f"lights[{index}]"
    if not isinstance(raw, dict):
        warnings.append(f"{prefix}: record is not an object and was skipped")
        return None
    identifier = _safe_text(raw.get("id"), f"light-{index + 1:03d}", warnings, f"{prefix}.id", maximum=96)
    name = _safe_text(raw.get("name"), f"Light {index + 1}", warnings, f"{prefix}.name")
    position = _vector(raw.get("position"), (0.0, 3.4, 3.0), warnings, f"{prefix}.position")
    target = _vector(raw.get("target"), (0.0, 1.2, 0.0), warnings, f"{prefix}.target")
    color = _vector(raw.get("color"), (1.0, 0.78, 0.42), warnings, f"{prefix}.color", color=True)
    illuminosity = _finite_number(raw.get("illuminosity_percent"), 72.0, 0.0, 160.0, warnings, f"{prefix}.illuminosity_percent")
    aperture_distance = _finite_number(raw.get("aperture_distance"), 2.5, 0.0, 100.0, warnings, f"{prefix}.aperture_distance")
    radius = _finite_number(raw.get("radius"), 10.0, 0.05, 250.0, warnings, f"{prefix}.radius")
    degree_burst = _finite_number(raw.get("cone_or_degree_burst"), 80.0, 0.0, 360.0, warnings, f"{prefix}.cone_or_degree_burst")
    scope = _choice(raw.get("scope"), "local", SCOPES, warnings, f"{prefix}.scope")
    zone = _safe_text(raw.get("zone"), "Reception Tape", warnings, f"{prefix}.zone")
    enabled = _bool(raw.get("enabled", True), True, warnings, f"{prefix}.enabled")
    dynamic = _bool(raw.get("dynamic", False), False, warnings, f"{prefix}.dynamic")
    bounce_limit = _integer(raw.get("bounce_count_limit"), 1, 0, 4, warnings, f"{prefix}.bounce_count_limit")
    bounce_cost = _finite_number(raw.get("bounce_cost"), 0.34, 0.0, 1.0, warnings, f"{prefix}.bounce_cost")
    shadow_policy = _choice(raw.get("shadow_policy"), "analytic", SHADOW_POLICIES, warnings, f"{prefix}.shadow_policy")
    day_night_binding = _choice(raw.get("day_night_binding"), "multiply", DAY_NIGHT_BINDINGS, warnings, f"{prefix}.day_night_binding")
    default_budget = 256 + bounce_limit * 128
    point_budget_cost = _integer(raw.get("point_budget_cost"), default_budget, 0, 200000, warnings, f"{prefix}.point_budget_cost")
    budget_priority = _integer(raw.get("budget_priority"), 100, 0, 1000, warnings, f"{prefix}.budget_priority")
    seed = _integer(raw.get("seed"), 0, 0, 2_147_483_647, warnings, f"{prefix}.seed")
    return {
        "id": identifier,
        "name": name,
        "position": position,
        "target": target,
        "color": color,
        "illuminosity_percent": illuminosity,
        "aperture_distance": aperture_distance,
        "radius": radius,
        "cone_or_degree_burst": degree_burst,
        "scope": scope,
        "zone": zone,
        "enabled": enabled,
        "dynamic": dynamic,
        "bounce_count_limit": bounce_limit,
        "bounce_cost": bounce_cost,
        "shadow_policy": shadow_policy,
        "day_night_binding": day_night_binding,
        "point_budget_cost": point_budget_cost,
        "budget_priority": budget_priority,
        "seed": seed,
    }


def _compile_day_night(raw: Any, warnings: list[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        warnings.append("day_night: record is not an object; safe defaults applied")
        raw = {}
    return {
        "day_color": _vector(raw.get("day_color"), (1.0, 0.95, 0.85), warnings, "day_night.day_color", color=True),
        "day_illuminosity_percent": _finite_number(raw.get("day_illuminosity_percent"), 95.0, 0.0, 160.0, warnings, "day_night.day_illuminosity_percent"),
        "night_color": _vector(raw.get("night_color"), (0.15, 0.18, 0.35), warnings, "day_night.night_color", color=True),
        "night_illuminosity_percent": _finite_number(raw.get("night_illuminosity_percent"), 18.0, 0.0, 160.0, warnings, "day_night.night_illuminosity_percent"),
        "day_to_night_seconds": _finite_number(raw.get("day_to_night_seconds"), 45.0, 1.0, 86400.0, warnings, "day_night.day_to_night_seconds"),
        "night_to_day_seconds": _finite_number(raw.get("night_to_day_seconds"), 60.0, 1.0, 86400.0, warnings, "day_night.night_to_day_seconds"),
        "time_of_day": _finite_number(raw.get("time_of_day"), 0.35, 0.0, 1.0, warnings, "day_night.time_of_day"),
        "playing": _bool(raw.get("playing", False), False, warnings, "day_night.playing"),
        "paused": _bool(raw.get("paused", False), False, warnings, "day_night.paused"),
        "protected_global": _bool(raw.get("protected_global", True), True, warnings, "day_night.protected_global"),
    }



def _compile_runtime_budget(raw: Any, warnings: list[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        warnings.append("runtime_budget: record is not an object; safe defaults applied")
        raw = {}
    return {
        "max_active_lights": _integer(raw.get("max_active_lights"), 8, 1, 64, warnings, "runtime_budget.max_active_lights"),
        "max_point_budget": _integer(raw.get("max_point_budget"), 4096, 64, 2_000_000, warnings, "runtime_budget.max_point_budget"),
        "rays_per_light": _integer(raw.get("rays_per_light"), 8, 1, 16, warnings, "runtime_budget.rays_per_light"),
        "max_diagnostic_rays": _integer(raw.get("max_diagnostic_rays"), 32, 1, 128, warnings, "runtime_budget.max_diagnostic_rays"),
        "stress_scale": _finite_number(raw.get("stress_scale"), 1.0, 0.1, 2.0, warnings, "runtime_budget.stress_scale"),
    }


def _select_budgeted_lights(lights: list[dict[str, Any]], runtime_budget: dict[str, Any]) -> tuple[int, int]:
    candidates = sorted(
        ((index, light) for index, light in enumerate(lights) if light["enabled"]),
        key=lambda item: (-int(item[1]["budget_priority"]), str(item[1]["id"]), item[0]),
    )
    max_count = int(runtime_budget["max_active_lights"])
    max_budget = int(round(int(runtime_budget["max_point_budget"]) * float(runtime_budget["stress_scale"])))
    selected_count = 0
    selected_cost = 0
    for _index, light in candidates:
        cost = int(light["point_budget_cost"])
        if selected_count >= max_count or selected_cost + cost > max_budget:
            continue
        selected_count += 1
        selected_cost += cost
    return selected_count, selected_cost

def _render_udata(source_relative: str, lights: Iterable[dict[str, Any]], day_night: dict[str, Any], runtime_budget: dict[str, Any], warnings: list[str], used_fallback: bool) -> str:
    compiled = list(lights)
    point_budget = sum(int(item["point_budget_cost"]) for item in compiled if item["enabled"])
    enabled_count = sum(1 for item in compiled if item["enabled"])
    lines = [
        "@udata 1",
        "",
        "[document]",
        _udata_line("schema_name", "signalcloud.illuminosity-runtime"),
        _udata_line("schema_major", 1),
        _udata_line("source_document", source_relative),
        _udata_line("light_count", len(compiled)),
        _udata_line("enabled_count", enabled_count),
        _udata_line("warning_count", len(warnings)),
        _udata_line("point_budget_cost", point_budget),
        _udata_line("used_fallback", used_fallback),
        "",
        "[runtime-budget]",
    ]
    for key, value in runtime_budget.items():
        lines.append(_udata_line(key, value))
    lines.extend(["", "[day-night]"])
    for key, value in day_night.items():
        lines.append(_udata_line(key, value))
    for index, light in enumerate(compiled):
        lines.extend(["", f"[light.{index}]"])
        for key, value in light.items():
            lines.append(_udata_line(key, value))
    lines.extend(["", "[warnings]", _udata_line("items", warnings), ""])
    return "\n".join(lines)


def compile_light_document(
    root: Path,
    *,
    source: Path | None = None,
    output: Path | None = None,
    report: Path | None = None,
) -> CompileResult:
    root = root.resolve()
    source_path = resolve_light_source(root, source)
    try:
        source_relative = source_path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("light source must remain inside the SignalCloud project root") from exc
    if not source_path.is_file():
        raise FileNotFoundError(f"light source not found: {source_path}")
    output_path = (output if output and output.is_absolute() else root / (output or DEFAULT_OUTPUT)).resolve()
    report_path = (report if report and report.is_absolute() else root / (report or DEFAULT_REPORT)).resolve()
    for candidate in (output_path, report_path):
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("compiled light outputs must remain inside the project root") from exc

    warnings: list[str] = []
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to parse light source: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("light source root must be a JSON object")
    schema = str(payload.get("schema", "signalcloud_light_set_v1"))
    if schema not in SCHEMA_NAMES:
        warnings.append(f"schema: unsupported {schema!r}; interpreted with v1 defaults")

    raw_lights = payload.get("lights", [])
    if not isinstance(raw_lights, list):
        warnings.append("lights: expected an array; safe fallback inserted")
        raw_lights = []
    lights = [item for index, raw in enumerate(raw_lights) if (item := _compile_light(raw, index, warnings)) is not None]
    used_fallback = False
    if not lights:
        used_fallback = True
        warnings.append("lights: no valid records remained; inserted disabled safe fallback")
        lights = [{
            "id": "safe-fallback",
            "name": "Disabled Safe Fallback",
            "position": [0.0, 3.4, 3.0],
            "target": [0.0, 1.2, 0.0],
            "color": [1.0, 1.0, 1.0],
            "illuminosity_percent": 0.0,
            "aperture_distance": 2.5,
            "radius": 1.0,
            "cone_or_degree_burst": 80.0,
            "scope": "local",
            "zone": "Reception Tape",
            "enabled": False,
            "dynamic": False,
            "bounce_count_limit": 0,
            "bounce_cost": 0.34,
            "shadow_policy": "none",
            "day_night_binding": "none",
            "point_budget_cost": 0,
            "budget_priority": 0,
            "seed": 0,
        }]
    day_night = _compile_day_night(payload.get("day_night"), warnings)
    runtime_budget = _compile_runtime_budget(payload.get("runtime_budget"), warnings)
    selected_count, selected_cost = _select_budgeted_lights(lights, runtime_budget)
    if selected_count < sum(1 for item in lights if item["enabled"]):
        warnings.append("runtime_budget: one or more enabled lights are deterministically budget-limited")
    text = _render_udata(source_relative, lights, day_night, runtime_budget, warnings, used_fallback)
    _atomic_write_text(output_path, text)

    enabled_count = sum(1 for item in lights if item["enabled"])
    point_budget = sum(int(item["point_budget_cost"]) for item in lights if item["enabled"])
    report_payload = {
        "schema": "signalcloud_illuminosity_compile_report_v1",
        "source_document": source_relative,
        "runtime_sidecar": output_path.relative_to(root).as_posix(),
        "light_count": len(lights),
        "enabled_count": enabled_count,
        "warning_count": len(warnings),
        "point_budget_cost": point_budget,
        "used_fallback": used_fallback,
        "runtime_budget": runtime_budget,
        "selected_light_count": selected_count,
        "selected_point_budget_cost": selected_cost,
        "budget_limited_count": max(0, enabled_count - selected_count),
        "warnings": warnings,
    }
    _atomic_write_text(report_path, json.dumps(report_payload, indent=2, sort_keys=True) + "\n")
    return CompileResult(
        source_path=source_path,
        output_path=output_path,
        report_path=report_path,
        light_count=len(lights),
        enabled_count=enabled_count,
        warning_count=len(warnings),
        point_budget_cost=point_budget,
        used_fallback=used_fallback,
        max_active_lights=int(runtime_budget["max_active_lights"]),
        max_point_budget=int(runtime_budget["max_point_budget"]),
        selected_light_count=selected_count,
        selected_point_budget_cost=selected_cost,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = compile_light_document(args.root, source=args.source, output=args.output, report=args.report)
    except Exception as exc:  # CLI boundary
        print(f"Illuminosity compile failed: {exc}")
        return 2
    print(
        "Illuminosity runtime: "
        f"{result.light_count} lights | {result.enabled_count} enabled | "
        f"budget {result.selected_point_budget_cost}/{result.max_point_budget} | "
        f"active {result.selected_light_count}/{result.light_count} | warnings {result.warning_count}"
    )
    print(result.output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
