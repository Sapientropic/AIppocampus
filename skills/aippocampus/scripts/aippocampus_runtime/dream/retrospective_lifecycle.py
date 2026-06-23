#!/usr/bin/env python3
"""Retrospective lifecycle for future-facing dream probes.

Prospective and active-imagination probes can point beyond the source that
created them. This runner parks them until their review horizon, then compares
them only with later source-backed rows that explicitly target the probe. Term
overlap is diagnostic noise, not support.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.dream import precision_policy as precision
from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows

LIFECYCLE_KIND = "aippocampus_dream_retrospective_lifecycle"
SUMMARY_KIND = "aippocampus_dream_retrospective_lifecycle_summary"
ELIGIBLE_DREAM_FUNCTIONS = {"prospective", "active_imagination"}
REGISTRY_LATER_ROW_FILES = (
    "dream_findings.jsonl",
    "working_memory.jsonl",
    "subconscious_jobs.jsonl",
    "promotion_candidates.jsonl",
    "correction_events.jsonl",
    "coding_decision_events.jsonl",
    "question_resolution_events.jsonl",
)


def load_retrospective_rows(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    return load_jsonl_dict_rows(path).rows


def probe_id(probe: Mapping[str, Any]) -> str:
    return str(probe.get("dream_finding_id") or probe.get("fingerprint") or probe.get("id") or "")


def is_retrospective_probe(probe: Mapping[str, Any]) -> bool:
    if probe.get("finding_kind") != precision.DREAM_FINDING_KIND:
        return False
    return str(probe.get("dream_function") or "") in ELIGIBLE_DREAM_FUNCTIONS


def row_created_at(row: Mapping[str, Any]) -> Any:
    return precision.parse_utc(row.get("created_at") or row.get("updated_at") or row.get("timestamp"))


def probe_created_at(probe: Mapping[str, Any]) -> Any:
    return precision.parse_utc(probe.get("created_at"))


def review_due(probe: Mapping[str, Any], *, now: str | Any | None = None) -> bool:
    now_dt = precision.normalize_now(now)
    review_after = precision.parse_utc(probe.get("review_after"))
    if review_after:
        return review_after <= now_dt
    expires_at = precision.parse_utc(probe.get("expires_at"))
    return bool(expires_at and expires_at <= now_dt)


def row_mentions_project(row: Mapping[str, Any], project: str | None) -> bool:
    if not project:
        return True
    wanted = project.casefold()
    labels = [row.get("project_label")]
    for ref in row.get("source_refs") or []:
        if isinstance(ref, Mapping):
            labels.append(ref.get("project_label"))
    return any(wanted == str(label or "").casefold() for label in labels)


def term_overlap_without_target(probe: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    if probe_id(probe) in precision.validation_targets(row):
        return False
    probe_terms = set(
        precision.text_terms(" ".join([str(probe.get("title") or ""), str(probe.get("summary") or ""), probe_id(probe)]))
    )
    row_terms = set(precision.text_terms(" ".join([str(row.get("title") or ""), str(row.get("summary") or "")])))
    return bool(probe_terms and row_terms and probe_terms & row_terms)


def eligible_later_rows_for_probe(
    probe: Mapping[str, Any],
    later_rows: Iterable[Mapping[str, Any]],
    *,
    now: str | Any | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    now_dt = precision.normalize_now(now)
    created_at = probe_created_at(probe)
    target_id = probe_id(probe)
    eligible: list[dict[str, Any]] = []
    window = {
        "ignored_before_probe": 0,
        "ignored_after_now": 0,
        "term_overlap_without_target": 0,
    }
    for row in later_rows:
        if not isinstance(row, Mapping):
            continue
        row_dt = row_created_at(row)
        if target_id not in precision.validation_targets(row):
            if term_overlap_without_target(probe, row):
                window["term_overlap_without_target"] += 1
            continue
        if row_dt and created_at and row_dt <= created_at:
            window["ignored_before_probe"] += 1
            continue
        if row_dt and row_dt > now_dt:
            window["ignored_after_now"] += 1
            continue
        eligible.append(dict(row))
    return eligible, window


def evidence_kind_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row.get("kind") or "unknown") for row in rows)
    return dict(sorted(counts.items()))


def lifecycle_item(
    probe: Mapping[str, Any],
    later_rows: Iterable[Mapping[str, Any]],
    *,
    now: str | Any | None = None,
) -> dict[str, Any]:
    finding_id = probe_id(probe)
    if not review_due(probe, now=now):
        return {
            "finding_id": finding_id,
            "dream_function": probe.get("dream_function"),
            "lifecycle_status": "parked_pending_review",
            "review_after": probe.get("review_after"),
            "expires_at": probe.get("expires_at"),
            "retrospective_policy": {"status": "parked_pending_review"},
            "window": {
                "ignored_before_probe": 0,
                "ignored_after_now": 0,
                "term_overlap_without_target": 0,
            },
            "evidence_kind_counts": {},
        }
    eligible_rows, window = eligible_later_rows_for_probe(probe, later_rows, now=now)
    policy = precision.retrospective_policy_for_probe(probe, eligible_rows, now=now)
    status = str(policy["retrospective_policy"]["status"])
    return {
        "finding_id": finding_id,
        "dream_function": probe.get("dream_function"),
        "probe_family": probe.get("probe_family"),
        "lifecycle_status": status,
        "review_after": probe.get("review_after"),
        "expires_at": probe.get("expires_at"),
        "retrospective_policy": dict(policy["retrospective_policy"]),
        "window": window,
        "evidence_kind_counts": evidence_kind_counts(eligible_rows),
    }


def run_retrospective_lifecycle(
    probes: Iterable[Mapping[str, Any]],
    later_rows: Iterable[Mapping[str, Any]],
    *,
    now: str | Any | None = None,
) -> dict[str, Any]:
    items = [
        lifecycle_item(probe, later_rows, now=now)
        for probe in probes
        if isinstance(probe, Mapping) and is_retrospective_probe(probe)
    ]
    counts = Counter(str(item.get("lifecycle_status") or "") for item in items)
    return {
        "schema_version": 1,
        "kind": LIFECYCLE_KIND,
        "created_at": precision.normalize_now(now).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "items": items,
        "counts": dict(sorted(counts.items())),
        "policy": {
            "requires_explicit_target_id": True,
            "term_overlap_counts_as_support": False,
            "future_rows_after_now_are_ignored": True,
            "pre_probe_rows_are_ignored": True,
        },
    }


def public_lifecycle_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": SUMMARY_KIND,
        "status_counts": dict(payload.get("counts") or {}),
        "item_count": len(payload.get("items") or []),
        "policy": {
            "requires_explicit_target_id": True,
            "term_overlap_counts_as_support": False,
            "public_output_omits_private_handles": True,
        },
    }


def load_registry_rows(root: Path, *, project: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in REGISTRY_LATER_ROW_FILES:
        for row in load_retrospective_rows(root / name):
            if row_mentions_project(row, project):
                rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run retrospective lifecycle for parked dream probes.")
    parser.add_argument("--registry-dir", type=Path)
    parser.add_argument("--project")
    parser.add_argument("--probes-jsonl", type=Path)
    parser.add_argument("--later-jsonl", type=Path)
    parser.add_argument("--now", default=now_utc())
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    root = Path(args.registry_dir).resolve() if args.registry_dir else None
    probes = load_retrospective_rows(args.probes_jsonl or (root / "dream_findings.jsonl" if root else None))
    later_rows = (
        load_retrospective_rows(args.later_jsonl)
        if args.later_jsonl
        else (load_registry_rows(root, project=args.project) if root else [])
    )
    payload = run_retrospective_lifecycle(probes, later_rows, now=args.now)
    output = public_lifecycle_summary(payload) if args.summary else payload
    print(json.dumps(output, ensure_ascii=False, indent=None if args.json_output else 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
