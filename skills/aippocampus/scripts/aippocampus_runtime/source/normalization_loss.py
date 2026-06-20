"""Redacted provider-normalization loss accounting.

Provider parsers are allowed to fail open on damaged host JSONL, but silent
source loss is worse than an honest degraded readiness card. These counters
must stay content-free: counts and reason codes only, never raw transcript
rows, local paths, or provider payloads.
"""

from __future__ import annotations

from typing import Any, Mapping

PROVIDER_NORMALIZATION_COUNT_KEYS = (
    "invalid_json_line_count",
    "non_object_line_count",
    "unsupported_event_count",
    "role_policy_drop_count",
    "empty_text_policy_drop_count",
    "injected_instruction_policy_drop_count",
    "duplicate_message_drop_count",
    "tool_payload_policy_drop_count",
    "orphan_assistant_drop_count",
    "system_role_policy_drop_count",
)


def empty_provider_normalization_loss(provider: str) -> dict[str, Any]:
    return {
        "scope": "provider_normalization",
        "provider": provider,
        "raw_private_text_emitted": False,
        "raw_provider_payload_emitted": False,
        "local_paths_emitted": False,
        "counts": {key: 0 for key in PROVIDER_NORMALIZATION_COUNT_KEYS},
        "warning_codes": [],
        "operator_next_step": {
            "inspect": "aippocampus health --detail full --json",
            "plan_rebuild": "aippocampus maintenance plan --json",
            "rebuild": "aippocampus maintenance apply --summary-json",
        },
    }


def count_provider_loss(report: dict[str, Any], key: str, amount: int = 1) -> None:
    if key not in PROVIDER_NORMALIZATION_COUNT_KEYS:
        raise ValueError(f"unknown provider normalization loss key: {key}")
    counts = report.setdefault("counts", {})
    counts[key] = int(counts.get(key) or 0) + amount


def finalize_provider_normalization_loss(report: Mapping[str, Any]) -> dict[str, Any]:
    counts = {
        key: int((report.get("counts") or {}).get(key) or 0)
        for key in PROVIDER_NORMALIZATION_COUNT_KEYS
    }
    parser_loss = counts["invalid_json_line_count"] + counts["non_object_line_count"]
    policy_loss = sum(
        counts[key]
        for key in PROVIDER_NORMALIZATION_COUNT_KEYS
        if key not in {"invalid_json_line_count", "non_object_line_count"}
    )
    warning_codes: list[str] = []
    if parser_loss:
        warning_codes.append("provider_parser_rows_dropped")
    if counts["unsupported_event_count"]:
        warning_codes.append("provider_unsupported_events_dropped")
    if policy_loss:
        warning_codes.append("provider_policy_rows_dropped")
    if parser_loss or policy_loss:
        warning_codes.append("provider_normalization_loss_detected")
    return {
        **dict(report),
        "counts": counts,
        "parser_loss_count": parser_loss,
        "policy_drop_count": policy_loss,
        "total_loss_count": parser_loss + policy_loss,
        "warning_codes": warning_codes,
    }

