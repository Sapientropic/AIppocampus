from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops import near_user_semantic_classifier_audit as audit  # noqa: E402


class NearUserSemanticClassifierAuditTests(unittest.TestCase):
    def test_audit_rows_answer_seven_placement_questions(self) -> None:
        report = audit.audit_report()

        self.assertEqual(report["row_count"], report["complete_seven_question_rows"])
        for row in report["rows"]:
            self.assertGreaterEqual(
                set(row["seven_question_answer"]),
                set(audit.SEVEN_QUESTIONS),
            )
        self.assertIn(
            "No near-user semantic concept should be added",
            report["placement_rule"],
        )

    def test_three_powers_keyword_fallback_is_demoted(self) -> None:
        report = audit.audit_report()
        three_powers = next(row for row in report["rows"] if row["file"] == "macro/three_powers.py")

        self.assertEqual(three_powers["classification"], "demote")
        self.assertEqual(three_powers["phrase_table_role"], "fallback_scent_only")
        self.assertIn("keyword_fallback_used", three_powers["fallback_diagnostics"])
        self.assertIn("unknown_orientation_defaults_to_human", report["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
