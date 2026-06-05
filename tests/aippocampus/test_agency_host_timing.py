from __future__ import annotations

import json
import subprocess
import sys
import tempfile
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
        self.assertEqual(report["schema_version"], 2)
        self.assertTrue(report["ok"])
        self.assertEqual(
            report["host_surface"]["surface_id"],
            agency_host_timing.HOST_SURFACE_ID,
        )
        self.assertEqual(
            report["host_surface"]["host"],
            "codex-desktop",
        )
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
            cases["suppress_same_surface_duplicate"]["reason"],
            "duplicate_surface_history",
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
        self.assertEqual(aggregate["feedback_ledger_count"], 3)
        self.assertEqual(aggregate["annoyance_counts"], {"high": 1, "low": 1, "medium": 1})
        self.assertEqual(aggregate["usefulness_counts"], {"not_useful": 1, "prevented_repeat": 1, "useful": 1})
        self.assertEqual(aggregate["correction_feedback_count"], 1)

    def test_replay_keeps_source_backed_duplicate_keys_and_boundary_nonclaims(self) -> None:
        report = agency_host_timing.fixture_host_timing_replay()
        show_case = report["cases_by_id"]["show_compaction_warning"]
        duplicate_case = report["cases_by_id"]["suppress_same_surface_duplicate"]
        readout_312 = report["issue_readouts"]["github_312"]
        readout_763 = report["issue_readouts"]["github_763"]
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(show_case["surface_event"]["duplicate_key"])
        self.assertEqual(show_case["surface_event"]["surface_host"], "codex-desktop")
        self.assertEqual(show_case["surface_event"]["host_surface_id"], agency_host_timing.HOST_SURFACE_ID)
        self.assertEqual(duplicate_case["duplicate_source_surface"], agency_host_timing.HOST_SURFACE_ID)
        self.assertEqual(readout_312["host_timing_fixture"], "deterministic_replay_only")
        self.assertEqual(readout_312["live_host_timing"], "not_measured")
        self.assertEqual(readout_312["autonomous_push_forward"], "not_supported")
        self.assertFalse(readout_312["closeout_eligible"])
        self.assertEqual(readout_763["selected_host_surface"], agency_host_timing.HOST_SURFACE_ID)
        self.assertEqual(readout_763["host_surface_timing"], "host_faithful_replay")
        self.assertEqual(readout_763["feedback_ledger"], "contract_replay_public_safe")
        self.assertEqual(readout_763["live_host_timing"], "not_measured")
        self.assertTrue(readout_763["closeout_eligible"])
        self.assertTrue(report["boundary"]["host_owns_permission"])
        self.assertTrue(report["boundary"]["no_live_host_claim"])
        self.assertTrue(report["boundary"]["host_faithful_replay_only"])
        self.assertTrue(report["privacy"]["raw_source_text_serialized"] is False)
        self.assertTrue(report["privacy"]["raw_feedback_text_serialized"] is False)
        self.assertNotIn(str(REPO_ROOT), encoded)
        self.assertNotIn(REPO_ROOT.as_posix(), encoded)
        self.assertNotIn("operator note", encoded)

    def test_feedback_ledger_rows_are_public_safe_and_appendable(self) -> None:
        affordance_map = agency_host_timing.fixture_affordance_map()
        ticket = agency_host_timing._fixture_ticket(
            affordance_map,
            topic_epoch="epoch-agency-host",
        )
        correction_ref = agency_host_timing.fixture_source_ref(99, message_id="msg-correction")

        row = agency_host_timing.host_feedback_ledger_event(
            ticket,
            host_id="codex-desktop",
            topic_epoch="epoch-agency-host",
            outcome="corrected",
            usefulness="not_useful",
            annoyance="high",
            correction_refs=[correction_ref],
            operator_note="operator note should not be serialized",
        )

        self.assertEqual(row["kind"], agency_host_timing.FEEDBACK_LEDGER_KIND)
        self.assertEqual(row["host_surface_id"], agency_host_timing.HOST_SURFACE_ID)
        self.assertEqual(row["outcome"], "corrected")
        self.assertEqual(row["usefulness"], "not_useful")
        self.assertEqual(row["annoyance"], "high")
        self.assertTrue(row["correction_source_ref_fingerprint"])
        self.assertFalse(row["raw_feedback_text_stored"])
        self.assertNotIn("operator note", json.dumps(row, ensure_ascii=False, sort_keys=True))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agency-host-feedback.jsonl"
            self.assertEqual(agency_host_timing.append_feedback_ledger_events(path, [row]), 1)
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["kind"], agency_host_timing.FEEDBACK_LEDGER_KIND)

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
        self.assertEqual(payload["host_surface"]["surface_id"], agency_host_timing.HOST_SURFACE_ID)


if __name__ == "__main__":
    unittest.main()
