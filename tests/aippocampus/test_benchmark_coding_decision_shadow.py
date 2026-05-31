from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
for _path in (SCRIPTS, BENCHMARKS):
    sys.path.insert(0, str(_path))

import benchmark_coding_decision_shadow as benchmark  # noqa: E402


class CodingDecisionShadowBenchmarkTests(unittest.TestCase):
    def test_reports_tracks_a_to_e_and_negative_controls_without_raw_text(self) -> None:
        payload = benchmark.run_benchmark()
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["quality_gate_ok"])
        self.assertEqual(
            set(payload["track_statuses"]),
            {
                "track_a_source_evidence",
                "track_b_rejected_path",
                "track_c_compaction_boundary",
                "track_d_navigation_selection",
                "track_e_anti_nag",
            },
        )
        self.assertTrue(all(status == "sufficient" for status in payload["track_statuses"].values()))
        self.assertEqual(payload["negative_controls"]["wrong_source_evidence"]["passed"], True)
        self.assertEqual(payload["negative_controls"]["visible_source_suppression"]["passed"], True)
        self.assertEqual(payload["negative_controls"]["stale_authority"]["passed"], True)
        self.assertFalse(payload["privacy_boundary"]["raw_text_emitted"])
        self.assertFalse(payload["privacy_boundary"]["raw_source_refs_emitted"])
        self.assertNotIn("Do not replace", encoded)
        self.assertNotIn("thread:decision-shadow", encoded)
        self.assertIn("private_real_history_behavior_lift", payload["cannot_claim"])

    def test_track_b_uses_warning_ticket_and_host_contract(self) -> None:
        payload = benchmark.run_benchmark()
        track_b = payload["tracks"]["track_b_rejected_path"]

        self.assertEqual(track_b["status"], "sufficient")
        self.assertEqual(track_b["cases"][0]["intervention_level"], "warning")
        self.assertEqual(track_b["cases"][0]["proposed_use"], "warn")
        self.assertEqual(track_b["cases"][0]["host_visibility"], "warning")
        self.assertGreater(track_b["cases"][0]["source_ref_count"], 0)

    def test_include_private_text_is_explicit_and_still_marks_boundary(self) -> None:
        payload = benchmark.run_benchmark(include_private_text=True)
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertTrue(payload["privacy_boundary"]["raw_text_emitted"])
        self.assertIn("Do not replace", encoded)
        self.assertIn("private_text_debug_mode_not_public_evidence", payload["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
