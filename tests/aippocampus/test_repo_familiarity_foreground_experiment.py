from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
SMOKE = (
    REPO_ROOT
    / "tools"
    / "aippocampus"
    / "smoke"
    / "smoke_repo_familiarity_foreground_experiment.py"
)
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops import (  # noqa: E402
    repo_familiarity_foreground_experiment,
    repo_familiarity_foreground_experiment_fixtures,
)


class RepoFamiliarityForegroundExperimentTests(unittest.TestCase):
    def test_fixture_report_compares_no_card_selected_and_stale_arms(self) -> None:
        report = (
            repo_familiarity_foreground_experiment_fixtures.fixture_foreground_experiment()
        )
        case = report["cases_by_id"]["hook_budget_semantic_gate"]
        arms = case["arms"]

        self.assertEqual(
            report["kind"],
            repo_familiarity_foreground_experiment.EXPERIMENT_KIND,
        )
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(
            set(report["aggregate"]["arms"]),
            {"no_card", "selected_card", "stale_or_irrelevant_card"},
        )
        self.assertTrue(report["experiment_boundary"]["opt_in_only"])
        self.assertTrue(report["experiment_boundary"]["deterministic_proxy_only"])
        self.assertTrue(report["experiment_boundary"]["cannot_claim_live_cost_reduction"])
        self.assertTrue(report["experiment_boundary"]["cannot_claim_default_foreground_lift"])
        self.assertTrue(report["experiment_boundary"]["no_multi_agent_persistence"])

        no_card = arms["no_card"]
        selected = arms["selected_card"]
        stale = arms["stale_or_irrelevant_card"]
        for arm in (no_card, selected, stale):
            self.assertIn("route_quality_proxy", arm)
            self.assertIn("tool_call_count", arm)
            self.assertIn("input_token_proxy", arm)
            self.assertIn("elapsed_ms_proxy", arm)
            self.assertIn("stale_route_drag_count", arm)

        self.assertGreater(selected["route_quality_proxy"], no_card["route_quality_proxy"])
        self.assertEqual(selected["selected_card_count"], 1)
        self.assertEqual(selected["selected_landmarks"], ["foreground hook semantic budget"])
        self.assertEqual(selected["stale_route_drag_count"], 0)
        self.assertEqual(stale["selected_card_count"], 0)
        self.assertGreater(stale["fast_reject_count"], 0)
        self.assertEqual(stale["stale_route_drag_count"], 0)

    def test_report_keeps_live_and_default_foreground_claims_unclaimed(self) -> None:
        report = (
            repo_familiarity_foreground_experiment_fixtures.fixture_foreground_experiment()
        )
        readout = report["issue_readouts"]["github_250"]

        self.assertEqual(readout["no_card_vs_selected_card"], "deterministic_proxy_only")
        self.assertEqual(readout["live_cost_reduction"], "not_measured")
        self.assertEqual(readout["live_answer_quality_lift"], "not_measured")
        self.assertEqual(readout["default_foreground_integration"], "not_implemented")
        self.assertEqual(readout["multi_agent_persistence"], "not_implemented")
        self.assertFalse(readout["closeout_eligible"])

    def test_report_does_not_emit_local_paths_or_raw_source_text(self) -> None:
        report = (
            repo_familiarity_foreground_experiment_fixtures.fixture_foreground_experiment()
        )
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertNotIn(str(REPO_ROOT), encoded)
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn("private source wording", encoded)
        self.assertTrue(report["privacy"]["local_paths_serialized"] is False)
        self.assertTrue(report["privacy"]["raw_source_snippets_serialized"] is False)

    def test_cli_smoke_emits_json_report(self) -> None:
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
        self.assertEqual(
            payload["kind"],
            repo_familiarity_foreground_experiment.EXPERIMENT_KIND,
        )
        self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
