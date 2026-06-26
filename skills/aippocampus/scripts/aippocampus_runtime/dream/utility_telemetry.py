#!/usr/bin/env python3
"""Privacy-safe utility telemetry for adjudicated Dream hypotheses.

These events are calibration evidence only. They let maintainers compare later
utility against the deterministic `conservative_v1` retention decision without
copying prompts, source excerpts, model payloads, or changing retention
coefficients online.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows

SCHEMA_VERSION = 1
EVENT_KIND = "aippocampus_dream_utility_event"
REPORT_KIND = "aippocampus_dream_utility_report"
DEFAULT_EVENTS_FILENAME = "dream_utility_events.jsonl"

SUPPORTED_DREAM_FUNCTIONS = {
    "active_imagination",
    "amplification",
    "compensatory",
    "constructive_draft",
    "prospective",
}
SUPPORTED_OUTCOMES = {
    "matched",
    "delivered",
    "used_quietly",
    "source_reopened",
    "ignored",
    "corrected",
    "later_supported",
    "later_refuted",
    "expired_unused",
}
SUPPORTED_CANDIDATE_KINDS = {
    "blind_spot",
    "bridge_concept",
    "cross_thread_resonance",
    "emergence_signal",
    "route_hypothesis",
    "synthesis_hypothesis",
    "trajectory_hint",
}
SUPPORTED_SOURCE_FAMILIES = {
    "private_dogfood",
    "public_coding_agent_trajectory",
    "public_e2e50_fixture",
    "public_memoryagentbench_fixture",
    "public_vcs_hard_event",
    "synthetic_public_safe",
}
SUPPORTED_RETENTION_DECISIONS = {
    "retain_for_review",
    "park_for_review",
    "drop_low_pressure",
    "unknown",
}
REQUIRED_PUBLIC_FIXTURE_BUCKETS = {
    "retained_unused",
    "dropped_later_useful",
    "retained_later_refuted",
    "expired_unused",
}
USEFUL_OUTCOMES = {"matched", "delivered", "used_quietly", "source_reopened", "later_supported"}
REFUTED_OUTCOMES = {"corrected", "later_refuted"}
SAFE_TOKEN_RE = re.compile(r"[^a-z0-9_:-]+")


def _safe_token(value: Any, *, default: str = "unknown") -> str:
    token = str(value or "").strip().casefold().replace(" ", "_")
    token = SAFE_TOKEN_RE.sub("_", token).strip("_")
    return token or default


def _hash_text(value: Any) -> str:
    text = str(value or "")
    digest = hashlib.sha256(text.casefold().encode("utf-8", errors="replace")).hexdigest()[:24]
    return f"sha256:{digest}"


def _safe_enum_or_hash(value: Any, allowed: set[str], *, default: str = "unknown") -> str:
    token = _safe_token(value, default=default)
    if token in allowed:
        return token
    if not str(value or "").strip():
        return default
    return f"custom:{_hash_text(value)}"


def value_bucket(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if number != number or number in {float("inf"), float("-inf")}:
        return "unknown"
    number = max(0.0, min(1.0, number))
    if number < 0.15:
        return "very_low"
    if number < 0.4:
        return "low"
    if number < 0.7:
        return "medium"
    if number < 0.9:
        return "high"
    return "very_high"


def dream_utility_source_boundary() -> dict[str, bool]:
    return {
        "raw_prompt_text_serialized": False,
        "raw_source_text_serialized": False,
        "external_model_payload_serialized": False,
        "local_paths_serialized": False,
        "dream_utility_is_calibration_evidence": True,
        "dream_utility_is_not_causal_lift_evidence": True,
    }


def _component_value_buckets(retention_policy: Mapping[str, Any]) -> dict[str, str]:
    raw_components = retention_policy.get("raw_components")
    if not isinstance(raw_components, Mapping):
        return {}
    buckets: dict[str, str] = {}
    for key, component in raw_components.items():
        if not isinstance(component, Mapping):
            continue
        buckets[_safe_token(key)] = value_bucket(component.get("value"))
    return {key: buckets[key] for key in sorted(buckets)}


def _is_public_source_family(source_family: str) -> bool:
    return source_family.startswith("public_") or source_family.startswith("synthetic_public")


def _safe_source_family(value: Any) -> str:
    return _safe_enum_or_hash(value, SUPPORTED_SOURCE_FAMILIES)


def _safe_fixture_bucket(value: Any) -> str:
    token = _safe_token(value, default="unclassified")
    if token in REQUIRED_PUBLIC_FIXTURE_BUCKETS:
        return token
    return "unclassified"


def _empty_group() -> dict[str, int]:
    return {
        "event_count": 0,
        "matched_count": 0,
        "delivered_count": 0,
        "used_quietly_count": 0,
        "source_reopened_count": 0,
        "ignored_count": 0,
        "corrected_count": 0,
        "later_supported_count": 0,
        "later_refuted_count": 0,
        "expired_unused_count": 0,
        "useful_outcome_count": 0,
        "refuted_outcome_count": 0,
    }


def _add_to_group(groups: dict[str, dict[str, int]], key: str, row: Mapping[str, Any]) -> None:
    group = groups.setdefault(key, _empty_group())
    outcome = _safe_token(row.get("outcome"))
    group["event_count"] += 1
    counter = f"{outcome}_count"
    if counter in group:
        group[counter] += 1
    if outcome in USEFUL_OUTCOMES:
        group["useful_outcome_count"] += 1
    if outcome in REFUTED_OUTCOMES:
        group["refuted_outcome_count"] += 1


def _sorted_groups(groups: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    return {key: groups[key] for key in sorted(groups)}


def _calibration_signal_for(row: Mapping[str, Any]) -> str | None:
    decision = _safe_token(row.get("retention_decision"))
    outcome = _safe_token(row.get("outcome"))
    if decision == "retain_for_review" and outcome == "ignored":
        return "retained_unused"
    if decision in {"drop_low_pressure", "park_for_review"} and outcome in USEFUL_OUTCOMES:
        return "dropped_later_useful"
    if decision == "retain_for_review" and outcome in REFUTED_OUTCOMES:
        return "retained_later_refuted"
    if outcome == "expired_unused":
        return "expired_unused"
    return None


def build_dream_utility_event(
    *,
    dream_hypothesis_id: str,
    dream_function: str,
    candidate_kind: str,
    outcome: str,
    retention_policy: Mapping[str, Any],
    source_family: str,
    utility_fixture_bucket: str | None = None,
) -> dict[str, Any]:
    normalized_outcome = _safe_enum_or_hash(outcome, SUPPORTED_OUTCOMES)
    if normalized_outcome.startswith("custom:"):
        normalized_outcome = "ignored"
    retention_decision = _safe_enum_or_hash(
        retention_policy.get("decision"),
        SUPPORTED_RETENTION_DECISIONS,
    )
    event = {
        "schema_version": SCHEMA_VERSION,
        "kind": EVENT_KIND,
        "created_at": now_utc(),
        "dream_hypothesis_id_hash": _hash_text(dream_hypothesis_id),
        "dream_function": _safe_enum_or_hash(dream_function, SUPPORTED_DREAM_FUNCTIONS),
        "candidate_kind": _safe_enum_or_hash(candidate_kind, SUPPORTED_CANDIDATE_KINDS),
        "outcome": normalized_outcome,
        "retention_decision": retention_decision,
        "coefficient_version": _safe_token(retention_policy.get("coefficient_version")),
        "component_value_buckets": _component_value_buckets(retention_policy),
        "source_family": _safe_source_family(source_family),
        "utility_fixture_bucket": _safe_fixture_bucket(utility_fixture_bucket),
        "source_boundary": dream_utility_source_boundary(),
    }
    identity = json.dumps(
        {
            key: value
            for key, value in event.items()
            if key not in {"created_at", "source_boundary"}
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    event["event_id"] = "dut_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return event


def record_dream_utility_event(
    events_path: Path,
    *,
    dream_hypothesis_id: str,
    dream_function: str,
    candidate_kind: str,
    outcome: str,
    retention_policy: Mapping[str, Any],
    source_family: str,
    utility_fixture_bucket: str | None = None,
) -> dict[str, Any]:
    event = build_dream_utility_event(
        dream_hypothesis_id=dream_hypothesis_id,
        dream_function=dream_function,
        candidate_kind=candidate_kind,
        outcome=outcome,
        retention_policy=retention_policy,
        source_family=source_family,
        utility_fixture_bucket=utility_fixture_bucket,
    )
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return event


def iter_dream_utility_events(events_path: Path) -> list[dict[str, Any]]:
    if not events_path.exists():
        return []
    return [row for row in load_jsonl_dict_rows(events_path).rows if row.get("kind") == EVENT_KIND]


def _component_bucket_counts(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        buckets = row.get("component_value_buckets")
        if not isinstance(buckets, Mapping):
            continue
        for component, bucket in buckets.items():
            component_counts = counts.setdefault(_safe_token(component), {})
            bucket_key = _safe_token(bucket)
            component_counts[bucket_key] = component_counts.get(bucket_key, 0) + 1
    return {
        component: {bucket: counts[component][bucket] for bucket in sorted(counts[component])}
        for component in sorted(counts)
    }


def build_dream_utility_report(events_path: Path) -> dict[str, Any]:
    rows = iter_dream_utility_events(events_path)
    by_function: dict[str, dict[str, int]] = {}
    by_decision: dict[str, dict[str, int]] = {}
    by_coefficient: dict[str, dict[str, int]] = {}
    by_source_family: dict[str, dict[str, int]] = {}
    signals: dict[str, dict[str, int]] = {
        bucket: _empty_group() for bucket in sorted(REQUIRED_PUBLIC_FIXTURE_BUCKETS)
    }
    matrix: dict[str, dict[str, dict[str, dict[str, int]]]] = {}
    public_buckets: set[str] = set()
    public_event_count = 0
    private_dogfood_event_count = 0

    for row in rows:
        dream_function = _safe_token(row.get("dream_function"))
        decision = _safe_token(row.get("retention_decision"))
        coefficient = _safe_token(row.get("coefficient_version"))
        source_family = _safe_token(row.get("source_family"))
        fixture_bucket = _safe_token(row.get("utility_fixture_bucket"), default="unclassified")
        _add_to_group(by_function, dream_function, row)
        _add_to_group(by_decision, decision, row)
        _add_to_group(by_coefficient, coefficient, row)
        _add_to_group(by_source_family, source_family, row)
        coefficient_group = (
            matrix.setdefault(dream_function, {})
            .setdefault(decision, {})
            .setdefault(coefficient, _empty_group())
        )
        _add_to_group({coefficient: coefficient_group}, coefficient, row)
        signal = _calibration_signal_for(row)
        if signal in signals:
            _add_to_group(signals, signal, row)
        if source_family == "private_dogfood":
            private_dogfood_event_count += 1
        if _is_public_source_family(source_family):
            public_event_count += 1
            if fixture_bucket in REQUIRED_PUBLIC_FIXTURE_BUCKETS:
                public_buckets.add(fixture_bucket)

    missing_public_buckets = sorted(REQUIRED_PUBLIC_FIXTURE_BUCKETS - public_buckets)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "event_count": len(rows),
        "public_event_count": public_event_count,
        "private_dogfood_event_count": private_dogfood_event_count,
        "by_dream_function": _sorted_groups(by_function),
        "by_retention_decision": _sorted_groups(by_decision),
        "by_coefficient_version": _sorted_groups(by_coefficient),
        "by_source_family": _sorted_groups(by_source_family),
        "by_component_value_bucket": _component_bucket_counts(rows),
        "dream_function_decision_coefficient_buckets": {
            dream_function: {
                decision: {
                    coefficient: decision_groups[decision][coefficient]
                    for coefficient in sorted(decision_groups[decision])
                }
                for decision in sorted(decision_groups)
            }
            for dream_function, decision_groups in sorted(matrix.items())
        },
        "calibration_signals": {bucket: signals[bucket] for bucket in sorted(signals)},
        "public_fixture_bucket_coverage": {
            "required_buckets": sorted(REQUIRED_PUBLIC_FIXTURE_BUCKETS),
            "covered_buckets": sorted(public_buckets),
            "missing_buckets": missing_public_buckets,
        },
        "policy": {
            "automatic_coefficient_update": False,
            "evidence_for_later_calibration_only": True,
            "model_self_rating_promoted_to_retention_signal": False,
            "claims_causal_user_visible_lift": False,
        },
        "source_boundary": dream_utility_source_boundary(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", default=DEFAULT_EVENTS_FILENAME)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    payload = build_dream_utility_report(Path(args.events))
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"events: {payload['event_count']}")
        for function, group in payload["by_dream_function"].items():
            print(f"- {function}: {group['event_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
