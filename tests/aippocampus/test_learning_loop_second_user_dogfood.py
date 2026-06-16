from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "learning_loop" / "second_user_dogfood_cases.jsonl"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.learning_loop.dogfood_cases import (  # noqa: E402
    build_sanitized_repro_package,
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
        self.assertEqual(report["case_count"], 6)
        self.assertGreaterEqual(metrics["first_wrong_action_avoided"], 3)
        self.assertGreaterEqual(metrics["broad_search_avoided"], 3)
        self.assertGreaterEqual(metrics["source_reopen_before_claim"], 4)
        self.assertEqual(metrics["hint_ignored_or_dismissed"], 0)
        self.assertEqual(metrics["repeat_failure_after_hint"], 0)
        self.assertEqual(metrics["stale_warning_suppressed"], 1)
        self.assertEqual(metrics["current_thread_visibility_boundary_preserved"], 1)
        self.assertEqual(metrics["hint_absent_due_to_no_cache"], 1)
        self.assertEqual(metrics["no_cache_not_algorithmic_miss"], 1)
        self.assertEqual(metrics["prepared_cache_navigation_only_hint_emitted"], 1)
        self.assertTrue(report["privacy_boundary"]["navigation_only"])
        self.assertFalse(report["privacy_boundary"]["raw_tool_args_serialized"])
        self.assertNotIn("PRIVATE_", encoded)
        self.assertNotIn("C:/", encoded)

    def test_sanitized_repro_package_preserves_issue_shape_without_private_leaks(self) -> None:
        package = build_sanitized_repro_package(
            {
                "surface": "agent_recall",
                "command": (
                    "aippocampus agent recall --cwd E:/SDY/private "
                    "--query sk-test-public-fixture"
                ),
                "stdout": {
                    "kind": "aippocampus_agent_recall",
                    "route_id": "route-public",
                    "local_path": "E:/SDY/private/thread.jsonl",
                    "metrics": {"candidate_count": 2},
                    "source_refs": [{"thread_key": "session-private", "message_id": "msg-1"}],
                },
                "stderr": "warning: token=super-secret-value",
                "expected": "route should explain next action",
                "actual": "route exposed noisy private path",
            },
            version="0.2.0-test",
            commit="abcdef1234567890",
            plugin_manifest_version="0.2.0-test",
        )
        encoded = json.dumps(package, ensure_ascii=False, sort_keys=True)

        self.assertEqual(package["kind"], "aippocampus_sanitized_repro_package")
        self.assertTrue(package["ok"], package)
        self.assertEqual(package["surface"], "agent_recall")
        self.assertEqual(package["versions"]["aippocampus"], "0.2.0-test")
        self.assertEqual(package["versions"]["git_commit"], "abcdef123456")
        self.assertGreaterEqual(package["output_shape"]["byte_count"], 1)
        self.assertEqual(package["privacy_scan"]["private_field_leak_count"], 0)
        self.assertIn("expected_vs_actual_template", package)
        self.assertIn("privacy_note", package)
        self.assertNotIn("E:/SDY/private", encoded)
        self.assertNotIn("sk-test-public-fixture", encoded)
        self.assertNotIn("super-secret-value", encoded)

    def test_learning_cli_builds_sanitized_repro_package_from_saved_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "command.json"
            input_path.write_text(
                json.dumps(
                    {
                        "surface": "benchmark",
                        "command": "python E:/SDY/private/benchmark.py --json",
                        "stdout": {"status": "failed", "path": "E:/SDY/private/out.json"},
                        "expected": "public-safe no-go",
                        "actual": "absolute path leaked",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "learning",
                    "repro-package",
                    "--input-json",
                    str(input_path),
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
        self.assertEqual(payload["kind"], "aippocampus_learning_frontdoor")
        self.assertEqual(payload["mode"], "repro_package")
        self.assertEqual(payload["repro_package"]["surface"], "benchmark")
        self.assertNotIn("E:/SDY/private", encoded)


if __name__ == "__main__":
    unittest.main()
