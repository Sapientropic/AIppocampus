"""Hot action-time hint hook for prepared PreToolUse anchors."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.hooks.action_hint_cache import (
    load_action_hint_records_with_diagnostics,
    read_action_hint_records,
)

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_pre_tool_action_hint_report"
HINT_KIND = "aippocampus_pre_tool_action_hint"
SUPPORTED_EVENT = "PreToolUse"
COMMAND_FAMILY_TERMS = {
    "cargo",
    "git",
    "mypy",
    "npm",
    "pnpm",
    "pytest",
    "ruff",
    "test",
    "tsc",
    "uv",
}


def _terms(*values: Any) -> list[str]:
    tokens: set[str] = set()
    for value in values:
        if isinstance(value, Mapping):
            tokens.update(_terms(*value.values()))
            continue
        if isinstance(value, (list, tuple, set)):
            tokens.update(_terms(*value))
            continue
        for token in re.split(r"[^a-zA-Z0-9]+", str(value or "").casefold()):
            if token:
                tokens.add(token)
    return sorted(tokens)


def _strings(value: Any, *, limit: int = 8) -> list[str]:
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_label(value: Any, *, limit: int = 160) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if re.search(r"(^[a-zA-Z]:[\\/]|^/Users/|^/home/|\\\\)", text):
        return ""
    return text[:limit]


def _path_values(raw_args: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for field in ("file_path", "file_paths", "path", "paths", "target_file"):
        value = raw_args.get(field)
        if isinstance(value, (list, tuple, set)):
            values.extend(str(item or "") for item in value if item)
        elif value:
            values.append(str(value))
    return values[:8]


def _looks_private_or_absolute_path(text: str) -> bool:
    normalized = text.replace("\\", "/").strip()
    return bool(
        re.search(r"^[a-zA-Z]:/", normalized)
        or normalized.startswith(("/", "~", "//"))
        or re.search(r"(^|/)(users|home)/[^/]+/", normalized.casefold())
    )


def _raw_tool_args(envelope: Mapping[str, Any]) -> Mapping[str, Any]:
    for field in ("tool_args", "tool_input", "input", "args"):
        value = envelope.get(field)
        if isinstance(value, Mapping):
            return value
    return {}


def _tool_name(envelope: Mapping[str, Any]) -> str:
    return str(
        envelope.get("tool_name")
        or envelope.get("tool")
        or envelope.get("name")
        or _raw_tool_args(envelope).get("tool_name")
        or ""
    )


def _path_terms(raw_args: Mapping[str, Any]) -> list[str]:
    terms: set[str] = set()
    for text in _path_values(raw_args):
        normalized = text.replace("\\", "/")
        # Keep only path fragments useful for matching. Full absolute paths stay
        # out of hook output and diagnostics.
        fragments = [part for part in normalized.split("/") if part and ":" not in part]
        if _looks_private_or_absolute_path(normalized):
            terms.update(_terms(fragments[-1:]))
        else:
            terms.update(_terms(fragments[-4:]))
    return sorted(terms)[:16]


def _path_category_fingerprints(raw_args: Mapping[str, Any]) -> list[str]:
    categories: list[str] = []
    seen: set[str] = set()
    for text in _path_values(raw_args):
        normalized = text.replace("\\", "/").strip().strip("/")
        if _looks_private_or_absolute_path(normalized):
            continue
        fragments = [part for part in normalized.split("/") if part and ":" not in part]
        if len(fragments) < 2:
            continue
        dirs = fragments[:-1]
        for size in (2, 1):
            if len(dirs) >= size:
                category = "/".join(dirs[-size:])
                key = category.casefold()
                if category and key not in seen:
                    seen.add(key)
                    categories.append(category)
        if len(categories) >= 4:
            break
    return categories[:4]


def _issue_ids(*values: Any) -> list[str]:
    ids: set[str] = set()
    for value in values:
        if isinstance(value, Mapping):
            ids.update(_issue_ids(*value.values()))
            continue
        if isinstance(value, (list, tuple, set)):
            ids.update(_issue_ids(*value))
            continue
        ids.update(match.group(1) for match in re.finditer(r"#?(\d{2,6})", str(value or "")))
    return sorted(ids)[:8]


def _command_terms(raw_args: Mapping[str, Any]) -> list[str]:
    values = [
        raw_args.get("command_family"),
        raw_args.get("command_terms"),
        raw_args.get("test_name"),
        raw_args.get("test_names"),
        raw_args.get("cmd"),
        raw_args.get("command"),
    ]
    terms = set(_terms(values)) & COMMAND_FAMILY_TERMS
    if {"pytest", "ruff", "mypy", "tsc", "cargo"} & terms:
        terms.add("test")
    return sorted(terms)


def extract_pending_action_features(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Return public-safe features for a pending action.

    The extractor reads raw hook payloads but only emits controlled labels,
    normalized terms, ids, and small action-state flags. It deliberately drops
    command text, tool args, source snippets, and absolute paths.
    """

    raw_args = _raw_tool_args(envelope)
    tool_name = _tool_name(envelope)
    command_terms = _command_terms(raw_args)
    path_terms = _path_terms(raw_args)
    explicit_path_category = _safe_label(
        envelope.get("path_category_fingerprint")
        or raw_args.get("path_category_fingerprint")
    )
    derived_path_categories = _path_category_fingerprints(raw_args)
    path_categories = [explicit_path_category, *derived_path_categories]
    path_categories = [category for index, category in enumerate(path_categories) if category and category not in path_categories[:index]]
    issue_ids = _issue_ids(
        raw_args.get("issue_ids"),
        raw_args.get("issue"),
        raw_args.get("command"),
        raw_args.get("branch"),
        envelope.get("issue_ids"),
    )
    risk_mode = str(envelope.get("risk") or envelope.get("risk_mode") or raw_args.get("risk") or "")
    terms = _terms(
        tool_name,
        path_terms,
        issue_ids,
        command_terms,
        raw_args.get("branch_name"),
        raw_args.get("branch"),
        envelope.get("intent"),
        envelope.get("action_class"),
        risk_mode,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_pending_action_features",
        "hook_event_name": str(envelope.get("hook_event_name") or envelope.get("event") or ""),
        "tool_name": tool_name,
        "tool_names": [tool_name] if tool_name else [],
        "path_terms": path_terms,
        "issue_ids": issue_ids,
        "command_terms": command_terms,
        "terms": terms,
        "topic_epoch": str(envelope.get("topic_epoch") or raw_args.get("topic_epoch") or ""),
        "scope": _safe_label(envelope.get("scope") or raw_args.get("scope")),
        "target_fingerprint": _safe_label(
            envelope.get("target_fingerprint") or raw_args.get("target_fingerprint")
        ),
        "path_category_fingerprint": path_categories[0] if path_categories else "",
        "path_category_fingerprints": path_categories,
        "workspace_or_environment_profile": _safe_label(
            envelope.get("workspace_or_environment_profile")
            or raw_args.get("workspace_or_environment_profile")
            or envelope.get("environment_profile")
            or raw_args.get("environment_profile")
        ),
        "active_recall_locks": _strings(
            envelope.get("active_recall_locks") or raw_args.get("active_recall_locks")
        ),
        "anti_nag_token_ids": _strings(
            envelope.get("anti_nag_token_ids")
            or envelope.get("recently_dismissed_hint_ids")
            or raw_args.get("anti_nag_token_ids")
        ),
        "risk_modes": [risk_mode] if risk_mode else [],
        "action_class": str(envelope.get("action_class") or raw_args.get("action_class") or ""),
        "support_level": str(envelope.get("support_level") or raw_args.get("support_level") or ""),
        "visible_source_refs": [
            dict(ref)
            for ref in envelope.get("visible_source_refs") or raw_args.get("visible_source_refs") or []
            if isinstance(ref, Mapping)
        ][:6],
        "source_open_token_ids": _strings(
            envelope.get("source_open_token_ids") or raw_args.get("source_open_token_ids")
        ),
        "privacy_boundary": {
            "raw_tool_args_emitted": False,
            "raw_command_text_emitted": False,
            "raw_source_snippets_emitted": False,
            "local_paths_emitted": False,
            "private_prompt_text_emitted": False,
        },
    }


