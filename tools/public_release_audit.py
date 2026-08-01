#!/usr/bin/env python3
"""Build and audit a repository-safe SignalCloud public source release.

A10 separates the accepted development tree from a clean public stage. The
source tree is never modified in place. Generated/private paths are excluded,
readable local paths are normalized in the staging copy, high-confidence
credential material is blocked, and deterministic tar/zip archives can be
produced. ``--strict-release`` returns non-zero when any publication blocker
remains.
"""
from __future__ import annotations

import argparse
import fnmatch
import gzip
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator, Sequence

SCHEMA_VERSION = 1
PHASE = "A10a2"
PUBLIC_VERSION = "v0.1.0-alpha.1"
PUBLIC_ROOT_NAME = "SignalCloud-Engine"

DEFAULT_POLICY = {
    "schema_version": 1,
    "phase": PHASE,
    "public_version": PUBLIC_VERSION,
    "public_root_name": PUBLIC_ROOT_NAME,
    "excluded_directories": [
        ".git", ".hg", ".svn", ".idea", ".vscode",
        ".venv", "venv", "env", ".envdir",
        "build", "build-core", "build-debug", "build-release",
        "cmake-build-*", "CMakeFiles", "_deps", "deps", ".deps",
        ".signalcloud_shared_deps", ".signalcloud_envs",
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        "cache", ".cache", "tmp", "temp",
        "reports", "user_data", "userdata", "saves", "save", "profiles",
        "content/quarantine", "exports/packs", "release_build",
        "arch", "archive", "archives",
        "wallet", "wallets", "keys", "private", "secrets", ".ssh", ".gnupg",
    ],
    "excluded_files": [
        "*.pyc", "*.pyo", "*.o", "*.obj", "*.a", "*.lib", "*.so", "*.dll", "*.dylib",
        "CMakeCache.txt", "build.ninja", ".ninja_deps", ".ninja_log", "cmake_install.cmake",
        "compile_commands.json", "install_manifest.txt",
        "prompt_history*", "Pasted text*", "conversation_export*", "chat_export*",
        "LIVE_SNAPSHOT.json", "RUN_STATE.json", "WATCHDOG_HEARTBEAT.json",
        "active.udata", "candidate.udata", "previous_known_good.udata",
        "promotion_receipt.udata", "workload_registry.udata",
        "*.tar", "*.tar.gz", "*.tgz", "*.zip", "*.7z", "*.rar",
        "*.log", "*.out", "*.trace", "core", "core.*",
        ".DS_Store", "Thumbs.db",
    ],
    "required_public_documents": [
        "README.md", "CONTRIBUTING.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md",
        "PUBLIC_RELEASE_LICENSE_DECISION.md",
    ],
    "strict_required_documents": ["LICENSE"],
    "advisory_paths": ["legacy", "phase reports"],
}

TEXT_SUFFIXES = {
    "", ".txt", ".md", ".rst", ".py", ".pyi", ".sh", ".bash", ".zsh",
    ".cpp", ".cc", ".cxx", ".c", ".hpp", ".hh", ".hxx", ".h",
    ".glsl", ".vert", ".frag", ".comp", ".cmake", ".json", ".csv",
    ".udata", ".scui", ".sclight", ".jmap", ".texgraph", ".playbook",
    ".scphysics", ".scshowcase", ".tupd", ".script", ".ini", ".cfg",
    ".conf", ".toml", ".yaml", ".yml", ".desktop", ".service",
    ".gitignore", ".gitattributes", ".license",
}

# High-confidence patterns only. Generic words such as "token" and "password"
# are intentionally not enough to block a file because the project contains
# schemas, tests, and documentation that discuss those concepts safely.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key-block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("openai-style-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
)

PERSONAL_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![A-Za-z0-9_])/(?:home|Users)/[^/\s\"']+/"),
    re.compile(r"(?<![A-Za-z0-9_])${HOME}/"),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s\"']+\\"),
)


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    detail: str


