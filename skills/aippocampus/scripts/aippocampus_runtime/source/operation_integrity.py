#!/usr/bin/env python3
"""Diagnose critical-operation coverage in a clean-source event lane."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aippocampus_runtime.source.operation_integrity_conflicts import (
    SUPPLEMENTAL_SUPERSESSION_FIELDS,
    conflict_gap_events,
    detect_conflicts,
)

CONTRACT_VERSION = "aippocampus-critical-operation-integrity-v1"


@dataclass(frozen=True)
class OperationFamilySpec:
    family: str
    title: str
    required_facts: tuple[str, ...]
    current_source: str
    gap_message: str


MANDATORY_FAMILIES: tuple[OperationFamilySpec, ...] = (
    OperationFamilySpec(
        family="file_edit_write_attempt",
        title="File edit/write attempt",
        required_facts=("event_id", "source_join", "path_identity", "generated_file", "status"),
        current_source="explicit_event_only",
        gap_message="No structured file write/edit attempt events were found in clean-source events.",
    ),
    OperationFamilySpec(
        family="test_check_command_result",
        title="Test/check command result",
        required_facts=(
            "event_id",
            "source_join",
            "command_family",
            "target_class",
            "exit_status",
            "failure_family_when_failed",
        ),
        current_source="legacy_tool_event_inference_or_explicit_event",
        gap_message="No behavior-backed test/check result events were found.",
    ),
    OperationFamilySpec(
        family="user_correction_or_superseding_decision",
        title="User correction, rejected route, or superseding decision",
        required_facts=("event_id", "source_join", "decision_kind", "scope", "status"),
        current_source="explicit_event_only",
        gap_message="No structured correction, rejected-route, or supersession events were found.",
    ),
    OperationFamilySpec(
        family="source_reopen_before_risky_action",
        title="Source reopen before risky action",
        required_facts=("event_id", "source_join", "reopened_source_ref", "risk_family", "status"),
        current_source="explicit_event_only",
        gap_message="No source-reopen-before-risky-action events were found.",
    ),
    OperationFamilySpec(
        family="tool_failure_changed_plan",
        title="Tool failure that changed the plan",
        required_facts=("event_id", "source_join", "tool_family", "failure_family", "plan_change_ref"),
        current_source="explicit_event_only",
        gap_message="Tool failures may exist, but none are linked to a structured plan change event.",
    ),
    OperationFamilySpec(
        family="explicit_user_constraint",
        title="Explicit user constraint",
        required_facts=("event_id", "source_join", "constraint_kind", "scope", "expiry_or_supersession"),
        current_source="explicit_event_only",
        gap_message="No structured explicit user-constraint events were found.",
    ),
)

FAMILY_BY_NAME = {spec.family: spec for spec in MANDATORY_FAMILIES}
FAMILY_ALIASES = {
    "test_check_result": "test_check_command_result",
    "test_result": "test_check_command_result",
    "check_result": "test_check_command_result",
    "file_write": "file_edit_write_attempt",
    "file_edit": "file_edit_write_attempt",
    "correction": "user_correction_or_superseding_decision",
    "rejected_route": "user_correction_or_superseding_decision",
    "superseding_decision": "user_correction_or_superseding_decision",
    "source_reopen": "source_reopen_before_risky_action",
    "tool_failure_plan_change": "tool_failure_changed_plan",
    "user_constraint": "explicit_user_constraint",
}

ABSOLUTE_PATH_RE = re.compile(
    r"(?i)(?:[a-z]:[\\/]|\\\\|/(?:users|home|var|tmp|mnt|volumes)/)"
)
SECRET_SHAPED_RE = re.compile(
    r"(?i)(secret|token|api[_-]?key|password|passwd|authorization|bearer\s+[a-z0-9._-]+)"
)
SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:/#@+-]+$")
HEX_64_RE = re.compile(r"^[a-fA-F0-9]{64}$")
PLACEHOLDER_VALUES = {
    "unknown",
    "none",
    "null",
    "missing",
    "n/a",
    "na",
    "undefined",
    "todo",
    "placeholder",
}
MAX_PLAUSIBLE_EXIT_STATUS = 2_147_483_647


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        item = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return item if isinstance(item, dict) else {}


def _looks_private(value: object) -> bool:
    text = str(value or "")
    return bool(ABSOLUTE_PATH_RE.search(text) or SECRET_SHAPED_RE.search(text))


def _is_placeholder(value: object) -> bool:
    text = str(value or "").strip().casefold()
    if not text:
        return True
    return text in PLACEHOLDER_VALUES or text.startswith(("unknown_", "missing_", "placeholder_"))


def _source_ref_looks_source_like(value: str) -> bool:
    text = value.casefold()
    return (
        ":" in value
        or "#l" in text
        or text.startswith(("src_", "source_", "clean_", "raw_", "turn_", "codex_"))
    )


def _safe_scalar(value: object) -> str | int | bool | None:
    if value is None or isinstance(value, (int, bool)):
        return value
    text = str(value)
    if not text or _looks_private(text):
        return None
    if SAFE_TOKEN_RE.match(text):
        return text
    return None


def _safe_sha256(value: object) -> str | None:
    text = str(value or "")
    return text if HEX_64_RE.match(text) and not _looks_private(text) else None


def _safe_scalar_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        safe = _safe_scalar(item)
        if isinstance(safe, str):
            items.append(safe)
    return items


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source_join_present(row: dict[str, Any]) -> bool:
    return any(row.get(key) for key in ("source_ref", "source_line", "raw_start_line", "event_id"))


def _source_join_keys_present(fact: dict[str, Any]) -> bool:
    return any(
        fact.get(key)
        for key in ("source_ref", "source_line", "raw_start_line", "raw_end_line", "turn_index", "source_id")
    )


def _safe_source_ref(row: dict[str, Any]) -> str | None:
    value = row.get("source_ref")
    if value is None or _looks_private(value):
        return None
    text = str(value)
    return text if SAFE_TOKEN_RE.match(text) else None


def _normalize_family(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = FAMILY_ALIASES.get(raw, raw)
    return normalized if normalized in FAMILY_BY_NAME else None


def _event_family(row: dict[str, Any]) -> str | None:
    for key in ("critical_operation_family", "operation_family", "event_family"):
        family = _normalize_family(row.get(key))
        if family:
            return family

    # Legacy clean-source rows already record a sanitized command class and
    # observed exit status. That is enough for the first test/check result
    # contract slice without reopening raw tool payloads.
    if (
        str(row.get("command_class") or "").casefold() == "test"
        and row.get("exit_code") is not None
        and str(row.get("event_kind") or "") == "tool_call_observed"
    ):
        return "test_check_command_result"
    return None


def _status(row: dict[str, Any]) -> str:
    status = _safe_scalar(row.get("status"))
    if isinstance(status, str):
        return status
    hard_kind = str(row.get("hard_event_kind") or "")
    if hard_kind.endswith("_failed"):
        return "failed"
    if hard_kind.endswith("_succeeded"):
        return "succeeded"
    return "observed"


def _failure_family(row: dict[str, Any], exit_status: int | None) -> str:
    explicit = _safe_scalar(row.get("failure_family"))
    if isinstance(explicit, str):
        return explicit
    if exit_status is not None and exit_status != 0:
        return "nonzero_exit"
    return "none"


def _target_class(row: dict[str, Any]) -> str:
    explicit = _safe_scalar(row.get("test_target_class") or row.get("target_class"))
    if isinstance(explicit, str):
        return explicit
    command_class = str(row.get("command_class") or "").casefold()
    if command_class == "test":
        return "unknown_test_target"
    return "unknown"


def _join_keys(row: dict[str, Any]) -> list[str]:
    keys = [
        key
        for key in (
            "source_id",
            "source_ref",
            "source_line",
            "raw_start_line",
            "raw_end_line",
            "turn_index",
            "event_id",
            "call_ref",
        )
        if row.get(key)
    ]
    return keys


def _base_fact(row: dict[str, Any]) -> dict[str, Any]:
    fact: dict[str, Any] = {
        "event_id": _safe_scalar(row.get("event_id") or row.get("id")),
        "source_id": _safe_scalar(row.get("source_id")),
        "source_ref": _safe_source_ref(row),
        "source_line": _int_or_none(row.get("source_line")),
        "raw_start_line": _int_or_none(row.get("raw_start_line")),
        "raw_end_line": _int_or_none(row.get("raw_end_line")),
        "turn_index": _int_or_none(row.get("turn_index")),
        "call_ref": _safe_scalar(row.get("call_ref")),
        "timestamp": _safe_scalar(row.get("timestamp")),
        "status": _status(row),
        "behavior_backed": bool(row.get("behavior_backed")),
        "confidence": "behavior_backed" if row.get("behavior_backed") else "source_event_row",
        "freshness": "timestamped" if row.get("timestamp") else "undated",
        "join_keys": _join_keys(row),
    }
    return {key: value for key, value in fact.items() if value not in (None, "", [])}


def _test_fact(row: dict[str, Any]) -> dict[str, Any]:
    exit_status = _int_or_none(row.get("exit_status"))
    if exit_status is None:
        exit_status = _int_or_none(row.get("exit_code"))
    command_family = _safe_scalar(row.get("command_family") or row.get("command_class"))
    fact = _base_fact(row)
    fact.update(
        {
            "family": "test_check_command_result",
            "command_family": command_family or "test",
            "target_class": _target_class(row),
            "exit_status": exit_status,
            "failure_family": _failure_family(row, exit_status),
            "input_sha256": _safe_sha256(row.get("input_sha256")),
            "observation_sha256": _safe_sha256(row.get("observation_sha256")),
            "path_categories": _safe_scalar_list(row.get("path_categories")),
            "generated_file": row.get("generated_file") if isinstance(row.get("generated_file"), bool) else None,
        }
    )
    for key in SUPPLEMENTAL_SUPERSESSION_FIELDS:
        value = _safe_scalar(row.get(key))
        if value not in (None, "", []):
            fact[key] = value
    return {key: value for key, value in fact.items() if value not in (None, "", [])}


def _explicit_fact(row: dict[str, Any], family: str) -> dict[str, Any]:
    fact = _base_fact(row)
    fact["family"] = family
    for key in (
        "path_identity",
        "path_sha256",
        "generated_file",
        "decision_kind",
        "scope",
        "reopened_source_ref",
        "risk_family",
        "tool_family",
        "failure_family",
        "plan_change_ref",
        "constraint_kind",
        "expiry_or_supersession",
        "generated_file_reason",
    ):
        value = _safe_scalar(row.get(key))
        if value not in (None, "", []):
            fact[key] = value
    for key in SUPPLEMENTAL_SUPERSESSION_FIELDS:
        value = _safe_scalar(row.get(key))
        if value not in (None, "", []):
            fact[key] = value
    for key in ("path_categories", "path_fingerprints"):
        values = _safe_scalar_list(row.get(key))
        if values:
            fact[key] = values
    return fact


def _fact_for_event(row: dict[str, Any], family: str) -> dict[str, Any]:
    if family == "test_check_command_result":
        return _test_fact(row)
    return _explicit_fact(row, family)


def _missing_required_fact_names(spec: OperationFamilySpec, fact: dict[str, Any]) -> list[str]:
    def has_fact(field: str) -> bool:
        if field not in fact:
            return False
        return fact[field] not in (None, "", [])

    missing: list[str] = []
    for field in spec.required_facts:
        if field == "source_join":
            if not _source_join_keys_present(fact):
                missing.append(field)
            continue
        if field == "path_identity":
            if not any(fact.get(key) for key in ("path_identity", "path_sha256", "path_fingerprints")):
                missing.append(field)
            continue
        if field == "failure_family_when_failed":
            if fact.get("exit_status") not in (None, 0) and not fact.get("failure_family"):
                missing.append(field)
            continue
        if field == "expiry_or_supersession":
            if not fact.get("expiry_or_supersession"):
                missing.append(field)
            continue
        if not has_fact(field):
            missing.append(field)
    return missing


def _validation_issue(
    *,
    code: str,
    field: str,
    fact: dict[str, Any],
) -> dict[str, Any]:
    event_id = fact.get("event_id")
    safe_event_id = event_id if isinstance(event_id, str) and not _is_placeholder(event_id) else "unknown"
    return {"code": code, "field": field, "event_id": safe_event_id}


def _weak_validation_reasons(
    spec: OperationFamilySpec,
    row: dict[str, Any],
    fact: dict[str, Any],
) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    raw_event_id = row.get("event_id") or row.get("id")
    if _is_placeholder(raw_event_id):
        reasons.append(_validation_issue(code="placeholder_value", field="event_id", fact=fact))

    if "source_ref" in row:
        raw_source_ref = row.get("source_ref")
        safe_source_ref = fact.get("source_ref")
        if _looks_private(raw_source_ref):
            reasons.append(_validation_issue(code="private_source_ref", field="source_ref", fact=fact))
        elif not isinstance(safe_source_ref, str):
            reasons.append(_validation_issue(code="malformed_source_ref", field="source_ref", fact=fact))
        elif not _source_ref_looks_source_like(safe_source_ref):
            reasons.append(_validation_issue(code="weak_source_ref_shape", field="source_ref", fact=fact))

    if spec.family == "test_check_command_result":
        raw_exit = row.get("exit_status") if row.get("exit_status") is not None else row.get("exit_code")
        if raw_exit is not None:
            exit_status = _int_or_none(raw_exit)
            if exit_status is None:
                reasons.append(_validation_issue(code="malformed_exit_status", field="exit_status", fact=fact))
            elif exit_status < 0 or exit_status > MAX_PLAUSIBLE_EXIT_STATUS:
                reasons.append(_validation_issue(code="implausible_exit_status", field="exit_status", fact=fact))

    for field in ("reopened_source_ref", "plan_change_ref", "expiry_or_supersession"):
        if field not in spec.required_facts and field not in row:
            continue
        raw_value = row.get(field)
        if raw_value in (None, "", []):
            continue
        if _is_placeholder(raw_value):
            reasons.append(_validation_issue(code="placeholder_value", field=field, fact=fact))
        elif _looks_private(raw_value):
            reasons.append(_validation_issue(code="private_value", field=field, fact=fact))
        elif not SAFE_TOKEN_RE.match(str(raw_value)):
            reasons.append(_validation_issue(code="malformed_value", field=field, fact=fact))

    return reasons


def _privacy_issue_for_event(row: dict[str, Any]) -> dict[str, Any] | None:
    checked_keys = (
        "source_ref",
        "command_family",
        "tool_intent",
        "path_identity",
        "path_sha256",
        "target_class",
        "test_target_class",
        "failure_family",
        "scope",
        "reopened_source_ref",
        "plan_change_ref",
        "constraint_kind",
        "expiry_or_supersession",
        "generated_file_reason",
    )
    for key in checked_keys:
        if key in row and _looks_private(row.get(key)):
            return {
                "code": "private_value_in_public_integrity_field",
                "field": key,
                "event_id": _safe_scalar(row.get("event_id") or row.get("id")) or "unknown",
            }
    for key in ("path_categories", "path_fingerprints", "path_extensions"):
        value = row.get(key)
        if not isinstance(value, list):
            continue
        if any(_looks_private(item) for item in value):
            return {
                "code": "private_value_in_public_integrity_field",
                "field": key,
                "event_id": _safe_scalar(row.get("event_id") or row.get("id")) or "unknown",
            }
    return None


def diagnose_clean_source(clean_source_dir: str | Path) -> dict[str, Any]:
    """Return a privacy-safe coverage report for critical operation facts.

    The diagnostic reads only clean-source sidecars by default. It reports gaps
    instead of reopening raw rollout payloads, because missing coverage is safer
    than silently upgrading narrative or raw tool text into source truth.
    """

    root = Path(clean_source_dir)
    manifest = _read_manifest(root / "manifest.json")
    events_path = root / "events.jsonl"
    events = _iter_jsonl(events_path)
    rows_by_family: dict[str, list[dict[str, Any]]] = {spec.family: [] for spec in MANDATORY_FAMILIES}
    privacy_issues: list[dict[str, Any]] = []
    for row in events:
        issue = _privacy_issue_for_event(row)
        if issue:
            privacy_issues.append(issue)
        family = _event_family(row)
        if family:
            rows_by_family[family].append(row)

    family_reports: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for spec in MANDATORY_FAMILIES:
        rows = rows_by_family[spec.family]
        facts = [_fact_for_event(row, spec.family) for row in rows]
        weak_fields_by_event: list[dict[str, Any]] = []
        for row, fact in zip(rows, facts, strict=True):
            reasons = _weak_validation_reasons(spec, row, fact)
            if not reasons:
                continue
            fact["validation_reasons"] = reasons
            weak_fields_by_event.append(
                {
                    "event_id": fact.get("event_id") or "unknown",
                    "validation_reasons": reasons,
                }
            )
        missing_fields_by_event = [
            {
                "event_id": fact.get("event_id") or "unknown",
                "missing_required_facts": _missing_required_fact_names(spec, fact),
            }
            for fact in facts
        ]
        missing_fields_by_event = [
            item for item in missing_fields_by_event if item["missing_required_facts"]
        ]
        family_conflicts = detect_conflicts(spec.family, facts, manifest)
        conflicts.extend(family_conflicts)

        if not rows:
            status = "missing"
            gap = {
                "family": spec.family,
                "gap_kind": "missing_event_family",
                "message": spec.gap_message,
                "ordinary_recall_allowed": True,
                "downstream_rule": "Do not claim this operation family is covered; reopen source or raw audit material before strong operation claims.",
            }
            gaps.append(gap)
        elif missing_fields_by_event:
            status = "partial"
            gap = {
                "family": spec.family,
                "gap_kind": "missing_required_facts",
                "events": missing_fields_by_event,
                "ordinary_recall_allowed": True,
                "downstream_rule": "Use captured facts as source-backed evidence, but keep missing fields explicit.",
            }
            gaps.append(gap)
        elif weak_fields_by_event:
            status = "weak_covered"
            gap = {
                "family": spec.family,
                "gap_kind": "weak_required_facts",
                "events": weak_fields_by_event,
                "ordinary_recall_allowed": True,
                "downstream_rule": "Use these rows as navigation or candidate evidence only; reopen source or raw audit material before strong operation claims.",
            }
            gaps.append(gap)
        else:
            status = "covered"
        if family_conflicts:
            if status == "covered":
                status = "weak_covered"
            gaps.append(
                {
                    "family": spec.family,
                    "gap_kind": "conflicting_facts",
                    "events": conflict_gap_events(family_conflicts),
                    "ordinary_recall_allowed": True,
                    "downstream_rule": "Use conflicted rows as route material only; reopen source or raw audit material before strong operation claims.",
                }
            )

        family_reports.append(
            {
                "family": spec.family,
                "title": spec.title,
                "status": status,
                "current_source": spec.current_source,
                "required_facts": list(spec.required_facts),
                "event_count": len(rows),
                "conflict_count": len(family_conflicts),
                "facts": facts,
            }
        )

    covered_count = sum(1 for item in family_reports if item["status"] == "covered")
    weak_covered_count = sum(1 for item in family_reports if item["status"] == "weak_covered")
    partial_count = sum(1 for item in family_reports if item["status"] == "partial")
    missing_count = sum(1 for item in family_reports if item["status"] == "missing")
    manifest_policy = manifest.get("event_lane_policy") if isinstance(manifest, dict) else {}
    if not isinstance(manifest_policy, dict):
        manifest_policy = {}

    conflict_count = len(conflicts)

    return {
        "ok": True,
        "contract_version": CONTRACT_VERSION,
        "contract_complete": (
            missing_count == 0
            and partial_count == 0
            and weak_covered_count == 0
            and conflict_count == 0
            and not privacy_issues
        ),
        "ordinary_recall_allowed": True,
        "inputs": {
            "manifest_json": "manifest.json" if (root / "manifest.json").exists() else None,
            "events_jsonl": "events.jsonl" if events_path.exists() else None,
        },
        "manifest": {
            "schema_version": manifest.get("schema_version"),
            "source_provider": manifest.get("source_provider"),
            "source_id": manifest.get("source_id"),
            "event_lane_status": manifest_policy.get("status"),
            "raw_payload_policy": manifest_policy.get("raw_payload_policy"),
        },
        "event_count": len(events),
        "coverage_summary": {
            "covered_family_count": covered_count,
            "weak_covered_family_count": weak_covered_count,
            "partial_family_count": partial_count,
            "missing_family_count": missing_count,
            "gap_count": len(gaps),
            "conflict_count": conflict_count,
            "privacy_issue_count": len(privacy_issues),
        },
        "families": family_reports,
        "gaps": gaps,
        "conflicts": conflicts,
        "privacy": {
            "raw_payload_policy": "hash_only",
            "issues": privacy_issues,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--clean-source-dir",
        required=True,
        help="Directory containing clean-source manifest.json and events.jsonl.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return a non-zero status when any required family is missing or partial.",
    )
    args = parser.parse_args(argv)

    report = diagnose_clean_source(args.clean_source_dir)
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        summary = report["coverage_summary"]
        print(f"contract: {report['contract_version']}")
        print(
            "families: "
            f"{summary['covered_family_count']} covered, "
            f"{summary['weak_covered_family_count']} weak-covered, "
            f"{summary['partial_family_count']} partial, "
            f"{summary['missing_family_count']} missing, "
            f"{summary['conflict_count']} conflicts"
        )
        for gap in report["gaps"]:
            print(f"gap: {gap['family']}: {gap['gap_kind']}")
    return 2 if args.strict and not report["contract_complete"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
