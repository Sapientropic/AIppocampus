from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from typing import Any

from aippocampus_runtime.question import index_sidecar as sidecar


class QuestionIndexSidecarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.jobs_path = self.root / "subconscious_jobs.jsonl"
        self.index_path = self.root / "question_index.sqlite"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_rows(self, rows: list[dict[str, Any]]) -> None:
        self.jobs_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    def question_row(self, suffix: str, **overrides: Any) -> dict[str, Any]:
        data = {
            "schema_version": 1,
            "kind": "aippocampus_subconscious_job_finding",
            "created_at": f"2026-05-2{suffix}T00:00:00Z",
            "job": "question_extraction",
            "finding_kind": "question_candidate",
            "fingerprint": f"sf_question_{suffix}",
            "title": "Agent context continuity",
            "summary": "The user is asking how agent context survives compaction.",
            "confidence": 0.86,
            "source_refs": [
                {
                    "thread_key": f"session:{suffix}",
                    "title": "AIppocampus",
                    "project_label": "AIppocampus",
                    "message_id": f"msg_{suffix}",
                    "turn_id": f"turn_{suffix}",
                    "source_line": int(suffix) * 10,
                    "timestamp": f"2026-05-2{suffix}T00:00:00Z",
                }
            ],
            "question_text": "How do I keep agent context across compaction?",
            "question_short": "agent context continuity",
            "intent_orientation": "implementation",
            "what_features": ["agent memory", "context continuity", "compaction"],
            "where_context": ["AIppocampus"],
            "phase_context": "post_compaction",
            "collaboration_context": ["Codex"],
            "concepts": ["AIppocampus", "context continuity"],
        }
        data.update(overrides)
        return data

    def test_missing_sidecar_degrades_without_write(self) -> None:
        self.write_rows([self.question_row("1"), self.question_row("2")])

        result = sidecar.evaluate_question_index_sidecar(
            jobs_path=self.jobs_path,
            index_path=self.index_path,
            no_write=True,
        )

        self.assertEqual(result["question_index_status"], "missing_degraded_to_baseline")
        self.assertFalse(result["wrote"])
        self.assertEqual(result["record_count"], 2)
        self.assertEqual(result["sidecar_pair_count"], 0)
        self.assertEqual(result["recommendation"], "baseline_safe_sidecar_unavailable")
        self.assertEqual(result["sidecar_adoption"]["decision"], "degrade_to_baseline")
        self.assertEqual(result["default_enablement"]["decision"], "degrade_to_baseline")
        self.assertFalse(result["sidecar_adoption"]["default_prefilter_recommended"])

    def test_builds_reuses_and_detects_stale_sidecar(self) -> None:
        self.write_rows([self.question_row("1"), self.question_row("2")])

        first = sidecar.evaluate_question_index_sidecar(
            jobs_path=self.jobs_path,
            index_path=self.index_path,
        )
        second = sidecar.evaluate_question_index_sidecar(
            jobs_path=self.jobs_path,
            index_path=self.index_path,
        )
        self.write_rows([self.question_row("1"), self.question_row("2"), self.question_row("3")])
        stale_no_write = sidecar.evaluate_question_index_sidecar(
            jobs_path=self.jobs_path,
            index_path=self.index_path,
            no_write=True,
        )

        self.assertEqual(first["question_index_status"], "rebuilt_missing")
        self.assertTrue(first["wrote"])
        self.assertEqual(second["question_index_status"], "reused")
        self.assertEqual(stale_no_write["question_index_status"], "stale_degraded_to_baseline")
        self.assertFalse(stale_no_write["wrote"])
        self.assertEqual(
            sidecar.load_question_index_metadata(self.index_path)["truth_boundary"],
            sidecar.TRUTH_BOUNDARY,
        )

    def test_source_ref_join_survives_sidecar_lookup(self) -> None:
        self.write_rows(
            [
                self.question_row("1"),
                self.question_row(
                    "2",
                    question_text="Why does Codex forget context after compaction?",
                    question_short="Codex context loss after compaction",
                ),
                self.question_row(
                    "3",
                    title="Dashboard layout",
                    summary="Unrelated UI planning question.",
                    question_text="How should the dashboard layout work?",
                    question_short="dashboard layout",
                    what_features=["dashboard", "layout"],
                    where_context=["Other"],
                    phase_context="design",
                    concepts=["dashboard"],
                ),
            ]
        )

        result = sidecar.evaluate_question_index_sidecar(
            jobs_path=self.jobs_path,
            index_path=self.index_path,
        )

        self.assertEqual(result["question_index_status"], "rebuilt_missing")
        self.assertGreater(result["sidecar_pair_count"], 0)
        self.assertEqual(result["sidecar_pair_count"], result["source_joined_pair_count"])
        self.assertTrue(result["source_ref_join_survived"])
        self.assertEqual(result["sidecar_pair_count"], result["source_ref_key_joined_pair_count"])
        self.assertTrue(result["source_ref_key_join_survived"])
        self.assertEqual(result["source_ref_key_mismatch_count"], 0)
        self.assertEqual(result["baseline_strong_pair_coverage"], 1.0)
        self.assertEqual(result["sidecar_adoption"]["decision"], "not_needed_now")
        self.assertFalse(result["sidecar_adoption"]["sidecar_needed_now"])

    def test_sidecar_payload_does_not_store_question_text(self) -> None:
        self.write_rows([self.question_row("1"), self.question_row("2")])

        sidecar.evaluate_question_index_sidecar(
            jobs_path=self.jobs_path,
            index_path=self.index_path,
        )

        with closing(sqlite3.connect(self.index_path)) as conn:
            rows = conn.execute("SELECT payload_json FROM question_record").fetchall()
        payloads = [json.loads(str(row[0])) for row in rows]

        self.assertTrue(payloads)
        self.assertNotIn("question_text", json.dumps(payloads, ensure_ascii=False))
        self.assertNotIn("question_short", json.dumps(payloads, ensure_ascii=False))

    def test_source_ref_key_mismatch_blocks_prefilter_recommendation(self) -> None:
        self.write_rows([self.question_row("1"), self.question_row("2")])
        sidecar.evaluate_question_index_sidecar(
            jobs_path=self.jobs_path,
            index_path=self.index_path,
        )
        with closing(sqlite3.connect(self.index_path)) as conn:
            source_id = str(conn.execute("SELECT source_id FROM question_record LIMIT 1").fetchone()[0])
            conn.execute(
                "UPDATE question_record SET source_ref_keys_json = ? WHERE source_id = ?",
                (json.dumps(["stale|source|ref|key"]), source_id),
            )
            conn.commit()

        result = sidecar.evaluate_question_index_sidecar(
            jobs_path=self.jobs_path,
            index_path=self.index_path,
        )

        self.assertEqual(result["question_index_status"], "reused")
        self.assertFalse(result["source_ref_key_join_survived"])
        self.assertEqual(result["source_ref_key_mismatch_count"], 1)
        self.assertEqual(
            result["recommendation"],
            "do_not_enable_index_prefilter_until_source_ref_join_is_complete",
        )
        self.assertEqual(result["sidecar_adoption"]["decision"], "blocked_source_ref_join_gap")
        self.assertFalse(result["sidecar_adoption"]["safe_to_enable_by_default"])

    def test_stale_or_unjoined_index_pairs_are_filtered_from_eval(self) -> None:
        self.write_rows([self.question_row("1"), self.question_row("2")])
        sidecar.evaluate_question_index_sidecar(
            jobs_path=self.jobs_path,
            index_path=self.index_path,
        )
        with closing(sqlite3.connect(self.index_path)) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO question_term(term, source_id) VALUES (?, ?)",
                ("context", "ghost-question"),
            )
            conn.execute(
                "INSERT OR IGNORE INTO question_term(term, source_id) VALUES (?, ?)",
                ("context", "q_deadbeef"),
            )
            conn.commit()

        pairs = sidecar.candidate_pairs_from_index(self.index_path, max_pairs=20)
        result = sidecar.evaluate_question_index_sidecar(
            jobs_path=self.jobs_path,
            index_path=self.index_path,
        )

        self.assertTrue(any("ghost-question" in pair[:2] for pair in pairs))
        self.assertEqual(result["sidecar_pair_count"], result["source_joined_pair_count"])
        self.assertTrue(result["source_ref_join_survived"])

    def test_coverage_gap_blocks_prefilter_recommendation(self) -> None:
        self.write_rows(
            [
                self.question_row("1"),
                self.question_row(
                    "2",
                    question_text="Why does Codex forget context after compaction?",
                    question_short="Codex context loss after compaction",
                ),
            ]
        )

        result = sidecar.evaluate_question_index_sidecar(
            jobs_path=self.jobs_path,
            index_path=self.index_path,
            max_pairs=0,
        )

        self.assertEqual(result["baseline_strong_pair_count"], 1)
        self.assertEqual(result["baseline_strong_pair_coverage"], 0.0)
        self.assertEqual(
            result["recommendation"],
            "do_not_enable_index_prefilter_until_coverage_gap_is_understood",
        )
        self.assertEqual(result["sidecar_adoption"]["decision"], "blocked_candidate_coverage_gap")
        self.assertFalse(result["sidecar_adoption"]["default_prefilter_recommended"])

if __name__ == "__main__":
    unittest.main()
