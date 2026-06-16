#!/usr/bin/env python3
"""Public-safe diagnostic meta-calibration report for navigation signals.

The report is deliberately no-write. It compares diagnostic families against
fixture labels only when a family has a meaningful denominator, separates
safety gates from quality gates, and keeps runtime weighting unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import _paths
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _paths

_paths.ensure_paths()

from aippocampus_runtime.navigation.local_global_compatibility import (  # noqa: E402
    build_local_global_compatibility_report,
)

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_diagnostic_meta_calibration_report"
DEFAULT_MIN_DENOMINATOR = 2
FAMILIES = (
    "local_global_compatibility",
    "dream_topology",
    "precision_pressure",
    "attention_semantic_route",
    "macro_yi",
    "learning_loop_action_hint",
)
FORBIDDEN_MARKERS = ("C:\\", "/Users/", "PRIVATE_", "raw_private_source_text", "secret-token")


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fixture_rows() -> list[dict[str, Any]]:
    return [
        {
            "family": "local_global_compatibility",
            "case_id": "lg-glue",
            "predicted": "safe_navigation",
            "label": "safe_navigation",
            "safety_gate": "pass",
            "quality_gate": "useful",
        },
        {
            "family": "local_global_compatibility",
            "case_id": "lg-blocked",
            "predicted": "blocked_boundary",
            "label": "blocked_boundary",
            "safety_gate": "pass",
            "quality_gate": "useful",
        },
        {
            "family": "dream_topology",
            "case_id": "dream-shadow",
            "predicted": "shadowed_route",
            "label": "shadowed_route",
            "safety_gate": "pass",
            "quality_gate": "useful",
        },
        {
            "family": "dream_topology",
            "case_id": "dream-overreach",
            "predicted": "foreground_fact",
            "label": "shadowed_route",
            "safety_gate": "fail",
            "quality_gate": "wrong_route",
        },
        {
            "family": "precision_pressure",
            "case_id": "precision-high",
            "predicted": "deepen_before_claim",
            "label": "deepen_before_claim",
            "safety_gate": "pass",
            "quality_gate": "useful",
        },
        {
            "family": "precision_pressure",
            "case_id": "precision-low",
            "predicted": "direction_only",
            "label": "direction_only",
            "safety_gate": "pass",
            "quality_gate": "useful",
        },
        {
            "family": "attention_semantic_route",
            "case_id": "semantic-reopen",
            "predicted": "reopen_first",
            "label": "reopen_first",
            "safety_gate": "pass",
            "quality_gate": "useful",
        },
        {
            "family": "attention_semantic_route",
            "case_id": "semantic-wrong",
            "predicted": "reopen_first",
            "label": "hold_back",
            "safety_gate": "pass",
            "quality_gate": "wrong_route",
        },
        {
            "family": "macro_yi",
            "case_id": "macro-single",
            "predicted": "review",
            "label": "review",
            "safety_gate": "pass",
            "quality_gate": "useful",
        },
        {
            "family": "learning_loop_action_hint",
            "case_id": "learning-preflight",
            "predicted": "run_preflight",
            "label": "run_preflight",
            "safety_gate": "pass",
            "quality_gate": "useful",
        },
        {
            "family": "learning_loop_action_hint",
            "case_id": "learning-stale",
            "predicted": "run_preflight",
            "label": "hold_back",
            "safety_gate": "pass",
            "quality_gate": "wrong_route",
        },
    ]


def _label(row: Mapping[str, Any], key: str) -> str:
    return str(row.get(key) or "").strip()


def _family_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        family = _label(row, "family")
        if family:
            grouped[family].append(row)
    return grouped


def _family_report(rows: Sequence[Mapping[str, Any]], *, min_denominator: int) -> dict[str, Any]:
    labeled = [row for row in rows if _label(row, "label")]
    denominator = len(labeled)
    safety_counts = Counter(_label(row, "safety_gate") or "unknown" for row in rows)
    quality_counts = Counter(_label(row, "quality_gate") or "unknown" for row in rows)
    if denominator < min_denominator:
        return {
            "status": "not_enough_evidence",
            "denominator": denominator,
            "min_denominator": min_denominator,
            "safety_gate_counts": dict(sorted(safety_counts.items())),
            "quality_gate_counts": dict(sorted(quality_counts.items())),
            "metrics": {},
            "review_recommendation": "collect_more_fixture_labels_before_calibrating",
        }
    correct = sum(1 for row in labeled if _label(row, "predicted") == _label(row, "label"))
    safety_failures = safety_counts.get("fail", 0)
    wrong_routes = quality_counts.get("wrong_route", 0)
    return {
        "status": "measured_fixture_only",
        "denominator": denominator,
        "min_denominator": min_denominator,
        "safety_gate_counts": dict(sorted(safety_counts.items())),
        "quality_gate_counts": dict(sorted(quality_counts.items())),
        "metrics": {
            "fixture_accuracy": round(correct / denominator, 6),
            "safety_failure_rate": round(safety_failures / max(1, len(rows)), 6),
            "wrong_route_rate": round(wrong_routes / max(1, len(rows)), 6),
        },
        "review_recommendation": "review_failures_before_runtime_weight_changes"
        if safety_failures or wrong_routes
        else "no_runtime_change_recommended",
    }


def _safe_file_label(path: Path) -> dict[str, Any]:
    name = path.name
    digest = "sha1:" + hashlib.sha1(name.encode("utf-8", errors="replace")).hexdigest()[:12]
    return {"label": name[:120], "fingerprint": digest}


def _load_json_or_jsonl(path: Path) -> list[Mapping[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("[") or text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
        if isinstance(data, list):
            return [row for row in data if isinstance(row, Mapping)]
        if isinstance(data, Mapping):
            nested = data.get("rows") or data.get("fixtures") or data.get("cases") or []
            if nested:
                return [row for row in nested if isinstance(row, Mapping)]
            return [data]
        return []
    rows: list[Mapping[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, Mapping):
            rows.append(item)
    return rows


def _feedback_row_to_meta(row: Mapping[str, Any]) -> dict[str, Any] | None:
    outcome = str(row.get("outcome") or row.get("signal") or "").strip()
    if not outcome:
        return None
    negative = outcome in {"wrong_route_drag", "wrong_route", "blocked", "superseded", "expired", "ignored"}
    positive = outcome in {"source_reopen_success", "reopened_deepened", "user_confirmed", "prevented_failure"}
    if not (negative or positive):
        return None
    route_id = str(row.get("candidate_id") or row.get("route_id") or row.get("source_id") or "route-feedback")
    return {
        "family": "attention_semantic_route",
        "case_id": "route_feedback_" + hashlib.sha1(route_id.encode("utf-8", errors="replace")).hexdigest()[:12],
        "predicted": "reopen_first",
        "label": "hold_back" if negative else "reopen_first",
        "safety_gate": "pass",
        "quality_gate": "wrong_route" if negative else "useful",
    }


def load_dated_evidence_rows(
    report_paths: Sequence[Path] | None = None,
    feedback_paths: Sequence[Path] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    families = Counter()
    for path in report_paths or []:
        loaded = [dict(row) for row in _load_json_or_jsonl(path)]
        rows.extend(loaded)
        files.append({**_safe_file_label(path), "row_family": "dated_report_rows", "row_count": len(loaded)})
    for path in feedback_paths or []:
        converted = [
            converted
            for row in _load_json_or_jsonl(path)
            if (converted := _feedback_row_to_meta(row)) is not None
        ]
        rows.extend(converted)
        files.append({**_safe_file_label(path), "row_family": "route_feedback_rows", "row_count": len(converted)})
    for row in rows:
        families[str(row.get("family") or "unknown")] += 1
    return rows, {
        "mode": "dated_evidence",
        "row_count": len(rows),
        "files": files,
        "row_families": dict(sorted(families.items())),
        "safe_labels_only": True,
    }


def build_diagnostic_meta_calibration_report(
    rows: Iterable[Mapping[str, Any]] | None = None,
    *,
    min_denominator: int = DEFAULT_MIN_DENOMINATOR,
    evidence_mode: str = "fixture",
    evidence_intake: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    materialized = list(rows) if rows is not None else fixture_rows()
    dated_mode = evidence_mode == "dated" or bool(evidence_intake)
    grouped = _family_rows(materialized)
    local_global = build_local_global_compatibility_report()
    family_reports = {
        family: _family_report(grouped.get(family, []), min_denominator=min_denominator)
        for family in FAMILIES
    }
    if dated_mode:
        for report in family_reports.values():
            if report["status"] == "measured_fixture_only":
                report["status"] = "measured_dated_evidence"
    encoded = json.dumps({"rows": materialized, "families": family_reports}, ensure_ascii=False, sort_keys=True)
    forbidden_count = sum(1 for marker in FORBIDDEN_MARKERS if marker in encoded)
    safety_fail_count = sum(
        int(report["safety_gate_counts"].get("fail", 0))
        for report in family_reports.values()
    )
    measured_count = sum(1 for report in family_reports.values() if report["status"] == "measured_fixture_only")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "created_at": now_utc(),
        "ok": forbidden_count == 0,
        "status": "dated_evidence_meta_calibration" if dated_mode else "fixture_meta_calibration",
        "min_denominator": min_denominator,
        "evidence_intake": dict(evidence_intake or {"mode": "fixture", "row_count": len(materialized), "files": []}),
        "family_reports": family_reports,
        "local_global_compatibility_fixture": {
            "ok": local_global["ok"],
            "metrics": local_global["metrics"],
            "runtime_boundary": local_global["runtime_boundary"],
            "authority_level": local_global["authority_level"],
            "claim_permission": local_global["claim_permission"],
        },
        "metrics": {
            "family_count": len(FAMILIES),
            "measured_family_count": measured_count,
            "not_enough_evidence_family_count": len(FAMILIES) - measured_count,
            "safety_failure_count": safety_fail_count,
            "runtime_weight_change_count": 0,
        },
        "policy_boundary": {
            "report_only": True,
            "runtime_weights_changed": False,
            "hard_masks_learned": False,
            "claim_permission_changed": False,
            "passing_meta_calibration_is_not_answer_truth": True,
        },
        "privacy_boundary": {
            "raw_prompts_emitted": False,
            "private_source_text_emitted": False,
            "local_paths_emitted": False,
            "forbidden_marker_count": forbidden_count,
        },
        "cannot_claim": [
            "answer_truth_from_meta_calibration",
            "diagnostic_meta_calibration_is_not_answer_truth",
            "runtime_weight_update",
            "private_history_quality",
            "benchmark_generalization_from_fixture_labels",
        ],
    }


def load_rows(path: Path) -> list[Mapping[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [row for row in data if isinstance(row, Mapping)]
    if isinstance(data, Mapping):
        nested = data.get("rows") or data.get("fixtures") or []
        return [row for row in nested if isinstance(row, Mapping)]
    return []


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--evidence-report", type=Path, action="append", default=[])
    parser.add_argument("--feedback-jsonl", type=Path, action="append", default=[])
    parser.add_argument("--min-denominator", type=int, default=DEFAULT_MIN_DENOMINATOR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    dated_rows: list[dict[str, Any]] | None = None
    intake: dict[str, Any] | None = None
    if args.evidence_report or args.feedback_jsonl:
        dated_rows, intake = load_dated_evidence_rows(args.evidence_report, args.feedback_jsonl)
    payload = build_diagnostic_meta_calibration_report(
        dated_rows if dated_rows is not None else load_rows(args.input) if args.input else None,
        min_denominator=args.min_denominator,
        evidence_mode="dated" if dated_rows is not None else "fixture",
        evidence_intake=intake,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("diagnostic meta-calibration: " + ("ok" if payload["ok"] else "blocked"))
        print(f"families measured: {payload['metrics']['measured_family_count']}")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
