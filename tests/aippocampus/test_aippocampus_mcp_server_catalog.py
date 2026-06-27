from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aippocampus_runtime.contracts import executable_command_violations
from aippocampus_runtime.mcp import server as mcp
from aippocampus_runtime.mcp import tool_handlers as mcp_handlers
from aippocampus_runtime.mcp import tool_readiness
from aippocampus_runtime.ops import provider_key_bridge
from tests.aippocampus.frontstage_assertions import assert_no_compact_debug_fields
from tests.aippocampus.mcp_server_fixtures import (
    assert_recall_template_action,
    field_path_count,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"


class AippocampusMcpServerCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.clean = self.cwd / ".aippocampus" / "clean-source"
        self.clean.mkdir(parents=True)
        self.messages = [
            {
                "message_id": "msg_user",
                "turn_id": "turn_1",
                "source_id": "src_test",
                "source_line": 2,
                "role": "user",
                "phase": "",
                "turn_index": 1,
                "is_final": False,
                "text": "小海马体需要 source-backed continuity。",
            },
            {
                "message_id": "msg_final",
                "turn_id": "turn_1",
                "source_id": "src_test",
                "source_line": 3,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 1,
                "is_final": True,
                "text": "AIppocampus 使用 clean source，而不是摘要替代事实。",
            },
        ]
        with (self.clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for item in self.messages:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        with (self.clean / "turns.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {
                        "turn_id": "turn_1",
                        "turn_index": 1,
                        "message_ids": ["msg_user", "msg_final"],
                        "assistant_phase": "final_answer",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def tool_payload(self, response: dict) -> dict:
        result = response["result"]
        if isinstance(result.get("structuredContent"), dict):
            payload = result["structuredContent"]
            if payload.get("detail") == "compact":
                assert_no_compact_debug_fields(
                    self,
                    payload,
                    surface=str(payload.get("surface") or payload.get("kind") or "mcp_compact"),
                )
            return payload
        text = result["content"][0]["text"]
        return json.loads(text)

    def assert_compact_structured_response(self, response: dict) -> dict:
        result = response["result"]
        payload = result.get("structuredContent")
        self.assertIsInstance(payload, dict)
        text = str(result["content"][0]["text"])
        self.assertFalse(text.lstrip().startswith(("{", "[")), text)
        self.assertLessEqual(len(text), 420)
        assert_no_compact_debug_fields(
            self,
            payload,
            surface=str(payload.get("surface") or payload.get("kind") or "mcp_compact"),
        )
        return payload

    def full_text_payload(self, response: dict) -> dict:
        result = response["result"]
        self.assertNotIn("structuredContent", result)
        text = result["content"][0]["text"]
        self.assertTrue(str(text).lstrip().startswith("{"))
        return json.loads(text)

    def call_tool_payload(self, name: str, arguments: dict[str, object]) -> dict:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": f"call-{name}",
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        return self.tool_payload(response)

    def test_mcp_missing_input_returns_foreground_recovery_cards(self) -> None:
        cases = {
            "recall_context": "missing_intent",
            "search_memory": "missing_query",
            "get_turn_context": "missing_turn_selector",
            "recall_deepen": "missing_recall_handle",
            "recall_diagnostic": "missing_cue",
            "deepen_telepathy_handoff": "missing_telepathy_handoff_card_id",
        }

        for tool_name, code in cases.items():
            with self.subTest(tool=tool_name):
                response = mcp.handle_request(
                    {
                        "jsonrpc": "2.0",
                        "id": f"missing-{tool_name}",
                        "method": "tools/call",
                        "params": {"name": tool_name, "arguments": {}},
                    }
                )
                payload = self.assert_compact_structured_response(response)
                encoded = json.dumps(payload, ensure_ascii=False)

                self.assertFalse(payload["ok"])
                self.assertEqual(payload["status"], "needs_input")
                self.assertEqual(payload["surface_class"], "foreground_recovery_card")
                self.assertEqual(payload["error"]["code"], code)
                self.assertNotIn("details", payload["error"])
                self.assertNotIn("source_boundary", payload)
                self.assertNotIn("related_issue", payload)
                self.assertNotIn("runtime_provenance", encoded)
                self.assertIn("safe_next_actions", payload)
                self.assertTrue(payload["safe_next_actions"][0]["tool_name"])
                if tool_name == "get_turn_context":
                    self.assertIn("staged_followup", payload)
                    self.assertEqual(payload["staged_followup"][0]["tool_name"], "agent_recall")
                    self.assertEqual(payload["staged_followup"][1]["tool_name"], "get_turn_context")
                if tool_name == "deepen_telepathy_handoff":
                    self.assertEqual(payload["foreground_action"]["tool_name"], "list_telepathy_handoffs")
                    self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])

    def test_initialize_and_tools_list_expose_stage4_memory_tools(self) -> None:
        init = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25"},
            }
        )
        self.assertEqual(init["result"]["protocolVersion"], "2025-11-25")
        self.assertIn("tools", init["result"]["capabilities"])

        listed = mcp.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {tool["name"] for tool in listed["result"]["tools"]}
        by_name = {tool["name"]: tool for tool in listed["result"]["tools"]}

        self.assertGreaterEqual(
            names,
            {
                "agent_recall",
                "agent_aippo",
                "agent_deepen",
                "agent_explain",
                "search_memory",
                "recall_context",
                "recall_deepen",
                "recall_diagnostic",
                "latest_reply",
                "get_turn_context",
                "list_threads",
                "register_thread",
                "sync_status",
                "memory_health",
                "list_telepathy_handoffs",
                "deepen_telepathy_handoff",
            },
        )
        agent_deepen_schema = by_name["agent_deepen"]["inputSchema"]
        self.assertNotIn("handle", agent_deepen_schema.get("required") or [])
        self.assertIn("request_index", agent_deepen_schema["properties"])
        self.assertIn("last_recall", agent_deepen_schema["properties"])
        self.assertIn("recall_selector", agent_deepen_schema["properties"])
        self.assertIn("detail", agent_deepen_schema["properties"])
        agent_explain_schema = by_name["agent_explain"]["inputSchema"]
        self.assertNotIn("handle", agent_explain_schema.get("required") or [])
        for prop in ("request_index", "last_recall", "recall_selector", "detail"):
            self.assertIn(prop, agent_explain_schema["properties"])
        self.assertIn("Find source-backed continuity routes", by_name["agent_recall"]["description"])
        self.assertIn("Get low-risk working guidance", by_name["agent_aippo"]["description"])
        self.assertIn("Open the selected recall route", by_name["agent_deepen"]["description"])
        self.assertIn("Search clean source", by_name["search_memory"]["description"])
        schema_text = json.dumps(listed["result"]["tools"], ensure_ascii=False)
        self.assertNotIn("MemoryPackets", schema_text)
        self.assertNotIn("opaque", schema_text)
        self.assertIn("clean_source_dir", by_name["latest_reply"]["inputSchema"]["properties"])
        self.assertEqual(
            by_name["get_turn_context"]["inputSchema"]["required_any"],
            ["turn_id", "message_id", "turn_index"],
        )
        self.assertEqual(
            by_name["agent_recall"]["inputSchema"]["required_any"],
            ["query", "intent", "cue"],
        )
        self.assertIn(
            {"required": ["query"]},
            by_name["agent_recall"]["inputSchema"]["anyOf"],
        )
        self.assertIn(
            {"required": ["intent"]},
            by_name["agent_recall"]["inputSchema"]["anyOf"],
        )
        self.assertIn(
            {"required": ["cue"]},
            by_name["agent_recall"]["inputSchema"]["anyOf"],
        )
        self.assertEqual(
            by_name["recall_context"]["inputSchema"]["required_any"],
            ["intent", "query", "cue"],
        )
        self.assertIn("handle", by_name["agent_deepen"]["inputSchema"]["required_any"])
        self.assertIn("request_index", by_name["agent_deepen"]["inputSchema"]["required_any"])
        self.assertIn("handle", by_name["agent_explain"]["inputSchema"]["required_any"])
        self.assertIn("request_index", by_name["agent_explain"]["inputSchema"]["required_any"])

    def test_mcp_tool_descriptions_disambiguate_when_and_after(self) -> None:
        listed = mcp.handle_request({"jsonrpc": "2.0", "id": 202, "method": "tools/list"})
        tools = listed["result"]["tools"]
        by_name = {tool["name"]: tool for tool in tools}

        for tool in tools:
            with self.subTest(tool=tool["name"]):
                description = tool["description"]
                self.assertIn("When:", description)
                self.assertIn("After:", description)

        self.assertIn("recall_context", by_name["agent_recall"]["description"])
        self.assertIn("agent_recall", by_name["recall_context"]["description"])
        self.assertIn("recall_deepen", by_name["agent_deepen"]["description"])
        self.assertIn("agent_deepen", by_name["recall_deepen"]["description"])
        self.assertIn("recall_diagnostic", by_name["agent_explain"]["description"])
        self.assertIn("agent_explain", by_name["recall_diagnostic"]["description"])
        self.assertIn("exact", by_name["search_memory"]["description"].casefold())

    def test_mcp_tool_catalog_has_one_detail_vocabulary_and_no_near_duplicate_descriptions(self) -> None:
        listed = mcp.handle_request({"jsonrpc": "2.0", "id": 203, "method": "tools/list"})
        tools = listed["result"]["tools"]
        detail_enums = {
            tuple(tool["inputSchema"]["properties"]["detail"]["enum"])
            for tool in tools
            if "detail" in tool["inputSchema"]["properties"]
        }

        self.assertEqual(detail_enums, {("compact", "full")})
        normalized: dict[str, set[str]] = {}
        for tool in tools:
            words = {
                word.strip(".,;:()[]`").casefold()
                for word in tool["description"].split()
                if len(word.strip(".,;:()[]`")) > 3
            }
            normalized[tool["name"]] = words
        for left_name, left_words in normalized.items():
            for right_name, right_words in normalized.items():
                if left_name >= right_name:
                    continue
                overlap = len(left_words & right_words)
                union = len(left_words | right_words) or 1
                self.assertLess(
                    overlap / union,
                    0.78,
                    f"{left_name} and {right_name} descriptions are too similar",
                )

    def test_mcp_catalog_classifies_core_tool_parameters_and_legacy_tools(self) -> None:
        listed = mcp.handle_request({"jsonrpc": "2.0", "id": 204, "method": "tools/list"})
        by_name = {tool["name"]: tool for tool in listed["result"]["tools"]}

        for tool_name in ("agent_recall", "agent_deepen", "search_memory", "memory_health"):
            with self.subTest(tool=tool_name):
                tool = by_name[tool_name]
                schema_tiers = tool["inputSchema"]["x-aippocampus-parameter-tiers"]
                metadata_tiers = tool["metadata"]["aippocampus"]["parameter_tiers"]
                self.assertEqual(schema_tiers, metadata_tiers)
                self.assertEqual(
                    set(schema_tiers),
                    {"required", "common", "advanced", "operator_internal"},
                )
                classified = {
                    parameter
                    for parameters in schema_tiers.values()
                    for parameter in parameters
                }
                self.assertEqual(
                    classified,
                    set(tool["inputSchema"]["properties"]),
                    f"{tool_name} has an unclassified schema parameter",
                )

                foreground = set(schema_tiers["required"]) | set(schema_tiers["common"])
                for parameter in schema_tiers["operator_internal"]:
                    self.assertNotIn(parameter, foreground)
                    self.assertRegex(parameter, r"(^apw_|_path$|_dir$|_jsonl$|^include_private_paths$)")
                if schema_tiers["operator_internal"]:
                    policy = tool["metadata"]["aippocampus"]["operator_internal_parameter_policy"]
                    self.assertEqual(policy["owner"], "mcp_detail_and_compat_surface")
                    self.assertIn("detail/full", policy["removal_criteria"])

        recall_context_meta = by_name["recall_context"]["metadata"]["aippocampus"]
        recall_deepen_meta = by_name["recall_deepen"]["metadata"]["aippocampus"]
        for metadata in (recall_context_meta, recall_deepen_meta):
            self.assertTrue(metadata["legacy"])
            self.assertEqual(metadata["posture"], "legacy_detail_compat")
            self.assertFalse(metadata["foreground_recommended"])
        self.assertEqual(recall_context_meta["enables_next"], ["recall_deepen"])
        self.assertEqual(recall_deepen_meta["requires_prior"], ["recall_context"])

    def test_mcp_catalog_workflow_metadata_marks_recall_search_and_source_opening(self) -> None:
        listed = mcp.handle_request({"jsonrpc": "2.0", "id": 205, "method": "tools/list"})
        by_name = {tool["name"]: tool for tool in listed["result"]["tools"]}

        recall_meta = by_name["agent_recall"]["metadata"]["aippocampus"]
        self.assertEqual(recall_meta["workflow"], "recall_then_deepen")
        self.assertEqual(recall_meta["posture"], "navigation_only")
        self.assertEqual(recall_meta["claim_boundary"], "no_claim_before_reopen")
        self.assertEqual(recall_meta["requires_prior"], [])
        self.assertEqual(recall_meta["enables_next"], ["agent_deepen"])

        deepen_meta = by_name["agent_deepen"]["metadata"]["aippocampus"]
        self.assertEqual(deepen_meta["workflow"], "open_selected_recall_route")
        self.assertEqual(deepen_meta["posture"], "opens_source")
        self.assertEqual(deepen_meta["claim_boundary"], "bounded_evidence_after_source_open")
        self.assertEqual(deepen_meta["requires_prior"], ["agent_recall"])
        self.assertIn("get_turn_context", deepen_meta["enables_next"])

        search_meta = by_name["search_memory"]["metadata"]["aippocampus"]
        self.assertEqual(search_meta["workflow"], "exact_search_then_open")
        self.assertEqual(search_meta["posture"], "source_locator")
        self.assertEqual(search_meta["claim_boundary"], "no_exact_claim_before_source_open")
        self.assertEqual(search_meta["requires_prior"], [])
        self.assertIn("get_turn_context", search_meta["enables_next"])
        self.assertIn("agent_deepen", search_meta["enables_next"])

    def test_mcp_status_missing_key_tools_includes_executable_repair_action(self) -> None:
        with mock.patch.object(
            tool_readiness,
            "TOOLS",
            [{"name": "search_memory", "description": "When: exact. After: reopen.", "inputSchema": {}}],
        ):
            payload = tool_readiness.tool_readiness_summary()

        self.assertFalse(payload["ok"])
        self.assertIn("agent_recall", payload["missing_key_tools"])
        self.assertEqual(payload["foreground_action"]["id"], "repair_mcp_tool_catalog")
        self.assertIn("aippocampus plugin install --codex --verify", payload["foreground_action"]["command"])
        self.assertIn("foreground_action", payload)
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertEqual(executable_command_violations(payload), [])

    def test_mcp_status_present_tools_gives_current_thread_chooser_and_loop_guide(self) -> None:
        payload = tool_readiness.tool_readiness_summary()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertEqual(payload["foreground_action"]["id"], "inspect_current_thread_tool_discovery")
        self.assertEqual(payload["foreground_action"]["mutation_risk"], "read_only")
        self.assertIn("aippocampus update status --json", payload["foreground_action"]["command"])
        self.assertIn("foreground_action", payload)
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertEqual(len(payload["safe_next_actions"]), 2)
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertEqual(
            action_ids,
            [
                "try_agent_recall",
                "deepen_recall_selector_route",
            ],
        )
        self.assertEqual(payload["cli_fallback_actions"][0]["id"], "record_route_feedback_cli_fallback")
        guide = payload["tool_use_guide"]
        self.assertEqual(guide["primary_consumer_field"], "foreground_action")
        self.assertIn("agent_recall", guide["when_to_use"])
        self.assertIn("agent_deepen", guide["when_to_use"])
        self.assertNotIn("agent_feedback", guide["when_to_use"])
        self.assertIn("route_feedback_cli", guide["fallbacks"])
        self.assertIn("current_thread_visibility_missing", guide["fallbacks"])
        self.assertEqual(executable_command_violations(payload), [])

    def test_mcp_status_uses_catalog_metadata_for_foreground_parameters_and_workflow(self) -> None:
        payload = tool_readiness.tool_readiness_summary()
        guide = payload["tool_use_guide"]

        self.assertEqual(
            guide["workflow"]["agent_recall"]["enables_next"],
            ["agent_deepen"],
        )
        self.assertEqual(
            guide["workflow"]["agent_deepen"]["requires_prior"],
            ["agent_recall"],
        )
        self.assertEqual(
            guide["workflow"]["agent_recall"]["claim_boundary"],
            "no_claim_before_reopen",
        )

        foreground_parameters = guide["foreground_parameters"]
        self.assertEqual(
            foreground_parameters["agent_recall"],
            {"required": ["query", "intent", "cue"], "common": ["cwd", "max", "detail"]},
        )
        self.assertEqual(
            foreground_parameters["agent_deepen"],
            {
                "required": ["handle", "request_index"],
                "common": ["recall_selector", "cwd", "max", "detail"],
            },
        )
        self.assertEqual(
            foreground_parameters["search_memory"],
            {"required": ["query"], "common": ["scope", "cwd", "max", "detail"]},
        )
        encoded = json.dumps(foreground_parameters, ensure_ascii=False)
        self.assertNotIn("apw_", encoded)
        self.assertNotIn("last_recall_path", encoded)
        self.assertNotIn("macro_state_jsonl", encoded)
        self.assertNotIn("include_private_paths", encoded)

    def test_mcp_exposes_agent_native_read_tools_with_navigation_boundary(self) -> None:
        last_recall_env = "AIPPOCAMPUS_AGENT_LAST_RECALL_PATH"
        old_last_recall = os.environ.get(last_recall_env)
        os.environ[last_recall_env] = str(self.cwd / "agent-last-recall.json")
        self.addCleanup(
            lambda: os.environ.pop(last_recall_env, None)
            if old_last_recall is None
            else os.environ.__setitem__(last_recall_env, old_last_recall)
        )
        listed = mcp.handle_request({"jsonrpc": "2.0", "id": 201, "method": "tools/list"})
        names = {tool["name"] for tool in listed["result"]["tools"]}
        self.assertGreaterEqual(
            names,
            {"agent_recall", "agent_aippo", "agent_deepen", "agent_explain"},
        )

        recall_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 202,
                "method": "tools/call",
                "params": {
                    "name": "agent_recall",
                    "arguments": {
                        "query": "clean source continuity",
                        "cwd": str(self.cwd),
                        "clean_source_dir": str(self.clean),
                        "max": 2,
                    },
                },
            }
        )

        payload = self.tool_payload(recall_response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(recall_response["result"].get("isError", False), payload)
        self.assertIn("structuredContent", recall_response["result"])
        self.assertEqual(recall_response["result"]["structuredContent"], payload)
        self.assertFalse(recall_response["result"]["content"][0]["text"].lstrip().startswith("{"))
        self.assertLessEqual(len(recall_response["result"]["content"][0]["text"]), 360)
        self.assertNotIn("kind", payload)
        self.assertNotIn("schema_version", payload)
        self.assertNotIn("mode", payload)
        self.assertNotIn("surface", payload)
        self.assertNotIn("opt_in_required", payload)
        self.assertIn("foreground_action", payload)
        self.assertIn("routes", payload)
        self.assertNotIn("apw_recovery_state", payload)
        self.assertNotIn("runtime_provenance", payload)
        self.assertEqual(payload["detail"], "compact")
        self.assertNotIn("output_boundary", payload)
        self.assertNotIn("action_boundary", payload)
        self.assertNotIn("metrics", payload)
        self.assertNotIn("audit_available", payload)
        self.assertNotIn("cannot_claim", payload)
        self.assertIn("reopen", payload["claim_boundary"])
        action = payload["foreground_action"]
        self.assertEqual(action["id"], "agent_deepen_selected_route")
        self.assertEqual(action["tool_name"], "agent_deepen")
        self.assertEqual(action["arguments"]["request_index"], 1)
        self.assertIn("recall_selector", action["arguments"])
        self.assertNotIn("last_recall", action["arguments"])
        self.assertIn("--recall-selector", action["command"])
        self.assertEqual(action["claim_boundary"], "no_claim_before_reopen")
        self.assertNotIn("foreground_action_card", payload)
        self.assertNotIn("memory_packets", payload)
        self.assertNotIn("deepen_requests", payload)
        self.assertNotIn("copy_paste_command", encoded)
        self.assertNotIn("machine_next_command", encoded)
        self.assertNotIn("aippo-nav:", encoded)
        self.assertLessEqual(len(encoded.encode("utf-8")), 5_000)
        self.assertLessEqual(len(payload), 20)
        self.assertLessEqual(field_path_count(payload), 120)
        self.assertNotIn("policy_boundary", payload)
        self.assertNotIn("operator_detail_command", payload)
        self.assertNotIn("associative_path_policy", payload)
        self.assertNotIn("source_anchor_gate", payload)
        self.assertNotIn(str(self.cwd), encoded)

        deepen_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2022,
                "method": "tools/call",
                "params": {
                    "name": "agent_deepen",
                    "arguments": action["arguments"],
                },
            }
        )
        deepen_payload = self.tool_payload(deepen_response)
        deepen_encoded = json.dumps(deepen_payload, ensure_ascii=False)
        self.assertFalse(deepen_response["result"].get("isError", False), deepen_payload)
        self.assertIn("structuredContent", deepen_response["result"])
        self.assertFalse(deepen_response["result"]["content"][0]["text"].lstrip().startswith("{"))
        self.assertEqual(deepen_payload["mode"], "deepen")
        self.assertEqual(deepen_payload["status"], "ok")
        self.assertEqual(deepen_payload["detail"], "compact")
        self.assertEqual(deepen_payload["source_open_posture"], "target_evidence_opened")
        self.assertNotIn("source_window_summary", deepen_payload)
        self.assertEqual(
            deepen_payload["primary_source_snippet"]["text"],
            "小海马体需要 source-backed continuity。",
        )
        self.assertNotIn("result", deepen_payload)
        self.assertNotIn("AIppocampus 使用 clean source", deepen_encoded)
        self.assertNotIn(str(self.cwd), deepen_encoded)

        full_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2021,
                "method": "tools/call",
                "params": {
                    "name": "agent_recall",
                    "arguments": {
                        "query": "clean source continuity",
                        "cwd": str(self.cwd),
                        "clean_source_dir": str(self.clean),
                        "max": 2,
                        "detail": "full",
                    },
                },
            }
        )
        full_payload = self.tool_payload(full_response)
        self.assertEqual(full_payload["detail"], "full")
        self.assertEqual(full_payload["surface"], "agent_cli_or_mcp_adapter")
        self.assertIn("runtime_provenance", full_payload)
        self.assertIn("memory_packets", full_payload)
        self.assertIn("deepen_requests", full_payload)
        self.assertIn("handle", full_payload["deepen_requests"][0])

    def test_mcp_runtime_provenance_is_profile_rendered_not_handler_injected(self) -> None:
        handler_source = (
            REPO_ROOT
            / "skills"
            / "aippocampus"
            / "scripts"
            / "aippocampus_runtime"
            / "mcp"
            / "tool_handlers.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("mcp_runtime_provenance", handler_source)
        self.assertNotIn('["runtime_provenance"]', handler_source)
        self.assertNotIn('["source_anchor_gate"]', handler_source)

    def test_agent_aippo_guidance_card_stays_compact(self) -> None:
        aippo_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 203,
                "method": "tools/call",
                "params": {
                    "name": "agent_aippo",
                    "arguments": {"task": "product usability closeout"},
                },
            }
        )
        aippo_payload = self.tool_payload(aippo_response)
        self.assertFalse(aippo_response["result"].get("isError", False), aippo_payload)
        self.assertEqual(aippo_payload["mode"], "aippo")
        self.assertEqual(aippo_payload["surface"], "agent_aippo_guidance_card")
        self.assertEqual(aippo_payload["foreground_action"]["action_type"], "use_project_working_guidance")
        self.assertNotIn("tool_name", aippo_payload["foreground_action"])
        self.assertEqual(aippo_payload["safe_next_actions"][0]["tool_name"], "agent_aippo")
        self.assertEqual(aippo_payload["safe_next_actions"][0]["arguments"], {"task": "product usability closeout"})
        self.assertIn("foreground_action", aippo_payload)
        self.assertNotIn(aippo_payload["foreground_action"], aippo_payload["safe_next_actions"])
        self.assertTrue(aippo_payload["boundary"]["navigation_only_not_fact"])
        self.assertNotIn("cannot_claim", aippo_payload)
        self.assertIn("source_backed_facts", aippo_payload["claim_boundary"]["must_reopen_for"])
        self.assertNotIn("contract_action", aippo_payload)
        self.assertNotIn("operator_detail", aippo_payload)
        self.assertNotIn("operator_json_command_template", aippo_payload)
        self.assertEqual(
            aippo_payload["operator_json_command"],
            "aippocampus agent aippo --task 'product usability closeout' --json --operator-json",
        )
        self.assertNotIn("activation_packet", aippo_payload)

        aippo_no_task_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 204,
                "method": "tools/call",
                "params": {"name": "agent_aippo", "arguments": {}},
            }
        )
        aippo_no_task_payload = self.tool_payload(aippo_no_task_response)
        encoded_no_task = json.dumps(aippo_no_task_payload, ensure_ascii=False, sort_keys=True)

        self.assertTrue(
            aippo_no_task_response["result"].get("isError", False),
            aippo_no_task_payload,
        )
        self.assertEqual(aippo_no_task_payload["surface"], "agent_aippo_guidance_card")
        self.assertEqual(aippo_no_task_payload["status"], "needs_input")
        self.assertEqual(aippo_no_task_payload["error"]["code"], "aippo_task_required")
        self.assertEqual(
            aippo_no_task_payload["foreground_action"]["id"],
            "provide_task_cue",
        )
        self.assertEqual(aippo_no_task_payload["foreground_action"]["requires"], ["task_cue"])
        self.assertNotIn(
            aippo_no_task_payload["foreground_action"],
            aippo_no_task_payload["safe_next_actions"],
        )
        self.assertNotIn("operator_json_command", aippo_no_task_payload)
        self.assertIn("operator_json_command_template", aippo_no_task_payload)
        self.assertNotIn("operator_detail", aippo_no_task_payload)
        self.assertNotIn("<task_cue>", encoded_no_task)
        self.assertEqual(executable_command_violations(aippo_no_task_payload), [])

    def test_agent_recall_rejects_explicit_invalid_max_values(self) -> None:
        valid = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2031,
                "method": "tools/call",
                "params": {
                    "name": "agent_recall",
                    "arguments": {
                        "query": "clean source continuity",
                        "cwd": str(self.cwd),
                        "clean_source_dir": str(self.clean),
                        "max": 1,
                    },
                },
            }
        )
        self.assertFalse(valid["result"].get("isError", False), self.tool_payload(valid))
        valid_payload = self.tool_payload(valid)
        self.assertEqual(len(valid_payload["routes"]), 1)
        self.assertNotIn("route_count", valid_payload)
        self.assertNotIn("metrics", self.tool_payload(valid))

        for request_id, value, message in [
            (2032, 0, "max must be >= 1"),
            (2033, -1, "max must be >= 1"),
            (2034, 26, "max must be <= 25"),
        ]:
            with self.subTest(value=value):
                response = mcp.handle_request(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "tools/call",
                        "params": {
                            "name": "agent_recall",
                            "arguments": {
                                "query": "clean source continuity",
                                "cwd": str(self.cwd),
                                "clean_source_dir": str(self.clean),
                                "max": value,
                            },
                        },
                    }
                )
                payload = self.tool_payload(response)
                self.assertTrue(response["result"]["isError"])
                self.assertEqual(payload["error"]["code"], "invalid_argument")
                self.assertIn(message, payload["error"]["message"])

    def test_agent_recall_invalid_max_survives_cli_support_reload(self) -> None:
        from aippocampus_runtime.recall import agent_continuity_cli_support

        importlib.reload(agent_continuity_cli_support)

        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2035,
                "method": "tools/call",
                "params": {
                    "name": "agent_recall",
                    "arguments": {
                        "query": "clean source continuity",
                        "cwd": str(self.cwd),
                        "clean_source_dir": str(self.clean),
                        "max": 0,
                    },
                },
            }
        )

        payload = self.tool_payload(response)
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["error"]["code"], "invalid_argument")
        self.assertIn("max must be >= 1", payload["error"]["message"])

    def test_agent_deepen_marks_cannot_verify_as_mcp_error(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2035,
                "method": "tools/call",
                "params": {
                    "name": "agent_deepen",
                    "arguments": {"handle": "not-a-navigation-handle", "cwd": str(self.cwd)},
                },
            }
        )

        payload = self.tool_payload(response)
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["status"], "cannot_verify")
        self.assertFalse(payload["ok"])

    def test_agent_deepen_missing_last_recall_is_recoverable_mcp_card(self) -> None:
        missing_path = self.cwd / "missing-last-recall.json"
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2036,
                "method": "tools/call",
                "params": {
                    "name": "agent_deepen",
                    "arguments": {
                        "request_index": 1,
                        "last_recall": True,
                        "last_recall_path": str(missing_path),
                    },
                },
            }
        )

        payload = self.assert_compact_structured_response(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(payload["status"], "cannot_verify")
        self.assertEqual(payload["surface"], "mcp_agent_deepen_compact")
        self.assertEqual(payload["error"]["code"], "last_recall_unavailable")
        assert_recall_template_action(
            self,
            payload["foreground_action"],
            action_id="recall_with_cue_full_detail",
            full_detail=True,
        )
        self.assertIn("foreground_action", payload)
        if "safe_next_actions" in payload:
            self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertNotIn("operator_detail_command", encoded)
        self.assertNotIn("source_boundary", encoded)
        self.assertNotIn(str(missing_path), encoded)

        full_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "agent-deepen-missing-last-full",
                "method": "tools/call",
                "params": {
                    "name": "agent_deepen",
                    "arguments": {
                        "request_index": 1,
                        "last_recall": True,
                        "last_recall_path": str(missing_path),
                        "detail": "full",
                    },
                },
            }
        )
        full_payload = self.full_text_payload(full_response)
        self.assertTrue(full_response["result"]["isError"])
        self.assertEqual(full_payload["detail"], "full")
        self.assertEqual(full_payload["output_boundary"], "local_private_diagnostic_full")
        self.assertEqual(full_payload["result"]["error"]["code"], "last_recall_unavailable")
        self.assertIn("operator_detail_command", full_payload)
        self.assertNotIn(str(missing_path), json.dumps(full_payload, ensure_ascii=False))

    def test_agent_deepen_and_explain_missing_handle_lead_with_recall(self) -> None:
        for request_id, tool_name in ((2037, "agent_deepen"), (2038, "agent_explain")):
            with self.subTest(tool_name=tool_name):
                response = mcp.handle_request(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "tools/call",
                        "params": {"name": tool_name, "arguments": {"cwd": str(self.cwd)}},
                    }
                )
                payload = self.assert_compact_structured_response(response)

                self.assertTrue(response["result"]["isError"])
                assert_recall_template_action(self, payload["foreground_action"])
                self.assertIn("foreground_action", payload)
                self.assertEqual(payload["surface"], f"mcp_agent_{tool_name.removeprefix('agent_')}_compact")
                self.assertNotIn("operator_detail_command", json.dumps(payload, ensure_ascii=False))
                self.assertIn(
                    f"aippocampus agent {tool_name.removeprefix('agent_')} --request",
                    payload["follow_up_action"]["command_template"],
                )
                self.assertIn("--recall-selector {recall_selector}", payload["follow_up_action"]["command_template"])
                self.assertEqual(payload["follow_up_action"]["requires"], ["recall_selector", "request_index"])

        full_response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "agent-deepen-missing-handle-full",
                "method": "tools/call",
                "params": {
                    "name": "agent_deepen",
                    "arguments": {"cwd": str(self.cwd), "detail": "full"},
                },
            }
        )
        full_payload = self.full_text_payload(full_response)
        self.assertTrue(full_response["result"]["isError"])
        self.assertEqual(full_payload["detail"], "full")
        self.assertEqual(full_payload["output_boundary"], "local_private_diagnostic_full")
        self.assertEqual(full_payload["error"]["code"], "missing_recall_handle")
        self.assertIn("operator_detail_command", full_payload)
        self.assertIn("--detail full", full_payload["operator_detail_command"])

    def test_agent_recall_missing_query_returns_recovery_card(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2039,
                "method": "tools/call",
                "params": {"name": "agent_recall", "arguments": {"cwd": str(self.cwd)}},
            }
        )

        self.assertTrue(response["result"]["isError"])
        payload = self.assert_compact_structured_response(response)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["surface"], "mcp_missing_input_recovery_compact")
        self.assertEqual(payload["error"]["code"], "agent_recall_cue_required")
        self.assertEqual(payload["foreground_action"]["id"], "recall_vague_cue")
        self.assertIn("aippocampus agent recall", payload["foreground_action"]["command_template"])
        self.assertEqual(payload["foreground_action"]["requires"], ["cue"])
        self.assertNotIn("old decision or handoff cue", encoded)
        self.assertNotIn("distinctive exact phrase", encoded)
        self.assertEqual(executable_command_violations(payload), [])

    def test_recall_diagnostic_applies_provider_bridge_before_live_semantic_gate(self) -> None:
        env_var = "MCP_PROVIDER_BRIDGE_TEST_KEY"
        secret_value = "mcp-provider-bridge-secret-value"
        codex_home = self.cwd / "codex-home"
        dotenv = self.cwd / "provider.env"
        dotenv.write_text(f"{env_var}={secret_value}\n", encoding="utf-8")
        provider_key_bridge.write_bridge_manifest(
            provider_key_bridge.bridge_manifest_path(codex_home),
            provider_key_bridge.build_bridge_manifest(
                target="codex-hooks",
                source="explicit-dotenv",
                provider_env_var=env_var,
                credential_dotenv=dotenv,
            ),
        )
        observed: dict[str, str | None] = {}

        def fake_report(**_kwargs: object) -> dict[str, object]:
            observed["env_value"] = os.environ.get(env_var)
            return {
                "kind": "aippocampus_recall_diagnostic",
                "ok": True,
                "surface_reports": [],
                "reasons": [],
            }

        old_value = os.environ.pop(env_var, None)
        try:
            with (
                mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}, clear=False),
                mock.patch.object(mcp_handlers, "recall_diagnostic_report", side_effect=fake_report),
            ):
                os.environ.pop(env_var, None)
                response = mcp_handlers.call_recall_diagnostic(
                    {
                        "cwd": str(self.cwd),
                        "cue": "vague continuity cue",
                        "run_semantic_gate": True,
                        "semantic_gate_mode": "on",
                    }
                )
        finally:
            if old_value is None:
                os.environ.pop(env_var, None)
            else:
                os.environ[env_var] = old_value

        payload = json.loads(response["content"][0]["text"])
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(observed["env_value"], secret_value)
        self.assertEqual(
            payload["provider_key_bridge"]["status"],
            "applied_to_current_mcp_process",
        )
        self.assertEqual(payload["provider_key_bridge"]["provider_env_vars"], [env_var])
        self.assertNotIn(secret_value, encoded)
        self.assertNotIn(str(dotenv), encoded)

    def test_agent_recall_applies_provider_bridge_before_live_semantic_gate(self) -> None:
        env_var = "MCP_AGENT_RECALL_PROVIDER_BRIDGE_TEST_KEY"
        secret_value = "mcp-agent-recall-provider-bridge-secret-value"
        codex_home = self.cwd / "codex-home-agent"
        dotenv = self.cwd / "agent-provider.env"
        dotenv.write_text(f"{env_var}={secret_value}\n", encoding="utf-8")
        provider_key_bridge.write_bridge_manifest(
            provider_key_bridge.bridge_manifest_path(codex_home),
            provider_key_bridge.build_bridge_manifest(
                target="codex-hooks",
                source="explicit-dotenv",
                provider_env_var=env_var,
                credential_dotenv=dotenv,
            ),
        )
        observed: dict[str, str | None] = {}

        class FakeAgent:
            MAX_ROUTES = 5

            @staticmethod
            def recall(*_args: object, **_kwargs: object) -> dict[str, object]:
                observed["env_value"] = os.environ.get(env_var)
                return {
                    "kind": "aippocampus_agent_continuity_path",
                    "status": "ok",
                    "semantic_gate_diagnostics": {"decision": "available"},
                }

        old_value = os.environ.pop(env_var, None)
        try:
            with (
                mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}, clear=False),
                mock.patch.object(mcp_handlers, "agent_continuity_module", return_value=FakeAgent),
            ):
                os.environ.pop(env_var, None)
                response = mcp_handlers.call_agent_recall(
                    {
                        "cwd": str(self.cwd),
                        "query": "vague continuity cue",
                        "run_semantic_gate": True,
                        "semantic": "on",
                        "detail": "full",
                    }
                )
        finally:
            if old_value is None:
                os.environ.pop(env_var, None)
            else:
                os.environ[env_var] = old_value

        payload = json.loads(response["content"][0]["text"])
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(observed["env_value"], secret_value)
        self.assertEqual(
            payload["provider_key_bridge"]["status"],
            "applied_to_current_mcp_process",
        )
        self.assertEqual(payload["provider_key_bridge"]["provider_env_vars"], [env_var])
        self.assertNotIn(secret_value, encoded)
        self.assertNotIn(str(dotenv), encoded)

    def test_tools_only_server_returns_empty_resource_lists(self) -> None:
        resources = mcp.handle_request(
            {"jsonrpc": "2.0", "id": 21, "method": "resources/list"}
        )
        templates = mcp.handle_request(
            {"jsonrpc": "2.0", "id": 22, "method": "resources/templates/list"}
        )

        self.assertEqual(resources["result"], {"resources": []})
        self.assertEqual(templates["result"], {"resourceTemplates": []})

if __name__ == "__main__":
    unittest.main()
