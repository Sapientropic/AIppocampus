from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.coding import episode_arcs, sequence_packets, sequence_reopen  # noqa: E402


def source_ref(line: int, message_id: str) -> dict[str, object]:
    return {
        "thread_key": "thread:episode-arc-test",
        "message_id": message_id,
        "turn_id": f"turn-{line}",
        "source_line": line,
    }


def event(
    event_id: str,
    event_kind: str,
    line: int,
    *,
    sequence_index: int | None = None,
    episode_id: str = "episode:route",
) -> dict[str, object]:
    row: dict[str, object] = {
        "episode_id": episode_id,
        "event_id": event_id,
        "event_kind": event_kind,
        "source_refs": [source_ref(line, f"m-{line}")],
        "turn_id": f"turn-{line}",
        "source_line": line,
        "affected_scope": {"files": [{"path": "src/widget.py", "path_kind": "repo_relative"}]},
    }
    if sequence_index is not None:
        row["sequence_index"] = sequence_index
    return row


class EpisodeArcReadModelTests(unittest.TestCase):
    def source_catalog_for_arc(self, arc: dict[str, object]) -> list[dict[str, object]]:
        raw_event_ids = arc.get("source_event_ids")
        raw_source_hashes = arc.get("source_ref_hashes")
        raw_source_refs = arc.get("source_refs")
        event_ids = [str(item) for item in raw_event_ids if str(item).strip()] if isinstance(raw_event_ids, list) else []
        source_hashes = (
            [str(item) for item in raw_source_hashes if str(item).strip()]
            if isinstance(raw_source_hashes, list)
            else []
        )
        source_refs = [item for item in raw_source_refs if isinstance(item, dict)] if isinstance(raw_source_refs, list) else []
        return [
            {
                "event_id": event_id,
                "source_ref_hash": source_hash,
                "source_refs": [source_ref],
                "raw_source_text": "RAW_SEQUENCE_REOPEN_SENTINEL",
            }
            for event_id, source_hash, source_ref in zip(event_ids, source_hashes, source_refs, strict=False)
        ]

    def test_builds_rejected_route_arc_packet_and_reopen_plan(self) -> None:
        arcs = episode_arcs.build_episode_arcs(
            [
                event("e-attempt", "attempted_route", 10, sequence_index=0),
                event("e-failed", "failed_check", 11, sequence_index=1),
                event("e-rejected", "route_rejected", 12, sequence_index=2),
            ]
        )

        self.assertEqual(len(arcs), 1)
        arc = arcs[0]
        self.assertEqual(arc["kind"], episode_arcs.EPISODE_ARC_KIND)
        self.assertEqual(arc["episode_kind"], "rejected_route_arc")
        self.assertEqual(arc["source_event_ids"], ["e-attempt", "e-failed", "e-rejected"])
        self.assertEqual(arc["event_order"], ["attempted_route", "failed_check", "route_rejected"])
        self.assertEqual(arc["turn_range"]["first_turn_id"], "turn-10")
        self.assertEqual(arc["turn_range"]["last_turn_id"], "turn-12")
        self.assertEqual(arc["affected_scope"]["files"][0]["path"], "src/widget.py")
        self.assertEqual(arc["current_validity"], "needs_reopen")
        self.assertEqual(arc["truth_status"], sequence_packets.CHAIN_TRUTH_STATUS)
        self.assertEqual(arc["sequence_gaps"], [])

        packet = episode_arcs.render_sequence_packet(arc, trigger="pre_patch")
        evidence = sequence_packets.evaluate_case_evidence(
            {"episode_chain": arc, "sequence_packet": packet}
        )

        self.assertEqual(packet["kind"], sequence_packets.SEQUENCE_PACKET_KIND)
        self.assertEqual(
            [row["event_kind"] for row in packet["timeline"]],
            ["attempted_route", "failed_check", "route_rejected"],
        )
        self.assertEqual(packet["current_assessment"]["proposed_use"], "refresh_sources")
        self.assertEqual(packet["current_assessment"]["truth_boundary"], "derived_weather_not_source_fact")
        self.assertIn("current_validity_requires_source_reopen", packet["cannot_claim"])
        self.assertTrue(evidence["sequence_contract_ok"])
        self.assertTrue(evidence["behavior_only_rejection_passed"])

        plan = episode_arcs.build_reopen_plan(arc)
        self.assertEqual(plan["kind"], episode_arcs.REOPEN_PLAN_KIND)
        self.assertEqual(plan["episode_id"], arc["episode_id"])
        self.assertEqual(plan["route"]["source_event_ids"], ["e-attempt", "e-failed", "e-rejected"])
        self.assertEqual(plan["recommended_use"], "refresh_sources")
        self.assertIn("source_window", plan["route"])
        self.assertIn("episode_arc_is_not_current_truth", plan["cannot_claim"])

    def test_sequence_packet_reopen_plan_resolves_catalog_without_arc_truth(self) -> None:
        arc = episode_arcs.build_episode_arcs(
            [
                event("e-attempt", "attempted_route", 10, sequence_index=0),
                event("e-failed", "failed_check", 11, sequence_index=1),
                event("e-rejected", "route_rejected", 12, sequence_index=2),
            ]
        )[0]
        packet = episode_arcs.render_sequence_packet(arc, trigger="pre_patch")
        plan = sequence_reopen.build_sequence_packet_reopen_plan(
            packet,
            source_catalog=self.source_catalog_for_arc(arc),
        )

        self.assertEqual(plan["kind"], sequence_reopen.SEQUENCE_PACKET_REOPEN_PLAN_KIND)
        self.assertEqual(plan["resolution_status"], "complete")
        self.assertEqual(plan["route"]["source_event_ids"], ["e-attempt", "e-failed", "e-rejected"])
        self.assertEqual(
            plan["route"]["resolved_source_event_ids"],
            ["e-attempt", "e-failed", "e-rejected"],
        )
        self.assertEqual(plan["route"]["source_window"]["unresolved_event_count"], 0)
        self.assertFalse(plan["route"]["source_window"]["raw_source_serialized"])
        self.assertIn("sequence_packet_is_not_evidence", plan["cannot_claim"])
        self.assertIn("current_validity_requires_source_reopen", plan["cannot_claim"])
        self.assertNotIn("RAW_SEQUENCE_REOPEN_SENTINEL", json.dumps(plan, ensure_ascii=False))
        self.assertEqual(
            plan["issue_readouts"]["github_663"]["source_reopen_from_sequence_packet"],
            "complete",
        )
        self.assertFalse(plan["issue_readouts"]["github_663"]["closeout_eligible"])

    def test_sequence_packet_reopen_plan_degrades_without_source_catalog(self) -> None:
        arc = episode_arcs.build_episode_arcs(
            [
                event("e-attempt", "attempted_route", 10, sequence_index=0),
                event("e-failed", "failed_check", 11, sequence_index=1),
                event("e-rejected", "route_rejected", 12, sequence_index=2),
            ]
        )[0]
        packet = episode_arcs.render_sequence_packet(arc, trigger="pre_patch")
        plan = sequence_reopen.build_sequence_packet_reopen_plan(packet)

        self.assertEqual(plan["resolution_status"], "unresolved")
        self.assertEqual(plan["recommended_use"], "refresh_sources")
        self.assertEqual(plan["safe_uses"], ["ask", "refresh_sources"])
        self.assertEqual(plan["route"]["source_refs"], [])
        self.assertEqual(len(plan["route"]["unresolved_timeline_events"]), 3)
        self.assertIn("source_catalog_required_for_reopen", plan["cannot_claim"])

    def test_gappy_sequence_packet_reopen_plan_stays_refresh_only(self) -> None:
        arc = episode_arcs.build_episode_arcs(
            [
                event("e-attempt", "attempted_route", 25, sequence_index=0, episode_id="episode:gappy-packet"),
                event("e-rejected", "rejected_route", 27, sequence_index=2, episode_id="episode:gappy-packet"),
            ]
        )[0]
        packet = episode_arcs.render_sequence_packet(arc, trigger="pre_patch")
        plan = sequence_reopen.build_sequence_packet_reopen_plan(
            packet,
            source_catalog=self.source_catalog_for_arc(arc),
        )

        self.assertEqual(plan["resolution_status"], "complete")
        self.assertEqual(plan["recommended_use"], "refresh_sources")
        self.assertEqual(plan["safe_uses"], ["ask", "refresh_sources"])
        self.assertIn("sequence_order_uncertain", plan["cannot_claim"])

    def test_same_events_wrong_order_are_marked_gappy_not_promoted(self) -> None:
        arcs = episode_arcs.build_episode_arcs(
            [
                event("e-failed", "failed_check", 11, episode_id="episode:wrong-order"),
                event("e-attempt", "attempted_route", 10, episode_id="episode:wrong-order"),
                event("e-rejected", "route_rejected", 12, episode_id="episode:wrong-order"),
            ]
        )

        arc = arcs[0]
        packet = episode_arcs.render_sequence_packet(arc, trigger="post_compact_behavior_audit")
        evidence = sequence_packets.evaluate_case_evidence(
            {"episode_chain": arc, "sequence_packet": packet}
        )

        self.assertEqual(arc["event_order"], ["failed_check", "attempted_route", "route_rejected"])
        self.assertIn("event_order_semantic_mismatch", arc["sequence_gaps"])
        self.assertFalse(arc["expected_valid"])
        self.assertEqual(packet["current_assessment"]["proposed_use"], "refresh_sources")
        self.assertIn("sequence_order_uncertain", packet["cannot_claim"])
        self.assertTrue(evidence["sequence_contract_ok"])
        self.assertTrue(evidence["middle_event_gap_detected"])

    def test_behavior_and_decision_rows_adapt_into_rejected_route_arc(self) -> None:
        arcs = episode_arcs.build_episode_arcs(
            [
                event(
                    "e-attempt",
                    "attempted_route",
                    20,
                    sequence_index=0,
                    episode_id="episode:adapter",
                ),
                {
                    "episode_id": "episode:adapter",
                    "event_id": "e-tool-failed",
                    "event_kind": "tool_call_observed",
                    "command_class": "test",
                    "exit_code": 1,
                    "hard_event_kind": "tool_call_failed",
                    "sequence_index": 1,
                    "source_refs": [source_ref(21, "m-21")],
                    "turn_id": "turn-21",
                    "source_line": 21,
                },
                {
                    "episode_id": "episode:adapter",
                    "decision_id": "decision-rejected",
                    "event_type": "rejected_route",
                    "sequence_index": 2,
                    "source_refs": [source_ref(22, "m-22")],
                    "turn_id": "turn-22",
                    "source_line": 22,
                },
            ]
        )

        arc = arcs[0]
        packet = episode_arcs.render_sequence_packet(arc, trigger="rejected_route")
        evidence = sequence_packets.evaluate_case_evidence(
            {"episode_chain": arc, "sequence_packet": packet}
        )

        self.assertEqual(arc["episode_kind"], "rejected_route_arc")
        self.assertEqual(arc["event_order"], ["attempted_route", "failed_check", "rejected_route"])
        self.assertEqual(arc["sequence_gaps"], [])
        self.assertTrue(arc["expected_valid"])
        self.assertEqual(arc["causal_edges"][0]["relation"], "failed_with")
        self.assertEqual(arc["causal_edges"][1]["relation"], "supported")
        self.assertTrue(evidence["sequence_contract_ok"])
        self.assertTrue(evidence["behavior_only_rejection_passed"])

    def test_thin_single_point_reopen_plan_only_allows_safe_uses(self) -> None:
        arcs = episode_arcs.build_episode_arcs(
            [event("e-single", "single_source_hint", 20, episode_id="episode:single")]
        )

        arc = arcs[0]
        packet = episode_arcs.render_sequence_packet(arc, trigger="source_reopen")
        plan = episode_arcs.build_reopen_plan(arc)

        self.assertEqual(arc["episode_kind"], "tacit_constraint_arc")
        self.assertIn("single_point_trap", arc["sequence_gaps"])
        self.assertFalse(arc["expected_valid"])
        self.assertEqual(packet["current_assessment"]["source_thickness"], "thin")
        self.assertEqual(packet["current_assessment"]["proposed_use"], "refresh_sources")
        self.assertEqual(plan["safe_uses"], ["ask", "refresh_sources"])
        self.assertNotIn("warn", plan["safe_uses"])

    def test_missing_middle_event_gap_requires_refresh_sources(self) -> None:
        arcs = episode_arcs.build_episode_arcs(
            [
                event("e-attempt", "attempted_route", 25, sequence_index=0, episode_id="episode:missing"),
                event("e-rejected", "rejected_route", 27, sequence_index=2, episode_id="episode:missing"),
            ]
        )

        arc = arcs[0]
        packet = episode_arcs.render_sequence_packet(arc, trigger="pre_patch")
        plan = episode_arcs.build_reopen_plan(arc)

        self.assertEqual(arc["episode_kind"], "rejected_route_arc")
        self.assertIn("missing_middle_event", arc["sequence_gaps"])
        self.assertFalse(arc["expected_valid"])
        self.assertEqual(packet["current_assessment"]["proposed_use"], "refresh_sources")
        self.assertIn("sequence_order_uncertain", packet["cannot_claim"])
        self.assertEqual(plan["safe_uses"], ["ask", "refresh_sources"])

    def test_public_gappy_chain_calibration_report_counts_reopen_only_cases(self) -> None:
        private_single = event("e-single", "single_source_hint", 40, episode_id="episode:single-public")
        private_single["raw_source_text"] = "RAW_PUBLIC_GAPPY_REPORT_SENTINEL"
        private_single["registry_path"] = r"C:\Users\Administrator\private\aippocampus\registry.jsonl"

        report = episode_arcs.build_public_gappy_chain_calibration_report(
            [
                event("e-attempt", "attempted_route", 10, sequence_index=0, episode_id="episode:complete"),
                event("e-failed", "failed_check", 11, sequence_index=1, episode_id="episode:complete"),
                event("e-rejected", "route_rejected", 12, sequence_index=2, episode_id="episode:complete"),
                event("e-missing-attempt", "attempted_route", 25, sequence_index=0, episode_id="episode:missing"),
                event("e-missing-rejected", "rejected_route", 27, sequence_index=2, episode_id="episode:missing"),
                event("e-wrong-failed", "failed_check", 31, episode_id="episode:wrong-order"),
                event("e-wrong-attempt", "attempted_route", 30, episode_id="episode:wrong-order"),
                event("e-wrong-rejected", "route_rejected", 32, episode_id="episode:wrong-order"),
                private_single,
                event("e-concern", "temporary_concern", 50, sequence_index=0, episode_id="episode:temporary"),
                event(
                    "e-normal",
                    "later_normal_progress",
                    51,
                    sequence_index=1,
                    episode_id="episode:temporary",
                ),
            ]
        )

        metrics = report["metrics"]
        self.assertEqual(report["kind"], episode_arcs.PUBLIC_GAPPY_CHAIN_REPORT_KIND)
        self.assertEqual(metrics["episode_arc_count"], 5)
        self.assertEqual(metrics["complete_arc_count"], 2)
        self.assertEqual(metrics["gappy_arc_count"], 3)
        self.assertEqual(metrics["missing_middle_event_count"], 1)
        self.assertEqual(metrics["wrong_order_arc_count"], 1)
        self.assertEqual(metrics["single_point_arc_count"], 1)
        self.assertEqual(metrics["temporary_concern_extinction_count"], 1)
        self.assertEqual(metrics["gappy_reopen_only_count"], 3)
        self.assertEqual(metrics["gappy_visible_action_overclaim_count"], 0)
        self.assertEqual(metrics["single_point_overclaim_rate"], 0.0)
        self.assertEqual(metrics["needs_reopen_projection_rate"], 1.0)

        for summary in report["case_summaries"]:
            if summary["sequence_gaps"]:
                self.assertEqual(summary["proposed_use"], "refresh_sources")
                self.assertEqual(summary["safe_uses"], ["ask", "refresh_sources"])
            self.assertNotIn("warn", summary["safe_uses"])
            self.assertNotIn("block", summary["safe_uses"])

        readout = report["issue_readouts"]["github_663"]
        self.assertEqual(readout["public_gappy_chain_fixture"], "measured_public_deterministic")
        self.assertFalse(readout["closeout_eligible"])
        self.assertIn("live_host_behavior_lift", report["cannot_claim"])

        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("RAW_PUBLIC_GAPPY_REPORT_SENTINEL", serialized)
        self.assertNotIn(r"C:\Users\Administrator\private", serialized)
        self.assertNotIn("thread:episode-arc-test", serialized)

    def test_temporary_concern_extinction_stays_local_only_without_warning(self) -> None:
        arcs = episode_arcs.build_episode_arcs(
            [
                event("e-concern", "temporary_concern", 28, sequence_index=0, episode_id="episode:temporary"),
                event(
                    "e-normal",
                    "later_normal_progress",
                    29,
                    sequence_index=1,
                    episode_id="episode:temporary",
                ),
            ]
        )

        arc = arcs[0]
        packet = episode_arcs.render_sequence_packet(arc, trigger="pre_patch")
        plan = episode_arcs.build_reopen_plan(arc)
        evidence = sequence_packets.evaluate_case_evidence(
            {"episode_chain": arc, "sequence_packet": packet}
        )

        self.assertEqual(arc["episode_kind"], "temporary_concern_arc")
        self.assertEqual(arc["current_validity"], "local_only")
        self.assertEqual(arc["outcome"], "constraint_not_current")
        self.assertEqual(arc["causal_edges"][0]["relation"], "extinguished_by")
        self.assertEqual(arc["sequence_gaps"], [])
        self.assertNotEqual(packet["current_assessment"]["proposed_use"], "warn")
        self.assertIn("remind", plan["safe_uses"])
        self.assertTrue(evidence["sequence_contract_ok"])
        self.assertTrue(evidence["supersession_passed"])

    def test_supersession_arc_preserves_order_without_claiming_current_truth(self) -> None:
        arcs = episode_arcs.build_episode_arcs(
            [
                event("e-old", "old_rule", 30, sequence_index=0, episode_id="episode:supersession"),
                event("e-new", "new_rule", 31, sequence_index=1, episode_id="episode:supersession"),
                event(
                    "e-current",
                    "current_rule_selected",
                    32,
                    sequence_index=2,
                    episode_id="episode:supersession",
                ),
            ]
        )

        arc = arcs[0]
        packet = episode_arcs.render_sequence_packet(arc, trigger="pre_patch")
        evidence = sequence_packets.evaluate_case_evidence(
            {"episode_chain": arc, "sequence_packet": packet}
        )

        self.assertEqual(arc["episode_kind"], "supersession_arc")
        self.assertEqual(arc["current_validity"], "superseded")
        self.assertEqual(arc["causal_edges"][0]["relation"], "superseded_by")
        self.assertTrue(evidence["sequence_contract_ok"])
        self.assertTrue(evidence["supersession_passed"])
        self.assertIn("episode_arc_as_truth_layer", packet["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
