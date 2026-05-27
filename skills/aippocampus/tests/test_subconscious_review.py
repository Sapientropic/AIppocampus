from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TESTS = ROOT / "tests"
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(SCRIPTS))

import subconscious_review as review  # noqa: E402
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
            path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

            findings = review.recent_findings(path)

        self.assertEqual([finding["job"] for finding in findings], ["project_drift"])

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
