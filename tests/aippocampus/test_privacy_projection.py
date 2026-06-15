from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.privacy import LOCAL_PATH_REDACTION, redact_private_paths  # noqa: E402


class PrivacyProjectionTests(unittest.TestCase):
    def test_route_kind_counters_and_workflow_paths_are_not_mistaken_for_local_paths(self) -> None:
        payload = {
            "source_reopen_path": "mcp.recall_deepen",
            "workflow_path": "agent recall -> deepen -> answer",
            "route_kinds": {"active_path": 1, "pathlet": 2},
            "file_path": "/Users/example/private.jsonl",
        }

        redacted = redact_private_paths(payload)

        self.assertEqual(redacted["source_reopen_path"], "mcp.recall_deepen")
        self.assertEqual(redacted["workflow_path"], "agent recall -> deepen -> answer")
        self.assertEqual(redacted["route_kinds"]["active_path"], 1)
        self.assertEqual(redacted["route_kinds"]["pathlet"], 2)
        self.assertEqual(redacted["file_path"], LOCAL_PATH_REDACTION)


if __name__ == "__main__":
    unittest.main()
