from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
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

import question_health as qh  # noqa: E402
from question_source_refs import build_source_ref_index  # noqa: E402


class QuestionHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def source_ref(self, suffix: str, *, timestamp: str) -> dict:
        return {
            "thread_key": f"session:{suffix}",
            "title": "Question thread",
            "project_label": "AIppocampus",
            "message_id": f"msg_{suffix}",
            "turn_id": f"turn_{suffix}",
            "source_line": int(suffix) * 10,
            "timestamp": timestamp,
        }

    def question_candidate(self, suffix: str, *, timestamp: str, **overrides) -> dict:
        data = {
            "schema_version": 1,
            "kind": "aippocampus_subconscious_job_finding",
            "created_at": timestamp,
            "finding_kind": "question_candidate",
            "fingerprint": f"sf_question_{suffix}",
            "title": "Agent context continuity",
            "summary": "The user is asking how agent context survives compaction.",
            "confidence": 0.86,
            "source_refs": [self.source_ref(suffix, timestamp=timestamp)],
            "question_text": "How do I keep agent context across compaction?",
            "question_short": f"context continuity {suffix}",
            "intent_orientation": "implementation",
            "what_features": ["agent memory", "context continuity", "compaction"],
            "where_context": ["AIppocampus"],
            "phase_context": "post_compaction",
            "collaboration_context": ["Codex"],
            "concepts": ["AIppocampus", "context continuity"],
        }
        data.update(overrides)
        return data

    def question_link(self, *, resolved: bool = False) -> dict:
        refs = [
            self.source_ref("1", timestamp="2026-01-01T00:00:00Z"),
            self.source_ref("2", timestamp="2026-02-10T00:00:00Z"),
        ]
        row = {
            "schema_version": 1,
            "kind": "aippocampus_subconscious_job_finding",
            "created_at": "2026-02-10T00:00:00Z",
            "finding_kind": "question_link",
            "fingerprint": "sf_link_context",
            "question_cluster_id": "ql_context",
            "linked_question_short": "agent context continuity",
            "question_count": 2,
            "link_type": "recurring",
            "first_seen": "2026-01-01T00:00:00Z",
            "last_seen": "2026-02-10T00:00:00Z",
            "source_refs": refs,
            "concepts": ["context continuity", "compaction"],
            "question_source_finding_ids": ["sf_question_1", "sf_question_2"],
            "linked_questions": [
                {
                    "question_id": "q_1",
                    "source_finding_id": "sf_question_1",
                    "question_short": "context continuity 1",
                    "phase_context": "post_compaction",
                },
                {
                    "question_id": "q_2",
                    "source_finding_id": "sf_question_2",
                    "question_short": "context continuity 2",
                    "phase_context": "post_compaction",
                },
            ],
        }
        if resolved:
            row["resolution_signal"] = {
                "kind": "user_said_resolved",
                "resolved_at": "2026-02-12T00:00:00Z",
                "source_refs": [self.source_ref("4", timestamp="2026-02-12T00:00:00Z")],
            }
        return row

    def frontier_marker(self) -> dict:
        return {
            "schema_version": 1,
            "kind": "aippocampus_subconscious_job_finding",
            "created_at": "2026-02-01T00:00:00Z",
            "finding_kind": "frontier_marker",
            "fingerprint": "sf_frontier",
            "frontier_type": "blocked",
            "linked_question_short": "agent context continuity",
            "boundary_reason": "Needs external evidence before claiming continuity works.",
            "source_refs": [self.source_ref("3", timestamp="2026-02-01T00:00:00Z")],
        }

    def question_resolution_signal(
        self,
        *,
        source_ref_suffix: str = "4",
        resolved_subject_id: str = "ql_context",
    ) -> dict:
        return {
            "schema_version": 1,
            "kind": "aippocampus_subconscious_job_finding",
            "created_at": "2026-02-12T00:00:00Z",
            "finding_kind": "question_resolution_signal",
            "fingerprint": "qr_context",
            "resolution_kind": "explicit_user_resolution",
            "resolved_subject_id": resolved_subject_id,
            "resolved_question_ids": ["q_1", "q_2"],
            "resolved_source_finding_ids": ["sf_question_1", "sf_question_2"],
            "resolved_at": "2026-02-12T00:00:00Z",
            "source_refs": [self.source_ref(source_ref_suffix, timestamp="2026-02-12T00:00:00Z")],
            "resolution_source_refs": [
                self.source_ref(source_ref_suffix, timestamp="2026-02-12T00:00:00Z")
            ],
        }

    def registry_for(self, suffixes: list[str]) -> Path:
        registry_path = self.root / "threads.json"
        threads = []
        for suffix in suffixes:
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
                    "thread_key": f"session:{suffix}",
                    "paths": {"clean_source_messages_jsonl": str(messages_path)},
                }
            )
        registry_path.write_text(json.dumps({"threads": threads}, ensure_ascii=False), encoding="utf-8")
        return registry_path

    def test_reports_dormant_resolved_and_frontier_stats_from_source_rows(self) -> None:
        rows = [
            self.question_link(resolved=True),
            self.question_candidate("3", timestamp="2026-01-01T00:00:00Z"),
            self.frontier_marker(),
        ]
        now = datetime(2026, 2, 15, tzinfo=timezone.utc)

        payload = qh.build_question_health_stats(rows, now=now, dormant_after_days=30)

        self.assertTrue(payload["available"])
        self.assertEqual(payload["tracked_question_count"], 3)
        self.assertEqual(payload["question_group_count"], 2)
        self.assertEqual(payload["recurring_link_count"], 1)
        self.assertEqual(payload["resolved_question_count"], 1)
        self.assertEqual(payload["dormant_question_count"], 1)
        self.assertEqual(payload["frontier_marker_counts"], {"blocked": 1})
        self.assertEqual(payload["phase_context_counts"], {"post_compaction": 3})
        self.assertTrue(payload["heuristic_contract"]["no_stalled_state"])
        self.assertIn("heuristics", payload["heuristic_contract"]["truth_boundary"])

    def test_resolved_requires_independent_resolution_source_refs(self) -> None:
        row = self.question_link(resolved=False)
        row["lifecycle_state"] = "resolved"
        row["resolution_source_refs"] = [self.source_ref("2", timestamp="2026-02-12T00:00:00Z")]
        rows = [row]
        now = datetime(2026, 2, 15, tzinfo=timezone.utc)

        payload = qh.build_question_health_stats(rows, now=now, dormant_after_days=30)

        self.assertEqual(payload["resolved_question_count"], 0)
        self.assertEqual(payload["open_question_count"], 1)

    def test_resolved_requires_signal_after_last_seen(self) -> None:
        row = self.question_link(resolved=False)
        row["lifecycle_state"] = "resolved"
        row["resolved_at"] = "2026-02-01T00:00:00Z"
        row["resolution_source_refs"] = [self.source_ref("4", timestamp="2026-02-01T00:00:00Z")]

        payload = qh.build_question_health_stats(
            [row],
            now=datetime(2026, 2, 15, tzinfo=timezone.utc),
            dormant_after_days=30,
        )

        self.assertEqual(payload["resolved_question_count"], 0)
        self.assertEqual(payload["open_question_count"], 1)

    def test_external_resolution_signal_cannot_reuse_subject_source_refs(self) -> None:
        rows = [
            self.question_link(resolved=False),
            self.question_resolution_signal(source_ref_suffix="2"),
        ]

        payload = qh.build_question_health_stats(
            rows,
            now=datetime(2026, 2, 15, tzinfo=timezone.utc),
            dormant_after_days=30,
        )

        self.assertEqual(payload["resolved_question_count"], 0)
        self.assertEqual(payload["open_question_count"], 1)

    def test_external_resolution_signal_marks_matching_question_resolved(self) -> None:
        rows = [self.question_link(resolved=False), self.question_resolution_signal()]

        payload = qh.build_question_health_stats(
            rows,
            now=datetime(2026, 2, 15, tzinfo=timezone.utc),
            dormant_after_days=30,
        )

        self.assertEqual(payload["resolved_question_count"], 1)
        self.assertEqual(payload["open_question_count"], 0)
        self.assertEqual(payload["resolution_signal_count"], 1)
        self.assertEqual(payload["external_resolution_signal_count"], 1)
        self.assertEqual(
            payload["lifecycle"][0]["resolution_signal"]["kind"],
            "explicit_user_resolution",
        )

    def test_stale_external_resolution_signal_is_ignored_with_registry_resolution(self) -> None:
        registry_path = self.registry_for(["1", "2"])
        source_index = build_source_ref_index(registry_path)
        self.assertIsNotNone(source_index)
        rows = [self.question_link(resolved=False), self.question_resolution_signal()]

        payload = qh.build_question_health_stats(
            rows,
            source_index=source_index,
            now=datetime(2026, 2, 15, tzinfo=timezone.utc),
            dormant_after_days=30,
        )

        self.assertTrue(payload["available"])
        self.assertEqual(payload["resolved_question_count"], 0)
        self.assertEqual(payload["open_question_count"], 1)
        self.assertEqual(payload["external_resolution_signal_count"], 0)
        self.assertEqual(payload["stale_or_unresolved_ref_row_count"], 1)

    def test_public_aggregate_omits_source_derived_lifecycle_titles(self) -> None:
        payload = qh.build_question_health_stats(
            [self.question_link(resolved=True)],
            now=datetime(2026, 2, 15, tzinfo=timezone.utc),
        )

        aggregate = qh.aggregate_question_health_stats(payload)

        self.assertTrue(aggregate["available"])
        self.assertIn("resolved_question_count", aggregate)
        self.assertNotIn("lifecycle", aggregate)
        self.assertNotIn("longest_running_open_question", aggregate)

    def test_longest_running_open_question_ignores_dormant_items(self) -> None:
        rows = [
            self.question_candidate("1", timestamp="2026-01-01T00:00:00Z"),
            self.question_candidate("2", timestamp="2026-02-10T00:00:00Z"),
        ]

        payload = qh.build_question_health_stats(
            rows,
            now=datetime(2026, 2, 15, tzinfo=timezone.utc),
            dormant_after_days=30,
        )

        self.assertEqual(payload["dormant_question_count"], 1)
        self.assertEqual(payload["open_question_count"], 1)
        self.assertEqual(
            payload["longest_running_open_question"]["state"],
            "open",
        )
        self.assertIn("context continuity 2", payload["longest_running_open_question"]["title"])

    def test_skips_stale_refs_when_registry_resolution_is_available(self) -> None:
        registry_path = self.registry_for(["1", "2"])
        source_index = build_source_ref_index(registry_path)
        self.assertIsNotNone(source_index)
        rows = [
            self.question_link(),
            self.question_candidate("3", timestamp="2026-01-01T00:00:00Z"),
            self.frontier_marker(),
        ]

        payload = qh.build_question_health_stats(
            rows,
            source_index=source_index,
            now=datetime(2026, 2, 15, tzinfo=timezone.utc),
        )

        self.assertTrue(payload["available"])
        self.assertEqual(payload["source_ref_resolution"], "registry_clean_source")
        self.assertEqual(payload["question_group_count"], 1)
        self.assertEqual(payload["frontier_marker_counts"], {})
        self.assertEqual(payload["stale_or_unresolved_ref_row_count"], 2)

    def test_no_source_backed_question_rows_are_unavailable(self) -> None:
        payload = qh.build_question_health_stats(
            [{"kind": "aippocampus_subconscious_job_finding", "finding_kind": "concept_edges"}],
            now=datetime(2026, 2, 15, tzinfo=timezone.utc),
        )

        self.assertFalse(payload["available"])
        self.assertEqual(payload["reason"], "no_source_backed_question_rows")


if __name__ == "__main__":
    unittest.main()
