"""Clean-source scanning for last-recall scoped exact search."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.source.clean_source import SCOPE_LABEL_ORDER
from aippocampus_runtime.source.query_match_gate import match_query_profile, query_match_gate
from aippocampus_runtime.source.registry_search_evidence import query_anchor_rank
from aippocampus_runtime.source.search_core import iter_clean_messages, score_message
from aippocampus_runtime.source.search_terms import search_query_terms
from aippocampus_runtime.source.semantic_scope_labels import (
    load_semantic_scope_labels,
    merged_scope_labels,
    semantic_labels_for_message,
)

PROCESS_NOISE_PREFIXES = (
    ("<subagent_notification>", "process_notification"),
    ("<tool", "tool_process"),
)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _process_noise_reason(text: str) -> str:
    snippet = str(text or "").lstrip().casefold()
    for prefix, reason in PROCESS_NOISE_PREFIXES:
        if snippet.startswith(prefix):
            return reason
    return ""


def search_clean_source_dir_for_last_recall(
    source_dir: Path,
    patterns: list[str],
    *,
    limit: int,
    snippet_chars: int,
) -> dict[str, Any]:
    semantic_sidecar = load_semantic_scope_labels(source_dir)
    terms = search_query_terms(patterns)
    query_text = " ".join(str(pattern) for pattern in patterns).strip()
    query_gate = query_match_gate(query_text)
    known_scope_labels = set(SCOPE_LABEL_ORDER)
    matches: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for message in iter_clean_messages(source_dir / "messages.jsonl"):
        message_text = str(message.get("text") or "")
        base_scope_labels = [
            str(label) for label in message.get("scope_labels", []) if isinstance(label, str)
        ]
        semantic_scope_labels = semantic_labels_for_message(message, semantic_sidecar)
        message_scope_labels = merged_scope_labels(base_scope_labels, semantic_scope_labels)
        for label in message_scope_labels:
            if label not in known_scope_labels:
                warnings.append(
                    {
                        "code": "unknown_scope_label",
                        "scope_label": label,
                        "message": f"Unknown scope label: {label}",
                    }
                )
        score = score_message(message, terms)
        if score <= 0:
            continue
        query_profile = match_query_profile(
            query_text=query_text,
            gate=query_gate,
            haystack=message_text,
        )
        match = {
            "id": message.get("message_id") or message.get("id"),
            "message_id": message.get("message_id") or message.get("id"),
            "turn_id": message.get("turn_id"),
            "source_line": message.get("source_line"),
            "role": message.get("role"),
            "phase": message.get("phase") or "",
            "turn_index": message.get("turn_index"),
            "is_final": bool(message.get("is_final")),
            "scope_labels": message_scope_labels,
            "semantic_scope_labels": semantic_scope_labels,
            "score": round(score, 3),
            "snippet": compact_text(message_text, snippet_chars) if snippet_chars else "",
            "snippet_omitted": snippet_chars == 0,
            "query_match_profile": query_profile,
        }
        if noise_reason := _process_noise_reason(message_text):
            match["search_noise"] = True
            match["noise_reason"] = noise_reason
        matches.append(match)
    matches.sort(
        key=lambda item: (
            1 if item.get("search_noise") else 0,
            -query_anchor_rank(item)[0],
            -query_anchor_rank(item)[1],
            -query_anchor_rank(item)[2],
            -_as_float(item.get("score")),
            _as_int(item.get("source_line")),
        )
    )
    return {"matches": matches[:limit], "warnings": warnings}


__all__ = ["search_clean_source_dir_for_last_recall"]
