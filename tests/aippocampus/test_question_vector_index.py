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

from aippocampus_runtime.question import vector_index as qvi  # noqa: E402


class QuestionVectorIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_local_index_returns_stable_source_ids_not_truth_claims(self) -> None:
        index = qvi.LocalQuestionVectorIndex()
        index.add(
            "thread-a:turn-1:question",
            [1.0, 0.0],
            {"clean_source_ref": "thread-a/clean-source/turns.jsonl#1"},
        )
        index.add("thread-b:turn-2:question", [0.0, 1.0])

        results = index.search([0.9, 0.1], top_k=2)

        self.assertEqual(results[0].source_id, "thread-a:turn-1:question")
        self.assertGreater(results[0].score, results[1].score)
        self.assertEqual(
            results[0].metadata["clean_source_ref"], "thread-a/clean-source/turns.jsonl#1"
        )
        self.assertNotIn("truth", results[0].as_dict())

    def test_local_index_supports_allowlist_and_remove(self) -> None:
        index = qvi.LocalQuestionVectorIndex()
        index.add("question:one", [1, 0])
        index.add("question:two", [0, 1])

        results = index.search([1, 0], allow_source_ids=["question:two"])

        self.assertEqual([item.source_id for item in results], ["question:two"])
        self.assertTrue(index.remove("question:two"))
        self.assertFalse(index.remove("question:two"))
        self.assertEqual([item.source_id for item in index.search([1, 0])], ["question:one"])

    def test_local_index_persists_rebuildable_sanitized_payload(self) -> None:
        index = qvi.LocalQuestionVectorIndex()
        index.add("question:source", [0.5, 0.5], {"scope": "question_tracking"})
        path = self.root / "question_index.json"

        index.write(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        loaded = qvi.LocalQuestionVectorIndex.load(path)

        self.assertEqual(payload["kind"], "aippocampus_question_vector_index")
        self.assertEqual(
            payload["truth_boundary"],
            "vector_neighbors_are_hints_requiring_clean_source_verification",
        )
        self.assertEqual(loaded.dimensions, 2)
        self.assertEqual(loaded.search([0.5, 0.5])[0].source_id, "question:source")

    def test_local_index_rejects_unstable_or_mismatched_vectors(self) -> None:
        index = qvi.LocalQuestionVectorIndex()

        with self.assertRaisesRegex(ValueError, "source_id"):
            index.add("  ", [1.0])
        with self.assertRaisesRegex(ValueError, "empty"):
            index.add("question:empty", [])

        index.add("question:one", [1.0, 0.0])
        with self.assertRaisesRegex(ValueError, "dimensions"):
            index.add("question:bad", [1.0, 0.0, 0.0])
        with self.assertRaisesRegex(ValueError, "dimensions"):
            index.search([1.0])


if __name__ == "__main__":
    unittest.main()
