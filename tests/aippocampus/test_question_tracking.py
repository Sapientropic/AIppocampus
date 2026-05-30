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

import question_tracking as tracking  # noqa: E402


class QuestionTrackingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.jobs_path = self.root / "subconscious_jobs.jsonl"

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

    def write_registry(self, thread_keys: list[str]) -> Path:
        registry_path = self.root / "threads.json"
        threads = []
        for thread_key in thread_keys:
            suffix = thread_key.split(":")[-1]
            clean_dir = self.root / f"clean-{suffix}"
            clean_dir.mkdir()
            messages_path = clean_dir / "messages.jsonl"
            messages_path.write_text(
                json.dumps(
                    {
                        "message_id": f"msg_{suffix}",
                        "turn_id": f"turn_{suffix}",
                        "turn_index": int(suffix),
                        "source_line": int(suffix) * 10,
                        "role": "user",
                        "text": f"Question source {suffix}",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            threads.append(
                {
                    "thread_key": thread_key,
                    "paths": {"clean_source_messages_jsonl": str(messages_path)},
                }
            )
        registry_path.write_text(json.dumps({"threads": threads}, ensure_ascii=False), encoding="utf-8")
        return registry_path

    def test_groups_source_backed_question_candidates_with_dependencies(self) -> None:
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

        result = tracking.run_question_tracking(jobs_path=self.jobs_path, no_write=True)

        self.assertEqual(result["candidate_count"], 3)
        self.assertEqual(result["link_count"], 1)
        link = result["links"][0]
        self.assertEqual(link["finding_kind"], "question_link")
        self.assertEqual(link["question_count"], 2)
        self.assertEqual(link["source_thread_count"], 2)
        self.assertEqual(len(link["dependency_edges"]), 1)
        self.assertEqual(link["dependency_edges"][0]["relation"], "ordered_after")
        self.assertEqual(
            link["dependency_edges"][0]["evidence_type"],
            "heuristic_temporal_specificity_order",
        )
        self.assertEqual(
            link["match_evidence"]["method"], "deterministic_multifield_hash_vector_v1"
        )
        linked_text = " ".join(item["question_text"] for item in link["linked_questions"])
        self.assertIn("compaction", linked_text)
        self.assertNotIn("dashboard", linked_text.casefold())

    def test_borderline_links_require_explicit_confirmation(self) -> None:
        self.write_rows(
            [
                self.question_row("1"),
                self.question_row(
                    "2",
                    question_text="Where should continuity clues appear in recall?",
                    question_short="continuity clues in recall",
                    what_features=["recall continuity"],
                    phase_context="architecture_review",
                ),
            ]
        )

        skipped = tracking.run_question_tracking(
            jobs_path=self.jobs_path,
            no_write=True,
            strong_threshold=0.99,
            borderline_threshold=0.10,
        )
        self.assertEqual(skipped["link_count"], 0)
        self.assertEqual(skipped["borderline_skipped_pair_count"], 1)

        def confirm(payload: dict[str, Any]) -> dict[str, Any]:
            self.assertEqual(len(payload["source_finding_ids"]), 2)
            return {
                "decision": "accept",
                "link_type": "evolving",
                "confidence": 0.81,
                "model": "test-reviewer",
                "rationale": "Both questions are about recall continuity placement.",
            }

        accepted = tracking.run_question_tracking(
            jobs_path=self.jobs_path,
            no_write=True,
            strong_threshold=0.99,
            borderline_threshold=0.10,
            confirmation_fn=confirm,
        )

        self.assertEqual(accepted["link_count"], 1)
        link = accepted["links"][0]
        self.assertEqual(link["link_type"], "evolving")
        self.assertEqual(link["match_evidence"]["borderline_confirmed_pair_count"], 1)
        self.assertEqual(
            link["match_evidence"]["accepted_pairs"][0]["confirmation"]["model"],
            "test-reviewer",
        )
        self.assertGreaterEqual(len(link["source_refs"]), 2)

    def test_malformed_borderline_confirmations_are_ignored(self) -> None:
        self.write_rows(
            [
                self.question_row("1"),
                self.question_row(
                    "2",
                    question_text="Where should continuity clues appear in recall?",
                    question_short="continuity clues in recall",
                    what_features=["recall continuity"],
                    phase_context="architecture_review",
                ),
            ]
        )

        def malformed(_payload: dict[str, Any]) -> dict[str, Any]:
            return {"decision": "accept", "confidence": "not-a-number"}

        result = tracking.run_question_tracking(
            jobs_path=self.jobs_path,
            no_write=True,
            strong_threshold=0.99,
            borderline_threshold=0.10,
            confirmation_fn=malformed,
        )

        self.assertEqual(result["link_count"], 0)
        self.assertEqual(result["borderline_skipped_pair_count"], 1)

    def test_skips_stale_candidates_without_source_refs(self) -> None:
        self.write_rows(
            [
                self.question_row("1"),
                self.question_row(
                    "2",
                    fingerprint="sf_stale",
                    source_refs=[{"thread_key": "session:stale"}],
                    question_text="How do I keep agent context across compaction?",
                ),
            ]
        )

        result = tracking.run_question_tracking(jobs_path=self.jobs_path, no_write=True)

        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["stale_candidate_count"], 1)
        self.assertEqual(result["link_count"], 0)

    def test_registry_source_ref_resolution_skips_well_shaped_stale_refs(self) -> None:
        registry_path = self.write_registry(["session:1", "session:2"])
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
                    fingerprint="sf_stale_well_shaped",
                    source_refs=[
                        {
                            "thread_key": "session:missing",
                            "message_id": "msg_missing",
                            "source_line": 30,
                        }
                    ],
                    question_text="How do I keep agent context across compaction?",
                ),
            ]
        )

        result = tracking.run_question_tracking(
            jobs_path=self.jobs_path,
            registry_path=registry_path,
            no_write=True,
        )

        self.assertEqual(result["source_ref_resolution"], "registry_clean_source")
        self.assertEqual(result["source_ref_index_message_count"], 2)
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["stale_candidate_count"], 1)
        self.assertEqual(result["link_count"], 1)

    def test_appends_question_links_without_duplicate_rerun(self) -> None:
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

        first = tracking.run_question_tracking(jobs_path=self.jobs_path)
        second = tracking.run_question_tracking(jobs_path=self.jobs_path)
        rows = list(tracking.iter_jsonl(self.jobs_path))
        link_rows = [row for row in rows if row.get("finding_kind") == "question_link"]

        self.assertEqual(first["wrote_count"], 1)
        self.assertEqual(second["wrote_count"], 0)
        self.assertEqual(second["duplicate_link_count"], 1)
        self.assertEqual(len(link_rows), 1)
        self.assertEqual(link_rows[0]["source"], "deterministic_question_tracking")


if __name__ == "__main__":
    unittest.main()
