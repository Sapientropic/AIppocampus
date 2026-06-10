from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.navigation import attention_evidence_packager as packager  # noqa: E402


class AttentionEvidencePackagerTests(unittest.TestCase):
    def test_source_window_can_package_context_visible_span(self) -> None:
        report = packager.build_evidence_packaging_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}
        case = by_id["context_visible_span_becomes_bounded_evidence"]
        packet = case["packet"]
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(case["baseline_window"]["source_window_radius"], 5)
        self.assertEqual(case["baseline_window"]["retrieval_rank"], 2)
        self.assertEqual(case["packaging"]["candidate_count"], 3)
        self.assertEqual(case["packaging"]["selected_span_rank"], 1)
        self.assertEqual(case["packaging"]["window_radius"], 5)
        self.assertEqual(case["packaging"]["claim_permission"], "bounded_claim_allowed")
        self.assertEqual(packet["output_mode"], "bounded_evidence")
        self.assertEqual(packet["claim_permission"], "bounded_claim_allowed")
        self.assertEqual(packet["source_handles"][0]["line_range"], [45, 53])
        self.assertEqual(packet["source_handles"][0]["char_range"], [128, 220])
        self.assertEqual(packet["head_votes"][0]["head"], "evidence_packaging_head")
        self.assertIn("context_visible_span_packaged", packet["head_votes"][0]["reason_code"])
        self.assertEqual(report["metrics"]["baseline_window_preserved_count"], 4)
        self.assertEqual(report["metrics"]["bounded_evidence_packet_count"], 2)
        self.assertNotIn("PRIVATE_SOURCE_WINDOW_TEXT_SENTINEL", encoded)
        self.assertNotIn("PRIVATE_SPAN_TEXT_SENTINEL", encoded)
        self.assertNotIn('"source_text"', encoded)
        self.assertNotIn('"raw_text"', encoded)

    def test_wrong_stale_and_conflicted_spans_do_not_become_claim_ready(self) -> None:
        report = packager.build_evidence_packaging_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}

        wrong = by_id["wrong_source_top_span_rejected"]
        stale = by_id["stale_span_requires_currentness_check"]
        conflicted = by_id["conflicted_span_packages_counter_evidence"]

        self.assertEqual(
            wrong["packaging"]["rejected_span_candidates"][0]["reason_code"],
            "wrong_source_span",
        )
        self.assertEqual(wrong["packaging"]["selected_span_rank"], 2)
        self.assertEqual(wrong["packet"]["output_mode"], "bounded_evidence")

        self.assertEqual(stale["packet"]["output_mode"], "reopenable_route")
        self.assertEqual(stale["packet"]["claim_permission"], "no_claim_before_reopen")
        self.assertTrue(stale["packaging"]["include_currentness_check"])
        self.assertEqual(stale["packaging"]["claim_permission"], "no_claim_before_reopen")

        self.assertEqual(conflicted["packet"]["output_mode"], "reopenable_route")
        self.assertEqual(conflicted["packet"]["claim_permission"], "no_claim_before_reopen")
        self.assertTrue(conflicted["packaging"]["include_counter_evidence"])
        self.assertEqual(
            conflicted["packaging"]["counter_evidence_handles"][0]["segment_id"],
            "counter-conflict-note",
        )

        self.assertEqual(report["metrics"]["wrong_source_span_promoted_count"], 0)
        self.assertEqual(report["metrics"]["stale_or_conflicted_claim_ready_count"], 0)
        self.assertIn("exact_line_quality_or_sota", report["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
