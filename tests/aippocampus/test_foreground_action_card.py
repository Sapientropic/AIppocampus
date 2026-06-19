import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.mcp.public_projection import compact_health_payload  # noqa: E402
from aippocampus_runtime.recall import agent_continuity, foreground_action_card  # noqa: E402


class ForegroundActionCardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.clean = self.cwd / ".aippocampus" / "clean-source"
        self.clean.mkdir(parents=True)
        with (self.clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {
                        "message_id": "msg_card",
                        "turn_id": "turn_card",
                        "source_id": "src_card",
                        "source_line": 1,
                        "role": "assistant",
                        "phase": "final_answer",
                        "turn_index": 1,
                        "is_final": True,
                        "text": "Agent recall should surface one action card before audit details.",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _packet(self, routes: list[dict[str, object]]) -> dict[str, object]:
        return {
            "kind": "aippocampus_recall_context",
            "status": "ok",
            "routes": routes,
        }

    def _recall_with_routes(self, routes: list[dict[str, object]]) -> dict[str, object]:
        with patch.object(agent_continuity, "recall_context_packet", return_value=self._packet(routes)):
            return agent_continuity.recall(
                "foreground action card",
                cwd=self.cwd,
                clean_source_dir=self.clean,
                max_routes=3,
            )

    def test_positive_route_card_precedes_audit_payload_and_has_callable_action(self) -> None:
        report = agent_continuity.recall(
            "agent recall foreground action card",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            max_routes=1,
        )
        card = report["foreground_action_card"]

        self.assertEqual(card["decision"], "use_route_first")
        self.assertEqual(card["next_action"], "deepen")
        self.assertEqual(card["canonical_action"]["action_id"], "agent_deepen_selected_route")
        self.assertEqual(card["canonical_action"]["tool_name"], "agent_deepen")
        self.assertEqual(card["canonical_action"]["arguments"]["request_index"], 1)
        self.assertEqual(card["claim_boundary"], "no_claim_before_reopen")
        self.assertEqual(card["callable_handle"], report["deepen_requests"][0]["handle"])
        self.assertLessEqual(len(card), foreground_action_card.CARD_FIELD_BUDGET)
        self.assertEqual(report["metrics"]["foreground_action_card_audit_key_leak_count"], 0)
        self.assertLess(
            list(report).index("foreground_action_card"),
            list(report).index("memory_packets"),
        )
        self.assertTrue(report["audit_available"])
        self.assertFalse(foreground_action_card.AUDIT_ONLY_KEYS & set(card))

    def test_no_route_card_offers_recoverable_search(self) -> None:
        report = self._recall_with_routes([])
        card = report["foreground_action_card"]

        self.assertEqual(report["status"], "no_routes")
        self.assertEqual(card["decision"], "recover_no_route")
        self.assertEqual(card["next_action"], "search_memory")
        self.assertEqual(card["canonical_action"]["tool_name"], "search_memory")
        self.assertEqual(
            shlex.split(card["canonical_action"]["cli_command"]),
            ["aippocampus", "search", "foreground action card", "--json"],
        )
        self.assertEqual(card["safe_next_actions"][0], card["canonical_action"])
        self.assertEqual(card["claim_boundary"], "no_route_claim")
        self.assertNotIn("metrics", card)

    def test_blocked_private_route_card_does_not_offer_a_handle(self) -> None:
        report = self._recall_with_routes(
            [
                {
                    "route_id": "route_private",
                    "kind": "source_ref",
                    "route_label": "private route should not foreground",
                    "action_grammar": "ignore_or_blocked",
                }
            ]
        )
        card = report["foreground_action_card"]
        encoded = json.dumps(card, ensure_ascii=False, sort_keys=True)

        self.assertEqual(card["decision"], "ignore_or_blocked")
        self.assertEqual(card["next_action"], "continue_normally")
        self.assertNotIn("callable_handle", card)
        self.assertNotIn(str(self.cwd), encoded)

    def test_stale_or_conflicted_route_card_requires_deepen_before_claim(self) -> None:
        report = self._recall_with_routes(
            [
                {
                    "route_id": "route_stale",
                    "kind": "source_ref",
                    "route_label": "stale route",
                    "handle": "handle:stale-route",
                    "currentness": "stale",
                    "conflict": "source_conflict",
                }
            ]
        )
        card = report["foreground_action_card"]

        self.assertEqual(card["decision"], "deepen_before_claim")
        self.assertEqual(card["next_action"], "deepen")
        self.assertEqual(card["callable_handle"], "handle:stale-route")
        self.assertIn("currentness", card["why"])

    def test_public_projection_redacts_card_handle_but_keeps_action_shape(self) -> None:
        report = agent_continuity.recall(
            "agent recall foreground action card",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            max_routes=1,
        )
        redacted_card = foreground_action_card.redact_public_card(report["foreground_action_card"])
        public = agent_continuity.public_recall_projection(
            {**report, "last_recall_cache_available": True}
        )
        encoded = json.dumps(public, ensure_ascii=False, sort_keys=True)
        action = public["foreground_action"]

        self.assertNotIn("callable_handle", redacted_card)
        self.assertTrue(redacted_card["callable_handle_redacted"])
        self.assertEqual(redacted_card["canonical_action"]["tool_name"], "agent_deepen")
        self.assertEqual(redacted_card["canonical_action"]["arguments"]["request_index"], 1)
        self.assertNotIn("handle", json.dumps(redacted_card["canonical_action"], ensure_ascii=False))
        self.assertEqual(redacted_card["next_action"], "deepen")
        self.assertNotIn("short_action_token", redacted_card)
        self.assertLessEqual(len(redacted_card), foreground_action_card.CARD_FIELD_BUDGET)
        self.assertEqual(action["tool_name"], "agent_deepen")
        self.assertEqual(action["arguments"]["request_index"], 1)
        self.assertNotIn("foreground_action_card", public)
        self.assertNotIn("deepen_requests", public)
        self.assertIn("foreground_action_card.callable_handle", public["local_private_fields"])
        self.assertNotIn(report["foreground_action_card"]["callable_handle"], encoded)

    def test_replay_report_shows_card_reduces_manual_compile_steps_without_truth_claim(self) -> None:
        report = foreground_action_card.build_action_card_replay_report()

        self.assertTrue(report["ok"])
        self.assertGreater(report["broad_manual_search_reduction_proxy"], 0)
        self.assertEqual(report["red_lines"]["audit_key_in_card_count"], 0)
        self.assertIn("causal_live_agent_behavior_lift", report["cannot_claim"])

    def test_card_metrics_use_central_profile_and_count_audit_key_leaks(self) -> None:
        card = {
            "decision": "use_route_first",
            "why": "Route likely matters.",
            "next_action": "deepen",
            "claim_boundary": "no_claim_before_reopen",
            "metrics": {"audit": True},
        }
        metrics = foreground_action_card.card_metrics(card)

        self.assertEqual(metrics["foreground_action_card_audit_key_leak_count"], 1)
        self.assertTrue(metrics["foreground_action_card_profile_ok"])

    def test_compact_health_separates_workspace_maintenance_from_recall_availability(self) -> None:
        compact = compact_health_payload(
            {
                "ok": True,
                "status": "ready_with_freshness_degraded",
                "product_readiness": {
                    "status": "ready_with_freshness_degraded",
                    "ready": True,
                    "ordinary_first_recall_usable": True,
                    "first_recall_phase": "steady_state_latest_degraded",
                    "cold_start_expected": False,
                    "workspace_source_maintenance_required": True,
                    "continuity_recall_available": True,
                    "maintenance_recommended": True,
                    "maintenance_required_before_recall": False,
                    "blocking_action_count": 0,
                    "high_severity_action_count": 1,
                },
                "recommended_actions": [
                    {
                        "id": "build_clean_source",
                        "severity": "critical",
                        "reason": "workspace clean source missing",
                        "facade_command": "aippocampus maintenance plan --summary-json",
                    }
                ],
                "freshness": {"latest_visible_gap": True},
            }
        )

        self.assertTrue(compact["ok"])
        self.assertTrue(compact["ordinary_first_recall_usable"])
        self.assertFalse(compact["blocks_first_recall"])
        self.assertTrue(compact["workspace_source_maintenance_required"])
        self.assertTrue(compact["continuity_recall_available"])
        self.assertEqual(compact["agent_next_action"]["id"], "continue_with_nonblocking_maintenance")
        self.assertIn("before_exact_latest_claims", compact["agent_next_action"])
        self.assertEqual(compact["readiness_card"]["state"], "ready_with_freshness_degraded")
        self.assertFalse(compact["readiness_card"]["blocks_first_recall"])
