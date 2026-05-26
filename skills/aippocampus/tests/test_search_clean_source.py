from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import search_clean_source as search  # noqa: E402
import registry  # noqa: E402


class SearchCleanSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.source = self.cwd / ".aippocampus" / "clean-source"
        self.source.mkdir(parents=True)
        messages = [
            {
                "id": "msg_user",
                "source_line": 10,
                "role": "user",
                "phase": "",
                "turn_index": 1,
                "is_final": False,
                "text": "为什么我们要做 AIppocampus？",
            },
            {
                "id": "msg_final",
                "source_line": 13,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 1,
                "is_final": True,
                "text": "AIppocampus 是清洗后的原文记忆库。",
            },
            {
                "id": "msg_fallback",
                "source_line": 21,
                "role": "assistant",
                "phase": "commentary",
                "turn_index": 2,
                "is_final": False,
                "text": "没有 final 时保留 commentary fallback。",
            },
        ]
        with (self.source / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for message in messages:
                f.write(json.dumps(message, ensure_ascii=False) + "\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_searches_clean_source_without_raw_rollout(self) -> None:
        result = search.search_clean_source(self.cwd, ["原文记忆库"], limit=5)

        self.assertEqual(result["source"], str(self.source / "messages.jsonl"))
        self.assertEqual(result["matches"][0]["source_line"], 13)
        self.assertEqual(result["matches"][0]["phase"], "final_answer")
        self.assertIn("AIppocampus 是清洗后的原文记忆库", result["matches"][0]["snippet"])

    def test_registry_deep_search_prefers_clean_source_without_sqlite(self) -> None:
        entry = {
            "paths": {
                "clean_source_messages_jsonl": str(self.source / "messages.jsonl"),
                "sqlite": str(self.cwd / "missing.sqlite"),
            }
        }

        score, hits = registry.deep_search_entry(entry, ["原文记忆库"], max_hits=2)

        self.assertGreater(score, 0)
        self.assertEqual(hits[0]["line"], 13)
        self.assertEqual(hits[0]["phase"], "final_answer")


if __name__ == "__main__":
    unittest.main()
