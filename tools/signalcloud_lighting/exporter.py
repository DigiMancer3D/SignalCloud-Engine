#!/usr/bin/env python3
"""Export a managed SignalCloud light document as deterministic canonical .sclight data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .compiler import compile_light_document, resolve_light_source

DEFAULT_OUTPUT = Path("content/user/lights/authoring_lab_export.sclight")
USER_EXPORT_LICENSE = "LicenseRef-SignalCloud-User-Authored"


def _inside(root: Path, path: Path) -> Path:
    root = root.resolve()
    candidate = path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("canonical light export must remain inside the SignalCloud project root") from exc
    return candidate


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        check = json.loads(temporary.read_text(encoding="utf-8"))
        if not isinstance(check, dict):
            raise ValueError("canonical light export validation failed")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def export_sclight(
    root: Path,
    *,
    source: Path | None = None,
    output: Path | None = None,
    compile_runtime: bool = True,
) -> Path:
    root = root.resolve()
    source_path = resolve_light_source(root, source)
    output_path = _inside(root, output or DEFAULT_OUTPUT)
    try:
        source_relative = source_path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("light export source must remain inside the SignalCloud project root") from exc
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("light export source must contain a top-level object")
    payload = dict(raw)
    payload["schema"] = "signalcloud_light_set_v3"
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload["canonical_export"] = {
        "format": "sclight",
        "source_document": source_relative,
        "compatibility": ["slight-v1", "slight-v2", "sclight-v3"],
        "content_sha256": hashlib.sha256(canonical).hexdigest(),
        "data_only": True,
        "license_id": USER_EXPORT_LICENSE,
    }
    _atomic_json(output_path, payload)
    try:
        from tools.asset_doctor.content_abi import write_asset_envelope
        write_asset_envelope(root / "content", output_path, license_id=USER_EXPORT_LICENSE)
    except (ImportError, ValueError, OSError):
        # Export remains usable outside the full Studio environment.
        pass
    if compile_runtime:
        compile_light_document(root, source=output_path)
    return output_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-compile", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        output = export_sclight(
            args.root,
            source=args.source,
            output=args.output,
            compile_runtime=not args.no_compile,
        )
    except Exception as exc:
        print(f"Canonical .sclight export failed: {exc}")
        return 2
    print(f"Canonical .sclight export: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
