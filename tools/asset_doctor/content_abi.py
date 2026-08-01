#!/usr/bin/env python3
"""SignalCloud Alpha A3 content ABI and validation foundation.

The public manifest remains the nine-column CSV consumed by the current C++
engine.  This module adds a richer, forward-compatible JSON index and explicit
validation/quarantine policy without executing asset content.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from tools.signalcloud_fonts.validator import validate_scfont

ABI_SCHEMA = "signalcloud.content-abi"
ABI_MAJOR = 1
ABI_MINOR = 0

SUPPORTED_EXTENSIONS: dict[str, tuple[str, str]] = {
    ".udata": ("udata", "data"),
    ".scui": ("scui", "ui"),
    ".slight": ("light_set", "lighting"),
    ".sclight": ("light_set", "lighting"),
    ".pcp3": ("pcp3_project", "point_cloud"),
    ".pcp3cloud": ("pcp3_cloud", "point_cloud"),
    ".3dbrush": ("pcp3_brush", "point_cloud"),
    ".json": ("json_sidecar", "metadata"),
    ".jmap": ("jitter_map", "materials"),
    ".texgraph": ("texture_graph", "materials"),
    ".scaudio": ("audio_interference_profile", "audio"),
    ".scfont": ("signalcloud_font", "font"),
    ".playbook": ("playbook", "behavior"),
    ".scanim": ("animation", "animation"),
    ".scphysics": ("physics_profile", "physics"),
    ".tupd": ("tupd_recipe", "items"),
    ".tupdinstance": ("tupd_instance", "items"),
}
IGNORED_NAMES = {"manifest.csv", "manifest_cache.json", "manifest_v2.json", "VALIDATION_REPORT.md"}
TEXT_LIMIT = 8 * 1024 * 1024
QUOTED_POSIX_ABSOLUTE = re.compile(r'(?P<quote>["\'])(?P<path>/(?:home|Users)/.*?)(?P=quote)')
QUOTED_WINDOWS_ABSOLUTE = re.compile(r'(?P<quote>["\'])(?P<path>[A-Za-z]:\\.*?)(?P=quote)')
UNQUOTED_ABSOLUTE = re.compile(r"(?:/(?:home|Users)/|[A-Za-z]:\\Users\\)")
VALID_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,95}$")
PCP3_CLOUD_HEADER = struct.Struct("<8sIIQ32sQ")


def pcp3_payload_sha256(path: Path) -> str:
    """Return and validate the embedded PCP3 point-payload digest."""
    data = path.read_bytes()
    if len(data) < PCP3_CLOUD_HEADER.size:
        raise ValueError("PCP3 cloud is smaller than its header")
    magic, version, record_size, count, expected_digest, _flags = PCP3_CLOUD_HEADER.unpack_from(data, 0)
    if magic != b"PCP3CLD1" or version != 1 or record_size != 64:
        raise ValueError("PCP3 cloud header is unsupported")
    payload = data[PCP3_CLOUD_HEADER.size:]
    if len(payload) != int(count) * int(record_size):
        raise ValueError("PCP3 cloud payload size does not match its header")
    observed = hashlib.sha256(payload).digest()
    if observed != expected_digest:
        raise ValueError("PCP3 cloud embedded payload checksum failed")
    return observed.hex()


@dataclass(slots=True)
class AssetIssue:
    severity: str
    code: str
    message: str
    relative_path: str = ""


@dataclass(slots=True)
class AssetRecord:
    asset_id: str
    asset_type: str
    family: str
    pack: str
    relative_path: str
    size_bytes: int
    sha256: str
    enabled: bool
    status: str
    schema_name: str = ABI_SCHEMA
    schema_major: int = ABI_MAJOR
    schema_minor: int = ABI_MINOR
    license_id: str = ""
    dependencies: list[str] = field(default_factory=list)
    hot_reload: str = "disabled"
    envelope_path: str = ""
    inferred: bool = True


@dataclass(slots=True)
class AssetDoctorReport:
    schema_name: str = "signalcloud.asset-doctor-report"
    schema_major: int = 1
    schema_minor: int = 0
    generated_unix: int = 0
    records: list[AssetRecord] = field(default_factory=list)
    issues: list[AssetIssue] = field(default_factory=list)
    quarantined: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(issue.severity == "error" for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.severity == "warning" for issue in self.issues)

    @property
    def valid_count(self) -> int:
        return sum(record.status == "valid" for record in self.records)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_name": self.schema_name,
            "schema_major": self.schema_major,
            "schema_minor": self.schema_minor,
            "generated_unix": self.generated_unix,
            "summary": {
                "records": len(self.records),
                "valid": self.valid_count,
                "errors": self.error_count,
                "warnings": self.warning_count,
                "quarantined": len(self.quarantined),
            },
            "records": [asdict(record) for record in self.records],
            "issues": [asdict(issue) for issue in self.issues],
            "quarantined": list(self.quarantined),
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def parse_udata(path: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    sections: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    section = ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return {}, [f"cannot read UDATA: {exc}"]
    for number, line in enumerate(lines, 1):
        cleaned = line.strip()
        if not cleaned or cleaned.startswith(("#", "//", "@udata")):
            continue
        if cleaned.startswith("[") and cleaned.endswith("]"):
            section = cleaned[1:-1].strip()
            sections.setdefault(section, {})
            continue
        if section and "=" in cleaned and not cleaned.endswith(";"):
            key, raw = cleaned.split("=", 1)
            value_text = raw.strip()
            value = _json_value(value_text)
            sections.setdefault(section, {})[key.strip()] = value if value is not None else value_text
            continue
        if not section or not cleaned.endswith(";") or ":" not in cleaned:
            # Legacy title/preamble lines are descriptive rather than invalid data.
            continue
        key, raw = cleaned[:-1].split(":", 1)
        value = _json_value(raw.strip())
        if value is None and raw.strip() != "null":
            warnings.append(f"line {number} has an invalid JSON value")
            continue
        sections.setdefault(section, {})[key.strip()] = value
    return sections, warnings


def envelope_candidates(path: Path) -> tuple[Path, ...]:
    return (
        path.with_suffix(path.suffix + ".asset.udata"),
        path.with_name(path.stem + ".asset.udata"),
    )


def _infer_pack(relative: Path) -> str:
    first = relative.parts[0] if relative.parts else "unknown"
    if first in {"core", "starter", "mods", "user", "quarantine"}:
        return first
    if first.startswith("pcp3_"):
        return "legacy"
    return first or "legacy"


def _infer_id(relative: Path) -> str:
    parts = [part.lower().replace(" ", "-") for part in relative.parts[-4:]]
    joined = ".".join(parts)
    safe = re.sub(r"[^a-z0-9._-]+", "-", joined).strip("-.")
    return safe[:96] or "unnamed-asset"


def _classify(path: Path) -> tuple[str, str]:
    return SUPPORTED_EXTENSIONS.get(path.suffix.lower(), ("unsupported", "unknown"))


def _load_envelope(content_root: Path, path: Path) -> tuple[dict[str, Any], str, list[str]]:
    for candidate in envelope_candidates(path):
        if candidate.exists() and candidate != path:
            sections, warnings = parse_udata(candidate)
            return sections.get("asset", {}), candidate.relative_to(content_root).as_posix(), warnings
    return {}, "", []


def _validate_payload(path: Path, relative: Path, issues: list[AssetIssue]) -> None:
    suffix = path.suffix.lower()
    json_payload: Any = None
    if path.stat().st_size > TEXT_LIMIT and suffix in {".json", ".slight", ".sclight", ".scui", ".udata", ".scaudio", ".scfont", ".tupdinstance"}:
        issues.append(AssetIssue("error", "asset.too-large", "text asset exceeds the 8 MiB authoring limit", relative.as_posix()))
        return
    if suffix == ".scfont":
        try:
            validate_scfont(path)
        except ValueError as exc:
            issues.append(AssetIssue("error", "asset.invalid-scfont", str(exc), relative.as_posix()))
            return
    elif suffix in {".json", ".slight", ".sclight", ".pcp3", ".3dbrush", ".jmap", ".texgraph", ".scaudio", ".playbook", ".scanim", ".scphysics", ".tupd", ".tupdinstance"}:
        try:
            json_payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(json_payload, (dict, list)):
                raise ValueError("top-level JSON must be an object or array")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            issues.append(AssetIssue("error", "asset.invalid-json", str(exc), relative.as_posix()))
            return
    elif suffix in {".udata", ".scui"}:
        sections, warnings = parse_udata(path)
        if not sections:
            issues.append(AssetIssue("error", "asset.invalid-udata", "no valid UDATA sections were found", relative.as_posix()))
        for warning in warnings[:8]:
            issues.append(AssetIssue("warning", "asset.udata-warning", warning, relative.as_posix()))

    # A PCP3 project is not a usable runtime asset without its sealed binary
    # point cloud. Validate the companion path and declared cloud hash here so
    # incomplete editor placeholders cannot silently pass Asset Doctor and then
    # warn every time the native game starts.
    if suffix == ".tupd" and isinstance(json_payload, dict):
        if json_payload.get("schema") != "signalcloud.tupd-recipe":
            issues.append(AssetIssue(
                "error", "tupd.invalid-schema",
                "Tupd recipe schema must be signalcloud.tupd-recipe",
                relative.as_posix(),
            ))
        recipe_id = json_payload.get("recipe_id")
        if not isinstance(recipe_id, str) or not recipe_id.strip():
            issues.append(AssetIssue(
                "error", "tupd.recipe-id",
                "Tupd recipe_id must be a non-empty string",
                relative.as_posix(),
            ))
        allowed_modes = {"modification", "forced_modification", "upgrade", "repair_small", "repair_full", "assembly"}
        if json_payload.get("mode") not in allowed_modes:
            issues.append(AssetIssue(
                "error", "tupd.mode",
                "Tupd mode is not recognized",
                relative.as_posix(),
            ))
        for field in ("inputs", "consumed_inputs", "required_interfaces", "connections", "forced_connections", "validation_rules"):
            values = json_payload.get(field, [])
            if not isinstance(values, list) or len(values) > 64 or any(not isinstance(value, str) for value in values):
                issues.append(AssetIssue(
                    "error", "tupd.array-bounds",
                    f"Tupd {field} must be a string array with at most 64 entries",
                    relative.as_posix(),
                ))
        point_budget = json_payload.get("point_budget", 0)
        if not isinstance(point_budget, (int, float)) or isinstance(point_budget, bool) or not (1 <= point_budget <= 50000):
            issues.append(AssetIssue(
                "error", "tupd.point-budget",
                "Tupd point_budget must be between 1 and 50000",
                relative.as_posix(),
            ))
        blocked_fields = {"script", "command", "executable", "shell", "python", "lua"}
        if any(field in json_payload for field in blocked_fields):
            issues.append(AssetIssue(
                "error", "tupd.executable-field",
                "Tupd recipes are data-only and may not declare executable fields",
                relative.as_posix(),
            ))

    if suffix == ".tupdinstance" and isinstance(json_payload, dict):
        if json_payload.get("schema") != "signalcloud.tupd-instance":
            issues.append(AssetIssue(
                "error", "tupd-instance.invalid-schema",
                "Tupd result instance schema must be signalcloud.tupd-instance",
                relative.as_posix(),
            ))
        for field in ("instance_id", "recipe_id", "result_id"):
            value = json_payload.get(field)
            if not isinstance(value, str) or not value.strip():
                issues.append(AssetIssue(
                    "error", "tupd-instance.required-id",
                    f"Tupd result instance {field} must be a non-empty string",
                    relative.as_posix(),
                ))
        for field in (
            "interfaces", "sockets", "tags", "applied_parts", "connections",
            "forced_connections", "test_actions",
        ):
            values = json_payload.get(field, [])
            if not isinstance(values, list) or len(values) > 64 or any(not isinstance(value, str) for value in values):
                issues.append(AssetIssue(
                    "error", "tupd-instance.array-bounds",
                    f"Tupd result instance {field} must be a string array with at most 64 entries",
                    relative.as_posix(),
                ))
        point_budget = json_payload.get("point_budget", 0)
        if not isinstance(point_budget, (int, float)) or isinstance(point_budget, bool) or not (1 <= point_budget <= 50000):
            issues.append(AssetIssue(
                "error", "tupd-instance.point-budget",
                "Tupd result instance point_budget must be between 1 and 50000",
                relative.as_posix(),
            ))
        blocked_fields = {"script", "command", "executable", "shell", "python", "lua"}
        if any(field in json_payload for field in blocked_fields):
            issues.append(AssetIssue(
                "error", "tupd-instance.executable-field",
                "Tupd result instances are data-only and may not declare executable fields",
                relative.as_posix(),
            ))

    if suffix == ".pcp3" and isinstance(json_payload, dict):
        cloud_name = str(json_payload.get("cloud_file", path.with_suffix(".pcp3cloud").name))
        cloud_relative = Path(cloud_name)
        if cloud_relative.is_absolute() or ".." in cloud_relative.parts:
            issues.append(AssetIssue(
                "error", "pcp3.cloud-path-unsafe",
                "PCP3 cloud_file must be a safe path beside the project",
                relative.as_posix(),
            ))
        else:
            cloud_path = (path.parent / cloud_relative).resolve()
            try:
                cloud_path.relative_to(path.parent.resolve())
            except ValueError:
                issues.append(AssetIssue(
                    "error", "pcp3.cloud-path-unsafe",
                    "PCP3 cloud_file escapes the project asset directory",
                    relative.as_posix(),
                ))
            else:
                if not cloud_path.is_file():
                    issues.append(AssetIssue(
                        "error", "pcp3.cloud-missing",
                        f"required PCP3 cloud companion is missing: {cloud_relative.as_posix()}",
                        relative.as_posix(),
                    ))
                else:
                    declared_hash = str(json_payload.get("cloud_sha256", ""))
                    try:
                        observed_hash = pcp3_payload_sha256(cloud_path)
                    except (OSError, ValueError) as exc:
                        issues.append(AssetIssue(
                            "error", "pcp3.cloud-invalid", str(exc), relative.as_posix()
                        ))
                    else:
                        if declared_hash and declared_hash != observed_hash:
                            issues.append(AssetIssue(
                                "error", "pcp3.cloud-hash",
                                "PCP3 cloud_sha256 does not match the binary companion payload",
                                relative.as_posix(),
                            ))
    if suffix not in {".pcp3cloud"}:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return
        matches = list(QUOTED_POSIX_ABSOLUTE.finditer(text)) + list(QUOTED_WINDOWS_ABSOLUTE.finditer(text))
        if not matches and UNQUOTED_ABSOLUTE.search(text):
            matches = [UNQUOTED_ABSOLUTE.search(text)]  # type: ignore[list-item]
        if matches:
            issues.append(AssetIssue(
                "warning",
                "asset.absolute-path",
                "asset contains a machine-specific absolute path; portable repair is available",
                relative.as_posix(),
            ))


def discover_assets(content_root: Path) -> Iterable[Path]:
    for path in sorted(content_root.rglob("*")):
        if not path.is_file() or path.name in IGNORED_NAMES:
            continue
        relative = path.relative_to(content_root)
        if relative.parts and relative.parts[0] == "quarantine":
            continue
        if path.name.endswith(".asset.udata"):
            continue
        yield path


def scan_content(content_root: Path) -> AssetDoctorReport:
    content_root = Path(content_root).resolve()
    report = AssetDoctorReport(generated_unix=int(time.time()))
    ids: dict[str, str] = {}
    for path in discover_assets(content_root):
        relative = path.relative_to(content_root)
        asset_type, family = _classify(path)
        local_issues: list[AssetIssue] = []
        envelope, envelope_path, envelope_warnings = _load_envelope(content_root, path)
        if asset_type == "unsupported" and not envelope:
            local_issues.append(AssetIssue("warning", "asset.unsupported-extension", f"unsupported extension {path.suffix or '<none>'}", relative.as_posix()))
        _validate_payload(path, relative, local_issues)
        for warning in envelope_warnings:
            local_issues.append(AssetIssue("warning", "asset.envelope-warning", warning, envelope_path))
        payload_sha256 = sha256_file(path)
        declared_source_hash = str(envelope.get("source_sha256") or "")
        if declared_source_hash and declared_source_hash != payload_sha256:
            local_issues.append(AssetIssue(
                "warning", "asset.envelope-stale",
                "asset envelope source_sha256 does not match the current payload; rebuild/export the envelope",
                relative.as_posix(),
            ))
        asset_id = str(envelope.get("asset_id") or _infer_id(relative))
        if not VALID_ID.match(asset_id):
            local_issues.append(AssetIssue("error", "asset.invalid-id", "asset_id must be lowercase and contain only letters, numbers, '.', '_' or '-'", relative.as_posix()))
        previous = ids.get(asset_id)
        if previous:
            local_issues.append(AssetIssue("error", "asset.duplicate-id", f"duplicate asset_id also used by {previous}", relative.as_posix()))
        else:
            ids[asset_id] = relative.as_posix()
        pack = str(envelope.get("pack") or _infer_pack(relative))
        license_id = str(envelope.get("license_id") or "")
        dependencies = envelope.get("dependencies") if isinstance(envelope.get("dependencies"), list) else []
        dependencies = [str(value) for value in dependencies if isinstance(value, str)]
        hot_reload = str(envelope.get("hot_reload") or ("authoring-only" if path.suffix.lower() in {".slight", ".sclight", ".scui", ".pcp3", ".jmap", ".texgraph", ".scaudio", ".scfont"} else "disabled"))
        if pack in {"starter", "mods", "user"} and not license_id:
            local_issues.append(AssetIssue("warning", "asset.license-missing", "redistributable packs should declare license_id", relative.as_posix()))
        status = "invalid" if any(issue.severity == "error" for issue in local_issues) else "valid"
        record = AssetRecord(
            asset_id=asset_id,
            asset_type=str(envelope.get("asset_type") or asset_type),
            family=str(envelope.get("family") or family),
            pack=pack,
            relative_path=relative.as_posix(),
            size_bytes=path.stat().st_size,
            sha256=payload_sha256,
            enabled=status == "valid",
            status=status,
            license_id=license_id,
            dependencies=dependencies,
            hot_reload=hot_reload,
            envelope_path=envelope_path,
            inferred=not bool(envelope),
        )
        report.records.append(record)
        report.issues.extend(local_issues)

    known = {record.asset_id for record in report.records}
    for record in report.records:
        for dependency in record.dependencies:
            if dependency not in known:
                report.issues.append(AssetIssue("error", "asset.missing-dependency", f"missing dependency {dependency}", record.relative_path))
                record.status = "invalid"
                record.enabled = False
    return report


def write_report(report: AssetDoctorReport, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return path


def write_manifest_v2(report: AssetDoctorReport, path: Path) -> Path:
    return write_report(report, path)


def write_hot_reload_index(report: AssetDoctorReport, project_root: Path, path: Path) -> Path:
    root = Path(project_root).resolve()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = [record for record in report.records if record.enabled and record.hot_reload == "authoring-only"]
    lines = [
        "@udata 1", "", "[index]",
        'schema_name: "signalcloud.hot-reload-index";',
        "schema_major: 1;", "schema_minor: 0;",
        'mode: "protected-authoring-only";',
        f"entry_count: {len(entries)};", "",
    ]
    for index, record in enumerate(entries):
        absolute = (root / "content" / record.relative_path).resolve()
        absolute.relative_to(root)
        lines += [
            f"[asset.{index}]",
            f"asset_id: {json.dumps(record.asset_id)};",
            f"relative_path: {json.dumps('content/' + record.relative_path)};",
            f"sha256: {json.dumps(record.sha256)};",
            f"asset_type: {json.dumps(record.asset_type)};",
            'session_scope: "authoring-preview";',
            "",
        ]
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text("\n".join(lines), encoding="utf-8")
    os.replace(temp, path)
    return path


def quarantine_invalid(report: AssetDoctorReport, content_root: Path) -> list[str]:
    content_root = Path(content_root).resolve()
    stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    moved: list[str] = []
    receipt_entries: list[dict[str, str]] = []
    invalid_paths = sorted({issue.relative_path for issue in report.issues if issue.severity == "error" and issue.relative_path})
    for relative_text in invalid_paths:
        source = (content_root / relative_text).resolve()
        try:
            relative = source.relative_to(content_root)
        except ValueError:
            continue
        if not relative.parts or relative.parts[0] not in {"user", "mods"} or not source.is_file():
            continue
        destination = content_root / "quarantine" / stamp / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_hash = sha256_file(source)
        shutil.move(str(source), str(destination))
        moved.append(relative.as_posix())
        receipt_entries.append({
            "original_relative_path": relative.as_posix(),
            "quarantined_relative_path": destination.relative_to(content_root).as_posix(),
            "sha256": source_hash,
        })
        for candidate in envelope_candidates(source):
            if candidate.exists():
                side_relative = candidate.relative_to(content_root)
                side_destination = content_root / "quarantine" / stamp / side_relative
                side_destination.parent.mkdir(parents=True, exist_ok=True)
                side_hash = sha256_file(candidate)
                shutil.move(str(candidate), str(side_destination))
                receipt_entries.append({
                    "original_relative_path": side_relative.as_posix(),
                    "quarantined_relative_path": side_destination.relative_to(content_root).as_posix(),
                    "sha256": side_hash,
                })
    if moved:
        receipt = content_root / "quarantine" / stamp / "QUARANTINE_RECEIPT.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({
            "schema_name": "signalcloud.quarantine-receipt",
            "schema_major": 1,
            "generated_unix": int(time.time()),
            "entries": receipt_entries,
            "moved": moved,
            "restored": False,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report.quarantined.extend(moved)
    return moved


PORTABLE_ROOT_MARKERS = ("/content/", "/user_data/", "/reports/", "/exports/")


def portable_project_reference(value: str) -> str:
    """Convert a machine path into a project-relative, repository-safe reference.

    Known SignalCloud roots are preserved. Unknown external paths are reduced to
    an explicit external reference rather than leaking a home directory.
    """
    normalized = str(value).replace("\\", "/")
    for marker in PORTABLE_ROOT_MARKERS:
        position = normalized.lower().find(marker.lower())
        if position >= 0:
            return normalized[position + 1 :]
    name = Path(normalized).name or "external-resource"
    return f"external://{name}"


def _repair_json_value(value: Any) -> tuple[Any, int]:
    if isinstance(value, dict):
        changed = 0
        output: dict[str, Any] = {}
        for key, item in value.items():
            repaired, count = _repair_json_value(item)
            output[key] = repaired
            changed += count
        return output, changed
    if isinstance(value, list):
        changed = 0
        output_list: list[Any] = []
        for item in value:
            repaired, count = _repair_json_value(item)
            output_list.append(repaired)
            changed += count
        return output_list, changed
    if isinstance(value, str):
        if value.startswith(("/home/", "/Users/")) or re.match(r"^[A-Za-z]:[\\/]", value):
            return portable_project_reference(value), 1
    return value, 0


def _replace_quoted_paths(text: str) -> tuple[str, int]:
    changed = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal changed
        changed += 1
        quote = match.group("quote")
        return f"{quote}{portable_project_reference(match.group('path'))}{quote}"

    text = QUOTED_POSIX_ABSOLUTE.sub(replace, text)
    text = QUOTED_WINDOWS_ABSOLUTE.sub(replace, text)
    return text, changed


def _refresh_existing_envelope_hash(content_root: Path, asset_path: Path) -> None:
    """Refresh only source_sha256 after a validated in-place portability repair."""
    root = Path(content_root).resolve()
    path = Path(asset_path).resolve()
    digest = sha256_file(path)
    for envelope in envelope_candidates(path):
        if envelope == path or not envelope.is_file():
            continue
        try:
            envelope.resolve().relative_to(root)
            original = envelope.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ValueError):
            continue
        updated, count = re.subn(
            r'(?m)^(source_sha256:\s*)[^;]+;',
            lambda match: f"{match.group(1)}{json.dumps(digest)};",
            original,
            count=1,
        )
        if count and updated != original:
            temporary = envelope.with_suffix(envelope.suffix + ".hash.tmp")
            temporary.write_text(updated, encoding="utf-8")
            os.replace(temporary, envelope)


def repair_machine_paths(content_root: Path) -> list[str]:
    """Repair machine-specific paths in text assets without executing content."""
    root = Path(content_root).resolve()
    repaired_paths: list[str] = []
    for path in discover_assets(root):
        if path.suffix.lower() == ".pcp3cloud":
            continue
        relative = path.relative_to(root).as_posix()
        try:
            original = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        updated = original
        count = 0
        if path.suffix.lower() in {".json", ".slight", ".sclight", ".pcp3", ".3dbrush", ".jmap", ".texgraph", ".playbook", ".scanim", ".scphysics", ".tupd", ".tupdinstance"}:
            try:
                payload = json.loads(original)
            except json.JSONDecodeError:
                payload = None
            if payload is not None:
                repaired, count = _repair_json_value(payload)
                if count:
                    updated = json.dumps(repaired, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if count == 0:
            updated, count = _replace_quoted_paths(original)
        if count and updated != original:
            temporary = path.with_suffix(path.suffix + ".portable.tmp")
            temporary.write_text(updated, encoding="utf-8")
            os.replace(temporary, path)
            _refresh_existing_envelope_hash(root, path)
            repaired_paths.append(relative)
    return repaired_paths


def write_asset_envelope(
    content_root: Path,
    asset_path: Path,
    *,
    asset_id: str | None = None,
    asset_type: str | None = None,
    family: str | None = None,
    pack: str | None = None,
    license_id: str = "",
    dependencies: Iterable[str] = (),
    hot_reload: str | None = None,
) -> Path:
    """Write an explicit data-only ABI envelope beside an exported asset."""
    root = Path(content_root).resolve()
    path = Path(asset_path).resolve()
    relative = path.relative_to(root)
    inferred_type, inferred_family = _classify(path)
    destination = path.with_suffix(path.suffix + ".asset.udata")
    resolved_id = asset_id or _infer_id(relative)
    resolved_pack = pack or _infer_pack(relative)
    resolved_reload = hot_reload or ("authoring-only" if path.suffix.lower() in {".slight", ".sclight", ".scui", ".pcp3", ".jmap", ".texgraph", ".scaudio", ".scfont"} else "disabled")
    lines = [
        "@udata 1", "", "[asset]",
        f"asset_id: {json.dumps(resolved_id)};",
        f"asset_type: {json.dumps(asset_type or inferred_type)};",
        f"family: {json.dumps(family or inferred_family)};",
        f"pack: {json.dumps(resolved_pack)};",
        f"license_id: {json.dumps(license_id)};",
        f"dependencies: {json.dumps(list(dependencies))};",
        f"hot_reload: {json.dumps(resolved_reload)};",
        f"source_sha256: {json.dumps(sha256_file(path))};",
        'data_only: true;',
        'unknown_fields_policy: "preserve";',
        "",
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def ensure_asset_envelope(content_root: Path, asset_path: Path, **kwargs: Any) -> Path:
    for candidate in envelope_candidates(Path(asset_path)):
        if candidate.exists() and candidate != Path(asset_path):
            return candidate
    return write_asset_envelope(content_root, asset_path, **kwargs)


@dataclass(slots=True)
class QuarantineEntry:
    original_relative_path: str
    quarantined_relative_path: str
    sha256: str


@dataclass(slots=True)
class QuarantineReceipt:
    receipt_path: Path
    generated_unix: int
    entries: list[QuarantineEntry]
    restored: bool = False


def list_quarantine_receipts(content_root: Path) -> list[QuarantineReceipt]:
    root = Path(content_root).resolve()
    receipts: list[QuarantineReceipt] = []
    for receipt_path in sorted((root / "quarantine").glob("*/QUARANTINE_RECEIPT.json"), reverse=True):
        try:
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entries: list[QuarantineEntry] = []
        raw_entries = payload.get("entries", [])
        if isinstance(raw_entries, list):
            for item in raw_entries:
                if not isinstance(item, dict):
                    continue
                original = str(item.get("original_relative_path", ""))
                quarantined = str(item.get("quarantined_relative_path", ""))
                if original and quarantined:
                    entries.append(QuarantineEntry(original, quarantined, str(item.get("sha256", ""))))
        if not entries and isinstance(payload.get("moved"), list):
            stamp_root = receipt_path.parent.relative_to(root)
            for original in payload["moved"]:
                if isinstance(original, str):
                    entries.append(QuarantineEntry(original, (stamp_root / original).as_posix(), ""))
        receipts.append(QuarantineReceipt(
            receipt_path=receipt_path,
            generated_unix=int(payload.get("generated_unix", 0)),
            entries=entries,
            restored=bool(payload.get("restored", False)),
        ))
    return receipts


def restore_quarantine_receipt(content_root: Path, receipt_path: Path) -> list[str]:
    root = Path(content_root).resolve()
    receipt_resolved = Path(receipt_path).resolve()
    receipt_resolved.relative_to(root / "quarantine")
    receipts = {item.receipt_path.resolve(): item for item in list_quarantine_receipts(root)}
    receipt = receipts.get(receipt_resolved)
    if receipt is None:
        raise ValueError("quarantine receipt is missing or invalid")
    restored: list[str] = []
    for entry in receipt.entries:
        original = (root / entry.original_relative_path).resolve()
        quarantined = (root / entry.quarantined_relative_path).resolve()
        original.relative_to(root)
        quarantined.relative_to(root / "quarantine")
        relative = original.relative_to(root)
        if not relative.parts or relative.parts[0] not in {"user", "mods"}:
            raise ValueError("quarantine recovery is limited to user/mod assets")
        if original.exists():
            raise FileExistsError(f"restore target already exists: {relative.as_posix()}")
        if not quarantined.is_file():
            continue
        if entry.sha256 and sha256_file(quarantined) != entry.sha256:
            raise ValueError(f"quarantined file hash changed: {entry.quarantined_relative_path}")
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(quarantined), str(original))
        restored.append(relative.as_posix())
    payload = json.loads(receipt_resolved.read_text(encoding="utf-8"))
    payload["restored"] = True
    payload["restored_unix"] = int(time.time())
    payload["restored_paths"] = restored
    receipt_resolved.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return restored
