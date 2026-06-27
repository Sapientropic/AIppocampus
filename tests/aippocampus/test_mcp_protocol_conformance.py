from __future__ import annotations

import json
import subprocess
import sys
import unittest

from tools.aippocampus import mcp_protocol_conformance

from aippocampus_runtime.mcp.protocol import (
    MCP_DEFAULT_PROTOCOL_VERSION,
    SDK_MIGRATION_NOTE,
    initialize_result,
)


class McpProtocolConformanceTests(unittest.TestCase):
    def test_protocol_policy_is_central_and_keeps_sdk_migration_parked(self) -> None:
        result = initialize_result({"protocolVersion": MCP_DEFAULT_PROTOCOL_VERSION})

        self.assertEqual(result["protocolVersion"], MCP_DEFAULT_PROTOCOL_VERSION)
        self.assertEqual(result["serverInfo"]["name"], "aippocampus")
        self.assertEqual(SDK_MIGRATION_NOTE["status"], "parked")
        self.assertIn("Do not migrate", SDK_MIGRATION_NOTE["do_not_do_now"])

    def test_conformance_report_covers_protocol_errors_and_success_path(self) -> None:
        payload = mcp_protocol_conformance.build_mcp_protocol_conformance_report()

        self.assertTrue(payload["ok"], payload)
        by_name = {case["name"]: case for case in payload["cases"]}
        self.assertEqual(
            by_name["tools_call_malformed_params"]["actual_error_code"],
            "malformed_params",
        )
        self.assertEqual(
            by_name["tools_call_malformed_arguments"]["actual_error_code"],
            "malformed_arguments",
        )
        self.assertEqual(by_name["tools_call_unknown_tool"]["actual_error_code"], "unknown_tool")
        self.assertEqual(
            by_name["tools_call_unsupported_mutation"]["actual_error_code"],
            "unsupported_mutation",
        )
        self.assertEqual(by_name["tools_call_agent_recall_success"]["foreground_tool"], "agent_deepen")
        self.assertEqual(by_name["tools_call_agent_deepen_success"]["status"], "ok")
        self.assertTrue(by_name["tools_call_agent_deepen_success"]["anchor_hit"])
        self.assertEqual(
            payload["protocol_policy"]["sdk_migration"]["status"],
            "parked",
        )

    def test_conformance_command_emits_json(self) -> None:
        proc = subprocess.run(
            [sys.executable, "tools/aippocampus/mcp_protocol_conformance.py", "--json"],
            check=False,
            text=True,
            capture_output=True,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["kind"], "aippocampus_mcp_protocol_conformance")


if __name__ == "__main__":
    unittest.main()
