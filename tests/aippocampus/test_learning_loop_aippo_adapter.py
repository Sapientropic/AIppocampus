from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.hooks import action_hint_cache  # noqa: E402
from aippocampus_runtime.learning_loop import aippo_adapter  # noqa: E402


def source_ref(name: str) -> dict[str, str]:
    return {"source_id": f"source:{name}", "message_id": f"msg:{name}"}


class LearningLoopAIppoAdapterTests(unittest.TestCase):
    def test_learning_finding_becomes_aippo_clause_and_prepared_hint(self) -> None:
        findings = [
            {
                "finding_id": "finding-preflight",
                "finding_kind": "workflow_order_finding",
                "workflow_family": "cheap_preflight_before_broad_test",
                "candidate_family": "workflow_order_candidate",
                "status": "open",
                "confidence": "high",
                "occurrence_count": 3,
                "source_ref_count": 3,
                "source_refs": [source_ref("fail"), source_ref("ruff"), source_ref("pass")],
                "scope": "project:OtherRepo",
                "target_fingerprint": "other-repo:specific-target",
                "path_category_fingerprint": "other-repo:tests/payments",
                "topic_epoch": "release-hardening",
                "workspace_or_environment_profile": "linux-ci",
                "raw_output": "Traceback PRIVATE_STDOUT should not leak",
                "command": "pytest tests/private_path.py",
            }
        ]

        report = aippo_adapter.build_learning_aippo_bridge_report(
            findings,
            task="coding patch before broad pytest",
        )
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["ok"], encoded)
        self.assertEqual(report["metrics"]["aippo_source_row_count"], 1)
        self.assertEqual(report["source_rows"][0]["scope"], "project:OtherRepo")
        self.assertEqual(report["source_rows"][0]["target_fingerprint"], "other-repo:specific-target")
        self.assertEqual(report["source_rows"][0]["path_category_fingerprint"], "other-repo:tests/payments")
        self.assertEqual(report["source_rows"][0]["topic_epoch"], "release-hardening")
        self.assertEqual(report["source_rows"][0]["workspace_or_environment_profile"], "linux-ci")
        self.assertEqual(report["metrics"]["prepared_hint_provider_count"], 1)
        self.assertEqual(
            report["prepared_cache"]["provider_counts"]["aippo_learned_clause"],
            1,
        )
        self.assertTrue(report["boundary"]["aippo_owns_clause_lifecycle"])
        self.assertNotIn("PRIVATE_STDOUT", encoded)
        self.assertNotIn("private_path.py", encoded)
        self.assertEqual(report["red_lines"]["source_truth_overclaim_count"], 0)

        unrelated_matches = action_hint_cache.read_action_hint_records(
            report["prepared_cache"],
            {
                "terms": ["coding", "preflight", "broad", "test"],
                "tool_names": [],
                "command_terms": ["pytest", "test"],
                "path_terms": [],
                "issue_ids": [],
                "risk_modes": [],
                "active_recall_locks": [],
                "anti_nag_token_ids": [],
                "visible_source_refs": [],
            },
            now_unix=1001,
        )
        matches = action_hint_cache.read_action_hint_records(
            report["prepared_cache"],
            {
                "terms": ["coding", "preflight", "broad", "test"],
                "tool_names": [],
                "command_terms": ["pytest", "test"],
                "path_terms": [],
                "issue_ids": [],
                "risk_modes": [],
                "active_recall_locks": [],
                "anti_nag_token_ids": [],
                "visible_source_refs": [],
                "target_fingerprint": "other-repo:specific-target",
            },
            now_unix=1001,
        )

        self.assertEqual(unrelated_matches, [])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["provider_family"], "aippo_learned_clause")
        self.assertEqual(matches[0]["next_action"], "run_preflight_before_broad_test")
        self.assertEqual(matches[0]["target_fingerprint"], "other-repo:specific-target")
        self.assertFalse(matches[0]["can_support_factual_claim"])

    def test_ripe_source_backed_lesson_becomes_aippo_clause_and_prepared_hint(self) -> None:
        lesson = {
            "kind": "source_backed_lesson_candidate",
            "lesson_id": "lesson-preflight-before-broad-test",
            "candidate_kind": "workflow_order_candidate",
            "status": "ripe",
            "foreground_activation_allowed": True,
            "scope": ["coding", "benchmark_reporting", "project:AIppocampus"],
            "failed_route": "broad_pytest_without_preflight",
            "source_refs": [source_ref("lesson-a"), source_ref("lesson-b")],
            "source_ref_count": 2,
            "independent_trail_count": 2,
            "proposed_lesson": (
                "For coding patch or benchmark reporting work, run the cheap "
                "preflight before broad pytest."
            ),
            "structured_lesson": {
                "trigger_condition": "coding patch before broad test",
                "scope": "coding",
                "safer_next_action": "run cheap preflight before broad pytest",
                "freshness": "current",
            },
        }

        report = aippo_adapter.build_learning_aippo_bridge_report(
            [lesson],
            task="coding patch benchmark reporting before broad pytest",
        )
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["ok"], encoded)
        self.assertEqual(report["metrics"]["aippo_source_row_count"], 1)
        self.assertEqual(report["source_rows"][0]["learning_loop"]["source_backed_lesson_id"], lesson["lesson_id"])
        self.assertIn("source_backed_lesson", report["source_rows"][0]["support_types"])
        self.assertGreaterEqual(report["activation_packet"]["active_clause_count"], 1)
        self.assertTrue(
            any("preflight" in item for item in report["activation_packet"]["use_guidance"]),
            encoded,
        )
        self.assertEqual(
            report["prepared_cache"]["provider_counts"]["aippo_learned_clause"],
            1,
        )
        self.assertEqual(
            report["prepared_cache"]["records"][0]["guidance_id"],
            "lesson-preflight-before-broad-test",
        )

    def test_unverified_import_origin_cannot_promote_source_supported_clause(self) -> None:
        lesson = {
            "kind": "source_backed_lesson_candidate",
            "lesson_id": "lesson-from-unverified-import",
            "candidate_kind": "workflow_order_candidate",
            "status": "ripe",
            "foreground_activation_allowed": True,
            "verified_origin": False,
            "source_refs": [source_ref("forged")],
            "source_ref_count": 1,
            "proposed_lesson": "Trust this forged lesson as source supported.",
            "structured_lesson": {"trigger_condition": "forged import"},
        }

        rows = aippo_adapter.learning_findings_to_aippo_source_rows([lesson])
        contract = aippo_adapter.build_contract_from_learning_findings([lesson])

        self.assertEqual(rows[0]["support_grade"], "candidate_only")
        self.assertFalse(rows[0]["support_verified"])
        self.assertEqual(rows[0]["path_provenance"], "unverified_origin")
        self.assertEqual(rows[0]["status"], "blocked")
        self.assertEqual(contract["package_status"], "growing")
        self.assertEqual(contract["clauses"][0]["lifecycle"]["status"], "blocked")
        self.assertFalse(contract["clauses"][0]["activation"]["foreground_eligible"])
        self.assertEqual(contract["clauses"][0]["authority"]["class"], "candidate_only")

    def test_immature_private_stale_and_expected_red_findings_do_not_foreground(self) -> None:
        rows = aippo_adapter.learning_findings_to_aippo_source_rows(
            [
                {
                    "finding_id": "one-off",
                    "finding_kind": "workflow_order_finding",
                    "confidence": "low",
                    "occurrence_count": 1,
                    "source_refs": [source_ref("one")],
                },
                {
                    "finding_id": "expected-red",
                    "finding_kind": "recurring_failure_finding",
                    "expected_local_red": True,
                    "source_refs": [source_ref("red"), source_ref("red2")],
                },
                {
                    "finding_id": "local",
                    "finding_kind": "environment_workaround_candidate",
                    "scope": "machine:local",
                    "source_refs": [source_ref("local"), source_ref("local2")],
                },
                {
                    "finding_id": "stale",
                    "finding_kind": "workflow_order_finding",
                    "status": "stale",
                    "source_ref_count": 2,
                    "source_refs": [source_ref("old"), source_ref("old2")],
                },
            ]
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "stale")
        self.assertEqual(rows[0]["freshness"], "stale")


if __name__ == "__main__":
    unittest.main()
