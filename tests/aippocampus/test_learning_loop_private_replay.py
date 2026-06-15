from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.learning_loop.private_export import (
    sanitize_events_for_private_replay,  # noqa: E402
)
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
        self.assertFalse(report["fixture_input"])
        self.assertEqual(report["input_origin"], "real_sanitized_history")
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
        self.assertGreaterEqual(metrics["effectiveness_ledger_row_count"], 1)
        self.assertTrue(report["effectiveness_ledger"]["contract"]["effectiveness_is_navigation_priority_not_truth"])
        self.assertTrue(all(row["navigation_only"] for row in report["effectiveness_ledger_rows"]))
        self.assertNotIn("PRIVATE_HISTORY_PAYLOAD", encoded)
        self.assertNotIn("E:/private", encoded)
        self.assertNotIn("test_secret.py", encoded)

    def test_private_export_sanitizes_raw_rollout_like_rows_for_replay(self) -> None:
        rows = sanitize_events_for_private_replay(
            [
                {
                    "event_id": "raw-row",
                    "status": "failed",
                    "command_family": "python_pytest",
                    "target_class": "focused_test_path",
                    "failure_family": "assertion_failure",
                    "target_fingerprint": "target:private",
                    "path_category_fingerprint": "path:private",
                    "workspace_or_environment_profile": "E:/private/profile",
                    "command": "pytest E:/private/source/test_secret.py",
                    "stdout": "PRIVATE_HISTORY_PAYLOAD",
                    "line": 42,
                }
            ]
        )
        encoded = json.dumps(rows, ensure_ascii=False)

        self.assertEqual(rows[0]["event_id"], "raw-row")
        self.assertIn("source_refs", rows[0])
        self.assertNotIn("command", rows[0])
        self.assertNotIn("stdout", rows[0])
        self.assertNotIn("PRIVATE_HISTORY_PAYLOAD", encoded)
        self.assertNotIn("E:/private", encoded)


if __name__ == "__main__":
    unittest.main()
