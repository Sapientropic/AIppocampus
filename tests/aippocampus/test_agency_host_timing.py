from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
SMOKE = REPO_ROOT / "tools" / "aippocampus" / "smoke" / "smoke_agency_host_timing.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.coding import agency_host_timing  # noqa: E402


class AgencyHostTimingReplayTests(unittest.TestCase):
    def test_fixture_replay_covers_show_hold_suppress_duplicate_and_feedback(self) -> None:
        report = agency_host_timing.fixture_host_timing_replay()
        cases = report["cases_by_id"]

        self.assertEqual(report["kind"], agency_host_timing.REPLAY_KIND)
        self.assertEqual(report["schema_version"], 1)
        self.assertTrue(report["ok"])
        self.assertEqual(cases["show_compaction_warning"]["decision"], "show")
        self.assertEqual(
            cases["hold_post_answer_phase"]["reason"],
            "task_phase_not_actionable",
        )
        self.assertEqual(
            cases["suppress_visible_source"]["reason"],
            "source_visible",
        )
        self.assertEqual(
            cases["suppress_cross_host_duplicate"]["reason"],
            "duplicate_across_host",
        )
        self.assertEqual(
            cases["suppress_recent_dismissal"]["reason"],
            "recent_negative_feedback",
        )

        aggregate = report["aggregate"]
        self.assertEqual(aggregate["decision_counts"], {"hold": 1, "show": 1, "suppress": 3})
        self.assertEqual(aggregate["foreground_show_count"], 1)
        self.assertEqual(aggregate["duplicate_suppression_count"], 1)
        self.assertEqual(aggregate["negative_feedback_suppression_count"], 1)

    def test_replay_keeps_source_backed_duplicate_keys_and_boundary_nonclaims(self) -> None:
        report = agency_host_timing.fixture_host_timing_replay()
        show_case = report["cases_by_id"]["show_compaction_warning"]
        duplicate_case = report["cases_by_id"]["suppress_cross_host_duplicate"]
        readout = report["issue_readouts"]["github_312"]
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(show_case["surface_event"]["duplicate_key"])
        self.assertEqual(show_case["surface_event"]["surface_host"], "codex-desktop")
        self.assertEqual(duplicate_case["duplicate_source_host"], "codex-desktop")
        self.assertEqual(readout["host_timing_fixture"], "deterministic_replay_only")
        self.assertEqual(readout["live_host_timing"], "not_measured")
        self.assertEqual(readout["autonomous_push_forward"], "not_supported")
        self.assertFalse(readout["closeout_eligible"])
        self.assertTrue(report["boundary"]["host_owns_permission"])
        self.assertTrue(report["boundary"]["no_live_host_claim"])
        self.assertTrue(report["privacy"]["raw_source_text_serialized"] is False)
        self.assertNotIn(str(REPO_ROOT), encoded)
        self.assertNotIn(REPO_ROOT.as_posix(), encoded)

    def test_cli_smoke_emits_public_safe_json_report(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SMOKE), "--json"],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], agency_host_timing.REPLAY_KIND)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["aggregate"]["case_count"], 5)


if __name__ == "__main__":
    unittest.main()
