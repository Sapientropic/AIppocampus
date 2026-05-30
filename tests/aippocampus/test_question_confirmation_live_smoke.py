from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
SMOKE = REPO_ROOT / "tools" / "aippocampus" / "smoke"
for _path in (SCRIPTS, SMOKE):
    sys.path.insert(0, str(_path))

import smoke_question_confirmation_live as smoke  # noqa: E402


class QuestionConfirmationLiveSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.jobs_path = self.root / "subconscious_jobs.jsonl"
        self.write_rows()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def source_ref(self, suffix: str) -> dict:
        return {
            "thread_key": f"session:{suffix}",
            "message_id": f"msg_{suffix}",
            "turn_id": f"turn_{suffix}",
            "source_line": int(suffix) * 10,
            "timestamp": f"2026-05-{int(suffix):02d}T00:00:00Z",
        }

    def question_row(self, suffix: str, **overrides) -> dict:
        data = {
            "schema_version": 1,
            "kind": "aippocampus_subconscious_job_finding",
            "created_at": f"2026-05-{int(suffix):02d}T00:00:00Z",
            "finding_kind": "question_candidate",
            "fingerprint": f"sf_question_{suffix}",
            "title": "Agent context continuity",
            "summary": "The user is asking how agent context survives compaction.",
            "confidence": 0.86,
            "source_refs": [self.source_ref(suffix)],
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

    def write_rows(self) -> None:
        rows = [
            self.question_row("1"),
            self.question_row(
                "2",
                question_text="Where should continuity clues appear in recall?",
                question_short="continuity clues in recall",
                what_features=["recall continuity"],
                phase_context="architecture_review",
            ),
        ]
        self.jobs_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    def test_dry_run_smoke_outputs_sanitized_aggregate_only(self) -> None:
        payload = smoke.run_question_confirmation_live_smoke(
            jobs_path=self.jobs_path,
            strong_threshold=0.99,
            borderline_threshold=0.10,
        )
        rendered = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["status"], "dry_run_no_model_call")
        self.assertEqual(payload["tracking"]["pending_confirmation_request_count"], 1)
        self.assertEqual(payload["tracking"]["wrote_count"], 0)
        self.assertFalse(payload["roundtrip"]["ran"])
        self.assertFalse(payload["privacy"]["raw_text_emitted"])
        self.assertNotIn("How do I keep", rendered)
        self.assertNotIn('"source_refs":', rendered)
        self.assertNotIn("sf_question_", rendered)

    def test_live_smoke_round_trips_fake_accept_without_formal_write(self) -> None:
        def fake_chat(messages, _config):
            rendered_messages = json.dumps(messages, ensure_ascii=False)
            self.assertNotIn('"source_refs":', rendered_messages)
            self.assertNotIn("message_id", rendered_messages)
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "decision": "accept",
                                    "confidence": 0.84,
                                    "link_type": "related",
                                    "rationale": "Both compact questions concern continuity.",
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {},
            }

        with patch.dict(os.environ, {"QUESTION_CONFIRMATION_TEST_KEY": "test-key"}):
            payload = smoke.run_question_confirmation_live_smoke(
                jobs_path=self.jobs_path,
                call_model=True,
                api_key_env="QUESTION_CONFIRMATION_TEST_KEY",
                strong_threshold=0.99,
                borderline_threshold=0.10,
                chat_fn=fake_chat,
            )
        rendered = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["status"], "live_roundtrip_completed")
        self.assertEqual(payload["live"]["artifact_count"], 1)
        self.assertEqual(payload["roundtrip"]["accepted_confirmation_count"], 1)
        self.assertEqual(payload["roundtrip"]["wrote_count"], 0)
        self.assertTrue(payload["privacy"]["temporary_artifacts_only"])
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn('"source_refs":', rendered)
        self.assertNotIn("sf_question_", rendered)


if __name__ == "__main__":
    unittest.main()
