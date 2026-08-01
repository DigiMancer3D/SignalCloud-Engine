#!/usr/bin/env python3
"""Bounded, dependency-free SCFONT 1 structural validator."""
from __future__ import annotations

import math
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

HEX_RGBA = re.compile(r"^[0-9A-Fa-f]{8}$")
MAX_GLYPHS = 65_536
MAX_LAYERS_PER_GLYPH = 256
MAX_POINTS = 10_000_000


@dataclass(frozen=True, slots=True)
class ScfontStats:
    name: str
    glyphs: int
    layers: int
    points: int


def _finite(raw: str, label: str, number: int) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"line {number}: {label} is not numeric") from exc
    if not math.isfinite(value):
        raise ValueError(f"line {number}: {label} must be finite")
    return value


def validate_scfont(path: Path) -> ScfontStats:
    path = Path(path)
    header = False
    font_seen = False
    metrics_seen = False
    ended = False
    active_glyph: int | None = None
    active_layer = False
    glyphs: set[int] = set()
    layers_for_glyph = 0
    layer_total = 0
    point_total = 0
    font_name = ""

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read SCFONT: {exc}") from exc

    for number, raw in enumerate(lines, 1):
        cleaned = raw.strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        if ended:
            raise ValueError(f"line {number}: data follows END")
        try:
            parts = shlex.split(cleaned, posix=True)
        except ValueError as exc:
            raise ValueError(f"line {number}: malformed quoting: {exc}") from exc
        if not parts:
            continue
        command = parts[0]
        if not header and command != "SCFONT":
            raise ValueError(f"line {number}: first meaningful record must be SCFONT 1")
        if command == "SCFONT":
            if header or parts != ["SCFONT", "1"]:
                raise ValueError(f"line {number}: expected exactly one SCFONT 1 header")
            header = True
        elif command == "FONT":
            if not header or font_seen or len(parts) != 2 or not parts[1]:
                raise ValueError(f"line {number}: expected one non-empty FONT record")
            font_seen = True
            font_name = parts[1]
        elif command == "METRICS":
            if metrics_seen or len(parts) != 10:
                raise ValueError(f"line {number}: METRICS requires exactly nine values")
            values = [_finite(value, "metric", number) for value in parts[1:]]
            if values[0] <= 0 or values[8] <= 0:
                raise ValueError(f"line {number}: em_size and line_height must be positive")
            metrics_seen = True
        elif command == "GLYPH":
            if active_glyph is not None or active_layer or len(parts) != 3:
                raise ValueError(f"line {number}: malformed or nested GLYPH")
            try:
                codepoint = int(parts[1], 10)
            except ValueError as exc:
                raise ValueError(f"line {number}: invalid glyph codepoint") from exc
            advance = _finite(parts[2], "glyph advance", number)
            if not 0 <= codepoint <= 0x10FFFF:
                raise ValueError(f"line {number}: glyph codepoint is outside Unicode range")
            if advance < 0:
                raise ValueError(f"line {number}: glyph advance cannot be negative")
            if codepoint in glyphs:
                raise ValueError(f"line {number}: duplicate glyph {codepoint}")
            glyphs.add(codepoint)
            if len(glyphs) > MAX_GLYPHS:
                raise ValueError("glyph count exceeds safety limit")
            active_glyph = codepoint
            layers_for_glyph = 0
        elif command == "LAYER":
            if active_glyph is None or active_layer or len(parts) != 4 or not parts[1]:
                raise ValueError(f"line {number}: malformed or nested LAYER")
            opacity = _finite(parts[2], "layer opacity", number)
            if not 0.0 <= opacity <= 1.0:
                raise ValueError(f"line {number}: layer opacity must be from 0 through 1")
            if parts[3] not in {"0", "1"}:
                raise ValueError(f"line {number}: layer visible flag must be 0 or 1")
            active_layer = True
            layers_for_glyph += 1
            layer_total += 1
            if layers_for_glyph > MAX_LAYERS_PER_GLYPH:
                raise ValueError(f"line {number}: glyph layer count exceeds safety limit")
        elif command == "POINT":
            if not active_layer or len(parts) not in {5, 6, 7}:
                raise ValueError(f"line {number}: POINT requires x y z alpha and optional RGBA/group")
            _finite(parts[1], "point x", number)
            _finite(parts[2], "point y", number)
            _finite(parts[3], "point z", number)
            alpha = _finite(parts[4], "point alpha", number)
            if not 0.0 <= alpha <= 1.0:
                raise ValueError(f"line {number}: point alpha must be from 0 through 1")
            if len(parts) >= 6 and not HEX_RGBA.fullmatch(parts[5]):
                raise ValueError(f"line {number}: point color must be eight hexadecimal RGBA digits")
            if len(parts) == 7:
                try:
                    int(parts[6], 10)
                except ValueError as exc:
                    raise ValueError(f"line {number}: point group must be an integer") from exc
            point_total += 1
            if point_total > MAX_POINTS:
                raise ValueError("font point count exceeds safety limit")
        elif command == "ENDLAYER":
            if not active_layer or len(parts) != 1:
                raise ValueError(f"line {number}: ENDLAYER without an open layer")
            active_layer = False
        elif command == "ENDGLYPH":
            if active_glyph is None or active_layer or len(parts) != 1:
                raise ValueError(f"line {number}: ENDGLYPH before ENDLAYER or without GLYPH")
            active_glyph = None
        elif command == "END":
            if active_glyph is not None or active_layer or len(parts) != 1:
                raise ValueError(f"line {number}: END encountered inside an open glyph or layer")
            ended = True
        else:
            raise ValueError(f"line {number}: unknown SCFONT command {command!r}")

    if not header:
        raise ValueError("missing SCFONT 1 header")
    if not font_seen:
        raise ValueError("missing FONT record")
    if not metrics_seen:
        raise ValueError("missing METRICS record")
    if active_layer or active_glyph is not None:
        raise ValueError("unbalanced GLYPH/LAYER records")
    if not ended:
        raise ValueError("missing END record")
    return ScfontStats(font_name, len(glyphs), layer_total, point_total)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Validate a bounded SCFONT 1 asset")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        stats = validate_scfont(args.path)
    except ValueError as exc:
        print(f"SCFONT validation failed: {exc}")
        return 1
    print(
        f"SCFONT validation: {stats.name} | glyphs {stats.glyphs} | "
        f"layers {stats.layers} | points {stats.points} | PASS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
