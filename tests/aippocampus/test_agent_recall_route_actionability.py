from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.recall import (
    agent_continuity,
    agent_continuity_cli_support,
)
from tests.aippocampus.product_probe_helpers import (
    SourceOpenExpectation,
    assert_deepen_opened_expected_source,
    write_clean_source_thread,
)


class AgentRecallRouteActionabilityTests(unittest.TestCase):
    def test_blocked_sibling_route_request_is_not_marked_reopenable_when_apw_primary_opens(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "clean-source"
            registry = root / "registry"
            write_clean_source_thread(
                clean,
                [
                    {
                        "thread_key": "session:apw-actionability",
                        "turn_id": "turn-apw-actionability",
                        "turn_index": 1,
                        "message_id": "msg-final",
                        "role": "assistant",
                        "phase": "final_answer",
                        "source_id": "src-apw-actionability",
                        "source_line": 7,
                        "line": 7,
                        "text": (
                            "source texture final answer closeout owner anchor text "
                            "confirms the APW source route can be reopened."
                        ),
                    }
                ],
            )
            payload = {
                "kind": "aippocampus_agent_continuity_path",
                "schema_version": "agent-continuity-path-v1",
                "mode": "recall",
                "status": "ok",
                "query": "source texture final answer closeout owner",
                "opt_in_required": False,
                "last_recall_cache_available": True,
                "recall_selector_id": "sel_apw_sibling_blocked",
                "foreground_action_card": {
                    "decision": "recover_low_confidence_route",
                    "canonical_action": {
                        "action_id": "inspect_low_confidence_route",
                        "tool_name": "agent_deepen",
                        "arguments": {"request_index": 1},
                        "claim_boundary": "low_confidence_no_claim_before_reopen",
                    },
                },
                "memory_packets": [
                    {
                        "route_id": "route-ordinary-blocked",
                        "route_topic": "agent_native_recall_facade",
                        "route_kind": "clean_source_route",
                        "output_mode": "reopenable_route",
                        "claim_permission": "no_claim_before_reopen",
                        "source_anchor_gate": {
                            "status": "blocked",
                            "reason": "top_route_source_not_reopenable",
                            "target_source_matched": False,
                            "opened_anchor_hits": 0,
                        },
                    }
                ],
                "deepen_requests": [
                    {
                        "request_index": 1,
                        "route_id": "route-ordinary-blocked",
                        "local_reopen_token": "tok-blocked",
                        "source_anchor_gate": {
                            "status": "blocked",
                            "reason": "top_route_source_not_reopenable",
                            "target_source_matched": False,
                            "opened_anchor_hits": 0,
                        },
                        "recommended_evidence_route": False,
                    },
                    {
                        "request_index": 6,
                        "route_id": "apw:current-clean-source:msg-final",
                        "handle": {
                            "kind": "source_ref",
                            "route_id": "apw:current-clean-source:msg-final",
                            "source_refs": [
                                {
                                    "source_id": "src-apw-actionability",
                                    "message_id": "msg-final",
                                    "line": 7,
                                }
                            ],
                        },
                        "local_reopen_token": "tok-apw",
                        "candidate_source_kind": "current_clean_source",
                        "selected_source_ref_count": 1,
                        "source_anchor_gate": {
                            "status": "pass",
                            "target_source_matched": True,
                            "opened_anchor_hits": 3,
                            "required_anchor_hits": 2,
                        },
                    },
                ],
                "associative_path_policy": {
                    "apw_candidate_input_available": True,
                    "ordinary_recall_recovery_needed": True,
                    "run_fallback": True,
                    "promotion_mode": "semi_default_recovery",
                },
                "associative_path_fallback": {
                    "kind": "aippocampus_associative_path_recall_fallback",
                    "status": "route_candidate",
                    "request_index": 6,
                    "label": "APW source route: source_texture / closeout",
                    "matched_cue_anchors": ["source_texture", "closeout", "owner"],
                    "route_choice_posture": "associative_path_semi_default_recovery",
                    "source_ref_digest": "digest-apw",
                    "selected_source_ref_count": 1,
                    "source_reopen_required_before_claim": True,
                    "source_anchor_gate": {
                        "status": "pass",
                        "target_source_matched": True,
                        "opened_anchor_hits": 3,
                        "required_anchor_hits": 2,
                    },
                },
            }
            public = agent_continuity_cli_support.public_recall_projection(payload)

            action = public["foreground_action"]
            self.assertEqual(action["id"], "deepen_associative_path_fallback")
            self.assertEqual(action["arguments"]["request_index"], 6)
            self.assertEqual(action["actionability"], "low_confidence_reopenable")
            self.assertEqual(public["routes"][0]["actionability"], "preview_only")
            self.assertEqual(public["routes"][0]["action_priority"], "secondary_preview")
            self.assertNotIn("action", public["routes"][0])
            encoded = json.dumps(public, ensure_ascii=False, sort_keys=True)
            self.assertNotIn("source_anchor_gate", encoded)
            self.assertNotIn("tok-blocked", encoded)

            cache_path = root / "last-recall.json"
            cache_written = agent_continuity_cli_support.write_last_recall_cache(
                payload["deepen_requests"],
                query="source texture final answer closeout owner",
                cwd=root,
                clean_source_dir=clean,
                registry_dir=registry,
                macro_state_path=None,
                project="AIppocampus",
                max_matches=5,
                schema_version=agent_continuity.SCHEMA_VERSION,
                path=cache_path,
            )
            selector_id = agent_continuity_cli_support.write_recall_selector_snapshot(cache_path)
            self.assertTrue(cache_written)
            self.assertIsNotNone(selector_id)
            handle, _context = agent_continuity_cli_support.handle_from_last_recall_cache(
                request_index=6,
                path=cache_path,
            )
            deepened = agent_continuity.deepen(
                handle,
                cwd=root,
                clean_source_dir=clean,
                registry_dir=registry,
            )
            assert_deepen_opened_expected_source(
                self,
                deepened,
                SourceOpenExpectation(
                    message_id="msg-final",
                    window_terms=("source texture final answer", "APW source route"),
                ),
            )


if __name__ == "__main__":
    unittest.main()
