#!/usr/bin/env python3
"""Inspect and export SignalCloud machine profiles without exposing private data."""
from __future__ import annotations

import argparse
import csv
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ENTRY_RE = re.compile(r"^([A-Za-z0-9_.-]+)\s*:\s*(.+)\s*;\s*$")
PRIVATE_VALUE_RE = re.compile(r"(?:^|[\"'])/(?:home|Users|mnt|media)/|[A-Za-z]:\\\\", re.I)
PROFILE_FILES = ("active.udata", "candidate.udata", "previous_known_good.udata")
PROMOTION_RECEIPT_FILE = "promotion_receipt.udata"
EXPORT_FILES = PROFILE_FILES + (PROMOTION_RECEIPT_FILE,)


@dataclass(frozen=True)
class ProfileStatus:
    name: str
    present: bool
    status: str
    ruleset_id: str
    fingerprint: str
    content_hash: str
    environment_points: int
    fallback_points: int
    resolution_width: int
    resolution_height: int
    target_fps: int
    validation_summary: str
    valid_for_display: bool
    content_signature_current: bool
    reason: str


@dataclass(frozen=True)
class PromotionReceiptStatus:
    name: str
    present: bool
    status: str
    ruleset_id: str
    fingerprint: str
    content_hash: str
    environment_points: int
    previous_known_good_preserved: bool
    valid_for_display: bool
    reason: str


def _unwrap(value: Any) -> Any:
    if isinstance(value, dict) and set(value) == {"value"}:
        return value["value"]
    return value


def parse_udata(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return result
    section = ""
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "//", "@")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            result.setdefault(section, {})
            continue
        match = ENTRY_RE.match(line)
        if not match or not section:
            continue
        key, payload = match.groups()
        try:
            result.setdefault(section, {})[key] = _unwrap(json.loads(payload))
        except json.JSONDecodeError:
            result.setdefault(section, {})[key] = payload
    return result


def machine_profile_content_hash(root: Path) -> str:
    """Match the native canonical performance-content manifest signature."""
    manifest = root / "content" / "manifest.csv"
    if not manifest.is_file():
        payload = "missing-profile-content-manifest"
    else:
        rows: list[str] = []
        try:
            with manifest.open("r", encoding="utf-8", newline="") as stream:
                for row in csv.DictReader(stream):
                    if str(row.get("asset_type", "")).lower() == "rules":
                        continue
                    rows.append("|".join((
                        str(row.get("asset_id", "")),
                        str(row.get("asset_type", "")),
                        str(row.get("family", "")),
                        str(row.get("pack", "")),
                        str(row.get("relative_path", "")),
                        str(row.get("size_bytes", "")),
                        str(row.get("sha256", "")),
                        str(row.get("enabled", "")).lower(),
                    )))
            payload = "\n".join(rows) + "\n"
        except (OSError, csv.Error):
            payload = "invalid-profile-content-manifest"
    value = 1469598103934665603
    for byte in payload.encode("utf-8"):
        value ^= byte
        value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return f"{value:016x}"


