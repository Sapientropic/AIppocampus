from __future__ import annotations

import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_smoke_module

REPO_ROOT = Path(__file__).resolve().parents[2]

smoke = import_smoke_module("smoke_semantic_paraphrase_reuse")

class SemanticParaphraseReuseSmokeTests(unittest.TestCase):
    def test_smoke_tracks_exact_single_warm_repeated_and_forced_paths(self) -> None:
        result = smoke.run_semantic_paraphrase_reuse_smoke(cwd=REPO_ROOT)

        self.assertTrue(result["ok"])
        self.assertEqual(result["case_count"], 4)

        rows = {str(row["name"]): row for row in result["rows"]}
        self.assertEqual(rows["exact_cache_hit"]["semantic_reuse"]["source"], "exact_semantic_cache")
        self.assertTrue(rows["exact_cache_hit"]["semantic_reuse"]["exact_cache_hit"])
        self.assertFalse(rows["exact_cache_hit"]["semantic_reuse"]["cold_model_call"])

        self.assertEqual(rows["single_warm_neighbor"]["semantic_reuse"]["source"], "cold_model_call")
        self.assertFalse(rows["single_warm_neighbor"]["semantic_reuse"]["semantic_cue_hit"])
        self.assertTrue(rows["single_warm_neighbor"]["semantic_reuse"]["cold_model_call"])
        self.assertEqual(rows["single_warm_neighbor"]["gate_calls"], 1)

        self.assertEqual(rows["repeated_cue_neighbor"]["semantic_reuse"]["source"], "semantic_cue_cache")
        self.assertTrue(rows["repeated_cue_neighbor"]["semantic_reuse"]["semantic_cue_hit"])
        self.assertFalse(rows["repeated_cue_neighbor"]["semantic_reuse"]["cold_model_call"])
        self.assertEqual(rows["repeated_cue_neighbor"]["gate_calls"], 0)

        self.assertEqual(rows["forced_live_calibration"]["semantic_reuse"]["source"], "cold_model_call")
        self.assertTrue(rows["forced_live_calibration"]["semantic_reuse"]["semantic_cue_hit"])
        self.assertTrue(rows["forced_live_calibration"]["semantic_reuse"]["cold_model_call"])
        self.assertEqual(rows["forced_live_calibration"]["gate_calls"], 1)

if __name__ == "__main__":
    unittest.main()
