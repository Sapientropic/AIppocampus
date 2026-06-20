"""Public JSON projection helpers for active recall CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime.artifacts.publish import ArtifactLeaseBusyError
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values


def public_json_payload(payload: dict[str, Any], *, include_private_paths: bool = False) -> dict[str, Any]:
    if include_private_paths:
        result = dict(payload)
        result["raw_source_path_hidden"] = False
        return result
    result = redact_sensitive_values(redact_private_paths(payload))
    if isinstance(result, dict):
        result["raw_source_path_hidden"] = True
        result.setdefault(
            "privacy_boundary",
            {
                "local_paths_redacted": True,
                "include_private_paths_flag": "--include-private-paths",
            },
        )
        return result
    return {"ok": False, "status": "redaction_failed", "raw_source_path_hidden": True}


def index_lease_busy_payload(exc: ArtifactLeaseBusyError, *, prompt: str, cwd: Path) -> dict[str, Any]:
    del cwd
    return {
        "ok": False,
        "status": "index_lease_busy",
        "prompt": prompt,
        "searched": False,
        "search": None,
        "fallback_used": "none",
        "retry_after_ms": 500,
        "next_step_hint": "Retry shortly, or continue without foreground recall if the task is not blocked.",
        "error": {
            "code": "index_lease_busy",
            "retryable": True,
            "message": "Another local agent is publishing the AIppocampus search index.",
            "lease": str(exc),
        },
    }


def emit_index_lease_busy(
    exc: ArtifactLeaseBusyError,
    *,
    prompt: str,
    cwd: Path,
    json_output: bool,
    include_private_paths: bool,
) -> int:
    busy = index_lease_busy_payload(exc, prompt=prompt, cwd=cwd)
    if json_output:
        print(
            json.dumps(
                public_json_payload(busy, include_private_paths=include_private_paths),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print("index_lease_busy: retry shortly", file=sys.stderr)
    return 2