def profile_status(path: Path, expected_content_hash: str | None = None) -> ProfileStatus:
    doc = parse_udata(path)
    if not doc:
        return ProfileStatus(path.name, False, "missing", "", "", "", 0, 0, 0, 0, 0, "", False, False, "not created")
    header = doc.get("header", {})
    fingerprint = doc.get("fingerprint", {})
    recommended = doc.get("recommended", {})
    validation = doc.get("validation", {})
    gate_names = (
        ("completed", "complete"),
        ("route_pass", "route"),
        ("frame_pacing_pass", "frame"),
        ("memory_guard_pass", "memory"),
        ("content_hash_pass", "content"),
    )
    gate_parts = [f"{label} {'PASS' if bool(validation.get(key, False)) else 'FAIL'}" for key, label in gate_names]
    if validation:
        passed_stages = int(validation.get("passed_stages", 0) or 0)
        failed_stages = int(validation.get("failed_stages", 0) or 0)
        all_gates_pass = all(bool(validation.get(key, False)) for key, _label in gate_names)
        failed_label = "exploratory limits" if all_gates_pass else "failed"
        gate_parts.append(f"stages {passed_stages} passed / {failed_stages} {failed_label}")
    validation_summary = " · ".join(gate_parts) if validation else ""
    schema_ok = header.get("schema_name") == "signalcloud_machine_profile" and int(header.get("schema_major", 0)) == 1
    privacy_ok = not PRIVATE_VALUE_RE.search(json.dumps(doc, sort_keys=True))
    stored_content_hash = str(fingerprint.get("content_hash", ""))
    content_signature_current = bool(expected_content_hash and stored_content_hash == expected_content_hash)
    if not schema_ok or not privacy_ok:
        reason = "unsupported schema or private value detected"
    elif expected_content_hash is None:
        reason = "profile document parsed; runtime content signature was not checked"
    elif content_signature_current:
        reason = "current performance-content signature"
    else:
        reason = "legacy or stale performance-content signature; clean Official + Promote revalidation required"
    return ProfileStatus(
        path.name,
        True,
        str(header.get("status", "unknown")),
        str(header.get("ruleset_id", "")),
        str(fingerprint.get("privacy_hash", "")),
        stored_content_hash,
        int(recommended.get("environment_points", 0) or 0),
        int(recommended.get("protected_fallback_points", 0) or 0),
        int(fingerprint.get("resolution_width", 0) or 0),
        int(fingerprint.get("resolution_height", 0) or 0),
        int(fingerprint.get("target_fps", 0) or 0),
        validation_summary,
        bool(schema_ok and privacy_ok),
        content_signature_current,
        reason,
    )


def promotion_receipt_status(path: Path) -> PromotionReceiptStatus:
    doc = parse_udata(path)
    if not doc:
        return PromotionReceiptStatus(path.name, False, "missing", "", "", "", 0, False, False, "not created")
    promotion = doc.get("promotion", {})
    privacy_ok = not PRIVATE_VALUE_RE.search(json.dumps(doc, sort_keys=True))
    receipt_ok = bool(promotion.get("ruleset_id")) and bool(promotion.get("fingerprint"))
    reason = "promotion receipt" if receipt_ok and privacy_ok else "incomplete receipt or private value detected"
    return PromotionReceiptStatus(
        path.name,
        True,
        str(promotion.get("status", "unknown")),
        str(promotion.get("ruleset_id", "")),
        str(promotion.get("fingerprint", "")),
        str(promotion.get("content_hash", "")),
        int(promotion.get("environment_points", 0) or 0),
        bool(promotion.get("previous_known_good_preserved", False)),
        bool(receipt_ok and privacy_ok),
        reason,
    )


def profile_directory(root: Path) -> Path:
    return root / "user_data" / "machine_profiles"


def collect_status(root: Path) -> list[ProfileStatus]:
    directory = profile_directory(root)
    expected_content_hash = machine_profile_content_hash(root)
    return [profile_status(directory / name, expected_content_hash) for name in PROFILE_FILES]


def status_text(root: Path) -> str:
    lines = [
        "SignalCloud Machine Profile",
        "Ruleset: signalcloud-alpha-a9-ruleset-1",
        "Private identity policy: hashed capability only",
        "",
    ]
    for item in collect_status(root):
        if not item.present:
            lines.append(f"{item.name}: MISSING")
            continue
        target = ""
        if item.resolution_width and item.resolution_height:
            target = f" | target {item.resolution_width}x{item.resolution_height}"
            if item.target_fps:
                target += f" @ {item.target_fps} FPS"
        status_label = item.status.upper()
        if item.valid_for_display and not item.content_signature_current:
            status_label += " (REVALIDATION REQUIRED)"
        lines.append(
            f"{item.name}: {status_label} | environment {item.environment_points:,} | "
            f"fallback {item.fallback_points:,}{target} | fingerprint {item.fingerprint or 'none'}"
        )
        if item.validation_summary:
            lines.append(f"  gates: {item.validation_summary}")
        if item.valid_for_display and not item.content_signature_current:
            lines.append(f"  runtime status: {item.reason}")

    receipt = promotion_receipt_status(profile_directory(root) / PROMOTION_RECEIPT_FILE)
    if not receipt.present:
        lines.append(f"{receipt.name}: MISSING")
    else:
        preserved = "yes" if receipt.previous_known_good_preserved else "no"
        lines.append(
            f"{receipt.name}: {receipt.status.upper()} PROMOTION RECEIPT | "
            f"environment {receipt.environment_points:,} | fingerprint {receipt.fingerprint or 'none'}"
        )
        lines.append(
            f"  previous known good preserved: {preserved} · content {receipt.content_hash or 'none'}"
        )

    active_item = collect_status(root)[0]
    if not (profile_directory(root) / "active.udata").exists():
        candidate = profile_status(profile_directory(root) / "candidate.udata", machine_profile_content_hash(root))
        lines += ["", "No active profile: the game will use the conservative capability fallback."]
        if candidate.present:
            lines.append(
                "A candidate was found, but it has not been promoted. Use the stress controller's "
                "Official + Promote action after every gate reports PASS."
            )
    elif active_item.valid_for_display and not active_item.content_signature_current:
        lines += [
            "",
            "The active profile document is preserved, but its legacy/stale content signature will be rejected by the game.",
            "Run one clean Official + Promote benchmark to issue the current A9a3 performance-content signature.",
        ]
    return "\n".join(lines) + "\n"


