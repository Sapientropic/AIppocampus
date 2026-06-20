from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.cli import facade  # noqa: E402
from aippocampus_runtime.contracts import (  # noqa: E402
    executable_command_violations,
    foreground_action_contract_violations,
)
from aippocampus_runtime.recall import task_orientation, understanding_state  # noqa: E402


class TaskOrientationPacketTests(unittest.TestCase):
    def test_packet_is_thin_active_path_projection_without_private_source_dump(self) -> None:
        packet = task_orientation.build_task_orientation_packet(
            "Land Task Orientation Packets across agent recall, AIppo, and issue work guard",
            project="AIppocampus",
        )
        encoded = json.dumps(packet, ensure_ascii=False, sort_keys=True)

        self.assertEqual(packet["kind"], "aippocampus_task_orientation_packet")
        self.assertEqual(packet["status"], "ok")
        self.assertEqual(packet["detail"], "compact")
        self.assertIn("current_orientation", packet)
        self.assertLessEqual(packet["current_orientation"]["active_path_count"], 3)
        self.assertNotIn("understanding_state_read_model", packet)
        self.assertNotIn("active_path_packet", packet)
        self.assertNotIn("external_source_anchors", packet)
        self.assertNotIn("suppressed_external_source_anchors", packet)
        self.assertNotIn("learning_and_aippo_constraints", packet)
        self.assertNotIn("suppressed_constraints", packet)
        self.assertIn("route_plan", packet)
        self.assertGreaterEqual(len(packet["route_plan"]["first_sources_to_reopen"]), 1)
        self.assertGreaterEqual(len(packet["route_plan"]["stop_conditions"]), 2)
        self.assertLessEqual(len(packet["source_routes"]), 3)
        self.assertTrue(packet["source_boundary"]["navigation_not_truth"])
        self.assertFalse(packet["source_boundary"]["raw_source_text_serialized"])
        self.assertFalse(packet["source_boundary"]["local_paths_serialized"])
        self.assertIn("product_boundary", packet)
        self.assertIn("operator_detail_command", packet)
        self.assertNotIn("cannot_claim", packet)
        self.assertNotIn("red_lines", packet)
        self.assertNotIn("metrics", packet)
        full_packet = task_orientation.build_task_orientation_packet(
            "Land Task Orientation Packets across agent recall, AIppo, and issue work guard",
            project="AIppocampus",
            detail="full",
        )
        self.assertEqual(full_packet["understanding_state_read_model"]["authority"], "navigation_only_not_fact")
        self.assertEqual(
            full_packet["understanding_state_read_model"]["truth_authority"],
            "clean_source_after_reopen",
        )
        self.assertEqual(full_packet["understanding_state_read_model"]["storage"], "derived_no_new_truth_store")
        self.assertEqual(full_packet["active_path_packet"]["kind"], "aippocampus_active_path_packet")
        self.assertLessEqual(full_packet["active_path_packet"]["path_count"], 3)
        self.assertIn("cannot_claim", full_packet)
        self.assertIn("red_lines", full_packet)
        self.assertIn("foreground_json_bytes", full_packet["metrics"])
        self.assertNotIn("trust_taxonomy", full_packet["active_path_packet"])
        self.assertNotIn("active_path_packet_proves_memory_fact", encoded)
        self.assertEqual(executable_command_violations(packet), [])
        self.assertEqual(foreground_action_contract_violations(packet), [])
        self.assertNotIn("get_turn_context", encoded)
        self.assertNotIn("PRIVATE_SOURCE_SENTINEL", encoded)
        self.assertNotIn("PRIVATE_SUMMARY_SENTINEL", encoded)
        self.assertNotIn("E:\\", encoded)
        self.assertNotIn(".aippocampus\\clean-source", encoded)
        self.assertNotIn("source_handles", encoded)

    def test_external_source_anchors_have_roles_and_stale_boundaries(self) -> None:
        packet = task_orientation.build_task_orientation_packet(
            "Connect papers, GitHub issues, and docs without treating them as memory truth",
            detail="full",
        )
        anchors = packet["external_source_anchors"]
        suppressed = packet["suppressed_external_source_anchors"]

        self.assertGreaterEqual(len(anchors), 3)
        self.assertTrue(all(anchor["authority"] == "route_not_evidence" for anchor in anchors))
        self.assertIn("github_issue", {anchor["source_kind"] for anchor in anchors})
        self.assertIn("github_discussion", {anchor["source_kind"] for anchor in anchors})
        self.assertIn("documentation", {anchor["source_kind"] for anchor in anchors})
        self.assertIn("research_reference", {anchor["source_kind"] for anchor in anchors})
        self.assertTrue(all("privacy_boundary" in anchor for anchor in anchors))
        self.assertTrue(
            all(anchor["safe_use"] == "reopen_before_claim" for anchor in anchors),
            anchors,
        )
        self.assertTrue(
            any(anchor["lifecycle_status"] in {"stale", "superseded"} for anchor in suppressed),
            suppressed,
        )
        self.assertTrue(
            all(anchor["safe_use"] == "do_not_rank_as_current_route" for anchor in suppressed),
            suppressed,
        )

    def test_learning_loop_and_aippo_constraints_feed_route_readiness_only(self) -> None:
        packet = task_orientation.build_task_orientation_packet(
            "Use learning-loop and AIppo constraints when orienting a new agent to issue work",
            detail="full",
        )
        constraints = packet["learning_and_aippo_constraints"]

        self.assertTrue(any(item["source"] == "issue_work_guard" for item in constraints))
        self.assertTrue(any(item["source"] == "aippo_working_contract" for item in constraints))
        self.assertTrue(any(item["source"] == "semantic_learning" for item in constraints))
        self.assertTrue(any(item["source"] == "source_backed_lessons" for item in constraints))
        self.assertTrue(any(item["source"] == "learning_loop_aippo_seed" for item in constraints))
        self.assertTrue(all(item["authority"] == "navigation_only_not_fact" for item in constraints))
        self.assertTrue(all("effectiveness_feedback" in item for item in constraints))
        self.assertGreaterEqual(packet["metrics"]["learning_constraint_count"], 5)
        self.assertGreaterEqual(packet["metrics"]["suppressed_unripe_constraint_count"], 1)
        full_packet = task_orientation.build_task_orientation_packet(
            "Use learning-loop and AIppo constraints when orienting a new agent to issue work",
            detail="full",
        )
        self.assertEqual(full_packet["red_lines"]["learning_constraint_promoted_to_fact"], 0)
        self.assertEqual(full_packet["red_lines"]["unripe_constraint_ranked_as_current"], 0)

        quiet = task_orientation.build_task_orientation_packet("Fix typo in README", detail="full")
        self.assertFalse(quiet["issue_work_guard"]["should_pull"])
        self.assertNotIn(
            "issue_work_guard",
            {item["source"] for item in quiet["learning_and_aippo_constraints"]},
        )

    def test_understanding_state_composes_upstream_read_models_without_bloating_foreground(self) -> None:
        state = understanding_state.build_understanding_state_read_model(
            "Continue Task Orientation Packet issue work after source-backed review",
            project="AIppocampus",
            continuity_snapshot={
                "domains": [
                    {
                        "domain_id": "task_orientation_continuity",
                        "title": "Task Orientation Packets",
                        "activation_cues": ["Task Orientation Packet", "source-backed review"],
                        "scope_labels": ["AIppocampus", "fresh-thread"],
                        "lifecycle": {"status": "active"},
                        "claim_contract": {
                            "trust_level": "source_required",
                            "action_grammar": "reopenable_route",
                        },
                        "evidence_trail": {
                            "representative_refs": [
                                {"source_id": "doc:task-orientation", "message_id": "m1"}
                            ]
                        },
                    }
                ]
            },
            journeys=[
                {
                    "kind": "aippocampus_journey",
                    "path_label": "fresh-thread understanding recovery",
                    "current_frontier": "Resume at the source-backed orientation boundary.",
                    "status": "traveling",
                    "source_refs": [{"thread_key": "journey-public", "message_id": "m2"}],
                }
            ],
            episode_arcs=[
                {
                    "episode_id": "episode-task-orientation",
                    "episode_kind": "rejected_route_arc",
                    "event_order": ["attempted_route", "failed_check", "route_rejected"],
                    "source_event_ids": ["attempt", "fail", "reject"],
                    "source_ref_hashes": ["h1", "h2", "h3"],
                    "current_validity": "needs_reopen",
                }
            ],
            repo_familiarity_manifest={
                "repo_commit": "public-fixture",
                "source_rows": [
                    {
                        "kind": "recall_runtime",
                        "landmark": "Task orientation runtime",
                        "route_terms": ["task", "orientation", "recall"],
                        "action_delta_required": "Check TOP runtime before broad search.",
                        "first_source_to_reopen": "skills/aippocampus/scripts/aippocampus_runtime/recall/task_orientation.py",
                        "stop_after": "Stop once the runtime projection answers the next source route.",
                        "source_refs": [{"path": "skills/aippocampus/scripts/aippocampus_runtime/recall/task_orientation.py"}],
                    }
                ],
            },
        )
        encoded = json.dumps(state, ensure_ascii=False, sort_keys=True)
        components = {item["component"] for item in state["upstream_components"]}
        foreground = state["foreground_projection"]

        self.assertEqual(state["kind"], "aippocampus_understanding_state")
        self.assertEqual(state["schema_version"], "aippocampus_understanding_state.v1")
        self.assertEqual(state["authority"], "navigation_only_not_fact")
        self.assertEqual(state["storage"], "derived_no_new_truth_store")
        self.assertEqual(
            state["working_conclusion_exposure_strategy"]["active_foreground_pull"],
            "compact_orientation_only",
        )
        self.assertTrue(
            {"continuity_domains", "journey", "episode_arcs", "repo_familiarity"}.issubset(
                components
            ),
            components,
        )
        self.assertGreaterEqual(len(state["route_cues"]), 3)
        self.assertLessEqual(len(foreground["first_routes_to_reopen"]), 3)
        self.assertLessEqual(foreground["byte_size"], foreground["byte_budget"])
        self.assertNotIn("RAW_SOURCE_SENTINEL", encoded)
        self.assertNotIn("E:\\", encoded)
        self.assertFalse(state["source_boundary"]["raw_source_text_serialized"])

    def test_public_fixture_eval_shows_less_blind_search_without_claiming_live_lift(self) -> None:
        report = task_orientation.build_task_orientation_eval_report()
        baseline = report["conditions"]["static_summary_baseline"]
        route_only = report["conditions"]["route_only_source_backed_recall"]
        top = report["conditions"]["task_orientation_packet"]
        top_plus = report["conditions"]["task_orientation_plus_constraints"]

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertLess(top["broad_manual_search_count"], baseline["broad_manual_search_count"])
        self.assertLess(top["blind_deepen_count"], baseline["blind_deepen_count"])
        self.assertLessEqual(top_plus["repeated_wrong_route_count"], route_only["repeated_wrong_route_count"])
        self.assertEqual(top["source_truth_overclaim_count"], 0)
        self.assertEqual(top_plus["source_truth_overclaim_count"], 0)
        self.assertEqual(
            {
                "complete",
                "partial",
                "stale_anchor",
                "conflicted",
                "missing_source",
                "foreground_too_heavy",
            },
            {case["case_id"] for case in report["fixture_cases"]},
        )
        self.assertEqual(report["claim_boundary"], "public_fixture_only_not_live_quality_claim")
        self.assertFalse(report["private_replay"]["enabled_by_default"])
        self.assertTrue(report["private_replay"]["aggregate_only"])

    def test_eval_can_include_opt_in_private_replay_aggregate_metrics(self) -> None:
        report = task_orientation.build_task_orientation_eval_report(
            include_private_replay_aggregate=True
        )
        private = report["private_replay"]
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertTrue(private["opt_in_required"])
        self.assertEqual(private["status"], "measured_public_safe_aggregate")
        self.assertTrue(private["aggregate_only"])
        self.assertFalse(private["enabled_by_default"])
        self.assertGreaterEqual(private["aggregate_metrics"]["guidance_count"], 1)
        self.assertEqual(private["aggregate_metrics"]["raw_private_text_leak_count"], 0)
        self.assertNotIn("PRIVATE_HISTORY_PAYLOAD", encoded)
        self.assertNotIn("tool_output", encoded)
        self.assertNotIn("E:/", encoded)

    def test_agent_orient_cli_returns_safe_packet_and_missing_task_recovery(self) -> None:
        result = facade.run_command(
            [
                "agent",
                "orient",
                "fresh-thread task orientation for AIppocampus issue work",
                "--json",
            ],
            capture_output=True,
        )

        self.assertEqual(result.exit_code, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["kind"], "aippocampus_task_orientation_packet")
        self.assertEqual(payload["mode"], "orient")
        self.assertIn("product_boundary", payload)
        self.assertIn("current_orientation", payload)
        self.assertNotIn("active_path_packet", payload)
        self.assertNotIn("suppressed_detail", payload)
        self.assertNotIn("cannot_claim", payload)
        self.assertNotIn("red_lines", payload)
        self.assertEqual(payload["foreground_action"]["command_template"], 'aippocampus agent recall "{task}" --json')
        self.assertEqual(executable_command_violations(payload), [])
        self.assertEqual(foreground_action_contract_violations(payload), [])

        full_result = facade.run_command(
            [
                "agent",
                "orient",
                "fresh-thread task orientation for AIppocampus issue work",
                "--json",
                "--detail",
                "full",
            ],
            capture_output=True,
        )
        full_payload = json.loads(full_result.stdout)
        self.assertEqual(full_result.exit_code, 0, full_result.stderr)
        self.assertIn("cannot_claim", full_payload)
        self.assertIn("red_lines", full_payload)

        missing = facade.run_command(["agent", "orient", "--json"], capture_output=True)
        missing_payload = json.loads(missing.stdout)

        self.assertEqual(missing.exit_code, 2)
        self.assertEqual(missing_payload["status"], "needs_input")
        self.assertEqual(
            missing_payload["foreground_action"]["command_template"],
            'aippocampus agent orient "{task}" --json',
        )
        self.assertEqual(executable_command_violations(missing_payload), [])

        eval_result = facade.run_command(
            ["agent", "orient", "--eval", "--json"],
            capture_output=True,
        )
        eval_payload = json.loads(eval_result.stdout)

        self.assertEqual(eval_result.exit_code, 0, eval_result.stderr)
        self.assertEqual(eval_payload["kind"], "aippocampus_task_orientation_eval_report")
        self.assertEqual(eval_payload["claim_boundary"], "public_fixture_only_not_live_quality_claim")

        private_eval = facade.run_command(
            ["agent", "orient", "--eval", "--private-replay-aggregate", "--json"],
            capture_output=True,
        )
        private_payload = json.loads(private_eval.stdout)

        self.assertEqual(private_eval.exit_code, 0, private_eval.stderr)
        self.assertEqual(private_payload["private_replay"]["status"], "measured_public_safe_aggregate")
        self.assertEqual(executable_command_violations(private_payload), [])


if __name__ == "__main__":
    unittest.main()
