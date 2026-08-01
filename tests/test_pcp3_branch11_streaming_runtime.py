from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.pcp3.io import udata_text
from tools.pcp3.model import PCPDocument, PCPPoint, SEMANTIC_FLAGS
from tools.pcp3.streaming_runtime import (
    SCHEMA,
    apply_profile,
    build_chunk_manifest,
    compile_streaming_runtime,
    ensure_streaming_runtime,
    planned_point_count,
    ratio_for_distance,
    streaming_runtime_udata,
    validate_streaming_runtime,
    write_streaming_runtime_files,
)


class Branch11StreamingRuntimeTests(unittest.TestCase):
    def make_doc(self) -> PCPDocument:
        doc = PCPDocument.new("room")
        doc.asset_id = "branch11_stream_room"
        doc.display_name = "Branch 11 Stream Room"
        for z in range(20):
            for x in range(20):
                flag = SEMANTIC_FLAGS["wall"] if x in {0, 19} or z in {0, 19} else 0
                doc.points.append(PCPPoint(float(x), 0.0, float(z), flags=flag))
        cfg = ensure_streaming_runtime(doc)
        cfg.update({"enabled": True, "game_enabled": True, "stress_enabled": True})
        return doc

    def test_profile_presets_keep_adaptive_8m_default(self) -> None:
        doc = PCPDocument.new("room")
        cfg = ensure_streaming_runtime(doc)
        self.assertEqual(cfg["profile"], "adaptive_8m")
        apply_profile(cfg, "low_memory")
        self.assertEqual(cfg["maximum_points"], 180_000)
        self.assertLess(cfg["very_far_ratio"], cfg["mid_ratio"])

    def test_distance_ratios_and_bounded_counts(self) -> None:
        doc = self.make_doc()
        cfg = ensure_streaming_runtime(doc)
        cfg.update({
            "near_distance": 10.0,
            "mid_distance": 20.0,
            "far_distance": 30.0,
            "near_ratio": 1.0,
            "mid_ratio": 0.5,
            "far_ratio": 0.25,
            "very_far_ratio": 0.1,
            "minimum_points": 20,
            "maximum_points": 300,
        })
        self.assertEqual(ratio_for_distance(cfg, 5.0), 1.0)
        self.assertEqual(ratio_for_distance(cfg, 15.0), 0.5)
        self.assertEqual(ratio_for_distance(cfg, 25.0), 0.25)
        self.assertEqual(ratio_for_distance(cfg, 40.0), 0.1)
        self.assertEqual(planned_point_count(doc, 5.0), 300)
        self.assertEqual(planned_point_count(doc, 40.0), 40)

    def test_chunk_manifest_is_deterministic_and_covers_source(self) -> None:
        doc = self.make_doc()
        cfg = ensure_streaming_runtime(doc)
        cfg["chunk_edge"] = 5.0
        first = build_chunk_manifest(doc)
        second = build_chunk_manifest(doc)
        self.assertEqual(first, second)
        self.assertEqual(sum(chunk["point_count"] for chunk in first["chunks"]), len(doc.points))
        self.assertGreater(first["chunk_count"], 1)
        self.assertGreater(first["important_point_count"], 0)

    def test_compile_reports_four_lod_tiers(self) -> None:
        payload = compile_streaming_runtime(self.make_doc())
        self.assertEqual(payload["schema"], SCHEMA)
        self.assertEqual([row["tier"] for row in payload["lod_samples"]], ["near", "mid", "far", "very_far"])
        counts = [row["planned_points"] for row in payload["lod_samples"]]
        self.assertEqual(counts, sorted(counts, reverse=True))
        self.assertFalse(payload["runtime_policy"]["source_geometry_mutation"])

    def test_validation_finds_no_target(self) -> None:
        doc = self.make_doc()
        cfg = ensure_streaming_runtime(doc)
        cfg["game_enabled"] = False
        cfg["stress_enabled"] = False
        findings = validate_streaming_runtime(doc)
        self.assertTrue(any(row["severity"] == "warning" and "no execution target" in row["message"] for row in findings))

    def test_sidecars_and_main_udata(self) -> None:
        doc = self.make_doc()
        with tempfile.TemporaryDirectory() as temp:
            paths = write_streaming_runtime_files(Path(temp), doc)
            self.assertTrue(paths["json"].exists())
            self.assertTrue(paths["udata"].exists())
            self.assertTrue(paths["chunks"].exists())
            loaded = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(loaded["asset_id"], doc.asset_id)
            self.assertIn("[streaming]", streaming_runtime_udata(loaded))
        doc.metadata["streaming_json_file"] = "branch11_stream_room.pcp3stream.json"
        doc.metadata["streaming_udata_file"] = "branch11_stream_room.pcp3stream.udata"
        doc.metadata["streaming_chunks_file"] = "branch11_stream_room.pcp3chunks.json"
        cert = {"author": {}, "serial_id": "PCP3-TEST", "created_epoch_octal": "0o1"}
        text = udata_text(doc, "a.pcp3cloud", "a.pcp3", "a.pcpcert.json", "abc", cert)
        self.assertIn("[runtime_streaming]", text)
        self.assertIn("adaptive_8m_preserved", text)
        self.assertIn("branch11_stream_room.pcp3stream.udata", text)

    def test_future_attributes_survive(self) -> None:
        doc = self.make_doc()
        cfg = ensure_streaming_runtime(doc)
        cfg["future_attributes"]["gpu_chunk_decode"] = {"version": 2}
        self.assertEqual(ensure_streaming_runtime(doc)["future_attributes"]["gpu_chunk_decode"]["version"], 2)


if __name__ == "__main__":
    unittest.main()