def _sanitized_profile(path: Path) -> dict[str, Any] | None:
    doc = parse_udata(path)
    if not doc:
        return None
    allowed: dict[str, set[str]] = {
        "header": {"schema_name", "schema_major", "ruleset_id", "status", "source_kind", "run_class"},
        "fingerprint": {"privacy_hash", "content_hash", "gpu_class", "resolution_width", "resolution_height", "target_fps"},
        "measured": {"burst_environment_points", "sustainable_environment_points", "burst_entities", "sustainable_entities"},
        "recommended": {
            "environment_points", "combined_point_budget", "protected_fallback_points", "submitted_soft_cap",
            "full_rate_entities", "reduced_rate_entities", "active_lights", "material_layers", "sound_ripples",
            "animated_actors", "playbook_evaluations", "tupd_test_objects", "scui_panels",
        },
        "validation": {"completed", "route_pass", "frame_pacing_pass", "memory_guard_pass", "content_hash_pass", "passed_stages", "failed_stages"},
        "privacy": {"contains_private_paths", "contains_hostname", "contains_serial", "identity_policy"},
        "promotion": {"status", "ruleset_id", "fingerprint", "content_hash", "environment_points", "previous_known_good_preserved"},
    }
    sanitized: dict[str, Any] = {}
    for section, keys in allowed.items():
        values = doc.get(section, {})
        selected = {key: values[key] for key in sorted(keys) if key in values}
        if selected:
            sanitized[section] = selected
    payload = json.dumps(sanitized, sort_keys=True)
    if PRIVATE_VALUE_RE.search(payload):
        raise ValueError(f"private-looking value rejected in {path.name}")
    return sanitized


def export_privacy_bundle(root: Path, output: Path | None = None) -> Path:
    directory = profile_directory(root)
    output = output or (root / "reports" / "machine_profile_privacy_bundle.zip")
    output.parent.mkdir(parents=True, exist_ok=True)
    summaries: dict[str, Any] = {
        "schema": "signalcloud_machine_profile_privacy_bundle_v1",
        "ruleset_id": "signalcloud-alpha-a9-ruleset-1",
        "project_root": "<PROJECT_ROOT>",
        "profiles": {},
    }
    for name in EXPORT_FILES:
        sanitized = _sanitized_profile(directory / name)
        if sanitized is not None:
            summaries["profiles"][name] = sanitized
    text = status_text(root)
    if PRIVATE_VALUE_RE.search(text):
        raise ValueError("status summary unexpectedly contains a private path or identity")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("machine_profiles.json", json.dumps(summaries, indent=2, sort_keys=True) + "\n")
        archive.writestr("PROFILE_SUMMARY.txt", text)
        archive.writestr(
            "PRIVACY_README.txt",
            "This bundle contains hashed capability identity and bounded benchmark recommendations only.\n"
            "It intentionally excludes usernames, home paths, hostnames, serial numbers, saves, logs, and raw hardware identifiers.\n",
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.export:
        output = Path(args.output).resolve() if args.output else None
        print(export_privacy_bundle(root, output))
        return 0
    if args.json:
        print(json.dumps([item.__dict__ for item in collect_status(root)], indent=2))
    else:
        print(status_text(root), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
