"""Operator JSON output helpers for the local update facade."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime.public_output import emit_public_text

SECRET_ASSIGNMENT_RE = re.compile(
    r"\b(api[_-]?key|secret|token|password|passwd|cookie|authorization)\b\s*[:=]\s*"
    r"(\"[^\"]*\"|'[^']*'|(?!(?:<redacted:))[^\s,;&]+)",
    re.IGNORECASE,
)
SENSITIVE_EXACT_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "client_secret",
    "cookie",
    "id_token",
    "password",
    "passphrase",
    "passwd",
    "private_key",
    "refresh_token",
    "secret",
    "token",
}
SENSITIVE_SUFFIXES = (
    "_api_key",
    "_apikey",
    "_authorization",
    "_cookie",
    "_password",
    "_passphrase",
    "_passwd",
    "_private_key",
    "_secret",
    "_token",
)
SAFE_ENV_SUFFIXES = ("_env", "_env_name", "_env_var")
TOKEN_METRIC_KEYS = {
    "completion_tokens",
    "estimated_tokens",
    "input_tokens",
    "max_tokens",
    "output_tokens",
    "prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens",
    "prompt_tokens",
    "total_tokens",
}


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return "<redacted:local-path>"
    return f"<non_json:{type(value).__name__}>"


def _normalized_key(key: Any) -> str:
    return str(key or "").replace("-", "_").casefold()


def _sensitive_key(key: Any) -> bool:
    normalized = _normalized_key(key)
    if not normalized or normalized in TOKEN_METRIC_KEYS or normalized.endswith(SAFE_ENV_SUFFIXES):
        return False
    return normalized in SENSITIVE_EXACT_KEYS or normalized.endswith(SENSITIVE_SUFFIXES)


def redact_sensitive_json_fields(value: Any, *, parent_key: Any = None) -> Any:
    """Redact credential-like values without stripping operator recovery paths."""

    if _sensitive_key(parent_key):
        return "<redacted:sensitive-json-field>"
    if isinstance(value, dict):
        return {key: redact_sensitive_json_fields(item, parent_key=key) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_json_fields(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive_json_fields(item) for item in value]
    if isinstance(value, str):
        return SECRET_ASSIGNMENT_RE.sub(r"\1=<redacted:secret>", value)
    return value


def emit_operator_json(payload: Any) -> None:
    safe_payload = redact_sensitive_json_fields(payload)
    sys.stdout.write(json.dumps(safe_payload, ensure_ascii=False, indent=2, default=_json_default))
    sys.stdout.write("\n")


def update_recovery_payload(
    *,
    code: str,
    message: str,
    next_command: str,
    schema_version: int = 1,
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "kind": "aippocampus_update_recovery",
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "next_command": next_command,
        },
        "next_actions": [
            {
                "label": "read update status",
                "command": "aippocampus update status --json",
                "mutates": False,
            },
            {
                "label": "preview update plan",
                "command": "aippocampus update plan --json",
                "mutates": False,
            },
        ],
        "safety": {
            "no_write_happened": True,
            "apply_requires_surface": True,
            "all_local_is_repair_shortcut_not_default": True,
        },
    }


def render_update_recovery(payload: dict[str, Any]) -> str:
    error = payload.get("error") or {}
    lines = [
        "AIppocampus update recovery card",
        f"reason: {error.get('code')}",
        "No write happened.",
        f"Try: {error.get('next_command')}",
        "choose a surface before apply; --all-local is a broad repair/bootstrap shortcut",
    ]
    return "\n".join(lines) + "\n"


def emit_update_recovery(payload: dict[str, Any], *, json_output: bool) -> int:
    if json_output:
        emit_operator_json(payload)
    else:
        emit_public_text(render_update_recovery(payload), end="", stream=sys.stderr)
    return 2