@dataclass
class AuditReport:
    schema_version: int = SCHEMA_VERSION
    phase: str = PHASE
    public_version: str = PUBLIC_VERSION
    source_root: str = "<PROJECT_ROOT>"
    stage_root: str = ""
    scanned_files: int = 0
    included_files: int = 0
    included_bytes: int = 0
    excluded_paths: list[str] = field(default_factory=list)
    redacted_files: list[str] = field(default_factory=list)
    manifest_sha256: str = ""
    archive_sha256: str = ""
    archive_name: str = ""
    zip_sha256: str = ""
    zip_name: str = ""
    release_ready: bool = False
    findings: list[Finding] = field(default_factory=list)

    @property
    def blockers(self) -> list[Finding]:
        return [item for item in self.findings if item.severity == "blocker"]

    @property
    def warnings(self) -> list[Finding]:
        return [item for item in self.findings if item.severity == "warning"]

    def to_jsonable(self) -> dict[str, object]:
        data = asdict(self)
        data["blocker_count"] = len(self.blockers)
        data["warning_count"] = len(self.warnings)
        return data


def _load_policy(root: Path) -> dict[str, object]:
    path = root / "config" / "public_release_policy.json"
    if not path.is_file():
        return json.loads(json.dumps(DEFAULT_POLICY))
    raw = json.loads(path.read_text(encoding="utf-8"))
    policy = json.loads(json.dumps(DEFAULT_POLICY))
    for key, value in raw.items():
        policy[key] = value
    return policy


def _normal_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _path_components(rel: str) -> tuple[str, ...]:
    return PurePosixPath(rel).parts


def _matches_directory_policy(rel: str, patterns: Sequence[str]) -> bool:
    parts = _path_components(rel)
    for pattern in patterns:
        pattern = pattern.strip("/")
        if not pattern:
            continue
        if "/" in pattern:
            if rel == pattern or rel.startswith(pattern + "/"):
                return True
            continue
        for part in parts:
            if fnmatch.fnmatchcase(part, pattern):
                return True
    return False


def _matches_file_policy(rel: str, patterns: Sequence[str]) -> bool:
    name = PurePosixPath(rel).name
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def _looks_text(path: Path, data: bytes) -> bool:
    if b"\x00" in data[:4096]:
        return False
    name = path.name.lower()
    suffix = path.suffix.lower()
    if name in {"cmakelists.txt", "makefile", ".gitignore", ".gitattributes"}:
        return True
    if suffix in TEXT_SUFFIXES:
        return True
    if len(data) > 2_000_000:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _secret_hits(text: str) -> list[str]:
    return [name for name, pattern in SECRET_PATTERNS if pattern.search(text)]


def _sanitize_text(text: str, source_root: Path) -> tuple[str, bool]:
    changed = False
    replacements: list[tuple[str, str]] = []
    root_text = str(source_root)
    home_text = str(Path.home())
    if root_text:
        replacements.append((root_text, "<PROJECT_ROOT>"))
    if home_text and home_text != "/":
        replacements.append((home_text, "${HOME}"))
    for old, new in replacements:
        if old in text:
            text = text.replace(old, new)
            changed = True

    new_text = re.sub(r"(?<![A-Za-z0-9_])/(?:home|Users)/[^/\s\"']+", "${HOME}", text)
    new_text = re.sub(r"(?<![A-Za-z0-9_])${HOME}", "${HOME}", new_text)
    new_text = re.sub(r"[A-Za-z]:\\Users\\[^\\\s\"']+", "${HOME}", new_text)
    if new_text != text:
        changed = True
        text = new_text
    return text, changed


