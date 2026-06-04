from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import ambient_cards as cards  # noqa: E402
from aippocampus_runtime.recall.fresh_thread_action import (  # noqa: E402
    EXAMPLE_ACTION_DECISIONS,
    fresh_thread_action_from_packet,
)
from aippocampus_runtime.recall.fresh_thread_scent import (  # noqa: E402
    fresh_thread_scent_packet_from_decision,
)


class FreshThreadActionPolicyTests(unittest.TestCase):
    def test_broad_low_confidence_scent_can_stay_internal_without_recall(self) -> None:
        payload = cards.ambient_recall_from_decision(
            {
                "decision": "scent",
                "confidence": "low",
                "candidates": [{"source_id": "clean:pressure", "thread_key": "session:old"}],
                "evidence": [],
                "working_memory": [],
                "cognitive_map": [],
            }
        )

        action = fresh_thread_action_from_packet(
            payload["fresh_thread_packet"],
            task_context={"broad_or_sensitive_prompt": True},
        )

        self.assertEqual(action["agent_action"], "use_silently")
        self.assertFalse(action["should_call_active_recall"])
        self.assertFalse(action["requires_source_reopen"])
        self.assertEqual(action["allowed_surface"], "internal_only")
        self.assertEqual(action["candidate_refs"], [])

    def test_suppressed_packets_do_not_steer_answer_or_lock_usage(self) -> None:
        packet = fresh_thread_scent_packet_from_decision(
            {
                "decision": "scent",
                "confidence": "high",
                "sensitivity": "suppress",
                "candidates": [{"source_id": "clean:private", "thread_key": "session:private"}],
            }
        )

        action = fresh_thread_action_from_packet(
            packet,
            task_context={"memory_may_change_answer": True},
            active_recall_lock={"state": "ready", "lock_id": "lock_ready_1"},
        )

        self.assertEqual(action["agent_action"], "ignore")
        self.assertEqual(action["allowed_surface"], "none")
        self.assertFalse(action["should_call_active_recall"])
        self.assertEqual(action["lock_handling"], "none")
        self.assertEqual(action["candidate_refs"], [])
        self.assertIn("Suppressed", action["privacy_boundary"]["rule"])

    def test_relevant_soft_hypothesis_uses_ready_active_recall_lock(self) -> None:
        packet = fresh_thread_scent_packet_from_decision(
            {
                "decision": "scent",
                "confidence": "medium",
                "sensitivity": "safe",
                "candidates": [{"source_id": "clean:frontend-taste", "thread_key": "session:ui"}],
            }
        )

        action = fresh_thread_action_from_packet(
            packet,
            task_context={"memory_may_change_answer": True},
            active_recall_lock={"state": "ready", "lock_id": "lock_frontend_123"},
        )

        self.assertEqual(action["agent_action"], "active_recall")
        self.assertTrue(action["should_call_active_recall"])
        self.assertEqual(action["lock_handling"], "use_ready_lock")
        self.assertEqual(action["lock_id"], "lock_frontend_123")
        self.assertFalse(action["source_refs_allowed"])
        self.assertEqual(action["candidate_refs"][0]["source_id"], "clean:frontend-taste")

    def test_ready_lock_without_reopenable_refs_is_not_used_as_ready(self) -> None:
        packet = fresh_thread_scent_packet_from_decision(
            {
                "decision": "scent",
                "confidence": "medium",
                "sensitivity": "safe",
                "candidates": [{"source_id": "clean:book-thread", "thread_key": "session:books"}],
            }
        )

        action = fresh_thread_action_from_packet(
            packet,
            task_context={"memory_may_change_answer": True},
            active_recall_lock={
                "state": "ready",
                "lock_id": "lock_books",
                "candidate_ref_count": 1,
                "reopenable_ref_count": 0,
            },
        )

        self.assertEqual(action["agent_action"], "active_recall")
        self.assertEqual(action["lock_handling"], "wait_or_probe_lock")
        self.assertEqual(action["lock_id"], "lock_books")

    def test_current_checkout_fact_context_suppresses_old_project_recall(self) -> None:
        packet = fresh_thread_scent_packet_from_decision(
            {
                "decision": "evidence",
                "confidence": "high",
                "evidence": [
                    {
                        "source_id": "clean:old-project-test-command",
                        "thread_key": "session:old-repo",
                        "message_id": "msg-old",
                        "line": 4,
                    }
                ],
            }
        )

        action = fresh_thread_action_from_packet(
            packet,
            task_context={
                "current_checkout_required": True,
                "memory_may_change_answer": True,
                "specific_memory_claim": True,
            },
            active_recall_lock={
                "state": "ready",
                "lock_id": "lock_old_repo",
                "reopenable_ref_count": 1,
            },
        )

        self.assertEqual(action["agent_action"], "ignore")
        self.assertEqual(action["reason"], "current_checkout_required_read_current_repo_first")
        self.assertFalse(action["should_call_active_recall"])
        self.assertFalse(action["source_refs_allowed"])
        self.assertEqual(action["candidate_refs"], [])
        self.assertEqual(action["lock_handling"], "none")

    def test_packet_suggestion_alone_does_not_force_active_recall(self) -> None:
        packet = fresh_thread_scent_packet_from_decision(
            {
                "decision": "scent",
                "confidence": "medium",
                "sensitivity": "safe",
                "candidates": [{"source_id": "clean:creative", "thread_key": "session:creative"}],
            }
        )

        action = fresh_thread_action_from_packet(packet)

        self.assertEqual(packet["suggested_action"], "active_recall")
        self.assertEqual(action["agent_action"], "ask_light_question")
        self.assertEqual(action["packet_action_hint"], "active_recall")
        self.assertFalse(action["packet_action_hint_authoritative"])
        self.assertIn(
            "final_policy_requires_task_context_or_source_before_active_recall",
            action["hint_divergence_reason"],
        )
        self.assertFalse(action["should_call_active_recall"])
        self.assertEqual(action["lock_handling"], "none")

    def test_task_context_flags_report_provenance_instead_of_magic_truth(self) -> None:
        packet = fresh_thread_scent_packet_from_decision(
            {
                "decision": "scent",
                "confidence": "medium",
                "sensitivity": "safe",
                "candidates": [{"source_id": "clean:design", "thread_key": "session:design"}],
            }
        )

        action = fresh_thread_action_from_packet(
            packet,
            task_context={
                "memory_may_change_answer": True,
                "activation_update": "confirmed",
                "current_checkout_required": False,
                "future_unreviewed_flag": True,
            },
        )
        contract = action["task_context_contract"]

        self.assertTrue(contract["semantic_flags_are_upstream_judgement"])
        self.assertFalse(contract["policy_parses_raw_prompt"])
        self.assertEqual(
            contract["known_flag_provenance"]["memory_may_change_answer"],
            "foreground_agent_or_reviewed_sidecar_judgement",
        )
        self.assertEqual(
            contract["known_flag_provenance"]["activation_update"],
            "fresh_thread_activation_state",
        )
        self.assertEqual(
            contract["known_flag_provenance"]["current_checkout_required"],
            "deterministic_repo_or_source_check",
        )
        self.assertEqual(contract["observed_flags"]["memory_may_change_answer"], True)
        self.assertIn("future_unreviewed_flag", contract["unknown_flags"])

    def test_canonical_advisory_action_takes_precedence_over_legacy_alias(self) -> None:
        packet = {
            "support_level": "soft_hypothesis",
            "confidence": "high",
            "sensitivity": "safe",
            "freshness": "current",
            "advisory_action": "ask_light_question",
            "suggested_action": "active_recall",
            "candidate_refs": [{"source_id": "clean:design", "thread_key": "session:design"}],
        }

        action = fresh_thread_action_from_packet(packet)

        self.assertEqual(action["packet_action_hint"], "ask_light_question")
        self.assertEqual(action["agent_action"], "ask_light_question")
        self.assertEqual(action["hint_divergence_reason"], "final_policy_aligned_with_packet_hint")

    def test_legacy_suggested_action_alias_still_feeds_hint_when_canonical_is_absent(self) -> None:
        packet = {
            "support_level": "soft_hypothesis",
            "confidence": "medium",
            "sensitivity": "safe",
            "freshness": "current",
            "suggested_action": "active_recall",
            "candidate_refs": [{"source_id": "clean:design", "thread_key": "session:design"}],
        }

        action = fresh_thread_action_from_packet(
            packet,
            task_context={"memory_may_change_answer": True},
        )

        self.assertEqual(action["packet_action_hint"], "active_recall")
        self.assertEqual(action["agent_action"], "active_recall")
        self.assertFalse(action["packet_action_hint_authoritative"])

    def test_specific_memory_claim_requires_source_reopen_when_refs_exist(self) -> None:
        packet = fresh_thread_scent_packet_from_decision(
            {
                "decision": "evidence",
                "confidence": "high",
                "evidence": [
                    {
                        "source_id": "clean:profile:msg-1",
                        "thread_key": "session:profile",
                        "message_id": "msg-1",
                        "line": 9,
                        "snippet": "private exact wording",
                    }
                ],
            }
        )

        action = fresh_thread_action_from_packet(
            packet,
            task_context={"specific_memory_claim": True},
        )

        self.assertEqual(action["agent_action"], "source_reopen")
        self.assertEqual(action["packet_action_hint"], "source_reopen")
        self.assertFalse(action["packet_action_hint_authoritative"])
        self.assertEqual(action["hint_divergence_reason"], "final_policy_aligned_with_packet_hint")
        self.assertTrue(action["requires_source_reopen"])
        self.assertTrue(action["source_refs_allowed"])
        self.assertFalse(action["should_call_active_recall"])
        self.assertEqual(
            action["candidate_refs"],
            [
                {
                    "source_id": "clean:profile:msg-1",
                    "thread_key": "session:profile",
                    "message_id": "msg-1",
                    "line": 9,
                }
            ],
        )

    def test_lock_states_are_route_handles_not_memory_facts(self) -> None:
        packet = fresh_thread_scent_packet_from_decision(
            {
                "decision": "scent",
                "confidence": "high",
                "sensitivity": "safe",
                "candidates": [{"source_id": "clean:design", "thread_key": "session:design"}],
            }
        )

        cases = [
            ({"state": "pending", "lock_id": "lock_pending"}, "wait_or_probe_lock", "lock_pending"),
            ({"state": "expired", "lock_id": "lock_old"}, "start_lock", ""),
            ({"state": "failed", "lock_id": "lock_failed"}, "start_lock", ""),
            ({}, "start_lock", ""),
        ]
        for lock, expected_handling, expected_lock_id in cases:
            with self.subTest(lock=lock):
                action = fresh_thread_action_from_packet(
                    packet,
                    task_context={"memory_may_change_answer": True},
                    active_recall_lock=lock,
                )

                self.assertEqual(action["agent_action"], "active_recall")
                self.assertEqual(action["lock_handling"], expected_handling)
                self.assertEqual(action["lock_id"], expected_lock_id)
                self.assertIn("not_facts", action["privacy_boundary"]["lock_boundary"])

    def test_action_policy_output_excludes_raw_prompt_snippets_secrets_and_paths(self) -> None:
        local_path = "E:" + "\\private\\family\\notes.md"
        packet = {
            "kind": "aippocampus_fresh_thread_scent_packet",
            "schema_version": 1,
            "support_level": "soft_hypothesis",
            "confidence": "medium",
            "sensitivity": "safe",
            "freshness": "current",
            "suggested_action": "active_recall",
            "prompt": f"raw prompt {local_path}",
            "candidate_refs": [
                {
                    "source_id": "clean:family",
                    "thread_key": "session:family",
                    "line": 4,
                    "title": "private title",
                    "snippet": "secret sk-test-123",
                    "path": local_path,
                }
            ],
        }

        action = fresh_thread_action_from_packet(
            packet,
            task_context={"memory_may_change_answer": True},
            active_recall_lock={"state": "ready", "lock_id": local_path},
        )
        serialized = json.dumps(action, ensure_ascii=False, sort_keys=True)

        self.assertIn("clean:family", serialized)
        self.assertNotIn("raw prompt", serialized)
        self.assertNotIn("private title", serialized)
        self.assertNotIn("sk-test", serialized)
        self.assertNotIn("family\\notes", serialized)
        self.assertEqual(action["lock_id"], "")

    def test_examples_include_positive_and_negative_controls(self) -> None:
        positives = [
            item
            for item in EXAMPLE_ACTION_DECISIONS
            if item.get("case_type") == "positive"
        ]
        negatives = [
            item
            for item in EXAMPLE_ACTION_DECISIONS
            if item.get("case_type") == "negative_control"
        ]

        self.assertGreaterEqual(len(positives), 3)
        self.assertGreaterEqual(len(negatives), 3)
        self.assertTrue(
            any(item["decision"]["agent_action"] == "source_reopen" for item in positives)
        )
        self.assertTrue(
            all(not item["decision"]["should_call_active_recall"] for item in negatives)
        )


if __name__ == "__main__":
    unittest.main()
