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
    reopen_follow_through,  # noqa: E402
)


class RecallNavigationComparisonTests(unittest.TestCase):
    def test_fixture_report_compares_direct_hook_and_progressive_arms(self) -> None:
        report = recall_navigation_comparison_fixtures.fixture_recall_navigation_comparison()
        arms = report["aggregate"]["arms"]
        positive = report["cases_by_id"]["vague_magic_moment"]

        self.assertEqual(report["kind"], recall_navigation_comparison.COMPARISON_KIND)
        self.assertEqual(report["schema_version"], 4)
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
        for arm in (direct, hook, progressive):
            self.assertIn("route_handle_present", arm)
            self.assertIn("source_join_present", arm)
            self.assertIn("reopen_landed", arm)
            self.assertIn("source_reopen_follow_through_eligible", arm)
            self.assertIn("expected_fail_closed", arm)
            self.assertIn("failure_class", arm)

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
        self.assertEqual(progressive["source_reopen_follow_through_rate"], 1.0)
        self.assertEqual(progressive["source_reopen_fail_closed_count"], 1)
        self.assertEqual(
            progressive["source_reopen_failure_classes"],
            {"stale_handle_rejected_before_source_use": 1},
        )
        self.assertGreater(progressive["wrong_route_drag_rate"], 0)
        self.assertGreater(direct["avg_manual_query_invention_count"], 0)
        self.assertGreater(hook["scent_as_fact_violation_rate"], 0)
        self.assertIn("manual_query_invention_count", report["metric_notes"])
        self.assertIn("source_reopen_follow_through_rate", report["metric_notes"])
        self.assertIn("wrong_route_drag_rate", report["metric_notes"])

    def test_progressive_reopen_diagnostics_separate_landing_from_fail_closed(self) -> None:
        report = recall_navigation_comparison_fixtures.fixture_recall_navigation_comparison()
        positive = report["cases_by_id"]["vague_magic_moment"]["arms"]["progressive_recall"]
        stale = report["cases_by_id"]["stale_handle_fast_reject"]["arms"]["progressive_recall"]

        self.assertTrue(positive["route_handle_present"])
        self.assertTrue(positive["source_join_present"])
        self.assertTrue(positive["source_reopen_attempted"])
        self.assertTrue(positive["reopen_landed"])
        self.assertTrue(positive["source_reopen_follow_through_eligible"])
        self.assertEqual(positive["failure_class"], "")

        self.assertTrue(stale["route_handle_present"])
        self.assertTrue(stale["source_join_present"])
        self.assertTrue(stale["source_reopen_attempted"])
        self.assertFalse(stale["reopen_landed"])
        self.assertFalse(stale["source_reopen_follow_through"])
        self.assertFalse(stale["source_reopen_follow_through_eligible"])
        self.assertTrue(stale["expected_fail_closed"])
        self.assertEqual(stale["failure_class"], "stale_handle_rejected_before_source_use")

    def test_blocked_reopen_diagnostic_is_expected_fail_closed(self) -> None:
        diagnostic = reopen_follow_through.reopen_diagnostics(
            route_handle_present=True,
            source_join_present=True,
            source_reopen_attempted=True,
            success=False,
            error_code="continuity_domain_blocked",
            source_refs=[],
        )

        self.assertFalse(diagnostic["reopen_landed"])
        self.assertFalse(diagnostic["source_reopen_follow_through_eligible"])
        self.assertTrue(diagnostic["expected_fail_closed"])
        self.assertEqual(
            diagnostic["failure_class"],
            "blocked_handle_rejected_before_source_use",
        )

    def test_issue_201_readout_measures_deterministic_foreground_lift(self) -> None:
        report = recall_navigation_comparison_fixtures.fixture_recall_navigation_comparison()
        readout = report["issue_readouts"]["github_201"]

        self.assertTrue(readout["route_actionability_measured"])
        self.assertTrue(readout["source_reopen_follow_through_measured"])
        self.assertEqual(readout["source_reopen_follow_through_eligible_count"], 3)
        self.assertEqual(readout["source_reopen_fail_closed_count"], 1)
        self.assertEqual(
            readout["source_reopen_failure_classes"],
            {"stale_handle_rejected_before_source_use": 1},
        )
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
        self.assertTrue(readout_786["action_grammar_documented"])
        self.assertTrue(readout_786["action_grammar_fixture_measured"])
        self.assertTrue(readout_786["bounded_evidence_changes_answer_without_manual_query"])
        self.assertTrue(readout_786["semantic_only_scent_not_factual_evidence"])
        self.assertEqual(
            readout_786["same_thread_issue_comment_route_quality"],
            "public_fixture_precise_route",
        )
        self.assertEqual(readout_786["bounded_evidence_card_count"], 1)
        self.assertEqual(readout_786["foreground_manual_query_invention_count"], 0)
        self.assertFalse(readout_786["closeout_eligible"])
        self.assertIn("foreground_source_reopen_after_packet", report["metric_notes"])
        self.assertIn("bounded_evidence_context_after_packet", report["metric_notes"])
        self.assertIn("graded_packet_trust_taxonomy", report["metric_notes"])
        self.assertIn("packet_action_grammar", report["metric_notes"])
        self.assertTrue(report["comparison_boundary"]["cannot_claim_live_default_foreground_lift"])
        self.assertFalse(readout["closeout_eligible"])

    def test_text_report_keeps_reopen_follow_through_denominator_visible(self) -> None:
        report = recall_navigation_comparison_fixtures.fixture_recall_navigation_comparison()
        text = recall_navigation_comparison.render_text(report)

        self.assertIn(
            "source reopen follow-through 1.0 (3/3 eligible, 1 fail-closed)",
            text,
        )

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

    def test_issue_797_presence_first_fixture_matrix_checks_behavior_not_fields(self) -> None:
        report = recall_navigation_comparison_fixtures.fixture_recall_navigation_comparison()
        matrix = report["presence_first_fixture_matrix"]
        readout = report["issue_readouts"]["github_797"]
        encoded = json.dumps(matrix, ensure_ascii=False, sort_keys=True)

        self.assertTrue(matrix["measured"])
        self.assertEqual(matrix["mode"], "deterministic_fixture")
        self.assertEqual(matrix["family_count"], 6)
        self.assertTrue(matrix["public_safe"])
        self.assertTrue(matrix["checks_behavior_not_just_fields"])
        self.assertTrue(matrix["old_everything_is_scent_baseline_fails"])
        self.assertGreaterEqual(matrix["old_posture_failure_count"], 1)
        self.assertEqual(matrix["privacy"]["raw_source_window_serialized"], False)
        self.assertEqual(matrix["privacy"]["local_paths_serialized"], False)

        cases = matrix["cases_by_family"]
        self.assertEqual(
            set(cases),
            {
                "memory_atmosphere",
                "working_continuity_brief",
                "bounded_evidence",
                "source_open",
                "source_court",
                "first_use_ten_minute_path",
            },
        )

        atmosphere = cases["memory_atmosphere"]
        self.assertEqual(atmosphere["agent_behavior"], "quietly_orients_without_claim")
        self.assertTrue(atmosphere["current_posture_pass"])
        self.assertFalse(atmosphere["makes_factual_claim"])

        continuity = cases["working_continuity_brief"]
        self.assertEqual(continuity["agent_behavior"], "uses_reopenable_route_without_manual_grep")
        self.assertEqual(continuity["manual_query_invention_count"], 0)
        self.assertTrue(continuity["next_action_changed"])

        bounded = cases["bounded_evidence"]
        self.assertEqual(bounded["agent_behavior"], "answers_within_scope")
        self.assertTrue(bounded["answer_changed_by_memory"])
        self.assertFalse(bounded["manual_query_required"])

        source_open = cases["source_open"]
        self.assertEqual(source_open["agent_behavior"], "uses_scoped_exact_wording")
        self.assertTrue(source_open["exact_wording_allowed"])
        self.assertFalse(source_open["requires_reopen_for_exact_wording"])

        source_court = cases["source_court"]
        self.assertEqual(source_court["agent_behavior"], "escalates_or_abstains")
        self.assertEqual(source_court["manual_query_invention_count"], 0)
        self.assertTrue(source_court["blocked_route_does_not_shape_answer"])
        self.assertTrue(source_court["requires_reopen_or_abstain"])

        first_use = cases["first_use_ten_minute_path"]
        self.assertEqual(first_use["agent_behavior"], "explains_recovered_continuity")
        self.assertTrue(first_use["feels_like_found_prior_context"])
        self.assertFalse(first_use["feels_like_governance_console"])

        self.assertTrue(readout["presence_fixture_matrix_measured"])
        self.assertTrue(readout["all_fixture_families_present"])
        self.assertTrue(readout["behavior_assertions_present"])
        self.assertTrue(readout["old_posture_failure_measured"])
        self.assertTrue(readout["source_court_escalation_measured"])
        self.assertTrue(readout["closeout_eligible"])
        self.assertIn("presence_first_fixture_matrix", report["metric_notes"])
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn("C:\\", encoded)

    def test_issue_786_same_thread_issue_comment_route_quality_smoke(self) -> None:
        report = recall_navigation_comparison_fixtures.fixture_recall_navigation_comparison()
        self.assertIn("same_thread_issue_comment_route_quality", report)
        route_quality = report["same_thread_issue_comment_route_quality"]
        readout = report["issue_readouts"]["github_786"]
        encoded = json.dumps(route_quality, ensure_ascii=False, sort_keys=True)

        self.assertTrue(route_quality["measured"])
        self.assertEqual(route_quality["mode"], "public_fixture")
        self.assertEqual(route_quality["agent_behavior"], "uses_precise_current_thread_route")
        self.assertEqual(route_quality["route"]["issue_number"], 786)
        self.assertEqual(route_quality["route"]["parent_issue_number"], 791)
        self.assertEqual(route_quality["route"]["action_grammar"], "reopenable_route")
        self.assertEqual(route_quality["route"]["manual_query_invention_count"], 0)
        self.assertTrue(route_quality["route"]["source_refs_available"])
        self.assertTrue(route_quality["precision"]["issue_number_and_topic_present"])
        self.assertTrue(route_quality["precision"]["parent_relation_present"])
        self.assertTrue(route_quality["precision"]["comment_context_present"])
        self.assertTrue(route_quality["precision"]["broad_topic_scent_only_fails"])
        self.assertFalse(route_quality["source_boundary"]["promoted_to_evidence"])
        self.assertTrue(route_quality["source_boundary"]["source_reopen_required"])
        self.assertFalse(route_quality["privacy"]["raw_comment_body_serialized"])
        self.assertFalse(route_quality["privacy"]["local_paths_serialized"])

        self.assertTrue(readout["same_thread_issue_comment_route_quality_measured"])
        self.assertEqual(
            readout["same_thread_issue_comment_route_quality"],
            "public_fixture_precise_route",
        )
        self.assertEqual(readout["same_thread_issue_comment_manual_query_count"], 0)
        self.assertEqual(readout["live_semantic_reopen_quality"], "not_measured")
        self.assertFalse(readout["closeout_eligible"])
        self.assertIn("same_thread_issue_comment_route_quality", report["metric_notes"])
        self.assertTrue(
            report["comparison_boundary"][
                "cannot_claim_live_same_thread_issue_comment_route_quality"
            ]
        )
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn("C:\\", encoded)
        self.assertNotIn(str(REPO_ROOT), encoded)

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
