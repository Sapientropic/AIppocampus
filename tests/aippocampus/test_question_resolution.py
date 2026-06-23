from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.source.io_kernel import write_jsonl_dict_rows
from aippocampus_runtime.subconscious import question_resolution as qr


class QuestionResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def source_ref(self, *, message_id: str, turn_index: int, line: int, timestamp: str) -> dict:
        return {
            "thread_key": "session:context",
            "message_id": message_id,
            "turn_id": f"turn_{turn_index}",
            "turn_index": turn_index,
            "source_line": line,
            "timestamp": timestamp,
        }

    def question_candidate(self) -> dict:
        return {
            "schema_version": 1,
            "kind": "aippocampus_subconscious_job_finding",
            "created_at": "2026-02-10T00:00:00Z",
            "finding_kind": "question_candidate",
            "fingerprint": "sf_context_question",
            "title": "Agent context continuity",
            "summary": "The user asks how agent context survives compaction.",
            "confidence": 0.86,
            "source_refs": [
                self.source_ref(
                    message_id="msg_question",
                    turn_index=1,
                    line=10,
                    timestamp="2026-02-10T00:00:00Z",
                )
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

    def registry_for_messages(self, messages: list[dict]) -> Path:
        clean_dir = self.root / "clean"
        clean_dir.mkdir()
        messages_path = clean_dir / "messages.jsonl"
        write_jsonl_dict_rows(messages_path, messages)
        registry_path = self.root / "threads.json"
        registry_path.write_text(
            json.dumps(
                {
                    "threads": [
                        {
                            "thread_key": "session:context",
                            "title": "Context thread",
                            "project_label": "AIppocampus",
                            "paths": {"clean_source_messages_jsonl": str(messages_path)},
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return registry_path

    def test_extracts_explicit_user_followup_resolution_without_raw_text(self) -> None:
        jobs_path = self.root / "jobs.jsonl"
        write_jsonl_dict_rows(jobs_path, [self.question_candidate()])
        registry_path = self.registry_for_messages(
            [
                {
                    "message_id": "msg_question",
                    "turn_id": "turn_1",
                    "turn_index": 1,
                    "source_line": 10,
                    "timestamp": "2026-02-10T00:00:00Z",
                    "role": "user",
                    "text": "How do I keep agent context across compaction?",
                },
                {
                    "message_id": "msg_resolution",
                    "turn_id": "turn_2",
                    "turn_index": 2,
                    "source_line": 20,
                    "timestamp": "2026-02-12T00:00:00Z",
                    "role": "user",
                    "text": "这个 compaction 问题解决了，已经明白了。",
                },
            ]
        )

        payload = qr.run_question_resolution(
            jobs_path=jobs_path,
            registry_path=registry_path,
            no_write=True,
        )

        self.assertEqual(payload["candidate_signal_count"], 1)
        self.assertEqual(payload["fresh_signal_count"], 1)
        signal = payload["signals"][0]
        self.assertEqual(signal["finding_kind"], "question_resolution_signal")
        self.assertEqual(signal["resolved_source_finding_ids"], ["sf_context_question"])
        self.assertEqual(signal["resolution_kind"], "explicit_user_resolution")
        self.assertEqual(signal["match_evidence"]["raw_text_emitted"], False)
        self.assertNotIn("问题解决了", json.dumps(signal, ensure_ascii=False))

    def test_ignores_negative_assistant_and_unrelated_resolution_mentions(self) -> None:
        jobs_path = self.root / "jobs.jsonl"
        write_jsonl_dict_rows(jobs_path, [self.question_candidate()])
        registry_path = self.registry_for_messages(
            [
                {
                    "message_id": "msg_question",
                    "turn_id": "turn_1",
                    "turn_index": 1,
                    "source_line": 10,
                    "timestamp": "2026-02-10T00:00:00Z",
                    "role": "user",
                    "text": "How do I keep agent context across compaction?",
                },
                {
                    "message_id": "msg_negative",
                    "turn_id": "turn_2",
                    "turn_index": 2,
                    "source_line": 20,
                    "timestamp": "2026-02-12T00:00:00Z",
                    "role": "user",
                    "text": "compaction 还没解决。",
                },
                {
                    "message_id": "msg_assistant",
                    "turn_id": "turn_3",
                    "turn_index": 3,
                    "source_line": 30,
                    "timestamp": "2026-02-13T00:00:00Z",
                    "role": "assistant",
                    "text": "The compaction problem is solved.",
                },
                {
                    "message_id": "msg_unrelated",
                    "turn_id": "turn_4",
                    "turn_index": 4,
                    "source_line": 40,
                    "timestamp": "2026-02-14T00:00:00Z",
                    "role": "user",
                    "text": "The billing issue is solved.",
                },
            ]
        )

        payload = qr.run_question_resolution(
            jobs_path=jobs_path,
            registry_path=registry_path,
            no_write=True,
        )

        self.assertEqual(payload["candidate_signal_count"], 0)
        self.assertEqual(payload["fresh_signal_count"], 0)

    def test_appends_and_deduplicates_resolution_signal_rows(self) -> None:
        jobs_path = self.root / "jobs.jsonl"
        write_jsonl_dict_rows(jobs_path, [self.question_candidate()])
        registry_path = self.registry_for_messages(
            [
                {
                    "message_id": "msg_question",
                    "turn_id": "turn_1",
                    "turn_index": 1,
                    "source_line": 10,
                    "timestamp": "2026-02-10T00:00:00Z",
                    "role": "user",
                    "text": "How do I keep agent context across compaction?",
                },
                {
                    "message_id": "msg_resolution",
                    "turn_id": "turn_2",
                    "turn_index": 2,
                    "source_line": 20,
                    "timestamp": "2026-02-12T00:00:00Z",
                    "role": "user",
                    "text": "The compaction question is solved.",
                },
            ]
        )

        first = qr.run_question_resolution(jobs_path=jobs_path, registry_path=registry_path)
        second = qr.run_question_resolution(jobs_path=jobs_path, registry_path=registry_path)

        rows = qr.load_tracking_rows(jobs_path)
        signal_rows = [row for row in rows if row.get("finding_kind") == "question_resolution_signal"]
        self.assertEqual(first["wrote_count"], 1)
        self.assertEqual(second["wrote_count"], 0)
        self.assertEqual(len(signal_rows), 1)
        self.assertEqual(signal_rows[0]["source"], "deterministic_question_resolution")

if __name__ == "__main__":
    unittest.main()
