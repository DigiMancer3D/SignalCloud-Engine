#!/usr/bin/env python3
"""Data-only SignalCloud pack builder.

Packs contain validated content and explicit ABI envelopes only. Executables,
Python modules, shell scripts, symlinks, caches, reports, and persistent saves
are rejected rather than bundled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

from .content_abi import (
    ABI_MAJOR,
    ABI_MINOR,
    ABI_SCHEMA,
    VALID_ID,
    AssetRecord,
    scan_content,
    sha256_file,
)

PACK_SCHEMA = "signalcloud.data-pack"
PACK_MAJOR = 1
PACK_MINOR = 0
ALLOWED_PACK_ROOTS = {"user", "mods", "starter"}
FORBIDDEN_SUFFIXES = {
    ".py", ".pyc", ".pyo", ".sh", ".bash", ".zsh", ".fish", ".exe", ".dll",
    ".so", ".dylib", ".bin", ".appimage", ".desktop", ".bat", ".cmd", ".ps1",
}
VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){0,3}(?:[-+][a-z0-9._-]+)?$")


@dataclass(frozen=True, slots=True)
class PackBuildResult:
    output_path: Path
    pack_id: str
    version: str
    asset_count: int
    file_count: int
    sha256: str


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


def _envelope_text(record: AssetRecord, *, license_id: str, pack_id: str) -> str:
    lines = [
        "@udata 1", "", "[asset]",
        f"asset_id: {json.dumps(record.asset_id)};",
        f"asset_type: {json.dumps(record.asset_type)};",
        f"family: {json.dumps(record.family)};",
        f"pack: {json.dumps(pack_id)};",
        f"license_id: {json.dumps(record.license_id or license_id)};",
        f"dependencies: {json.dumps(record.dependencies)};",
        f"hot_reload: {json.dumps(record.hot_reload)};",
        f"source_sha256: {json.dumps(record.sha256)};",
        "data_only: true;",
        'unknown_fields_policy: "preserve";',
        "",
    ]
    return "\n".join(lines)


def _safe_source(content_root: Path, source: str | Path) -> tuple[Path, PurePosixPath]:
    root = content_root.resolve()
    raw = Path(source)
    resolved = raw.resolve() if raw.is_absolute() else (root.parent / raw).resolve()
    try:
        relative_content = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("pack source must remain inside the content directory") from exc
    if not relative_content.parts or relative_content.parts[0] not in ALLOWED_PACK_ROOTS:
        raise ValueError("pack source must begin with content/user, content/mods, or content/starter")
    if resolved.is_symlink() or not resolved.is_dir():
        raise ValueError("pack source must be a real directory")
    return resolved, PurePosixPath(relative_content.as_posix())


def _validate_metadata(pack_id: str, version: str, license_id: str) -> None:
    if not VALID_ID.match(pack_id):
        raise ValueError("pack_id must be lowercase and use letters, numbers, '.', '_' or '-'")
    if not VERSION_RE.match(version):
        raise ValueError("version must be a dotted numeric version with an optional safe suffix")
    if not license_id.strip():
        raise ValueError("data packs must declare a license_id")


def build_pack(
    project_root: Path,
    source: str | Path,
    *,
    pack_id: str,
    display_name: str,
    version: str,
    license_id: str,
    output_dir: str | Path = "exports/packs",
) -> PackBuildResult:
    project = Path(project_root).resolve()
    content_root = project / "content"
    _validate_metadata(pack_id, version, license_id)
    source_root, source_relative = _safe_source(content_root, source)
    report = scan_content(content_root)
    issues_by_path: dict[str, list[str]] = {}
    for issue in report.issues:
        issues_by_path.setdefault(issue.relative_path, []).append(f"{issue.severity}:{issue.code}")

    records: list[AssetRecord] = []
    prefix = source_relative.as_posix().rstrip("/") + "/"
    for record in report.records:
        if record.relative_path == source_relative.as_posix() or record.relative_path.startswith(prefix):
            records.append(record)
    if not records:
        raise ValueError("pack source contains no recognized assets")

    archive_files: dict[str, bytes] = {}
    manifest_records: list[dict[str, object]] = []
    for record in sorted(records, key=lambda item: item.relative_path):
        if record.status != "valid":
            raise ValueError(f"invalid asset cannot be packed: {record.relative_path}")
        path = content_root / record.relative_path
        if path.is_symlink():
            raise ValueError(f"symlinks are not permitted in packs: {record.relative_path}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or os.access(path, os.X_OK):
            raise ValueError(f"executable content is not permitted in data packs: {record.relative_path}")
        if record.asset_type == "unsupported":
            raise ValueError(f"unsupported content cannot be packed: {record.relative_path}")
        problem_codes = issues_by_path.get(record.relative_path, [])
        if any(code.startswith("error:") or code == "warning:asset.absolute-path" for code in problem_codes):
            raise ValueError(f"asset requires repair before packing: {record.relative_path}")
        archive_relative = PurePosixPath("content") / PurePosixPath(record.relative_path)
        archive_files[archive_relative.as_posix()] = path.read_bytes()

        envelope_name = archive_relative.as_posix() + ".asset.udata"
        envelope_bytes = _envelope_text(record, license_id=license_id, pack_id=pack_id).encode("utf-8")
        archive_files[envelope_name] = envelope_bytes
        manifest_records.append({
            "asset_id": record.asset_id,
            "asset_type": record.asset_type,
            "family": record.family,
            "relative_path": archive_relative.as_posix(),
            "sha256": record.sha256,
            "envelope_path": envelope_name,
            "dependencies": list(record.dependencies),
            "hot_reload": record.hot_reload,
        })

    pack_manifest = {
        "schema_name": PACK_SCHEMA,
        "schema_major": PACK_MAJOR,
        "schema_minor": PACK_MINOR,
        "content_abi": {"schema_name": ABI_SCHEMA, "schema_major": ABI_MAJOR, "schema_minor": ABI_MINOR},
        "pack_id": pack_id,
        "display_name": display_name.strip() or pack_id,
        "version": version,
        "license_id": license_id,
        "data_only": True,
        "source_root": f"content/{source_relative.as_posix()}",
        "asset_count": len(manifest_records),
        "assets": manifest_records,
        "unknown_fields_policy": "preserve",
    }
    archive_files["PACK_MANIFEST.json"] = (json.dumps(pack_manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    checksums = [f"{hashlib.sha256(data).hexdigest()}  {name}" for name, data in sorted(archive_files.items())]
    archive_files["PACK_SHA256SUMS.txt"] = ("\n".join(checksums) + "\n").encode("utf-8")

    destination_root = Path(output_dir)
    if not destination_root.is_absolute():
        destination_root = (project / destination_root).resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    destination = destination_root / f"{pack_id}-{version}.scpack.zip"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w") as archive:
        for name, data in sorted(archive_files.items()):
            archive.writestr(_zip_info(name), data)
    os.replace(temporary, destination)
    digest = sha256_file(destination)
    destination.with_suffix(destination.suffix + ".sha256").write_text(
        f"{digest}  {destination.name}\n", encoding="utf-8"
    )
    return PackBuildResult(destination, pack_id, version, len(manifest_records), len(archive_files), digest)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a validated data-only SignalCloud content pack")
    parser.add_argument("project_root", nargs="?", default=".")
    parser.add_argument("--source", required=True, help="content/user, content/mods, or content/starter subdirectory")
    parser.add_argument("--pack-id", required=True)
    parser.add_argument("--display-name", default="")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--license-id", required=True)
    parser.add_argument("--output-dir", default="exports/packs")
    args = parser.parse_args()
    result = build_pack(
        Path(args.project_root), args.source,
        pack_id=args.pack_id,
        display_name=args.display_name,
        version=args.version,
        license_id=args.license_id,
        output_dir=args.output_dir,
    )
    print(f"Pack Builder: {result.asset_count} assets | {result.file_count} files | {result.output_path}")
    print(f"SHA-256: {result.sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
