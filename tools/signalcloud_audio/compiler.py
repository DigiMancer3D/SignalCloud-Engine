#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = "signalcloud_audio_interference_profile_v1"
BANDS = {"low", "mid", "high", "broadband"}


def _clamp(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return max(lo, min(hi, number))


def _u32(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, number))


def _safe(root: Path, relative: str) -> Path:
    root = root.resolve()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"path escapes project root: {relative}")
    return candidate


def _q(value: str) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class AudioCompileResult:
    output: Path
    profile_count: int
    warning_count: int
    point_budget_cost: int
    signature: str


def compile_audio_interference_runtime(
    project_root: Path,
    source_relative: str = "content/core/audio/hash_dog_bark.scaudio",
    output_relative: str = "user_data/studio/audio_interference_runtime.udata",
) -> AudioCompileResult:
    root = Path(project_root).resolve()
    managed = root / "content/user/audio/hash_dog_bark.scaudio"
    if source_relative == "content/core/audio/hash_dog_bark.scaudio" and managed.is_file():
        source_relative = managed.relative_to(root).as_posix()
    source = _safe(root, source_relative)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise ValueError("unsupported audio-interference profile schema")

    warnings: list[str] = []
    asset_id = str(payload.get("asset_id", "core.audio.hash_dog_bark")).strip()[:96]
    if not asset_id:
        asset_id = "core.audio.hash_dog_bark"
        warnings.append("empty asset_id defaulted")
    band = str(payload.get("frequency_band", "mid")).lower()
    if band not in BANDS:
        band = "mid"
        warnings.append("unknown frequency band defaulted")
    event = payload.get("event", {}) if isinstance(payload.get("event"), dict) else {}
    visual = payload.get("visual", {}) if isinstance(payload.get("visual"), dict) else {}
    gameplay = payload.get("gameplay", {}) if isinstance(payload.get("gameplay"), dict) else {}
    runtime = payload.get("runtime", {}) if isinstance(payload.get("runtime"), dict) else {}
    normalized = {
        "asset_id": asset_id,
        "name": str(payload.get("name", asset_id))[:96],
        "frequency_band": band,
        "strength": _clamp(event.get("strength"), 0.08, 1.0, 0.82),
        "duration_seconds": _clamp(event.get("duration_seconds"), 0.18, 1.8, 1.08),
        "obstruction_path": _clamp(event.get("obstruction_path"), 0.0, 1.0, 0.12),
        "seed_salt": _u32(event.get("seed_salt"), 1, 0xFFFFFFFF, 0xA5A30001),
        "radius_scale": _clamp(visual.get("radius_scale"), 0.35, 2.0, 1.0),
        "wave_count": _u32(visual.get("wave_count"), 1, 8, 3),
        "wave_sharpness": _clamp(visual.get("wave_sharpness"), 0.08, 1.0, 0.72),
        "displacement_scale": _clamp(visual.get("displacement_scale"), 0.0, 1.5, 0.82),
        "color_mix": _clamp(visual.get("color_mix"), 0.0, 1.0, 0.34),
        "visibility_floor": _clamp(visual.get("visibility_floor"), 0.0, 0.4, 0.08),
        "hearing_loudness": _clamp(gameplay.get("hearing_loudness"), 0.08, 1.25, 0.86),
        "cooldown_seconds": _clamp(gameplay.get("cooldown_seconds"), 0.5, 60.0, 7.5),
        "point_budget_cost": _u32(runtime.get("point_budget_cost"), 0, 4096, 224),
    }
    signature_source = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    signature = hashlib.sha256(signature_source.encode("utf-8")).hexdigest()[:16]
    output = _safe(root, output_relative)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "@udata 1", "", "[meta]",
        'schema: "signalcloud_audio_interference_runtime_v1";',
        f"source_profile: {_q(source.relative_to(root).as_posix())};",
        "profile_count: 1;",
        f"warning_count: {len(warnings)};",
        f"signature: {_q(signature)};",
        "", "[profile.0]",
    ]
    for key in ("asset_id", "name", "frequency_band"):
        lines.append(f"{key}: {_q(str(normalized[key]))};")
    for key in (
        "strength", "duration_seconds", "obstruction_path", "radius_scale",
        "wave_sharpness", "displacement_scale", "color_mix", "visibility_floor",
        "hearing_loudness", "cooldown_seconds",
    ):
        lines.append(f"{key}: {float(normalized[key]):.6f};")
    for key in ("seed_salt", "wave_count", "point_budget_cost"):
        lines.append(f"{key}: {int(normalized[key])};")
    lines.append("")
    output.write_text("\n".join(lines), encoding="utf-8")
    report = output.with_suffix(".json")
    report.write_text(json.dumps({
        "schema": "signalcloud_audio_interference_compile_report_v1",
        "source": source.relative_to(root).as_posix(),
        "output": output.relative_to(root).as_posix(),
        "warnings": warnings,
        "profile": normalized,
        "signature": signature,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return AudioCompileResult(output, 1, len(warnings), int(normalized["point_budget_cost"]), signature)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile a SignalCloud authored audio-interference profile")
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--source", default="content/core/audio/hash_dog_bark.scaudio")
    parser.add_argument("--output", default="user_data/studio/audio_interference_runtime.udata")
    args = parser.parse_args()
    result = compile_audio_interference_runtime(args.project_root, args.source, args.output)
    print(f"Audio interference runtime: {result.profile_count} profile | budget {result.point_budget_cost} | warnings {result.warning_count} | sig {result.signature}")
    print(result.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
