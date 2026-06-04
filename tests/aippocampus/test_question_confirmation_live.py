from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.question import confirmation_live as live  # noqa: E402
from aippocampus_runtime.question import confirmation_live as live_owner  # noqa: E402
from aippocampus_runtime.question.confirmation import (  # noqa: E402
    load_confirmation_decisions,
    normalize_confirmation,
)


class QuestionConfirmationLiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.requests_path = self.root / "pending.jsonl"
        self.output_path = self.root / "confirmed.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def request(self) -> dict:
        return {
            "schema_version": 1,
            "kind": "question_pair_confirmation_request",
            "pair_id": "qp_fixture",
            "score": 0.72,
            "source_finding_ids": ["sf_left", "sf_right"],
            "question_ids": ["q_left", "q_right"],
            "threshold_policy": {"strong_threshold": 0.8, "borderline_threshold": 0.66},
            "left": {
                "question_id": "q_left",
                "source_finding_id": "sf_left",
                "question_text": "How should context continuity work?",
                "what_features": ["context continuity"],
            },
            "right": {
                "question_id": "q_right",
                "source_finding_id": "sf_right",
                "question_text": "Where should continuity clues appear?",
                "what_features": ["recall continuity"],
            },
            "privacy_contract": {
                "full_history_included": False,
                "raw_clean_source_text_included": False,
                "source_refs_included": False,
                "model_may_only_accept_or_reject_source_backed_pair": True,
            },
        }

    def write_requests(self, rows: list[dict] | None = None) -> None:
        rows = rows or [self.request()]
        self.requests_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    def test_default_dry_run_does_not_call_or_write(self) -> None:
        self.write_requests()

        payload = live.run_question_confirmation_live(
            requests_path=self.requests_path,
            output_path=self.output_path,
        )

        self.assertEqual(payload["status"], "dry_run_no_model_call")
        self.assertEqual(payload["request_count"], 1)
        self.assertEqual(payload["wrote_count"], 0)
        self.assertFalse(self.output_path.exists())
        self.assertIn("live_external_model_confirmation", payload["cannot_claim"])

    def test_cli_json_uses_public_confirmation_projection(self) -> None:
        private_payload = {
            "ok": True,
            "status": "live_model_confirmation_completed",
            "request_count": 1,
            "artifact_count": 1,
            "wrote_count": 0,
            "output": str(self.output_path),
            "route": {
                "provider": "deepseek",
                "base_url": "https://private-model.example/v1",
                "api_key_env": "QUESTION_CONFIRMATION_TEST_KEY",
            },
            "api_key_env": "QUESTION_CONFIRMATION_TEST_KEY",
            "usage": [{"prompt_tokens": 7, "total_tokens": 11}],
            "artifacts": [
                {
                    "decision": "accept",
                    "rationale": "private rationale with E:\\private\\notes.md",
                    "request_contract": {"source_refs_included": False},
                }
            ],
            "raw_text_emitted": False,
            "can_claim": ["live_model_confirmation_artifacts_generated"],
            "cannot_claim": ["real_user_calibration"],
        }
        stdout = io.StringIO()

        with (
            patch.object(live_owner, "run_question_confirmation_live", return_value=private_payload),
            patch.object(sys, "argv", ["question_confirmation_live.py", "--json"]),
            contextlib.redirect_stdout(stdout),
        ):
            code = live.main()

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["artifact_count"], 1)
        self.assertEqual(payload["model_route"], {"provider": "deepseek"})
        self.assertNotIn("artifacts", payload)
        self.assertNotIn("output", payload)
        self.assertNotIn("api_key_env", encoded)
        self.assertNotIn("private-model.example", encoded)
        self.assertNotIn("private rationale", encoded)
        self.assertNotIn("E:\\private", encoded)

    def test_missing_api_key_skips_live_call(self) -> None:
        self.write_requests()

        with patch.dict(os.environ, {}, clear=True):
            payload = live.run_question_confirmation_live(
                requests_path=self.requests_path,
                output_path=self.output_path,
                call_model=True,
                api_key_env="QUESTION_CONFIRMATION_TEST_KEY",
            )

        self.assertEqual(payload["status"], "skipped_missing_api_key")
        self.assertEqual(payload["wrote_count"], 0)
        self.assertFalse(self.output_path.exists())

    def test_live_accept_artifact_round_trips_to_tracking_confirmation_contract(self) -> None:
        self.write_requests()

        def fake_chat(messages, config):
            rendered_messages = json.dumps(messages, ensure_ascii=False)
            self.assertNotIn('"source_refs":', rendered_messages)
            self.assertNotIn("message_id", rendered_messages)
            self.assertEqual(config.cache_contract, "deepseek_prefix_v1")
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "decision": "accept",
                                    "confidence": 0.82,
                                    "link_type": "related",
                                    "rationale": "Both extracted questions concern context continuity.",
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {},
            }

        with patch.dict(os.environ, {"QUESTION_CONFIRMATION_TEST_KEY": "test-key"}):
            payload = live.run_question_confirmation_live(
                requests_path=self.requests_path,
                output_path=self.output_path,
                call_model=True,
                api_key_env="QUESTION_CONFIRMATION_TEST_KEY",
                chat_fn=fake_chat,
            )

        self.assertEqual(payload["status"], "live_model_confirmation_completed")
        self.assertEqual(payload["wrote_count"], 1)
        confirm = load_confirmation_decisions(self.output_path)
        self.assertIsNotNone(confirm)
        raw = confirm(self.request()) if confirm else None
        normalized = normalize_confirmation(raw, payload=self.request())
        self.assertEqual(normalized["decision"], "accept")
        self.assertEqual(normalized["model"], "deepseek-v4-flash")
        self.assertEqual(
            normalized["artifact_audit"]["artifact_kind"],
            "question_pair_confirmation_artifact",
        )
        self.assertEqual(normalized["artifact_audit"]["pair_id"], "qp_fixture")
        self.assertEqual(
            normalized["artifact_audit"]["source_finding_ids"],
            ["sf_left", "sf_right"],
        )
        self.assertNotIn("source_refs", normalized["artifact_audit"])

    def test_live_reject_artifact_is_valid_confirmation(self) -> None:
        self.write_requests()

        def fake_chat(_messages, _config):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "decision": "reject",
                                    "confidence": 0.9,
                                    "link_type": "related",
                                    "rationale": "One question is about persistence, the other about placement.",
                                }
                            )
                        }
                    }
                ],
            }

        with patch.dict(os.environ, {"QUESTION_CONFIRMATION_TEST_KEY": "test-key"}):
            payload = live.run_question_confirmation_live(
                requests_path=self.requests_path,
                output_path=self.output_path,
                call_model=True,
                api_key_env="QUESTION_CONFIRMATION_TEST_KEY",
                no_write=True,
                chat_fn=fake_chat,
            )

        artifact = payload["artifacts"][0]
        normalized = normalize_confirmation(artifact, payload=self.request())
        self.assertEqual(artifact["decision"], "reject")
        self.assertEqual(normalized["decision"], "reject")

    def test_malformed_model_response_writes_invalid_artifact_shape(self) -> None:
        self.write_requests()

        def fake_chat(_messages, _config):
            return {"choices": [{"message": {"content": "not json"}}]}

        with patch.dict(os.environ, {"QUESTION_CONFIRMATION_TEST_KEY": "test-key"}):
            payload = live.run_question_confirmation_live(
                requests_path=self.requests_path,
                output_path=self.output_path,
                call_model=True,
                api_key_env="QUESTION_CONFIRMATION_TEST_KEY",
                no_write=True,
                chat_fn=fake_chat,
            )

        artifact = payload["artifacts"][0]
        self.assertEqual(artifact["decision"], "invalid")
        self.assertEqual(artifact["invalid_reason"], "non_json_model_response")
        normalized = normalize_confirmation(artifact, payload=self.request())
        self.assertEqual(normalized["decision"], "invalid")


if __name__ == "__main__":
    unittest.main()
