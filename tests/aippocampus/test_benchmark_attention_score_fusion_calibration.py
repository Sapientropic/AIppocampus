from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
for _path in (SCRIPTS, BENCHMARKS):
    sys.path.insert(0, str(_path))

import benchmark_attention_score_fusion_calibration as calibration  # noqa: E402


class AttentionScoreFusionCalibrationTests(unittest.TestCase):
    def test_report_exports_sanitized_features_and_improves_anti_nag_precision(self) -> None:
        report = calibration.run_attention_score_fusion_calibration()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(report["kind"], "aippocampus_attention_score_fusion_calibration")
        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(report["feature_rows"]["row_count"], 12)
        self.assertFalse(report["privacy_boundary"]["raw_text_emitted"])
        self.assertFalse(report["privacy_boundary"]["private_text_emitted"])
        self.assertNotIn("PRIVATE_", encoded)
        self.assertNotIn("gold_answer", encoded)

        current = report["arms"]["current_deterministic_weights"]
        calibrated = report["arms"]["calibrated_rule_grid"]

        self.assertLess(
            current["metrics"]["route_precision_at_threshold"]["rate"],
            calibrated["metrics"]["route_precision_at_threshold"]["rate"],
        )
        self.assertEqual(current["red_lines"]["anti_nag_violation_count"], 1)
        self.assertEqual(calibrated["red_lines"]["anti_nag_violation_count"], 0)
        self.assertEqual(calibrated["metrics"]["route_precision_at_threshold"]["rate"], 1.0)
        self.assertEqual(calibrated["metrics"]["route_recall_at_threshold"]["rate"], 1.0)
        self.assertEqual(calibrated["red_lines"]["privacy_bypass_count"], 0)
        self.assertEqual(calibrated["red_lines"]["hard_mask_override_count"], 0)
        self.assertIn("calibration_affects_routing_only", report["cannot_claim"])
        self.assertIn("default_foreground_adoption", report["cannot_claim"])

    def test_hard_masks_remain_non_negotiable_even_with_high_scores(self) -> None:
        rows = calibration.export_attention_feature_rows()
        masked_rows = copy.deepcopy(rows)
        masked = next(row for row in masked_rows if row["features"]["hard_mask_count"] > 0)
        for key in (
            "lexical_score",
            "semantic_score",
            "action_score",
            "evidence_packaging_score",
            "scope_score",
            "salience_score",
        ):
            masked["features"][key] = 1.0

        evaluated = calibration.evaluate_calibration_arm(
            masked_rows,
            calibration.CALIBRATED_RULE_GRID,
            arm_name="mutated_high_score_masked_row",
        )

        masked_result = next(row for row in evaluated["rows"] if row["case_id"] == masked["case_id"])
        self.assertFalse(masked_result["predicted_useful_route"])
        self.assertEqual(evaluated["red_lines"]["privacy_bypass_count"], 0)
        self.assertEqual(evaluated["red_lines"]["hard_mask_override_count"], 0)
        self.assertGreater(evaluated["metrics"]["masked_high_score_suppressed_count"], 0)


if __name__ == "__main__":
    unittest.main()
