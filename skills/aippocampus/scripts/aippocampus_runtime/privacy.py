"""Public-safe projections for local AIppocampus payloads."""

from __future__ import annotations

import re

LOCAL_PATH_REDACTION = "<local-path-redacted>"
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


def redact_private_paths(value):
    """Return a public projection that keeps identity but removes local locators."""

    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_private_path_key(key_text, item) and item:
                redacted[key] = LOCAL_PATH_REDACTION
            else:
                redacted[key] = redact_private_paths(item)
        return redacted
    if isinstance(value, list):
        return [redact_private_paths(item) for item in value]
    return value


def _is_private_path_key(key: str, value=None) -> bool:
    normalized = key.casefold()
    if normalized == "source":
        return isinstance(value, str) and _looks_like_path(value)
    return (
        normalized in PRIVATE_PATH_KEYS
        or normalized.endswith("_path")
        or normalized.endswith("_dir")
        or normalized.endswith("_file")
    )


def _looks_like_path(value: str) -> bool:
    text = str(value)
    return (
        "\\" in text
        or "/" in text
        or bool(re.match(r"^[A-Za-z]:", text))
        or text.endswith((".jsonl", ".json", ".sqlite", ".md"))
    )