def _hint_message(record: Mapping[str, Any]) -> str:
    action = str(record.get("next_action") or "reopen_source_before_action")
    if action == "reopen_source_before_specific_claim":
        return "Reopen source before making this specific memory/source claim."
    if "preflight" in action:
        return "Run the cheap source-backed preflight before the broader action."
    if "capture_evidence" in action:
        return "Capture or reopen the active anchor before this action changes evidence."
    return "Use the prepared source route before treating this as guidance."


def build_hint(record: Mapping[str, Any]) -> dict[str, Any]:
    handles = [
        {
            key: value
            for key, value in dict(handle).items()
            if key in {"route_id", "lock_id", "source_id", "segment_id", "deepen_route_id", "reopen_required"}
        }
        for handle in record.get("source_handles") or []
        if isinstance(handle, Mapping)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": HINT_KIND,
        "hint_id": str(record.get("record_id") or ""),
        "provider_family": str(record.get("provider_family") or ""),
        "action_hint_kind": str(record.get("action_hint_kind") or ""),
        "message": _hint_message(record),
        "recommended_action": str(record.get("next_action") or "source_reopen"),
        "navigation_only": True,
        "no_claim_before_reopen": True,
        "source_reopen_required": True,
        "can_support_factual_claim": False,
        "authority": "navigation_only",
        "source_ref_count": len(record.get("source_refs") or []),
        "source_handles": handles[:2],
        "reason_codes": list(record.get("reason_codes") or [])[:6],
        "match_score": float(record.get("match_score") or 0.0),
    }


