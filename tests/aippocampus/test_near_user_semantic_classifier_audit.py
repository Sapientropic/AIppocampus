from __future__ import annotations

import unittest

from aippocampus_runtime.ops import near_user_semantic_classifier_audit as audit


class NearUserSemanticClassifierAuditTests(unittest.TestCase):
    def test_audit_rows_answer_seven_placement_questions(self) -> None:
        report = audit.audit_report()

        self.assertEqual(report["row_count"], report["complete_seven_question_rows"])
        self.assertEqual(report["missing_required_surfaces"], [])
        self.assertEqual(report["duplicate_surface_files"], [])
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

    def test_required_surface_inventory_is_complete_and_unique(self) -> None:
        report = audit.audit_report()
        row_files = [row["file"] for row in report["rows"]]

        self.assertEqual(set(row_files), audit.REQUIRED_AUDIT_SURFACES)
        self.assertEqual(len(row_files), len(set(row_files)))
        self.assertEqual(report["required_surface_count"], len(audit.REQUIRED_AUDIT_SURFACES))
        self.assertEqual(report["suspect_surface_count"], len(audit.SUSPECT_AUDIT_SURFACES))
        self.assertEqual(
            report["suspect_surface_reviewed_count"],
            len(audit.SUSPECT_AUDIT_SURFACES),
        )

    def test_suspect_surfaces_have_review_or_not_applicable_justification(self) -> None:
        report = audit.audit_report()
        rows = {row["file"]: row for row in report["rows"]}

        for surface in audit.SUSPECT_AUDIT_SURFACES:
            row = rows[surface]
            self.assertGreaterEqual(
                set(row["seven_question_answer"]),
                set(audit.SEVEN_QUESTIONS),
            )
            if row["classification"] == "not_applicable":
                self.assertTrue(row.get("justification"))

if __name__ == "__main__":
    unittest.main()
