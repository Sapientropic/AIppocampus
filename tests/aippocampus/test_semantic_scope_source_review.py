from __future__ import annotations

import json
import os
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
        self.assertEqual(result["review_buckets"]["accepted"], 1)
        self.assertEqual(result["review_buckets"]["model_failure"], 0)
        self.assertEqual(result["review_buckets"]["unreviewed"], 0)
        self.assertGreaterEqual(
            result["per_label_floors"]["personal_reflection"]["min_pass_rate"], 0.65
        )
        self.assertNotIn("lighthouse", rendered)
        self.assertNotIn("Private Life Title", rendered)
        self.assertNotIn("msg_life", rendered)
        self.assertNotIn(str(self.root), rendered)

    def test_observe_only_reports_label_floors_without_review_claim(self) -> None:
        self._write_fixture()

        result = review.run_semantic_scope_source_review(
            registry_path=self.registry,
            live=False,
            max_cases=2,
            min_cases=1,
        )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["ok"], rendered)
        self.assertEqual(result["status"], "observe_only")
        self.assertEqual(result["review_buckets"]["accepted"], 0)
        self.assertEqual(result["review_buckets"]["model_failure"], 0)
        self.assertEqual(result["review_buckets"]["unreviewed"], 2)
        self.assertEqual(result["per_label_floors"]["personal_reflection"]["selected_case_count"], 1)
        self.assertEqual(result["per_label_floors"]["idea_seed"]["selected_case_count"], 1)
        self.assertFalse(result["per_label_floors"]["life_context"]["selection_floor_met"])
        self.assertIn("fresh_live_model_review", result["cannot_claim"])
        self.assertEqual(result["cases"], [])
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
        self.assertEqual(result["per_label"]["idea_seed"]["status"], "accepted")
        self.assertEqual(result["per_label"]["personal_reflection"]["pass_rate"], 0.0)
        self.assertEqual(result["per_label"]["personal_reflection"]["status"], "below_floor")
        self.assertIn("personal_reflection", result["failed_label_categories"])
        self.assertEqual(result["review_buckets"]["accepted"], 1)
        self.assertEqual(result["review_buckets"]["rejected"], 1)
        self.assertEqual(result["review_buckets"]["ambiguous_or_human_review"], 0)
        self.assertEqual(
            result["label_failure_taxonomy"]["by_label"]["personal_reflection"]["by_class"],
            {"unsupported_label": 1},
        )

    def test_expected_unsupported_review_does_not_require_support_confidence(self) -> None:
        case = {
            "labels": ["personal_reflection"],
            "expected_review_outcome": "unsupported",
        }
        review_payload = {
            "unsupported_labels": ["personal_reflection"],
            "needs_human_review": False,
            "confidence": 0.0,
        }
        self.assertTrue(
            review.review_passed(case, review_payload, min_review_confidence=0.65)
        )

    def test_expected_human_review_accepts_stale_or_blocked_escalation(self) -> None:
        case = {
            "labels": ["technical_work"],
            "expected_review_outcome": "needs_human_review",
        }
        review_payload = {
            "unsupported_labels": ["technical_work"],
            "needs_human_review": True,
            "confidence": 0.5,
        }
        self.assertTrue(
            review.review_passed(case, review_payload, min_review_confidence=0.65)
        )

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

    def test_live_source_review_classifies_partial_failure_without_raw_error(self) -> None:
        self._write_fixture()
        os.environ["FAKE_DEEPSEEK_KEY"] = "present"

        def failing_chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):  # noqa: ANN001
            raise TimeoutError("temporary reviewer timeout with private prompt fragment")

        result = review.run_semantic_scope_source_review(
            registry_path=self.registry,
            live=True,
            api_key_env="FAKE_DEEPSEEK_KEY",
            max_cases=1,
            min_cases=1,
            min_pass_rate=0.0,
            max_attempts=2,
            chat_fn=failing_chat_fn,
        )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "live_model_partial_failure")
        self.assertEqual(result["failure_count"], 1)
        self.assertEqual(result["failure_taxonomy"]["by_class"]["timeout"], 1)
        self.assertEqual(result["failure_taxonomy"]["by_class"]["retry_exhaustion"], 1)
        self.assertIn("retry_exhaustion", result["failure_taxonomy"]["known_classes"])
        self.assertEqual(result["failure_taxonomy"]["retry_exhausted_count"], 1)
        self.assertEqual(result["failure_taxonomy"]["failure_count"], 1)
        self.assertEqual(result["cases"][0]["failure_class"], "timeout")
        self.assertIn("selected_source_review_passed", result["cannot_claim"])
        self.assertNotIn("private prompt fragment", rendered)
        self.assertNotIn("temporary reviewer timeout", rendered)
        self.assertNotIn("lighthouse", rendered)

    def test_failure_taxonomy_classifies_non_provider_operational_buckets(self) -> None:
        cases = {
            "prompt_context_issue": RuntimeError("prompt_context payload too large"),
            "source_open_issue": RuntimeError("inspect_review_case clean source lookup failed"),
            "report_aggregation_bug": RuntimeError("review_buckets aggregation failed"),
            "provider_transport_error": RuntimeError("HTTP transport connection reset"),
            "provider_response_shape": ValueError("empty reviewer choices"),
        }
        for expected, exc in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(
                    review.classify_review_failure(exc)["failure_class"],
                    expected,
                )

    def test_live_source_review_classifies_response_shape_failure(self) -> None:
        self._write_fixture()
        os.environ["FAKE_DEEPSEEK_KEY"] = "present"

        def malformed_chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):  # noqa: ANN001
            return {"choices": []}

        result = review.run_semantic_scope_source_review(
            registry_path=self.registry,
            live=True,
            api_key_env="FAKE_DEEPSEEK_KEY",
            max_cases=1,
            min_cases=1,
            min_pass_rate=0.0,
            max_attempts=1,
            chat_fn=malformed_chat_fn,
        )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertFalse(result["ok"])
        self.assertEqual(result["failure_taxonomy"]["by_class"]["provider_response_shape"], 1)
        self.assertEqual(result["cases"][0]["failure_class"], "provider_response_shape")
        self.assertNotIn("lighthouse", rendered)
        self.assertNotIn("msg_life", rendered)

    def test_source_review_claim_level_keeps_broader_runs_diagnostic(self) -> None:
        claim_level = review.source_review_claim_level(
            public_shadow=False,
            status="sufficient",
            failures=0,
            case_count=96,
        )
        self.assertEqual(claim_level, "broader_selected_source_review_diagnostic")
        self.assertIn(
            "selected_source_review_green_gate",
            review.cannot_claim("sufficient", live=True, claim_level=claim_level),
        )

    def test_public_shadow_rejects_explicit_registry_override(self) -> None:
        self._write_fixture()
        with self.assertRaises(ValueError):
            review.run_semantic_scope_source_review(
                registry_path=self.registry,
                public_shadow=True,
                live=False,
                max_cases=1,
                min_cases=1,
            )

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
        self.assertEqual(result["cases"][0]["unsupported_evidence_label_count"], 1)
        self.assertEqual(
            result["label_failure_taxonomy"]["by_label"]["personal_reflection"]["by_class"],
            {"unsupported_label_evidence": 1},
        )

    def test_preference_label_failures_get_sanitized_taxonomy(self) -> None:
        clean = self.root / "thread-pref" / "clean-source"
        clean.mkdir(parents=True)
        (clean / "messages.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "message_id": "msg_pref_one",
                            "turn_id": "turn_pref_one",
                            "source_line": 1,
                            "role": "user",
                            "text": "I prefer short Chinese summaries before long review notes.",
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            "message_id": "msg_pref_two",
                            "turn_id": "turn_pref_two",
                            "source_line": 2,
                            "role": "user",
                            "text": "This old preference is superseded; now use concise summaries.",
                        },
                        ensure_ascii=False,
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (clean / "semantic-scope-labels.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "message_id": "msg_pref_one",
                            "turn_id": "turn_pref_one",
                            "scope_labels": ["preference"],
                            "confidence": 0.91,
                            "label_evidence": [
                                {
                                    "label": "preference",
                                    "reason": "The source states a preference.",
                                    "confidence": 0.9,
                                }
                            ],
                            "source_refs": [
                                {
                                    "message_id": "msg_pref_one",
                                    "turn_id": "turn_pref_one",
                                    "source_line": 1,
                                    "role": "user",
                                }
                            ],
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            "message_id": "msg_pref_two",
                            "turn_id": "turn_pref_two",
                            "scope_labels": ["preference"],
                            "confidence": 0.9,
                            "expected_review_outcome": "needs_human_review",
                            "public_shadow_case": "preference_stale_currentness_boundary",
                            "label_evidence": [
                                {
                                    "label": "preference",
                                    "reason": "The stale preference should be treated as current.",
                                    "confidence": 0.91,
                                }
                            ],
                            "source_refs": [
                                {
                                    "message_id": "msg_pref_two",
                                    "turn_id": "turn_pref_two",
                                    "source_line": 2,
                                    "role": "user",
                                }
                            ],
                        },
                        ensure_ascii=False,
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self.registry.write_text(
            json.dumps(
                {
                    "threads": [
                        {
                            "thread_key": "session:pref",
                            "title": "Private Preference Title",
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
        os.environ["FAKE_DEEPSEEK_KEY"] = "present"

        def fake_chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):  # noqa: ANN001
            payload = json.loads(messages[1]["content"])
            text = payload["review_case"]["clean_source_message"]
            if "superseded" in text:
                response = {
                    "supported_labels": [],
                    "unsupported_labels": payload["review_case"]["labels"],
                    "confidence": 0.5,
                    "needs_human_review": True,
                }
            else:
                response = {
                    "supported_labels": [],
                    "unsupported_labels": payload["review_case"]["labels"],
                    "confidence": 0.92,
                    "needs_human_review": False,
                }
            return {"choices": [{"message": {"content": json.dumps(response)}}]}

        result = review.run_semantic_scope_source_review(
            registry_path=self.registry,
            live=True,
            api_key_env="FAKE_DEEPSEEK_KEY",
            max_cases=2,
            min_cases=2,
            min_pass_rate=0.0,
            min_label_pass_rate=0.65,
            chat_fn=fake_chat_fn,
        )

        rendered = json.dumps(result, ensure_ascii=False)
        preference_taxonomy = result["label_failure_taxonomy"]["by_label"]["preference"]

        self.assertEqual(result["failed_label_categories"], ["preference"])
        self.assertEqual(
            preference_taxonomy["by_class"],
            {
                "stale_or_currentness_boundary": 1,
                "unsupported_label": 1,
            },
        )
        self.assertEqual(len(preference_taxonomy["public_safe_examples"]), 2)
        self.assertNotIn("short Chinese summaries", rendered)
        self.assertNotIn("Private Preference Title", rendered)
        self.assertNotIn("msg_pref_", rendered)

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

    def test_public_shadow_cohort_exercises_expected_source_review_cases(self) -> None:
        os.environ["FAKE_DEEPSEEK_KEY"] = "present"

        def fake_chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):  # noqa: ANN001
            payload = json.loads(messages[1]["content"])
            labels = payload["review_case"]["labels"]
            text = payload["review_case"]["clean_source_message"]
            unsupported = (
                labels
                if "unsupported shadow label" in text
                or "stale note is superseded" in text
                or "build finished at noon" in text
                or "old preference is superseded" in text
                else []
            )
            supported = [] if unsupported else labels
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "supported_labels": supported,
                                    "unsupported_labels": unsupported,
                                    "confidence": 0.92,
                                    "needs_human_review": False,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

        result = review.run_semantic_scope_source_review(
            live=True,
            public_shadow=True,
            api_key_env="FAKE_DEEPSEEK_KEY",
            max_cases=8,
            min_cases=7,
            min_pass_rate=1.0,
            chat_fn=fake_chat_fn,
        )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["ok"], rendered)
        self.assertEqual(result["cohort"], "public_source_review_shadow")
        self.assertEqual(result["claim_level"], "public_shadow_source_review")
        self.assertEqual(result["case_count"], 7)
        self.assertEqual(result["passed_count"], 7)
        self.assertEqual(result["review_buckets"]["expected_supported"], 3)
        self.assertEqual(result["review_buckets"]["expected_unsupported"], 2)
        self.assertEqual(result["review_buckets"]["expected_human_review"], 2)
        self.assertEqual(result["per_label"]["preference"]["case_count"], 3)
        self.assertEqual(
            result["label_failure_taxonomy"]["by_label"]["preference"]["by_class"],
            {
                "stale_or_currentness_boundary": 1,
                "unsupported_label": 1,
            },
        )
        self.assertEqual(
            result["public_shadow_requirements"],
            {
                "source_open_positive": True,
                "stale_or_superseded_source": True,
                "unsupported_semantic_sidecar": True,
                "multilingual_paraphrase": True,
                "preference_source_open_positive": True,
                "preference_unsupported_generic_claim": True,
                "preference_stale_currentness_boundary": True,
            },
        )
        self.assertNotIn("unsupported shadow label", rendered)
        self.assertNotIn("stale note is superseded", rendered)
        self.assertNotIn("concise Chinese", rendered)
        self.assertNotIn("shadow_msg_", rendered)

    def test_public_shadow_requires_all_shadow_case_families_before_claiming(self) -> None:
        os.environ["FAKE_DEEPSEEK_KEY"] = "present"

        def fake_chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):  # noqa: ANN001
            payload = json.loads(messages[1]["content"])
            labels = payload["review_case"]["labels"]
            text = payload["review_case"]["clean_source_message"]
            unsupported = (
                labels
                if "unsupported shadow label" in text
                or "stale note is superseded" in text
                or "build finished at noon" in text
                or "old preference is superseded" in text
                else []
            )
            supported = [] if unsupported else labels
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "supported_labels": supported,
                                    "unsupported_labels": unsupported,
                                    "confidence": 0.92,
                                    "needs_human_review": False,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

        result = review.run_semantic_scope_source_review(
            live=True,
            public_shadow=True,
            api_key_env="FAKE_DEEPSEEK_KEY",
            max_cases=3,
            min_cases=3,
            min_pass_rate=1.0,
            chat_fn=fake_chat_fn,
        )

        self.assertFalse(result["ok"], result)
        self.assertEqual(result["status"], "public_shadow_missing_required_cases")
        self.assertEqual(result["claim_level"], "diagnostic_only")
        self.assertIn(False, result["public_shadow_requirements"].values())


if __name__ == "__main__":
    unittest.main()
