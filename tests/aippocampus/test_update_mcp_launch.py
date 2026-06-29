from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.update.mcp_readiness import status_mcp


class UpdateMcpLaunchTests(unittest.TestCase):
    def _status_for_args(self, args: list[str]) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mcp_config = root / ".mcp.json"
            mcp_config.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "aippocampus": {
                                "command": "python",
                                "args": args,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            return status_mcp(root, mcp_config)

    def test_facade_module_launch_is_current_host_shape(self) -> None:
        payload = self._status_for_args(["-m", "aippocampus_runtime.cli.facade", "mcp"])

        self.assertEqual(payload["status"], "current")
        self.assertTrue(payload["package_artifact_current"])
        self.assertTrue(payload["current_module_entrypoint"])
        self.assertEqual(
            payload["portable_module_command"],
            f"{Path(sys.executable).name} -m aippocampus_runtime.cli.facade mcp",
        )

    def test_legacy_server_module_launch_needs_review_not_ready_claim(self) -> None:
        payload = self._status_for_args(["-m", "aippocampus_runtime.mcp.server"])

        self.assertEqual(payload["status"], "detect_only")
        self.assertFalse(payload["package_artifact_current"])
        self.assertFalse(payload["current_module_entrypoint"])
        self.assertTrue(payload["manual_review_needed"])


if __name__ == "__main__":
    unittest.main()
