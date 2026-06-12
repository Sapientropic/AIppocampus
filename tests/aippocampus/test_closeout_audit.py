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


if __name__ == "__main__":
    unittest.main()
