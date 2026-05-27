from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import smoke_source_evidence_recall_eval as recall_eval  # noqa: E402


class SourceEvidenceRecallEvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry = self.root / "registry" / "threads.json"
        self.registry.parent.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_fixture(self, *, with_sidecar: bool = True) -> Path:
        clean = self.root / "thread-life" / "clean-source"
        clean.mkdir(parents=True)
        (clean / "messages.jsonl").write_text(
            json.dumps(
                {
                    "message_id": "msg_life",
                    "turn_id": "turn_life",
                    "source_line": 7,
                    "timestamp": "2026-05-27T00:00:00Z",
                    "role": "user",
                    "turn_index": 1,
                    "scope_labels": [],
                    "text": "The lighthouse metaphor felt like a pivot for long-term continuity.",
                },
                ensure_ascii=False,
            )
            + "\n"
            + json.dumps(
                {
                    "message_id": "msg_distractor",
                    "turn_id": "turn_distractor",
                    "source_line": 13,
                    "timestamp": "2026-05-27T00:00:01Z",
                    "role": "user",
                    "turn_index": 2,
                    "scope_labels": ["technical_work"],
                    "text": "A database migration note about indexes and schema checks.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (clean / "turns.jsonl").write_text(
            json.dumps(
                {
                    "turn_id": "turn_life",
                    "turn_index": 1,
                    "message_ids": ["msg_life"],
                    "scope_labels": [],
                },
                ensure_ascii=False,
            )
            + "\n"
            + json.dumps(
                {
                    "turn_id": "turn_distractor",
                    "turn_index": 2,
                    "message_ids": ["msg_distractor"],
                    "scope_labels": ["technical_work"],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        if with_sidecar:
            (clean / "semantic-scope-labels.jsonl").write_text(
                json.dumps(
                    {
                        "message_id": "msg_life",
                        "turn_id": "turn_life",
                        "source": "deepseek_subconscious_scope_labels",
                        "scope_labels": ["personal_reflection", "idea_seed", "life_context"],
                        "confidence": 0.94,
                        "label_evidence": [
                            {
                                "label": "personal_reflection",
                                "reason": "The source says the metaphor felt like a continuity pivot.",
                                "confidence": 0.88,
                            },
                            {
                                "label": "life_context",
                                "reason": "The source frames continuity as recurring lived context.",
                                "confidence": 0.94,
                            },
                        ],
                        "source_refs": [
                            {
                                "thread_key": "session:life",
                                "message_id": "msg_life",
                                "turn_id": "turn_life",
                                "source_line": 7,
                                "role": "user",
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
        self.registry.write_text(
            json.dumps(
                {
                    "threads": [
                        {
                            "thread_key": "session:life",
                            "title": "Private Life Title",
                            "project_key": "project:life",
                            "project_label": "Private Life",
                            "paths": {
                                "clean_source_messages_jsonl": str(clean / "messages.jsonl"),
                                "clean_source_turns_jsonl": str(clean / "turns.jsonl"),
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return clean

    def test_selected_fuzzy_life_wide_prompt_hits_expected_clean_source_without_leaking_text(self) -> None:
        self._write_fixture(with_sidecar=True)

        result = recall_eval.run_source_evidence_recall_eval(
            registry_path=self.registry,
            max_cases=1,
            min_cases=1,
            top_k=3,
            min_hit_rate=1.0,
            require_semantic_sidecar=True,
        )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["ok"], rendered)
        self.assertEqual(result["status"], "sufficient")
        self.assertEqual(result["case_count"], 1)
        self.assertEqual(result["passed_count"], 1)
        self.assertEqual(result["top_k_hit_rate"], 1.0)
        self.assertEqual(result["ranking"], "dynamic_source")
        self.assertIn("corpus rarity", result["selection"]["boundary"])
        self.assertEqual(result["cases"][0]["prompt_kind"], "fuzzy_life_wide_source_evidence")
        self.assertTrue(result["cases"][0]["expected_evidence"].startswith("evidence:"))
        self.assertIn("personal_reflection", result["label_coverage"])
        self.assertNotIn("lighthouse", rendered)
        self.assertNotIn("Private Life Title", rendered)
        self.assertNotIn("msg_life", rendered)
        self.assertNotIn("source_refs", rendered)
        self.assertNotIn(str(self.root), rendered)

    def test_eval_reports_insufficient_when_selected_semantic_cases_are_missing(self) -> None:
        self._write_fixture(with_sidecar=False)

        result = recall_eval.run_source_evidence_recall_eval(
            registry_path=self.registry,
            max_cases=1,
            min_cases=1,
            require_semantic_sidecar=True,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "insufficient_selected_cases")
        self.assertIn("selected_semantic_source_evidence", result["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
