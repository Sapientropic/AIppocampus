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
        messages = self.root / "clean-source" / "messages.jsonl"
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
        self.registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:old-project-test-command",
                            "title": "OldProject test command",
                            "project_label": "OldProject",
                            "keywords": ["source-backed evidence", "测试命令", "pytest"],
                            "summary": "OldProject used pytest -q as its test command.",
                            "paths": {"clean_source_messages_jsonl": str(messages)},
                        }
                    ],
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
        self.assertEqual(result["registry"]["selected_reopenable_thread_count"], 1)

        encoded = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("OldProject", encoded)
        self.assertNotIn("pytest -q", encoded)
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn("session:old-project-test-command", encoded)

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


if __name__ == "__main__":
    unittest.main()
