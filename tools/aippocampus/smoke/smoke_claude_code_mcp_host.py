#!/usr/bin/env python3
"""Read-only Claude Code MCP host probe for AIppocampus."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from typing import Any


def run_claude_mcp_probe(server_name: str = "aippocampus") -> dict[str, Any]:
    claude = shutil.which("claude")
    if not claude:
        return {
            "ok": False,
            "status": "blocked_missing_claude_cli",
            "blocker": "The `claude` CLI is not available on PATH.",
            "commands": ["claude mcp list", f"claude mcp get {server_name}"],
        }

    list_proc = subprocess.run(
        [claude, "mcp", "list"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    get_proc = subprocess.run(
        [claude, "mcp", "get", server_name],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    list_text = sanitize_host_output((list_proc.stdout or list_proc.stderr or "").strip())
    get_text = sanitize_host_output((get_proc.stdout or get_proc.stderr or "").strip())
    return {
        "ok": list_proc.returncode == 0 and get_proc.returncode == 0,
        "status": "reachable" if list_proc.returncode == 0 and get_proc.returncode == 0 else "blocked_host_config",
        "server_name": server_name,
        "commands": ["claude mcp list", f"claude mcp get {server_name}"],
        "list_returncode": list_proc.returncode,
        "get_returncode": get_proc.returncode,
        "list_summary": list_text[:500],
        "get_summary": get_text[:500],
        "privacy": "This smoke reports command status only and does not print transcript contents.",
    }


def sanitize_host_output(text: str) -> str:
    text = re.sub(
        r"([?&][A-Za-z0-9_.-]*(?:key|token|secret)[A-Za-z0-9_.-]*=)[^&\s]+",
        r"\1<redacted>",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1<redacted>", text)
    text = re.sub(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s]+", "<local-path-redacted>", text)
    text = re.sub(
        r"(?<![A-Za-z0-9:])/(?:Users|home|private/tmp|tmp)/[^\s]+",
        "<local-path-redacted>",
        text,
    )
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-name", default="aippocampus")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = run_claude_mcp_probe(server_name=args.server_name)
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Claude Code MCP host: {result['status']}")
        if result.get("blocker"):
            print(f"blocker: {result['blocker']}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
