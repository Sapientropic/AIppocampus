from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

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

    def test_selected_fuzzy_life_wide_prompt_hits_expected_clean_source_without_leaking_text(
        self,
    ) -> None:
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
        self.assertFalse(result["sample_gate_ok"])
        self.assertFalse(result["quality_gate_ok"])
        self.assertIn("semantic_sidecar_sample_coverage", result["cannot_claim"])

    def test_eval_separates_selected_case_quality_from_sample_size(self) -> None:
        self._write_fixture(with_sidecar=True)

        result = recall_eval.run_source_evidence_recall_eval(
            registry_path=self.registry,
            max_cases=1,
            min_cases=2,
            top_k=3,
            min_hit_rate=1.0,
            require_semantic_sidecar=True,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "insufficient_selected_cases")
        self.assertEqual(result["case_count"], 1)
        self.assertEqual(result["passed_count"], 1)
        self.assertEqual(result["top_k_hit_rate"], 1.0)
        self.assertEqual(
            result["rate_estimates"]["top_k_hit_rate"]["confidence_interval"]["method"],
            "wilson_score",
        )
        self.assertFalse(result["sample_gate_ok"])
        self.assertTrue(result["quality_gate_ok"])
        self.assertEqual(result["gate_diagnostics"]["sample_gap"], 1)
        self.assertEqual(result["gate_diagnostics"]["sample_status"], "insufficient_selected_cases")
        self.assertEqual(result["gate_diagnostics"]["quality_status"], "sufficient")
        self.assertEqual(
            result["gate_diagnostics"]["rate_estimates"]["top_k_hit_rate"]["denominator"],
            1,
        )
        self.assertIn("semantic_sidecar_sample_coverage", result["cannot_claim"])
        self.assertNotIn("selected_semantic_source_evidence_quality", result["cannot_claim"])

    def test_dynamic_source_uses_turn_scope_when_terms_live_on_sibling_message(
        self,
    ) -> None:
        case = {
            "case_id": "evidence:test-turn-scope",
            "query_terms": ["lighthouse", "continuity"],
            "scope_labels": ["personal_reflection"],
            "expected": {
                "thread_key": "session:life",
                "message_id": "msg_user",
                "turn_id": "turn_life",
            },
        }
        corpus = [
            {
                "thread_key": "session:life",
                "text_low": "plain user request",
                "entry": {},
                "message": {
                    "message_id": "msg_user",
                    "turn_id": "turn_life",
                    "scope_labels": ["personal_reflection"],
                    "text": "Plain user request",
                },
            },
            {
                "thread_key": "session:life",
                "text_low": "lighthouse continuity pivot",
                "entry": {},
                "message": {
                    "message_id": "msg_assistant",
                    "turn_id": "turn_life",
                    "scope_labels": [],
                    "text": "lighthouse continuity pivot",
                },
            },
            {
                "thread_key": "session:life",
                "text_low": "lighthouse continuity unrelated turn",
                "entry": {},
                "message": {
                    "message_id": "msg_other_turn",
                    "turn_id": "turn_other",
                    "scope_labels": [],
                    "text": "lighthouse continuity unrelated turn",
                },
            },
        ]

        result = recall_eval.search_expected_evidence_dynamic_source(
            corpus, case, top_k=1
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["rank"], 1)

    def test_dynamic_source_scores_source_terms_not_generic_prompt_frame(
        self,
    ) -> None:
        case = {
            "case_id": "evidence:test-source-terms",
            "query_terms": [
                "之前",
                "那个",
                "life-wide、像个人线索或想法火花的片段，和",
                "片段",
                "lighthouse",
                "continuity",
            ],
            "source_terms": ["lighthouse", "continuity"],
            "scope_labels": ["personal_reflection"],
            "expected": {
                "thread_key": "session:life",
                "message_id": "msg_expected",
                "turn_id": "turn_life",
            },
        }
        corpus = [
            {
                "thread_key": "session:life",
                "text_low": (
                    "life-wide、像个人线索或想法火花的片段，和 "
                    "life-wide、像个人线索或想法火花的片段，和 "
                    "之前 那个 片段"
                ),
                "entry": {},
                "message": {
                    "message_id": "msg_generic",
                    "turn_id": "turn_generic",
                    "scope_labels": ["personal_reflection"],
                    "text": (
                        "life-wide、像个人线索或想法火花的片段，和 "
                        "life-wide、像个人线索或想法火花的片段，和 "
                        "之前 那个 片段"
                    ),
                },
            },
            {
                "thread_key": "session:life",
                "text_low": "lighthouse continuity pivot",
                "entry": {},
                "message": {
                    "message_id": "msg_expected",
                    "turn_id": "turn_life",
                    "scope_labels": ["personal_reflection"],
                    "text": "lighthouse continuity pivot",
                },
            },
        ]

        result = recall_eval.search_expected_evidence_dynamic_source(
            corpus, case, top_k=1
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["rank"], 1)

    def test_failure_diagnostics_classify_scope_term_split_without_private_text(self) -> None:
        case = {
            "case_id": "evidence:test-split",
            "query_terms": ["lighthouse", "continuity"],
            "scope_labels": ["personal_reflection"],
            "expected": {
                "thread_key": "session:life",
                "message_id": "msg_user",
                "turn_id": "turn_life",
            },
        }
        corpus = [
            {
                "thread_key": "session:life",
                "text_low": "plain user request",
                "entry": {},
                "message": {
                    "message_id": "msg_user",
                    "turn_id": "turn_life",
                    "scope_labels": ["personal_reflection"],
                    "text": "Plain user request",
                },
            },
            {
                "thread_key": "session:life",
                "text_low": "lighthouse continuity pivot",
                "entry": {},
                "message": {
                    "message_id": "msg_assistant",
                    "turn_id": "turn_life",
                    "scope_labels": [],
                    "text": "lighthouse continuity pivot",
                },
            },
        ]

        diagnostics = recall_eval.source_evidence_failure_diagnostics(
            cases=[case],
            results=[(case, {"passed": False, "rank": None})],
            corpus=corpus,
            top_k=5,
            ranking="dynamic_source",
        )

        rendered = json.dumps(diagnostics, ensure_ascii=False)
        self.assertEqual(diagnostics["failed_count"], 1)
        self.assertEqual(
            diagnostics["categories"]["scope_term_split_across_expected_turn"], 1
        )
        self.assertEqual(
            diagnostics["failed_cases"][0]["category"],
            "scope_term_split_across_expected_turn",
        )
        self.assertNotIn("lighthouse", rendered)
        self.assertNotIn("msg_user", rendered)


if __name__ == "__main__":
    unittest.main()