def evaluate_action_hint(
    envelope: Mapping[str, Any],
    prepared_records: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    *,
    now_unix: float | None = None,
) -> dict[str, Any]:
    now_value = float(now_unix if now_unix is not None else time.time())
    features = extract_pending_action_features(envelope)
    if features["hook_event_name"] != SUPPORTED_EVENT:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": REPORT_KIND,
            "ok": True,
            "decision": "silent",
            "reason": "unsupported_event",
            "features": features,
            "hint": None,
            "privacy_boundary": features["privacy_boundary"],
        }
    matches = read_action_hint_records(prepared_records, features, now_unix=now_value, max_records=1)
    hint = build_hint(matches[0]) if matches else None
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "ok": True,
        "decision": "hint" if hint else "silent",
        "reason": "prepared_record_match" if hint else "no_prepared_record_match",
        "features": features,
        "hint": hint,
        "diagnostics": {
            "prepared_record_count": len(
                prepared_records.get("records", [])
                if isinstance(prepared_records, Mapping)
                else prepared_records
            ),
            "matched_record_count": len(matches),
            "raw_tool_args_serialized": False,
            "raw_command_text_serialized": False,
            "command_rewritten": False,
            "permission_system_behavior": False,
        },
        "privacy_boundary": features["privacy_boundary"],
    }


def _read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    payload = json.loads(raw)
    return dict(payload) if isinstance(payload, Mapping) else {}


def _silent_report(reason: str, *, diagnostics: Mapping[str, Any] | None = None) -> dict[str, Any]:
    privacy = {
        "raw_tool_args_emitted": False,
        "raw_command_text_emitted": False,
        "raw_source_snippets_emitted": False,
        "local_paths_emitted": False,
        "private_prompt_text_emitted": False,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "ok": True,
        "decision": "silent",
        "reason": reason,
        "features": {},
        "hint": None,
        "diagnostics": {
            "prepared_record_count": 0,
            "matched_record_count": 0,
            "raw_tool_args_serialized": False,
            "raw_command_text_serialized": False,
            "command_rewritten": False,
            "permission_system_behavior": False,
            **dict(diagnostics or {}),
        },
        "privacy_boundary": privacy,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-jsonl", type=Path, help="Prepared action-hint record JSONL.")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    try:
        envelope = _read_stdin_json()
    except json.JSONDecodeError:
        report = _silent_report("malformed_input")
    else:
        cache_diagnostics: dict[str, Any] = {}
        if args.cache_jsonl:
            cache_report = load_action_hint_records_with_diagnostics(args.cache_jsonl)
            records = list(cache_report.get("records") or [])
            cache_diagnostics = {
                "malformed_cache_line_count": int(
                    cache_report.get("malformed_cache_line_count") or 0
                ),
                "cache_line_count": int(cache_report.get("line_count") or 0),
            }
        else:
            records = []
        report = evaluate_action_hint(envelope, records)
        if cache_diagnostics:
            diagnostics = report.setdefault("diagnostics", {})
            if isinstance(diagnostics, dict):
                diagnostics.update(cache_diagnostics)
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report.get("hint"):
        print(report["hint"]["message"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
