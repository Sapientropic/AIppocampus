"""Public-safe source-intake health diagnostics for #1127."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows
from aippocampus_runtime.source.source_texture import source_texture_health_summary

SCHEMA_VERSION = "source-intake-health-v0"
SECRET_LIKE_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9_]{8,}|xox[baprs]-[A-Za-z0-9-]{8,})"
)
LOCAL_PATH_RE = re.compile(r"([A-Za-z]:\\|/Users/|/home/)")
POLLUTION_KEYS = {
    "raw_tool_payload",
    "tool_payload",
    "tool_output",
    "raw_stdout",
    "raw_stderr",
    "full_command",
    "stack_trace",
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    result = load_jsonl_dict_rows(path)
    rows = list(result.rows)
    rows.extend({"_malformed_json": True} for _ in range(_safe_int(result.loss.get("invalid_json_line_count"))))
    rows.extend({"_non_object_json": True} for _ in range(_safe_int(result.loss.get("non_object_line_count"))))
    return rows


def _duplicate_count(rows: Sequence[Mapping[str, Any]], keys: tuple[str, ...]) -> int:
    seen: set[str] = set()
    duplicates = 0
    for row in rows:
        for key in keys:
            value = row.get(key)
            if isinstance(value, str) and value:
                marker = f"{key}:{value}"
                if marker in seen:
                    duplicates += 1
                else:
                    seen.add(marker)
                break
    return duplicates


def _contains_pollution(row: Mapping[str, Any]) -> bool:
    if row.get("_malformed_json") or row.get("_non_object_json"):
        return True
    if any(key in row for key in POLLUTION_KEYS):
        return True
    payload = row.get("payload")
    return isinstance(payload, Mapping) and any(key in payload for key in POLLUTION_KEYS)


def _source_ref_metrics(clean_manifest: Mapping[str, Any]) -> tuple[int, int]:
    broken = 0
    unreopenable = 0
    refs = clean_manifest.get("source_refs")
    if not isinstance(refs, list):
        return 0, 0
    for item in refs:
        if not isinstance(item, Mapping):
            broken += 1
            continue
        if item.get("path_exists") is False or item.get("broken") is True:
            broken += 1
        if item.get("reopenable") is False:
            unreopenable += 1
    return broken, unreopenable


def _manifest_gap(clean_manifest: Mapping[str, Any], actual_key: str, expected_key: str) -> int:
    if actual_key not in clean_manifest or expected_key not in clean_manifest:
        return 0
    return int(_safe_int(clean_manifest.get(actual_key)) < _safe_int(clean_manifest.get(expected_key)))


def _hook_status(clean_manifest: Mapping[str, Any]) -> tuple[bool | None, str]:
    intake = _mapping(clean_manifest.get("source_intake"))
    hook = _mapping(intake.get("hook"))
    if "available" not in hook and "version_status" not in hook:
        return None, "unknown"
    return bool(hook.get("available")), str(hook.get("version_status") or "unknown")


def _loss_accounting_projection(
    clean_manifest: Mapping[str, Any],
) -> tuple[dict[str, int], list[str]]:
    loss = _mapping(clean_manifest.get("loss_accounting"))
    reason_counts = _mapping(loss.get("reason_counts"))
    warning_codes = [
        str(item)
        for item in loss.get("warning_codes") or []
        if isinstance(item, str) and item
    ]
    metrics = {
        "clean_source_filtered_or_dropped_message_count": _safe_int(
            loss.get("filtered_or_dropped_message_count")
        ),
        "clean_source_user_only_turn_count": _safe_int(loss.get("user_only_turn_count")),
        "clean_source_empty_clean_turn_count": _safe_int(loss.get("empty_clean_turn_count")),
        "clean_source_no_clean_assistant_turn_count": _safe_int(
            loss.get("turns_with_no_clean_assistant_count")
        ),
        "clean_source_no_final_answer_count": _safe_int(reason_counts.get("no_final_answer")),
        "clean_source_tool_only_turn_count": _safe_int(reason_counts.get("tool_only_turn")),
        "clean_source_empty_after_filter_count": _safe_int(
            reason_counts.get("empty_after_filter")
        ),
        "clean_source_loss_warning_count": len(warning_codes),
    }
    degraded_reasons = []
    if "user_only_turn_spike" in warning_codes:
        degraded_reasons.append("clean_source_user_only_turn_spike")
    if "empty_clean_turns" in warning_codes:
        degraded_reasons.append("clean_source_empty_clean_turns")
    return metrics, degraded_reasons


def _provider_normalization_loss_projection(
    clean_manifest: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str], list[str]]:
    loss = _mapping(clean_manifest.get("provider_normalization_loss"))
    counts = _mapping(loss.get("counts"))
    warning_codes = [
        str(item)
        for item in loss.get("warning_codes") or []
        if isinstance(item, str) and item
    ]
    invalid_json = _safe_int(counts.get("invalid_json_line_count"))
    non_object = _safe_int(counts.get("non_object_line_count"))
    unsupported = _safe_int(counts.get("unsupported_event_count"))
    policy_drop = _safe_int(loss.get("policy_drop_count"))
    total_loss = _safe_int(loss.get("total_loss_count"))
    metrics: dict[str, Any] = {
        "provider_normalization_loss_reported": bool(loss),
        "provider_invalid_json_line_count": invalid_json,
        "provider_non_object_line_count": non_object,
        "provider_unsupported_event_count": unsupported,
        "provider_policy_drop_count": policy_drop,
        "provider_normalization_loss_count": total_loss,
        "provider_normalization_warning_count": len(warning_codes),
    }
    degraded_reasons = []
    if invalid_json or non_object:
        degraded_reasons.append("provider_parser_rows_dropped")
    if unsupported:
        degraded_reasons.append("provider_unsupported_events_dropped")
    if policy_drop:
        degraded_reasons.append("provider_policy_rows_dropped")
    if "provider_normalization_loss_unreported" in warning_codes:
        degraded_reasons.append("provider_normalization_loss_unreported")
    next_steps = []
    next_step = _mapping(loss.get("operator_next_step"))
    for key in ("inspect", "plan_rebuild", "rebuild"):
        value = next_step.get(key)
        if isinstance(value, str) and value:
            next_steps.append(value)
    return metrics, degraded_reasons, next_steps


def source_intake_health_summary(
    clean_source_dir: Path,
    clean_manifest: Mapping[str, Any],
    *,
    registry_path: Path | None = None,
    expected_message_count: int | None = None,
    expected_turn_count: int | None = None,
) -> dict[str, Any]:
    """Return sanitized source-intake health without exposing private rows."""

    messages = _load_jsonl(clean_source_dir / "messages.jsonl")
    turns = _load_jsonl(clean_source_dir / "turns.jsonl")
    hook_available, hook_version_status = _hook_status(clean_manifest)
    manifest_message_count = _safe_int(clean_manifest.get("message_count"), len(messages))
    manifest_turn_count = _safe_int(clean_manifest.get("turn_count"), len(turns))
    expected_messages = expected_message_count if expected_message_count is not None else manifest_message_count
    expected_turns = expected_turn_count if expected_turn_count is not None else manifest_turn_count
    source_truncation_detected_count = int(
        max(0, expected_messages - manifest_message_count) > 0
        or max(0, expected_turns - manifest_turn_count) > 0
        or bool(clean_manifest.get("truncated"))
    )
    duplicated_source_event_count = _duplicate_count(
        messages + turns,
        ("message_id", "turn_id", "source_id", "source_ref"),
    )
    polluted_source_event_count = sum(1 for row in messages + turns if _contains_pollution(row))
    encoded_private_rows = "\n".join(json.dumps(row, ensure_ascii=False) for row in messages + turns)
    local_path_leak_count = len(LOCAL_PATH_RE.findall(encoded_private_rows))
    secret_like_leak_count = len(SECRET_LIKE_RE.findall(encoded_private_rows))
    broken_source_ref_count, unreopenable_handle_count = _source_ref_metrics(clean_manifest)
    registry_entry_count = clean_manifest.get("registry_entry_count")
    materialized_source_count = clean_manifest.get("materialized_source_count")
    registry_clean_source_mismatch_count = int(
        registry_entry_count is not None
        and materialized_source_count is not None
        and _safe_int(registry_entry_count) != _safe_int(materialized_source_count)
    )
    derived_summary_count = clean_manifest.get("derived_summary_count")
    user_facing_summary_count = clean_manifest.get("user_facing_summary_count")
    derived_summary_mismatch_count = int(
        derived_summary_count is not None
        and user_facing_summary_count is not None
        and _safe_int(derived_summary_count) != _safe_int(user_facing_summary_count)
    )
    stale_hook_path_count = int(hook_version_status in {"stale", "stale_versioned_path"})
    restart_durability_status = str(
        _mapping(clean_manifest.get("source_intake")).get("restart_durability_status") or "unknown"
    )
    missing_final_answer_count = _manifest_gap(
        clean_manifest,
        "final_answer_count",
        "expected_final_answer_count",
    )
    missing_user_turn_count = _manifest_gap(
        clean_manifest,
        "user_turn_count",
        "expected_user_turn_count",
    )
    loss_metrics, loss_degraded_reasons = _loss_accounting_projection(clean_manifest)
    (
        provider_loss_metrics,
        provider_loss_degraded_reasons,
        provider_loss_next_steps,
    ) = _provider_normalization_loss_projection(clean_manifest)

    metrics = {
        "hook_available": hook_available,
        "hook_version_status": hook_version_status,
        "stale_hook_path_count": stale_hook_path_count,
        "source_truncation_detected_count": source_truncation_detected_count,
        "duplicated_source_event_count": duplicated_source_event_count,
        "polluted_source_event_count": polluted_source_event_count,
        "local_path_leak_count": local_path_leak_count,
        "secret_like_leak_count": secret_like_leak_count,
        "missing_final_answer_count": missing_final_answer_count,
        "missing_user_turn_count": missing_user_turn_count,
        "broken_source_ref_count": broken_source_ref_count,
        "unreopenable_handle_count": unreopenable_handle_count,
        "registry_clean_source_mismatch_count": registry_clean_source_mismatch_count,
        "derived_summary_mismatch_count": derived_summary_mismatch_count,
        "restart_durability_status": restart_durability_status,
        "generic_import_fallback_available": True,
        "registry_path_configured": registry_path is not None,
        **provider_loss_metrics,
        **loss_metrics,
    }
    degraded_keys = (
        "stale_hook_path_count",
        "source_truncation_detected_count",
        "duplicated_source_event_count",
        "polluted_source_event_count",
        "local_path_leak_count",
        "secret_like_leak_count",
        "missing_final_answer_count",
        "missing_user_turn_count",
        "broken_source_ref_count",
        "unreopenable_handle_count",
        "registry_clean_source_mismatch_count",
        "derived_summary_mismatch_count",
    )
    degraded_reasons = [key for key in degraded_keys if metrics[key]]
    degraded_reasons.extend(provider_loss_degraded_reasons)
    degraded_reasons.extend(loss_degraded_reasons)
    if hook_available is False:
        degraded_reasons.append("hook_missing_or_disabled")
    if restart_durability_status == "degraded":
        degraded_reasons.append("restart_durability_degraded")
    source_quality_status = "degraded" if degraded_reasons else "ok"
    cannot_claim = []
    if degraded_reasons:
        cannot_claim.extend(
            [
                "source_backed_claims_safe_when_intake_degraded",
                "host_hooks_are_stable_forever",
                "ingestion_success_means_source_quality_ok",
            ]
        )

    return {
        "kind": "aippocampus_source_intake_health",
        "schema_version": SCHEMA_VERSION,
        "source_quality_status": source_quality_status,
        "degraded_reasons": degraded_reasons,
        "metrics": metrics,
        "fallback_posture": [
            "hook_path",
            "source_health_check",
            "generic_import_fallback",
            "manual_reopen_or_audit",
        ],
        "operator_next_steps": provider_loss_next_steps,
        "privacy_boundary": {
            "raw_private_text_emitted": False,
            "raw_tool_payload_emitted": False,
            "local_paths_emitted": False,
            "secret_values_emitted": False,
        },
        "cannot_claim": cannot_claim,
    }


def clean_source_health_summaries(
    clean_source_dir: Path,
    clean_manifest: Mapping[str, Any],
    registry_path: Path | None,
    visibility: Any,
) -> dict[str, Any]:
    """Return clean-source health sidecars without growing the health owner."""

    return {
        "source_texture": source_texture_health_summary(clean_source_dir, clean_manifest),
        "source_intake": source_intake_health_summary(
            clean_source_dir,
            clean_manifest,
            registry_path=registry_path,
            expected_message_count=getattr(visibility, "expected_clean_source_message_count", None),
            expected_turn_count=getattr(visibility, "expected_clean_source_turn_count", None),
        ),
    }
