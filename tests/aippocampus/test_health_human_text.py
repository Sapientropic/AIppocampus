from __future__ import annotations

import unittest
from io import StringIO
from unittest import mock

from aippocampus_runtime import health as health


class HealthHumanTextTests(unittest.TestCase):
    def test_human_health_labels_ready_advisory_commands_as_optional(self) -> None:
        payload = {
            "ok": True,
            "rollout": {"path": "rollout.jsonl", "size": 10, "message_count": 2},
            "index": {"exists": True, "stale": False, "message_delta": 2, "byte_delta": 100, "rag": {}},
            "clean_source": {"exists": True, "stale": False},
            "segments": {"exists": False, "needed": False},
            "checkpoint": {"due": True},
            "graphify": {"stale": True},
            "storage": {},
            "question_stats": {},
            "background_cognition": {},
            "logs": {},
            "health_trajectory": {},
            "product_readiness": {
                "status": "ready_with_live_delta",
                "ready": True,
                "blocking_action_count": 0,
            },
            "recommended_actions": [
                {
                    "id": "prepare_graphify_corpus",
                    "severity": "info",
                    "reason": "graphify corpus was prepared from an older index manifest",
                    "command": "aippocampus maintenance",
                }
            ],
        }

        with mock.patch("sys.stdout", new=StringIO()) as stdout:
            health.render_health_text(payload)

        text = stdout.getvalue()
        self.assertIn("thread memory health: OK", text)
        self.assertIn("best next action: continue", text)
        self.assertIn("can_continue_recall_now: yes", text)
        self.assertIn("blocks_exact_latest_claims: no", text)
        self.assertIn("Maintenance to inspect when idle:", text)
        self.assertIn("1. prepare_graphify_corpus [inspect]: aippocampus maintenance", text)
        self.assertNotIn("\nNext:", text)

    def test_human_health_separates_recall_ready_from_exact_latest_blocker(self) -> None:
        payload = {
            "ok": True,
            "rollout": {"path": "rollout.jsonl", "size": 10, "message_count": 2},
            "index": {"exists": True, "stale": False, "message_delta": 0, "byte_delta": 0, "rag": {}},
            "clean_source": {"exists": True, "stale": True},
            "segments": {"exists": False, "needed": False},
            "checkpoint": {"due": False},
            "graphify": {"stale": False},
            "storage": {},
            "question_stats": {},
            "background_cognition": {},
            "logs": {},
            "health_trajectory": {},
            "product_readiness": {
                "status": "ready_with_freshness_degraded",
                "ready": True,
                "ordinary_first_recall_usable": True,
                "freshness_degraded": True,
                "latest_current_thread_may_be_missing": True,
            },
            "recommended_actions": [
                {
                    "id": "build_clean_source",
                    "severity": "warning",
                    "reason": "latest visible clean-source messages are missing",
                    "command": "aippocampus maintenance plan --summary-json",
                }
            ],
        }

        with mock.patch("sys.stdout", new=StringIO()) as stdout:
            health.render_health_text(payload)

        text = stdout.getvalue()
        self.assertIn("readiness: yes (ready_with_freshness_degraded)", text)
        self.assertIn("can_continue_recall_now: yes", text)
        self.assertIn("blocks_exact_latest_claims: yes", text)
        self.assertIn("inspect: aippocampus maintenance plan --summary-json", text)
        self.assertNotIn("fix:", text)

if __name__ == "__main__":
    unittest.main()
