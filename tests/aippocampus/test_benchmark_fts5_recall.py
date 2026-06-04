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

import benchmark_fts5_recall as benchmark  # noqa: E402
from aippocampus_runtime.recall.index_builder import make_sqlite  # noqa: E402


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


class Fts5RecallBenchmarkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.clean = self.root / "thread" / "clean-source"
        self.index = self.root / "thread" / "index"
        self.index.mkdir(parents=True)
        self.sqlite = self.index / "source_index.sqlite"
        self.messages = [
            {
                "message_id": "msg-target",
                "turn_id": "turn-target",
                "source_line": 10,
                "raw_start_line": 10,
                "raw_end_line": 10,
                "role": "user",
                "phase": "",
                "text": "The blue lighthouse recall marker belongs to this source message.",
            },
            {
                "message_id": "msg-other",
                "turn_id": "turn-other",
                "source_line": 20,
                "raw_start_line": 20,
                "raw_end_line": 20,
                "role": "assistant",
                "phase": "final_answer",
                "is_final": True,
                "text": "A different final answer about unrelated project notes.",
            },
        ]
        write_jsonl(self.clean / "messages.jsonl", self.messages)
        make_sqlite(
            self.sqlite,
            [
                {
                    "line": 10,
                    "timestamp": None,
                    "role": "user",
                    "kind": "message",
                    "phase": "",
                    "turn_index": 1,
                    "is_final": False,
                    "sha1": "sha-target",
                    "text": self.messages[0]["text"],
                },
                {
                    "line": 20,
                    "timestamp": None,
                    "role": "assistant",
                    "kind": "message",
                    "phase": "final_answer",
                    "turn_index": 1,
                    "is_final": True,
                    "sha1": "sha-other",
                    "text": self.messages[1]["text"],
                },
            ],
            anchors=[],
            turns=[],
        )
        self.registry_path = self.root / "threads.json"
        self.registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:test-thread",
                            "title": "Private test thread",
                            "paths": {
                                "clean_source_messages_jsonl": str(self.clean / "messages.jsonl"),
                                "sqlite": str(self.sqlite),
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_build_cases_are_source_backed_and_redacted_by_default(self) -> None:
        registry = benchmark.load_registry(self.registry_path)

        cases, corpus = benchmark.build_eval_cases(registry, sample_size=1, seed=7)

        self.assertEqual(corpus["registry_threads"], 1)
        self.assertEqual(cases[0].expected_message_id, "msg-target")
        self.assertEqual(cases[0].expected_line_start, 10)
        public = cases[0].to_result_stub(include_private_text=False)
        self.assertNotIn("query", public)
        self.assertNotIn("snippet", public)
        self.assertIn("query_sha1", public)

    def test_build_cases_skip_sensitive_candidates_with_shared_policy(self) -> None:
        sensitive_text = (
            "Connect with postgres://user:pass@db.internal:5432/app "
            "and contact person@example.com for access."
        )
        write_jsonl(
            self.clean / "messages.jsonl",
            [
                *self.messages,
                {
                    "message_id": "msg-sensitive",
                    "turn_id": "turn-sensitive",
                    "source_line": 30,
                    "raw_start_line": 30,
                    "raw_end_line": 30,
                    "role": "user",
                    "phase": "",
                    "text": sensitive_text,
                },
            ],
        )
        registry = benchmark.load_registry(self.registry_path)

        cases, corpus = benchmark.build_eval_cases(registry, sample_size=4, seed=7)

        self.assertEqual(corpus["messages_skipped_sensitive"], 1)
        self.assertNotIn("msg-sensitive", {case.expected_message_id for case in cases})
        encoded = json.dumps(
            [case.to_result_stub(include_private_text=False) for case in cases],
            ensure_ascii=False,
        )
        self.assertNotIn("db.internal", encoded)
        self.assertNotIn("person@example.com", encoded)

    def test_evaluate_case_marks_fts5_hit_rank(self) -> None:
        case = benchmark.EvalCase(
            case_id="case-hit",
            case_type="source_phrase",
            thread_key="session:test-thread",
            sqlite_path=self.sqlite,
            clean_source_path=self.clean / "messages.jsonl",
            query="blue lighthouse recall marker",
            query_terms=["blue lighthouse recall marker"],
            expected_message_id="msg-target",
            expected_line_start=10,
            expected_line_end=10,
            role="user",
            phase="",
            snippet="private source text",
        )

        result = benchmark.evaluate_case(case, top_k=5)

        self.assertEqual(result["fts5"]["rank"], 1)
        self.assertTrue(result["fts5"]["hit_top_k"])
        self.assertNotIn("query", result)
        self.assertNotIn("snippet", result)

    def test_summarize_results_counts_misses(self) -> None:
        hit = {
            "case_type": "source_phrase",
            "fts5": {"rank": 1, "hit_top_k": True, "expected_line_present": True},
        }
        miss = {
            "case_type": "source_phrase",
            "fts5": {"rank": None, "hit_top_k": False, "expected_line_present": False},
        }

        metrics = benchmark.summarize_results([hit, miss], top_k=5)

        self.assertEqual(metrics["total_cases"], 2)
        self.assertEqual(metrics["fts5"]["hit_top5"], 1)
        self.assertEqual(metrics["fts5"]["miss_top5"], 1)
        self.assertEqual(metrics["fts5"]["hit_rate_top5"], 0.5)
        self.assertEqual(
            metrics["fts5"]["miss_categories_top_k"]["expected_line_absent_from_sqlite"], 1
        )


if __name__ == "__main__":
    unittest.main()
