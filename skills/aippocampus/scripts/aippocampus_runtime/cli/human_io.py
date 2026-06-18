"""Small shared output helpers for public CLI entrypoints."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import Any, TextIO

from aippocampus_runtime.cli.errors import cli_exit_code_for_error_code
from aippocampus_runtime.public_output import emit_public_text
from aippocampus_runtime.safety import sanitize_external_model_payload


def emit_json(payload: Mapping[str, Any], *, stream: TextIO | None = None) -> None:
    safe_payload = sanitize_external_model_payload(dict(payload))
    emit_public_text(json.dumps(safe_payload, ensure_ascii=False, indent=2), stream=stream or sys.stdout)


def exit_code_for_payload(payload: Mapping[str, Any], *, default: int = 0) -> int:
    error = payload.get("error")
    if isinstance(error, Mapping):
        return cli_exit_code_for_error_code(str(error.get("code") or "runtime_error"))
    issues = payload.get("issues")
    if isinstance(issues, list):
        for issue in issues:
            if isinstance(issue, Mapping) and issue.get("code"):
                return cli_exit_code_for_error_code(str(issue.get("code")))
    status = str(payload.get("status") or "")
    if status in {
        "blocked_dirty_worktree",
        "cannot_verify",
        "missing_manifest",
        "needs_input",
        "no_routes",
    }:
        return cli_exit_code_for_error_code(status)
    if payload.get("ok") is False:
        # A structured report can legitimately be "not OK" because the host
        # needs setup, a cache has multiple candidates, or an optional surface
        # needs attention. Keep those as operational failures (1). Usage,
        # validation, and missing-prerequisite exits stay 2 through the stable
        # error/status branches above so shell callers can distinguish a bad
        # invocation from an actionable diagnostic card.
        return 1
    return default
