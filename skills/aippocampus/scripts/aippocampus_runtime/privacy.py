"""Public-safe projections for local AIppocampus payloads."""

from __future__ import annotations

import re

LOCAL_PATH_REDACTION = "<local-path-redacted>"
SENSITIVE_VALUE_REDACTION = "<sensitive-value-redacted>"
PRIVATE_PATH_KEYS = {
    "anchor_file",
    "anchors",
    "clean_source_dir",
    "clean_source_messages_jsonl",
    "clean_source_turns_jsonl",
    "cwd",
    "dashboard_html",
    "dashboard_note",
    "graph_json",
    "graphify_corpus",
    "index_dir",
    "manifest",
    "messages_jsonl",
    "object_storage_script",
    "path",
    "registry",
    "registry_json",
    "registry_markdown",
    "registry_thread_store",
    "rollout",
    "script",
    "sqlite",
    "source_rollout",
    "source_transcript",
    "sync_dir",
    "vault",
    "workspace",
}

PUBLIC_NON_PATH_KEYS = {
    # MCP recall navigation uses "path" in the workflow sense: which tool to
    # call next to reopen source. It is not a local filesystem locator, and
    # redacting it would hide the agent-facing progressive-recall contract.
    "source_reopen_path",
}

SENSITIVE_EXACT_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "client_secret",
    "credential",
    "credentials",
    "password",
    "passwd",
    "private_key",
    "refresh_token",
    "secret",
    "secret_access_key",
    "token",
}

SENSITIVE_KEY_SUFFIXES = (
    "_access_token",
    "_api_key",
    "_auth_token",
    "_client_secret",
    "_password",
    "_private_key",
    "_refresh_token",
    "_secret_access_key",
    "_secret_key",
)

SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|access[_-]?token|auth[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|secret|password|passwd|authorization)\b\s*[:=]\s*"
    r"([^\s,;\"']+)"
)
BEARER_VALUE_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{8,}")
OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9._-]{8,}\b")
LOCAL_PATH_TEXT_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:\\|/(?:Users|home|tmp|var|private|Volumes)/)[^\s,;\"')\]]+)"
)


def redact_private_paths(value):
    """Return a public projection that keeps identity but removes local locators."""

    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_private_path_key(key_text, item) and item:
                redacted[key] = _redact_private_path_value(item)
            else:
                redacted[key] = redact_private_paths(item)
        return redacted
    if isinstance(value, list):
        return [redact_private_paths(item) for item in value]
    if isinstance(value, str):
        return _redact_private_path_text(value)
    return value


def redact_sensitive_values(value):
    """Return a public projection that removes credential-shaped values.

    This intentionally does not treat every field containing "token" as secret:
    public diagnostics often need token counts or env-var names. Redact exact
    auth-bearing keys and assignment-shaped strings at the final public-output
    boundary instead of weakening useful observability fields upstream.
    """

    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_value_key(key_text) and item not in (None, "", False):
                redacted[key] = SENSITIVE_VALUE_REDACTION
            else:
                redacted[key] = redact_sensitive_values(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_values(item) for item in value]
    if isinstance(value, str):
        return _redact_sensitive_text(value)
    return value


def _is_private_path_key(key: str, value=None) -> bool:
    normalized = key.casefold()
    if normalized in PUBLIC_NON_PATH_KEYS:
        return False
    if normalized == "source":
        return isinstance(value, str) and _looks_like_path(value)
    if normalized in PRIVATE_PATH_KEYS:
        return True
    if normalized.endswith(("_path", "_dir", "_file")):
        return _value_looks_like_path(value)
    return False


def _redact_private_path_value(value):
    # Path-bearing containers often also carry public metadata such as byte
    # counts. Keep the shape and redact only the locator leaves so renderers
    # do not lose non-private health context.
    if isinstance(value, dict):
        return redact_private_paths(value)
    if isinstance(value, list):
        return [_redact_private_path_value(item) for item in value]
    return LOCAL_PATH_REDACTION


def _is_sensitive_value_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return normalized in SENSITIVE_EXACT_KEYS or any(
        normalized.endswith(suffix) for suffix in SENSITIVE_KEY_SUFFIXES
    )


def _redact_sensitive_text(value: str) -> str:
    text = str(value)
    text = SENSITIVE_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}={SENSITIVE_VALUE_REDACTION}",
        text,
    )
    text = BEARER_VALUE_RE.sub(f"Bearer {SENSITIVE_VALUE_REDACTION}", text)
    return OPENAI_KEY_RE.sub(SENSITIVE_VALUE_REDACTION, text)


def _redact_private_path_text(value: str) -> str:
    return LOCAL_PATH_TEXT_RE.sub(LOCAL_PATH_REDACTION, str(value))


def _looks_like_path(value: str) -> bool:
    text = str(value)
    return (
        "\\" in text
        or "/" in text
        or bool(re.match(r"^[A-Za-z]:", text))
        or text.endswith((".jsonl", ".json", ".sqlite", ".md"))
    )


def _value_looks_like_path(value) -> bool:
    if isinstance(value, str):
        return _looks_like_path(value)
    if isinstance(value, dict):
        return any(_value_looks_like_path(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_value_looks_like_path(item) for item in value)
    return False
