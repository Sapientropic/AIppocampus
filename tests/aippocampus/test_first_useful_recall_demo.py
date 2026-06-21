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
PUBLIC_CLEAN_SOURCE = REPO_ROOT / "examples" / "public-memory-bundle" / "clean-source"
DEMO_CUE = "can an agent catch up without pretending it has innate memory?"

class FirstUsefulRecallDemoSmokeTests(unittest.TestCase):
    def test_public_bundle_recall_cue_round_trips_to_deepen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "last-recall.json"
            env = {
                **os.environ,
                "PYTHONPATH": str(SCRIPTS),
                "AIPPOCAMPUS_AGENT_LAST_RECALL_PATH": str(cache_path),
            }
            base = [sys.executable, "-m", "aippocampus_runtime.recall.agent_continuity"]
            recall_proc = subprocess.run(
                [
                    *base,
                    "recall",
                    DEMO_CUE,
                    "--cwd",
                    str(REPO_ROOT),
                    "--clean-source-dir",
                    str(PUBLIC_CLEAN_SOURCE),
                    "--last-recall-path",
                    str(cache_path),
                    "--json",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
            )

            self.assertEqual(recall_proc.returncode, 0, recall_proc.stderr)
            recall_payload = json.loads(recall_proc.stdout)
            self.assertEqual(recall_payload["status"], "ok")
            self.assertTrue(recall_payload["last_recall_cache_available"])
            self.assertIn("foreground_action", recall_payload)

            deepen_proc = subprocess.run(
                [
                    *base,
                    "deepen",
                    "--request",
                    "1",
                    "--last-recall",
                    "--last-recall-path",
                    str(cache_path),
                    "--json",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
            )
            deepen_payload = json.loads(deepen_proc.stdout)

            self.assertEqual(deepen_proc.returncode, 0, deepen_proc.stderr)
            self.assertEqual(deepen_payload["status"], "ok")
            self.assertEqual(deepen_payload["mode"], "deepen")
            self.assertIn("source", json.dumps(deepen_payload, ensure_ascii=False).casefold())

            second_recall = subprocess.run(
                [
                    *base,
                    "recall",
                    DEMO_CUE,
                    "--cwd",
                    str(REPO_ROOT),
                    "--clean-source-dir",
                    str(PUBLIC_CLEAN_SOURCE),
                    "--last-recall-path",
                    str(cache_path),
                    "--json",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
            )
            second_payload = json.loads(second_recall.stdout)

            self.assertEqual(second_recall.returncode, 0, second_recall.stderr)
            self.assertEqual(
                second_payload["foreground_action"]["id"],
                "reopen_already_opened_route_context",
            )
            self.assertEqual(second_payload["foreground_action"]["tool_name"], "agent_deepen")
            self.assertEqual(second_payload["foreground_action"]["arguments"]["request_index"], 1)
            self.assertIn("--request 1", second_payload["foreground_action"]["command"])
            self.assertIn("--json", second_payload["foreground_action"]["command"])

if __name__ == "__main__":
    unittest.main()