def _iter_source_files(root: Path, policy: dict[str, object]) -> Iterator[tuple[str, Path]]:
    excluded_dirs = tuple(str(item) for item in policy["excluded_directories"])
    excluded_files = tuple(str(item) for item in policy["excluded_files"])
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        current_rel = "" if current_path == root else _normal_rel(current_path, root)
        kept_dirs: list[str] = []
        for directory in sorted(dirs):
            candidate = current_path / directory
            rel = directory if not current_rel else f"{current_rel}/{directory}"
            if candidate.is_symlink() or _matches_directory_policy(rel, excluded_dirs):
                continue
            kept_dirs.append(directory)
        dirs[:] = kept_dirs
        for filename in sorted(files):
            path = current_path / filename
            if path.is_symlink() or not path.is_file():
                continue
            rel = filename if not current_rel else f"{current_rel}/{filename}"
            if _matches_directory_policy(rel, excluded_dirs):
                continue
            if _matches_file_policy(rel, excluded_files):
                continue
            yield rel, path


def _source_exclusions(root: Path, policy: dict[str, object]) -> list[str]:
    excluded_dirs = tuple(str(item) for item in policy["excluded_directories"])
    excluded_files = tuple(str(item) for item in policy["excluded_files"])
    found: list[str] = []
    for path in root.rglob("*"):
        try:
            rel = _normal_rel(path, root)
        except ValueError:
            continue
        if path.is_dir() and _matches_directory_policy(rel, excluded_dirs):
            found.append(rel + "/")
        elif path.is_file() and (
            _matches_directory_policy(rel, excluded_dirs)
            or _matches_file_policy(rel, excluded_files)
        ):
            found.append(rel)
    return sorted(set(found), key=str.casefold)


def _add_document_findings(root: Path, report: AuditReport, policy: dict[str, object]) -> None:
    for rel in policy["required_public_documents"]:
        if not (root / str(rel)).is_file():
            report.findings.append(Finding(
                "blocker", "missing-public-document", str(rel),
                "Required public-alpha documentation is missing.",
            ))
    for rel in policy["strict_required_documents"]:
        if not (root / str(rel)).is_file():
            report.findings.append(Finding(
                "blocker", "license-selection-required", str(rel),
                "The project owner must select and add the public code/content license before publication.",
            ))
    for rel in policy.get("advisory_paths", []):
        path = root / str(rel)
        if path.exists():
            report.findings.append(Finding(
                "warning", "history-review-required", str(rel),
                "This historical tree is retained in the candidate and should be curated before the final public tag.",
            ))


