from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_tool_root_module

readiness = import_tool_root_module("recall_integration_readiness")
REPO_ROOT = Path(__file__).resolve().parents[2]


class RecallIntegrationReadinessTests(unittest.TestCase):
    def test_default_report_names_foreground_wired_and_blocked_surfaces(self) -> None:
        report = readiness.build_recall_integration_readiness()
        by_id = {surface["surface_id"]: surface for surface in report["surfaces"]}

        self.assertTrue(report["ok"])
        self.assertEqual(report["kind"], "aippocampus_recall_integration_readiness")
        self.assertEqual(
            by_id["repo_familiarity_fallback"]["status"],
            "wired_foreground_action",
        )
        self.assertTrue(by_id["repo_familiarity_fallback"]["foreground_callable"])
        self.assertTrue(by_id["mcp_agent_recall_deepen_parity"]["mcp_wired"])
        self.assertEqual(
            by_id["ambient_tiny_agent_recall_affordance"]["status"],
            "wired_secondary_action",
        )
        self.assertTrue(by_id["ambient_tiny_agent_recall_affordance"]["foreground_callable"])
        self.assertTrue(by_id["ambient_tiny_agent_recall_affordance"]["mcp_wired"])
        self.assertIn(
            "not default source evidence",
            by_id["ambient_tiny_agent_recall_affordance"]["claim"],
        )
        self.assertEqual(by_id["ambient_tiny_agent_recall_affordance"]["owner_issue"], "#2554")

    def test_proxy_only_foreground_claim_fails(self) -> None:
        report = readiness.build_recall_integration_readiness(
            [
                {
                    "surface_id": "bad_proxy",
                    "status": "proxy_only",
                    "owner_issue": "#0",
                    "foreground_callable": False,
                    "cli_wired": False,
                    "mcp_wired": False,
                    "claim": "foreground ready from a proxy smoke",
                }
            ]
        )

        self.assertFalse(report["ok"])
        self.assertEqual(
            report["failures"][0]["reason"],
            "proxy_only_surface_claims_foreground_ready",
        )

    def test_cli_wired_mcp_unwired_agent_surface_fails(self) -> None:
        report = readiness.build_recall_integration_readiness(
            [
                {
                    "surface_id": "cli_only_agent_feature",
                    "status": "wired_foreground_action",
                    "owner_issue": "#0",
                    "foreground_callable": True,
                    "cli_wired": True,
                    "mcp_wired": False,
                    "claim": "CLI foreground path is done",
                }
            ]
        )

        self.assertFalse(report["ok"])
        self.assertEqual(
            report["failures"][0]["reason"],
            "agent_facing_cli_wired_but_mcp_unwired",
        )

    def test_live_dogfood_failure_blocks_readiness(self) -> None:
        report = readiness.build_recall_integration_readiness(
            dogfood_report={
                "ok": False,
                "case_count": 3,
                "passed_count": 2,
                "failing_owners": ["registry_search_phrase_coverage"],
            }
        )

        self.assertFalse(report["ok"])
        self.assertEqual(report["failures"][0]["surface_id"], "known_artifact_recall_dogfood")
        self.assertEqual(report["failures"][0]["reason"], "live known-artifact dogfood failed")

    def test_cli_json_report_is_machine_readable(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tools" / "aippocampus" / "recall_integration_readiness.py"),
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
        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(payload["surface_count"], 6)


if __name__ == "__main__":
    unittest.main()
