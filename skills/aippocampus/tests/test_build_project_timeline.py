from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import build_project_timeline as timeline  # noqa: E402


class ProjectTimelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry = self.root / "registry" / "threads.json"
        self.registry.parent.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_clean_source(self, name: str, timestamp: str, user: str, assistant: str) -> tuple[Path, Path]:
        clean = self.root / name / "clean-source"
        clean.mkdir(parents=True)
        messages = clean / "messages.jsonl"
        turns = clean / "turns.jsonl"
        rows = [
            {
                "message_id": f"{name}-u",
                "turn_id": f"{name}-turn",
                "source_line": 10,
                "timestamp": timestamp,
                "role": "user",
                "phase": "",
                "turn_index": 4,
                "text": user,
            },
            {
                "message_id": f"{name}-a",
                "turn_id": f"{name}-turn",
                "source_line": 12,
                "timestamp": timestamp,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 4,
                "is_final": True,
                "text": assistant,
            },
        ]
        messages.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        turns.write_text(
            json.dumps(
                {
                    "turn_id": f"{name}-turn",
                    "turn_index": 4,
                    "user_line": 10,
                    "assistant_line": 12,
                    "message_ids": [f"{name}-u", f"{name}-a"],
                    "assistant_phase": "final_answer",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return messages, turns

    def test_build_project_timeline_uses_latest_clean_turns(self) -> None:
        old_messages, old_turns = self._write_clean_source(
            "old",
            "2026-05-20T00:00:00Z",
            "旧问题",
            "旧回答",
        )
        new_messages, new_turns = self._write_clean_source(
            "new",
            "2026-05-25T00:00:00Z",
            "现在 T-Sense 是否该重写 Go runtime？",
            "推向市场前做 Go runtime spike 有意义，但不要重写整个 app。",
        )
        entries = [
            {
                "thread_key": "session:old",
                "title": "T-Sense old",
                "project_key": "project:t-sense",
                "project_label": "T-Sense",
                "project_tags": ["tg-channel-scanner"],
                "paths": {
                    "clean_source_messages_jsonl": str(old_messages),
                    "clean_source_turns_jsonl": str(old_turns),
                },
            },
            {
                "thread_key": "session:new",
                "title": "T-Sense new",
                "project_key": "project:t-sense",
                "project_label": "T-Sense",
                "project_tags": ["tg-channel-scanner"],
                "paths": {
                    "clean_source_messages_jsonl": str(new_messages),
                    "clean_source_turns_jsonl": str(new_turns),
                },
            },
        ]
        self.registry.write_text(json.dumps({"schema_version": 1, "threads": entries}, ensure_ascii=False), encoding="utf-8")

        result = timeline.build_project_timeline(self.registry, max_per_project=5)
        project = result["projects"]["project:t-sense"]

        self.assertEqual(project["thread_count"], 2)
        self.assertEqual(project["latest_turns"][0]["thread_key"], "session:new")
        self.assertIn("Go runtime", project["latest_turns"][0]["assistant"])
        self.assertIn("T-Sense", project["project_tags"])


if __name__ == "__main__":
    unittest.main()
