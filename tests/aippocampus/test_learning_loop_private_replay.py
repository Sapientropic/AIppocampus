from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.learning_loop.private_replay import (  # noqa: E402
    build_private_history_replay_report,
    private_replay_fixture_events,
)


class LearningLoopPrivateReplayTests(unittest.TestCase):
    def test_private_replay_reports_aggregate_metrics_without_raw_leaks(self) -> None:
        events = private_replay_fixture_events()
        events[0]["raw_text"] = "PRIVATE_HISTORY_PAYLOAD should never be serialized"
        events[0]["command"] = "pytest E:/private/source/test_secret.py"
        events[0]["stderr"] = "traceback PRIVATE_HISTORY_PAYLOAD"

        report = build_private_history_replay_report(events)
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertTrue(report["ok"], report)
        metrics = report["metrics"]
        self.assertIn("repeated_failure_detection_recall", metrics)
        self.assertGreaterEqual(metrics["workflow_order_detection_count"], 1)
        self.assertGreaterEqual(metrics["context_loss_to_reopen_source_count"], 1)
        self.assertGreaterEqual(metrics["source_backed_guidance_changed_action_order_count"], 1)
        self.assertEqual(metrics["false_positive_nudge_rate"], 0.0)
        self.assertEqual(metrics["raw_private_text_leak_count"], 0)
        self.assertGreaterEqual(metrics["one_off_suppressed_count"], 1)
        self.assertGreaterEqual(metrics["expected_tdd_red_suppressed_count"], 1)
        self.assertTrue(report["guidance_authority"]["all_navigation_only"])
        self.assertTrue(report["guidance_authority"]["all_source_reopen_required"])
        self.assertFalse(report["guidance_authority"]["can_support_factual_claim"])
        self.assertNotIn("PRIVATE_HISTORY_PAYLOAD", encoded)
        self.assertNotIn("E:/private", encoded)
        self.assertNotIn("test_secret.py", encoded)


if __name__ == "__main__":
    unittest.main()
