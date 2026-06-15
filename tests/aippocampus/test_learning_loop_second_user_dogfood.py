from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "learning_loop" / "second_user_dogfood_cases.jsonl"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.learning_loop.dogfood_cases import (  # noqa: E402
    build_second_user_dogfood_report,
    load_second_user_cases,
)


class LearningLoopSecondUserDogfoodTests(unittest.TestCase):
    def test_second_user_cases_report_hint_effects_without_private_leaks(self) -> None:
        rows = load_second_user_cases(FIXTURE)
        report = build_second_user_dogfood_report(rows)
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        metrics = report["metrics"]

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["case_count"], 5)
        self.assertGreaterEqual(metrics["first_wrong_action_avoided"], 3)
        self.assertGreaterEqual(metrics["broad_search_avoided"], 3)
        self.assertGreaterEqual(metrics["source_reopen_before_claim"], 4)
        self.assertEqual(metrics["hint_ignored_or_dismissed"], 0)
        self.assertEqual(metrics["repeat_failure_after_hint"], 0)
        self.assertEqual(metrics["stale_warning_suppressed"], 1)
        self.assertEqual(metrics["current_thread_visibility_boundary_preserved"], 1)
        self.assertTrue(report["privacy_boundary"]["navigation_only"])
        self.assertNotIn("PRIVATE_", encoded)
        self.assertNotIn("C:/", encoded)


if __name__ == "__main__":
    unittest.main()
