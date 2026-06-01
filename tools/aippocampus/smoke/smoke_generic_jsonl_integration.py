#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Generic JSONL non-native runtime integration smoke."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from _paths import SKILL_SCRIPTS, ensure_paths
except ImportError:  # pragma: no cover - direct script fallback
    repo_root = Path(__file__).resolve().parents[3]
    SKILL_SCRIPTS = repo_root / "skills" / "aippocampus" / "scripts"

    def ensure_paths() -> None:
        if str(SKILL_SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SKILL_SCRIPTS))


ensure_paths()

import aippocampus_mcp_server as mcp  # noqa: E402


MARKER = "generic-jsonl-internal-agent-marker-399"


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_internal_agent_transcript(path: Path, *, cwd: Path, marker: str = MARKER) -> None:
    rows = [
        {
            "session_id": "internal-agent-runtime-demo",
            "timestamp": "2026-06-02T02:00:00Z",
            "cwd": str(cwd),
            "role": "user",
            "turn_id": "turn-1",
            "text": (
                "An internal planning agent exported this visible note for "
                f"AIppocampus: {marker}."
            ),
            "provider_metadata": {
                "provider": "internal-agent-demo",
                "runtime": "generic-jsonl-smoke",
            },
        },
        {
            "session_id": "internal-agent-runtime-demo",
            "timestamp": "2026-06-02T02:00:01Z",
            "cwd": str(cwd),
            "role": "assistant",
            "turn_id": "turn-1",
            "phase": "final_answer",
            "text": (
                "The internal runtime keeps the exported marker "
                f"{marker} retrievable after explicit local import."
            ),
            "provider_metadata": {
                "provider": "internal-agent-demo",
                "runtime": "generic-jsonl-smoke",
            },
        },
    ]
    _write_jsonl(path, rows)


def _run_cli(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(SKILL_SCRIPTS / "aippocampus_cli.py"), *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = None
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "json": payload,
    }


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
                },
            },
        }
    )
    text = response["result"]["content"][0]["text"]
    return json.loads(text)


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
    text = response["result"]["content"][0]["text"]
    return json.loads(text)


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


def _public_cli_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    return {
        "ok": payload.get("ok"),
        "dry_run": payload.get("dry_run"),
        "source_provider": payload.get("source_provider"),
        "thread_key": payload.get("thread_key") or entry.get("thread_key"),
        "message_count": payload.get("message_count") or entry.get("message_count"),
        "turn_count": payload.get("turn_count") or entry.get("clean_turn_count"),
        "already_registered": payload.get("already_registered"),
    }


def run_smoke() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cwd = root / "project"
        cwd.mkdir()
        registry_dir = root / "registry"
        transcript = root / "exports" / "internal-agent-session.jsonl"
        write_internal_agent_transcript(transcript, cwd=cwd)

        base_args = [
            "import",
            "conversation",
            "--registry-dir",
            str(registry_dir),
            "--format",
            "generic-jsonl",
            "--input",
            str(transcript),
            "--project",
            "Internal Agent Demo",
            "--tag",
            "ecosystem",
            "--json",
        ]
        dry_run = _run_cli([*base_args, "--dry-run"])
        dry_run_created_registry = (registry_dir / "threads.json").exists()
        imported = _run_cli(base_args)

        imported_json = imported.get("json") if isinstance(imported.get("json"), dict) else {}
        entry = imported_json.get("entry") if isinstance(imported_json.get("entry"), dict) else {}
        clean_source_dir = Path(entry.get("paths", {}).get("clean_source_dir", ""))
        search_payload = (
            mcp_search(cwd, clean_source_dir, MARKER)
            if imported.get("ok") and clean_source_dir.exists()
            else {}
        )
        list_payload = mcp_list_threads(registry_dir) if imported.get("ok") else {}
        source_refs = source_refs_with_prefix(
            search_payload,
            "generic-jsonl:session:internal-agent-runtime-demo#L",
        )
        public_encoded = json.dumps(
            {"search": search_payload, "threads": list_payload},
            ensure_ascii=False,
        )
        private_path_free = not payload_contains_private_root(public_encoded, root)
        dry_run_json = dry_run.get("json") if isinstance(dry_run.get("json"), dict) else {}

        ok = (
            dry_run.get("ok")
            and imported.get("ok")
            and not dry_run_created_registry
            and dry_run_json.get("dry_run") is True
            and imported_json.get("dry_run") is False
            and imported_json.get("source_provider") == "generic-jsonl"
            and entry.get("source_provider") == "generic-jsonl"
            and entry.get("thread_key") == "generic-jsonl:session:internal-agent-runtime-demo"
            and bool(search_payload.get("matches"))
            and MARKER in public_encoded
            and bool(source_refs)
            and list_payload.get("count") == 1
            and list_payload.get("registry") == "<local-path-redacted>"
            and private_path_free
            and "innate memory" not in public_encoded.casefold()
        )
        return {
            "ok": bool(ok),
            "status": "passed" if ok else "failed",
            "proof": {
                "integration_surface": (
                    "generic JSONL import -> registry clean source -> MCP search_memory"
                ),
                "non_native_host_label": "internal-agent-demo",
                "verified_levels": [
                    "data import/export",
                    "agent read tools through MCP after explicit import",
                ],
                "not_claimed": [
                    "native framework adapter",
                    "automatic ambient recall",
                    "official third-party host support",
                    "hosted memory service",
                ],
                "required_fields": ["session_id", "role", "text"],
                "dry_run": _public_cli_summary(dry_run_json),
                "import": _public_cli_summary(imported_json),
                "dry_run_created_registry": dry_run_created_registry,
                "mcp": {
                    "match_count": len(search_payload.get("matches") or []),
                    "source_refs": source_refs,
                    "registry_thread_count": list_payload.get("count"),
                    "registry_redacted": list_payload.get("registry")
                    == "<local-path-redacted>",
                    "private_path_free_payload": private_path_free,
                    "false_claim_guard": (
                        "This smoke checks source-backed retrieval only; it does "
                        "not claim model-native or automatic recall."
                    ),
                },
            },
            "debug": {
                "dry_run_returncode": dry_run.get("returncode"),
                "import_returncode": imported.get("returncode"),
                "dry_run_stderr": dry_run.get("stderr"),
                "import_stderr": imported.get("stderr"),
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
        print(f"generic JSONL ecosystem integration: {result['status']}")
        proof = result["proof"]
        print(f"host label: {proof['non_native_host_label']}")
        print(f"MCP matches: {proof['mcp']['match_count']}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
