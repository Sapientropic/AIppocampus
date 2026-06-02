#!/usr/bin/env python3
"""OpenAI Agents SDK function-tool contract smoke.

This smoke intentionally stops before `Runner.run(...)`: a real runner call
would require model credentials and would send tool schemas to a hosted model.
The integration claim here is narrower and safer: AIppocampus can be exposed as
an app-owned local function tool whose schema carries source ids instead of
private registry paths or raw transcripts.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
from collections.abc import Callable
from typing import Any

SMOKE_CHECKED_AT = "2026-06-02"
INSTALL_COMMAND = 'python -m pip install -e ".[openai-agents]"'
OFFICIAL_DOCS = {
    "agents_sdk_quickstart": "https://openai.github.io/openai-agents-python/quickstart/",
    "agents_sdk_tools": "https://openai.github.io/openai-agents-python/tools/",
    "platform_agents_sdk": "https://platform.openai.com/docs/guides/agents-sdk/",
}
FORBIDDEN_TOOL_OUTPUT_PATTERNS = (
    re.compile(r"[A-Za-z]:[\\/][^\\n\\r\\t ]+"),
    re.compile(r"/(?:Users|home|private|var)/[^\\n\\r\\t ]+"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?i)bearer\\s+[A-Za-z0-9._-]+"),
    re.compile(r"(?i)raw[_ -]?transcript"),
    re.compile(r"(?i)registry[_ -]?path"),
)


def build_sanitized_lookup_payload(query: str) -> dict[str, Any]:
    """Return the public-safe shape an app-owned Agents SDK tool may emit."""
    return {
        "kind": "aippocampus_openai_agents_sdk_tool_contract",
        "query_echo": query,
        "source_ids": ["src_public_demo_001"],
        "source_titles": ["Public demo source"],
        "private_locator_forwarded": False,
        "transcript_text_forwarded": False,
        "hosted_model_input_policy": "query_and_source_ids_only",
    }


def payload_is_private_locator_free(payload: dict[str, Any]) -> bool:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return not any(pattern.search(text) for pattern in FORBIDDEN_TOOL_OUTPUT_PATTERNS)


def load_agents_sdk() -> tuple[Any | None, str | None]:
    try:
        return importlib.import_module("agents"), None
    except ImportError as exc:
        return None, str(exc)


def build_agent_tool_contract(agents: Any) -> dict[str, Any]:
    agent_cls = agents.Agent
    function_tool: Callable[..., Any] = agents.function_tool

    @function_tool
    def aippocampus_lookup_memory(query: str) -> str:
        """Return sanitized AIppocampus memory cues by query."""
        payload = build_sanitized_lookup_payload(query)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    agent = agent_cls(
        name="AIppocampus local memory smoke",
        instructions=(
            "Use AIppocampus source ids only. Never request private registry "
            "paths, raw transcripts, credentials, or local machine details."
        ),
        tools=[aippocampus_lookup_memory],
    )
    tool = agent.tools[0]
    schema = tool.params_json_schema
    return {
        "agent_name": agent.name,
        "tool_name": tool.name,
        "tool_description": tool.description,
        "strict_json_schema": bool(tool.strict_json_schema),
        "schema": schema,
        "schema_properties": sorted(schema.get("properties", {}).keys()),
        "additional_properties": schema.get("additionalProperties"),
        "needs_approval": bool(getattr(tool, "needs_approval", False)),
    }


def run_smoke() -> dict[str, Any]:
    agents, import_error = load_agents_sdk()
    if agents is None:
        return {
            "ok": False,
            "status": "missing_openai_agents_dependency",
            "install_command": INSTALL_COMMAND,
            "error": import_error,
            "claim_boundary": "no OpenAI Agents SDK integration claim without optional smoke",
        }

    tool_contract = build_agent_tool_contract(agents)
    sample_payload = build_sanitized_lookup_payload("Find the public demo source id.")
    checks = {
        "sdk_imported": True,
        "agent_holds_one_tool": tool_contract["tool_name"] == "aippocampus_lookup_memory",
        "query_schema_present": "query" in tool_contract["schema_properties"],
        "strict_schema": tool_contract["strict_json_schema"] is True,
        "extra_args_rejected_by_schema": tool_contract["additional_properties"] is False,
        "sample_payload_private_locator_free": payload_is_private_locator_free(sample_payload),
        "no_runner_or_model_call": True,
    }
    ok = all(checks.values())
    return {
        "ok": ok,
        "status": "passed" if ok else "failed",
        "checked_at": SMOKE_CHECKED_AT,
        "sdk_version": getattr(agents, "__version__", "unknown"),
        "official_docs": OFFICIAL_DOCS,
        "integration_surface": "Agent plus local function_tool schema wiring only",
        "tool_contract": tool_contract,
        "sample_payload": sample_payload,
        "checks": checks,
        "cannot_claim": [
            "official OpenAI partner support",
            "hosted Runner execution",
            "ambient automatic recall inside OpenAI Agents SDK apps",
            "private registry path or raw transcript forwarding",
            "credential handling or production OpenAI API configuration",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_smoke()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"OpenAI Agents SDK smoke: {result['status']}")
        if not result["ok"]:
            print(f"Install with: {INSTALL_COMMAND}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
