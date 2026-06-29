"""Runtime-generation checks for long-lived MCP stdio transports."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

RUNTIME_GENERATION_MARKER = ".aippocampus-runtime-generation.json"


def package_root_for_runtime_file(path: Path | None = None) -> Path:
    """Return the plugin/source root that contains the installable skill.

    For the installed plugin this resolves to the plugin package root:
    `<plugin>/skills/aippocampus/scripts/aippocampus_runtime/...`. In the source
    checkout it resolves to the repository root. The marker is intentionally
    absent from ordinary source checkouts, so local development does not reload
    on every file edit.
    """

    runtime_file = (path or Path(__file__)).resolve()
    try:
        return runtime_file.parents[5]
    except IndexError:
        return runtime_file.parent


def marker_path(path: Path | None = None) -> Path:
    return package_root_for_runtime_file(path) / RUNTIME_GENERATION_MARKER


def read_runtime_generation(path: Path | None = None) -> str | None:
    marker = marker_path(path)
    if not marker.exists():
        return None
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    generation = payload.get("generation")
    return str(generation) if generation else None


STARTUP_RUNTIME_GENERATION = read_runtime_generation()


def runtime_generation_changed() -> bool:
    """Return whether the installed runtime changed after this process started."""

    current = read_runtime_generation()
    if STARTUP_RUNTIME_GENERATION is None:
        # Editable/source-checkout MCP launches used to start without a marker,
        # so they could never notice a later plugin install. Treat a newly
        # written marker as a generation change; the proxy/re-exec path will
        # then switch to the fresh runtime before answering the consumed request.
        return current is not None
    return bool(current and current != STARTUP_RUNTIME_GENERATION)


def current_reexec_argv() -> list[str]:
    entrypoint = Path(sys.argv[0]) if sys.argv else None
    if entrypoint is not None and entrypoint.suffix.casefold() == ".py" and entrypoint.exists():
        return [sys.executable, *sys.argv]
    return [sys.executable, "-m", "aippocampus_runtime.cli.facade", "mcp"]


def proxy_request_through_fresh_runtime(
    raw_message: str,
    *,
    timeout_seconds: float = 30.0,
) -> subprocess.CompletedProcess[str]:
    """Run the current MCP entrypoint once so a stale process can relay a reply.

    The stale server has already consumed the host's JSON-RPC request from
    stdin. Re-execing immediately would drop that request and make the host wait
    for a response. Instead, relay the single request through a freshly-started
    copy of the same entrypoint, return its stdout, then let the parent re-exec
    itself for subsequent calls.
    """

    request = raw_message.rstrip("\r\n") + "\n"
    return subprocess.run(
        current_reexec_argv(),
        input=request,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
    )


def reexec_current_process() -> None:
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(sys.executable, current_reexec_argv())


def hot_reload_state() -> dict[str, Any]:
    current = read_runtime_generation()
    return {
        "kind": "aippocampus_mcp_runtime_generation",
        "startup_generation_known": STARTUP_RUNTIME_GENERATION is not None,
        "current_generation_known": current is not None,
        "changed": runtime_generation_changed(),
        "claim_boundary": "runtime generation is transport freshness evidence, not source evidence",
    }


__all__ = [
    "RUNTIME_GENERATION_MARKER",
    "STARTUP_RUNTIME_GENERATION",
    "current_reexec_argv",
    "hot_reload_state",
    "marker_path",
    "package_root_for_runtime_file",
    "proxy_request_through_fresh_runtime",
    "read_runtime_generation",
    "reexec_current_process",
    "runtime_generation_changed",
]
