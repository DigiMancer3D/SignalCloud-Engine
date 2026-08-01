#!/usr/bin/env python3
"""Non-destructive protected-reload proof for one validated SCFONT asset."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from tools.asset_doctor.asset_doctor import run as run_asset_doctor
from tools.asset_doctor.hot_reload_bridge import stage_preview_reload
from tools.signalcloud_fonts.validator import validate_scfont


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(project_root: Path) -> dict[str, object]:
    root = Path(project_root).resolve()
    live_font = root / "content/core/fonts/terminal_00/Terminal_00.scfont"
    live_hash = sha256(live_font)
    with tempfile.TemporaryDirectory(prefix="signalcloud-font-reload-") as td:
        isolated = Path(td) / "project"
        shutil.copytree(root / "content", isolated / "content")
        probe_font = isolated / "content/user/fonts/terminal_probe.scfont"
        probe_font.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(live_font, probe_font)
        envelope = probe_font.with_name(probe_font.name + ".asset.udata")
        envelope.write_text(
            "@udata 1\n\n[asset]\n"
            'asset_id: "user.fonts.terminal_probe";\n'
            'asset_type: "signalcloud_font";\n'
            'family: "font";\n'
            'pack: "user";\n'
            'license_id: "LicenseRef-SignalCloud-User-Authored";\n'
            'dependencies: [];\n'
            'hot_reload: "authoring-only";\n'
            f'source_sha256: "{sha256(probe_font)}";\n'
            'data_only: true;\n'
            'unknown_fields_policy: "preserve";\n',
            encoding="utf-8",
        )
        if run_asset_doctor(isolated) != 0:
            raise RuntimeError("isolated baseline Asset Doctor failed")
        baseline_hash = sha256(probe_font)
        text = probe_font.read_text(encoding="utf-8")
        text = text.replace('FONT "SC_term_00"', 'FONT "SC_term_00_probe"', 1)
        if text == probe_font.read_text(encoding="utf-8"):
            raise RuntimeError("probe could not locate the FONT record")
        probe_font.write_text(text, encoding="utf-8")
        stats = validate_scfont(probe_font)
        envelope_text = envelope.read_text(encoding="utf-8")
        import re
        envelope_text = re.sub(
            r'source_sha256: "[0-9a-f]{64}";',
            f'source_sha256: "{sha256(probe_font)}";',
            envelope_text,
        )
        envelope.write_text(envelope_text, encoding="utf-8")
        result = stage_preview_reload(isolated)
        status_text = result.status_path.read_text(encoding="utf-8")
        if result.changed_count != 1 or result.changed_font_count != 1 or result.invalid_count != 0:
            raise RuntimeError(
                f"expected exactly one changed font, got changed={result.changed_count}, "
                f"fonts={result.changed_font_count}, invalid={result.invalid_count}"
            )
        if 'asset_type: "signalcloud_font"' not in status_text or 'status: "changed"' not in status_text:
            raise RuntimeError("protected receipt does not contain the changed font")
        if sha256(live_font) != live_hash:
            raise RuntimeError("live core font changed during isolated proof")
        payload: dict[str, object] = {
            "schema": "signalcloud.a5a3r2-font-reload-probe",
            "validation": "PASS",
            "font_name": stats.name,
            "glyphs": stats.glyphs,
            "points": stats.points,
            "changed_count": result.changed_count,
            "changed_font_count": result.changed_font_count,
            "invalid_count": result.invalid_count,
            "transaction_id": result.transaction_id,
            "baseline_sha256": baseline_hash,
            "edited_sha256": sha256(probe_font),
            "live_content_unchanged": True,
        }
    report = root / "reports/a5a3r2_changed_font_probe.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        result = probe(Path(args.project_root))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"A5a3r2 changed-font probe: FAIL | {exc}")
        return 1
    print(
        "A5a3r2 changed-font probe: PASS | fonts "
        f"{result['changed_font_count']} | invalid {result['invalid_count']} | "
        f"tx {result['transaction_id']} | live content unchanged"
    )
    print(Path(args.project_root).resolve() / "reports/a5a3r2_changed_font_probe.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
