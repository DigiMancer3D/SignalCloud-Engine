from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from tools.asset_doctor.manifest_builder import build_manifest


class ManifestBuilderTests(unittest.TestCase):
    def test_build_and_incremental_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            content = Path(temp) / "content"
            asset = content / "core" / "weapons" / "training" / "sample.udata"
            asset.parent.mkdir(parents=True)
            asset.write_text("sample", encoding="utf-8")

            first = build_manifest(content)
            second = build_manifest(content)
            self.assertEqual(len(first), 1)
            self.assertEqual(first[0].sha256, second[0].sha256)

            with (content / "manifest.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["asset_id"], "sample")
            self.assertEqual(len(rows[0]["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
