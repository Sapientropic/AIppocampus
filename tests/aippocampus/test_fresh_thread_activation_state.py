from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"

from aippocampus_runtime.recall.fresh_thread_action import (
    fresh_thread_action_from_packet,
)
from aippocampus_runtime.recall.fresh_thread_activation import (
    ACTIVATION_STATES,
    advance_fresh_thread_activation,
    fresh_thread_activation_context,
)
from aippocampus_runtime.recall.fresh_thread_scent import (
    fresh_thread_scent_packet_from_decision,
)

SOURCE_BACKED_AFTER_REOPEN = "source_backed"


class FreshThreadActivationStateTests(unittest.TestCase):
    def _packet(self, *, confidence: str = "medium") -> dict[str, object]:
        return fresh_thread_scent_packet_from_decision(
            {
                "decision": "scent",
                "confidence": confidence,
                "sensitivity": "safe",
                "prompt": "raw prompt must not survive",
                "candidates": [
                    {
                        "source_id": "clean:theme:1",
                        "thread_key": "session:theme",
                        "message_id": "m1",
                        "line": 9,
                        "snippet": "private source wording",
                    }
                ],
            }
        )

    def test_scent_state_is_privacy_safe_and_lock_aware(self) -> None:
        state = advance_fresh_thread_activation(
            None,
            event="scent_emitted",
            packet=self._packet(),
            thread_id="thread-raw-private",
            workspace="E:/private/workspace",
            topic_epoch="epoch-theme",
            registry_fingerprint="registry-v1",
            active_recall_lock={"state": "pending", "lock_id": "lock_theme_1"},
            now_unix=100.0,
        )
        serialized = json.dumps(state, ensure_ascii=False, sort_keys=True)

        self.assertEqual(state["state"], "scent_emitted")
        self.assertEqual(state["active_recall_lock"]["state"], "pending")
        self.assertEqual(state["active_recall_lock"]["lock_id"], "lock_theme_1")
        self.assertTrue(state["route_fingerprint"].startswith("far_"))
        self.assertNotIn("raw-private", serialized)
        self.assertNotIn("private/workspace", serialized.replace("\\", "/"))
        self.assertNotIn("raw prompt", serialized)
        self.assertNotIn("private source wording", serialized)

    def test_confirmed_state_enables_deeper_active_recall(self) -> None:
        packet = self._packet()
        state = advance_fresh_thread_activation(
            None,
            event="scent_emitted",
            packet=packet,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-theme",
            registry_fingerprint="registry-v1",
            now_unix=100.0,
        )
        confirmed = advance_fresh_thread_activation(
            state,
            event="user_confirmed",
            packet=packet,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-theme",
            registry_fingerprint="registry-v1",
            active_recall_lock={"state": "ready", "lock_id": "lock_ready"},
            now_unix=110.0,
        )
        context = fresh_thread_activation_context(
            confirmed,
            topic_epoch="epoch-theme",
            registry_fingerprint="registry-v1",
            now_unix=111.0,
        )
        action = fresh_thread_action_from_packet(
            packet,
            task_context=context,
            active_recall_lock=confirmed["active_recall_lock"],
        )

        self.assertEqual(confirmed["state"], "confirmed")
        self.assertTrue(context["user_confirmed_memory_theme"])
        self.assertEqual(action["agent_action"], "active_recall")
        self.assertEqual(action["lock_handling"], "use_ready_lock")

    def test_rejected_state_suppresses_same_route_for_topic_epoch(self) -> None:
        packet = self._packet()
        state = advance_fresh_thread_activation(
            None,
            event="user_rejected",
            packet=packet,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-theme",
            registry_fingerprint="registry-v1",
            now_unix=100.0,
        )
        context = fresh_thread_activation_context(
            state,
            topic_epoch="epoch-theme",
            registry_fingerprint="registry-v1",
            now_unix=101.0,
        )
        action = fresh_thread_action_from_packet(
            packet,
            task_context={**context, "memory_may_change_answer": True},
            active_recall_lock={"state": "ready", "lock_id": "lock_ready"},
        )

        self.assertEqual(state["state"], "rejected")
        self.assertTrue(context["route_suppressed_by_activation"])
        self.assertEqual(action["agent_action"], "ignore")
        self.assertEqual(action["candidate_refs"], [])

    def test_ignored_soft_hypothesis_does_not_reappear_without_new_anchor(self) -> None:
        packet = self._packet()
        shown = advance_fresh_thread_activation(
            None,
            event="soft_hypothesis_shown",
            packet=packet,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-theme",
            registry_fingerprint="registry-v1",
            now_unix=100.0,
        )
        ignored = advance_fresh_thread_activation(
            shown,
            event="user_ignored",
            packet=packet,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-theme",
            registry_fingerprint="registry-v1",
            now_unix=120.0,
        )
        quiet_context = fresh_thread_activation_context(
            ignored,
            topic_epoch="epoch-theme",
            registry_fingerprint="registry-v1",
            now_unix=121.0,
            user_anchor=False,
        )
        anchored_context = fresh_thread_activation_context(
            ignored,
            topic_epoch="epoch-theme",
            registry_fingerprint="registry-v1",
            now_unix=121.0,
            user_anchor=True,
        )

        quiet_action = fresh_thread_action_from_packet(packet, task_context=quiet_context)
        anchored_action = fresh_thread_action_from_packet(packet, task_context=anchored_context)

        self.assertEqual(ignored["state"], "ignored")
        self.assertTrue(quiet_context["prior_scent_without_new_anchor"])
        self.assertEqual(quiet_action["agent_action"], "use_silently")
        self.assertFalse(anchored_context["prior_scent_without_new_anchor"])
        self.assertEqual(anchored_action["agent_action"], "ask_light_question")

    def test_source_reopened_upgrades_state_without_bypassing_future_source_rules(self) -> None:
        packet = self._packet(confidence="high")
        state = advance_fresh_thread_activation(
            None,
            event="source_reopened",
            packet=packet,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-theme",
            registry_fingerprint="registry-v1",
            now_unix=100.0,
        )
        context = fresh_thread_activation_context(
            state,
            topic_epoch="epoch-theme",
            registry_fingerprint="registry-v1",
            now_unix=101.0,
        )
        action = fresh_thread_action_from_packet(
            packet,
            task_context={**context, "specific_memory_claim": True},
        )

        self.assertEqual(state["state"], SOURCE_BACKED_AFTER_REOPEN)
        self.assertTrue(context["activation_source_reopened"])
        self.assertEqual(action["agent_action"], "source_reopen")
        self.assertTrue(action["requires_source_reopen"])

    def test_topic_shift_and_registry_freshness_retire_stale_theme(self) -> None:
        packet = self._packet()
        state = advance_fresh_thread_activation(
            None,
            event="scent_emitted",
            packet=packet,
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-old",
            registry_fingerprint="registry-v1",
            now_unix=100.0,
        )

        topic_context = fresh_thread_activation_context(
            state,
            topic_epoch="epoch-new",
            registry_fingerprint="registry-v1",
            now_unix=110.0,
        )
        registry_context = fresh_thread_activation_context(
            state,
            topic_epoch="epoch-old",
            registry_fingerprint="registry-v2",
            now_unix=110.0,
        )

        self.assertEqual(topic_context["activation_update"], "retired")
        self.assertEqual(topic_context["activation_invalidation"], "topic_epoch_changed")
        self.assertTrue(topic_context["route_suppressed_by_activation"])
        self.assertEqual(registry_context["activation_invalidation"], "registry_freshness_changed")

    def test_ttl_expiry_retires_activation_state(self) -> None:
        state = advance_fresh_thread_activation(
            None,
            event="scent_emitted",
            packet=self._packet(),
            thread_id="thread-a",
            workspace="workspace",
            topic_epoch="epoch-theme",
            registry_fingerprint="registry-v1",
            now_unix=100.0,
            ttl_seconds=10,
        )

        context = fresh_thread_activation_context(
            state,
            topic_epoch="epoch-theme",
            registry_fingerprint="registry-v1",
            now_unix=111.0,
        )

        self.assertEqual(context["activation_update"], "retired")
        self.assertEqual(context["activation_invalidation"], "expired")

    def test_state_contract_lists_required_progressive_states(self) -> None:
        self.assertTrue(
            {
                "pending",
                "scent_emitted",
                "soft_hypothesis",
                "ignored",
                "confirmed",
                "rejected",
                "source_backed",
                "retired",
                "suppressed",
            }.issubset(ACTIVATION_STATES)
        )

if __name__ == "__main__":
    unittest.main()
