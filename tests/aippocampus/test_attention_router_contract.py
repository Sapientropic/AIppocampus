from __future__ import annotations

import json
import unittest

from aippocampus_runtime.navigation import attention_router_contract as contract


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

    def test_bounded_summary_is_route_not_evidence(self) -> None:
        report = contract.build_contract_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        summary = by_id["bounded_summary_as_route"]["packet"]

        self.assertEqual(summary["output_mode"], "bounded_summary_as_route")
        self.assertEqual(summary["action_grammar"], "direction_only")
        self.assertEqual(summary["claim_permission"], "no_claim_before_reopen")
        self.assertEqual(summary["bounded_summary"]["scope"], "project:AIppocampus")
        self.assertEqual(
            summary["bounded_summary"]["source_coverage"],
            ["discussion:#1106", "issue:#1107"],
        )
        self.assertTrue(summary["contract"]["bounded_summary_is_route_not_evidence"])
        self.assertEqual(report["metrics"]["summary_claim_ready_without_reopen_count"], 0)
        self.assertNotIn("PRIVATE_SUMMARY_TEXT_SENTINEL", encoded)
        self.assertNotIn('"summary_text"', encoded)

    def test_bounded_summary_falls_back_when_stale_or_weak(self) -> None:
        report = contract.build_contract_fixture_report()
        by_id = {case["case_id"]: case for case in report["cases"]}

        stale = by_id["stale_summary_falls_back_to_direction_only"]["packet"]

        self.assertEqual(stale["output_mode"], "direction_only")
        self.assertEqual(stale["action_grammar"], "direction_only")
        self.assertEqual(stale["claim_permission"], "no_claim_before_reopen")
        self.assertIn("summary_stale", stale["summary_fallback_reason_codes"])
        self.assertIn("summary_coverage_weak", stale["summary_fallback_reason_codes"])
        self.assertEqual(report["metrics"]["bounded_summary_fallback_count"], 1)

if __name__ == "__main__":
    unittest.main()
