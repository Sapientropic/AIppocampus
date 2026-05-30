from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

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

import build_concept_graph as concept_graph  # noqa: E402
import theme_emergence as themes  # noqa: E402


class ThemeEmergenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.jobs_path = self.root / "subconscious_jobs.jsonl"
        self.concept_graph = self.root / "concept_index.sqlite"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_rows(self, rows: list[dict[str, Any]]) -> None:
        self.jobs_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    def build_graph(self) -> None:
        associations = self.root / "associations.json"
        associations.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "context continuity": {
                            "term": "context continuity",
                            "status": "verified",
                            "confidence": 0.95,
                            "hit_count": 12,
                            "related_terms": ["source-backed recall", "continuity map"],
                            "threads": [],
                        },
                        "agent alignment": {
                            "term": "agent alignment",
                            "status": "verified",
                            "confidence": 0.94,
                            "hit_count": 12,
                            "related_terms": ["source-backed recall", "continuity map"],
                            "threads": [],
                        },
                        "dashboard layout": {
                            "term": "dashboard layout",
                            "status": "verified",
                            "confidence": 0.92,
                            "hit_count": 8,
                            "related_terms": ["visual hierarchy"],
                            "threads": [],
                        },
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        concept_graph.build_concept_graph(associations, self.concept_graph)

    def question_link(self, suffix: str, *, concepts: list[str] | None = None) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": "aippocampus_subconscious_job_finding",
            "created_at": f"2026-05-2{suffix}T00:00:00Z",
            "job": "question_tracking",
            "finding_kind": "question_link",
            "fingerprint": f"sf_link_{suffix}",
            "title": f"Question continuity {suffix}",
            "summary": "Tracked recurring question continuity.",
            "confidence": 0.86,
            "source": "deterministic_question_tracking",
            "question_cluster_id": f"ql_{suffix}",
            "linked_question_short": f"context continuity {suffix}",
            "question_count": 2,
            "link_type": "recurring",
            "first_seen": f"2026-05-2{suffix}T00:00:00Z",
            "last_seen": f"2026-05-2{suffix}T12:00:00Z",
            "concepts": concepts or ["context continuity", "agent alignment"],
            "source_refs": [
                {
                    "thread_key": f"session:{suffix}",
                    "title": "AIppocampus",
                    "message_id": f"msg_{suffix}",
                    "source_line": int(suffix) * 10,
                    "timestamp": f"2026-05-2{suffix}T00:00:00Z",
                }
            ],
            "linked_questions": [
                {
                    "question_id": f"q_{suffix}",
                    "question_short": f"context continuity {suffix}",
                    "what_features": concepts or ["context continuity", "agent alignment"],
                }
            ],
        }

    def frontier(self, suffix: str, *, related: bool) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": "aippocampus_subconscious_job_finding",
            "created_at": f"2026-05-2{suffix}T18:00:00Z",
            "job": "question_extraction",
            "finding_kind": "frontier_marker",
            "fingerprint": f"sf_frontier_{suffix}",
            "frontier_type": "blocked" if related else "scope_boundary",
            "linked_question_short": "context continuity" if related else "dashboard layout",
            "boundary_reason": (
                "Context continuity work stopped at a missing source-backed recall check."
                if related
                else "Dashboard layout exploration stopped at viewport scope."
            ),
            "concepts": ["context continuity"] if related else ["dashboard layout"],
            "source_refs": [
                {
                    "thread_key": f"session:f{suffix}",
                    "title": "Frontier",
                    "message_id": f"msg_frontier_{suffix}",
                    "source_line": int(suffix) * 100,
                }
            ],
        }

    def test_no_cluster_when_fewer_than_three_recurring_links(self) -> None:
        self.build_graph()
        self.write_rows([self.question_link("1"), self.question_link("2")])

        result = themes.run_theme_emergence(
            jobs_path=self.jobs_path,
            concept_graph_path=self.concept_graph,
            no_write=True,
        )

        self.assertEqual(result["theme_count"], 0)
        self.assertEqual(result["question_link_count"], 2)

    def test_no_cluster_without_shared_concept_neighbors(self) -> None:
        self.build_graph()
        self.write_rows(
            [
                self.question_link("1", concepts=["context continuity"]),
                self.question_link("2", concepts=["agent alignment"]),
                self.question_link("3", concepts=["dashboard layout"]),
            ]
        )

        result = themes.run_theme_emergence(
            jobs_path=self.jobs_path,
            concept_graph_path=self.concept_graph,
            no_write=True,
        )

        self.assertEqual(result["theme_count"], 0)

    def test_requires_concept_graph_before_theme_claim(self) -> None:
        self.write_rows([self.question_link("1"), self.question_link("2"), self.question_link("3")])

        result = themes.run_theme_emergence(
            jobs_path=self.jobs_path,
            concept_graph_path=self.root / "missing.sqlite",
            no_write=True,
        )

        self.assertFalse(result["concept_graph_available"])
        self.assertEqual(result["theme_count"], 0)

    def test_builds_supported_theme_candidate_with_boundary_map(self) -> None:
        self.build_graph()
        self.write_rows(
            [
                self.question_link("1"),
                self.question_link("2"),
                self.question_link("3"),
                self.frontier("4", related=True),
                self.frontier("5", related=False),
            ]
        )

        result = themes.run_theme_emergence(
            jobs_path=self.jobs_path,
            concept_graph_path=self.concept_graph,
            no_write=True,
        )

        self.assertEqual(result["theme_count"], 1)
        theme = result["themes"][0]
        self.assertEqual(theme["finding_kind"], "theme_candidate")
        self.assertEqual(theme["cluster_method"], "deterministic_shared_concept_neighbors_v1")
        self.assertGreaterEqual(len(theme["shared_concepts"]), 2)
        self.assertEqual(theme["question_link_count"], 3)
        self.assertEqual(theme["linked_question_count"], 6)
        self.assertEqual(theme["thread_span"], 4)
        self.assertGreaterEqual(theme["time_span_days"], 2)
        top_level_message_ids = {
            str(ref.get("message_id") or "") for ref in theme["source_refs"]
        }
        self.assertIn("msg_1", top_level_message_ids)
        self.assertIn("msg_2", top_level_message_ids)
        self.assertIn("msg_3", top_level_message_ids)
        self.assertIn("msg_frontier_4", top_level_message_ids)
        self.assertNotIn("msg_frontier_5", top_level_message_ids)
        self.assertEqual(theme["question_link_refs"][0]["source_refs"][0]["message_id"], "msg_1")
        self.assertEqual(theme["question_link_refs"][0]["source_refs"][0]["source_line"], 10)
        self.assertEqual(theme["boundary_map"]["frontier_count"], 1)
        self.assertEqual(theme["frontier_refs"][0]["frontier_type"], "blocked")
        self.assertEqual(theme["frontier_refs"][0]["source_refs"][0]["message_id"], "msg_frontier_4")
        self.assertFalse(theme["naming_evidence"]["llm_naming"])
        self.assertEqual(
            theme["match_evidence"]["method"],
            "deterministic_shared_concept_graph_neighbors_v1",
        )

    def test_appends_theme_candidate_without_duplicate_rerun(self) -> None:
        self.build_graph()
        self.write_rows([self.question_link("1"), self.question_link("2"), self.question_link("3")])

        first = themes.run_theme_emergence(
            jobs_path=self.jobs_path,
            concept_graph_path=self.concept_graph,
        )
        second = themes.run_theme_emergence(
            jobs_path=self.jobs_path,
            concept_graph_path=self.concept_graph,
        )
        rows = [
            json.loads(line)
            for line in self.jobs_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        theme_rows = [row for row in rows if row.get("finding_kind") == "theme_candidate"]

        self.assertEqual(first["fresh_theme_count"], 1)
        self.assertEqual(second["fresh_theme_count"], 0)
        self.assertEqual(len(theme_rows), 1)
        self.assertEqual(theme_rows[0]["source"], "deterministic_theme_emergence")


if __name__ == "__main__":
    unittest.main()
