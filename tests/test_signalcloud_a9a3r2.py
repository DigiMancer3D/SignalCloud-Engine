from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from tools.native_stress_watchdog import (
    WatchdogPolicy, _parse_args, heartbeat_timeout_for_phase, run_watchdog,
)

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA9A3R2Tests(unittest.TestCase):
    def test_phase_marker_rule_and_repair_documents_exist(self) -> None:
        paths = (
            ROOT / "ALPHA_A9A3R2_INSTALLED.txt",
            ROOT / "docs/alpha/A9A3R2_GENERATION_HEARTBEAT_TRUTHFUL_HUD.md",
            ROOT / "content/core/rules/a9a3r2_generation_heartbeat_truthful_hud.udata",
            ROOT / "content/core/rules/a9a3r2_generation_heartbeat_truthful_hud.udata.asset.udata",
        )
        for path in paths:
            self.assertTrue(path.is_file(), path)
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths[:4]).lower()
        for phrase in ("generation", "heartbeat", "truthful", "watchdog", "official + promote", "a10"):
            self.assertIn(phrase, combined)

    def test_watchdog_uses_longer_timeout_only_for_generation(self) -> None:
        policy = WatchdogPolicy(heartbeat_timeout=8.0, generation_timeout=90.0)
        self.assertEqual(heartbeat_timeout_for_phase("rendering", policy), 8.0)
        self.assertEqual(heartbeat_timeout_for_phase("stage-complete", policy), 8.0)
        self.assertEqual(heartbeat_timeout_for_phase("generating", policy), 90.0)
        source = (ROOT / "tools/native_stress_watchdog.py").read_text(encoding="utf-8")
        self.assertIn("WATCHDOG_GENERATION_TIMEOUT", source)
        self.assertIn("active_timeout_seconds", source)

    def test_watchdog_cli_and_launcher_expose_generation_override(self) -> None:
        args = _parse_args([
            "/tmp/project", "--heartbeat-timeout=8", "--generation-timeout=120",
            "--", "native-child",
        ])
        self.assertEqual(args.generation_timeout, 120.0)
        launcher = (ROOT / "tools/native_stress_launcher.py").read_text(encoding="utf-8")
        for token in (
            "watchdog_generation_timeout",
            "Point generation/upload timeout seconds",
            "--generation-timeout=",
        ):
            self.assertIn(token, launcher)
        config = json.loads((ROOT / "config/native_stress_gui.json").read_text(encoding="utf-8"))
        self.assertEqual(config["watchdog_generation_timeout"], "90")


    def test_generation_phase_survives_normal_heartbeat_gap(self) -> None:
        with tempfile.TemporaryDirectory(prefix="SignalCloud A9a3r2 watchdog ") as directory:
            root = Path(directory)
            child = root / "fake_child.py"
            child.write_text(
                "import json, sys, time\n"
                "from pathlib import Path\n"
                "values = {}\n"
                "for arg in sys.argv[1:]:\n"
                "    if arg.startswith('--') and '=' in arg:\n"
                "        key, value = arg[2:].split('=', 1)\n"
                "        values[key] = value\n"
                "session = Path(values['session-dir'])\n"
                "heartbeat = Path(values['heartbeat-file'])\n"
                "session.mkdir(parents=True, exist_ok=True)\n"
                "heartbeat.write_text(json.dumps({'phase': 'generating'}), encoding='utf-8')\n"
                "time.sleep(0.50)\n"
                "(session / 'NATIVE_STRESS_REPORT.md').write_text('# completed\\n', encoding='utf-8')\n"
                "(session / 'RUN_STATE.json').write_text(json.dumps({'state': 'completed', 'reason': 'COMPLETED'}), encoding='utf-8')\n",
                encoding="utf-8",
            )
            code = run_watchdog(
                root, [sys.executable, str(child)],
                WatchdogPolicy(heartbeat_timeout=0.20, generation_timeout=3.0, startup_timeout=5.0, poll_seconds=0.02),
            )
            self.assertEqual(code, 0)

    def test_final_hud_state_cannot_revert_to_complete(self) -> None:
        launcher = (ROOT / "tools/native_stress_launcher.py").read_text(encoding="utf-8")
        for token in (
            "self.hud_final_state",
            "self.hud_final_reason",
            'self.hud_final_state = "previous"',
            'self.hud_final_reason = "NO ACTIVE CAMPAIGN"',
            "self.live_path.unlink()",
            'data["campaign_final_state"] = self.hud_final_state or "finished"',
            "final_watchdog_data = watchdog_data",
        ):
            self.assertIn(token, launcher)
        hud = (ROOT / "tools/native_stress_hud.py").read_text(encoding="utf-8")
        self.assertIn('data.get("campaign_final_state", "unknown")', hud)
        self.assertNotIn('data.get("campaign_final_state", "completed")', hud)


if __name__ == "__main__":
    unittest.main()
