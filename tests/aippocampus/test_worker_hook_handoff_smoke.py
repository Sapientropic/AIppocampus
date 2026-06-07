from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops import worker_hook_handoff  # noqa: E402


class WorkerHookHandoffSmokeTests(unittest.TestCase):
    def test_three_arm_handoff_fixture_reports_ready_blocked_and_missing_artifacts(self) -> None:
        report = worker_hook_handoff.build_worker_hook_handoff_smoke()
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertTrue(report["ok"])
        self.assertEqual(report["kind"], "aippocampus_worker_hook_handoff_smoke")
        self.assertEqual(report["issue_readout"]["github_issue"], 909)
        metrics = report["metrics"]
        self.assertEqual(metrics["case_count"], 3)
        self.assertEqual(metrics["worker_candidate_available_count"], 2)
        self.assertEqual(metrics["worker_candidate_to_foreground_route_count"], 1)
        self.assertEqual(metrics["plain_scent_after_worker_hit_count"], 0)
        self.assertEqual(metrics["manual_search_after_worker_hint_count"], 0)
        self.assertEqual(metrics["bounded_evidence_after_worker_route_count"], 1)
        self.assertEqual(metrics["stale_or_blocked_worker_candidate_count"], 1)

        no_worker = report["cases_by_id"]["no_worker_artifact"]
        self.assertFalse(no_worker["worker_candidate_available"])
        self.assertFalse(no_worker["foreground_route_emitted"])
        self.assertEqual(no_worker["suppression_reasons"], ["no_worker_artifact_available"])

        blocked = report["cases_by_id"]["blocked_worker_artifact"]
        self.assertTrue(blocked["worker_candidate_available"])
        self.assertFalse(blocked["foreground_route_emitted"])
        self.assertIn("ignore_or_blocked", blocked["action_grammars"])
        self.assertIn("stale_or_blocked_worker_candidate", blocked["suppression_reasons"])

        ready = report["cases_by_id"]["ready_worker_artifact"]
        self.assertTrue(ready["worker_candidate_available"])
        self.assertTrue(ready["hook_context_available"])
        self.assertTrue(ready["foreground_route_emitted"])
        self.assertTrue(ready["bounded_evidence_after_worker_route"])
        self.assertFalse(ready["manual_query_invention_expected"])
        self.assertEqual(ready["source_reopen"]["success_count"], 1)
        self.assertIn("bounded_evidence", ready["action_grammars"])

        self.assertNotIn("Clean source says", encoded)
        self.assertNotIn(str(REPO_ROOT), encoded)
        self.assertFalse(report["contract"]["raw_prompt_text_serialized"])
        self.assertFalse(report["contract"]["raw_source_text_serialized"])
        self.assertFalse(report["contract"]["local_paths_serialized"])

    def test_smoke_cli_runs_as_json(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "tools/aippocampus/smoke/smoke_worker_hook_handoff.py",
                "--json",
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], "aippocampus_worker_hook_handoff_smoke")
        self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
