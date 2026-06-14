from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.macro import state as macro_state  # noqa: E402
from aippocampus_runtime.navigation import attention_route_projection  # noqa: E402
from aippocampus_runtime.recall import agent_continuity  # noqa: E402


class AgentOptInContinuityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.clean = self.cwd / ".aippocampus" / "clean-source"
        self.clean.mkdir(parents=True)
        messages = [
            {
                "message_id": "msg_user",
                "turn_id": "turn_1",
                "source_id": "src_test",
                "source_line": 2,
                "role": "user",
                "phase": "",
                "turn_index": 1,
                "is_final": False,
                "text": "继续 agent-native recall opt-in path，但不要把 SECRET_TOKEN=abc123 放进前台。",
            },
            {
                "message_id": "msg_final",
                "turn_id": "turn_1",
                "source_id": "src_test",
                "source_line": 3,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 1,
                "is_final": True,
                "text": "Opt-in continuity should return a compact MemoryPacket, then deepen source before claims.",
            },
        ]
        with (self.clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for item in messages:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        with (self.clean / "turns.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {
                        "turn_id": "turn_1",
                        "turn_index": 1,
                        "message_ids": ["msg_user", "msg_final"],
                        "assistant_phase": "final_answer",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _append_clean_rows(self, rows: list[dict[str, object]]) -> None:
        with (self.clean / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _macro_state_path(
        self,
        *,
        active_layer: str = "人",
        momentum: dict[str, object] | None = None,
    ) -> Path:
        macro_path = self.cwd / f"macro-{active_layer}.jsonl"
        entry = macro_state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="乾",
            changing_lines=(1, 2, 3),
            source_refs=({"source_id": f"macro-live-{active_layer}"},),
            updated_at="2026-06-11T10:00:00Z",
            active_layer=active_layer,
            momentum=momentum,
        )
        macro_state.append_macro_orientation_state(macro_path, entry)
        return macro_path

    def _append_default_macro_state(
        self,
        *,
        active_layer: str = "人",
        changing_lines: tuple[int, ...] = (1, 2, 3),
    ) -> Path:
        macro_path = self.cwd / ".aippocampus" / "macro-orientation.jsonl"
        entry = macro_state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="乾",
            changing_lines=changing_lines,
            source_refs=({"source_id": f"default-macro-{active_layer}"},),
            updated_at="2026-06-11T10:00:00Z",
            active_layer=active_layer,
            momentum={"basis": {"counter_evidence_delta": 0.2}},
        )
        macro_state.append_macro_orientation_state(macro_path, entry)
        return macro_path

    def test_recall_returns_compact_packet_and_deepens_only_on_request(self) -> None:
        report = agent_continuity.recall(
            "agent-native recall opt-in SECRET_TOKEN=abc123",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            max_routes=3,
        )
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(report["kind"], "aippocampus_agent_continuity_path")
        self.assertEqual(report["mode"], "recall")
        self.assertTrue(report["opt_in_required"])
        self.assertEqual(report["status"], "ok")
        self.assertFalse(report["policy_boundary"]["default_hook_foreground"])
        self.assertTrue(report["policy_boundary"]["source_reopen_required_for_strong_claims"])
        self.assertEqual(report["metrics"]["foreground_forbidden_key_count"], 0)
        self.assertEqual(report["metrics"]["blind_deepen_required_count"], 0)
        self.assertGreaterEqual(report["metrics"]["top_route_selection_hint_present_count"], 1)
        self.assertGreaterEqual(report["metrics"]["topic_label_present_count"], 1)
        self.assertEqual(report["red_lines"]["foreground_source_dump_count"], 0)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("source_id", encoded)
        self.assertNotIn("msg_final", encoded)
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("SECRET_TOKEN", encoded)

        topic_packet = next(
            packet for packet in report["memory_packets"] if packet.get("route_topic")
        )
        self.assertTrue(topic_packet["route_label"])
        self.assertTrue(topic_packet["route_topic"])
        self.assertNotEqual(
            topic_packet["display_hint"],
            "A source route may matter; reopen it before using the detail.",
        )

        deepen_request = report["deepen_requests"][0]
        packet = next(
            packet
            for packet in report["memory_packets"]
            if packet["route_id"] == deepen_request["route_id"]
        )
        self.assertEqual(packet["kind"], "aippocampus_memory_packet")
        self.assertEqual(packet["claim_permission"], "no_claim_before_reopen")
        self.assertIn(packet["next_action"], {"reopen_source", "use_hint"})
        self.assertTrue(packet["deepen_route_id"].startswith("deepen:"))
        self.assertTrue(packet["route_label"])

        self.assertEqual(deepen_request["route_id"], packet["route_id"])
        self.assertTrue(deepen_request["deepen_route_id_display_only"])
        self.assertEqual(deepen_request["callable_handle"], deepen_request["handle"])
        self.assertEqual(deepen_request["callable_handle_field"], "deepen_requests[].handle")
        self.assertIn(deepen_request["handle"], deepen_request["copy_paste_command"])
        self.assertEqual(report["suggested_next_command"], deepen_request["copy_paste_command"])
        self.assertNotIn("source_refs", json.dumps(deepen_request, ensure_ascii=False))

        deepened = agent_continuity.deepen(
            deepen_request["handle"],
            cwd=self.cwd,
            clean_source_dir=self.clean,
        )
        self.assertEqual(deepened["mode"], "deepen")
        self.assertEqual(deepened["surface"], "recall")
        self.assertEqual(deepened["result"]["evidence_level"], "source_backed")
        self.assertIn("compact MemoryPacket", json.dumps(deepened, ensure_ascii=False))

    def test_topic_labels_distinguish_routes_that_share_broad_scope_bucket(self) -> None:
        rows = [
            {
                "message_id": "msg_benchmark",
                "turn_id": "turn_benchmark",
                "source_line": 10,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 10,
                "is_final": True,
                "scope_labels": ["technical_work"],
                "text": "Benchmark claim posture should use measured_result, supports, limits, and avoid over-conservative cannot_claim wording.",
            },
            {
                "message_id": "msg_issue",
                "turn_id": "turn_issue",
                "source_line": 11,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 11,
                "is_final": True,
                "scope_labels": ["technical_work"],
                "text": "Issue backlog interpretation should separate roadmap seeds, active issues, milestone cleanup, and planning queue triage.",
            },
            {
                "message_id": "msg_eval",
                "turn_id": "turn_eval",
                "source_line": 12,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 12,
                "is_final": True,
                "scope_labels": ["technical_work"],
                "text": "Developer assessment and second-user evaluation comments should be kept separate from benchmark proof.",
            },
        ]
        with (self.clean / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        report = agent_continuity.recall(
            "technical work route labels for benchmark, issue backlog, and developer evaluation",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            max_routes=5,
        )
        packets = report["memory_packets"]
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        topics = {packet.get("route_topic") for packet in packets}

        self.assertIn("benchmark_claim_posture", topics)
        self.assertIn("issue_backlog_interpretation", topics)
        self.assertIn("developer_assessment", topics)
        self.assertGreaterEqual(report["metrics"]["topic_label_present_count"], 3)
        self.assertEqual(report["metrics"]["blind_deepen_required_count"], 0)
        self.assertGreaterEqual(report["metrics"]["packet_triage_distinctiveness"], 0.75)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("msg_benchmark", encoded)
        self.assertNotIn(str(self.cwd), encoded)

    def test_attention_router_projection_reorders_existing_routes_only(self) -> None:
        routes = [
            {
                "route_id": "route_generic",
                "kind": "source_ref",
                "handle": "handle:generic",
                "route_label": "generic technical route",
                "route_topic": "",
                "source_refs": [
                    {"source_id": "src_generic", "message_id": "msg_generic", "line": 10}
                ],
            },
            {
                "route_id": "route_attention",
                "kind": "source_ref",
                "handle": "handle:attention",
                "route_label": "attention router score fusion route",
                "route_topic": "attention_router",
                "source_refs": [
                    {"source_id": "src_attention", "message_id": "msg_attention", "line": 12}
                ],
                "triage_rank_reason_codes": ["attention_router_route_selection"],
            },
        ]

        reordered, diagnostics = attention_route_projection.rerank_routes_with_attention_router(
            query="attention router score fusion hard masks route selection",
            routes=routes,
            max_routes=2,
        )
        encoded = json.dumps(diagnostics, ensure_ascii=False, sort_keys=True)

        self.assertEqual(reordered[0]["route_id"], "route_attention")
        self.assertEqual(reordered[1]["route_id"], "route_generic")
        self.assertTrue(diagnostics["applied"])
        self.assertTrue(diagnostics["top_route_changed"])
        self.assertEqual(diagnostics["ranked_route_count"], 2)
        self.assertTrue(diagnostics["boundary"]["attention_score_is_not_evidence"])
        self.assertTrue(diagnostics["boundary"]["source_reopen_required_for_claims"])
        self.assertNotIn("source_handles", encoded)
        self.assertNotIn("head_votes", encoded)
        self.assertNotIn("src_attention", encoded)

    def test_recall_can_opt_into_attention_router_route_selection(self) -> None:
        routes = [
            {
                "route_id": "route_generic",
                "kind": "source_ref",
                "handle": "handle:generic",
                "route_label": "generic technical route",
                "route_topic": "",
                "source_refs": [
                    {"source_id": "src_generic", "message_id": "msg_generic", "line": 10}
                ],
            },
            {
                "route_id": "route_attention",
                "kind": "source_ref",
                "handle": "handle:attention",
                "route_label": "attention router score fusion route",
                "route_topic": "attention_router",
                "source_refs": [
                    {"source_id": "src_attention", "message_id": "msg_attention", "line": 12}
                ],
                "triage_rank_reason_codes": ["attention_router_route_selection"],
            },
        ]
        fake_packet = {
            "kind": "aippocampus_recall_context",
            "status": "ok",
            "routes": routes,
            "route_count": len(routes),
        }

        with patch.object(agent_continuity, "recall_context_packet", return_value=fake_packet):
            default_report = agent_continuity.recall(
                "attention router score fusion route selection",
                cwd=self.cwd,
                clean_source_dir=self.clean,
                max_routes=2,
            )
            routed_report = agent_continuity.recall(
                "attention router score fusion route selection",
                cwd=self.cwd,
                clean_source_dir=self.clean,
                max_routes=2,
                attention_router=True,
            )

        encoded = json.dumps(routed_report, ensure_ascii=False, sort_keys=True)
        self.assertEqual(default_report["memory_packets"][0]["route_id"], "route_generic")
        self.assertFalse(default_report["attention_router_navigation"]["enabled"])
        self.assertEqual(default_report["attention_router_navigation"]["policy"]["mode"], "off")
        self.assertEqual(routed_report["memory_packets"][0]["route_id"], "route_attention")
        self.assertTrue(routed_report["attention_router_navigation"]["enabled"])
        self.assertEqual(routed_report["attention_router_navigation"]["policy"]["mode"], "on")
        self.assertTrue(routed_report["attention_router_navigation"]["top_route_changed"])
        self.assertEqual(
            routed_report["memory_packets"][0]["selection_hint"]["source"],
            "attention_router",
        )
        self.assertIn(
            "attention_router_top_route_changed",
            routed_report["memory_packets"][0]["route_delta_reason_codes"],
        )
        self.assertEqual(
            routed_report["memory_packets"][0]["recommended_next"],
            "deepen_this_route_first",
        )
        self.assertTrue(routed_report["metrics"]["attention_router_applied"])
        self.assertEqual(routed_report["metrics"]["attention_router_ranked_route_count"], 2)
        self.assertEqual(routed_report["metrics"]["foreground_forbidden_key_count"], 0)
        self.assertEqual(routed_report["red_lines"]["source_backed_claim_without_reopen"], 0)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("source_handles", encoded)
        self.assertNotIn("head_votes", encoded)
        self.assertNotIn("src_attention", encoded)

    def test_attention_router_auto_mode_uses_explicit_recall_gate(self) -> None:
        fake_packet = {
            "kind": "aippocampus_recall_context",
            "status": "ok",
            "routes": [
                {
                    "route_id": "route_generic",
                    "kind": "source_ref",
                    "handle": "handle:generic",
                    "route_label": "generic technical route",
                    "source_refs": [{"source_id": "src_generic", "message_id": "msg_generic"}],
                },
                {
                    "route_id": "route_attention",
                    "kind": "source_ref",
                    "handle": "handle:attention",
                    "route_label": "attention router score fusion route",
                    "route_topic": "attention_router",
                    "source_refs": [
                        {"source_id": "src_attention", "message_id": "msg_attention"}
                    ],
                },
            ],
        }

        with patch.object(agent_continuity, "recall_context_packet", return_value=fake_packet):
            report = agent_continuity.recall(
                "attention router score fusion route selection",
                cwd=self.cwd,
                clean_source_dir=self.clean,
                max_routes=2,
                attention_router="auto",
            )

        policy = report["attention_router_navigation"]["policy"]
        self.assertEqual(policy["mode"], "auto")
        self.assertTrue(policy["promotion_gate_checked"])
        self.assertTrue(policy["default_adoption_allowed"])
        self.assertTrue(report["attention_router_navigation"]["enabled"])
        self.assertEqual(report["memory_packets"][0]["route_id"], "route_attention")
        self.assertTrue(report["attention_router_navigation"]["top_route_changed"])
        self.assertNotIn("fixture_only_not_live_default_path", policy["promotion_blockers"])

    def test_attention_router_auto_mode_fails_closed_when_gate_blocks(self) -> None:
        fake_packet = {
            "kind": "aippocampus_recall_context",
            "status": "ok",
            "routes": [
                {
                    "route_id": "route_generic",
                    "kind": "source_ref",
                    "handle": "handle:generic",
                    "route_label": "generic technical route",
                    "source_refs": [{"source_id": "src_generic", "message_id": "msg_generic"}],
                },
                {
                    "route_id": "route_attention",
                    "kind": "source_ref",
                    "handle": "handle:attention",
                    "route_label": "attention router score fusion route",
                    "route_topic": "attention_router",
                    "source_refs": [
                        {"source_id": "src_attention", "message_id": "msg_attention"}
                    ],
                },
            ],
        }
        blocked_gate = {
            "surface": "explicit_agent_recall",
            "gate_ok": False,
            "public_quality_gate_ok": False,
            "default_adoption_gate_ok": False,
            "promotion_decision": "not_promoted",
            "blockers": ["safety_red_line_present"],
            "metrics": {},
        }

        with (
            patch.object(agent_continuity, "recall_context_packet", return_value=fake_packet),
            patch.object(
                agent_continuity.attention_router_policy,
                "explicit_recall_auto_gate",
                return_value=blocked_gate,
            ),
        ):
            report = agent_continuity.recall(
                "attention router score fusion route selection",
                cwd=self.cwd,
                clean_source_dir=self.clean,
                max_routes=2,
                attention_router="auto",
            )

        policy = report["attention_router_navigation"]["policy"]
        self.assertEqual(policy["mode"], "auto")
        self.assertTrue(policy["promotion_gate_checked"])
        self.assertFalse(policy["default_adoption_allowed"])
        self.assertFalse(report["attention_router_navigation"]["enabled"])
        self.assertEqual(report["memory_packets"][0]["route_id"], "route_generic")
        self.assertIn("safety_red_line_present", policy["promotion_blockers"])

    def test_macro_applied_recall_exposes_compact_route_delta_hint(self) -> None:
        fake_packet = {
            "kind": "aippocampus_recall_context",
            "status": "ok",
            "routes": [
                {
                    "route_id": "route_macro",
                    "kind": "source_ref",
                    "handle": "handle:macro",
                    "route_label": "project architecture route",
                    "route_topic": "architecture_validation",
                    "source_refs": [{"source_id": "src_macro", "message_id": "msg_macro"}],
                }
            ],
        }
        macro_path = self._macro_state_path(
            active_layer="人",
            momentum={"basis": {"support_delta": 0.2}},
        )

        with patch.object(agent_continuity, "recall_context_packet", return_value=fake_packet):
            report = agent_continuity.recall(
                "继续架构验收，判断下一步该查哪条产品路径",
                cwd=self.cwd,
                clean_source_dir=self.clean,
                macro_state_path=macro_path,
                max_routes=1,
            )

        packet = report["memory_packets"][0]
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        self.assertTrue(report["macro_navigation"]["applied"])
        self.assertEqual(packet["selection_hint"]["source"], "macro_orientation")
        self.assertIn("macro_orientation_recall_prior", packet["route_delta_reason_codes"])
        self.assertIn("macro_active_layer", packet["selection_hint"]["why"])
        self.assertEqual(packet["recommended_next"], "deepen_this_route_first")
        self.assertNotIn("src_macro", encoded)
        self.assertNotIn("source_refs", encoded)

    def test_stale_and_malformed_deepen_cannot_verify(self) -> None:
        recall = agent_continuity.recall(
            "agent-native recall opt-in",
            cwd=self.cwd,
            clean_source_dir=self.clean,
        )
        handle = recall["deepen_requests"][0]["handle"]

        with (self.clean / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {
                        "message_id": "msg_later",
                        "turn_id": "turn_2",
                        "source_line": 9,
                        "role": "assistant",
                        "phase": "final_answer",
                        "turn_index": 2,
                        "is_final": True,
                        "text": "Later source should stale the old agent-continuity handle.",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        stale = agent_continuity.deepen(handle, cwd=self.cwd, clean_source_dir=self.clean)
        encoded_stale = json.dumps(stale, ensure_ascii=False)
        self.assertEqual(stale["status"], "cannot_verify")
        self.assertEqual(stale["result"]["error"]["code"], "stale_recall_handle")
        self.assertNotIn("Later source", encoded_stale)

        malformed = agent_continuity.deepen(
            "not-a-navigation-handle",
            cwd=self.cwd,
            clean_source_dir=self.clean,
        )
        self.assertEqual(malformed["status"], "cannot_verify")
        self.assertEqual(malformed["result"]["error"]["code"], "malformed_recall_handle")
        self.assertIn("deepen_requests[].handle", malformed["result"]["error"]["message"])
        self.assertIn("source_backed_claim", malformed["cannot_claim"])

        route_id_misuse = agent_continuity.deepen(
            recall["memory_packets"][0]["deepen_route_id"],
            cwd=self.cwd,
            clean_source_dir=self.clean,
        )
        self.assertEqual(route_id_misuse["status"], "cannot_verify")
        self.assertEqual(route_id_misuse["result"]["error"]["code"], "malformed_recall_handle")
        self.assertEqual(
            route_id_misuse["result"]["error"]["details"]["callable_handle_field"],
            "deepen_requests[].handle",
        )

    def test_macro_orientation_changes_live_recall_fanout_and_ordering(self) -> None:
        self._append_clean_rows(
            [
                {
                    "message_id": "macro_benchmark",
                    "turn_id": "turn_macro_benchmark",
                    "source_line": 20,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 20,
                    "is_final": True,
                    "scope_labels": ["technical_work"],
                    "text": "Macro route shared cue benchmark evidence fixture quality gate measured result.",
                },
                {
                    "message_id": "macro_issue",
                    "turn_id": "turn_macro_issue",
                    "source_line": 21,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 21,
                    "is_final": True,
                    "scope_labels": ["technical_work"],
                    "text": "Macro route shared cue issue backlog workflow handoff project triage next action.",
                },
                {
                    "message_id": "macro_roadmap",
                    "turn_id": "turn_macro_roadmap",
                    "source_line": 22,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 22,
                    "is_final": True,
                    "scope_labels": ["technical_work"],
                    "text": "Macro route shared cue roadmap north star product claim direction thesis.",
                },
            ]
        )
        human_path = self._macro_state_path(active_layer="人")
        earth_path = self._macro_state_path(active_layer="地")

        baseline = agent_continuity.recall(
            "macro route shared cue",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            max_routes=2,
        )
        human = agent_continuity.recall(
            "macro route shared cue",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            max_routes=2,
            macro_state_path=human_path,
        )
        earth = agent_continuity.recall(
            "macro route shared cue",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            max_routes=2,
            macro_state_path=earth_path,
        )
        encoded = json.dumps(human, ensure_ascii=False, sort_keys=True)

        self.assertFalse(baseline["metrics"]["macro_orientation_applied"])
        self.assertTrue(human["metrics"]["macro_orientation_applied"])
        self.assertGreater(human["metrics"]["effective_max_routes"], 2)
        self.assertGreater(len(human["memory_packets"]), len(baseline["memory_packets"]))
        self.assertEqual(human["macro_navigation"]["active_layer"], "human")
        self.assertEqual(earth["macro_navigation"]["active_layer"], "earth")
        self.assertEqual(human["memory_packets"][0]["route_topic"], "issue_backlog_interpretation")
        self.assertEqual(earth["memory_packets"][0]["route_topic"], "benchmark_claim_posture")
        self.assertIn("macro_active_layer_human", encoded)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("macro-live", encoded)

    def test_recall_uses_default_scoped_macro_state_without_manual_path(self) -> None:
        self._append_clean_rows(
            [
                {
                    "message_id": "default_macro_benchmark",
                    "turn_id": "turn_default_macro_benchmark",
                    "source_line": 40,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 40,
                    "is_final": True,
                    "scope_labels": ["technical_work"],
                    "text": "Default macro shared cue benchmark evidence fixture quality gate measured result.",
                },
                {
                    "message_id": "default_macro_issue",
                    "turn_id": "turn_default_macro_issue",
                    "source_line": 41,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 41,
                    "is_final": True,
                    "scope_labels": ["technical_work"],
                    "text": "Default macro shared cue issue backlog workflow handoff project triage next action.",
                },
            ]
        )
        macro_path = self._append_default_macro_state(active_layer="地")

        report = agent_continuity.recall(
            "default macro shared cue",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            max_routes=2,
        )
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["metrics"]["macro_orientation_applied"])
        self.assertEqual(report["macro_navigation"]["status"], "applied")
        self.assertEqual(report["macro_navigation"]["active_layer"], "earth")
        self.assertGreater(report["metrics"]["effective_max_routes"], 2)
        self.assertIn("momentum_first_decay_recheck", report["macro_navigation"]["recheck_on"])
        self.assertEqual(report["memory_packets"][0]["route_topic"], "benchmark_claim_posture")
        self.assertNotIn(str(macro_path), encoded)
        self.assertNotIn("default-macro", encoded)
        self.assertNotIn("source_refs", encoded)

    def test_macro_momentum_recheck_stays_diagnostic_not_evidence(self) -> None:
        self._append_clean_rows(
            [
                {
                    "message_id": "macro_recheck_issue",
                    "turn_id": "turn_macro_recheck",
                    "source_line": 30,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 30,
                    "is_final": True,
                    "text": "Momentum recheck route issue workflow currentness before closeout.",
                }
            ]
        )
        macro_path = self._macro_state_path(
            active_layer="人",
            momentum={"basis": {"counter_evidence_delta": 0.2}},
        )

        recall = agent_continuity.recall(
            "momentum recheck issue workflow",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            max_routes=2,
            macro_state_path=macro_path,
        )
        handle = recall["deepen_requests"][0]["handle"]
        explanation = agent_continuity.explain(handle, macro_state_path=macro_path)
        deepened = agent_continuity.deepen(
            handle,
            cwd=self.cwd,
            clean_source_dir=self.clean,
            macro_state_path=macro_path,
        )

        self.assertEqual(recall["macro_navigation"]["authority_level"], "navigation_only")
        self.assertIn("momentum_first_decay_recheck", recall["macro_navigation"]["recheck_on"])
        self.assertIn(
            "macro_momentum_recheck",
            explanation["explanation"]["reason_codes"],
        )
        self.assertEqual(
            explanation["explanation"]["claim_permission"],
            "no_claim_before_reopen",
        )
        self.assertEqual(
            deepened["macro_navigation_diagnostics"]["claim_permission"],
            "no_claim_before_reopen",
        )
        self.assertFalse(deepened["macro_navigation_diagnostics"]["fact_claim_allowed"])

    def test_explain_is_public_safe(self) -> None:
        recall = agent_continuity.recall(
            "agent-native recall opt-in",
            cwd=self.cwd,
            clean_source_dir=self.clean,
        )
        handle = recall["deepen_requests"][0]["handle"]

        explanation = agent_continuity.explain(handle)
        encoded = json.dumps(explanation, ensure_ascii=False, sort_keys=True)

        self.assertEqual(explanation["kind"], "aippocampus_agent_continuity_path")
        self.assertEqual(explanation["mode"], "explain")
        self.assertEqual(explanation["surface"], "recall")
        self.assertEqual(explanation["explanation"]["next_safe_action"], "reopen_source")
        self.assertIn("reopenable_route_available", explanation["explanation"]["reason_codes"])
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("msg_final", encoded)

    def test_aippo_activation_deepen_explain_and_feedback_stay_low_authority(self) -> None:
        activation = agent_continuity.activate_aippo(task="coding issue closeout")
        encoded_activation = json.dumps(activation, ensure_ascii=False, sort_keys=True)

        self.assertEqual(activation["kind"], "aippocampus_agent_continuity_path")
        self.assertEqual(activation["mode"], "aippo")
        self.assertEqual(activation["activation_packet"]["kind"], "aippocampus_aippo_activation_packet")
        self.assertIn("coding", activation["activation_packet"]["task_families"])
        self.assertTrue(activation["activation_packet"]["use_guidance"])
        self.assertEqual(activation["metrics"]["generic_safety_posture_only_count"], 0)
        self.assertGreaterEqual(
            activation["metrics"]["low_risk_guidance_allowed_without_reopen_count"],
            1,
        )
        self.assertTrue(activation["metrics"]["usefulness_gate_ok"])
        self.assertEqual(
            activation["activation_packet"]["claim_permission"],
            "working_contract_allowed_no_fact_claim",
        )
        self.assertNotIn("source_refs", encoded_activation)
        self.assertNotIn("candidate_provenance", encoded_activation)
        self.assertEqual(activation["red_lines"]["stale_clause_activated_as_current"], 0)

        deepened = agent_continuity.deepen(
            activation["activation_packet"]["deepen_route_id"],
            cwd=self.cwd,
            clean_source_dir=self.clean,
        )
        self.assertEqual(deepened["surface"], "aippo")
        self.assertGreater(
            deepened["result"]["source_support_ledger"]["source_ref_count"],
            0,
        )
        self.assertFalse(deepened["result"]["candidate_provenance"]["candidate_inputs_are_truth"])

        explanation = agent_continuity.explain(activation["activation_packet"]["deepen_route_id"])
        self.assertEqual(explanation["surface"], "aippo")
        self.assertIn(
            "candidate_surfaces_are_navigation_not_truth",
            explanation["explanation"]["reason_codes"],
        )

        receipt = agent_continuity.capture_feedback(
            route_id=activation["activation_packet"]["aippo_id"],
            outcome="source_reopen_success",
            route_kind="active_path",
            reason="user accepted after source reopen",
        )
        self.assertEqual(receipt["mode"], "feedback")
        self.assertEqual(receipt["authority"], "low_authority_feedback_signal")
        self.assertEqual(receipt["red_lines"]["feedback_promoted_without_source"], 0)
        self.assertTrue(receipt["policy_boundary"]["source_reopen_required_for_claims"])

    def test_cli_agent_recall_outputs_json(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "recall",
                "agent-native recall opt-in",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
                "--json",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertEqual(payload["mode"], "recall")
        self.assertEqual(payload["memory_packets"][0]["kind"], "aippocampus_memory_packet")
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn(str(self.cwd), encoded)

    def test_cli_agent_recall_default_output_is_compact_human_frontstage(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "recall",
                "agent-native recall opt-in",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("AIppocampus agent recall: ok", proc.stdout)
        self.assertIn("Next: call agent_deepen", proc.stdout)
        self.assertIn("Boundary: route only", proc.stdout)
        self.assertNotIn('"memory_packets"', proc.stdout)
        self.assertNotIn("source_refs", proc.stdout)
        self.assertNotIn(str(self.cwd), proc.stdout)

    def test_cli_agent_recall_auto_attention_reports_promotion_blockers(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "recall",
                "attention router score fusion route selection",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
                "--attention-router-mode",
                "auto",
                "--json",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        policy = payload["attention_router_navigation"]["policy"]
        self.assertEqual(policy["mode"], "auto")
        self.assertTrue(policy["default_adoption_allowed"])
        self.assertEqual(policy["promotion_blockers"], [])

    def test_cli_agent_aippo_task_selects_useful_clause_family(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "aippo",
                "--task",
                "benchmark reporting issue closeout",
                "--json",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        packet = payload["activation_packet"]
        encoded = json.dumps(packet, ensure_ascii=False, sort_keys=True)

        self.assertEqual(payload["mode"], "aippo")
        self.assertIn("benchmark_reporting", packet["task_families"])
        self.assertIn("measured results", " ".join(packet["use_guidance"]))
        self.assertTrue(payload["metrics"]["usefulness_gate_ok"])
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("candidate_provenance", encoded)

    def test_cli_agent_macro_outputs_compact_packet(self) -> None:
        macro_path = self.cwd / "macro-orientation.jsonl"
        entry = macro_state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="乾",
            changing_lines=(1,),
            source_refs=({"source_id": "macro-cli-source"},),
            updated_at="2026-06-11T10:00:00Z",
        )
        macro_state.append_macro_orientation_state(macro_path, entry)
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "macro",
                "--project",
                "AIppocampus",
                "--macro-state-jsonl",
                str(macro_path),
                "--json",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertEqual(payload["mode"], "macro")
        self.assertEqual(
            payload["memory_packets"][0]["packet_kind"],
            "macro_orientation_packet",
        )
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("macro-cli-source", encoded)


if __name__ == "__main__":
    unittest.main()
