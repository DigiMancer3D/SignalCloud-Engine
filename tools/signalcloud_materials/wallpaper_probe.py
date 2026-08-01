#!/usr/bin/env python3
"""CPU reference probe for the A5a2r2 wallpaper shader contract."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Iterable

TAU = math.tau


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _smoothstep(low: float, high: float, value: float) -> float:
    if high <= low:
        return 1.0 if value >= high else 0.0
    t = _clamp((value - low) / (high - low), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def wall_shell_mask(rgb: Iterable[float]) -> float:
    r, g, b = (float(component) for component in rgb)
    warm = _smoothstep(0.43, 0.58, r) * _smoothstep(0.36, 0.51, g)
    blue = _smoothstep(0.17, 0.29, b) * (1.0 - _smoothstep(0.58, 0.78, b))
    balance = 1.0 - _smoothstep(0.24, 0.48, abs(r - g))
    return _clamp(warm * blue * balance, 0.0, 1.0)


def wallpaper_pattern(u: float, v: float, material: dict) -> tuple[float, float]:
    jitter = material["jitter"]
    pattern = material["pattern"]
    seed = float(jitter["seed"])
    jg = max(0.001, float(jitter["jG"]))
    jl = max(0.001, float(jitter["jL"]))
    jc = max(0.01, float(jitter["jC"]))
    js = max(0.02, float(jitter["jS"]))
    primary = max(0.08, float(pattern["primary_spacing"]))
    breakup_scale = max(0.2, float(pattern["breakup_scale"]))
    breakup_strength = _clamp(float(pattern["breakup_strength"]), 0.0, 1.0)
    line_width = _clamp(float(pattern["line_width"]), 0.02, 0.48)

    phase = (seed * 0.0000001192092896 % 1.0) * TAU
    primary_wave = math.sin(u * TAU / primary + phase)
    material_macro = math.sin((u + seed * 0.00017) / jg + (v - seed * 0.00011) / js)
    material_local = math.sin((u - v) / jl + seed * 0.0013)
    material_cluster = math.sin(math.hypot(u, v) / jc + seed * 0.00071)
    legacy_grain = math.sin(
        material_macro * 1.73 + material_local * 0.61 + material_cluster * 1.19 + phase * 0.23
    )
    paper_grain = (
        material_macro * 0.31
        + material_local * 0.27
        + material_cluster * 0.22
        + legacy_grain * 0.20
    )
    sparse_seam = _smoothstep(1.0 - line_width, 1.0, abs(primary_wave))
    seam_break_signal = 0.5 + 0.5 * math.sin(
        (u * 0.29 + v * 0.47) * TAU / breakup_scale
        + phase * 0.31
        + legacy_grain * 0.35
    )
    broken_seam = sparse_seam * _smoothstep(0.58, 0.82, seam_break_signal)
    value = _clamp(0.50 + paper_grain * breakup_strength * 0.09 + broken_seam * 0.045, 0.38, 0.64)
    return value, broken_seam


def build_report(material_path: Path, material_label: str | None = None) -> dict:
    material = json.loads(material_path.read_text(encoding="utf-8"))
    horizontal = [wallpaper_pattern(i * 0.05, 1.7, material)[0] for i in range(241)]
    vertical = [wallpaper_pattern(1.2, i * 0.025, material)[0] for i in range(161)]
    seams = [wallpaper_pattern(i * 0.05, 1.7, material)[1] for i in range(241)]
    seam_runs = 0
    active = False
    for value in seams:
        now = value > 0.20
        if now and not active:
            seam_runs += 1
        active = now
    return {
        "schema": "signalcloud_wallpaper_probe_v1",
        "material": material_label or material_path.as_posix(),
        "pattern_min": min(horizontal + vertical),
        "pattern_max": max(horizontal + vertical),
        "pattern_range": max(horizontal + vertical) - min(horizontal + vertical),
        "horizontal_samples": len(horizontal),
        "vertical_samples": len(vertical),
        "sparse_seam_runs_12m": seam_runs,
        "structural_wall_mask": wall_shell_mask((0.72, 0.64, 0.36)),
        "reception_desk_mask": wall_shell_mask((0.31, 0.25, 0.12)),
        "cyan_portal_mask": wall_shell_mask((0.18, 0.86, 0.96)),
        "periodic_height_wave": False,
        "screen_space_wall_weave": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root", nargs="?", default=".")
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    material_relative = Path("content/core/materials/office_wallpaper.jmap")
    report = build_report(root / material_relative, material_relative.as_posix())
    output = Path(args.output).resolve() if args.output else root / "reports/wallpaper_pattern_probe.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Wallpaper probe: "
        f"range {report['pattern_range']:.4f} | seams/12m {report['sparse_seam_runs_12m']} | "
        f"wall mask {report['structural_wall_mask']:.3f} | desk {report['reception_desk_mask']:.3f}"
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
