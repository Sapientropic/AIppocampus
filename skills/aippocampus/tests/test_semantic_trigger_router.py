from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import semantic_trigger_router as router  # noqa: E402


class SemanticTriggerRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.candidates = self.root / "promotion_candidates.jsonl"
        self.output = self.root / "semantic_triggers.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_candidates(self, rows: list[dict]) -> None:
        with self.candidates.open("w", encoding="utf-8", newline="\n") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def test_hook_trigger_candidate_becomes_semantic_trigger(self) -> None:
        self.write_candidates(
            [
                {
                    "kind": "aippocampus_promotion_candidate",
                    "status": "staging",
                    "candidate_type": "hook_trigger",
                    "title": "AIppocampus semantic recall gate",
                    "summary": "DeepSeek semantic gate replaces brittle hard-coded cue phrases for ambient recall.",
                    "recommendation": "Use semantic aliases when user paraphrases memory continuity.",
                    "confidence": 0.86,
                    "source_refs": [
                        {"thread_key": "session:a", "title": "AIppocampus", "line": 42}
                    ],
                }
            ]
        )

        result = router.build_semantic_triggers(
            candidates_path=self.candidates, output_path=self.output
        )
        rows = [json.loads(line) for line in self.output.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(result["trigger_count"], 1)
        self.assertEqual(rows[0]["kind"], "aippocampus_semantic_trigger")
        self.assertIn("AIppocampus semantic recall gate", rows[0]["aliases"])
        self.assertEqual(rows[0]["source_refs"][0]["line"], 42)

    def test_low_confidence_or_unsourced_candidate_is_not_foreground_trigger(self) -> None:
        self.write_candidates(
            [
                {
                    "kind": "aippocampus_promotion_candidate",
                    "candidate_type": "hook_trigger",
                    "title": "Too weak",
                    "summary": "Nope",
                    "confidence": 0.4,
                    "source_refs": [{"thread_key": "session:a", "line": 1}],
                },
                {
                    "kind": "aippocampus_promotion_candidate",
                    "candidate_type": "hook_trigger",
                    "title": "No source",
                    "summary": "Nope",
                    "confidence": 0.9,
                    "source_refs": [],
                },
            ]
        )

        result = router.build_semantic_triggers(
            candidates_path=self.candidates, output_path=self.output
        )
        self.assertEqual(result["trigger_count"], 0)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
