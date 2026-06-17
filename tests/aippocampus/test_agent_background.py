from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.mcp import server as mcp  # noqa: E402
from aippocampus_runtime.recall import background_findings  # noqa: E402


def write_background_working_memory(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "kind": "aippocampus_working_memory",
                "status": "active",
                "route": "use_with_source",
                "candidate_type": "hook_trigger",
                "candidate_key": "wm_action_time_learning",
                "title": "Background finding",
                "summary": "Repeated coding mistakes should refresh action-time learning guidance.",
                "activation_cues": ["action-time learning", "repeated coding mistakes"],
                "trigger_terms": ["action", "action-time learning", "repeated coding mistakes"],
                "source_finding_ids": ["finding_action_learning"],
                "confidence": 0.72,
                "project_label": "AIppocampus",
                "review_state": "agent_adjudicated",
                "route_reason": "Action-time learning guidance can prevent repeated coding mistakes.",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


class AgentBackgroundTests(unittest.TestCase):
    def tool_payload(self, response: dict) -> dict:
        text = response["result"]["content"][0]["text"]
        return json.loads(text)

    def test_agent_background_describes_generic_reviewed_finding_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            working_memory = Path(tmp) / "working_memory.jsonl"
            write_background_working_memory(working_memory)

            payload = background_findings.background_findings_card(
                "repeated coding mistakes and action-time learning",
                working_memory_path=working_memory,
            )

        finding = payload["findings"][0]
        self.assertEqual(finding["shape_label"], "action_hint_candidate")
        self.assertEqual(finding["finding_title"], "Action hint candidate")
        self.assertNotEqual(finding["title"], "Background finding")
        self.assertFalse(finding["low_information_label"])
        self.assertIn("Action-time learning", finding["match_reason"])
        self.assertNotEqual(finding["matched_terms"], ["action"])
        self.assertIn("action-time learning", finding["matched_terms"])

    def test_mcp_exposes_agent_background_tool_schema(self) -> None:
        listed = mcp.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        by_name = {tool["name"]: tool for tool in listed["result"]["tools"]}

        self.assertIn("agent_background", by_name)
        self.assertIn("reviewed background findings", by_name["agent_background"]["description"])
        self.assertEqual(
            by_name["agent_background"]["inputSchema"]["required_any"],
            ["cue", "query", "task"],
        )

    def test_agent_background_mcp_tool_projects_reviewed_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            working_memory = Path(tmp) / "working_memory.jsonl"
            write_background_working_memory(working_memory)

            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 206,
                    "method": "tools/call",
                    "params": {
                        "name": "agent_background",
                        "arguments": {
                            "cue": "repeated coding mistakes and action-time learning",
                            "working_memory_path": str(working_memory),
                        },
                    },
                }
            )

        payload = self.tool_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(response["result"].get("isError", False), payload)
        self.assertEqual(payload["kind"], "aippocampus_background_findings_card")
        self.assertEqual(payload["surface"], "agent_background")
        self.assertEqual(payload["finding_count"], 1)
        self.assertEqual(payload["findings"][0]["shape_label"], "action_hint_candidate")
        self.assertIn("Action-time learning", payload["findings"][0]["match_reason"])
        self.assertNotIn(str(working_memory), encoded)


if __name__ == "__main__":
    unittest.main()
