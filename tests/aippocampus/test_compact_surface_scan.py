from __future__ import annotations

import sys
import unittest
from unittest import mock

from tools.aippocampus import compact_surface_scan


class CompactSurfaceScanTests(unittest.TestCase):
    def test_denied_field_paths_find_nested_policy_fields(self) -> None:
        payload = {
            "foreground_action": {
                "id": "act",
                "claim_boundary": "operator_proof_not_frontstage",
            },
            "safe_next_actions": [
                {
                    "id": "detail",
                    "operator_json_available": True,
                }
            ],
        }

        self.assertEqual(
            sorted(compact_surface_scan.denied_field_paths(payload)),
            [
                "foreground_action.claim_boundary",
                "safe_next_actions[0].operator_json_available",
            ],
        )

    def test_mcp_runtime_recovery_scan_requires_structured_content(self) -> None:
        check = compact_surface_scan.scan_mcp_runtime_recovery()

        self.assertTrue(check["ok"], check)
        self.assertTrue(check["has_structured_content"])
        self.assertEqual(check["denied_field_paths"], [])

    def test_cli_scan_covers_background_success_and_recovery_paths(self) -> None:
        self.assertIn("aippocampus agent background --json", compact_surface_scan.CLI_COMMANDS)
        self.assertIn(
            'aippocampus agent background "compact foreground audit" --json',
            compact_surface_scan.CLI_COMMANDS,
        )

    def test_cli_scan_covers_search_doctor_and_storage_surfaces(self) -> None:
        self.assertIn(
            'aippocampus search --all "compact foreground audit" --json --max 5',
            compact_surface_scan.CLI_COMMANDS,
        )
        self.assertIn("aippocampus doctor provider --json", compact_surface_scan.CLI_COMMANDS)
        self.assertIn(
            "aippocampus storage gc --dry-run --summary-json --cwd .",
            compact_surface_scan.CLI_COMMANDS,
        )
        self.assertIn(
            "aippocampus storage gc --dry-run --json --top 1 --cwd .",
            compact_surface_scan.CLI_COMMANDS,
        )
        deep_search = next(
            probe
            for probe in compact_surface_scan.CLI_PROBES
            if "--search-budget deep" in probe.command
        )
        self.assertEqual(deep_search.profile, "detail_or_full")

    def test_cli_scan_records_successful_elapsed_time(self) -> None:
        check = compact_surface_scan.scan_cli_command(
            [
                sys.executable,
                "-c",
                "import json; print(json.dumps({'ok': True, 'safe_next_actions': []}))",
            ],
            cwd=compact_surface_scan.PATHS.repo_root,
            timeout_seconds=2,
        )

        self.assertTrue(check["ok"], check)
        self.assertIn("elapsed_ms", check)
        self.assertGreaterEqual(check["elapsed_ms"], 0)
        self.assertEqual(check["timeout_seconds"], 2)

    def test_cli_scan_timeout_is_structured_failure(self) -> None:
        check = compact_surface_scan.scan_cli_command(
            [sys.executable, "-c", "import time; time.sleep(2)"],
            cwd=compact_surface_scan.PATHS.repo_root,
            timeout_seconds=0.1,
        )

        self.assertFalse(check["ok"], check)
        self.assertEqual(check["error"], "timeout")
        self.assertIn("time.sleep", check["surface"])
        self.assertIn("elapsed_ms", check)
        self.assertLess(check["elapsed_ms"], 1500)

    def test_run_scan_reports_first_slow_surface(self) -> None:
        report = compact_surface_scan.run_scan(
            cwd=compact_surface_scan.PATHS.repo_root,
            include_cli=False,
            slow_probe_ms=0,
        )

        self.assertTrue(report["ok"], report)
        self.assertIn("elapsed_ms", report)
        self.assertGreater(report["checked_count"], 0)
        self.assertIsNotNone(report["first_slow_surface"])

    def test_run_scan_clamps_exhausted_budget_before_probe(self) -> None:
        observed_timeouts: list[float] = []

        def fake_scan_cli_command(*args: object, **kwargs: object) -> dict[str, object]:
            observed_timeouts.append(float(kwargs["timeout_seconds"]))
            return {
                "surface": "fake slow probe",
                "kind": "cli",
                "profile": "foreground_compact",
                "ok": False,
                "error": "scan_budget_exhausted",
                "elapsed_ms": 0.0,
            }

        with (
            mock.patch.object(
                compact_surface_scan,
                "CLI_PROBES",
                (compact_surface_scan.SurfaceProbe("fake slow probe"),),
            ),
            mock.patch.object(
                compact_surface_scan,
                "perf_counter",
                side_effect=[0.0, 1.0, 1.0],
            ),
            mock.patch.object(
                compact_surface_scan,
                "scan_cli_command",
                side_effect=fake_scan_cli_command,
            ),
            mock.patch.object(
                compact_surface_scan,
                "scan_mcp_runtime_recovery",
                return_value={
                    "surface": "mcp_runtime_recovery:agent_recall",
                    "kind": "mcp",
                    "profile": "foreground_compact",
                    "ok": True,
                    "elapsed_ms": 0.0,
                },
            ),
            mock.patch.object(
                compact_surface_scan,
                "scan_mcp_key_tool_compact_cards",
                return_value=[],
            ),
        ):
            report = compact_surface_scan.run_scan(
                cwd=compact_surface_scan.PATHS.repo_root,
                scan_budget_seconds=0.5,
            )

        self.assertEqual(observed_timeouts, [0.0])
        self.assertFalse(report["ok"], report)
        self.assertEqual(report["checks"][0]["error"], "scan_budget_exhausted")

    def test_mcp_key_tool_compact_scan_covers_aippo_and_background(self) -> None:
        checks = compact_surface_scan.scan_mcp_key_tool_compact_cards(
            cwd=compact_surface_scan.PATHS.repo_root,
        )

        self.assertEqual(
            [check["surface"] for check in checks],
            [
                "mcp_tool:agent_aippo",
                "mcp_tool:agent_background",
                "mcp_tool:agent_background_missing_input",
            ],
        )
        for check in checks:
            self.assertTrue(check["ok"], check)
            self.assertTrue(check["has_structured_content"], check)
            self.assertEqual(check["denied_field_paths"], [])


if __name__ == "__main__":
    unittest.main()
