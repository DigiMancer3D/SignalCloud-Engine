#!/usr/bin/env python3
"""Dependency-free incremental manifest generator for HRB content assets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ManifestRow:
    asset_id: str
    asset_type: str
    family: str
    pack: str
    relative_path: str
    size_bytes: int
    sha256: str
    modified_ns: int
    enabled: str = "true"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def infer_metadata(relative: Path) -> tuple[str, str, str, str]:
    parts = relative.parts
    pack = parts[0] if parts else "unknown"
    if relative.suffix.lower() == ".scfont":
        return relative.stem, "signalcloud_font", "font", pack
    asset_type = parts[1] if len(parts) > 1 else "pack"
    family = parts[2] if len(parts) > 2 else "general"
    asset_id = relative.stem
    return asset_id, asset_type, family, pack


def discover(content_dir: Path) -> Iterable[Path]:
    for path in sorted(content_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(content_dir)
        if path.name in {"manifest.csv", "manifest_cache.json", "manifest_v2.json"}:
            continue
        if relative.parts and relative.parts[0] == "quarantine":
            continue
        yield path


def load_cache(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def build_manifest(content_dir: Path) -> list[ManifestRow]:
    cache_path = content_dir / "manifest_cache.json"
    old_cache = load_cache(cache_path)
    new_cache: dict[str, dict[str, object]] = {}
    rows: list[ManifestRow] = []

    for path in discover(content_dir):
        relative = path.relative_to(content_dir)
        stat = path.stat()
        cache_key = relative.as_posix()
        cached = old_cache.get(cache_key, {})
        if cached.get("size_bytes") == stat.st_size and cached.get("modified_ns") == stat.st_mtime_ns:
            digest = str(cached.get("sha256", ""))
        else:
            digest = sha256_file(path)

        asset_id, asset_type, family, pack = infer_metadata(relative)
        row = ManifestRow(
            asset_id=asset_id,
            asset_type=asset_type,
            family=family,
            pack=pack,
            relative_path=cache_key,
            size_bytes=stat.st_size,
            sha256=digest,
            modified_ns=stat.st_mtime_ns,
        )
        rows.append(row)
        new_cache[cache_key] = {
            "size_bytes": stat.st_size,
            "modified_ns": stat.st_mtime_ns,
            "sha256": digest,
        }

    manifest_path = content_dir / "manifest.csv"
    temp_manifest = manifest_path.with_suffix(".csv.tmp")
    with temp_manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()) if rows else [
            "asset_id", "asset_type", "family", "pack", "relative_path",
            "size_bytes", "sha256", "modified_ns", "enabled"
        ])
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    os.replace(temp_manifest, manifest_path)

    temp_cache = cache_path.with_suffix(".json.tmp")
    temp_cache.write_text(json.dumps(new_cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp_cache, cache_path)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("content_dir", nargs="?", default="content")
    args = parser.parse_args()
    content_dir = Path(args.content_dir).resolve()
    if not content_dir.is_dir():
        parser.error(f"Content directory does not exist: {content_dir}")
    rows = build_manifest(content_dir)
    print(f"Generated {content_dir / 'manifest.csv'} with {len(rows)} records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
