from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import smoke_semantic_scope_source_review as review  # noqa: E402


class SemanticScopeSourceReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry = self.root / "registry" / "threads.json"
        self.registry.parent.mkdir()
        self.old_key = os.environ.get("FAKE_DEEPSEEK_KEY")

    def tearDown(self) -> None:
        if self.old_key is None:
            os.environ.pop("FAKE_DEEPSEEK_KEY", None)
        else:
            os.environ["FAKE_DEEPSEEK_KEY"] = self.old_key
        self.tmp.cleanup()

    def _write_fixture(self) -> None:
        clean = self.root / "thread-life" / "clean-source"
        clean.mkdir(parents=True)
        (clean / "messages.jsonl").write_text(
            json.dumps(
                {
                    "message_id": "msg_life",
                    "turn_id": "turn_life",
                    "source_line": 7,
                    "role": "user",
                    "text": "The lighthouse metaphor felt like a pivot for long-term continuity.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (clean / "semantic-scope-labels.jsonl").write_text(
            json.dumps(
                {
                    "message_id": "msg_life",
                    "turn_id": "turn_life",
                    "scope_labels": ["personal_reflection", "idea_seed"],
                    "confidence": 0.9,
                    "label_evidence": [
                        {
                            "label": "personal_reflection",
                            "reason": "The source treats the metaphor as personally meaningful.",
                            "confidence": 0.88,
                        },
                        {
                            "label": "idea_seed",
                            "reason": "The source frames the metaphor as a continuity pivot.",
                            "confidence": 0.86,
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
                            "paths": {
                                "clean_source_messages_jsonl": str(clean / "messages.jsonl"),
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_live_source_review_passes_without_leaking_clean_text(self) -> None:
        self._write_fixture()
        os.environ["FAKE_DEEPSEEK_KEY"] = "present"

        def fake_chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):  # noqa: ANN001
            payload = json.loads(messages[1]["content"])
            self.assertLess(
                messages[1]["content"].index("label_guidance_catalog"),
                messages[1]["content"].index("review_case"),
            )
            self.assertEqual(
                payload["review_case"]["label_evidence"]["personal_reflection"]["confidence"], 0.88
            )
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "supported_labels": payload["review_case"]["labels"],
                                    "unsupported_labels": [],
                                    "confidence": 0.91,
                                    "needs_human_review": False,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {
                    "prompt_cache_hit_tokens": 8,
                    "prompt_cache_miss_tokens": 2,
                },
            }

        result = review.run_semantic_scope_source_review(
            registry_path=self.registry,
            live=True,
            api_key_env="FAKE_DEEPSEEK_KEY",
            max_cases=1,
            min_cases=1,
            min_pass_rate=1.0,
            chat_fn=fake_chat_fn,
        )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["ok"], rendered)
        self.assertEqual(result["status"], "sufficient")
        self.assertEqual(result["claim_level"], "selected_semantic_label_source_review")
        self.assertEqual(result["case_count"], 1)
        self.assertEqual(result["passed_count"], 1)
        self.assertEqual(result["cache"]["hit_rate"], 0.8)
        self.assertIn("personal_reflection", result["label_coverage"])
        self.assertNotIn("lighthouse", rendered)
        self.assertNotIn("Private Life Title", rendered)
        self.assertNotIn("msg_life", rendered)
        self.assertNotIn(str(self.root), rendered)

    def test_live_source_review_reports_per_label_failure_categories(self) -> None:
        self._write_fixture()
        os.environ["FAKE_DEEPSEEK_KEY"] = "present"

        def fake_chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):  # noqa: ANN001
            payload = json.loads(messages[1]["content"])
            labels = payload["review_case"]["labels"]
            supported = [label for label in labels if label == "idea_seed"]
            unsupported = [label for label in labels if label != "idea_seed"]
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "supported_labels": supported,
                                    "unsupported_labels": unsupported,
                                    "confidence": 0.91,
                                    "needs_human_review": False,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

        result = review.run_semantic_scope_source_review(
            registry_path=self.registry,
            live=True,
            api_key_env="FAKE_DEEPSEEK_KEY",
            max_cases=2,
            min_cases=2,
            min_pass_rate=0.0,
            min_label_pass_rate=0.75,
            chat_fn=fake_chat_fn,
        )

        self.assertEqual(result["case_count"], 2)
        self.assertEqual(result["per_label"]["idea_seed"]["pass_rate"], 1.0)
        self.assertEqual(result["per_label"]["personal_reflection"]["pass_rate"], 0.0)
        self.assertIn("personal_reflection", result["failed_label_categories"])

    def test_live_missing_api_key_fails_instead_of_observe_fallback(self) -> None:
        self._write_fixture()
        os.environ.pop("FAKE_DEEPSEEK_KEY", None)

        result = review.run_semantic_scope_source_review(
            registry_path=self.registry,
            live=True,
            api_key_env="FAKE_DEEPSEEK_KEY",
            max_cases=1,
            min_cases=1,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "live_model_missing_api_key")
        self.assertIn("selected_source_review_passed", result["cannot_claim"])

    def test_live_source_review_retries_transient_model_errors(self) -> None:
        self._write_fixture()
        os.environ["FAKE_DEEPSEEK_KEY"] = "present"
        calls = 0

        def flaky_chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):  # noqa: ANN001
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("temporary reviewer timeout")
            payload = json.loads(messages[1]["content"])
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "supported_labels": payload["review_case"]["labels"],
                                    "unsupported_labels": [],
                                    "confidence": 0.91,
                                    "needs_human_review": False,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

        result = review.run_semantic_scope_source_review(
            registry_path=self.registry,
            live=True,
            api_key_env="FAKE_DEEPSEEK_KEY",
            max_cases=1,
            min_cases=1,
            min_pass_rate=1.0,
            max_attempts=2,
            chat_fn=flaky_chat_fn,
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(calls, 2)
        self.assertEqual(result["failure_count"], 0)

    def test_live_source_review_fails_when_label_evidence_is_unsupported(self) -> None:
        self._write_fixture()
        os.environ["FAKE_DEEPSEEK_KEY"] = "present"

        def fake_chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):  # noqa: ANN001
            payload = json.loads(messages[1]["content"])
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "supported_labels": payload["review_case"]["labels"],
                                    "unsupported_labels": [],
                                    "unsupported_evidence_labels": payload["review_case"]["labels"],
                                    "confidence": 0.91,
                                    "needs_human_review": False,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

        result = review.run_semantic_scope_source_review(
            registry_path=self.registry,
            live=True,
            api_key_env="FAKE_DEEPSEEK_KEY",
            max_cases=1,
            min_cases=1,
            min_pass_rate=1.0,
            chat_fn=fake_chat_fn,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["passed_count"], 0)
        self.assertEqual(result["cases"][0]["unsupported_label_count"], 1)

    def test_agentic_source_review_uses_pro_route_and_tool_observation(self) -> None:
        self._write_fixture()
        os.environ["FAKE_DEEPSEEK_KEY"] = "present"
        calls: list[dict[str, object]] = []

        def fake_chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):  # noqa: ANN001
            calls.append({"model": model, "messages": messages})
            if len(calls) == 1:
                payload = json.loads(messages[1]["content"])
                self.assertEqual(payload["review_mode"], "agentic_source_review")
                self.assertNotIn("lighthouse", messages[1]["content"])
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"action": "tool", "tool": "inspect_review_case", "args": {}},
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                }
            self.assertIn("TOOL_RESULT", messages[-1]["content"])
            self.assertIn("lighthouse", messages[-1]["content"])
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "action": "final",
                                    "review": {
                                        "supported_labels": ["personal_reflection"],
                                        "unsupported_labels": [],
                                        "unsupported_evidence_labels": [],
                                        "confidence": 0.95,
                                        "needs_human_review": False,
                                    },
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"prompt_cache_hit_tokens": 4, "prompt_cache_miss_tokens": 1},
            }

        result = review.run_semantic_scope_source_review(
            registry_path=self.registry,
            live=True,
            api_key_env="FAKE_DEEPSEEK_KEY",
            max_cases=1,
            min_cases=1,
            min_pass_rate=1.0,
            agentic_review=True,
            chat_fn=fake_chat_fn,
        )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["ok"], rendered)
        self.assertEqual(result["model_route"]["route"], "agentic_source_review")
        self.assertEqual(result["model_route"]["model"], "deepseek-v4-pro")
        self.assertEqual({call["model"] for call in calls}, {"deepseek-v4-pro"})
        self.assertEqual(result["cases"][0]["review_mode"], "agentic")
        self.assertGreaterEqual(result["cases"][0]["tool_step_count"], 1)
        self.assertNotIn("lighthouse", rendered)
        self.assertNotIn("msg_life", rendered)


if __name__ == "__main__":
    unittest.main()
