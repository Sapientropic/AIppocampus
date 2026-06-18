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
    if payload.get("ok") is False:
        return 2
    return default