def _write_manifest(stage_root: Path) -> tuple[Path, str, int, int]:
    entries: list[tuple[str, str, int]] = []
    ignored = {
        "PUBLIC_SOURCE_MANIFEST.sha256",
        "PUBLIC_SOURCE_AUDIT.json",
        "PUBLIC_SOURCE_AUDIT.md",
    }
    for path in sorted(stage_root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file():
            continue
        rel = _normal_rel(path, stage_root)
        if rel in ignored:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append((rel, digest, path.stat().st_size))
    manifest = stage_root / "PUBLIC_SOURCE_MANIFEST.sha256"
    lines = [f"{digest}  {rel}" for rel, digest, _ in entries]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    return manifest, manifest_digest, len(entries), sum(size for _, _, size in entries)


def _scan_stage(stage_root: Path, report: AuditReport) -> None:
    for path in sorted(stage_root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file():
            continue
        rel = _normal_rel(path, stage_root)
        report.scanned_files += 1
        data = path.read_bytes()
        if path.suffix.lower() in {".o", ".obj", ".a", ".lib", ".so", ".dll", ".dylib", ".pyc", ".pyo"}:
            report.findings.append(Finding(
                "blocker", "binary-artifact", rel,
                "Generated binary/object material entered the public stage.",
            ))
        if _looks_text(path, data):
            text = data.decode("utf-8")
            for name in _secret_hits(text):
                report.findings.append(Finding(
                    "blocker", "secret-pattern", rel,
                    f"High-confidence credential pattern detected: {name}.",
                ))
            for pattern in PERSONAL_PATH_PATTERNS:
                if pattern.search(text):
                    report.findings.append(Finding(
                        "blocker", "personal-absolute-path", rel,
                        "A personal absolute path remained after staging normalization.",
                    ))
                    break


def prepare_public_stage(source_root: Path, stage_parent: Path, *, replace: bool = False) -> AuditReport:
    source_root = source_root.expanduser().resolve()
    stage_parent = stage_parent.expanduser().resolve()
    if not source_root.is_dir() or not (source_root / "CMakeLists.txt").is_file():
        raise ValueError(f"Not a SignalCloud source root: {source_root}")
    try:
        stage_parent.relative_to(source_root)
    except ValueError:
        pass
    else:
        raise ValueError("Public stage output must be outside the project source root.")

    policy = _load_policy(source_root)
    public_name = str(policy.get("public_root_name", PUBLIC_ROOT_NAME))
    stage_root = stage_parent / public_name
    if stage_parent.exists():
        if not replace and any(stage_parent.iterdir()):
            raise FileExistsError(f"Output directory is not empty: {stage_parent}")
        if replace:
            shutil.rmtree(stage_parent)
    stage_root.mkdir(parents=True, exist_ok=True)

    report = AuditReport(
        phase=str(policy.get("phase", PHASE)),
        public_version=str(policy.get("public_version", PUBLIC_VERSION)),
        stage_root=public_name,
    )
    report.excluded_paths = _source_exclusions(source_root, policy)

    for rel, source in _iter_source_files(source_root, policy):
        data = source.read_bytes()
        destination = stage_root / PurePosixPath(rel)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if _looks_text(source, data):
            text = data.decode("utf-8")
            hits = _secret_hits(text)
            if hits:
                report.excluded_paths.append(rel + " [credential-pattern-blocked]")
                report.findings.append(Finding(
                    "blocker", "secret-source-file-blocked", rel,
                    "File was withheld from staging because it contains: " + ", ".join(hits),
                ))
                continue
            text, changed = _sanitize_text(text, source_root)
            data = text.encode("utf-8")
            if changed:
                report.redacted_files.append(rel)
        destination.write_bytes(data)
        mode = stat.S_IMODE(source.stat().st_mode)
        os.chmod(destination, mode)
        report.included_files += 1
        report.included_bytes += len(data)

    _add_document_findings(stage_root, report, policy)
    _, report.manifest_sha256, manifest_count, manifest_bytes = _write_manifest(stage_root)
    # The manifest itself is intentionally outside its own hash list.
    report.included_files = manifest_count + 1
    report.included_bytes = manifest_bytes + (stage_root / "PUBLIC_SOURCE_MANIFEST.sha256").stat().st_size
    _scan_stage(stage_root, report)
    report.release_ready = not report.blockers
    _write_reports(stage_root, report)
    return report


def _write_reports(stage_root: Path, report: AuditReport) -> None:
    json_path = stage_root / "PUBLIC_SOURCE_AUDIT.json"
    md_path = stage_root / "PUBLIC_SOURCE_AUDIT.md"
    json_path.write_text(
        json.dumps(report.to_jsonable(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# SignalCloud Public Source Audit",
        "",
        f"- Phase: **{report.phase}**",
        f"- Candidate version: **{report.public_version}**",
        f"- Release ready: **{'YES' if report.release_ready else 'NO'}**",
        f"- Included files: **{report.included_files}**",
        f"- Included bytes: **{report.included_bytes}**",
        f"- Redacted text files: **{len(report.redacted_files)}**",
        f"- Excluded development/private paths: **{len(report.excluded_paths)}**",
        f"- Manifest SHA-256: `{report.manifest_sha256}`",
        "",
        "## Blocking items",
        "",
    ]
    if report.blockers:
        lines.extend(f"- `{item.code}` — `{item.path}`: {item.detail}" for item in report.blockers)
    else:
        lines.append("- None.")
    lines.extend(["", "## Warnings", ""])
    if report.warnings:
        lines.extend(f"- `{item.code}` — `{item.path}`: {item.detail}" for item in report.warnings)
    else:
        lines.append("- None.")
    lines.extend([
        "",
        "## Important boundary",
        "",
        "This public stage is generated from the accepted source tree without modifying it. "
        + (
            "The strict publication gate passed with no blockers."
            if report.release_ready
            else "Publication remains blocked until every item above is resolved."
        ),
        "",
    ])
    md_path.write_text("\n".join(lines), encoding="utf-8")


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    if info.isdir():
        info.mode = 0o755
    elif info.isfile():
        executable = bool(info.mode & 0o111)
        info.mode = 0o755 if executable else 0o644
    return info


def build_deterministic_archive(stage_root: Path, archive_path: Path) -> str:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with archive_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as zipped:
            with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as tar:
                tar.add(stage_root, arcname=stage_root.name, recursive=True, filter=_tar_filter)
    return hashlib.sha256(archive_path.read_bytes()).hexdigest()


def build_deterministic_zip(stage_root: Path, zip_path: Path) -> str:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    fixed_time = (1980, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(stage_root.rglob("*"), key=lambda item: item.as_posix().casefold()):
            rel = PurePosixPath(stage_root.name) / PurePosixPath(_normal_rel(path, stage_root))
            if path.is_dir():
                info = zipfile.ZipInfo(str(rel).rstrip("/") + "/", date_time=fixed_time)
                info.create_system = 3
                info.external_attr = (0o755 << 16) | 0x10
                archive.writestr(info, b"")
                continue
            info = zipfile.ZipInfo(str(rel), date_time=fixed_time)
            info.create_system = 3
            executable = bool(stat.S_IMODE(path.stat().st_mode) & 0o111)
            info.external_attr = ((0o755 if executable else 0o644) << 16)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    return hashlib.sha256(zip_path.read_bytes()).hexdigest()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--output", type=Path, help="Parent directory for the SignalCloud-Engine staging tree.")
    parser.add_argument("--archive", type=Path, help="Optional deterministic .tar.gz output path.")
    parser.add_argument("--zip", dest="zip_path", type=Path, help="Optional deterministic .zip output path.")
    parser.add_argument("--replace", action="store_true", help="Replace an existing output directory.")
    parser.add_argument("--strict-release", action="store_true", help="Return non-zero while any blocker remains.")
    parser.add_argument("--json", action="store_true", help="Print the final report as JSON.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    root = args.project_root.expanduser().resolve()
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if args.output is None:
        temporary = tempfile.TemporaryDirectory(prefix="signalcloud-public-audit-")
        output = Path(temporary.name)
    else:
        output = args.output.expanduser().resolve()
    try:
        report = prepare_public_stage(root, output, replace=args.replace)
        stage_root = output / str(_load_policy(root).get("public_root_name", PUBLIC_ROOT_NAME))
        if args.archive is not None:
            archive = args.archive.expanduser().resolve()
            digest = build_deterministic_archive(stage_root, archive)
            report.archive_name = archive.name
            report.archive_sha256 = digest
        if args.zip_path is not None:
            zip_path = args.zip_path.expanduser().resolve()
            digest = build_deterministic_zip(stage_root, zip_path)
            report.zip_name = zip_path.name
            report.zip_sha256 = digest
        if args.archive is not None or args.zip_path is not None:
            _write_reports(stage_root, report)
        if args.json:
            print(json.dumps(report.to_jsonable(), indent=2, sort_keys=True))
        else:
            print("SignalCloud public source candidate audit")
            print(f"Stage: {stage_root}")
            print(f"Included: {report.included_files} files | {report.included_bytes} bytes")
            print(f"Excluded: {len(report.excluded_paths)} paths | redacted: {len(report.redacted_files)} files")
            print(f"Blockers: {len(report.blockers)} | warnings: {len(report.warnings)}")
            print(f"Release ready: {'YES' if report.release_ready else 'NO'}")
            if report.archive_name:
                print(f"Archive: {report.archive_name} | SHA-256 {report.archive_sha256}")
            if report.zip_name:
                print(f"ZIP: {report.zip_name} | SHA-256 {report.zip_sha256}")
            for item in report.blockers:
                print(f"BLOCKER {item.code}: {item.path} — {item.detail}")
        return 2 if args.strict_release and report.blockers else 0
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
