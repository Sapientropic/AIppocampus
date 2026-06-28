from __future__ import annotations

import json
import unittest

from aippocampus_runtime.coding import agent_trajectory_packets, sequence_packets, sequence_reopen
from aippocampus_runtime.recall import narrative_packet


def ref(line: int, message_id: str) -> dict[str, object]:
    return {
        "thread_key": "thread:agent-trajectory-test",
        "message_id": message_id,
        "turn_id": f"turn-{line}",
        "line": line,
        "path": r"E:\private\raw-rollout.jsonl",
    }


class AgentTrajectoryPacketTests(unittest.TestCase):
    def test_complete_live_agent_trajectory_reopens_ordered_source_refs(self) -> None:
        report = agent_trajectory_packets.build_live_agent_trajectory_packet(
            route_notes=[
                {
                    "route_note_id": "rn-check-source-first",
                    "note_types": ["intent_before_tool"],
                    "source_refs": [ref(10, "msg-route-note")],
                    "raw_commentary": "RAW COMMENTARY MUST NOT LEAK",
                }
            ],
            behavior_events=[
                {
                    "event_id": "tool-test-pass",
                    "event_kind": "tool_call_succeeded",
                    "source_refs": [ref(11, "msg-tool")],
                    "raw_tool_output": "RAW TOOL OUTPUT MUST NOT LEAK",
                    "command": "pytest E:\\private\\tests",
                }
            ],
            decision_events=[
                {
                    "decision_id": "decision-narrow-scope",
                    "event_type": "scope_narrowing",
                    "source_refs": [ref(12, "msg-decision")],
                    "summary": "Raw decision prose should not be serialized as truth.",
                }
            ],
            final_closeouts=[
                {
                    "message_id": "msg-final",
                    "source_refs": [ref(13, "msg-final")],
                    "text": "Raw final closeout text should not be copied into the trajectory.",
                }
            ],
        )
        packet = report["sequence_packet"]
        plan = report["reopen_plan"]
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(report["status"], "complete")
        self.assertEqual(packet["kind"], sequence_packets.SEQUENCE_PACKET_KIND)
        self.assertEqual(packet["producer_family"], "agent_trajectory")
        self.assertEqual(
            [row["event_kind"] for row in packet["timeline"]],
            ["route_note", "tool_call_succeeded", "scope_narrowing", "final_closeout"],
        )
        self.assertEqual(plan["kind"], sequence_reopen.SEQUENCE_PACKET_REOPEN_PLAN_KIND)
        self.assertEqual(plan["resolution_status"], "complete")
        self.assertEqual(
            [row["message_id"] for row in plan["route"]["source_refs"]],
            ["msg-route-note", "msg-tool", "msg-decision", "msg-final"],
        )
        self.assertIn("process_supervision", packet["training_signal_roles"])
        self.assertNotIn("RAW COMMENTARY", encoded)
        self.assertNotIn("RAW TOOL OUTPUT", encoded)
        self.assertNotIn("E:\\private", encoded)
        self.assertNotIn("raw-rollout", encoded)

    def test_missing_middle_event_degrades_to_refresh_sources(self) -> None:
        report = agent_trajectory_packets.build_live_agent_trajectory_packet(
            route_notes=[{"route_note_id": "rn-only", "source_refs": [ref(20, "msg-route")]}],
            final_closeouts=[{"message_id": "msg-final", "source_refs": [ref(22, "msg-final")]}],
        )

        self.assertEqual(report["status"], "gappy")
        self.assertIn("missing_behavior_event", report["sequence_packet"]["sequence_gaps"])
        self.assertEqual(report["reopen_plan"]["resolution_status"], "complete")
        self.assertEqual(report["reopen_plan"]["recommended_use"], "refresh_sources")
        self.assertEqual(report["compact_summary"]["status"], "refresh_sources")

    def test_wrong_order_chain_is_gappy_even_when_sources_resolve(self) -> None:
        report = agent_trajectory_packets.build_live_agent_trajectory_packet(
            route_notes=[{"route_note_id": "rn-late", "source_refs": [ref(31, "msg-route")]}],
            behavior_events=[
                {
                    "event_id": "tool-before-note",
                    "event_kind": "tool_call_succeeded",
                    "source_refs": [ref(30, "msg-tool")],
                }
            ],
            final_closeouts=[{"message_id": "msg-final", "source_refs": [ref(32, "msg-final")]}],
        )

        self.assertEqual(report["status"], "gappy")
        self.assertIn("wrong_order", report["sequence_packet"]["sequence_gaps"])
        self.assertEqual(report["reopen_plan"]["resolution_status"], "complete")
        self.assertEqual(report["reopen_plan"]["recommended_use"], "refresh_sources")

    def test_trajectory_sequence_packet_feeds_narrative_source_reopen_mesh(self) -> None:
        report = agent_trajectory_packets.build_live_agent_trajectory_packet(
            route_notes=[{"route_note_id": "rn-start", "source_refs": [ref(40, "msg-route")]}],
            behavior_events=[
                {
                    "event_id": "test-after-route-note",
                    "event_kind": "tool_call_succeeded",
                    "source_refs": [ref(41, "msg-tool")],
                }
            ],
            decision_events=[
                {
                    "decision_id": "decision-keep-source-open",
                    "event_type": "scope_narrowing",
                    "source_refs": [ref(42, "msg-decision")],
                }
            ],
            final_closeouts=[{"message_id": "msg-final", "source_refs": [ref(43, "msg-final")]}],
            trigger="previous agent checked old source before changing source_texture",
        )

        packet = narrative_packet.compile_narrative_packet(
            trigger="previous agent checked old source before changing source_texture",
            current_query="prior source_texture trajectory",
            sequence_packets=[report["sequence_packet"]],
            source_catalog=report["source_catalog"],
        )
        reopen_plan = packet["source_reopen"]["sequence_reopen_plans"][0]
        encoded = json.dumps(packet, ensure_ascii=False, sort_keys=True)

        self.assertEqual(packet["use_boundary"]["action_grammar"], "reopenable_route")
        self.assertFalse(packet["source_reopen"]["manual_query_invention_expected"])
        self.assertEqual(reopen_plan["resolution_status"], "complete")
        self.assertEqual(
            [row["message_id"] for row in reopen_plan["route"]["source_refs"]],
            ["msg-route", "msg-tool", "msg-decision", "msg-final"],
        )
        self.assertIn("sequence_packet_is_not_evidence", reopen_plan["cannot_claim"])
        self.assertNotIn("E:\\private", encoded)


if __name__ == "__main__":
    unittest.main()
