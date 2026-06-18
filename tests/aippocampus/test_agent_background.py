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

        finding = payload["best_finding"]
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["detail"], "compact")
        self.assertNotIn("findings", payload)
        self.assertNotIn("operator_detail", payload)
        self.assertNotIn("reader_diagnostic", payload)
        action_ids = [action["id"] for action in finding["next_actions"]]
        self.assertEqual(
            action_ids,
            [
                "reopen_background_finding_source_route",
                "mark_background_finding_helpful",
                "mark_background_finding_wrong",
                "keep_background_finding_quiet",
            ],
        )
        self.assertEqual(finding["next_actions"][0]["mutation_risk"], "read_only")
        for action in finding["next_actions"][1:]:
            self.assertEqual(action["mutation_risk"], "durable_low_authority_feedback_write")
            self.assertEqual(action["claim_boundary"], "feedback_is_not_source_truth")
        self.assertNotIn("materialize_action_hint_from_finding", encoded)
        self.assertEqual(finding["shape_label"], "action_hint_candidate")
        self.assertEqual(finding["finding_title"], "Action hint candidate")
        self.assertIn("Action-time learning", finding["match_reason"])
        self.assertNotEqual(finding["matched_terms"], ["action"])
        self.assertIn("action-time learning", finding["matched_terms"])

    def test_agent_background_actions_target_the_selected_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            working_memory = Path(tmp) / "working_memory.jsonl"
            write_background_working_memory(working_memory)

            payload = background_findings.background_findings_card(
                "repeated coding mistakes and action-time learning",
                working_memory_path=working_memory,
                detail="full",
            )

        finding = payload["findings"][0]
        actions = {action["id"]: action for action in finding["next_actions"]}
        self.assertEqual(payload["agent_next_action"], finding["next_actions"][0])
        self.assertEqual(
            actions["reopen_background_finding_source_route"]["target"]["finding_id"],
            "wm_action_time_learning",
        )
        self.assertEqual(
            actions["reopen_background_finding_source_route"]["target"]["source_finding_ids"],
            ["finding_action_learning"],
        )
        self.assertIn("finding_action_learning", actions["reopen_background_finding_source_route"]["command"])
        self.assertEqual(
            actions["mark_background_finding_helpful"]["target"]["finding_id"],
            "wm_action_time_learning",
        )
        self.assertEqual(
            actions["keep_background_finding_quiet"]["target"]["finding_id"],
            "wm_action_time_learning",
        )
        self.assertEqual(
            actions["materialize_action_hint_from_finding"]["target"]["source_finding_ids"],
            ["finding_action_learning"],
        )
        self.assertEqual(
            actions["materialize_action_hint_from_finding"]["mutation_risk"],
            "explicit_local_cache_write",
        )

    def test_agent_background_detail_keeps_reopen_actions_without_feedback_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            working_memory = Path(tmp) / "working_memory.jsonl"
            write_background_working_memory(working_memory)

            payload = background_findings.background_findings_card(
                "repeated coding mistakes and action-time learning",
                working_memory_path=working_memory,
                detail="detail",
            )

        encoded = json.dumps(payload, ensure_ascii=False)
        actions = payload["findings"][0]["next_actions"]
        self.assertEqual(payload["detail"], "detail")
        self.assertEqual([action["id"] for action in actions], ["reopen_background_finding_source_route"])
        self.assertNotIn("mark_background_finding_helpful", encoded)
        self.assertNotIn("materialize_action_hint_from_finding", encoded)

    def test_mcp_exposes_agent_background_tool_schema(self) -> None:
        listed = mcp.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        by_name = {tool["name"]: tool for tool in listed["result"]["tools"]}

        self.assertIn("agent_background", by_name)
        self.assertIn("reviewed background findings", by_name["agent_background"]["description"])
        self.assertIn("detail", by_name["agent_background"]["inputSchema"]["properties"])
        self.assertEqual(
            by_name["agent_background"]["inputSchema"]["required_any"],
            ["cue", "query", "task"],
        )

    def test_agent_background_mcp_missing_input_prefers_tool_action(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 205,
                "method": "tools/call",
                "params": {"name": "agent_background", "arguments": {}},
            }
        )

        payload = self.tool_payload(response)
        action = payload["foreground_action"]
        self.assertTrue(response["result"].get("isError", False), payload)
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(action["id"], "background_for_task_cue")
        self.assertEqual(action["tool_name"], "agent_background")
        self.assertEqual(action["arguments_template"], {"task": "{task_cue}"})
        self.assertNotIn("command", action)
        self.assertIn("cli_fallback", action)
        self.assertEqual(action["cli_fallback"]["command_template"], 'aippocampus agent background "{task_cue}" --json')
        self.assertEqual(payload["agent_next_action"], action)
        self.assertEqual(payload["safe_next_actions"][0], action)

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
        self.assertEqual(payload["best_finding"]["shape_label"], "action_hint_candidate")
        self.assertIn("Action-time learning", payload["best_finding"]["match_reason"])
        self.assertNotIn("findings", payload)
        self.assertNotIn("reader_diagnostic", payload)
        self.assertNotIn(str(working_memory), encoded)

    def test_agent_background_mcp_full_detail_keeps_operator_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            working_memory = Path(tmp) / "working_memory.jsonl"
            write_background_working_memory(working_memory)

            response = mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 207,
                    "method": "tools/call",
                    "params": {
                        "name": "agent_background",
                        "arguments": {
                            "cue": "repeated coding mistakes and action-time learning",
                            "working_memory_path": str(working_memory),
                            "detail": "full",
                        },
                    },
                }
            )

        payload = self.tool_payload(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["detail"], "full")
        self.assertIn("findings", payload)
        self.assertIn("reader_diagnostic", payload)
        self.assertIn("operator_detail", payload)
        self.assertIn("mark_background_finding_helpful", encoded)
        self.assertNotIn(str(working_memory), encoded)


if __name__ == "__main__":
    unittest.main()
