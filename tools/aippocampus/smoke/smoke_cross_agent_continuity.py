#!/usr/bin/env python3
"""Deterministic synthetic Codex/Claude cross-agent continuity smoke."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from _paths import repo_root
except ImportError:  # pragma: no cover - direct script fallback
    repo_root = None  # type: ignore[assignment]


def _bootstrap_paths() -> Path:
    root = repo_root() if repo_root else Path(__file__).resolve().parents[3]
    scripts = root / "skills" / "aippocampus" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return root


_bootstrap_paths()

from aippocampus_runtime.mcp import server as mcp  # noqa: E402
from aippocampus_runtime.mcp.compact_profile import mcp_tool_result_payload  # noqa: E402
from aippocampus_runtime.registry import api as registry  # noqa: E402
from conversation_sources import (  # noqa: E402
    ClaudeCodeConversationProvider,
    CodexConversationProvider,
)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_codex_rollout(path: Path, *, session_id: str, cwd: Path, marker: str) -> None:
    rows = [
        {
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "timestamp": "2026-05-30T05:00:00Z",
                "cwd": str(cwd),
                "originator": "Codex Desktop",
                "source": "codex",
                "thread_source": "codex",
            },
        },
        {
            "type": "event_msg",
            "timestamp": "2026-05-30T05:00:00Z",
            "payload": {
                "type": "user_message",
                "message": f"Remember the Codex-origin source-backed marker {marker}.",
            },
        },
        {
            "type": "event_msg",
            "timestamp": "2026-05-30T05:00:01Z",
            "payload": {
                "type": "agent_message",
                "phase": "final_answer",
                "message": f"Codex final answer keeps {marker} retrievable through clean source.",
            },
        },
    ]
    _write_jsonl(path, rows)


def write_claude_transcript(path: Path, *, session_id: str, cwd: Path, marker: str) -> None:
    rows = [
        {
            "type": "user",
            "sessionId": session_id,
            "timestamp": "2026-05-30T05:01:00Z",
            "cwd": str(cwd),
            "uuid": "claude-user-1",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Remember the Claude-origin source-backed marker {marker}.",
                    }
                ],
            },
        },
        {
            "type": "assistant",
            "sessionId": session_id,
            "timestamp": "2026-05-30T05:01:01Z",
            "cwd": str(cwd),
            "uuid": "claude-assistant-1",
            "parentUuid": "claude-user-1",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": f"Claude final answer keeps {marker} retrievable through clean source.",
                    }
                ],
            },
        },
    ]
    _write_jsonl(path, rows)


def mcp_search(cwd: Path, clean_source_dir: Path, query: str) -> dict[str, Any]:
    response = mcp.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search_memory",
                "arguments": {
                    "cwd": str(cwd),
                    "clean_source_dir": str(clean_source_dir),
                    "query": query,
                    "max": 4,
                    "detail": "full",
                    "include_source_snippets": True,
                },
            },
        }
    )
    return mcp_tool_result_payload(response["result"])


def mcp_list_threads(registry_dir: Path) -> dict[str, Any]:
    response = mcp.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "list_threads",
                "arguments": {
                    "registry_dir": str(registry_dir),
                    "max": 10,
                },
            },
        }
    )
    return mcp_tool_result_payload(response["result"])


def source_refs_with_prefix(payload: dict[str, Any], prefix: str) -> list[str]:
    refs = [
        str(match.get("source_ref"))
        for match in payload.get("matches", [])
        if match.get("source_ref")
    ]
    return [ref for ref in refs if ref.startswith(prefix)]


def payload_contains_private_root(encoded_payload: str, private_root: Path) -> bool:
    variants = {
        str(private_root),
        str(private_root).replace("\\", "/"),
        json.dumps(str(private_root), ensure_ascii=False).strip('"'),
        json.dumps(str(private_root).replace("\\", "/"), ensure_ascii=False).strip('"'),
    }
    return any(variant and variant in encoded_payload for variant in variants)


def run_smoke() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cwd = root / "project"
        cwd.mkdir()
        registry_dir = root / "registry"
        codex_home = root / "codex-home"
        claude_home = root / "claude-home"
        codex_rollout = codex_home / "sessions" / "2026" / "05" / "30" / "rollout-codex.jsonl"
        claude_transcript = claude_home / "projects" / "synthetic" / "session-claude.jsonl"
        codex_marker = "codex-origin-marker-112-120"
        claude_marker = "claude-origin-marker-112-120"

        write_codex_rollout(
            codex_rollout,
            session_id="codex-cross-agent",
            cwd=cwd,
            marker=codex_marker,
        )
        write_claude_transcript(
            claude_transcript,
            session_id="claude-cross-agent",
            cwd=cwd,
            marker=claude_marker,
        )

        codex_registered = registry.register_rollout_thread(
            codex_rollout,
            cwd=cwd,
            project="Synthetic Cross-Agent",
            tags=["codex", "cross-agent"],
            registry_dir=registry_dir,
            provider=CodexConversationProvider(codex_home),
        )
        claude_registered = registry.register_rollout_thread(
            claude_transcript,
            cwd=cwd,
            project="Synthetic Cross-Agent",
            tags=["claude-code", "cross-agent"],
            registry_dir=registry_dir,
            provider=ClaudeCodeConversationProvider(claude_home),
        )

        codex_clean_dir = Path(codex_registered["entry"]["paths"]["clean_source_dir"])
        claude_clean_dir = Path(claude_registered["entry"]["paths"]["clean_source_dir"])
        codex_payload = mcp_search(cwd, codex_clean_dir, codex_marker)
        claude_payload = mcp_search(cwd, claude_clean_dir, claude_marker)
        list_payload = mcp_list_threads(registry_dir)

        codex_refs = source_refs_with_prefix(codex_payload, "codex:session:")
        claude_refs = source_refs_with_prefix(claude_payload, "claude-code:session:")
        encoded = json.dumps(
            {
                "codex": codex_payload,
                "claude": claude_payload,
                "threads": list_payload,
            },
            ensure_ascii=False,
        )
        private_path_free = not payload_contains_private_root(encoded, root)
        ok = (
            bool(codex_payload.get("matches"))
            and bool(claude_payload.get("matches"))
            and codex_marker in encoded
            and claude_marker in encoded
            and bool(codex_refs)
            and bool(claude_refs)
            and private_path_free
            and "innate memory" not in encoded.casefold()
            and list_payload.get("count") == 2
        )
        return {
            "ok": ok,
            "status": "passed" if ok else "failed",
            "proof": {
                "retrieval_surface": "registry clean-source + MCP search_memory",
                "registry_surface": "MCP list_threads",
                "registry_thread_count": list_payload.get("count"),
                "registry_redacted": list_payload.get("registry") == "<local-path-redacted>",
                "private_path_free_payload": private_path_free,
                "false_claim_guard": "The smoke checks source-backed retrieval only; no model-native recall claim is made.",
                "directions": [
                    {
                        "origin_provider": "codex",
                        "consumer_host_label": "claude-code",
                        "source_thread_key": codex_registered["entry"].get("thread_key"),
                        "match_count": len(codex_payload.get("matches") or []),
                        "redacted_source": codex_payload.get("source"),
                        "source_refs": codex_refs,
                    },
                    {
                        "origin_provider": "claude-code",
                        "consumer_host_label": "codex",
                        "source_thread_key": claude_registered["entry"].get("thread_key"),
                        "match_count": len(claude_payload.get("matches") or []),
                        "redacted_source": claude_payload.get("source"),
                        "source_refs": claude_refs,
                    },
                ],
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = run_smoke()
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"cross-agent continuity: {result['status']}")
        for direction in result["proof"]["directions"]:
            print(
                f"{direction['origin_provider']} -> {direction['consumer_host_label']}: "
                f"{direction['match_count']} matches"
            )
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
