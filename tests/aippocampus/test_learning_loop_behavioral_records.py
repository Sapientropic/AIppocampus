from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))


class LearningLoopBehavioralRecordsCliTests(unittest.TestCase):
    def run_cli_with_env(self, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "aippocampus_runtime.cli.facade", *args],
            cwd=SCRIPTS,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

    def test_replay_missing_source_uses_foreground_action_contract(self) -> None:
        proc = self.run_cli_with_env("learning", "replay", "--json", env=os.environ.copy())

        self.assertEqual(proc.returncode, 2, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "needs_source_selection")
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])

    def test_behavioral_records_are_discoverable_and_purgeable(self) -> None:
        tmp_ctx = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_ctx.cleanup)
        root = Path(tmp_ctx.name)
        workspace = root / "workspace"
        workspace.mkdir()
        ledger = workspace / ".aippocampus" / "learning-loop" / "effectiveness-ledger.jsonl"
        outcome = workspace / ".aippocampus" / "recall" / "outcome-feedback.jsonl"
        ledger.parent.mkdir(parents=True)
        outcome.parent.mkdir(parents=True)
        ledger.write_text('{"kind":"effectiveness"}\n', encoding="utf-8")
        outcome.write_text('{"kind":"outcome"}\n', encoding="utf-8")
        env = {**os.environ, "AIPPOCAMPUS_HOME": str(root / "registry-home")}

        discover = self.run_cli_with_env(
            "learning", "discover-history", "--cwd", str(workspace), "--json", env=env
        )
        inventory = self.run_cli_with_env(
            "learning", "behavioral-records", "--cwd", str(workspace), "--json", env=env
        )
        dry_run = self.run_cli_with_env(
            "learning",
            "purge-behavioral-records",
            "--cwd",
            str(workspace),
            "--target",
            "all",
            "--dry-run",
            "--json",
            env=env,
        )

        self.assertEqual(discover.returncode, 0, discover.stderr)
        discover_payload = json.loads(discover.stdout)
        candidate_ids = {row["id"] for row in discover_payload["candidates"]}
        self.assertIn("effectiveness_ledger", candidate_ids)
        self.assertIn("recall_outcome_feedback", candidate_ids)
        self.assertIn("agent_route_feedback", candidate_ids)
        self.assertEqual(discover_payload["foreground_action_contract"], "foreground-action-v2")
        discover_action_ids = [action["id"] for action in discover_payload["safe_next_actions"]]
        self.assertNotIn(discover_payload["foreground_action"]["id"], discover_action_ids)

        self.assertEqual(inventory.returncode, 0, inventory.stderr)
        inventory_payload = json.loads(inventory.stdout)
        records = {row["id"]: row for row in inventory_payload["records"]}
        self.assertEqual(records["effectiveness_ledger"]["row_count"], 1)
        self.assertEqual(records["recall_outcome_feedback"]["row_count"], 1)
        self.assertFalse(inventory_payload["privacy_boundary"]["source_truth"])
        self.assertEqual(inventory_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertEqual(
            inventory_payload["foreground_action"]["id"],
            "review_behavioral_records_inventory",
        )
        self.assertIn(
            "preview_behavioral_records_purge",
            {action["id"] for action in inventory_payload["safe_next_actions"]},
        )
        self.assertTrue(
            all(action["mutation_risk"] == "read_only" for action in inventory_payload["safe_next_actions"])
        )

        self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
        dry_run_payload = json.loads(dry_run.stdout)
        self.assertEqual(dry_run_payload["status"], "dry_run")
        self.assertEqual(dry_run_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertTrue(
            all(action["mutation_risk"] == "read_only" for action in dry_run_payload["safe_next_actions"])
        )
        self.assertEqual(
            dry_run_payload["write_next_actions"][0]["id"],
            "confirm_behavioral_records_purge",
        )
        self.assertTrue(dry_run_payload["write_next_actions"][0]["requires_explicit_user_confirmation"])
        self.assertTrue(ledger.exists())
        self.assertTrue(outcome.exists())

        confirmed = self.run_cli_with_env(
            "learning",
            "purge-behavioral-records",
            "--cwd",
            str(workspace),
            "--target",
            "all",
            "--confirm",
            "--json",
            env=env,
        )
        self.assertEqual(confirmed.returncode, 0, confirmed.stderr)
        confirmed_payload = json.loads(confirmed.stdout)
        self.assertEqual(confirmed_payload["status"], "purged")
        self.assertEqual(confirmed_payload["deleted_count"], 2)
        self.assertEqual(confirmed_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("write_next_actions", confirmed_payload)
        self.assertFalse(ledger.exists())
        self.assertFalse(outcome.exists())


if __name__ == "__main__":
    unittest.main()
