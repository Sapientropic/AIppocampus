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
                "scope": "project:AIppocampus",
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
        self.assertEqual(report["metrics"]["prepared_hint_provider_count"], 1)
        self.assertEqual(
            report["prepared_cache"]["provider_counts"]["aippo_learned_clause"],
            1,
        )
        self.assertTrue(report["boundary"]["aippo_owns_clause_lifecycle"])
        self.assertNotIn("PRIVATE_STDOUT", encoded)
        self.assertNotIn("private_path.py", encoded)
        self.assertEqual(report["red_lines"]["source_truth_overclaim_count"], 0)

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
            },
            now_unix=1001,
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["provider_family"], "aippo_learned_clause")
        self.assertFalse(matches[0]["can_support_factual_claim"])

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
