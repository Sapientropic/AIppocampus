from __future__ import annotations

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
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import subconscious_review as review  # noqa: E402
from aippocampus_runtime.subconscious import review_public_output  # noqa: E402
from redaction_fixtures import (  # noqa: E402
    FAKE_TEST_BEARER_TOKEN,
    FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER,
    FAKE_TEST_OPENAI_API_KEY,
    FAKE_TEST_SECRET_VALUE,
    fake_test_windows_path,
)


class SubconsciousReviewTests(unittest.TestCase):
    def test_review_payload_keeps_findings_before_variable_focus(self) -> None:
        payload = review.compact_review_payload(
            [
                {
                    "fingerprint": "sf_runtime",
                    "job": "project_drift",
                    "kind": "project_drift",
                    "title": "Runtime drift",
                    "summary": "T-Sense moved toward Go runtime work.",
                    "confidence": 0.9,
                    "source_refs": [],
                }
            ],
            [],
            focus="T-Sense runtime architecture",
        )
        keys = list(payload.keys())

        self.assertLess(keys.index("findings"), keys.index("focus"))
        self.assertLess(keys.index("focus_rule"), keys.index("focus"))

    def test_review_payload_redacts_external_model_sensitive_text(self) -> None:
        payload = review.compact_review_payload(
            [
                {
                    "fingerprint": "sf_secret",
                    "job": "project_drift",
                    "kind": "project_drift",
                    "title": "Secret route",
                    "summary": f"Do not leak api_key={FAKE_TEST_OPENAI_API_KEY} or {fake_test_windows_path('review.txt')}",
                    "recommendation": f"Bearer {FAKE_TEST_BEARER_TOKEN}",
                    "confidence": 0.9,
                    "source_refs": [],
                }
            ],
            [],
            focus=f"token={FAKE_TEST_SECRET_VALUE}",
        )
        text = json.dumps(payload, ensure_ascii=False)

        self.assertNotIn(FAKE_TEST_OPENAI_API_KEY, text)
        self.assertNotIn(FAKE_TEST_BEARER_TOKEN, text)
        self.assertNotIn(FAKE_TEST_SECRET_VALUE, text)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, text)
        self.assertIn("<redacted:api-key>", text)
        self.assertIn("<redacted:local-path>", text)

    def test_recent_findings_normalizes_quality_and_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "subconscious_jobs.jsonl"
            row = {
                "kind": "aippocampus_subconscious_job_finding",
                "job": "project_drift",
                "finding_kind": "project_drift",
                "title": "Runtime drift",
                "summary": "T-Sense moved toward Go runtime work.",
                "confidence": 0.9,
                "source_refs": [{"thread_key": "session:one", "assistant_line": 12}],
            }
            path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

            findings = review.recent_findings(path)

        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0]["fingerprint"].startswith("sf_"))
        self.assertIn("promotion_readiness", findings[0]["quality"])

    def test_recent_findings_excludes_navigation_only_semantic_labels_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "subconscious_jobs.jsonl"
            rows = [
                {
                    "kind": "aippocampus_subconscious_job_finding",
                    "job": "semantic_scope_labeling",
                    "finding_kind": "semantic_scope_labels",
                    "title": "Casual-important label",
                    "summary": "Navigation-only label.",
                    "confidence": 0.9,
                    "source_refs": [{"thread_key": "session:one", "source_line": 12}],
                },
                {
                    "kind": "aippocampus_subconscious_job_finding",
                    "job": "project_drift",
                    "finding_kind": "project_drift",
                    "title": "Runtime drift",
                    "summary": "Project memory candidate.",
                    "confidence": 0.9,
                    "source_refs": [{"thread_key": "session:one", "assistant_line": 14}],
                },
            ]
            path.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                encoding="utf-8",
            )

            findings = review.recent_findings(path)

        self.assertEqual([finding["job"] for finding in findings], ["project_drift"])

    def test_openai_compatible_route_reports_provider_neutral_review_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jobs_path = root / "subconscious_jobs.jsonl"
            jobs_path.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_subconscious_job_finding",
                        "job": "project_drift",
                        "finding_kind": "project_drift",
                        "title": "Provider drift",
                        "summary": "Local route should not inherit DeepSeek cache assumptions.",
                        "confidence": 0.9,
                        "source_refs": [{"thread_key": "session:one", "assistant_line": 12}],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            def fake_chat(
                messages,
                api_key,
                model,
                base_url,
                max_tokens,
                timeout,
                temperature,
            ):
                del messages, api_key, base_url, max_tokens, timeout, temperature
                self.assertEqual(model, "local-review-model")
                content = {
                    "action": "final",
                    "promotion_candidates": [],
                    "duplicate_groups": [],
                    "weak_findings": [],
                }
                return {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"total_tokens": 1},
                }

            with patch.dict(
                os.environ,
                {
                    "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE": "local_review",
                    "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER": "local-test",
                    "AIPPOCAMPUS_OPENAI_COMPAT_MODEL": "local-review-model",
                    "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL": "http://127.0.0.1:11434/v1",
                    "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV": "LOCAL_REVIEW_KEY",
                    "LOCAL_REVIEW_KEY": "present",
                },
                clear=False,
            ):
                result = review.run_review(
                    jobs_path=jobs_path,
                    output_path=root / "promotion_candidates.jsonl",
                    max_findings=10,
                    jobs=None,
                    focus="",
                    model=review.DEFAULT_MODEL,
                    base_url=review.DEFAULT_BASE_URL,
                    api_key=None,
                    model_route="local_review",
                    no_write=True,
                    chat_fn=fake_chat,
                )

        self.assertEqual(result["model"], "local-review-model")
        self.assertEqual(result["model_route"]["provider"], "local-test")
        self.assertEqual(result["cache"], {"available": False, "kind": "none"})

    def test_review_output_can_record_external_model_source_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "promotion_candidates.jsonl"
            review.append_review_output(
                output,
                {
                    "promotion_candidates": [
                        {
                            "candidate_type": "project_memory",
                            "title": "Provider boundary",
                            "summary": f"External route provenance is explicit; api_key={FAKE_TEST_OPENAI_API_KEY}.",
                            "recommendation": f"Review {fake_test_windows_path('candidate.txt')} before promotion.",
                            "confidence": 0.8,
                            "source_finding_ids": ["sf_one"],
                        }
                    ],
                    "duplicate_groups": [],
                    "weak_findings": [],
                },
                model="local-review-model",
                batch_id="batch",
                usage={},
                source="external_model_subconscious_review",
                model_route={"provider": "local-test"},
            )
            row = json.loads(output.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(row["source"], "external_model_subconscious_review")
        self.assertEqual(row["model_route"]["provider"], "local-test")
        self.assertEqual(row["content_boundary"], review_public_output.MODEL_TEXT_OUTPUT_BOUNDARY)
        self.assertEqual(row["source_finding_ids"], ["sf_one"])
        self.assertEqual(row["candidate_type"], "project_memory")
        row_text = json.dumps(row, ensure_ascii=False)
        self.assertNotIn(FAKE_TEST_OPENAI_API_KEY, row_text)
        self.assertNotIn(FAKE_TEST_ESCAPED_WINDOWS_LOCAL_PATH_MARKER, row_text)
        self.assertNotIn("External route provenance", row_text)
        self.assertNotIn("candidate.txt", row_text)

    def test_validate_review_requires_existing_source_findings(self) -> None:
        findings_by_id = {
            "sf_one": {
                "fingerprint": "sf_one",
                "source_refs": [{"thread_key": "session:one", "assistant_line": 12}],
            }
        }
        parsed = {
            "promotion_candidates": [
                {
                    "candidate_type": "project_memory",
                    "title": "Runtime drift",
                    "summary": "Worth promoting as project memory.",
                    "recommendation": "Review for project memory.",
                    "confidence": 0.88,
                    "source_finding_ids": ["sf_one"],
                },
                {
                    "candidate_type": "project_memory",
                    "title": "Missing",
                    "summary": "Should be ignored.",
                    "confidence": 0.99,
                    "source_finding_ids": ["sf_missing"],
                },
            ]
        }

        result = review.validate_review(parsed, findings_by_id)

        self.assertEqual(len(result["promotion_candidates"]), 1)
        self.assertEqual(result["promotion_candidates"][0]["source_finding_ids"], ["sf_one"])
        self.assertEqual(result["promotion_candidates"][0]["source_refs"][0]["line"], 12)

    def test_validate_review_preserves_activation_cues_for_hook_candidates(self) -> None:
        self.assertIn("activation_cues", review.REVIEW_SYSTEM_PROMPT)
        findings_by_id = {
            "sf_trigger": {
                "fingerprint": "sf_trigger",
                "source_refs": [{"thread_key": "session:friction", "assistant_line": 88}],
            }
        }
        parsed = {
            "promotion_candidates": [
                {
                    "candidate_type": "hook_trigger",
                    "title": "Natural friction recall",
                    "summary": "Use source-backed cue route for natural friction prompts.",
                    "recommendation": "Feed semantic trigger and working-memory sidecars.",
                    "activation_cues": [
                        "最近让我很烦",
                        "recent personal friction",
                        "что меня раздражало недавно",
                    ],
                    "confidence": 0.9,
                    "source_finding_ids": ["sf_trigger"],
                },
                {
                    "candidate_type": "hook_trigger",
                    "title": "No cue trigger",
                    "summary": "Should not fall back to summary prose.",
                    "recommendation": "Drop this until the sidecar has activation cues.",
                    "confidence": 0.9,
                    "source_finding_ids": ["sf_trigger"],
                }
            ]
        }

        result = review.validate_review(parsed, findings_by_id)

        self.assertEqual(len(result["promotion_candidates"]), 1)
        candidate = result["promotion_candidates"][0]
        self.assertEqual(candidate["candidate_type"], "hook_trigger")
        self.assertEqual(
            candidate["activation_cues"],
            ["最近让我很烦", "recent personal friction", "что меня раздражало недавно"],
        )

    def test_review_prompt_admits_question_tracking_candidate_types(self) -> None:
        for candidate_type in [
            "question_candidate",
            "frontier_marker",
            "question_link",
            "theme_candidate",
        ]:
            self.assertIn(candidate_type, review.REVIEW_SYSTEM_PROMPT)

    def test_validate_review_blocks_navigation_only_semantic_label_promotion(self) -> None:
        findings_by_id = {
            "sf_semantic": {
                "fingerprint": "sf_semantic",
                "job": "semantic_scope_labeling",
                "source_refs": [{"thread_key": "session:one", "source_line": 12}],
            }
        }
        parsed = {
            "promotion_candidates": [
                {
                    "candidate_type": "project_memory",
                    "title": "Over-personalizing label",
                    "summary": "Should not become memory.",
                    "recommendation": "Promote.",
                    "confidence": 0.9,
                    "source_finding_ids": ["sf_semantic"],
                }
            ]
        }

        result = review.validate_review(parsed, findings_by_id)

        self.assertEqual(result["promotion_candidates"], [])

    def test_focus_filter_moves_off_focus_candidates_to_weak(self) -> None:
        result = review.apply_focus_filter(
            {
                "promotion_candidates": [
                    {
                        "candidate_type": "project_memory",
                        "title": "International payment setup",
                        "summary": "Card application for overseas payments.",
                        "recommendation": "",
                        "source_finding_ids": ["sf_pay"],
                    },
                    {
                        "candidate_type": "project_memory",
                        "title": "T-Sense Go runtime",
                        "summary": "Runtime architecture shift for Telegram signal work.",
                        "recommendation": "",
                        "source_finding_ids": ["sf_runtime"],
                    },
                ],
                "weak_findings": [],
            },
            "T-Sense runtime architecture",
        )

        self.assertEqual(len(result["promotion_candidates"]), 1)
        self.assertEqual(result["promotion_candidates"][0]["source_finding_ids"], ["sf_runtime"])
        self.assertEqual(result["weak_findings"][0]["finding_id"], "sf_pay")


if __name__ == "__main__":
    unittest.main()
