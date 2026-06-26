#!/usr/bin/env python3
"""Privacy-safe utility telemetry for concept-graph expansions.

These events measure whether a graph expansion later helped route recall. They
are ranking-policy diagnostics only: they never mutate edge weights and never
turn graph proximity into source evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.navigation.associations import normalize_term
from aippocampus_runtime.registry.api import registry_paths
from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows

SCHEMA_VERSION = 1
EVENT_KIND = "aippocampus_concept_edge_utility_event"
REPORT_KIND = "aippocampus_concept_edge_utility_report"
DEFAULT_EVENTS_FILENAME = "concept_edge_utility_events.jsonl"

SUPPORTED_OUTCOMES = {
    "source_reopen_success",
    "source_reopen",
    "useful_match",
    "correction",
    "skip",
}
FAILURE_OUTCOMES = {"correction", "skip"}
SUPPORTED_STATUSES = {"verified", "staging", "parked", "retired", "blocked", "unknown"}
SUPPORTED_EDGE_TYPES = {
    "alias",
    "verified_related",
    "same_decision_space",
    "decision_about",
    "project_topic",
    "depends_on",
    "contrasts_with",
    "supersedes",
    "related",
    "co_occurs",
}
SAFE_TOKEN_RE = re.compile(r"[^a-z0-9_:-]+")


def default_concept_edge_utility_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_EVENTS_FILENAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_EVENTS_FILENAME


def score_bucket(score: float) -> str:
    value = max(0.0, min(1.0, float(score or 0.0)))
    if value < 0.15:
        return "very_low"
    if value < 0.4:
        return "low"
    if value < 0.7:
        return "medium"
    if value < 0.9:
        return "high"
    return "very_high"


def depth_bucket(depth: int | None) -> str:
    if depth is None:
        return "unknown"
    value = max(0, int(depth))
    if value <= 1:
        return "depth_1"
    if value == 2:
        return "depth_2"
    return "depth_3_plus"


def _safe_token(value: Any, *, default: str = "unknown") -> str:
    token = str(value or "").strip().casefold().replace(" ", "_")
    token = SAFE_TOKEN_RE.sub("_", token).strip("_")
    return token or default


def _hash_text(value: Any) -> str:
    normalized = normalize_term(str(value or "")).casefold()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return f"sha256:{digest}"


def _hashed_bucket(value: Any, *, prefix: str) -> str:
    text = normalize_term(str(value or ""))
    if not text:
        return "none"
    return f"{prefix}:{_hash_text(text)}"


def _safe_edge_type(value: Any) -> str:
    token = _safe_token(value)
    if token in SUPPORTED_EDGE_TYPES:
        return token
    if not str(value or "").strip():
        return "unknown"
    return f"custom:{_hash_text(value)}"


def _seed_term_class(value: Any) -> str:
    text = str(value or "")
    if not text:
        return "empty"
    has_ascii = any(ord(char) < 128 and char.isalnum() for char in text)
    has_cjk = any("\u4e00" <= char <= "\u9fff" for char in text)
    if has_ascii and has_cjk:
        return "mixed"
    if has_cjk:
        return "cjk"
    if has_ascii:
        return "ascii"
    return "other"


def _signal_flags(outcome: str) -> dict[str, bool]:
    return {
        "led_to_source_reopen": outcome in {"source_reopen", "source_reopen_success"},
        "led_to_useful_match": outcome in {"useful_match", "source_reopen_success"},
        "led_to_correction": outcome == "correction",
        "led_to_skip": outcome == "skip",
    }


def concept_edge_utility_source_boundary() -> dict[str, bool]:
    return {
        "edge_utility_is_navigation_only": True,
        "edge_weights_are_ranking_priors": True,
        "edge_utility_is_not_source_evidence": True,
        "raw_prompt_text_serialized": False,
        "raw_source_text_serialized": False,
        "local_paths_serialized": False,
    }


def build_edge_utility_event(
    *,
    seed_term: str,
    edge_type: str,
    edge_status: str,
    score: float,
    outcome: str,
    project_bucket: str | None = None,
    domain_bucket: str | None = None,
    depth: int | None = None,
) -> dict[str, Any]:
    normalized_outcome = _safe_token(outcome)
    if normalized_outcome not in SUPPORTED_OUTCOMES:
        normalized_outcome = "skip"
    normalized_status = _safe_token(edge_status)
    if normalized_status not in SUPPORTED_STATUSES:
        normalized_status = "unknown"
    normalized_edge_type = _safe_edge_type(edge_type)
    event = {
        "schema_version": SCHEMA_VERSION,
        "kind": EVENT_KIND,
        "created_at": now_utc(),
        "seed_term_hash": _hash_text(seed_term),
        "seed_term_class": _seed_term_class(seed_term),
        "edge_type": normalized_edge_type,
        "edge_status": normalized_status,
        "score_bucket": score_bucket(score),
        "depth_bucket": depth_bucket(depth),
        "outcome": normalized_outcome,
        "project_bucket": _hashed_bucket(project_bucket, prefix="project"),
        "domain_bucket": _hashed_bucket(domain_bucket, prefix="domain"),
        "source_boundary": concept_edge_utility_source_boundary(),
    }
    event.update(_signal_flags(normalized_outcome))
    identity = json.dumps(
        {
            key: value
            for key, value in event.items()
            if key not in {"created_at", "source_boundary"}
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    event["event_id"] = "ceut_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return event


def record_edge_utility_event(
    events_path: Path,
    *,
    seed_term: str,
    edge_type: str,
    edge_status: str,
    score: float,
    outcome: str,
    project_bucket: str | None = None,
    domain_bucket: str | None = None,
    depth: int | None = None,
) -> dict[str, Any]:
    event = build_edge_utility_event(
        seed_term=seed_term,
        edge_type=edge_type,
        edge_status=edge_status,
        score=score,
        outcome=outcome,
        project_bucket=project_bucket,
        domain_bucket=domain_bucket,
        depth=depth,
    )
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return event


def iter_edge_utility_events(events_path: Path) -> list[dict[str, Any]]:
    if not events_path.exists():
        return []
    return [row for row in load_jsonl_dict_rows(events_path).rows if row.get("kind") == EVENT_KIND]


def _empty_group() -> dict[str, int]:
    return {
        "event_count": 0,
        "source_reopen_success_count": 0,
        "source_reopen_count": 0,
        "useful_match_count": 0,
        "correction_count": 0,
        "skip_count": 0,
    }


def _add_to_group(groups: dict[str, dict[str, int]], key: str, row: dict[str, Any]) -> None:
    group = groups.setdefault(key, _empty_group())
    outcome = _safe_token(row.get("outcome"))
    group["event_count"] += 1
    if outcome == "source_reopen_success":
        group["source_reopen_success_count"] += 1
    if bool(row.get("led_to_source_reopen")):
        group["source_reopen_count"] += 1
    if bool(row.get("led_to_useful_match")):
        group["useful_match_count"] += 1
    if bool(row.get("led_to_correction")):
        group["correction_count"] += 1
    if bool(row.get("led_to_skip")):
        group["skip_count"] += 1


def _sorted_groups(groups: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    return {key: groups[key] for key in sorted(groups)}


def build_edge_utility_report(events_path: Path) -> dict[str, Any]:
    rows = iter_edge_utility_events(events_path)
    by_edge_type: dict[str, dict[str, int]] = {}
    by_status: dict[str, dict[str, int]] = {}
    by_score_bucket: dict[str, dict[str, int]] = {}
    by_project_bucket: dict[str, dict[str, int]] = {}
    by_domain_bucket: dict[str, dict[str, int]] = {}
    failure_modes = {outcome: 0 for outcome in sorted(FAILURE_OUTCOMES)}
    matrix: dict[str, dict[str, dict[str, dict[str, int]]]] = {}
    for row in rows:
        edge_type = _safe_token(row.get("edge_type"))
        status = _safe_token(row.get("edge_status"))
        bucket = _safe_token(row.get("score_bucket"))
        project_bucket = _safe_token(row.get("project_bucket"), default="none")
        domain_bucket = _safe_token(row.get("domain_bucket"), default="none")
        outcome = _safe_token(row.get("outcome"))
        _add_to_group(by_edge_type, edge_type, row)
        _add_to_group(by_status, status, row)
        _add_to_group(by_score_bucket, bucket, row)
        _add_to_group(by_project_bucket, project_bucket, row)
        _add_to_group(by_domain_bucket, domain_bucket, row)
        if outcome in failure_modes:
            failure_modes[outcome] += 1
        bucket_group = matrix.setdefault(edge_type, {}).setdefault(status, {}).setdefault(
            bucket, _empty_group()
        )
        _add_to_group({bucket: bucket_group}, bucket, row)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "event_count": len(rows),
        "by_edge_type": _sorted_groups(by_edge_type),
        "by_status": _sorted_groups(by_status),
        "by_score_bucket": _sorted_groups(by_score_bucket),
        "by_project_bucket": _sorted_groups(by_project_bucket),
        "by_domain_bucket": _sorted_groups(by_domain_bucket),
        "edge_type_status_score_buckets": {
            edge_type: {
                status: {
                    bucket: status_groups[status][bucket]
                    for bucket in sorted(status_groups[status])
                }
                for status in sorted(status_groups)
            }
            for edge_type, status_groups in sorted(matrix.items())
        },
        "failure_modes": failure_modes,
        "policy": {
            "mutates_edge_type_multipliers": False,
            "automatic_weight_learning": False,
            "use": "offline evidence for a later explicit scoring-policy change",
        },
        "source_boundary": concept_edge_utility_source_boundary(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events")
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--seed-term")
    parser.add_argument("--edge-type")
    parser.add_argument("--edge-status", default="unknown")
    parser.add_argument("--score", type=float, default=0.0)
    parser.add_argument("--outcome", choices=sorted(SUPPORTED_OUTCOMES))
    parser.add_argument("--project-bucket")
    parser.add_argument("--domain-bucket")
    parser.add_argument("--depth", type=int)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    registry_path = (
        Path(args.registry).resolve()
        if args.registry
        else registry_paths(Path(args.registry_dir).resolve() if args.registry_dir else None)[0]
    )
    events_path = (
        Path(args.events).resolve()
        if args.events
        else default_concept_edge_utility_path(registry_path=registry_path)
    )
    if args.record:
        if not args.seed_term or not args.edge_type or not args.outcome:
            parser.error("--record requires --seed-term, --edge-type, and --outcome")
        payload = record_edge_utility_event(
            events_path,
            seed_term=args.seed_term,
            edge_type=args.edge_type,
            edge_status=args.edge_status,
            score=args.score,
            outcome=args.outcome,
            project_bucket=args.project_bucket,
            domain_bucket=args.domain_bucket,
            depth=args.depth,
        )
    else:
        payload = build_edge_utility_report(events_path)
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    elif args.record:
        print(f"recorded {payload['event_id']} -> {events_path}")
    else:
        print(f"events: {payload['event_count']}")
        for edge_type, group in payload["by_edge_type"].items():
            print(f"- {edge_type}: {group['event_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
