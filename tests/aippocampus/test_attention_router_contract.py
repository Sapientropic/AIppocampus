from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.navigation import attention_router_contract as contract  # noqa: E402


class AttentionRouterContractTests(unittest.TestCase):
    def test_hard_masks_block_high_relevance_routes(self) -> None:
        report = contract.build_contract_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}

        masked = by_id["privacy_mask_beats_high_relevance"]

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(masked["packet"]["output_mode"], "silence")
        self.assertEqual(masked["packet"]["claim_permission"], "blocked")
        self.assertFalse(masked["packet"]["emitted"])
        self.assertIn("privacy_domain", masked["packet"]["masks_applied"])
        self.assertGreater(masked["packet"]["head_votes"][0]["score"], 0.95)
        self.assertEqual(report["metrics"]["masked_source_resurrection_count"], 0)

    def test_route_packets_are_handles_not_memory_facts(self) -> None:
        report = contract.build_contract_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}

        route = by_id["source_backed_reopenable_route"]["packet"]
        bounded = by_id["source_open_bounded_evidence"]["packet"]
        direction = by_id["source_thin_direction_only"]["packet"]
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(route["output_mode"], "reopenable_route")
        self.assertEqual(route["claim_permission"], "no_claim_before_reopen")
        self.assertTrue(route["source_handles"][0]["reopen_required"])
        self.assertTrue(route["contract"]["route_value_is_not_memory_fact"])

        self.assertEqual(bounded["output_mode"], "bounded_evidence")
        self.assertEqual(bounded["claim_permission"], "bounded_claim_allowed")
        self.assertEqual(direction["output_mode"], "direction_only")
        self.assertEqual(direction["claim_permission"], "no_claim_before_reopen")

        self.assertNotIn("PRIVATE_ROUTER_TEXT_SENTINEL", encoded)
        self.assertNotIn('"source_text"', encoded)
        self.assertIn("broad_attention_router_quality", report["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
