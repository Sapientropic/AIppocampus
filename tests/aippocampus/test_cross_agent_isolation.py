from __future__ import annotations

import json
import unittest

from aippocampus_runtime.recall import cross_agent_isolation as isolation


class CrossAgentIsolationTests(unittest.TestCase):
    def test_fixture_blocks_cross_agent_paths_and_sanitizes_report(self) -> None:
        report = isolation.build_cross_agent_isolation_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["metrics"]["case_count"], 8)
        self.assertEqual(report["metrics"]["blocked_scope_hit_count"], 6)
        self.assertEqual(report["metrics"]["allowed_shared_scope_count"], 2)
        self.assertEqual(report["metrics"]["fast_path_bypass_prevented_count"], 6)
        self.assertEqual(report["red_lines"]["cross_scope_recall_leak_count"], 0)
        self.assertEqual(report["red_lines"]["cross_scope_route_leak_count"], 0)
        self.assertEqual(report["red_lines"]["cross_scope_evidence_leak_count"], 0)
        self.assertEqual(report["privacy_boundary"]["forbidden_marker_count"], 0)
        self.assertNotIn("AGENT_A_PRIVATE_SOURCE_SENTINEL", encoded)
        self.assertNotIn("raw_private_source_text", encoded)
        self.assertIn("enterprise_multi_tenant_authorization_complete", report["cannot_claim"])

        read_paths = report["metrics"]["read_path_counts"]
        self.assertEqual(read_paths["search_memory"], 2)
        self.assertEqual(read_paths["recall_deepen"], 2)
        self.assertEqual(read_paths["prompt_hot_path"], 1)
        self.assertEqual(read_paths["semantic_sidecar"], 1)
        self.assertEqual(read_paths["cached_summary"], 1)

    def test_blocked_cross_agent_case_returns_no_route_or_source_handles(self) -> None:
        result = isolation.evaluate_scope_read_case(
            {
                "case_id": "blocked_semantic_sidecar",
                "read_path": "semantic_sidecar",
                "request_scope": {
                    "provider": "codex",
                    "agent_id": "agent_b",
                    "project_scope_id": "project:AIppocampus",
                },
                "source_scope": {
                    "provider": "codex",
                    "agent_id": "agent_a",
                    "sharing": "private",
                },
                "marker_hash": isolation.isolation_hash("AGENT_A_PRIVATE_SOURCE_SENTINEL"),
                "would_match_without_scope_filter": True,
            }
        )

        self.assertEqual(result["decision"], "blocked")
        self.assertEqual(result["output_mode"], "ignore_or_blocked")
        self.assertEqual(result["claim_permission"], "blocked")
        self.assertEqual(result["source_handle_count"], 0)
        self.assertNotIn("route_id", result)
        self.assertNotIn("source_handles", result)
        self.assertEqual(result["blocked_scope_hit_count"], 1)
        self.assertEqual(result["fast_path_bypass_prevented_count"], 1)

    def test_declared_shared_scope_allows_reopenable_route_without_private_text(self) -> None:
        result = isolation.evaluate_scope_read_case(
            {
                "case_id": "allowed_shared_project_deepen",
                "read_path": "recall_deepen",
                "request_scope": {
                    "provider": "codex",
                    "agent_id": "agent_b",
                    "project_scope_id": "project:AIppocampus",
                },
                "source_scope": {
                    "provider": "codex",
                    "agent_id": "agent_a",
                    "sharing": "shared_project",
                    "shared_scope_ids": ["project:AIppocampus"],
                    "allowed_agent_ids": ["agent_a", "agent_b"],
                },
                "marker_hash": isolation.isolation_hash("SHARED_PROJECT_SYNTHETIC_MARKER"),
            }
        )

        self.assertEqual(result["decision"], "allowed")
        self.assertEqual(result["status"], "source_route")
        self.assertEqual(result["claim_permission"], "no_claim_before_reopen")
        self.assertEqual(result["source_handle_count"], 1)
        self.assertEqual(result["source_handles"][0]["scope_boundary"], "shared_project")
        self.assertEqual(result["cross_scope_route_leak_count"], 0)

    def test_simulated_filter_bypass_increments_red_lines(self) -> None:
        result = isolation.evaluate_scope_read_case(
            {
                "case_id": "leaky_cached_summary",
                "read_path": "cached_summary",
                "request_scope": {
                    "provider": "codex",
                    "agent_id": "agent_b",
                    "project_scope_id": "project:AIppocampus",
                },
                "source_scope": {
                    "provider": "codex",
                    "agent_id": "agent_a",
                    "sharing": "private",
                },
                "marker_hash": isolation.isolation_hash("AGENT_A_PRIVATE_SOURCE_SENTINEL"),
                "would_match_without_scope_filter": True,
                "simulate_filter_bypass": True,
            }
        )

        self.assertFalse(result["scope_allowed"])
        self.assertEqual(result["decision"], "leaked")
        self.assertEqual(result["cross_scope_recall_leak_count"], 1)
        self.assertEqual(result["cross_scope_route_leak_count"], 1)
        self.assertEqual(result["cross_scope_evidence_leak_count"], 1)

if __name__ == "__main__":
    unittest.main()
