from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
TOOLS_SMOKE = REPO_ROOT / "tools" / "aippocampus" / "smoke"
for path in (SCRIPTS, TOOLS_SMOKE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import smoke_fresh_thread_real_history as smoke  # noqa: E402


class FreshThreadRealHistorySmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.registry_path = self.root / "registry" / "threads.json"
        self.registry_path.parent.mkdir()
        threads = []
        for index in range(1, 4):
            messages = self.root / "clean-source" / f"messages-{index}.jsonl"
            messages.parent.mkdir(exist_ok=True)
            messages.write_text(
                json.dumps(
                    {
                        "message_id": f"msg-{index}",
                        "turn_id": f"turn-{index}",
                        "turn_index": index + 3,
                        "source_line": 50 + index,
                        "role": "assistant",
                        "phase": "final_answer",
                        "text": f"OldProject {index} 的测试命令是 pytest -q；这只适用于旧仓库。",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            threads.append(
                {
                    "thread_key": f"session:old-project-test-command-{index}",
                    "title": f"OldProject test command {index}",
                    "project_label": f"OldProject {index}",
                    "keywords": ["source-backed evidence", "测试命令", "pytest"],
                    "summary": f"OldProject {index} used pytest -q as its test command.",
                    "paths": {"clean_source_messages_jsonl": str(messages)},
                }
            )
        self.registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": threads,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_smoke_verifies_reopenability_and_current_repo_negative_control(self) -> None:
        result = smoke.run_fresh_thread_real_history_smoke(
            registry_path=self.registry_path,
            cwd=self.workspace,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["privacy"], "aggregate_hash_only")
        self.assertEqual(result["checks"]["ready_lock_reopenability"]["status"], "passed")
        self.assertEqual(result["checks"]["thread_only_lock_boundary"]["status"], "passed")
        self.assertEqual(result["checks"]["current_repo_fact_negative_control"]["status"], "passed")
        self.assertEqual(result["checks"]["current_repo_fact_negative_control"]["evidence_count"], 0)
        self.assertEqual(result["registry"]["sample_limit"], 3)
        self.assertEqual(result["registry"]["minimum_sample_count"], 2)
        self.assertEqual(result["registry"]["eligible_clean_source_row_count"], 3)
        self.assertEqual(result["registry"]["selected_reopenable_thread_count"], 3)
        self.assertEqual(result["registry"]["sampled_reopenable_ref_count"], 3)
        self.assertEqual(result["sample_coverage_status"], "passed")

        encoded = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("OldProject", encoded)
        self.assertNotIn("pytest -q", encoded)
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn("session:old-project-test-command-1", encoded)

    def test_smoke_reports_insufficient_sample_coverage_without_false_expanded_claim(self) -> None:
        one_ref_registry = self.root / "one-ref" / "threads.json"
        one_ref_registry.parent.mkdir()
        messages = self.root / "one-ref-clean-source" / "messages.jsonl"
        messages.parent.mkdir()
        messages.write_text(
            json.dumps(
                {
                    "message_id": "msg-1",
                    "turn_id": "turn-1",
                    "turn_index": 4,
                    "source_line": 58,
                    "role": "assistant",
                    "phase": "final_answer",
                    "text": "OldProject 的测试命令是 pytest -q；这只适用于旧仓库。",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        one_ref_registry.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:old-project-test-command",
                            "paths": {"clean_source_messages_jsonl": str(messages)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = smoke.run_fresh_thread_real_history_smoke(
            registry_path=one_ref_registry,
            cwd=self.workspace,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "insufficient_sample_coverage")
        self.assertEqual(result["sample_coverage_status"], "insufficient_sample_coverage")
        self.assertEqual(result["registry"]["selected_reopenable_thread_count"], 1)
        self.assertEqual(result["registry"]["sample_gap"], 1)
        self.assertIn("multi-ref real-history fresh-thread coverage", result["cannot_claim"])

    def test_smoke_can_report_insufficient_registry_without_false_claim(self) -> None:
        empty_registry = self.root / "empty" / "threads.json"
        empty_registry.parent.mkdir()
        empty_registry.write_text(
            json.dumps({"schema_version": 1, "threads": []}),
            encoding="utf-8",
        )

        result = smoke.run_fresh_thread_real_history_smoke(
            registry_path=empty_registry,
            cwd=self.workspace,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "insufficient_real_history")
        self.assertEqual(result["cannot_claim"][0], "real-history fresh-thread recall boundary passed")
        self.assertEqual(result["registry"]["selected_reopenable_thread_count"], 0)
        self.assertEqual(result["sample_coverage_status"], "insufficient_real_history")


if __name__ == "__main__":
    unittest.main()
