#!/usr/bin/env python3
"""Inspection and atomic installation for SignalCloud data-only packs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .content_abi import (
    AssetDoctorReport,
    parse_udata,
    scan_content,
    sha256_file,
    write_hot_reload_index,
    write_manifest_v2,
    write_report,
)
from .manifest_builder import build_manifest
from .pack_builder import (
    FORBIDDEN_SUFFIXES,
    PACK_MAJOR,
    PACK_SCHEMA,
    VALID_ID,
    VERSION_RE,
)

MAX_ARCHIVE_FILES = 20_000
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ENTRY_BYTES = 128 * 1024 * 1024
INSTALL_SCHEMA = "signalcloud.pack-install-receipt"
SAFE_SOURCE_ROOTS = {"user", "mods", "starter"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class PackFinding:
    severity: str
    code: str
    message: str
    path: str = ""


@dataclass(slots=True)
class PackInspectionResult:
    archive_path: Path
    archive_sha256: str = ""
    pack_id: str = ""
    display_name: str = ""
    version: str = ""
    license_id: str = ""
    asset_count: int = 0
    file_count: int = 0
    total_uncompressed_bytes: int = 0
    manifest: dict[str, Any] = field(default_factory=dict)
    findings: list[PackFinding] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(item.severity == "error" for item in self.findings)

    @property
    def warning_count(self) -> int:
        return sum(item.severity == "warning" for item in self.findings)

    @property
    def installable(self) -> bool:
        return self.error_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_name": "signalcloud.pack-inspection",
            "schema_major": 1,
            "archive_path": str(self.archive_path),
            "archive_sha256": self.archive_sha256,
            "pack_id": self.pack_id,
            "display_name": self.display_name,
            "version": self.version,
            "license_id": self.license_id,
            "asset_count": self.asset_count,
            "file_count": self.file_count,
            "total_uncompressed_bytes": self.total_uncompressed_bytes,
            "installable": self.installable,
            "findings": [asdict(item) for item in self.findings],
            "manifest": self.manifest,
        }


@dataclass(frozen=True, slots=True)
class PackInstallResult:
    pack_id: str
    version: str
    target_path: Path
    receipt_path: Path
    installed_files: int
    installed_assets: int
    transaction_id: str
    archive_sha256: str


def _finding(result: PackInspectionResult, severity: str, code: str, message: str, path: str = "") -> None:
    result.findings.append(PackFinding(severity, code, message, path))


def _safe_archive_name(name: str) -> PurePosixPath | None:
    if not name or "\\" in name or name.startswith("/"):
        return None
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _is_zip_executable(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return bool(mode & 0o111)


def _parse_checksum_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), 1):
        cleaned = line.strip()
        if not cleaned:
            continue
        parts = cleaned.split(None, 1)
        if len(parts) != 2 or not HEX64.match(parts[0]):
            raise ValueError(f"invalid checksum line {number}")
        name = parts[1].strip()
        if name.startswith("*"):
            name = name[1:]
        if _safe_archive_name(name) is None:
            raise ValueError(f"unsafe checksum path on line {number}")
        if name in values:
            raise ValueError(f"duplicate checksum path {name}")
        values[name] = parts[0]
    return values


def _parse_envelope_bytes(data: bytes) -> dict[str, Any]:
    # Pack envelopes are small UDATA documents. Parse the accepted scalar/list
    # subset in-memory so inspection never extracts or executes archive data.
    section = ""
    output: dict[str, Any] = {}
    for raw_line in data.decode("utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "//", "@udata")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if section != "asset" or not line.endswith(";") or ":" not in line:
            continue
        key, raw = line[:-1].split(":", 1)
        try:
            output[key.strip()] = json.loads(raw.strip())
        except json.JSONDecodeError:
            output[key.strip()] = raw.strip()
    return output


def inspect_pack(project_root: Path, archive_path: str | Path) -> PackInspectionResult:
    project = Path(project_root).resolve()
    raw_archive = Path(archive_path)
    archive = raw_archive.resolve() if raw_archive.is_absolute() else (project / raw_archive).resolve()
    result = PackInspectionResult(archive_path=archive)
    if not archive.is_file():
        _finding(result, "error", "pack.missing", "pack archive does not exist")
        return result
    if archive.suffix.lower() != ".zip" or not archive.name.endswith(".scpack.zip"):
        _finding(result, "error", "pack.extension", "pack must use the .scpack.zip extension")
        return result
    result.archive_sha256 = sha256_file(archive)

    try:
        with zipfile.ZipFile(archive, "r") as bundle:
            infos = bundle.infolist()
            result.file_count = len(infos)
            if len(infos) > MAX_ARCHIVE_FILES:
                _finding(result, "error", "pack.too-many-files", f"pack exceeds {MAX_ARCHIVE_FILES} entries")
            names: set[str] = set()
            safe_infos: dict[str, zipfile.ZipInfo] = {}
            total = 0
            for info in infos:
                path = _safe_archive_name(info.filename)
                if path is None:
                    _finding(result, "error", "pack.unsafe-path", "archive entry has an unsafe path", info.filename)
                    continue
                name = path.as_posix()
                if name in names:
                    _finding(result, "error", "pack.duplicate-path", "archive contains a duplicate path", name)
                    continue
                names.add(name)
                if info.flag_bits & 0x1:
                    _finding(result, "error", "pack.encrypted", "encrypted pack entries are not supported", name)
                if _is_zip_symlink(info):
                    _finding(result, "error", "pack.symlink", "symlinks are not permitted in data packs", name)
                if not info.is_dir() and (_is_zip_executable(info) or path.suffix.lower() in FORBIDDEN_SUFFIXES):
                    _finding(result, "error", "pack.executable", "executable or script content is not permitted", name)
                if info.file_size > MAX_ENTRY_BYTES:
                    _finding(result, "error", "pack.entry-too-large", f"entry exceeds {MAX_ENTRY_BYTES} bytes", name)
                total += info.file_size
                safe_infos[name] = info
            result.total_uncompressed_bytes = total
            if total > MAX_ARCHIVE_BYTES:
                _finding(result, "error", "pack.too-large", f"pack exceeds {MAX_ARCHIVE_BYTES} uncompressed bytes")

            required = {"PACK_MANIFEST.json", "PACK_SHA256SUMS.txt"}
            for name in sorted(required - names):
                _finding(result, "error", "pack.required-file", "required pack file is missing", name)
            if result.error_count:
                return result

            try:
                manifest = json.loads(bundle.read("PACK_MANIFEST.json"))
            except (KeyError, UnicodeError, json.JSONDecodeError) as exc:
                _finding(result, "error", "pack.manifest-invalid", str(exc), "PACK_MANIFEST.json")
                return result
            if not isinstance(manifest, dict):
                _finding(result, "error", "pack.manifest-invalid", "manifest must be a JSON object", "PACK_MANIFEST.json")
                return result
            result.manifest = manifest
            result.pack_id = str(manifest.get("pack_id", ""))
            result.display_name = str(manifest.get("display_name", result.pack_id))
            result.version = str(manifest.get("version", ""))
            result.license_id = str(manifest.get("license_id", ""))
            try:
                schema_major = int(manifest.get("schema_major", -1))
            except (TypeError, ValueError):
                schema_major = -1
            if manifest.get("schema_name") != PACK_SCHEMA or schema_major != PACK_MAJOR:
                _finding(result, "error", "pack.schema", "unsupported SignalCloud pack schema", "PACK_MANIFEST.json")
            if manifest.get("data_only") is not True:
                _finding(result, "error", "pack.data-only", "pack must explicitly declare data_only=true", "PACK_MANIFEST.json")
            if not VALID_ID.match(result.pack_id):
                _finding(result, "error", "pack.id", "pack_id is missing or invalid", "PACK_MANIFEST.json")
            if not VERSION_RE.match(result.version):
                _finding(result, "error", "pack.version", "pack version is missing or invalid", "PACK_MANIFEST.json")
            if not result.license_id.strip():
                _finding(result, "error", "pack.license", "pack license_id is required", "PACK_MANIFEST.json")

            try:
                checksums = _parse_checksum_text(bundle.read("PACK_SHA256SUMS.txt").decode("utf-8"))
            except (KeyError, UnicodeError, ValueError) as exc:
                _finding(result, "error", "pack.checksums-invalid", str(exc), "PACK_SHA256SUMS.txt")
                return result
            expected_checksum_names = names - {"PACK_SHA256SUMS.txt"}
            if set(checksums) != expected_checksum_names:
                missing = sorted(expected_checksum_names - set(checksums))
                extra = sorted(set(checksums) - expected_checksum_names)
                if missing:
                    _finding(result, "error", "pack.checksum-missing", f"checksum entries missing: {', '.join(missing[:8])}")
                if extra:
                    _finding(result, "error", "pack.checksum-extra", f"checksum entries reference absent files: {', '.join(extra[:8])}")
            for name, expected in checksums.items():
                observed = hashlib.sha256(bundle.read(name)).hexdigest()
                if observed != expected:
                    _finding(result, "error", "pack.checksum-mismatch", "entry SHA-256 does not match", name)

            raw_assets = manifest.get("assets", [])
            if not isinstance(raw_assets, list):
                _finding(result, "error", "pack.assets", "manifest assets must be a list", "PACK_MANIFEST.json")
                return result
            result.asset_count = len(raw_assets)
            try:
                declared_count = int(manifest.get("asset_count", -1))
            except (TypeError, ValueError):
                declared_count = -1
            if declared_count != result.asset_count:
                _finding(result, "error", "pack.asset-count", "asset_count does not match the manifest list", "PACK_MANIFEST.json")

            installed_report = scan_content(project / "content") if (project / "content").is_dir() else AssetDoctorReport()
            installed_ids = {record.asset_id for record in installed_report.records if record.status == "valid"}
            pack_ids: set[str] = set()
            dependency_rows: list[tuple[str, list[str], str]] = []
            referenced_files = {"PACK_MANIFEST.json", "PACK_SHA256SUMS.txt"}
            for index, raw in enumerate(raw_assets):
                location = f"PACK_MANIFEST.json#assets[{index}]"
                if not isinstance(raw, dict):
                    _finding(result, "error", "pack.asset-record", "asset record must be an object", location)
                    continue
                asset_id = str(raw.get("asset_id", ""))
                path_text = str(raw.get("relative_path", ""))
                envelope_text = str(raw.get("envelope_path", ""))
                asset_hash = str(raw.get("sha256", ""))
                dependencies = raw.get("dependencies", [])
                if not VALID_ID.match(asset_id):
                    _finding(result, "error", "pack.asset-id", "asset_id is missing or invalid", location)
                elif asset_id in pack_ids:
                    _finding(result, "error", "pack.duplicate-asset-id", "duplicate asset_id inside pack", asset_id)
                else:
                    pack_ids.add(asset_id)
                    if asset_id in installed_ids:
                        _finding(result, "error", "pack.asset-id-installed", "asset_id already exists in installed content", asset_id)
                asset_path = _safe_archive_name(path_text)
                envelope_path = _safe_archive_name(envelope_text)
                if asset_path is None or len(asset_path.parts) < 3 or asset_path.parts[0] != "content" or asset_path.parts[1] not in SAFE_SOURCE_ROOTS:
                    _finding(result, "error", "pack.asset-path", "asset path must begin with content/user, content/mods, or content/starter", path_text)
                    continue
                if envelope_path is None or envelope_text != path_text + ".asset.udata":
                    _finding(result, "error", "pack.envelope-path", "asset envelope path is invalid", envelope_text)
                    continue
                referenced_files.update({path_text, envelope_text})
                if path_text not in names or envelope_text not in names:
                    _finding(result, "error", "pack.asset-file-missing", "asset payload or envelope is missing", path_text)
                    continue
                if not HEX64.match(asset_hash) or hashlib.sha256(bundle.read(path_text)).hexdigest() != asset_hash:
                    _finding(result, "error", "pack.asset-hash", "asset manifest SHA-256 does not match payload", path_text)
                try:
                    envelope = _parse_envelope_bytes(bundle.read(envelope_text))
                except (UnicodeError, ValueError) as exc:
                    _finding(result, "error", "pack.envelope-invalid", str(exc), envelope_text)
                    envelope = {}
                if str(envelope.get("asset_id", "")) != asset_id:
                    _finding(result, "error", "pack.envelope-id", "envelope asset_id does not match manifest", envelope_text)
                resolved_license = str(envelope.get("license_id", "") or result.license_id)
                if not resolved_license:
                    _finding(result, "error", "pack.asset-license", "asset license could not be resolved", envelope_text)
                if envelope.get("data_only") is not True:
                    _finding(result, "error", "pack.envelope-data-only", "asset envelope must declare data_only=true", envelope_text)
                if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
                    _finding(result, "error", "pack.dependencies", "dependencies must be a list of asset IDs", location)
                    dependencies = []
                dependency_rows.append((asset_id, list(dependencies), path_text))

            unreferenced_content = sorted(
                name for name in names
                if name.startswith("content/") and name not in referenced_files and not name.endswith("/")
            )
            for name in unreferenced_content[:32]:
                _finding(result, "error", "pack.unmanifested-content", "content file is not declared by the pack manifest", name)
            for asset_id, dependencies, path_text in dependency_rows:
                for dependency in dependencies:
                    if dependency not in pack_ids and dependency not in installed_ids:
                        _finding(result, "error", "pack.missing-dependency", f"missing dependency {dependency}", path_text)
            if not raw_assets:
                _finding(result, "error", "pack.empty", "pack contains no assets")
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        _finding(result, "error", "pack.open", str(exc))
    return result


def _safe_install_relative(path_text: str) -> PurePosixPath:
    path = _safe_archive_name(path_text)
    if path is None or len(path.parts) < 3 or path.parts[0] != "content" or path.parts[1] not in SAFE_SOURCE_ROOTS:
        raise ValueError(f"unsafe install path {path_text}")
    tail = PurePosixPath(*path.parts[2:])
    if not tail.parts:
        raise ValueError(f"empty install path {path_text}")
    return tail


def _write_receipt(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def install_pack(project_root: Path, archive_path: str | Path) -> PackInstallResult:
    project = Path(project_root).resolve()
    result = inspect_pack(project, archive_path)
    if not result.installable:
        first = next((item for item in result.findings if item.severity == "error"), None)
        raise ValueError(first.message if first else "pack inspection failed")
    tx_seed = f"{result.archive_sha256}:{result.pack_id}:{result.version}"
    transaction_id = hashlib.sha256(tx_seed.encode("utf-8")).hexdigest()[:16]
    target = project / "content" / "mods" / result.pack_id / result.version
    if target.exists():
        raise FileExistsError(f"pack target already exists: {target.relative_to(project)}")
    staging_root = project / "user_data" / "studio" / "pack_install_staging" / transaction_id
    staging_content = staging_root / "content"
    shutil.rmtree(staging_root, ignore_errors=True)
    staging_content.mkdir(parents=True, exist_ok=True)
    installed_paths: list[str] = []
    try:
        with zipfile.ZipFile(result.archive_path, "r") as bundle:
            for raw in result.manifest.get("assets", []):
                for key in ("relative_path", "envelope_path"):
                    source_name = str(raw[key])
                    relative = _safe_install_relative(source_name)
                    destination = staging_content / relative.as_posix()
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    temporary = destination.with_suffix(destination.suffix + ".tmp")
                    temporary.write_bytes(bundle.read(source_name))
                    os.replace(temporary, destination)
                    installed_paths.append(relative.as_posix())
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging_content, target)
        report = scan_content(project / "content")
        target_prefix = target.relative_to(project / "content").as_posix() + "/"
        target_errors = [
            issue for issue in report.issues
            if issue.severity == "error" and issue.relative_path.startswith(target_prefix)
        ]
        if target_errors:
            raise ValueError(f"installed pack failed Content ABI validation: {target_errors[0].message}")
        build_manifest(project / "content")
        write_manifest_v2(report, project / "content" / "manifest_v2.json")
        write_report(report, project / "reports" / "asset_doctor" / "latest.json")
        write_hot_reload_index(report, project, project / "user_data" / "studio" / "hot_reload_candidates.udata")
        receipt = project / "user_data" / "studio" / "installed_packs" / f"{result.pack_id}-{result.version}.json"
        _write_receipt(receipt, {
            "schema_name": INSTALL_SCHEMA,
            "schema_major": 1,
            "transaction_id": transaction_id,
            "pack_id": result.pack_id,
            "version": result.version,
            "license_id": result.license_id,
            "archive_path": str(result.archive_path),
            "archive_sha256": result.archive_sha256,
            "target_relative_path": target.relative_to(project).as_posix(),
            "installed_unix": int(time.time()),
            "installed_files": sorted(installed_paths),
            "asset_ids": [str(item.get("asset_id", "")) for item in result.manifest.get("assets", [])],
            "status": "installed",
        })
        return PackInstallResult(
            result.pack_id,
            result.version,
            target,
            receipt,
            len(installed_paths),
            result.asset_count,
            transaction_id,
            result.archive_sha256,
        )
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            try:
                report = scan_content(project / "content")
                build_manifest(project / "content")
                write_manifest_v2(report, project / "content" / "manifest_v2.json")
                write_hot_reload_index(report, project, project / "user_data" / "studio" / "hot_reload_candidates.udata")
            except Exception:
                pass
        raise
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect or atomically install a SignalCloud .scpack.zip")
    parser.add_argument("project_root", nargs="?", default=".")
    parser.add_argument("archive")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.install:
        installed = install_pack(Path(args.project_root), args.archive)
        print(
            f"Pack installed: {installed.pack_id} {installed.version} | "
            f"{installed.installed_assets} assets | {installed.target_path}"
        )
        print(f"Receipt: {installed.receipt_path}")
        return 0
    inspected = inspect_pack(Path(args.project_root), args.archive)
    if args.json:
        print(json.dumps(inspected.to_dict(), indent=2, sort_keys=True))
    else:
        print(
            f"Pack inspection: {inspected.pack_id or '<unknown>'} {inspected.version or ''} | "
            f"{inspected.asset_count} assets | {inspected.error_count} errors | "
            f"{inspected.warning_count} warnings"
        )
        for finding in inspected.findings:
            print(f"{finding.severity.upper()}: {finding.code}: {finding.path}: {finding.message}")
    return 0 if inspected.installable else 1


if __name__ == "__main__":
    raise SystemExit(main())
