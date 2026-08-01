from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.asset_doctor.asset_doctor import run as run_asset_doctor
from tools.asset_doctor.hot_reload_bridge import stage_preview_reload
from tools.signalcloud_audio.compiler import compile_audio_interference_runtime
from tools.signalcloud_audio.managed import ensure_managed_audio_profile, save_profile
from tools.signalcloud_materials.compiler import compile_material_runtime
from tools.signalcloud_materials.managed import (
    ensure_managed_material_set,
    save_surface_definition_layers,
)

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA5A3Tests(unittest.TestCase):
    def test_shipped_audio_profile_compiles_deterministically(self) -> None:
        first = compile_audio_interference_runtime(ROOT)
        text_a = first.output.read_text(encoding="utf-8")
        second = compile_audio_interference_runtime(ROOT)
        self.assertEqual(first.signature, second.signature)
        self.assertEqual(text_a, second.output.read_text(encoding="utf-8"))
        self.assertEqual(first.profile_count, 1)
        self.assertEqual(first.warning_count, 0)
        self.assertIn('frequency_band: "low"', text_a)
        self.assertIn("wave_count: 3", text_a)

    def test_definition_layers_compile_all_named_channels(self) -> None:
        result = compile_material_runtime(ROOT)
        text = result.output.read_text(encoding="utf-8")
        for token in (
            "definition_layer_count", "definition_hd_light", "definition_hd_texture",
            "definition_outer_light", "definition_outer_texture", "definition_inner_texture",
        ):
            self.assertIn(token, text)
        carpet = json.loads((ROOT / "content/core/materials/office_carpet.jmap").read_text())
        wall = json.loads((ROOT / "content/core/materials/office_wallpaper.jmap").read_text())
        ceiling = json.loads((ROOT / "content/core/materials/ceiling_tile.jmap").read_text())
        self.assertGreaterEqual(len(carpet["definition_layers"]), 3)
        self.assertGreaterEqual(len(wall["definition_layers"]), 3)
        self.assertEqual({item["name"] for item in ceiling["definition_layers"]}, {"HD Light", "Outer Light"})

    def test_renderer_consumes_definition_and_authored_audio_controls(self) -> None:
        cpp = (ROOT / "engine/render/point_renderer.cpp").read_text()
        for token in (
            "uMaterialDefinitionLayers", "definitionHDLight", "definitionInnerTexture",
            "uSoundWaveCount", "uSoundWaveSharpness", "uSoundDisplacementScale",
            "uSoundColorMix", "uSoundVisibilityFloor",
        ):
            self.assertIn(token, cpp)
        self.assertIn("set_audio_interference(const SoundInterferenceEvent&", (ROOT / "engine/render/point_renderer.hpp").read_text())

    def test_hash_dog_uses_authored_profile_for_visual_and_hearing(self) -> None:
        game = (ROOT / "app/game_main.cpp").read_text()
        self.assertIn("audio_interference_runtime.hash_dog_bark()", game)
        self.assertIn("bark_profile.wave_count", game)
        self.assertIn("bark_profile.hearing_loudness", game)
        self.assertIn("bark_profile.cooldown_seconds", game)
        self.assertIn("renderer.set_audio_interference(audio_event)", game)

    def test_managed_audio_profile_is_preferred_and_stageable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shutil.copytree(ROOT / "content/core/audio", root / "content/core/audio")
            (root / "content/user/audio").mkdir(parents=True)
            managed = ensure_managed_audio_profile(root)
            self.assertTrue(managed.created)
            save_profile(root, {"wave_count": 5, "color_mix": 0.5})
            result = compile_audio_interference_runtime(root)
            text = result.output.read_text(encoding="utf-8")
            self.assertIn("content/user/audio/hash_dog_bark.scaudio", text)
            self.assertIn("wave_count: 5", text)

    def test_protected_stage_compiles_changed_audio_runtime(self) -> None:
        profile = ROOT / "content/core/audio/hash_dog_bark.scaudio"
        original = profile.read_text(encoding="utf-8")
        try:
            self.assertEqual(run_asset_doctor(ROOT), 0)
            payload = json.loads(original)
            payload["visual"]["wave_count"] = 4
            profile.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            result = stage_preview_reload(ROOT)
            self.assertGreaterEqual(result.changed_audio_count, 1)
            status = (ROOT / "user_data/studio/hot_reload_latest.udata").read_text()
            self.assertIn("changed_audio_count", status)
            self.assertIn("hot_reload/audio", status)
        finally:
            profile.write_text(original, encoding="utf-8")
            run_asset_doctor(ROOT)
            compile_audio_interference_runtime(ROOT)
            stage_preview_reload(ROOT)

    def test_managed_definition_layers_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shutil.copytree(ROOT / "content/core/materials", root / "content/core/materials")
            ensure_managed_material_set(root)
            save_surface_definition_layers(root, "wall", [
                {"name": "HD Texture", "opacity": 0.31},
                {"name": "Outer Texture", "opacity": 0.49},
                {"name": "Inner Texture", "opacity": 0.77},
            ])
            result = compile_material_runtime(root)
            text = result.output.read_text(encoding="utf-8")
            self.assertIn("definition_hd_texture: 0.310000", text)
            self.assertIn("definition_outer_texture: 0.490000", text)
            self.assertIn("definition_inner_texture: 0.770000", text)

    def test_studio_exposes_definition_and_audio_editors(self) -> None:
        lab = (ROOT / "tools/jitter_texture_lab.py").read_text()
        self.assertIn("Definition layers", lab)
        self.assertIn("Edit audio interference", lab)
        self.assertIn("Managed Audio Interference", lab)
        self.assertTrue((ROOT / "scripts/create_managed_audio_profile.sh").is_file())
        self.assertTrue((ROOT / "scripts/toggle_audio_interference_profile.sh").is_file())

    def test_build_gates_compile_audio_runtime_and_f9_receipt(self) -> None:
        for script in ("scripts/run_selftests.sh", "scripts/setup_dev_environment.sh", "scripts/launch_game.sh"):
            self.assertIn("compile_audio_interference_runtime.sh", (ROOT / script).read_text())
        cmake = (ROOT / "CMakeLists.txt").read_text()
        self.assertIn("engine/audio/audio_interference_runtime.cpp", cmake)
        self.assertIn("signalcloud_audio_interference_runtime_tests", cmake)
        game = (ROOT / "app/game_main.cpp").read_text()
        self.assertIn("changed_audio_profile", game)
        self.assertIn("audio_applied", game)
        self.assertIn("audio_runtime_signature", game)

    def test_audio_toggle_stages_against_pre_edit_baseline(self) -> None:
        script = (ROOT / "scripts/toggle_audio_interference_profile.sh").read_text()
        baseline = script.index("if run(root) != 0")
        edit = script.index("save_profile(root")
        stage = script.index("stage_preview_reload(root)")
        self.assertLess(baseline, edit)
        self.assertLess(edit, stage)
        self.assertNotIn("compile_audio_interference_runtime(root)\nrun(root)", script)


if __name__ == "__main__":
    unittest.main()
