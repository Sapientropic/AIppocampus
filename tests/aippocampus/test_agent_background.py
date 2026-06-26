from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.mcp import server as mcp
from aippocampus_runtime.mcp.compact_profile import mcp_tool_result_payload
from aippocampus_runtime.recall import background_findings, background_recovery


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

def write_generic_issue_working_memory(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "kind": "aippocampus_working_memory",
                "status": "active",
                "route": "use_with_source",
                "candidate_type": "preference_review",
                "candidate_key": "wm_generic_issue",
                "title": "Preference review",
                "summary": "Generic issue review should not look task-specific.",
                "activation_cues": ["issue"],
                "trigger_terms": ["issue"],
                "source_finding_ids": ["finding_generic_issue"],
                "confidence": 0.9,
                "project_label": "AIppocampus",
                "review_state": "agent_adjudicated",
                "route_reason": "Only a generic issue term matched.",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def write_generic_output_working_memory(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "kind": "aippocampus_working_memory",
                "status": "active",
                "route": "use_with_source",
                "candidate_type": "project_memory",
                "candidate_key": "wm_generic_output",
                "title": "Output",
                "summary": "Generic output review should not look task-specific.",
                "activation_cues": ["output"],
                "trigger_terms": ["output"],
                "source_finding_ids": ["sf_generic_output"],
                "confidence": 0.9,
                "project_label": "AIppocampus",
                "review_state": "agent_adjudicated",
                "route_reason": "Only a generic output term matched.",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


class AgentBackgroundTests(unittest.TestCase):
    def tool_payload(self, response: dict) -> dict:
        result = response["result"]
        if isinstance(result.get("structuredContent"), dict):
            self.assertFalse(result["content"][0]["text"].lstrip().startswith("{"))
        return mcp_tool_result_payload(result)

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
        self.assertNotIn("foreground_action_contract", payload)
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertNotIn("findings", payload)
        self.assertNotIn("operator_detail", payload)
        self.assertNotIn("operator_detail_command", payload)
        self.assertNotIn("reader_diagnostic", payload)
        self.assertNotIn("boundary", payload)
        self.assertNotIn("output_boundary", payload)
        self.assertNotIn("cue_used", payload)
        self.assertNotIn(payload["best_finding"], payload.get("finding_summaries", []))
        self.assertNotIn("boundary", finding)
        self.assertNotIn("source_summary", finding)
        self.assertNotIn("next_actions", finding)
        self.assertEqual(payload["foreground_action"]["id"], "reopen_background_finding_source_route")
        self.assertEqual(payload["foreground_action"]["mutation_risk"], "read_only")
        self.assertEqual(finding["source_ref_count"], 0)
        self.assertNotIn("use_boundary", finding)
        self.assertNotIn("durable_low_authority_feedback_write", encoded)
        self.assertNotIn("materialize_action_hint_from_finding", encoded)
        self.assertNotIn("shape_label", finding)
        self.assertEqual(finding["finding_title"], "Action hint candidate")
        self.assertEqual(finding["match_strength"], "distinctive")
        self.assertGreaterEqual(finding["distinctive_match_count"], 1)
        self.assertNotIn("match_reason", finding)
        self.assertNotEqual(finding["matched_terms"], ["action"])
        self.assertIn("action-time learning", finding["matched_terms"])

    def test_agent_background_downgrades_generic_issue_only_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            working_memory = Path(tmp) / "working_memory.jsonl"
            write_generic_issue_working_memory(working_memory)

            payload = background_findings.background_findings_card(
                "AIppocampus UX issue review source-backed continuity",
                working_memory_path=working_memory,
            )

        self.assertEqual(payload["status"], "no_relevant_background_findings")
        self.assertEqual(payload["finding_count"], 0)
        self.assertIsNone(payload["best_finding"])
        self.assertEqual(payload["foreground_action"]["id"], "ordinary_recall")
        self.assertIn("agent recall", payload["foreground_action"]["command"])
        self.assertNotIn("Preference review", json.dumps(payload, ensure_ascii=False))

    def test_agent_background_downgrades_generic_output_only_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            working_memory = Path(tmp) / "working_memory.jsonl"
            write_generic_output_working_memory(working_memory)

            payload = background_findings.background_findings_card(
                "agent-facing UX compact output",
                working_memory_path=working_memory,
            )

        self.assertEqual(payload["status"], "no_relevant_background_findings")
        self.assertEqual(payload["finding_count"], 0)
        self.assertIsNone(payload["best_finding"])
        self.assertEqual(payload["foreground_action"]["id"], "ordinary_recall")

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
        self.assertEqual(payload["foreground_action"], finding["next_actions"][0])
        self.assertNotIn("agent_next_action", payload)
        self.assertEqual(
            actions["reopen_background_finding_source_route"]["target"]["finding_id"],
            "wm_action_time_learning",
        )
        self.assertEqual(
            actions["reopen_background_finding_source_route"]["target"]["source_finding_ids"],
            ["finding_action_learning"],
        )
        self.assertIn("finding_action_learning", actions["reopen_background_finding_source_route"]["command"])
        self.assertIn("--detail compact", actions["reopen_background_finding_source_route"]["command"])
        self.assertIn("agent recall", actions["reopen_background_finding_source_route"]["command"])
        self.assertEqual(
            actions["mark_background_finding_helpful"]["target"]["finding_id"],
            "wm_action_time_learning",
        )
        self.assertEqual(
            actions["keep_background_finding_quiet"]["target"]["finding_id"],
            "wm_action_time_learning",
        )
        self.assertEqual(
            actions["mark_background_finding_helpful"]["mutation_risk"],
            "durable_low_authority_feedback_write",
        )
        self.assertEqual(
            actions["materialize_action_hint_from_finding"]["target"]["source_finding_ids"],
            ["finding_action_learning"],
        )
        self.assertEqual(
            actions["materialize_action_hint_from_finding"]["mutation_risk"],
            "explicit_local_cache_write",
        )

    def test_background_recovery_does_not_reappend_existing_finding_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry_dir = Path(tmp)
            write_background_working_memory(registry_dir / "working_memory.jsonl")

            payload = background_recovery.background_recovery_for_weak_recall(
                query="repeated coding mistakes wm_action_time_learning finding_action_learning sf_12345678",
                registry_dir=registry_dir,
                project="AIppocampus",
                memory_packets=[],
                deepen_requests=[],
                triage_metrics={"memory_packet_count": 0, "deepen_request_count": 0},
            )

        self.assertIsNone(payload)

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
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertEqual(action["id"], "background_for_task_cue")
        self.assertEqual(action["tool_name"], "agent_background")
        self.assertEqual(action["command_template"], 'aippocampus agent background "{task_cue}" --json')
        self.assertTrue(action["template_only"])
        self.assertEqual(action["arguments_template"], {"task": "{task_cue}"})
        self.assertNotIn("command", action)
        self.assertIn("cli_fallback", action)
        self.assertEqual(action["cli_fallback"]["command_template"], 'aippocampus agent background "{task_cue}" --json')
        self.assertTrue(action["cli_fallback"]["template_only"])
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn(action, payload["safe_next_actions"])

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
        self.assertNotIn("foreground_action_contract", payload)
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertEqual(payload["finding_count"], 1)
        self.assertNotIn("shape_label", payload["best_finding"])
        self.assertNotIn("match_reason", payload["best_finding"])
        self.assertNotIn("boundary", payload["best_finding"])
        self.assertNotIn("source_summary", payload["best_finding"])
        self.assertNotIn("next_actions", payload["best_finding"])
        self.assertNotIn("use_boundary", payload["best_finding"])
        self.assertNotIn("findings", payload)
        self.assertNotIn("reader_diagnostic", payload)
        self.assertNotIn("operator_detail_command", payload)
        self.assertNotIn("boundary", payload)
        self.assertNotIn("output_boundary", payload)
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
