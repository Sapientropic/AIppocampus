from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SKILL_SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

from aippocampus_runtime.ops import (
    cognitive_observatory,  # noqa: E402
    observatory_completeness,  # noqa: E402
)


class CognitiveObservatoryCurrentCompletenessTests(unittest.TestCase):
    def test_current_fixture_reports_surface_matrix_and_read_only_boundaries(self) -> None:
        report = observatory_completeness.build_current_completeness_report()

        self.assertEqual(
            report["kind"],
            "aippocampus_cognitive_observatory_current_completeness",
        )
        self.assertTrue(report["ok"], report)
        self.assertTrue(report["complete_current_surface"], report)
        self.assertEqual(report["mode"], "local_current_fixture")

        rows = {row["surface"]: row for row in report["surface_matrix"]}
        for surface in observatory_completeness.EXPECTED_CURRENT_SURFACES:
            self.assertIn(surface, rows)
            self.assertTrue(rows[surface]["surface_supported"], surface)
            self.assertTrue(rows[surface]["surface_present_in_this_readout"], surface)
            self.assertTrue(rows[surface]["surface_validated_by_fixture"], surface)
            self.assertEqual(rows[surface]["included_count"], 1, surface)
            self.assertEqual(rows[surface]["missing_count"], 0, surface)

        reader_contract = report["reader_contract"]
        self.assertEqual(
            reader_contract["included_surfaces"],
            list(observatory_completeness.EXPECTED_CURRENT_SURFACES),
        )
        self.assertEqual(reader_contract["missing_optional_surfaces"], [])
        self.assertGreaterEqual(
            len(reader_contract["blocked_or_suppressed_surfaces"]),
            1,
        )
        self.assertEqual(reader_contract["control_plane_status"], "read_only")
        self.assertGreaterEqual(len(reader_contract["recommended_next_actions"]), 1)

        summary = report["summary"]
        self.assertGreaterEqual(summary["included_surface_count"], 7)
        self.assertGreater(summary["stale_bucket_count"], 0)
        self.assertGreater(summary["privacy_blocked_bucket_count"], 0)
        self.assertGreater(summary["suppressed_bucket_count"], 0)
        self.assertEqual(summary["raw_leak_flag_count"], 0)
        self.assertGreater(summary["control_attempts_blocked"], 0)
        self.assertEqual(summary["ranking_or_hook_mutation_count"], 0)

        boundary = report["control_plane_boundary"]
        self.assertTrue(boundary["blocked_diagnostics_only"])
        self.assertGreater(boundary["attempted_control_action_count"], 0)
        self.assertGreater(boundary["attempted_foreground_hook_mutation_count"], 0)
        self.assertEqual(boundary["ranking_or_hook_mutation_count"], 0)

        self.assertTrue(
            report["issue_readouts"]["github_1443"]["closeout_eligible"],
            report["issue_readouts"]["github_1443"],
        )

        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        for forbidden in [
            "raw_prompt",
            "raw_source_text",
            "source_refs",
            "thread_id",
            "provider_payload",
            "SECRET_TOKEN",
            "E:\\",
        ]:
            self.assertNotIn(forbidden, encoded)

    def test_missing_expected_surface_is_explicit_not_silent_completeness(self) -> None:
        observatory_report = cognitive_observatory.fixture_cognitive_observatory_readout()

        report = observatory_completeness.build_current_completeness_report(
            observatory_report=observatory_report,
        )

        rows = {row["surface"]: row for row in report["surface_matrix"]}
        self.assertTrue(rows["cognitive_load_calibration"]["surface_supported"])
        self.assertFalse(
            rows["cognitive_load_calibration"]["surface_present_in_this_readout"]
        )
        self.assertFalse(
            rows["cognitive_load_calibration"]["surface_validated_by_fixture"]
        )
        self.assertEqual(rows["cognitive_load_calibration"]["included_count"], 0)
        self.assertEqual(rows["cognitive_load_calibration"]["missing_count"], 1)
        self.assertFalse(report["complete_current_surface"])
        self.assertFalse(report["issue_readouts"]["github_1443"]["closeout_eligible"])
        self.assertIn(
            "cognitive_load_calibration",
            report["summary"]["missing_surfaces"],
        )
        self.assertIn(
            "cognitive_load_calibration",
            report["reader_contract"]["missing_optional_surfaces"],
        )

    def test_smoke_cli_emits_public_json(self) -> None:
        smoke = (
            REPO_ROOT
            / "tools"
            / "aippocampus"
            / "smoke"
            / "smoke_cognitive_observatory_current_completeness.py"
        )
        result = subprocess.run(
            [sys.executable, str(smoke), "--json"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)

        self.assertEqual(
            payload["kind"],
            "aippocampus_cognitive_observatory_current_completeness",
        )
        self.assertTrue(payload["issue_readouts"]["github_1443"]["closeout_eligible"])
        self.assertEqual(payload["reader_contract"]["control_plane_status"], "read_only")
        self.assertEqual(payload["summary"]["ranking_or_hook_mutation_count"], 0)
        self.assertNotIn("source_refs", result.stdout)
        self.assertNotIn("E:\\", result.stdout)


if __name__ == "__main__":
    unittest.main()
