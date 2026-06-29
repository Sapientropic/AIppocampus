from __future__ import annotations

import unittest

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
