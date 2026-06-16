"""Prepared action-hint cache for hot PreToolUse advisory hooks."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.hooks.action_hint_cache_records import (
    BLOCKED_STATES,
    CACHE_KIND,
    SCHEMA_VERSION,
    WEAK_SUPPORT_LEVELS,
    build_action_hint_cache_report,
)
from aippocampus_runtime.learning_loop.effectiveness_ledger import (
    apply_effectiveness_to_guidance,
    load_ledger_rows,
    summarize_effectiveness_ledger,
)

DEFAULT_ACTION_HINT_CACHE_RELATIVE = Path(".aippocampus") / "action-hints" / "pretooluse-cache.jsonl"
DEFAULT_ACTION_HINT_CACHE_LABEL = ".aippocampus/action-hints/pretooluse-cache.jsonl"


def default_action_hint_cache_path(cwd: Path | None = None) -> Path:
    return (cwd or Path.cwd()).resolve() / DEFAULT_ACTION_HINT_CACHE_RELATIVE


def _visible_ref_overlap(record: Mapping[str, Any], features: Mapping[str, Any]) -> bool:
    visible = {
        json.dumps(ref, sort_keys=True, default=str)
        for ref in features.get("visible_source_refs") or []
        if isinstance(ref, Mapping)
    }
    if not visible:
        return False
    refs = {
        json.dumps(ref, sort_keys=True, default=str)
        for ref in record.get("source_refs") or []
        if isinstance(ref, Mapping)
    }
    return bool(visible & refs)


def _text(value: Any) -> str:
    return str(value or "").strip().casefold()


def _list_values(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value] if value else []


def _specific_applicability_matches(record: Mapping[str, Any], features: Mapping[str, Any]) -> bool:
    if _text(record.get("transferability")) in {
        "general_agent_workflow",
        "general",
        "global",
        "cross_project",
    }:
        return True
    target = _text(record.get("target_fingerprint"))
    path = _text(record.get("path_category_fingerprint"))
    scope = _text(record.get("scope"))
    profile = _text(record.get("workspace_or_environment_profile"))
    topic = _text(record.get("topic_epoch"))
    if target or path:
        target_match = bool(target) and target == _text(features.get("target_fingerprint"))
        feature_paths = {
            _text(value)
            for value in [
                features.get("path_category_fingerprint"),
                *_list_values(features.get("path_category_fingerprints")),
            ]
            if _text(value)
        }
        path_match = bool(path) and any(_path_category_matches(path, value) for value in feature_paths)
        return target_match or path_match
    if scope.startswith("project:") or scope.startswith("machine:"):
        return scope == _text(features.get("scope"))
    if profile and profile != "unknown_environment":
        return profile == _text(features.get("workspace_or_environment_profile"))
    if topic:
        return topic == _text(features.get("topic_epoch"))
    return True


def _path_category_matches(record_path: str, feature_path: str) -> bool:
    if record_path == feature_path:
        return True
    if ":" in record_path and ":" not in feature_path:
        return record_path.endswith(f":{feature_path}")
    if ":" in feature_path and ":" not in record_path:
        return feature_path.endswith(f":{record_path}")
    return False


def _eligible_record(record: Mapping[str, Any], features: Mapping[str, Any], *, now_unix: float) -> bool:
    if str(record.get("freshness") or "").casefold() in BLOCKED_STATES:
        return False
    if str(record.get("authority") or "") != "navigation_only":
        return False
    if not bool(record.get("no_claim_before_reopen")):
        return False
    try:
        if float(record.get("expires_at_unix") or 0) <= now_unix:
            return False
    except (TypeError, ValueError):
        return False
    if str(record.get("confidence") or "") == "low" and int(record.get("occurrence_count") or 1) < 2:
        return False
    anti_nag = {str(value) for value in features.get("anti_nag_token_ids") or []}
    if anti_nag & {str(record.get("record_id") or ""), *map(str, record.get("anti_nag_ids") or [])}:
        return False
    if not _specific_applicability_matches(record, features):
        return False
    return not _visible_ref_overlap(record, features)


def _match_score(record: Mapping[str, Any], features: Mapping[str, Any]) -> float:
    score = 0.0
    action_class = str(record.get("action_class") or "")
    if action_class and action_class == str(features.get("action_class") or ""):
        support = str(features.get("support_level") or "").casefold()
        if support in set(record.get("support_levels") or WEAK_SUPPORT_LEVELS):
            score += 3.0
    if set(record.get("active_recall_lock_ids") or []) & set(features.get("active_recall_locks") or []):
        score += 2.0
    for field in ("tool_names", "issue_ids", "path_terms", "command_terms", "risk_modes"):
        if set(record.get(field) or []) & set(features.get(field) or []):
            score += 0.75
    if set(record.get("match_terms") or []) & set(features.get("terms") or []):
        score += 1.0
    try:
        score += float(record.get("navigation_priority_delta") or 0.0)
    except (TypeError, ValueError):
        pass
    return round(score, 3)


def read_action_hint_records(
    records_or_report: Iterable[Mapping[str, Any]] | Mapping[str, Any],
    features: Mapping[str, Any],
    *,
    now_unix: float | None = None,
    max_records: int = 5,
) -> list[dict[str, Any]]:
    if isinstance(records_or_report, Mapping):
        raw_records = records_or_report.get("records") or []
    else:
        raw_records = records_or_report
    now_value = float(now_unix if now_unix is not None else time.time())
    matches: list[dict[str, Any]] = []
    for record in raw_records:
        if not isinstance(record, Mapping) or not _eligible_record(record, features, now_unix=now_value):
            continue
        score = _match_score(record, features)
        if score <= 0:
            continue
        matches.append({**dict(record), "match_score": score})
    matches.sort(key=lambda row: (row["match_score"], row.get("confidence") == "high"), reverse=True)
    return matches[:max_records]


def load_action_hint_records_with_diagnostics(path: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    malformed_count = 0
    line_count = 0
    if not path.exists():
        return {
            "records": records,
            "line_count": line_count,
            "malformed_cache_line_count": malformed_count,
            "cache_exists": False,
        }
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        line_count += 1
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            malformed_count += 1
            continue
        if isinstance(payload, Mapping) and payload.get("kind") == CACHE_KIND:
            records.extend(dict(row) for row in payload.get("records") or [] if isinstance(row, Mapping))
        elif isinstance(payload, Mapping):
            records.append(dict(payload))
    return {
        "records": records,
        "line_count": line_count,
        "malformed_cache_line_count": malformed_count,
        "cache_exists": True,
    }


def load_action_hint_records(path: Path) -> list[dict[str, Any]]:
    diagnostics = load_action_hint_records_with_diagnostics(path)
    return list(diagnostics.get("records") or [])


def write_action_hint_cache(path: Path, report: Mapping[str, Any]) -> dict[str, Any]:
    """Write one compact cache report line readable by the hot hook.

    The cache is a prepared navigation surface, not a source artifact. Keep the
    writer boring and whole-file replaceable so hook install paths can refresh
    it without appending stale duplicate records forever.
    """

    payload = dict(report)
    if payload.get("kind") != CACHE_KIND:
        raise ValueError(f"unsupported action-hint cache kind: {payload.get('kind')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "kind": "aippocampus_action_hint_cache_write_report",
        "schema_version": SCHEMA_VERSION,
        "path": str(path),
        "record_count": int(payload.get("record_count") or 0),
        "cache_status": "with_cache_records" if int(payload.get("record_count") or 0) else "with_empty_cache",
        "privacy_boundary": payload.get("privacy_boundary") or {},
    }


def _load_provider_rows(path: Path | None) -> list[dict[str, Any]] | None:
    if path is None:
        return None
    if not path.exists():
        return []
    if path.suffix.lower() == ".jsonl":
        return [
            dict(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        rows = payload.get("records") or payload.get("rows") or payload.get("candidate_records") or []
        return [dict(row) for row in rows if isinstance(row, Mapping)]
    return []


def _default_learning_finding_paths(cwd: Path | None) -> list[Path]:
    if cwd is None:
        return []
    root = cwd.resolve()
    return [
        root / ".aippocampus" / "learning-loop" / "findings.jsonl",
        root / ".aippocampus" / "learning-loop" / "findings.json",
        root / ".aippocampus" / "learning" / "findings.jsonl",
        root / ".aippocampus" / "learning" / "findings.json",
    ]


def _default_effectiveness_ledger_paths(cwd: Path | None) -> list[Path]:
    if cwd is None:
        return []
    root = cwd.resolve()
    return [
        root / ".aippocampus" / "learning-loop" / "effectiveness-ledger.jsonl",
        root / ".aippocampus" / "learning" / "effectiveness-ledger.jsonl",
    ]


def _load_default_learning_findings(cwd: Path | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates = _default_learning_finding_paths(cwd)
    for path in candidates:
        if path.exists():
            rows = _load_provider_rows(path) or []
            return rows, {
                "status": "found",
                "source": "default_learning_findings",
                "candidate_count": len(candidates),
                "finding_count": len(rows),
            }
    return [], {
        "status": "not_found",
        "source": "default_learning_findings",
        "candidate_count": len(candidates),
        "finding_count": 0,
    }


def _load_default_effectiveness_ledger(cwd: Path | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates = _default_effectiveness_ledger_paths(cwd)
    for path in candidates:
        if path.exists():
            rows = load_ledger_rows(path)
            return rows, {
                "status": "found",
                "source": "default_effectiveness_ledger",
                "candidate_count": len(candidates),
                "row_count": len(rows),
            }
    return [], {
        "status": "not_found",
        "source": "default_effectiveness_ledger",
        "candidate_count": len(candidates),
        "row_count": 0,
    }


def _aippo_clauses_from_learning_findings(rows: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    materialized = [dict(row) for row in rows if isinstance(row, Mapping)]
    if not materialized:
        return [], {"finding_count": 0, "included_count": 0, "skipped_or_blocked_count": 0}
    from aippocampus_runtime.aippo import working_contract
    from aippocampus_runtime.learning_loop import aippo_adapter

    aippo_rows = aippo_adapter.learning_findings_to_aippo_source_rows(materialized)
    contract = working_contract.select_aippo_working_contract(
        working_contract.build_aippo_working_contracts(aippo_rows)
    )
    clauses = [dict(clause) for clause in contract.get("clauses") or [] if isinstance(clause, Mapping)]
    return clauses, {
        "finding_count": len(materialized),
        "included_count": len(aippo_rows),
        "learned_clause_count": len(clauses),
        "skipped_or_blocked_count": max(0, len(materialized) - len(aippo_rows)),
    }


def refresh_action_hint_cache(
    *,
    cwd: Path | None = None,
    cache_jsonl: Path | None = None,
    write: bool = False,
    aar_v2_records: Iterable[Mapping[str, Any]] | None = None,
    learning_guidance: Iterable[Mapping[str, Any]] | None = None,
    learning_findings: Iterable[Mapping[str, Any]] | None = None,
    aippo_learned_clauses: Iterable[Mapping[str, Any]] | None = None,
    aippo_verification_probes: Iterable[Mapping[str, Any]] | None = None,
    active_recall_locks: Iterable[Mapping[str, Any]] | None = None,
    attention_route_tokens: Iterable[Mapping[str, Any]] | None = None,
    now_unix: float | None = None,
    include_default_learning: bool = True,
    effectiveness_ledger_rows: Iterable[Mapping[str, Any]] | None = None,
    include_default_effectiveness_ledger: bool = True,
) -> dict[str, Any]:
    root = cwd.resolve() if cwd else Path.cwd()
    default_cache_path_used = cache_jsonl is None
    if cache_jsonl is None:
        cache_jsonl = default_action_hint_cache_path(root)
    learned_intake: dict[str, Any] = {
        "status": "not_requested",
        "source": "none",
        "finding_count": 0,
        "included_count": 0,
        "skipped_or_blocked_count": 0,
        "prepared_record_count": 0,
    }
    effective_aippo_clauses = (
        [dict(row) for row in aippo_learned_clauses if isinstance(row, Mapping)]
        if aippo_learned_clauses is not None
        else None
    )
    if effective_aippo_clauses is None:
        source_rows: Iterable[Mapping[str, Any]] | None = learning_findings
        if source_rows is None and include_default_learning:
            loaded, load_report = _load_default_learning_findings(cwd)
            source_rows = loaded
            learned_intake.update(load_report)
        elif source_rows is not None:
            learned_intake.update({"status": "found", "source": "explicit_learning_findings"})
        if source_rows is not None:
            effective_aippo_clauses, conversion = _aippo_clauses_from_learning_findings(source_rows)
            learned_intake.update(conversion)
            if learned_intake.get("status") == "not_found" and conversion.get("finding_count"):
                learned_intake["status"] = "found"
            if conversion.get("finding_count"):
                learned_intake["status"] = "included" if conversion.get("included_count") else "blocked"
    else:
        learned_intake.update(
            {
                "status": "explicit_aippo_clauses",
                "source": "explicit_aippo_clauses",
                "learned_clause_count": len(effective_aippo_clauses),
            }
        )
    ledger_intake: dict[str, Any] = {
        "status": "not_requested",
        "source": "none",
        "row_count": 0,
    }
    materialized_ledger_rows: list[dict[str, Any]] = []
    if effectiveness_ledger_rows is not None:
        materialized_ledger_rows = [
            dict(row) for row in effectiveness_ledger_rows if isinstance(row, Mapping)
        ]
        ledger_intake.update(
            {
                "status": "explicit",
                "source": "explicit_effectiveness_ledger",
                "row_count": len(materialized_ledger_rows),
            }
        )
    elif include_default_effectiveness_ledger:
        materialized_ledger_rows, ledger_intake = _load_default_effectiveness_ledger(cwd)
    if materialized_ledger_rows:
        if learning_guidance is not None:
            learning_guidance = apply_effectiveness_to_guidance(
                learning_guidance,
                materialized_ledger_rows,
            )
        if effective_aippo_clauses is not None:
            effective_aippo_clauses = apply_effectiveness_to_guidance(
                effective_aippo_clauses,
                materialized_ledger_rows,
            )
    report = build_action_hint_cache_report(
        aar_v2_records=aar_v2_records,
        learning_guidance=learning_guidance,
        aippo_learned_clauses=effective_aippo_clauses,
        aippo_verification_probes=aippo_verification_probes,
        active_recall_locks=active_recall_locks,
        attention_route_tokens=attention_route_tokens,
        now_unix=now_unix,
    )
    result: dict[str, Any] = {
        "ok": True,
        "kind": "aippocampus_action_hint_cache_refresh_report",
        "schema_version": SCHEMA_VERSION,
        "write_requested": bool(write),
        "wrote": False,
        "cache_status": "not_written",
        "cache_path_label": DEFAULT_ACTION_HINT_CACHE_LABEL,
        "default_cache_path_used": default_cache_path_used,
        "cache": report,
        "learned_provider_intake": {
            **learned_intake,
            "prepared_record_count": report["provider_counts"].get("aippo_learned_clause", 0),
        },
        "effectiveness_ledger_intake": {
            **ledger_intake,
            "summary": summarize_effectiveness_ledger(materialized_ledger_rows),
            "applied_to_guidance_before_cache": bool(materialized_ledger_rows),
        },
        "privacy_boundary": report["privacy_boundary"],
    }
    if write:
        write_report = write_action_hint_cache(cache_jsonl, report)
        result["wrote"] = True
        result["cache_status"] = write_report["cache_status"]
        result["write_report"] = write_report
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["report", "refresh-cache"], nargs="?", default="report")
    parser.add_argument("--cwd", type=Path)
    parser.add_argument("--cache-jsonl", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--aar-v2-json", type=Path)
    parser.add_argument("--learning-guidance-json", type=Path)
    parser.add_argument("--learning-findings-json", type=Path)
    parser.add_argument("--aippo-clauses-json", type=Path)
    parser.add_argument("--aippo-probes-json", type=Path)
    parser.add_argument("--active-recall-locks-json", type=Path)
    parser.add_argument("--attention-route-tokens-json", type=Path)
    parser.add_argument("--no-default-learning", action="store_true")
    parser.add_argument("--effectiveness-ledger-jsonl", type=Path)
    parser.add_argument("--no-default-effectiveness-ledger", action="store_true")
    parser.add_argument("--now-unix", type=float)
    parser.add_argument("--include-private-paths", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    result = refresh_action_hint_cache(
        cwd=args.cwd.resolve() if args.cwd else Path.cwd(),
        cache_jsonl=args.cache_jsonl.resolve() if args.cache_jsonl else None,
        write=args.write,
        aar_v2_records=_load_provider_rows(args.aar_v2_json),
        learning_guidance=_load_provider_rows(args.learning_guidance_json),
        learning_findings=_load_provider_rows(args.learning_findings_json),
        aippo_learned_clauses=_load_provider_rows(args.aippo_clauses_json),
        aippo_verification_probes=_load_provider_rows(args.aippo_probes_json),
        active_recall_locks=_load_provider_rows(args.active_recall_locks_json),
        attention_route_tokens=_load_provider_rows(args.attention_route_tokens_json),
        now_unix=args.now_unix,
        include_default_learning=not args.no_default_learning,
        effectiveness_ledger_rows=(
            load_ledger_rows(args.effectiveness_ledger_jsonl)
            if args.effectiveness_ledger_jsonl
            else None
        ),
        include_default_effectiveness_ledger=not args.no_default_effectiveness_ledger,
    )
    if not args.include_private_paths and isinstance(result.get("write_report"), Mapping):
        result["write_report"] = {
            key: value
            for key, value in dict(result["write_report"]).items()
            if key != "path"
        }
        result["cache_path_redacted"] = True
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = result.get("cache_status")
        count = (result.get("cache") or {}).get("record_count") if isinstance(result.get("cache"), Mapping) else 0
        print(f"action hint cache: {status}; records: {count}")
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
