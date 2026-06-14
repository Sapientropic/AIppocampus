from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "aippocampus"
    / "github"
    / "closeout_audit.py"
)
SPEC = importlib.util.spec_from_file_location("closeout_audit", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
closeout_audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = closeout_audit
SPEC.loader.exec_module(closeout_audit)


class CloseoutAuditTests(unittest.TestCase):
    def test_simple_bugfix_closeout_passes_without_extra_ceremony(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Fixes the negated numeric answer gate.

            Closes #1304.
            """
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["findings"], [])

    def test_unchecked_template_options_do_not_make_closeout_risky(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Adds the closeout audit.

            Closes #1308.

            Closeout class:

            - [x] `complete` - acceptance criteria are satisfied.
            - [ ] `complete_with_followups` - any remaining gaps are linked below.
            - [ ] `blocker_recorded` - useful blocker evidence landed.
            - [ ] `narrow_slice_only` - use relates-to wording.
            """
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["closeout_class"], "complete")
        self.assertEqual(report["risk_terms"], [])

    def test_failure_report_closeout_requires_followup_issue(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Adds a useful failure report, but this is diagnostic-only and not default.

            Closes #1193.
            """
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["findings"][0]["kind"], "risky_closeout_missing_followup")

    def test_empty_template_followup_heading_cannot_borrow_closing_ref(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Adds a useful failure report, but this is diagnostic-only and not default.

            Closes #1193.

            Closeout class:

            - [ ] `complete` - acceptance criteria are satisfied.
            - [ ] `complete_with_followups` - any remaining gaps are linked below.
            - [ ] `blocker_recorded` - useful blocker evidence landed; do not use a
                  closing keyword unless a follow-up issue owns the remaining work.
            - [ ] `narrow_slice_only` - use relates-to wording, not `Closes #...`.

            Remaining gap / follow-up issue:
            """
        )

        self.assertFalse(report["ok"], report)
        self.assertFalse(report["has_followup_pointer"], report)
        self.assertEqual(report["findings"][0]["kind"], "risky_closeout_missing_followup")

    def test_checked_source_boundary_cannot_claim_text_is_not_closeout_risk(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Fixes a straightforward bug.

            Closes #1304.

            ## Source And Privacy Boundary

            - [x] Any public benchmark or readiness claim states what it cannot claim.
            """
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["risk_terms"], [])

    def test_complete_with_followups_accepts_remaining_gap_issue(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Adds a useful failure report, but this is diagnostic-only and not default.

            Closeout class: complete_with_followups
            remaining_gap: #1305 owns semantic/source-side cache measurement.

            Closes #1193.
            """
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["closeout_class"], "complete_with_followups")

    def test_narrow_slice_only_cannot_use_closing_keyword(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Implements one adapter slice.

            Closeout class: narrow_slice_only
            Relates to #1188.
            Closes #1188.
            """
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["findings"][0]["kind"], "narrow_slice_closes_issue")

    def test_scripted_proxy_cannot_close_model_backed_behavior_issue(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Adds a deterministic scripted proxy for the bounded resonance prompt pilot.

            Evidence level: scripted_proxy
            Issue intent: model-backed behavior

            Closes #1319.
            """
        )

        self.assertFalse(report["ok"], report)
        finding = report["findings"][0]
        self.assertEqual(finding["kind"], "evidence_level_mismatch")
        self.assertEqual(finding["declared_evidence_level"], "scripted_proxy")
        self.assertIn("model_pilot", finding["required_evidence_levels"])
        self.assertIn("behavior_run", finding["required_evidence_levels"])

    def test_contract_pack_cannot_close_live_behavior_issue_without_followup(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Lands the public E2E50 contract pack.

            Evidence level: contract_fixture
            Issue intent: live behavior validation

            Closes #279.
            """
        )

        self.assertFalse(report["ok"], report)
        self.assertEqual(report["findings"][0]["kind"], "evidence_level_mismatch")

    def test_lower_evidence_level_passes_with_complete_followup(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Lands the public E2E50 contract pack.

            Closeout class: complete_with_followups
            Evidence level: contract_fixture
            Issue intent: live behavior validation
            remaining_gap: #1322 owns model-backed behavior validation.

            Closes #279.
            """
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["evidence_level"], "contract_fixture")
        self.assertIn("behavior_run", report["required_evidence_levels"])

    def test_benchmark_source_side_closeout_requires_aippocampus_orientation(
        self,
    ) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Adds a LongMemEval source-side semantic cache result.

            Evidence level: scale_run

            Closes #1323.
            """
        )

        self.assertFalse(report["ok"], report)
        self.assertEqual(
            report["findings"][0]["kind"],
            "missing_aippocampus_orientation",
        )

    def test_benchmark_local_provider_prompt_cannot_close_source_side_warming(
        self,
    ) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Uses a temporary provider prompt to label source route text for a
            LongMemEval source-side warming result.

            Evidence level: scale_run
            AIppocampus orientation: checked semantic_scope_builder.

            Closes #1323.
            """
        )

        self.assertFalse(report["ok"], report)
        self.assertEqual(
            report["findings"][0]["kind"],
            "benchmark_local_scaffold_closes_source_side",
        )

    def test_benchmark_local_provider_prompt_passes_as_isolated_experiment_with_followup(
        self,
    ) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Uses a temporary provider prompt as an isolated_experiment for
            LongMemEval source-side semantic cache research.

            Closeout class: complete_with_followups
            Evidence level: scale_run
            AIppocampus orientation: checked semantic_scope_builder and warm_ambient.
            remaining_gap: #1323 owns canonical source-side semantic materialization.

            Closes #1328.
            """
        )

        self.assertTrue(report["ok"], report)

    def test_issue_metadata_file_can_supply_intent_when_pr_body_omits_it(self) -> None:
        report = closeout_audit.audit_pr_body(
            """
            ## Summary
            Lands the public E2E50 contract pack.

            Evidence level: contract_fixture

            Closes #279.
            """,
            issue_metadata={
                279: {
                    "title": "Run model-backed public E2E50 behavior validation",
                    "body": "Need live/model-backed behavior evidence, not only a contract pack.",
                }
            },
        )

        self.assertFalse(report["ok"], report)
        self.assertEqual(report["issue_intent_levels"]["279"], ["model_pilot", "behavior_run"])

    def test_cli_reads_body_file_and_returns_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            body = Path(tmp) / "body.md"
            body.write_text(
                "Closes #1193\n\nfailure report without follow-up\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--body-file",
                    str(body),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])

    def test_closed_issue_traceability_flags_malformed_and_missing_evidence(self) -> None:
        report = closeout_audit.audit_closed_issue_traceability(
            [
                {
                    "number": 1401,
                    "closedByPullRequestsReferences": {"nodes": []},
                    "comments": {
                        "nodes": [
                            {
                                "body": (
                                    "Closeout: fixed on $branch at ^[cf754d8. "
                                    "Verification passed."
                                )
                            }
                        ]
                    },
                },
                {
                    "number": 1402,
                    "closedByPullRequestsReferences": {"nodes": []},
                    "comments": {"nodes": [{"body": "Thanks."}]},
                },
            ],
            window_start="2026-06-13T18:33:49Z",
            window_end="2026-06-14T06:33:49Z",
        )

        self.assertFalse(report["ok"], report)
        self.assertEqual(report["summary"]["closed_issue_count"], 2)
        kinds = [finding["kind"] for finding in report["findings"]]
        self.assertIn("malformed_closeout_comment", kinds)
        self.assertIn("missing_pr_or_commit_reference", kinds)
        self.assertIn("missing_closeout_comment", kinds)
        self.assertTrue(report["policy"]["do_not_rewrite_existing_comments"])

    def test_closed_issue_traceability_accepts_pr_linked_closeout_comment(self) -> None:
        report = closeout_audit.audit_closed_issue_traceability(
            {
                "issues": [
                    {
                        "number": 1403,
                        "closedByPullRequestsReferences": {
                            "nodes": [{"number": 1436, "url": "https://example.test/pull/1436"}]
                        },
                        "comments": {
                            "nodes": [
                                {
                                    "body": (
                                        "Closeout: PR #1436 merged. "
                                        "Verification: docs health and PR gate passed. "
                                        "Cannot claim live/private quality."
                                    )
                                }
                            ]
                        },
                    }
                ]
            }
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["summary"]["issues_with_closed_pr_count"], 1)
        self.assertEqual(report["findings"], [])

    def test_cli_reads_closed_issue_file_and_returns_traceability_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload_path = Path(tmp) / "closed.json"
            payload_path.write_text(
                json.dumps(
                    [
                        {
                            "number": 1404,
                            "closedByPullRequestsReferences": {"nodes": []},
                            "comments": {"nodes": []},
                        }
                    ]
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--closed-issues-file",
                    str(payload_path),
                    "--closed-window-start",
                    "2026-06-13T18:33:49Z",
                    "--closed-window-end",
                    "2026-06-14T06:33:49Z",
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["kind"], "aippocampus_closed_issue_traceability_audit")
        self.assertEqual(payload["window"]["start"], "2026-06-13T18:33:49Z")


if __name__ == "__main__":
    unittest.main()
