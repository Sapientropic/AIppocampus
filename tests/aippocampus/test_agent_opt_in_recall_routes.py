from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime.contracts import (
    foreground_action_contract_violations,
)
from aippocampus_runtime.macro import state as macro_state
from aippocampus_runtime.navigation import attention_route_projection
from aippocampus_runtime.recall import (
    agent_continuity,
    agent_continuity_cli_support,
    agent_recall_pipeline,
    agent_recall_primitives,
    background_findings,
    feedback_events,
)
from aippocampus_runtime.recall import (
    agent_facade_contract as facade,
)
from aippocampus_runtime.registry import api as registry_api
from tests.aippocampus.product_probe_helpers import (
    SourceOpenExpectation,
    assert_deepen_opened_expected_source,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"

class AgentOptInRecallRoutesTests(unittest.TestCase):
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

    def assertCanonicalForegroundAction(self, payload: dict[str, object]) -> None:
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertIsInstance(payload["foreground_action"], dict)
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn("next_safe_action", payload)
        self.assertNotIn(payload["foreground_action"], payload.get("safe_next_actions", []))
        self.assertEqual(foreground_action_contract_violations(payload), [])

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
            updated_at=macro_state.utc_now_iso(),
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
            updated_at=macro_state.utc_now_iso(),
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
        compact_report = agent_continuity_cli_support.public_recall_projection(
            {**report, "last_recall_cache_available": True}
        )
        encoded = json.dumps(compact_report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(report["kind"], "aippocampus_agent_continuity_path")
        self.assertEqual(report["mode"], "recall")
        self.assertFalse(report["opt_in_required"])
        self.assertEqual(report["schema_version"], "agent-continuity-path-v1")
        self.assertEqual(report["policy_boundary"]["activation_model"], "explicit_foreground_action")
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["foreground_action_card"]["decision"], "use_route_first")
        self.assertEqual(report["foreground_action_card"]["next_action"], "deepen")
        self.assertEqual(
            report["foreground_action_card"]["claim_boundary"],
            "no_claim_before_reopen",
        )
        self.assertTrue(report["audit_available"])
        self.assertFalse(report["policy_boundary"]["default_hook_foreground"])
        self.assertTrue(report["policy_boundary"]["source_reopen_required_for_strong_claims"])
        self.assertEqual(report["metrics"]["foreground_forbidden_key_count"], 0)
        self.assertEqual(report["metrics"]["foreground_action_card_audit_key_leak_count"], 0)
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
        self.assertNotIn("copy_paste_command", deepen_request)
        self.assertIn(
            "--request 1 --recall-selector {recall_selector} --json",
            deepen_request["copy_paste_command_template"],
        )
        self.assertIn("--last-recall --json", deepen_request["last_recall_fallback_command"])
        self.assertIn(deepen_request["handle"], deepen_request["private_handle_command"])
        self.assertIsNone(report["suggested_next_command"])
        self.assertNotIn("source_refs", json.dumps(deepen_request, ensure_ascii=False))

        deepened = agent_continuity.deepen(
            deepen_request["handle"],
            cwd=self.cwd,
            clean_source_dir=self.clean,
        )
        self.assertEqual(deepened["mode"], "deepen")
        self.assertEqual(deepened["surface"], "recall")
        self.assertEqual(deepened["result"]["evidence_level"], "source_backed")
        assert_deepen_opened_expected_source(
            self,
            deepened,
            SourceOpenExpectation(window_terms=("compact MemoryPacket",)),
        )

    def test_human_recall_does_not_print_opaque_aippo_nav_handle(self) -> None:
        long_handle = "aippo-nav:" + ("x" * 540)
        fake_packet = {
            "kind": "aippocampus_recall_context",
            "status": "ok",
            "routes": [
                {
                    "route_id": "route_long_handle",
                    "kind": "source_ref",
                    "handle": long_handle,
                    "route_label": "long opaque navigation handle route",
                    "source_refs": [{"source_id": "src_long", "message_id": "msg_long"}],
                }
            ],
        }

        with patch.object(agent_recall_pipeline, "recall_context_packet", return_value=fake_packet):
            report = agent_continuity.recall(
                "topology attention router macro sheaf callable handle UX",
                cwd=self.cwd,
                clean_source_dir=self.clean,
                max_routes=1,
            )

        human = agent_continuity_cli_support.render_recall_human(report)
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertIn(long_handle, encoded)
        self.assertEqual(report["deepen_requests"][0]["handle"], long_handle)
        self.assertIn("handle_preview", report["deepen_requests"][0])
        self.assertIn("handle_sha256_12", report["deepen_requests"][0])
        self.assertIn("Next:", human)
        self.assertNotIn("aippocampus agent deepen --request 1 --last-recall --json", human)
        self.assertIn("private_handle_command", report["deepen_requests"][0])
        self.assertNotIn(long_handle, human)
        self.assertNotIn("aippo-nav:", human)
        self.assertLess(max(len(line) for line in human.splitlines()), 180)

    def test_public_recall_json_marks_and_omits_local_private_handles(self) -> None:
        report = agent_continuity.recall(
            "agent-native recall opt-in",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            max_routes=1,
        )
        public = agent_continuity_cli_support.public_recall_projection(
            {**report, "last_recall_cache_available": True}
        )

        encoded = json.dumps(public, ensure_ascii=False)
        action = public["foreground_action"]
        self.assertEqual(public["surface"], "agent_cli_public_compact")
        self.assertEqual(action["tool_name"], "agent_deepen")
        self.assertEqual(action["arguments"]["request_index"], 1)
        self.assertNotIn("last_recall", action["arguments"])
        self.assertIn("--recall-selector {recall_selector}", action["command_template"])
        self.assertEqual(action["requires"], ["recall_selector"])
        self.assertIn("--last-recall", action["last_recall_fallback_command"])
        self.assertNotIn("handle_boundary", public)
        self.assertNotIn("local_private_fields", public)
        self.assertNotIn("output_boundary", public)
        self.assertNotIn("action_boundary", public)
        self.assertNotIn("metrics", public)
        self.assertNotIn("audit_available", public)
        self.assertNotIn("suggested_next_command", public)
        self.assertCanonicalForegroundAction(public)
        self.assertNotIn("public_safe_command_preview", public)
        self.assertNotIn("public_safe_recall_command", public)
        self.assertNotIn("foreground_action_card", public)
        self.assertNotIn("deepen_requests", public)
        self.assertNotIn("memory_packets", public)
        self.assertNotIn("macro_navigation", public)
        self.assertNotIn("attention_router_navigation", public)
        self.assertNotIn("aippo-nav:", encoded)
        self.assertLess(len(encoded.encode("utf-8")), 4096)

    def test_agent_background_projects_reviewed_dream_finding_as_navigation_handle(self) -> None:
        working_memory = self.cwd / "working_memory.jsonl"
        working_memory.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_working_memory",
                    "status": "active",
                    "route": "use_with_source",
                    "candidate_type": "dream_hypothesis",
                    "candidate_key": "wm_dream_continuity",
                    "title": "Continuity route bridge",
                    "summary": "Use only as a route hint.",
                    "trigger_terms": ["continuity source refs"],
                    "source_finding_ids": ["dreamfinding_continuity"],
                    "source_refs": [{"thread_key": "session:a", "message_id": "msg-a", "line": 10}],
                    "confidence": 0.7,
                    "project_label": "AIppocampus",
                    "review_state": "agent_adjudicated",
                    "truth_boundary": "adjudicated_dream_hypothesis_not_fact",
                    "sensitive_use_gate": {"state": "allowed"},
                    "foreground_use": {"strong_claim_requires_source_reopen": True},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        payload = background_findings.background_findings_card(
            "AIppocampus continuity source refs",
            working_memory_path=working_memory,
        )
        full_payload = background_findings.background_findings_card(
            "AIppocampus continuity source refs",
            working_memory_path=working_memory,
            detail="full",
        )

        encoded = json.dumps([payload, full_payload], ensure_ascii=False)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["finding_count"], 1)
        self.assertNotIn("findings", payload)
        self.assertEqual(payload["best_finding"]["finding_id"], "wm_dream_continuity")
        self.assertEqual(payload["best_finding"]["surface"], "dream_working_memory")
        self.assertCanonicalForegroundAction(payload)
        finding = full_payload["findings"][0]
        self.assertEqual(finding["finding_id"], "wm_dream_continuity")
        self.assertEqual(finding["surface"], "dream_working_memory")
        self.assertEqual(finding["boundary"]["action_grammar"], "reopenable_route")
        self.assertFalse(finding["boundary"]["source_backed_claim_allowed"])
        self.assertTrue(finding["source"]["source_reopen_required_before_claims"])
        self.assertFalse(finding["source"]["raw_source_refs_emitted"])
        self.assertEqual(
            payload["foreground_action"]["id"],
            "reopen_background_finding_source_route",
        )
        self.assertIn("dreamfinding_continuity", payload["foreground_action"]["command"])
        self.assertEqual(
            payload["foreground_action"]["target"]["finding_id"],
            "wm_dream_continuity",
        )
        self.assertNotIn(
            "materialize_action_hint_from_finding",
            {action["id"] for action in finding["next_actions"]},
        )
        self.assertNotIn("session:a", encoded)
        self.assertNotIn("msg-a", encoded)
        self.assertNotIn(str(working_memory), encoded)

    def test_public_recall_no_routes_returns_recovery_card_without_deepen_placeholder(self) -> None:
        empty_registry = self.cwd / "empty-registry"
        empty_registry.mkdir()
        (empty_registry / "threads.json").write_text(
            json.dumps({"schema_version": 1, "threads": []}),
            encoding="utf-8",
        )
        report = agent_continuity.recall(
            "unlikely-no-match-token-xyz-12345",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            registry_dir=empty_registry,
            max_routes=2,
        )
        public = agent_continuity_cli_support.public_recall_projection(
            {**report, "last_recall_cache_available": False}
        )
        encoded = json.dumps(public, ensure_ascii=False)

        self.assertEqual(public["status"], "no_routes")
        self.assertNotIn("route_count", public)
        self.assertNotIn("suggested_next_command", public)
        self.assertNotIn("public_safe_command_preview", public)
        self.assertNotIn("<local-private-handle>", encoded)
        self.assertNotIn("<", encoded)
        self.assertNotIn("agent deepen", encoded)
        self.assertCanonicalForegroundAction(public)
        self.assertEqual(public["foreground_action"]["id"], "recover_recall_miss")
        self.assertEqual(public["foreground_action"]["tool_name"], "search_memory")
        self.assertEqual(public["foreground_action"]["command_template"], 'aippocampus search "{exact_phrase}" --json')
        self.assertEqual(public["foreground_action"]["arguments_template"]["query"], "{exact_phrase}")
        self.assertEqual(public["foreground_action"]["requires"], ["exact_phrase"])
        self.assertEqual(public["miss_recovery_card"]["miss_class"], "no_route")
        self.assertIn("refine", " ".join(public["miss_recovery_card"]["recovery_actions"]))
        self.assertIn(
            "onboard --provider auto --status",
            " ".join(public["miss_recovery_card"]["recovery_actions"]),
        )

    def test_public_recall_weak_route_without_deepen_request_gets_recovery_card(self) -> None:
        public = agent_continuity_cli_support.public_recall_projection(
            {
                "kind": "aippocampus_agent_continuity_path",
                "schema_version": "agent-continuity-path-v1",
                "mode": "recall",
                "status": "ok",
                "opt_in_required": False,
                "foreground_action_card": {
                    "decision": "continue_normally",
                    "canonical_action": {
                        "action_id": "continue_normally",
                        "arguments": {},
                        "claim_boundary": "no_route_claim",
                    },
                },
                "memory_packets": [
                    {
                        "route_id": "route_weak",
                        "route_label": "broad direction-only route",
                        "route_kind": "direction_only",
                        "claim_permission": "no_claim_before_reopen",
                    }
                ],
                "deepen_requests": [],
                "metrics": {"memory_packet_count": 1, "deepen_request_count": 0},
            }
        )

        self.assertNotIn("route_count", public)
        self.assertCanonicalForegroundAction(public)
        self.assertEqual(public["foreground_action"]["id"], "recover_weak_route")
        self.assertEqual(public["weak_route_recovery_card"]["miss_class"], "weak_route")
        self.assertIn("exact search", " ".join(public["weak_route_recovery_card"]["recovery_actions"]))

    def test_recall_route_limit_rejects_explicit_zero_negative_and_overlarge(self) -> None:
        ok = agent_continuity.recall(
            "agent-native recall opt-in",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            max_routes=1,
        )

        self.assertEqual(ok["metrics"]["requested_max_routes"], 1)
        for value, message in [(0, "max must be >= 1"), (-1, "max must be >= 1"), (26, "max must be <= 25")]:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, message):
                agent_continuity.recall(
                    "agent-native recall opt-in",
                    cwd=self.cwd,
                    clean_source_dir=self.clean,
                    max_routes=value,
                )

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
        compact_report = agent_continuity_cli_support.public_recall_projection(
            {**report, "last_recall_cache_available": True}
        )
        encoded = json.dumps(compact_report, ensure_ascii=False, sort_keys=True)
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
                "route_hints": {
                    "topology_explain_only": {
                        "topology_shape": "local_global_glue",
                        "risk_reason_codes": ["local_global_obstruction"],
                    }
                },
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

    def test_attention_router_does_not_promote_lower_cue_fit_route(self) -> None:
        routes = [
            {
                "route_id": "route_exact",
                "kind": "source_ref",
                "handle": "handle:exact",
                "route_label": "mcp health compact json doctor config route",
                "route_topic": "mcp_health_doctor_config",
                "why_this_may_matter": "Matches the foreground MCP health compact JSON task.",
                "source_refs": [{"source_id": "src_exact", "message_id": "msg_exact"}],
            },
            {
                "route_id": "route_broad",
                "kind": "source_ref",
                "handle": "handle:broad",
                "route_label": "broad topology route",
                "route_topic": "topology_shape",
                "why_this_may_matter": "General architecture scent.",
                "source_refs": [{"source_id": "src_broad", "message_id": "msg_broad"}],
            },
        ]
        fake_packets = [
            {
                "route_id": "route_exact",
                "emitted": True,
                "output_mode": "reopenable_route",
                "router_diagnostics": {"score": 0.4, "reason_codes": []},
            },
            {
                "route_id": "route_broad",
                "emitted": True,
                "output_mode": "reopenable_route",
                "router_diagnostics": {"score": 0.95, "reason_codes": []},
            },
        ]

        with patch.object(
            attention_route_projection.attention_hot_router,
            "route_attention",
            return_value=fake_packets,
        ):
            reordered, diagnostics = (
                attention_route_projection.rerank_routes_with_attention_router(
                    query="mcp health compact json",
                    routes=routes,
                    max_routes=2,
                )
            )

        self.assertEqual(reordered[0]["route_id"], "route_exact")
        self.assertFalse(diagnostics["top_route_changed"])
        self.assertTrue(diagnostics["promotion_blocked_lower_cue_fit"])
        self.assertEqual(diagnostics["promotion_blocked_route_id"], "route_broad")
        self.assertGreater(diagnostics["selected_query_term_overlap_count"], 0)
        self.assertEqual(diagnostics["selected_route_id"], "route_exact")

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

        with patch.object(agent_recall_pipeline, "recall_context_packet", return_value=fake_packet):
            default_report = agent_continuity.recall(
                "attention router topology score fusion route selection",
                cwd=self.cwd,
                clean_source_dir=self.clean,
                max_routes=2,
            )
            routed_report = agent_continuity.recall(
                "attention router topology score fusion route selection",
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
        self.assertEqual(
            routed_report["navigation_signals"]["kind"],
            "architecture_navigation_affordance",
        )
        self.assertIn(
            "attention_router_top_route_changed",
            routed_report["navigation_signals"]["signals"],
        )
        self.assertIn(
            "topology_requested",
            routed_report["navigation_signals"]["signals"],
        )
        self.assertEqual(
            routed_report["navigation_signals"]["next_safe_action"],
            "deepen_selected_route",
        )
        human = agent_continuity_cli_support.render_recall_human(routed_report)
        self.assertIn("why: attention_router:top_route_changed", human)
        self.assertIn("Navigation:", human)
        self.assertNotIn("aippocampus agent deepen --request 1 --last-recall --json", human)
        self.assertTrue(routed_report["metrics"]["attention_router_applied"])
        self.assertEqual(routed_report["metrics"]["attention_router_ranked_route_count"], 2)
        self.assertEqual(routed_report["metrics"]["foreground_forbidden_key_count"], 0)
        self.assertEqual(routed_report["red_lines"]["source_backed_claim_without_reopen"], 0)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("source_handles", encoded)
        self.assertNotIn("head_votes", encoded)
        self.assertNotIn("src_attention", encoded)

    def test_recall_attention_router_consumes_feedback_jsonl(self) -> None:
        routes = [
            {
                "route_id": "route_stale",
                "route_kind": "active_path",
                "kind": "source_ref",
                "handle": "handle:stale",
                "route_label": "attention router stale drag route",
                "route_topic": "attention_router",
                "source_refs": [{"source_id": "src_stale", "message_id": "msg_stale"}],
            },
            {
                "route_id": "route_helpful",
                "route_kind": "active_path",
                "kind": "source_ref",
                "handle": "handle:helpful",
                "route_label": "attention router helpful reopen route",
                "route_topic": "attention_router",
                "source_refs": [{"source_id": "src_helpful", "message_id": "msg_helpful"}],
            },
        ]
        feedback_path = self.cwd / "feedback.jsonl"
        events = [
            feedback_events.active_flow_event(
                route_id=route_id,
                route_kind="active_path",
                signal=signal,
            )
            for route_id, signal in (
                ("route_helpful", "source_reopen_success"),
                ("route_helpful", "user_confirmed"),
                ("route_stale", "wrong_route_drag"),
                ("route_stale", "blocked"),
            )
        ]
        with feedback_path.open("w", encoding="utf-8", newline="\n") as handle:
            for event in events:
                handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            handle.write("{not json\n")
        fake_packet = {
            "kind": "aippocampus_recall_context",
            "status": "ok",
            "routes": routes,
            "route_count": len(routes),
        }

        with patch.object(agent_recall_pipeline, "recall_context_packet", return_value=fake_packet):
            report = agent_continuity.recall(
                "attention router route feedback calibration",
                cwd=self.cwd,
                clean_source_dir=self.clean,
                max_routes=2,
                attention_router=True,
                feedback_path=feedback_path,
            )

        diagnostics = report["attention_router_navigation"]["feedback_calibration"]
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        self.assertEqual(report["memory_packets"][0]["route_id"], "route_helpful")
        self.assertEqual(diagnostics["matched_route_count"], 2)
        self.assertEqual(diagnostics["positive_delta_count"], 1)
        self.assertEqual(diagnostics["negative_delta_count"], 1)
        self.assertEqual(
            report["metrics"]["attention_router_feedback_calibration_matched_count"],
            2,
        )
        self.assertIn("feedback_calibration_lift", encoded)
        self.assertNotIn(str(feedback_path), encoded)
        self.assertNotIn("source_open_token_ids", encoded)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("source_handles", encoded)
        self.assertNotIn("head_votes", encoded)
        self.assertNotIn("src_helpful", encoded)

    def test_last_recall_cache_preserves_dict_handles_as_json(self) -> None:
        cache_path = self.cwd / "last-recall-dict.json"
        handle_dict = {
            "kind": "thread_candidate",
            "route_id": "route_dict",
            "thread_key": "session:test",
        }

        wrote = agent_continuity_cli_support.write_last_recall_cache(
            [{"request_index": 1, "route_id": "route_dict", "handle": handle_dict}],
            cwd=self.cwd,
            clean_source_dir=self.clean,
            registry_dir=None,
            macro_state_path=None,
            project="AIppocampus",
            max_matches=1,
            schema_version=agent_continuity.SCHEMA_VERSION,
            path=cache_path,
        )
        handle, _context = agent_continuity_cli_support.handle_from_last_recall_cache(
            request_index=1,
            path=cache_path,
        )

        self.assertTrue(wrote)
        self.assertEqual(json.loads(handle), handle_dict)

    def test_legacy_last_recall_cache_dict_handle_still_reopens_as_json(self) -> None:
        cache_path = self.cwd / "last-recall-legacy-dict.json"
        handle_dict = {
            "kind": "source_ref",
            "route_id": "route_legacy_dict",
            "source_refs": [{"source_id": "src_test", "message_id": "msg_user"}],
        }
        cache_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_agent_last_recall",
                    "schema_version": agent_continuity.SCHEMA_VERSION,
                    "requests": [
                        {
                            "request_index": 1,
                            "route_id": "route_legacy_dict",
                            "handle": handle_dict,
                        }
                    ],
                    "context": {},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        handle, _context = agent_continuity_cli_support.handle_from_last_recall_cache(
            request_index=1,
            path=cache_path,
        )

        self.assertEqual(json.loads(handle), handle_dict)
        self.assertNotIn("'", handle)

    def test_last_recall_cache_marks_opened_routes_without_plaintext_handles(self) -> None:
        cache_path = self.cwd / "last-recall-opened.json"
        wrote = agent_continuity_cli_support.write_last_recall_cache(
            [
                {
                    "request_index": 1,
                    "route_id": "route_opened",
                    "handle": {
                        "route_id": "route_opened",
                        "message_id": "msg_private_handle",
                    },
                    "handle_sha256_12": "abc123abc123",
                }
            ],
            query="opened route cue",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            registry_dir=self.cwd / "registry",
            macro_state_path=None,
            project="AIppocampus",
            max_matches=5,
            schema_version=agent_continuity.SCHEMA_VERSION,
            path=cache_path,
        )

        marked = agent_continuity_cli_support.mark_last_recall_request_opened(
            1,
            path=cache_path,
        )
        cache = agent_continuity_cli_support.read_last_recall_cache(cache_path)
        encoded = cache_path.read_text(encoding="utf-8")

        self.assertTrue(wrote)
        self.assertTrue(marked)
        self.assertTrue(cache["requests"][0]["opened"])
        self.assertEqual(cache["opened_routes"][0]["route_id"], "route_opened")
        self.assertEqual(cache["opened_routes"][0]["handle_sha256_12"], "abc123abc123")
        self.assertIn(
            "route_opened|abc123abc123",
            agent_continuity_cli_support.opened_route_keys_from_last_recall_cache(cache_path),
        )
        self.assertIn(
            "route_opened|*",
            agent_continuity_cli_support.opened_route_keys_from_last_recall_cache(cache_path),
        )
        self.assertNotIn("msg_private_handle", encoded)
        self.assertNotIn(str(self.cwd), encoded)

    def test_recall_does_not_resuggest_deepen_for_already_opened_route(self) -> None:
        cache_path = self.cwd / "last-recall-repeat.json"
        first = agent_continuity.recall(
            "opt-in continuity source before claims",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            registry_dir=self.cwd / "registry",
            max_routes=1,
        )
        self.assertEqual(first["status"], "ok")
        self.assertEqual(
            first["foreground_action_card"]["canonical_action"]["action_id"],
            "agent_deepen_selected_route",
        )
        agent_continuity_cli_support.write_last_recall_cache(
            first["deepen_requests"],
            query="opt-in continuity source before claims",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            registry_dir=self.cwd / "registry",
            macro_state_path=None,
            project="AIppocampus",
            max_matches=5,
            schema_version=agent_continuity.SCHEMA_VERSION,
            path=cache_path,
        )
        self.assertTrue(
            agent_continuity_cli_support.mark_last_recall_request_opened(
                1,
                path=cache_path,
            )
        )
        expected_opened_key = agent_continuity_cli_support.last_recall_route_key(
            first["deepen_requests"][0]["route_id"],
            first["deepen_requests"][0]["handle_sha256_12"],
        )
        opened_keys = agent_continuity_cli_support.opened_route_keys_from_last_recall_cache(cache_path)
        self.assertIn(
            expected_opened_key,
            opened_keys,
        )

        second = agent_continuity.recall(
            "opt-in continuity source before claims",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            registry_dir=self.cwd / "registry",
            max_routes=1,
            opened_route_keys=opened_keys,
        )
        packet = next(
            item
            for item in second["memory_packets"]
            if item["route_id"] == first["memory_packets"][0]["route_id"]
        )

        self.assertTrue(packet["already_opened"])
        self.assertEqual(
            packet["recommended_next"],
            "use_opened_route_context_or_deepen_if_scope_changed",
        )
        self.assertEqual(second["metrics"]["already_opened_route_count"], 1)
        self.assertEqual(
            second["foreground_action_card"]["canonical_action"]["action_id"],
            "use_opened_route_context",
        )

    def test_agent_recall_keeps_thread_candidate_as_direction_only(self) -> None:
        fake_packet = {
            "kind": "aippocampus_recall_context",
            "status": "ok",
            "routes": [
                {
                    "kind": "thread_candidate",
                    "route_id": "route_thread_candidate",
                    "title": "Thread-level registry hint",
                    "summary": "This is a weak navigation hint.",
                    "handle": {
                        "kind": "thread_candidate",
                        "route_id": "route_thread_candidate",
                        "thread_key": "session:thread-candidate",
                    },
                    "reopenable": False,
                    "triage_rank_reason_codes": ["registry_thread_candidate"],
                }
            ],
            "route_count": 1,
        }

        with patch.object(agent_recall_pipeline, "recall_context_packet", return_value=fake_packet):
            payload = agent_continuity.recall(
                "weak registry thread hint",
                cwd=self.cwd,
                clean_source_dir=self.clean,
                registry_dir=self.cwd / "registry",
            )

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["memory_packets"][0]["output_mode"], "direction_only")
        self.assertEqual(payload["memory_packets"][0]["route_kind"], "thread_candidate")
        self.assertEqual(payload["deepen_requests"], [])

    def test_agent_deepen_rejects_bare_json_thread_candidate_handle(self) -> None:
        registry_dir = self.cwd / "registry"
        thread_key = "session:thread-candidate"
        clean_dir = registry_api.thread_store_dir(thread_key, registry_dir) / "clean-source"
        clean_dir.mkdir(parents=True)
        with (clean_dir / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps(
                    {
                        "thread_key": thread_key,
                        "message_id": "msg_tc",
                        "turn_id": "turn_tc",
                        "turn_index": 1,
                        "source_line": 1,
                        "role": "assistant",
                        "phase": "final_answer",
                        "is_final": True,
                        "text": "Thread candidate handles should reopen clean source.",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        payload = agent_continuity.deepen(
            json.dumps(
                {
                    "kind": "thread_candidate",
                    "route_id": "route_thread_candidate",
                    "thread_key": thread_key,
                },
                ensure_ascii=False,
            ),
            cwd=self.cwd,
            clean_source_dir=self.clean,
            registry_dir=registry_dir,
        )

        self.assertEqual(payload["status"], "cannot_verify")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "thread_candidate_needs_source_resolution")
        self.assertEqual(
            payload["result"]["error"]["details"]["suggested_next"]["tool"],
            "search_memory",
        )
        self.assertNotIn("source_window", json.dumps(payload, ensure_ascii=False))

    def test_compact_projection_does_not_advertise_last_recall_when_cache_missing(self) -> None:
        payload = {
            "kind": agent_continuity.KIND,
            "schema_version": agent_continuity.SCHEMA_VERSION,
            "mode": "recall",
            "status": "ok",
            "opt_in_required": False,
            "last_recall_cache_available": False,
            "foreground_action_card": {
                "canonical_action": {
                    "action_id": "agent_deepen_selected_route",
                    "tool_name": "agent_deepen",
                    "arguments": {"request_index": 1},
                    "cli_command_template": (
                        "aippocampus agent deepen --request 1 "
                        "--recall-selector {recall_selector} --json"
                    ),
                    "requires": ["recall_selector"],
                    "template_only": True,
                    "claim_boundary": "no_claim_before_reopen",
                }
            },
            "memory_packets": [
                {
                    "route_id": "route_missing_cache",
                    "route_label": "missing cache route",
                    "output_mode": "reopenable_route",
                    "claim_permission": "no_claim_before_reopen",
                }
            ],
            "metrics": {"requested_max_routes": 1, "effective_max_routes": 1},
            "policy_boundary": agent_continuity.policy_boundary(),
        }

        projected = agent_continuity_cli_support.public_recall_projection(payload)
        encoded = json.dumps(projected, ensure_ascii=False)

        self.assertNotIn("last_recall_cache_available", projected)
        self.assertNotIn("--last-recall", encoded)
        self.assertEqual(projected["foreground_action"]["id"], "repair_last_recall_cache")
        self.assertCanonicalForegroundAction(projected)
        self.assertIn("last_recall_cache_recovery_card", projected)

    def test_last_recall_unavailable_recovery_does_not_loop_to_same_command(self) -> None:
        payload = agent_continuity_cli_support.last_recall_unavailable_payload(
            mode="deepen",
            exc=ValueError("public compact recall projection needs the same-machine last recall cache"),
            schema_version=agent_continuity.SCHEMA_VERSION,
            kind=agent_continuity.KIND,
        )
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["foreground_action"]["id"], "recall_with_cue_full_detail")
        self.assertCanonicalForegroundAction(payload)
        self.assertNotIn("follow_up_action", payload)
        self.assertNotIn("--last-recall", encoded)

    def test_memory_packet_budget_trimming_keeps_route_label(self) -> None:
        packet = {
            "kind": "aippocampus_memory_packet",
            "route_id": "route_budget",
            "output_mode": "reopenable_route",
            "claim_permission": "no_claim_before_reopen",
            "next_action": "reopen_source",
            "deepen_route_id": "deepen:route_budget",
            "route_label": (
                "mcp health compact json doctor config install sync release gate "
                "route label"
            ),
            "route_topic": "mcp_health_doctor_config_install_sync_release_gate",
            "display_hint": "Reopen this route before using release gate details. " * 8,
            "selection_hint": {
                "source": "attention_router",
                "why": "attention router top route changed but source reopen is still required " * 8,
            },
            "route_delta_reason_codes": [
                "attention_router_top_route_changed",
                "topology_requested",
                "macro_orientation_recall_prior",
            ],
            "triage_rank_reason_codes": [
                "source_reopen_required",
                "scope_label_available",
            ],
            "risk_flags": ["source_reopen_required", "check_currentness"],
        }

        fitted = agent_recall_primitives._fit_memory_packet_with_route_delta(dict(packet))

        self.assertLessEqual(
            agent_recall_primitives._json_bytes(fitted),
            facade.FOREGROUND_PACKET_BYTE_BUDGET,
        )
        self.assertIn("route_label", fitted)
        self.assertTrue(fitted["route_label"])
        self.assertIn("mcp health", fitted["route_label"])

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

        with patch.object(agent_recall_pipeline, "recall_context_packet", return_value=fake_packet):
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
            patch.object(agent_recall_pipeline, "recall_context_packet", return_value=fake_packet),
            patch.object(
                agent_recall_pipeline.attention_router_policy,
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

    def test_low_anchor_source_route_is_not_default_foreground_action(self) -> None:
        self._append_clean_rows(
            [
                {
                    "message_id": "msg_low_anchor",
                    "turn_id": "turn_low_anchor",
                    "source_id": "src_test",
                    "source_line": 40,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 40,
                    "is_final": True,
                    "text": "General recall implementation notes without the benchmark complaint anchors.",
                }
            ]
        )
        handle = {
            "kind": "source_ref",
            "route_id": "route_low_anchor",
            "source_refs": [{"source_id": "src_test", "message_id": "msg_low_anchor"}],
        }
        fake_packet = {
            "kind": "aippocampus_recall_context",
            "status": "ok",
            "routes": [
                {
                    "route_id": "route_low_anchor",
                    "kind": "source_ref",
                    "handle": handle,
                    "route_label": "coding_route_recovery route",
                    "source_refs": handle["source_refs"],
                }
            ],
        }

        with patch.object(agent_recall_pipeline, "recall_context_packet", return_value=fake_packet):
            report = agent_continuity.recall(
                "benchmark 实测检索不弱 recall deepen 实际都好差劲",
                cwd=self.cwd,
                clean_source_dir=self.clean,
            )
            already_opened_report = agent_continuity.recall(
                "benchmark 实测检索不弱 recall deepen 实际都好差劲",
                cwd=self.cwd,
                clean_source_dir=self.clean,
                opened_route_keys={
                    agent_continuity_cli_support.last_recall_route_wildcard_key(
                        "route_low_anchor"
                    )
                },
            )

        self.assertEqual(report["source_anchor_gate"]["status"], "blocked")
        self.assertEqual(report["foreground_action_card"]["decision"], "recover_low_confidence_route")
        self.assertEqual(report["suggested_next"], "search_memory")
        self.assertIn("low_source_anchor_coverage", report["memory_packets"][0]["risk_flags"])
        secondary = report["foreground_action_card"]["safe_next_actions"][1]
        self.assertEqual(secondary["action_id"], "deepen_low_confidence_route")
        self.assertTrue(already_opened_report["memory_packets"][0]["already_opened"])
        self.assertEqual(
            already_opened_report["foreground_action_card"]["decision"],
            "recover_low_confidence_route",
        )

    def test_anchor_matching_source_route_remains_default_deepen_action(self) -> None:
        self._append_clean_rows(
            [
                {
                    "message_id": "msg_anchor_match",
                    "turn_id": "turn_anchor_match",
                    "source_id": "src_test",
                    "source_line": 41,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 41,
                    "is_final": True,
                    "material_class": "clean_source_text",
                    "source_claim_policy": "source_open_required_for_exact_claim",
                    "text": "黏菌 联想回忆 探索算法 all point to the same current source trail.",
                }
            ]
        )
        handle = {
            "kind": "source_ref",
            "route_id": "route_anchor_match",
            "source_refs": [{"source_id": "src_test", "message_id": "msg_anchor_match"}],
        }
        fake_packet = {
            "kind": "aippocampus_recall_context",
            "status": "ok",
            "routes": [
                {
                    "route_id": "route_anchor_match",
                    "kind": "source_ref",
                    "handle": handle,
                    "route_label": "agent_native_recall_facade route",
                    "source_refs": handle["source_refs"],
                }
            ],
        }

        with patch.object(agent_recall_pipeline, "recall_context_packet", return_value=fake_packet):
            report = agent_continuity.recall(
                "黏菌 联想回忆 探索算法",
                cwd=self.cwd,
                clean_source_dir=self.clean,
            )

        self.assertEqual(report["source_anchor_gate"]["status"], "passed")
        self.assertEqual(report["source_anchor_gate"]["opened_anchor_hits"], 3)
        self.assertEqual(report["foreground_action_card"]["decision"], "use_route_first")
        self.assertEqual(report["suggested_next"], "agent deepen")

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

        with patch.object(agent_recall_pipeline, "recall_context_packet", return_value=fake_packet):
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
        self.assertIn("macro_orientation_applied", report["navigation_signals"]["signals"])
        self.assertEqual(report["navigation_signals"]["action_grammar"], "reopenable_route")
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

    def test_cli_malformed_deepen_and_explain_are_nonzero_and_actionable(self) -> None:
        deepen_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "deepen",
                "not-a-valid-handle",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        explain_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "explain",
                "not-a-valid-handle",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(deepen_proc.returncode, 2)
        self.assertIn("AIppocampus agent deepen: cannot_verify", deepen_proc.stdout)
        self.assertIn("Next: rerun agent recall", deepen_proc.stdout)
        self.assertEqual(explain_proc.returncode, 2)
        self.assertIn("AIppocampus agent explain: cannot verify handle", explain_proc.stdout)
        self.assertIn("deepen_requests[].handle", explain_proc.stdout)

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
        compact_human = agent_continuity_cli_support.public_recall_projection(
            {**human, "last_recall_cache_available": True}
        )
        encoded = json.dumps(compact_human, ensure_ascii=False, sort_keys=True)

        self.assertFalse(baseline["metrics"]["macro_orientation_applied"])
        self.assertTrue(human["metrics"]["macro_orientation_applied"])
        self.assertGreater(human["metrics"]["effective_max_routes"], 2)
        self.assertGreater(len(human["memory_packets"]), len(baseline["memory_packets"]))
        self.assertEqual(human["macro_navigation"]["active_layer"], "human")
        self.assertEqual(earth["macro_navigation"]["active_layer"], "earth")
        self.assertEqual(human["memory_packets"][0]["route_topic"], "issue_backlog_interpretation")
        self.assertEqual(earth["memory_packets"][0]["route_topic"], "benchmark_claim_posture")
        self.assertIn("macro_active_layer_human", json.dumps(human, ensure_ascii=False, sort_keys=True))
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
        compact_report = agent_continuity_cli_support.public_recall_projection(
            {**report, "last_recall_cache_available": True}
        )
        encoded = json.dumps(compact_report, ensure_ascii=False, sort_keys=True)

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

if __name__ == "__main__":
    unittest.main()
