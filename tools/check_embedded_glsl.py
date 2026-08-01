#!/usr/bin/env python3
"""Small deterministic preflight for embedded GLSL raw strings."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

RAW = re.compile(r'R"GLSL\((.*?)\)GLSL"', re.DOTALL)


def balanced(text: str, opening: str, closing: str) -> bool:
    depth = 0
    for char in text:
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def check(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    blocks = RAW.findall(text)
    errors: list[str] = []
    if len(blocks) < 2:
        errors.append("expected embedded vertex and fragment GLSL blocks")
        return errors
    for index, block in enumerate(blocks):
        if "#version" not in block or "void main()" not in block:
            errors.append(f"GLSL block {index} lacks version or main")
        if not balanced(block, "{", "}"):
            errors.append(f"GLSL block {index} has unbalanced braces")
        if not balanced(block, "(", ")"):
            errors.append(f"GLSL block {index} has unbalanced parentheses")
    vertex = blocks[0]
    required = (
        "uMaterialPatternMode", "uMaterialPrimarySpacing", "uMaterialSecondarySpacing",
        "uMaterialBreakupScale", "uMaterialBreakupStrength",
        "uMaterialDisplacementWeight", "uMaterialColorWeight", "wallFacesX",
    )
    for token in required:
        if token not in vertex:
            errors.append(f"vertex GLSL missing {token}")
    material_start = vertex.find("Stable world-anchored surface coordinates")
    material_end = vertex.find("float deformationPass", material_start)
    if material_start < 0 or material_end < 0:
        errors.append("material projection contract markers are missing")
    elif "uTime" in vertex[material_start:material_end]:
        errors.append("material pattern unexpectedly depends on runtime time")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="engine/render/point_renderer.cpp")
    args = parser.parse_args()
    path = Path(args.path)
    errors = check(path)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(f"PASS: embedded GLSL preflight ({path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
