from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
SMOKE = REPO_ROOT / "tools" / "aippocampus" / "smoke" / "smoke_recall_navigation_comparison.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops import (
    recall_navigation_comparison,  # noqa: E402
    recall_navigation_comparison_fixtures,  # noqa: E402
)


class RecallNavigationComparisonTests(unittest.TestCase):
    def test_fixture_report_compares_direct_hook_and_progressive_arms(self) -> None:
        report = recall_navigation_comparison_fixtures.fixture_recall_navigation_comparison()
        arms = report["aggregate"]["arms"]
        positive = report["cases_by_id"]["vague_magic_moment"]

        self.assertEqual(report["kind"], recall_navigation_comparison.COMPARISON_KIND)
        self.assertEqual(report["schema_version"], 3)
        self.assertEqual(set(arms), {"direct_search", "hook_only", "progressive_recall"})
        self.assertGreaterEqual(len(report["cases"]), 2)
        self.assertTrue(report["comparison_boundary"]["deterministic_proxy_only"])
        self.assertTrue(report["comparison_boundary"]["cannot_claim_live_cost_reduction"])

        direct = positive["arms"]["direct_search"]
        hook = positive["arms"]["hook_only"]
        progressive = positive["arms"]["progressive_recall"]

        self.assertTrue(direct["source_backed_success"])
        self.assertGreaterEqual(direct["manual_query_invention_count"], 2)
        self.assertFalse(hook["source_backed_success"])
        self.assertTrue(hook["scent_as_fact_violation"])
        self.assertTrue(progressive["source_backed_success"])
        self.assertTrue(progressive["route_actionable"])
        self.assertTrue(progressive["source_reopen_attempted"])
        self.assertTrue(progressive["source_reopen_follow_through"])
        self.assertEqual(progressive["manual_query_invention_count"], 0)
        self.assertEqual(progressive["selected_next_tool"], "recall_deepen")

    def test_stale_handle_case_is_rejected_without_leaking_handle_or_source_text(self) -> None:
        report = recall_navigation_comparison_fixtures.fixture_recall_navigation_comparison()
        stale = report["cases_by_id"]["stale_handle_fast_reject"]
        progressive = stale["arms"]["progressive_recall"]
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertFalse(progressive["source_backed_success"])
        self.assertTrue(progressive["source_reopen_attempted"])
        self.assertFalse(progressive["source_reopen_follow_through"])
        self.assertTrue(progressive["wrong_or_stale_handle"])
        self.assertEqual(progressive["error_code"], "stale_recall_handle")
        self.assertEqual(progressive["rejection_stage"], "deepen")
        self.assertNotIn("aippo-nav:", encoded)
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn("private magic wording", encoded)
        self.assertNotIn(str(REPO_ROOT), encoded)

    def test_aggregate_metrics_track_route_actionability_and_wrong_route_drag(self) -> None:
        report = recall_navigation_comparison_fixtures.fixture_recall_navigation_comparison()
        progressive = report["aggregate"]["arms"]["progressive_recall"]
        direct = report["aggregate"]["arms"]["direct_search"]
        hook = report["aggregate"]["arms"]["hook_only"]

        self.assertGreater(progressive["route_actionability_rate"], 0)
        self.assertGreater(progressive["source_reopen_follow_through_rate"], 0)
        self.assertLess(progressive["source_reopen_follow_through_rate"], 1)
        self.assertGreater(progressive["wrong_route_drag_rate"], 0)
        self.assertGreater(direct["avg_manual_query_invention_count"], 0)
        self.assertGreater(hook["scent_as_fact_violation_rate"], 0)
        self.assertIn("manual_query_invention_count", report["metric_notes"])
        self.assertIn("source_reopen_follow_through_rate", report["metric_notes"])
        self.assertIn("wrong_route_drag_rate", report["metric_notes"])

    def test_issue_201_readout_measures_deterministic_foreground_lift(self) -> None:
        report = recall_navigation_comparison_fixtures.fixture_recall_navigation_comparison()
        readout = report["issue_readouts"]["github_201"]

        self.assertTrue(readout["route_actionability_measured"])
        self.assertTrue(readout["source_reopen_follow_through_measured"])
        self.assertTrue(readout["foreground_lift_measured"])
        self.assertEqual(
            readout["default_foreground_first_turn_lift"],
            "measured_route_hint_under_semantic_timeout",
        )
        self.assertEqual(
            readout["default_foreground_second_turn_lift"],
            "measured_cache_reuse",
        )
        self.assertTrue(readout["semantic_timeout_but_route_available"])
        self.assertTrue(readout["source_boundary_preserved"])
        self.assertTrue(readout["foreground_source_reopen_follow_through_measured"])
        self.assertTrue(readout["foreground_source_reopen_follow_through"])
        self.assertEqual(readout["foreground_manual_query_invention_count"], 0)
        foreground = report["foreground_lift"]
        self.assertEqual(foreground["first_turn"]["decision"], "scent")
        self.assertTrue(foreground["first_turn"]["route_actionable"])
        self.assertEqual(
            foreground["first_turn"]["semantic_reuse_source"],
            "semantic_provider_timeout",
        )
        self.assertEqual(foreground["first_turn"]["evidence_count"], 0)
        self.assertEqual(foreground["second_turn"]["cache_status"], "hit")
        self.assertGreaterEqual(foreground["second_turn"]["cached_card_count"], 1)
        source_reopen = foreground["source_reopen_after_packet"]
        self.assertTrue(source_reopen["measured"])
        self.assertTrue(source_reopen["candidate_ref_consumed"])
        self.assertEqual(source_reopen["selected_ref_kind"], "thread_key")
        self.assertTrue(source_reopen["source_reopen_attempted"])
        self.assertTrue(source_reopen["source_reopen_follow_through"])
        self.assertEqual(source_reopen["manual_query_invention_count"], 0)
        self.assertTrue(source_reopen["source_boundary_preserved"])
        self.assertFalse(source_reopen["raw_source_snippet_serialized"])
        self.assertTrue(source_reopen["bounded_evidence_context_emitted"])
        self.assertEqual(source_reopen["bounded_evidence_card_count"], 1)
        self.assertTrue(source_reopen["bounded_evidence_separate_from_packet"])
        self.assertFalse(source_reopen["fresh_thread_packet_contains_raw_source_text"])
        self.assertEqual(readout["foreground_bounded_evidence_card_count"], 1)
        self.assertTrue(readout["foreground_bounded_evidence_context_measured"])
        readout_707 = report["issue_readouts"]["github_707"]
        self.assertTrue(readout_707["bounded_evidence_context_measured"])
        self.assertEqual(readout_707["bounded_evidence_card_count"], 1)
        self.assertFalse(readout_707["fresh_thread_packet_contains_raw_source_text"])
        self.assertEqual(readout_707["foreground_manual_query_invention_count"], 0)
        self.assertFalse(readout_707["closeout_eligible"])
        readout_786 = report["issue_readouts"]["github_786"]
        self.assertTrue(readout_786["trust_taxonomy_documented"])
        self.assertTrue(readout_786["bounded_evidence_changes_answer_without_manual_query"])
        self.assertTrue(readout_786["semantic_only_scent_not_factual_evidence"])
        self.assertEqual(readout_786["bounded_evidence_card_count"], 1)
        self.assertEqual(readout_786["foreground_manual_query_invention_count"], 0)
        self.assertFalse(readout_786["closeout_eligible"])
        self.assertIn("foreground_source_reopen_after_packet", report["metric_notes"])
        self.assertIn("bounded_evidence_context_after_packet", report["metric_notes"])
        self.assertIn("graded_packet_trust_taxonomy", report["metric_notes"])
        self.assertTrue(report["comparison_boundary"]["cannot_claim_live_default_foreground_lift"])
        self.assertFalse(readout["closeout_eligible"])

    def test_vague_cue_candidate_funnel_tracks_sentinel_source_rejoin_boundaries(self) -> None:
        report = recall_navigation_comparison_fixtures.fixture_recall_navigation_comparison()
        funnel = report["vague_cue_candidate_funnel"]
        metrics = funnel["metrics"]
        candidate_pool = funnel["candidate_pool"]
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(funnel["measured"])
        self.assertEqual(funnel["mode"], "deterministic_fixture")
        self.assertFalse(funnel["default_prefilter_enabled"])
        self.assertFalse(funnel["vector_prefilter_enabled"])
        self.assertTrue(funnel["source_reopen_required_for_evidence"])
        self.assertGreaterEqual(metrics["core_candidate_count"], 3)
        self.assertGreaterEqual(metrics["sentinel_candidate_count"], 2)
        self.assertGreater(metrics["verifier_pool_size"], metrics["core_candidate_count"])
        self.assertEqual(metrics["source_ref_rejoin_rate"], 1.0)
        self.assertEqual(metrics["sentinel_source_ref_coverage_rate"], 1.0)
        self.assertEqual(metrics["golden_association_rescued_by_sentinel_count"], 1)
        self.assertEqual(metrics["wrong_route_drag_from_sentinel_count"], 0)
        self.assertGreater(metrics["frontier_marker_helpfulness_rate"], 0)
        self.assertGreater(metrics["intersection_bridge_lift"], 0)
        self.assertGreaterEqual(len(candidate_pool["core"]), 3)
        self.assertGreaterEqual(len(candidate_pool["sentinel"]), 2)
        for candidate in candidate_pool["sentinel"]:
            self.assertTrue(candidate["why_included"])
            self.assertGreaterEqual(candidate["source_ref_count"], 1)
            self.assertTrue(candidate["source_joined"])
            self.assertFalse(candidate["promoted_to_evidence"])

        readout_201 = report["issue_readouts"]["github_201"]
        readout_281 = report["issue_readouts"]["github_281"]
        readout_309 = report["issue_readouts"]["github_309"]
        readout_248 = report["issue_readouts"]["github_248"]
        self.assertTrue(readout_201["vague_cue_candidate_funnel_measured"])
        self.assertTrue(readout_281["fresh_thread_candidate_funnel_measured"])
        self.assertEqual(readout_281["live_fresh_thread_quality"], "not_measured")
        self.assertTrue(readout_309["candidate_funnel_measured"])
        self.assertEqual(readout_309["golden_association_rescued_by_sentinel_count"], 1)
        self.assertEqual(readout_309["wrong_route_drag_from_sentinel_count"], 0)
        self.assertFalse(readout_309["default_vector_prefilter_enabled"])
        self.assertTrue(readout_248["source_ref_rejoin_measured"])
        self.assertEqual(readout_248["default_prefilter_adoption"], "not_enabled")
        self.assertEqual(readout_248["answer_quality_calibration"], "not_measured")
        self.assertFalse(readout_248["closeout_eligible"])
        self.assertTrue(report["comparison_boundary"]["candidate_pool_navigation_only"])
        self.assertTrue(report["comparison_boundary"]["cannot_claim_default_prefilter_safety"])
        self.assertIn("vague_cue_candidate_funnel", report["metric_notes"])
        self.assertNotIn("PRIVATE_OVERCLAIM_CASE", encoded)
        self.assertNotIn("C:\\", encoded)

    def test_cli_smoke_emits_json_report(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SMOKE), "--json"],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], recall_navigation_comparison.COMPARISON_KIND)
        self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
