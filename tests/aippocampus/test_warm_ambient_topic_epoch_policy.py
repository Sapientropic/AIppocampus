from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.warm_ambient import recall as warm  # noqa: E402


class WarmAmbientTopicEpochPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.cache_path = self.root / "ambient-thread-cache.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_clean_thread(self, thread_key: str, rows: list[dict]) -> Path:
        clean_dir = self.root / "clean" / thread_key.replace(":", "-")
        clean_dir.mkdir(parents=True)
        messages_path = clean_dir / "messages.jsonl"
        messages_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
        return messages_path

    def _write_registry(self, entries: list[dict]) -> Path:
        registry_path = self.root / "registry" / "threads.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(
            json.dumps({"schema_version": 1, "threads": entries}, ensure_ascii=False),
            encoding="utf-8",
        )
        return registry_path

    def test_topic_epoch_suppress_with_supported_cards_rotates_instead_of_blind_suppress(self) -> None:
        messages = self._write_clean_thread(
            "session:old",
            [
                {
                    "message_id": "msg-1",
                    "source_line": 42,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": "The source says warm ambient recall should keep source-addressable cards usable.",
                }
            ],
        )
        registry_path = self._write_registry(
            [
                {
                    "thread_key": "session:old",
                    "title": "Warm ambient recall",
                    "paths": {"clean_source_messages_jsonl": str(messages)},
                }
            ]
        )

        def scout_fn(scout, payload, **kwargs):
            del scout, payload, kwargs
            return {
                "decision": "evidence",
                "confidence": 0.92,
                "topic_epoch_action": "suppress",
                "topic_epoch_label": "ambient recall drift",
                "topic_epoch_reason": "Topic changed, rotate instead of reusing the prior epoch.",
                "candidates": [
                    {
                        "theme": "source-addressable warm recall",
                        "support_level": "evidence",
                        "key_line": "warm ambient recall should keep source-addressable cards usable",
                        "matched_terms": ["warm ambient recall", "source-addressable"],
                        "source_refs": [
                            {"thread_key": "session:old", "message_id": "msg-1", "line": 42}
                        ],
                    }
                ],
            }

        result = warm.run_warm_ambient_recall(
            "继续 warm ambient recall source-addressable 这条线",
            cwd=self.workspace,
            thread_id="thread-a",
            registry_path=registry_path,
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("deep_theme_matcher",),
            quorum=1,
            timeout=0.5,
        )

        self.assertTrue(result["available"])
        self.assertNotEqual(result["status"], "suppressed")
        self.assertEqual(result["status"], "written")
        self.assertEqual(result["cache_write"]["status"], "written")
        self.assertEqual(result["cards"][0]["source_validation"]["status"], "supported")
        self.assertEqual(result["topic_epoch_decision"]["action"], "rotate")
        self.assertEqual(result["topic_epoch_decision"]["requested_action"], "suppress")
        self.assertEqual(result["topic_epoch_decision"]["write_policy"], "rotate_epoch")
        self.assertFalse(result["topic_epoch_decision"]["suppress_write"])
        self.assertNotIn("topic_epoch_suppressed", result["suppression_reason_buckets"])
        self.assertEqual(
            result["suppression_diagnostics"]["topic_epoch_vote_counts_by_family"],
            {"deep_theme_matcher": {"suppress": 1}},
        )


if __name__ == "__main__":
    unittest.main()
