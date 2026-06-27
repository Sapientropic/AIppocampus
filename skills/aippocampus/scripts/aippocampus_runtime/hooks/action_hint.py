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

from aippocampus_runtime.hooks import recent_recall_routes

# aippocampus-instruction-surface: action-hint hook/probe compact projection and detail diagnostics owner.

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_pre_tool_action_hint_report"
HINT_KIND = "aippocampus_pre_tool_action_hint"
SUPPORTED_EVENT = "PreToolUse"
COMMAND_FAMILY_TERMS = {
    "broad_search",
    "cargo",
    "git",
    "grep",
    "mypy",
    "npm",
    "pnpm",
    "pytest",
    "rg",
    "ripgrep",
    "ruff",
    "search",
    "search_clean_source",
    "test",
    "tsc",
    "uv",
}
BROAD_SEARCH_COMMAND_TERMS = {
    "grep",
    "rg",
    "ripgrep",
    "search",
    "search_clean_source",
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
    if terms & BROAD_SEARCH_COMMAND_TERMS:
        terms.update({"broad_search", "search"})
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
            if key
            in {
                "route_id",
                "lock_id",
                "source_id",
                "segment_id",
                "deepen_route_id",
                "reopen_required",
                "request_index",
                "recall_selector",
                "query",
                "tool_name",
                "arguments",
                "command",
            }
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
    from aippocampus_runtime.hooks.action_hint_cache import read_action_hint_records

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


def _default_probe_envelope() -> dict[str, Any]:
    return {
        "hook_event_name": SUPPORTED_EVENT,
        "tool_name": "Bash",
        "tool_input": {
            "command": "rg AIppocampus recall source route",
            "command_family": "rg",
        },
        "intent": "broad search for a recent recall source route",
    }


def _with_probe_usefulness(report: dict[str, Any]) -> dict[str, Any]:
    raw_hint = report.get("hint")
    hint: Mapping[str, Any] = raw_hint if isinstance(raw_hint, Mapping) else {}
    source_handles = [
        handle for handle in hint.get("source_handles") or [] if isinstance(handle, Mapping)
    ]
    primary_handle = source_handles[0] if source_handles else {}
    followthrough = (
        recent_recall_routes.probe_recent_recall_handle_followthrough(primary_handle)
        if primary_handle
        else {"status": "blocked", "reason": "no_source_handle"}
    )
    useful = bool(
        report.get("decision") == "hint"
        and hint.get("source_reopen_required")
        and source_handles
        and followthrough.get("status") in {"passed", "not_applicable"}
    )
    diagnostics = report.setdefault("diagnostics", {})
    if isinstance(diagnostics, dict):
        diagnostics["probe"] = True
        diagnostics["source_followthrough_handle_count"] = len(source_handles)
        diagnostics["source_followthrough_probe"] = {
            key: value
            for key, value in followthrough.items()
            if value not in (None, "", [], {})
        }
    report["usefulness_stage"] = "useful" if useful else "active" if source_handles else "callable"
    report["useful"] = useful
    if not useful and source_handles:
        report["reason"] = str(followthrough.get("reason") or report.get("reason") or "")
    report["claim_boundary"] = (
        "probe verifies hook hint selection and follow-through handle presence; "
        "agent_deepen or recall_deepen must still open source before claims"
    )
    return report


def _primary_probe_handle(hint: Mapping[str, Any]) -> dict[str, Any] | None:
    for handle in hint.get("source_handles") or []:
        if isinstance(handle, Mapping):
            return dict(handle)
    return None


def compact_probe_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return the foreground probe card without feature extraction diagnostics.

    The status card recommends this probe to foreground agents, so the default
    JSON must stay action-sized. Full feature vectors, cache accounting, and raw
    diagnostics remain available through ``--detail full`` for operator review.
    """

    raw_hint = report.get("hint")
    hint = raw_hint if isinstance(raw_hint, Mapping) else {}
    primary_handle = _primary_probe_handle(hint)
    useful = bool(report.get("useful"))
    action: dict[str, Any]
    if useful and primary_handle and primary_handle.get("command"):
        raw_arguments = primary_handle.get("arguments")
        arguments = raw_arguments if isinstance(raw_arguments, Mapping) else {}
        action = {
            "id": "deepen_probe_source_route",
            "label": "Deepen probe source route",
            "command": str(primary_handle.get("command") or ""),
            "tool_name": str(primary_handle.get("tool_name") or "agent_deepen"),
            "arguments": dict(arguments),
            "why": "The probe matched a prepared action-time hint; open its source route before claims.",
            "mutation_risk": "read_only",
            "claim_boundary": "no_claim_before_reopen",
        }
    else:
        refresh_query = str((primary_handle or {}).get("query") or "").strip()
        refresh_command = (
            f"aippocampus agent recall {json.dumps(refresh_query, ensure_ascii=False)} --json"
            if refresh_query
            else "aippocampus hooks action refresh-cache --write --json"
        )
        action = {
            "id": "refresh_probe_source_route",
            "label": "Refresh probe source route",
            "command": refresh_command,
            "why": (
                "The probe did not validate a live source route; refresh recall/source "
                "routing before treating action-time hints as useful."
            ),
            "mutation_risk": "read_only",
            "claim_boundary": "action_hints_are_navigation_not_source_truth",
        }
    compact_hint = None
    if hint:
        compact_hint = {
            "hint_id": str(hint.get("hint_id") or ""),
            "provider_family": str(hint.get("provider_family") or ""),
            "action_hint_kind": str(hint.get("action_hint_kind") or ""),
            "message": str(hint.get("message") or ""),
            "recommended_action": str(hint.get("recommended_action") or ""),
            "navigation_only": bool(hint.get("navigation_only", True)),
            "source_reopen_required": bool(hint.get("source_reopen_required", True)),
            "authority": str(hint.get("authority") or "navigation_only"),
            "source_ref_count": int(hint.get("source_ref_count") or 0),
        }
    return {
        "schema_version": int(report.get("schema_version") or SCHEMA_VERSION),
        "kind": "aippocampus_action_hint_probe_compact",
        "detail": "compact",
        "ok": bool(report.get("ok", True)),
        "decision": str(report.get("decision") or ""),
        "reason": str(report.get("reason") or ""),
        "useful": useful,
        "usefulness_stage": str(report.get("usefulness_stage") or ""),
        "hint": compact_hint,
        "foreground_action": action,
        "source_reopen_boundary": (
            "Probe usefulness means a navigation handle exists; deepen or reopen "
            "that source before factual claims."
        ),
        "claim_boundary": str(
            report.get("claim_boundary")
            or "action_hints_are_navigation_not_source_truth"
        ),
    }


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


def _cache_readiness(cache_jsonl: Path | None) -> dict[str, Any]:
    """Return a tiny hot-path readiness check before reading hook payload details.

    `PreToolUse` runs before ordinary agent actions, so empty/missing caches
    must not pay the full feature-extraction and matching path. Missing and
    zero-byte files are decided with filesystem metadata only; non-empty files
    then use the normal cache loader to distinguish fresh from expired records.
    """

    if cache_jsonl is None:
        return {
            "cache_status": "with_missing_cache_file",
            "cache_configured": False,
            "cache_exists": False,
            "record_count": 0,
            "fresh_record_count": 0,
            "malformed_cache_line_count": 0,
            "records": [],
        }
    if not cache_jsonl.exists():
        return {
            "cache_status": "with_missing_cache_file",
            "cache_configured": True,
            "cache_exists": False,
            "record_count": 0,
            "fresh_record_count": 0,
            "malformed_cache_line_count": 0,
            "records": [],
        }
    try:
        if cache_jsonl.stat().st_size <= 0:
            return {
                "cache_status": "with_empty_cache",
                "cache_configured": True,
                "cache_exists": True,
                "record_count": 0,
                "fresh_record_count": 0,
                "malformed_cache_line_count": 0,
                "records": [],
            }
    except OSError:
        return {
            "cache_status": "with_missing_cache_file",
            "cache_configured": True,
            "cache_exists": False,
            "record_count": 0,
            "fresh_record_count": 0,
            "malformed_cache_line_count": 0,
            "records": [],
        }

    from aippocampus_runtime.hooks.action_hint_cache import (
        load_action_hint_records_with_diagnostics,
    )
    from aippocampus_runtime.hooks.action_hint_cache_records import BLOCKED_STATES

    cache_report = load_action_hint_records_with_diagnostics(cache_jsonl)
    records = [row for row in cache_report.get("records") or [] if isinstance(row, Mapping)]
    now_unix = time.time()
    fresh_count = 0
    for record in records:
        freshness = str(record.get("freshness") or "").casefold()
        try:
            expires_at = float(record.get("expires_at_unix") or 0)
        except (TypeError, ValueError):
            expires_at = 0.0
        if freshness in BLOCKED_STATES or (expires_at and expires_at <= now_unix):
            continue
        fresh_count += 1
    if not records:
        cache_status = "with_empty_cache"
    elif fresh_count:
        cache_status = "with_fresh_records"
    else:
        cache_status = "with_expired_records"
    return {
        "cache_status": cache_status,
        "cache_configured": True,
        "cache_exists": bool(cache_report.get("cache_exists", True)),
        "record_count": len(records),
        "fresh_record_count": fresh_count,
        "malformed_cache_line_count": int(cache_report.get("malformed_cache_line_count") or 0),
        "records": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["run", "probe"], nargs="?", default="run")
    parser.add_argument("--cache-jsonl", type=Path, help="Prepared action-hint record JSONL.")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--compact-json", action="store_true", dest="compact_json")
    parser.add_argument("--operator-json", action="store_true", dest="operator_json")
    parser.add_argument("--detail", choices=["compact", "full"], default="compact")
    args = parser.parse_args(argv)
    try:
        envelope = _read_stdin_json() or (_default_probe_envelope() if args.action == "probe" else {})
    except json.JSONDecodeError:
        report = _silent_report("malformed_input")
    else:
        cache_jsonl = args.cache_jsonl
        if cache_jsonl is None and args.action == "probe":
            from aippocampus_runtime.hooks.action_hint_cache import default_action_hint_cache_path

            cache_jsonl = default_action_hint_cache_path()
        readiness = _cache_readiness(cache_jsonl)
        if readiness["cache_status"] != "with_fresh_records":
            report = _silent_report(
                "cache_not_ready",
                diagnostics={
                    "hot_path_bailed": True,
                    "cache_status": readiness["cache_status"],
                    "cache_configured": readiness["cache_configured"],
                    "cache_exists": readiness["cache_exists"],
                    "prepared_record_count": readiness["record_count"],
                    "fresh_record_count": readiness["fresh_record_count"],
                    "malformed_cache_line_count": readiness["malformed_cache_line_count"],
                },
            )
        else:
            report = evaluate_action_hint(envelope, readiness["records"])
            diagnostics = report.setdefault("diagnostics", {})
            if isinstance(diagnostics, dict):
                diagnostics.update(
                    {
                        "hot_path_bailed": False,
                        "cache_status": readiness["cache_status"],
                        "malformed_cache_line_count": readiness["malformed_cache_line_count"],
                    }
                )
    if args.action == "probe":
        report = _with_probe_usefulness(report)
    if args.operator_json:
        args.json_output = True
        args.detail = "full"
    if args.compact_json:
        args.json_output = True
        args.detail = "compact"
    if args.json_output:
        payload: Mapping[str, Any] = (
            compact_probe_report(report)
            if args.action == "probe" and args.detail == "compact"
            else {
                **report,
                **(
                    {
                        "detail": "full",
                        "output_boundary": "local_private_diagnostic_full",
                        "compact_command": "aippocampus hooks action probe --compact-json",
                    }
                    if args.action == "probe"
                    else {}
                ),
            }
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif report.get("hint"):
        print(report["hint"]["message"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
