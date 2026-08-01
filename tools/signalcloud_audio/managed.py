#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.asset_doctor.content_abi import write_asset_envelope

LICENSE_ID = "LicenseRef-SignalCloud-User-Authored"


@dataclass(frozen=True)
class ManagedAudioResult:
    path: Path
    created: bool


def ensure_managed_audio_profile(project_root: Path) -> ManagedAudioResult:
    root = Path(project_root).resolve()
    source = root / "content/core/audio/hash_dog_bark.scaudio"
    target = root / "content/user/audio/hash_dog_bark.scaudio"
    created = False
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.loads(source.read_text(encoding="utf-8"))
        payload["asset_id"] = "user.audio.hash_dog_bark"
        payload["name"] = "Managed Hash Dog Low-Band Bark"
        payload.setdefault("extensions", {})["managed_from"] = source.relative_to(root).as_posix()
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        created = True
    payload = json.loads(target.read_text(encoding="utf-8"))
    write_asset_envelope(
        root / "content", target,
        asset_id=str(payload["asset_id"]), asset_type="audio_interference_profile",
        family="audio", pack="user", license_id=LICENSE_ID,
        hot_reload="authoring-only",
    )
    return ManagedAudioResult(target, created)


def load_profile(project_root: Path) -> tuple[Path, dict[str, Any]]:
    managed = ensure_managed_audio_profile(project_root)
    return managed.path, json.loads(managed.path.read_text(encoding="utf-8"))


def save_profile(project_root: Path, updates: dict[str, Any]) -> Path:
    path, payload = load_profile(project_root)
    event = payload.setdefault("event", {})
    visual = payload.setdefault("visual", {})
    gameplay = payload.setdefault("gameplay", {})
    for key in ("strength", "duration_seconds", "obstruction_path"):
        if key in updates:
            event[key] = updates[key]
    for key in ("radius_scale", "wave_count", "wave_sharpness", "displacement_scale", "color_mix", "visibility_floor"):
        if key in updates:
            visual[key] = updates[key]
    for key in ("hearing_loudness", "cooldown_seconds"):
        if key in updates:
            gameplay[key] = updates[key]
    if "frequency_band" in updates:
        payload["frequency_band"] = updates["frequency_band"]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_asset_envelope(
        Path(project_root).resolve() / "content", path,
        asset_id=str(payload["asset_id"]), asset_type="audio_interference_profile",
        family="audio", pack="user", license_id=LICENSE_ID,
        hot_reload="authoring-only",
    )
    return path
