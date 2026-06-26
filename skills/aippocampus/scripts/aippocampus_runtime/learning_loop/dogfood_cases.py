"""Public-safe second-user dogfood cases for learning/action-time hints."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_learning_loop_second_user_dogfood_report"
REPRO_PACKAGE_KIND = "aippocampus_sanitized_repro_package"

OPAQUE_HANDLE_KEYS = {
    "handle",
    "message_id",
    "request_id",
    "segment_id",
    "session_id",
    "source_id",
    "source_ref",
    "thread_id",
    "thread_key",
    "turn_id",
}
PROMPT_LIKE_KEYS = {
    "content",
    "messages",
    "prompt",
    "query",
    "raw_prompt",
    "user_prompt",
}
RAW_OUTPUT_KEYS = {"output", "raw_stderr", "raw_stdout", "stderr", "stdout"}
LOCAL_PATH_PATTERN = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:Users|home|tmp|var|private|Volumes)/)")
WINDOWS_FORWARD_PATH_TEXT_RE = re.compile(r"[A-Za-z]:/[^\s,;\"')\]]+")
SECRET_PATTERN = re.compile(
    r"(?i)\bsk-[A-Za-z0-9._-]{8,}\b|"
    r"\b(?:api[_-]?key|token|secret|password)\s*[:=]\s*(?!<sensitive-value-redacted>)"
)


def _sha1_short(value: Any, *, length: int = 12) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(payload.encode("utf-8", errors="replace")).hexdigest()[:length]


def _hash_opaque_handles(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.casefold() in OPAQUE_HANDLE_KEYS and item not in (None, "", [], {}):
                out[key] = f"hash:{_sha1_short(item)}"
            else:
                out[key] = _hash_opaque_handles(item)
        return out
    if isinstance(value, list):
        return [_hash_opaque_handles(item) for item in value]
    return value


def _public_projection(value: Any) -> Any:
    projected = _hash_opaque_handles(redact_sensitive_values(redact_private_paths(value)))
    if isinstance(projected, str):
        return WINDOWS_FORWARD_PATH_TEXT_RE.sub("<local-path-redacted>", projected)
    return projected


def _redact_stdio_text(value: Any, *, inside_raw_output: bool = False) -> Any:
    """Keep repro output shape useful while removing raw prompt/stdout text.

    Repro packages are meant for public issue bodies. Raw stdout/stderr leaves
    can contain private prompts even when they do not look like paths or secrets,
    so string leaves under raw output surfaces are redacted by default. Metrics
    and status outside those raw surfaces remain available for triage.
    """

    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).casefold()
            next_inside = inside_raw_output or key_text in RAW_OUTPUT_KEYS
            if next_inside and key_text in PROMPT_LIKE_KEYS:
                out[key] = "<prompt-like-text-redacted>"
            else:
                out[key] = _redact_stdio_text(item, inside_raw_output=next_inside)
        return out
    if isinstance(value, list):
        return [_redact_stdio_text(item, inside_raw_output=inside_raw_output) for item in value]
    if inside_raw_output and isinstance(value, str) and value:
        return "<raw-output-text-redacted>"
    return value


def _line_count(value: Any) -> int:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return text.count("\n") + 1 if text else 0


def _byte_count(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"))


def _compact_sample(value: Any, *, limit: int = 1800) -> Any:
    projected = _public_projection(value)
    encoded = json.dumps(projected, ensure_ascii=False, sort_keys=True, default=str)
    if len(encoded) <= limit:
        return projected
    return {
        "truncated": True,
        "sha1": _sha1_short(projected, length=16),
        "preview": encoded[:limit].rstrip(),
    }


def _privacy_scan(value: Any) -> dict[str, Any]:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    local_path_count = len(LOCAL_PATH_PATTERN.findall(encoded))
    secret_count = len(SECRET_PATTERN.findall(encoded))
    return {
        "local_path_leak_count": local_path_count,
        "secret_like_leak_count": secret_count,
        "private_field_leak_count": local_path_count + secret_count,
    }


def _related_issue_suggestions(surface: str) -> list[str]:
    text = surface.casefold()
    suggestions: list[str] = []
    if "benchmark" in text:
        suggestions.extend(["benchmark_report_contract", "official_boundary"])
    if "recall" in text or "agent" in text:
        suggestions.extend(["foreground_recall_route", "source_reopen_boundary"])
    if "learning" in text or "dogfood" in text:
        suggestions.append("learning_loop_dogfood")
    return suggestions[:4]


def build_sanitized_repro_package(
    payload: Mapping[str, Any],
    *,
    version: str = "unknown",
    commit: str = "unknown",
    plugin_manifest_version: str = "unknown",
) -> dict[str, Any]:
    """Build a public-pasteable dogfood repro package.

    The repro package is intentionally an issue-quality shape, not evidence.
    It preserves dimensions, command class, metrics, and expected/actual notes
    while redacting local paths, credentials, raw prompts, and opaque source
    handles that would make second-user feedback unsafe to paste publicly.
    """

    materialized = dict(payload)
    surface = str(materialized.get("surface") or materialized.get("surface_kind") or "unknown")
    command = str(materialized.get("command") or materialized.get("command_shape") or "")
    output_payload = {
        "stdout": materialized.get("stdout"),
        "stderr": materialized.get("stderr"),
        "metrics": materialized.get("metrics"),
        "status": materialized.get("status"),
    }
    public_command = _public_projection(command)
    public_output = _public_projection(_redact_stdio_text(output_payload))
    package = {
        "kind": REPRO_PACKAGE_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "surface": surface,
        "versions": {
            "aippocampus": str(version or "unknown"),
            "git_commit": str(commit or "unknown")[:12],
            "plugin_manifest": str(plugin_manifest_version or "unknown"),
        },
        "command_shape": public_command,
        "output_shape": {
            "byte_count": _byte_count(output_payload),
            "line_count": _line_count(output_payload),
            "redacted_command_byte_count": len(str(public_command).encode("utf-8")),
        },
        "key_metrics": _compact_sample(materialized.get("metrics") or {}),
        "compact_sample_payload": _compact_sample(public_output),
        "expected_vs_actual_template": {
            "expected": str(_public_projection(materialized.get("expected") or "")),
            "actual": str(_public_projection(materialized.get("actual") or "")),
            "minimal_repro_steps": [
                "run the redacted command shape",
                "compare compact_sample_payload with expected/actual",
                "reopen private source only locally if maintainers request it",
            ],
        },
        "related_issue_suggestions": _related_issue_suggestions(surface),
        "privacy_note": (
            "Local paths, credential-shaped values, raw prompts/stdout/stderr text, "
            "and opaque source handles are redacted or hashed by default."
        ),
        "privacy_boundary": {
            "safe_to_paste_public_issue_by_default": True,
            "raw_prompt_serialized": False,
            "raw_stdout_stderr_serialized": False,
            "raw_output_text_preserved": False,
            "human_review_required": False,
            "local_paths_serialized": False,
            "secrets_serialized": False,
            "opaque_source_handles_hashed": True,
        },
    }
    package["privacy_scan"] = _privacy_scan(package)
    public_safe = package["privacy_scan"]["private_field_leak_count"] == 0
    package["ok"] = public_safe
    package["privacy_boundary"]["safe_to_paste_public_issue_by_default"] = public_safe
    package["privacy_boundary"]["human_review_required"] = not public_safe
    return package


def load_second_user_cases(path: Path) -> list[dict[str, Any]]:
    return load_jsonl_dict_rows(path).rows


def _phase_cases(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Mapping[str, Any]]]:
    cases: dict[str, dict[str, Mapping[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        case_id = str(row.get("case_id") or "")
        phase = str(row.get("phase") or "")
        if case_id and phase:
            cases.setdefault(case_id, {})[phase] = row
    return cases


def _flag(row: Mapping[str, Any] | None, key: str) -> bool:
    return bool((row or {}).get(key))


def build_second_user_dogfood_report(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    materialized = [dict(row) for row in rows if isinstance(row, Mapping)]
    cases = _phase_cases(materialized)
    case_reports: list[dict[str, Any]] = []
    for case_id, phases in sorted(cases.items()):
        before = phases.get("without_hint")
        after = phases.get("with_hint")
        case_reports.append(
            {
                "case_id": case_id,
                "category": str((after or before or {}).get("category") or ""),
                "first_wrong_action_avoided": _flag(before, "first_wrong_action_taken")
                and not _flag(after, "first_wrong_action_taken"),
                "broad_search_avoided": _flag(before, "broad_search_taken")
                and not _flag(after, "broad_search_taken"),
                "source_reopen_before_claim": _flag(after, "source_reopened_before_claim"),
                "hint_ignored_or_dismissed": _flag(after, "hint_ignored")
                or _flag(after, "hint_dismissed"),
                "repeat_failure_after_hint": _flag(after, "repeat_failure_after_hint"),
                "stale_warning_suppressed": _flag(before, "stale_warning_emitted")
                and not _flag(after, "stale_warning_emitted"),
                "current_thread_visibility_boundary_preserved": _flag(
                    after,
                    "current_thread_visibility_boundary_preserved",
                ),
                "hint_absent_due_to_no_cache": _flag(before, "hook_installed")
                and int((before or {}).get("prepared_cache_record_count") or 0) == 0
                and _flag(before, "hint_absent_due_to_no_cache"),
                "no_cache_not_algorithmic_miss": _flag(before, "hint_absent_due_to_no_cache")
                and not _flag(before, "generic_algorithmic_miss"),
                "prepared_cache_navigation_only_hint_emitted": int(
                    (after or {}).get("prepared_cache_record_count") or 0
                )
                > 0
                and _flag(after, "navigation_only_hint_emitted")
                and _flag(after, "action_hint_ready"),
            }
        )
    metrics = {
        "first_wrong_action_avoided": sum(1 for row in case_reports if row["first_wrong_action_avoided"]),
        "broad_search_avoided": sum(1 for row in case_reports if row["broad_search_avoided"]),
        "source_reopen_before_claim": sum(1 for row in case_reports if row["source_reopen_before_claim"]),
        "hint_ignored_or_dismissed": sum(1 for row in case_reports if row["hint_ignored_or_dismissed"]),
        "repeat_failure_after_hint": sum(1 for row in case_reports if row["repeat_failure_after_hint"]),
        "stale_warning_suppressed": sum(1 for row in case_reports if row["stale_warning_suppressed"]),
        "current_thread_visibility_boundary_preserved": sum(
            1 for row in case_reports if row["current_thread_visibility_boundary_preserved"]
        ),
        "hint_absent_due_to_no_cache": sum(
            1 for row in case_reports if row["hint_absent_due_to_no_cache"]
        ),
        "no_cache_not_algorithmic_miss": sum(
            1 for row in case_reports if row["no_cache_not_algorithmic_miss"]
        ),
        "prepared_cache_navigation_only_hint_emitted": sum(
            1 for row in case_reports if row["prepared_cache_navigation_only_hint_emitted"]
        ),
    }
    encoded = json.dumps({"cases": case_reports, "metrics": metrics}, ensure_ascii=False, sort_keys=True)
    red_lines = {
        "raw_private_text_leak_count": int("PRIVATE_" in encoded),
        "local_path_leak_count": int("C:/" in encoded or "E:/" in encoded or "\\Users\\" in encoded),
        "source_truth_overclaim_count": int("source_truth" in encoded),
    }
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": bool(case_reports) and all(value == 0 for value in red_lines.values()),
        "case_count": len(case_reports),
        "metrics": metrics,
        "cases": case_reports,
        "red_lines": red_lines,
        "privacy_boundary": {
            "public_safe_or_private_sanitized_cases_only": True,
            "raw_private_text_serialized": False,
            "raw_tool_args_serialized": False,
            "raw_commands_serialized": False,
            "raw_source_snippets_serialized": False,
            "local_paths_serialized": False,
            "navigation_only": True,
        },
        "cannot_claim": [
            "causal_live_behavior_lift",
            "all_second_user_feedback_resolved",
            "source_truth_from_hint",
        ],
    }


__all__ = [
    "build_sanitized_repro_package",
    "build_second_user_dogfood_report",
    "load_second_user_cases",
]
