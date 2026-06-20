from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime.ops import successor_evidence
from aippocampus_runtime.ops.successor_evidence import (
    SUCCESSOR_ISSUE_STATE_MANIFEST,
    SUCCESSOR_ISSUES,
    build_successor_evidence_sweep_report,
    load_github_successor_issue_state,
)


class SuccessorEvidenceTests(unittest.TestCase):
    def test_sweep_covers_open_successors_without_default_promotion(self) -> None:
        report = build_successor_evidence_sweep_report()

        self.assertTrue(report["ok"])
        self.assertEqual(report["covered_issue_numbers"], sorted(SUCCESSOR_ISSUES))
        self.assertEqual(report["coverage"]["missing_open_successor_issue_numbers"], [])
        self.assertEqual(report["coverage"]["stale_closed_duplicate_issue_numbers"], [])
        self.assertGreaterEqual(report["coverage"]["closed_duplicate_redirects_recorded_count"], 3)
        self.assertFalse(report["coverage"]["hard_coded_inventory_only"])
        self.assertEqual(report["public_safety"]["raw_private_text_leak_count"], 0)
        self.assertIn("foreground_default_adoption", report["cannot_claim"])

        for row in report["issues"]:
            self.assertTrue(row["closeout_allowed"])
            self.assertFalse(row["default_or_live_claim_allowed"])
            self.assertFalse(row["metrics"]["default_adoption_allowed"])
            self.assertEqual(row["metrics"]["raw_private_text_leak_count"], 0)

    def test_cli_report_separates_manifest_closeout_from_issue_actions(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        completed = subprocess.run(
            [
                sys.executable,
                str(repo_root / "benchmarks" / "aippocampus" / "benchmark_successor_evidence_sweep.py"),
                "--json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(completed.stdout)

        self.assertEqual(report["coverage"]["live_issue_scope"], "manifest_only")
        self.assertFalse(report["coverage"]["github_state_checked"])
        first = report["issues"][0]
        self.assertTrue(first["manifest_closeout_allowed"])
        self.assertFalse(first["live_state_checked"])
        self.assertFalse(first["issue_closeout_action_allowed"])
        self.assertEqual(first["next_action"], "verify_live_issue_before_closeout")
        self.assertEqual(
            first["command"],
            f"gh issue view {first['issue']} --json state,body,comments",
        )
        self.assertEqual(
            report["issue_actions"][0]["next_action"],
            "verify_live_issue_before_closeout",
        )
        self.assertTrue(
            report["closeout_action_boundary"][
                "manifest_closeout_allowed_is_not_live_issue_closeout"
            ]
        )

    def test_fixture_state_catches_new_open_successor_missing_from_sweep(self) -> None:
        issue_state = {
            number: dict(row)
            for number, row in SUCCESSOR_ISSUE_STATE_MANIFEST.items()
        }
        issue_state[1999] = {
            "state": "open",
            "title": "new live successor missing from local inventory",
            "parent": 1918,
            "parent_relationship_source": "native_parent_graph",
        }

        report = build_successor_evidence_sweep_report(issue_state=issue_state)

        self.assertFalse(report["ok"])
        self.assertIn(1999, report["coverage"]["missing_open_successor_issue_numbers"])
        self.assertNotIn(1999, report["covered_issue_numbers"])

    def test_nested_execution_children_do_not_fail_top_level_successor_coverage(self) -> None:
        issue_state = {
            number: dict(row)
            for number, row in SUCCESSOR_ISSUE_STATE_MANIFEST.items()
        }
        issue_state[1978] = {
            "state": "open",
            "title": "nested semantic outcome child",
            "parent": 1960,
            "parent_relationship_source": "native_parent_graph",
        }
        issue_state[1979] = {
            "state": "open",
            "title": "nested discussion atlas child",
            "parent": 1961,
            "parent_relationship_source": "native_parent_graph",
        }
        issue_state[1980] = {
            "state": "open",
            "title": "nested successor inventory child",
            "parent": 1958,
            "parent_relationship_source": "native_parent_graph",
        }

        report = build_successor_evidence_sweep_report(
            issue_state=issue_state,
            github_state_checked=True,
        )

        self.assertTrue(report["ok"])
        self.assertEqual(report["coverage"]["missing_top_level_successor_issue_numbers"], [])
        self.assertEqual(report["coverage"]["nested_child_missing_parent_metric_numbers"], [])
        self.assertEqual(report["coverage"]["nested_child_issue_numbers"], [1978, 1979, 1980])
        self.assertNotIn(1978, report["covered_issue_numbers"])
        self.assertTrue(report["coverage"]["native_parent_graph_checked"])
        self.assertEqual(report["coverage"]["live_issue_scope"], "native_parent_graph")

    def test_live_github_state_falls_back_when_native_parent_graph_unavailable(self) -> None:
        issue_rows = [
            {
                "number": 1981,
                "state": "OPEN",
                "title": "Validate E2E50 private/local field behavior",
                "body": "Parent: #1918",
                "labels": [],
            }
        ]

        def fake_check_output(command, **kwargs):
            if command[:3] == ["gh", "api", "graphql"]:
                raise subprocess.CalledProcessError(1, command, output="transient")
            return json.dumps(issue_rows)

        with patch(
            "aippocampus_runtime.ops.successor_evidence.subprocess.check_output",
            side_effect=fake_check_output,
        ):
            state = load_github_successor_issue_state(limit=1)

        self.assertEqual(state[1981]["parent"], 1918)
        self.assertEqual(state[1981]["parent_relationship_source"], "body_parent_fallback")
        self.assertIsNone(state[1981]["native_parent"])

    def test_closed_duplicate_rows_are_redirected_not_active_coverage(self) -> None:
        report = build_successor_evidence_sweep_report()

        self.assertNotIn(1938, report["covered_issue_numbers"])
        self.assertNotIn(1939, report["covered_issue_numbers"])
        self.assertNotIn(1940, report["covered_issue_numbers"])
        redirects = {
            row["issue"]: row["redirect"]
            for row in report["excluded_closed_duplicates"]
        }
        self.assertEqual(redirects[1938], 1941)
        self.assertEqual(redirects[1939], 1942)
        self.assertEqual(redirects[1940], 1943)

    def test_new_successors_have_specific_acceptance_metrics(self) -> None:
        report = build_successor_evidence_sweep_report()
        by_issue = {row["issue"]: row for row in report["issues"]}

        self.assertEqual(report["coverage"]["generic_placeholder_metric_row_count"], 0)
        self.assertIn("foreground_hint_usefulness_delta", by_issue[1952]["metrics"])
        self.assertIn("duplicate_work_reduced_count", by_issue[1953]["metrics"])
        self.assertIn("trace_backed_observed_use_count", by_issue[1954]["metrics"])
        self.assertGreaterEqual(by_issue[1955]["metrics"]["surface_count_compared"], 4)
        self.assertIn("glued_route_helpful_selection_count", by_issue[1956]["metrics"])
        self.assertEqual(by_issue[1957]["metrics"]["fixture_only_case_count"], 0)
        self.assertFalse(by_issue[1958]["metrics"]["hard_coded_inventory_only"])
        self.assertTrue(by_issue[1959]["metrics"]["observed_agent_behavior"])
        self.assertFalse(by_issue[1959]["metrics"]["runtime_policy_adoption_gate_ok"])
        self.assertIn("semantic_guidance_surface_count", by_issue[1960]["metrics"])
        self.assertIn("missing_row_detected_count", by_issue[1961]["metrics"])
        self.assertIn(
            "bounded_evidence_after_semantic_reopen_count",
            by_issue[1962]["metrics"],
        )
        self.assertIn("large_association_term_count", by_issue[1963]["metrics"])
        self.assertTrue(by_issue[1964]["metrics"]["source_addressable_card_rate_reported"])
        self.assertIn("fixture_replay_complete_count", by_issue[1965]["metrics"])
        self.assertIn("runtime_line_signal_producer_present", by_issue[1965]["metrics"])
        self.assertIn("real_foreground_packet_path_count", by_issue[1966]["metrics"])
        self.assertIn("active_arm_delta_vs_fts_only", by_issue[1967]["metrics"])
        self.assertIn("aippocampus_delta_vs_fresh_missing_context", by_issue[1968]["metrics"])
        self.assertIn("public_cohort_case_count", by_issue[1969]["metrics"])
        self.assertIn("attention_promoted_family_count", by_issue[1970]["metrics"])
        self.assertIn("live_or_sanitized_replay_case_count", by_issue[1971]["metrics"])
        self.assertIn("public_currentness_case_count", by_issue[1972]["metrics"])
        self.assertIn("multimodal_replay_case_count", by_issue[1973]["metrics"])
        self.assertIn("conversational_media_replay_case_count", by_issue[1974]["metrics"])
        self.assertIn("niah_observed_answerer_case_count", by_issue[1975]["metrics"])
        self.assertIn("governed_runtime_replay_case_count", by_issue[1976]["metrics"])
        self.assertIn("long_thread_replay_case_count", by_issue[1977]["metrics"])
        self.assertIn("field_case_count", by_issue[1981]["metrics"])
        self.assertIn("observed_guidance_outcome_case_count", by_issue[1960]["metrics"])
        self.assertIn("live_check_depth", by_issue[1961]["metrics"])
        self.assertIn("live_issue_scope", by_issue[1958]["metrics"])

    def test_macro_topology_successors_have_load_bearing_and_no_help_metrics(self) -> None:
        report = build_successor_evidence_sweep_report()
        macro_rows = [row for row in report["issues"] if row["track"] == "macro_topology"]

        self.assertGreaterEqual(len(macro_rows), 4)
        for row in macro_rows:
            metrics = row["metrics"]
            self.assertGreaterEqual(metrics["real_or_replay_case_count"], 5)
            self.assertGreaterEqual(metrics["macro_helpful_route_change_count"], 1)
            self.assertGreaterEqual(metrics["topology_helpful_action_change_count"], 1)
            self.assertGreaterEqual(metrics["macro_no_help_correctly_ignored_count"], 1)
            self.assertEqual(metrics["authority_upgrade_violation_count"], 0)
            self.assertFalse(metrics["live_product_lift_claimed"])

    def test_macro_replay_successors_use_runtime_replay_metrics(self) -> None:
        report = build_successor_evidence_sweep_report()
        by_issue = {row["issue"]: row for row in report["issues"]}
        macro_metrics = by_issue[1965]["metrics"]
        topology_metrics = by_issue[1966]["metrics"]

        self.assertGreaterEqual(macro_metrics["macro_replay_case_count"], 4)
        self.assertEqual(macro_metrics["macro_fixture_only_case_count"], 1)
        self.assertGreaterEqual(macro_metrics["fixture_replay_complete_count"], 1)
        self.assertEqual(macro_metrics["real_producer_complete_count"], 0)
        self.assertFalse(macro_metrics["runtime_line_signal_producer_present"])
        self.assertEqual(macro_metrics["runtime_macro_state_write_count"], 0)
        self.assertGreaterEqual(macro_metrics["macro_helpful_route_change_count"], 1)
        self.assertGreaterEqual(
            macro_metrics["macro_helpful_deepen_or_recheck_change_count"],
            1,
        )
        self.assertGreaterEqual(
            macro_metrics["macro_no_help_correctly_ignored_count"],
            3,
        )
        self.assertEqual(macro_metrics["default_fixture_hexagram_rejected_count"], 1)
        self.assertEqual(macro_metrics["false_positive_or_noise_count"], 0)
        self.assertEqual(macro_metrics["authority_upgrade_violation_count"], 0)
        self.assertFalse(macro_metrics["live_product_lift_claimed"])

        self.assertGreaterEqual(topology_metrics["topology_replay_case_count"], 6)
        self.assertGreaterEqual(topology_metrics["real_foreground_packet_path_count"], 1)
        self.assertGreaterEqual(
            topology_metrics["topology_helpful_action_change_count"],
            4,
        )
        self.assertGreaterEqual(topology_metrics["topology_safety_catch_count"], 4)
        self.assertEqual(topology_metrics["healthy_packet_unchanged_count"], 1)
        self.assertEqual(topology_metrics["agency_suppression_relief_count"], 1)
        self.assertEqual(topology_metrics["annotation_or_vocabulary_blocked_count"], 1)
        self.assertEqual(topology_metrics["false_positive_or_overfilter_count"], 0)
        self.assertEqual(topology_metrics["foreground_noise_added_count"], 0)
        self.assertEqual(topology_metrics["authority_upgrade_violation_count"], 0)
        self.assertFalse(topology_metrics["live_product_lift_claimed"])

    def test_benchmark_public_cohort_successors_use_runtime_reports(self) -> None:
        report = build_successor_evidence_sweep_report()
        by_issue = {row["issue"]: row for row in report["issues"]}
        field = by_issue[1967]["metrics"]
        context_loss = by_issue[1968]["metrics"]
        agent_loop = by_issue[1969]["metrics"]

        self.assertGreaterEqual(field["public_or_replay_case_count"], 8)
        self.assertGreaterEqual(field["synthetic_fixture_case_count"], 5)
        self.assertGreater(field["active_arm_delta_vs_fts_only"], 0)
        self.assertGreater(field["active_arm_delta_vs_summary_first"], 0)
        self.assertGreater(field["active_arm_delta_vs_hook_only"], 0)
        self.assertEqual(field["privacy_report_leakage_rate"], 0.0)
        self.assertTrue(field["quality_gate_ok"])
        self.assertFalse(field["live_product_lift_claimed"])

        self.assertGreaterEqual(context_loss["public_or_replay_case_count"], 6)
        self.assertGreaterEqual(context_loss["heldout_case_count"], 2)
        self.assertEqual(context_loss["private_aggregate_case_count"], 0)
        self.assertEqual(context_loss["live_host_evidence_count"], 0)
        self.assertEqual(context_loss["source_reopen_success_rate"], 1.0)
        self.assertGreater(
            context_loss["aippocampus_delta_vs_fresh_missing_context"],
            0,
        )
        self.assertTrue(context_loss["quality_gate_ok"])
        self.assertFalse(context_loss["public_quality_gate_ok"])
        self.assertEqual(context_loss["raw_private_text_leak_count"], 0)

        self.assertEqual(agent_loop["public_cohort_case_count"], 180)
        self.assertEqual(agent_loop["heldout_case_count"], 45)
        self.assertEqual(agent_loop["contract_fixture_case_count"], 8)
        self.assertTrue(agent_loop["usefulness_gate_ok"])
        self.assertTrue(agent_loop["attention_cost_ok"])
        self.assertTrue(agent_loop["quality_gate_ok"])
        self.assertEqual(agent_loop["generic_hint_count"], 0)
        self.assertEqual(agent_loop["route_label_collision_count"], 0)
        self.assertEqual(agent_loop["foreground_noise_added_count"], 0)
        self.assertEqual(agent_loop["attention_cost_overrun_count"], 0)
        self.assertEqual(agent_loop["raw_private_text_leak_count"], 0)
        self.assertFalse(agent_loop["live_product_lift_claimed"])

    def test_latest_successors_use_runtime_reports_and_keep_claim_boundaries(self) -> None:
        report = build_successor_evidence_sweep_report()
        by_issue = {row["issue"]: row for row in report["issues"]}
        attention = by_issue[1970]["metrics"]
        provider = by_issue[1971]["metrics"]
        h1h2 = by_issue[1972]["metrics"]

        self.assertTrue(attention["public_cohort_profile_ok"])
        self.assertTrue(attention["contract_smoke_profile_ok"])
        self.assertEqual(attention["public_cohort_case_count"], 270)
        self.assertEqual(attention["holdout_case_count"], 90)
        self.assertTrue(attention["public_quality_gate_ok"])
        self.assertTrue(attention["explicit_agent_recall_auto_gate_ok"])
        self.assertEqual(attention["attention_promoted_family_count"], 1)
        self.assertGreaterEqual(attention["remaining_candidate_family_count"], 1)
        self.assertTrue(attention["attention_removed_from_selected_candidates"])
        self.assertEqual(attention["quality_false_planning_drift_count"], 0)
        self.assertFalse(attention["default_foreground_hook_lift_claimed"])
        self.assertFalse(attention["live_product_lift_claimed"])

        self.assertTrue(provider["sanitized_replay_ok"])
        self.assertTrue(provider["synthetic_kit_passed"])
        self.assertGreaterEqual(provider["real_or_dogfood_provider_count"], 2)
        self.assertGreaterEqual(provider["synthetic_provider_count"], 5)
        self.assertGreaterEqual(provider["live_or_sanitized_replay_case_count"], 6)
        self.assertGreaterEqual(provider["cross_provider_route_success_count"], 3)
        self.assertGreaterEqual(provider["cross_provider_source_reopen_success_count"], 3)
        self.assertGreaterEqual(provider["foreground_action_helpful_count"], 1)
        self.assertEqual(provider["copied_summary_promoted_to_source_count"], 0)
        self.assertEqual(provider["mcp_blob_source_truth_violation_count"], 0)
        self.assertEqual(provider["injected_content_durable_memory_count"], 0)
        self.assertGreaterEqual(provider["missing_source_ref_affordance_count"], 1)
        self.assertEqual(provider["raw_provider_log_leak_count"], 0)
        self.assertEqual(provider["local_path_or_settings_path_leak_count"], 0)
        self.assertEqual(provider["secret_leak_count"], 0)
        self.assertFalse(provider["all_client_drop_in_support_claimed"])
        self.assertFalse(provider["broad_private_history_quality_claimed"])

        self.assertEqual(h1h2["public_currentness_case_count"], 4)
        self.assertEqual(h1h2["synthetic_contract_case_count"], 12)
        self.assertEqual(h1h2["superseded_currentness_case_count"], 3)
        self.assertEqual(h1h2["current_source_selected_count"], 2)
        self.assertEqual(h1h2["stale_as_current_count"], 1)
        self.assertEqual(h1h2["wrong_source_evidence_count"], 1)
        self.assertEqual(h1h2["unsupported_as_fact_count"], 1)
        self.assertEqual(h1h2["confabulation_count"], 0)
        self.assertEqual(h1h2["source_reopen_before_evidence_rate"], 1.0)
        self.assertTrue(h1h2["public_quality_gate_ok"])
        self.assertFalse(h1h2["full_p1_matrix_claimed"])
        self.assertTrue(h1h2["locomo_supersession_boundary_visible"])
        self.assertEqual(
            h1h2["locomo_supersession_unsupported_reason"],
            "locomo_has_dialogue_order_but_no_reliable_supersession_labels",
        )
        self.assertFalse(h1h2["private_real_history_quality_claimed"])

    def test_multimodal_and_governed_runtime_successors_use_replay_metrics(self) -> None:
        report = build_successor_evidence_sweep_report()
        by_issue = {row["issue"]: row for row in report["issues"]}
        corpus = by_issue[1973]["metrics"]
        ingest = by_issue[1974]["metrics"]
        niah = by_issue[1975]["metrics"]
        knowledge = by_issue[1976]["metrics"]

        self.assertTrue(corpus["source_open_replay_ok"])
        self.assertEqual(corpus["multimodal_replay_case_count"], 6)
        self.assertEqual(corpus["deterministic_fixture_only_case_count"], 4)
        self.assertEqual(corpus["raw_media_source_open_success_rate"], 1.0)
        self.assertEqual(corpus["visual_or_document_claim_source_open_rate"], 1.0)
        self.assertEqual(corpus["caption_shortcut_violation_count"], 0)
        self.assertEqual(corpus["unsupported_visual_claim_rate"], 0.0)
        self.assertEqual(corpus["stale_or_weaker_source_selected_rate"], 0.0)
        self.assertEqual(corpus["cross_modal_join_success_rate"], 1.0)
        self.assertEqual(corpus["abstention_accuracy"], 1.0)
        self.assertEqual(corpus["provider_unavailable_blocker_count"], 1)
        self.assertEqual(corpus["provider_blocked_status"], "blocked")
        self.assertEqual(corpus["raw_media_bytes_public_reported_count"], 0)
        self.assertEqual(corpus["absolute_path_leak_count"], 0)
        self.assertFalse(corpus["live_product_lift_claimed"])

        self.assertTrue(ingest["source_open_replay_ok"])
        self.assertEqual(ingest["conversational_media_replay_case_count"], 7)
        self.assertEqual(ingest["fixture_boolean_only_case_count"], 6)
        self.assertEqual(ingest["conversation_turn_source_open_rate"], 1.0)
        self.assertEqual(ingest["attached_media_source_open_rate"], 1.0)
        self.assertEqual(ingest["personal_reference_resolution_rate"], 1.0)
        self.assertEqual(ingest["text_hint_as_visual_proof_violation_count"], 0)
        self.assertEqual(ingest["stale_label_correction_success_rate"], 1.0)
        self.assertEqual(ingest["hidden_durable_write_count"], 0)
        self.assertEqual(ingest["background_media_access_denied_count"], 1)
        self.assertEqual(ingest["unsupported_visual_claim_rate"], 0.0)
        self.assertEqual(ingest["provider_unavailable_blocker_count"], 1)
        self.assertEqual(ingest["raw_media_bytes_public_reported_count"], 0)
        self.assertEqual(ingest["absolute_path_leak_count"], 0)
        self.assertFalse(ingest["live_product_lift_claimed"])

        self.assertTrue(niah["answerer_replay_ok"])
        self.assertEqual(niah["niah_observed_answerer_case_count"], 6)
        self.assertEqual(niah["deterministic_fixture_only_case_count"], 4)
        self.assertEqual(niah["pool_ground_truth_coverage_rate"], 1.0)
        self.assertEqual(niah["answer_correctness"], 1.0)
        self.assertEqual(niah["source_selection_accuracy"], 1.0)
        self.assertEqual(niah["source_anchor_citation_accuracy"], 1.0)
        self.assertEqual(niah["stale_or_conflicting_distractor_selection_rate"], 0.0)
        self.assertEqual(niah["ambiguous_currentness_reopen_or_abstain_rate"], 1.0)
        self.assertEqual(niah["unsupported_claim_rate"], 0.0)
        self.assertEqual(niah["abstention_accuracy"], 1.0)
        self.assertEqual(niah["prompt_ground_truth_leak_count"], 0)
        self.assertFalse(niah["retrieval_quality_claimed"])
        self.assertEqual(niah["raw_media_bytes_public_reported_count"], 0)
        self.assertEqual(niah["absolute_path_leak_count"], 0)

        self.assertTrue(knowledge["governed_runtime_replay_ok"])
        self.assertEqual(knowledge["governed_runtime_replay_case_count"], 8)
        self.assertEqual(knowledge["contract_smoke_only_case_count"], 13)
        self.assertEqual(knowledge["knowledge_runtime_caller_count"], 1)
        self.assertEqual(knowledge["source_reopen_required_violation_count"], 0)
        self.assertEqual(knowledge["bounded_answer_with_cited_spans_count"], 1)
        self.assertEqual(knowledge["missing_context_question_rate"], 1.0)
        self.assertEqual(knowledge["stale_source_harm_rate"], 0.0)
        self.assertEqual(knowledge["authority_override_rate"], 0.0)
        self.assertEqual(knowledge["conflict_human_review_rate"], 1.0)
        self.assertEqual(knowledge["privacy_partition_leak_rate"], 0.0)
        self.assertEqual(knowledge["external_tool_source_text_transfer_violation_count"], 0)
        self.assertEqual(knowledge["unsupported_claim_rate"], 0.0)
        self.assertEqual(knowledge["default_personal_recall_ceremony_regression_count"], 0)
        self.assertEqual(knowledge["raw_source_text_public_reported_count"], 0)
        self.assertEqual(knowledge["absolute_path_leak_count"], 0)
        self.assertFalse(knowledge["live_high_risk_answer_coverage_claimed"])

    def test_segmented_merge_and_semantic_outcome_successors_use_runtime_metrics(self) -> None:
        report = build_successor_evidence_sweep_report()
        by_issue = {row["issue"]: row for row in report["issues"]}
        segmented = by_issue[1977]["metrics"]
        semantic = by_issue[1960]["metrics"]

        self.assertTrue(segmented["segmented_merge_replay_ok"])
        self.assertEqual(segmented["synthetic_policy_fixture_case_count"], 5)
        self.assertGreaterEqual(segmented["long_thread_replay_case_count"], 8)
        self.assertEqual(segmented["monolithic_target_hit_rate"], 1.0)
        self.assertEqual(segmented["full_fanout_target_hit_rate"], 1.0)
        self.assertLess(
            segmented["budgeted_fanout_target_hit_rate"],
            segmented["full_fanout_target_hit_rate"],
        )
        self.assertEqual(segmented["answer_support_after_source_reopen_rate"], 1.0)
        self.assertGreater(segmented["early_segment_miss_count"], 0)
        self.assertGreater(segmented["middle_segment_miss_count"], 0)
        self.assertEqual(segmented["cross_boundary_pairing_success_rate"], 1.0)
        self.assertEqual(segmented["stale_superseded_false_promotion_count"], 0)
        self.assertEqual(segmented["duplicate_recap_overpromotion_count"], 0)
        self.assertTrue(segmented["replay_source_open_validation_separate"])
        self.assertTrue(segmented["synthetic_fixture_separate_from_replay"])
        self.assertTrue(segmented["generated_soak_separate_from_replay"])
        self.assertTrue(segmented["budgeted_fanout_is_not_full_quality_claim"])
        self.assertEqual(segmented["absolute_path_leak_count"], 0)

        self.assertTrue(semantic["semantic_learning_observed_outcome_ok"])
        self.assertEqual(semantic["observed_guidance_outcome_case_count"], 4)
        self.assertEqual(semantic["surfaced_without_observed_outcome_count"], 1)
        self.assertEqual(
            semantic["repeat_semantic_failure_prevented_or_redirected_count"],
            1,
        )
        self.assertEqual(semantic["repeat_semantic_failure_after_surface_count"], 1)
        self.assertEqual(semantic["false_positive_nudge_count"], 2)
        self.assertEqual(semantic["source_reopen_after_semantic_guidance_rate"], 0.25)
        self.assertEqual(semantic["unobserved_guidance_prevented_count"], 0)
        self.assertEqual(semantic["private_replay_auto_prevented_repeat_count"], 0)
        self.assertGreaterEqual(semantic["private_replay_unobserved_guidance_count"], 1)
        self.assertTrue(semantic["dogfood_fixture_contract_smoke_only"])
        self.assertEqual(semantic["dogfood_fixture_prevented_repeat_count"], 0)
        self.assertFalse(semantic["live_product_lift_claimed"])

    def test_e2e50_field_validation_successor_reports_private_shortfall_boundary(self) -> None:
        report = build_successor_evidence_sweep_report()
        by_issue = {row["issue"]: row for row in report["issues"]}
        metrics = by_issue[1981]["metrics"]

        self.assertTrue(metrics["e2e50_field_validation_report_ok"])
        self.assertTrue(metrics["public_contract_gate_ok"])
        self.assertFalse(metrics["field_validation_gate_ok"])
        self.assertEqual(metrics["field_case_count"], 7)
        self.assertEqual(metrics["retained_control_case_count"], 7)
        self.assertEqual(metrics["retained_case_shortfall"], 13)
        self.assertGreaterEqual(metrics["negative_control_count"], 1)
        self.assertEqual(metrics["behavior_scored_case_count"], 6)
        self.assertEqual(metrics["private_text_leak_count"], 0)
        self.assertEqual(metrics["raw_ref_or_local_path_leak_count"], 0)
        self.assertEqual(metrics["public_fixture_only_case_count"], 50)
        self.assertFalse(metrics["field_behavior_lift_claimed"])
        self.assertFalse(metrics["live_host_behavior_lift_claimed"])
        self.assertFalse(metrics["representative_e2e50_quality_claimed"])
        self.assertFalse(metrics["semantic_judge_quality_claimed"])
        self.assertTrue(metrics["private_shortfall_blocks_public_pack"])

    def test_hard_blocker_successor_hygiene_is_itself_tracked(self) -> None:
        report = build_successor_evidence_sweep_report()
        by_issue = {row["issue"]: row for row in report["issues"]}
        metrics = by_issue[1998]["metrics"]

        self.assertIn(1998, report["covered_issue_numbers"])
        self.assertGreaterEqual(metrics["hard_blocker_successor_path_count"], 3)
        self.assertEqual(metrics["hard_blocker_without_successor_count"], 0)
        self.assertEqual(metrics["closed_blocker_without_execution_owner_count"], 0)
        self.assertFalse(metrics["hard_blocker_closed_as_product_done"])

    def test_external_provider_blockers_publish_public_provider_artifact_metadata(self) -> None:
        report = build_successor_evidence_sweep_report()
        by_issue = {row["issue"]: row for row in report["issues"]}

        for issue_number in (1929, 1931):
            metrics = by_issue[issue_number]["metrics"]
            artifact = metrics["provider_artifact"]

            self.assertIn(artifact["provider"], {"openrouter", "not_requested", "local_scripted"})
            self.assertIn("model", artifact)
            self.assertIn("prompt", artifact)
            self.assertIn("runner", artifact)
            self.assertIn("cost", artifact)
            self.assertIn("run_date", artifact)
            self.assertEqual(artifact["blocker_metadata"]["successor_issue"], 2043)
            self.assertFalse(artifact["privacy_boundary"]["raw_provider_payload_included"])
            self.assertFalse(artifact["privacy_boundary"]["provider_credentials_included"])
            self.assertFalse(metrics["official_provider_score_claimed"])

    def test_live_blockers_publish_private_trace_index_without_raw_trace(self) -> None:
        report = build_successor_evidence_sweep_report()
        by_issue = {row["issue"]: row for row in report["issues"]}

        for issue_number in (1942, 1944, 1945):
            metrics = by_issue[issue_number]["metrics"]
            index = metrics["private_trace_artifact_index"]

            self.assertEqual(index["successor_issue"], 2044)
            self.assertGreaterEqual(index["case_count"], 0)
            self.assertRegex(index["trace_hash"], r"^ptr_[0-9a-f]{16}$")
            self.assertIn("public_issue_summary_redacted", index)
            self.assertEqual(index["local_pointer_kind"], "private_operator_artifact_pointer")
            self.assertFalse(index["privacy_boundary"]["raw_trace_included"])
            self.assertFalse(index["privacy_boundary"]["local_path_public"])
            self.assertFalse(metrics["live_product_lift_claimed"])

    def test_live_or_provider_successors_close_as_blocked_not_promoted(self) -> None:
        report = build_successor_evidence_sweep_report()
        blocked = [
            row for row in report["issues"]
            if row["decision"] == "hard_blocker_recorded_no_default_promotion"
        ]

        self.assertGreaterEqual(len(blocked), 4)
        self.assertEqual(report["coverage"]["closed_hard_blocker_without_successor_count"], 0)
        for row in blocked:
            self.assertEqual(row["metrics"]["hard_blocker"], "missing_live_provider_or_pretooluse_trace")
            self.assertFalse(row["metrics"]["provider_or_live_trace_available"])
            self.assertFalse(row["default_or_live_claim_allowed"])
            self.assertTrue(row["closeout_allowed"])
            self.assertEqual(row["hard_blocker_execution_path"]["path_kind"], "open_successor_issue")
            self.assertIn(
                row["hard_blocker_execution_path"]["successor_issue"],
                {2043, 2044},
            )

    def test_hard_blocker_rows_require_successor_or_deferred_pointer(self) -> None:
        with patch.dict(successor_evidence.HARD_BLOCKER_EXECUTION_PATHS, {}, clear=True):
            report = build_successor_evidence_sweep_report()

        blocked_without_path = report["coverage"]["closed_hard_blocker_without_successor_numbers"]
        by_issue = {row["issue"]: row for row in report["issues"]}

        self.assertFalse(report["ok"])
        self.assertGreaterEqual(report["coverage"]["closed_hard_blocker_without_successor_count"], 4)
        self.assertIn(1942, blocked_without_path)
        self.assertFalse(by_issue[1942]["closeout_allowed"])
        self.assertEqual(
            by_issue[1942]["hard_blocker_execution_path"]["status"],
            "missing_successor_or_deferred_pointer",
        )

    def test_e2e50_bounded_validation_keeps_retained_case_successor_pointer(self) -> None:
        report = build_successor_evidence_sweep_report()
        by_issue = {row["issue"]: row for row in report["issues"]}
        row = by_issue[1981]

        self.assertEqual(row["decision"], "bounded_validation_no_default_promotion")
        self.assertEqual(row["bounded_validation_deferred_path"]["successor_issue"], 2045)
        self.assertEqual(row["metrics"]["bounded_validation_deferred_path"]["successor_issue"], 2045)

    def test_dream_successors_report_observed_boundary_and_wrong_hint_metrics(self) -> None:
        report = build_successor_evidence_sweep_report()
        dream_rows = [row for row in report["issues"] if row["track"] == "avatar_dream"]

        self.assertGreaterEqual(len(dream_rows), 4)
        for row in dream_rows:
            metrics = row["metrics"]
            self.assertIn("observed_agent_behavior", metrics)
            self.assertIn("wrong_hint_rate", metrics)
            self.assertEqual(metrics["annoyance_or_noise_count"], 0)
            self.assertEqual(metrics["source_truth_overclaim_count"], 0)


if __name__ == "__main__":
    unittest.main()
