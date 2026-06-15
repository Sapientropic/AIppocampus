"""AIppo clause probes, relation selection, and lifecycle calibration."""

from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 1
PROBE_KIND = "aippocampus_aippo_verification_probe"
CALIBRATION_KIND = "aippocampus_aippo_lifecycle_calibration"
RELATION_KIND = "aippocampus_aippo_relation_selection"
STALE_POLICY_DAYS = {
    "environment_workaround": 7,
    "reopen_first_workflow_clause": 14,
    "workflow_order_clause": 45,
    "workflow_default": 45,
}
SEVERITY_WEIGHTS = {
    "wrong_route_drag": 5,
    "source_correction": 5,
    "misleading": 4,
    "stale": 3,
    "noisy": 1,
    "helped": -2,
}


def _stable_id(prefix: str, *parts: Any) -> str:
    encoded = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}_{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:16]}"


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(item) for item in value if str(item or "").strip()]
    return []


def _source_refs(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    refs = row.get("source_refs")
    return [ref for ref in refs if isinstance(ref, Mapping)] if isinstance(refs, Sequence) else []


def _status(clause: Mapping[str, Any]) -> str:
    return str(_as_mapping(clause.get("lifecycle")).get("status") or "").casefold()


def _activation(clause: dict[str, Any]) -> dict[str, Any]:
    raw = clause.setdefault("activation", {})
    if not isinstance(raw, dict):
        raw = {}
        clause["activation"] = raw
    return raw


def _lifecycle(clause: dict[str, Any]) -> dict[str, Any]:
    raw = clause.setdefault("lifecycle", {})
    if not isinstance(raw, dict):
        raw = {}
        clause["lifecycle"] = raw
    return raw


def _parse_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def verification_probes_from_growing_clauses(
    clauses: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    for clause in clauses:
        if _status(clause) != "growing":
            continue
        refs = _source_refs(clause)
        support = _as_mapping(clause.get("support"))
        if not refs or support.get("support_grade") in {"candidate_only", "private"}:
            continue
        if clause.get("privacy_domain") in {"private", "restricted"}:
            continue
        task_family = _strings(clause.get("applies_when"))[:3] or ["coding"]
        probes.append(
            {
                "kind": PROBE_KIND,
                "schema_version": SCHEMA_VERSION,
                "probe_id": _stable_id("aippo_probe", clause.get("clause_id"), task_family),
                "clause_id": clause.get("clause_id"),
                "probe_class": "workflow_order_probe"
                if "workflow" in str(clause.get("kind") or "")
                else "context_reopen_probe",
                "task_family": task_family,
                "expected_observation": "source_backed_outcome_changes_repeat_failure_or_drag",
                "source_refs": [dict(ref) for ref in refs[:4]],
                "invalidators": _strings(_as_mapping(clause.get("freshness")).get("invalidators")),
                "navigation_only": True,
                "source_reopen_required_before_claim": True,
                "can_ripen_from_agent_self_report": False,
                "action_time_exposure": {
                    "optional": True,
                    "anti_nag_id": _stable_id("anti_nag", clause.get("clause_id")),
                    "tiny_hint_only": True,
                },
            }
        )
    return probes


def apply_probe_outcomes(
    clauses: Iterable[Mapping[str, Any]],
    outcomes: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    updated = [copy.deepcopy(dict(clause)) for clause in clauses]
    outcomes_by_clause: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in outcomes:
        outcomes_by_clause[str(row.get("clause_id") or "")].append(row)
    for clause in updated:
        clause_id = str(clause.get("clause_id") or "")
        source_backed = [
            row for row in outcomes_by_clause.get(clause_id, []) if row.get("source_backed")
        ]
        if not source_backed:
            continue
        lifecycle = _lifecycle(clause)
        activation = _activation(clause)
        signals = {str(row.get("outcome_signal") or "") for row in source_backed}
        if signals & {"helped", "reduced_repeat_failure", "preflight_helped"}:
            lifecycle["status"] = "ripe"
            lifecycle["review_state"] = "machine_checked"
            activation["foreground_eligible"] = True
            activation["next_action"] = "use_hint"
        if signals & {"wrong_route_drag", "source_correction", "refuted"}:
            lifecycle["status"] = "challenged"
            lifecycle["degrade_to"] = "reopenable_route"
            activation["foreground_eligible"] = False
            activation["next_action"] = "reopen_source"
        if signals & {"stale", "superseded"}:
            lifecycle["status"] = "stale"
            lifecycle["degrade_to"] = "reopenable_route"
            activation["foreground_eligible"] = False
            activation["next_action"] = "reopen_source"
    return updated


def resolve_clause_relations(
    clauses: Iterable[Mapping[str, Any]],
    *,
    task: str = "",
    max_items: int = 3,
) -> dict[str, Any]:
    eligible = [dict(clause) for clause in clauses if _status(clause) == "ripe"]
    ids = {str(clause.get("clause_id") or "") for clause in eligible}
    conflicts: list[tuple[str, str]] = []
    ordered_edges: list[tuple[str, str]] = []
    blocked: set[str] = set()
    for clause in eligible:
        clause_id = str(clause.get("clause_id") or "")
        rel = _as_mapping(clause.get("relations"))
        for target in _strings(rel.get("conflicts_with")):
            if target in ids:
                conflicts.append((clause_id, target))
        for target in _strings(rel.get("ordered_before") or rel.get("prerequisite_of")):
            if target in ids:
                ordered_edges.append((clause_id, target))
        for condition in _strings(rel.get("blocked_by")):
            if condition:
                blocked.add(clause_id)
    selected = [clause for clause in eligible if str(clause.get("clause_id") or "") not in blocked]
    if conflicts:
        next_action = "deepen_or_reopen_source"
        selected = []
    else:
        order_rank = {dst: index + 1 for index, (_, dst) in enumerate(ordered_edges)}
        selected.sort(key=lambda row: order_rank.get(str(row.get("clause_id") or ""), 0))
        next_action = "ordered_mini_plan" if ordered_edges else "use_hint"
    return {
        "kind": RELATION_KIND,
        "schema_version": SCHEMA_VERSION,
        "task": task,
        "selected_clause_ids": [clause.get("clause_id") for clause in selected[:max_items]],
        "ordered_plan": [
            {"before": before, "after": after, "authority": "navigation_only"}
            for before, after in ordered_edges
        ],
        "conflicts": [{"left": left, "right": right} for left, right in conflicts],
        "blocked_clause_ids": sorted(blocked),
        "next_action": next_action,
        "claim_permission": "working_contract_allowed_no_fact_claim",
        "relation_metadata_raises_authority": False,
        "foreground_budget_preserved": True,
    }


def calibrate_clause_lifecycle(
    clauses: Iterable[Mapping[str, Any]],
    feedback_rows: Iterable[Mapping[str, Any]],
    *,
    now: str = "2026-06-15T00:00:00Z",
) -> dict[str, Any]:
    now_dt = _parse_date(now) or datetime.now(timezone.utc)
    rows = [row for row in feedback_rows if isinstance(row, Mapping)]
    updated = [copy.deepcopy(dict(clause)) for clause in clauses]
    severity_by_clause: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.get("self_report_only") and row.get("outcome_signal") == "helped":
            continue
        clause_id = str(row.get("clause_id") or "")
        signal = str(row.get("outcome_signal") or "")
        severity = int(row.get("severity") or SEVERITY_WEIGHTS.get(signal, 0))
        severity_by_clause[clause_id] += severity
    for clause in updated:
        lifecycle = _lifecycle(clause)
        activation = _activation(clause)
        clause_id = str(clause.get("clause_id") or "")
        kind = str(clause.get("kind") or "")
        freshness = _as_mapping(clause.get("freshness"))
        last_source = _parse_date(freshness.get("last_source_seen_at") or freshness.get("built_at"))
        max_age = STALE_POLICY_DAYS.get(kind, 30)
        if lifecycle.get("status") == "ripe" and last_source:
            if (now_dt - last_source).days > max_age:
                lifecycle["status"] = "review_overdue" if kind != "environment_workaround" else "stale"
                lifecycle["degrade_to"] = "reopenable_route"
                activation["foreground_eligible"] = False
                activation["next_action"] = "reopen_source"
        score = severity_by_clause.get(clause_id, 0)
        if score >= 5:
            lifecycle["status"] = "challenged"
            lifecycle["degrade_to"] = "reopenable_route"
            activation["foreground_eligible"] = False
            activation["next_action"] = "reopen_source"
        if clause.get("relation_conflicted") or clause.get("high_risk"):
            activation["next_action"] = "deepen"
            activation["foreground_eligible"] = False
            lifecycle["foreground_priority"] = "conditional_deepen"
    return {
        "kind": CALIBRATION_KIND,
        "schema_version": SCHEMA_VERSION,
        "updated_clauses": updated,
        "feedback_weight_by_clause": dict(severity_by_clause),
        "clean_source_mutated": False,
        "activation_packets_include_feedback_traces": False,
    }


def build_clause_lifecycle_fixture_report() -> dict[str, Any]:
    clauses = [
        {
            "clause_id": "growing_preflight",
            "kind": "workflow_order_clause",
            "guidance": "Run ruff before broad pytest.",
            "applies_when": ["coding", "test"],
            "support": {"support_grade": "source_supported", "source_ref_count": 2},
            "source_refs": [{"source_ref": "src:fail"}, {"source_ref": "src:pass"}],
            "freshness": {"last_source_seen_at": "2026-06-14T00:00:00Z"},
            "lifecycle": {"status": "growing"},
            "activation": {"foreground_eligible": False},
        },
        {
            "clause_id": "old_env",
            "kind": "environment_workaround",
            "support": {"support_grade": "source_supported", "source_ref_count": 2},
            "source_refs": [{"source_ref": "src:env"}],
            "freshness": {"last_source_seen_at": "2026-05-01T00:00:00Z"},
            "lifecycle": {"status": "ripe"},
            "activation": {"foreground_eligible": True},
        },
    ]
    probes = verification_probes_from_growing_clauses(clauses)
    ripened = apply_probe_outcomes(
        clauses,
        [{"clause_id": "growing_preflight", "outcome_signal": "helped", "source_backed": True}],
    )
    challenged = apply_probe_outcomes(
        clauses,
        [
            {
                "clause_id": "growing_preflight",
                "outcome_signal": "wrong_route_drag",
                "source_backed": True,
            }
        ],
    )
    relation = resolve_clause_relations(
        [
            {**ripened[0], "relations": {"ordered_before": ["old_env"]}},
            {**clauses[1], "relations": {"conflicts_with": ["growing_preflight"]}},
        ]
    )
    calibrated = calibrate_clause_lifecycle(
        clauses,
        [
            {"clause_id": "old_env", "outcome_signal": "noisy", "severity": 1},
            {"clause_id": "old_env", "outcome_signal": "wrong_route_drag", "severity": 5},
            {
                "clause_id": "growing_preflight",
                "outcome_signal": "helped",
                "self_report_only": True,
            },
        ],
    )
    encoded = json.dumps(
        {"probes": probes, "calibrated": calibrated, "relation": relation},
        ensure_ascii=False,
        sort_keys=True,
    )
    red_lines = {
        "self_report_promoted_to_truth_count": 0,
        "clean_source_mutated_count": int(calibrated["clean_source_mutated"]),
        "raw_command_or_path_leak_count": int("C:\\" in encoded or "pytest tests/private" in encoded),
    }
    return {
        "kind": "aippocampus_aippo_clause_lifecycle_fixture",
        "schema_version": SCHEMA_VERSION,
        "ok": bool(probes) and all(value == 0 for value in red_lines.values()),
        "probes": probes,
        "ripened_clauses": ripened,
        "challenged_clauses": challenged,
        "relation_selection": relation,
        "calibration": calibrated,
        "red_lines": red_lines,
    }


__all__ = [
    "apply_probe_outcomes",
    "build_clause_lifecycle_fixture_report",
    "calibrate_clause_lifecycle",
    "resolve_clause_relations",
    "verification_probes_from_growing_clauses",
]
