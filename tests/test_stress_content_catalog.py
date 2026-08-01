from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "stress_content_catalog.py"
spec = importlib.util.spec_from_file_location("stress_content_catalog", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class StressCatalogTests(unittest.TestCase):
    def test_current_manifest_classifies_native_entities(self) -> None:
        root = Path(__file__).resolve().parents[1]
        records, warnings = module.build_catalog(root)
        self.assertFalse(warnings)
        by_id = {r.asset_id: r for r in records}
        self.assertEqual(by_id["hash_dog"].runtime_support, "native_runtime")
        self.assertEqual(by_id["formless_shadow"].stress_spawn_policy, "spawn_real_engine_entity")
        self.assertEqual(by_id["pivot6_room_complex"].category, "room_set")

    def test_future_boss_is_discovered_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "content/core/entities").mkdir(parents=True)
            (root / "content/core/entities/future_boss.udata").write_text(
                '@udata 1\n[header]\ndata_type: {"name":"combat_entity"};\n'
                '[body]\nrepresentation: {"value":"segmented_point_boss"};\n', encoding='utf-8')
            with (root / "content/manifest.csv").open('w', newline='', encoding='utf-8') as h:
                w=csv.writer(h); w.writerow(['asset_id','asset_type','family','pack','relative_path','size_bytes','sha256','modified_ns','enabled'])
                w.writerow(['future_boss','entities','future_boss.udata','core','core/entities/future_boss.udata','1','0'*64,'0','true'])
            records, _ = module.build_catalog(root)
            self.assertEqual(records[0].category, 'boss')
            self.assertEqual(records[0].runtime_support, 'discovered_proxy_until_factory')


if __name__ == '__main__':
    unittest.main()
