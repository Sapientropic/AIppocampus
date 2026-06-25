#!/usr/bin/env python3
"""Privacy-safe advisory guard for mined navigation term and graph quality."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime.navigation.associations import (
    default_associations_path,
    load_associations,
)
from aippocampus_runtime.navigation.concept_graph_health import concept_graph_health
from aippocampus_runtime.navigation.concept_graph_schema import default_concept_graph_path
from aippocampus_runtime.navigation.concept_graph_term_quality import (
    TermQualityContext,
    assess_concept_term,
)
from aippocampus_runtime.registry.api import registry_paths
from aippocampus_runtime.text import has_cjk_ideograph

SCHEMA_VERSION = "navigation_data_quality_guard_v1"
DEFAULT_MAX_LOW_VALUE_CJK_RATIO = 0.02
DEFAULT_MAX_LOW_AV_RATIO = 0.1
DEFAULT_MAX_BAD_CJK_BOUNDARY_RATIO = 0.15
DEFAULT_MAX_WEAK_CJK_ANCHOR_RATIO = 0.15
DEFAULT_MAX_GRAPH_LOW_VALUE_CJK_FRAGMENTS = 0
DEFAULT_MAX_SUBCONSCIOUS_COLLAPSED_HUBS = 0


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _thread_count(item: Mapping[str, Any]) -> int:
    return len(
        {
            str(source.get("thread_key") or "")
            for source in item.get("threads") or []
            if isinstance(source, Mapping) and source.get("thread_key")
        }
    )


def _term_quality(item: Mapping[str, Any]) -> Mapping[str, Any] | None:
    stat = item.get("term_quality") or item.get("phrase_stat")
    return stat if isinstance(stat, Mapping) else None


def _empty_association_metrics() -> dict[str, Any]:
    return {
        "status": "missing",
        "term_count": 0,
        "related_term_count": 0,
        "cjk_term_count": 0,
        "low_value_cjk_rejection_count": 0,
        "low_accessor_variety_rejection_count": 0,
        "bad_cjk_boundary_rejection_count": 0,
        "weak_cjk_anchor_rejection_count": 0,
        "cjk_terms_with_av_count": 0,
        "low_value_cjk_ratio": 0.0,
        "low_accessor_variety_ratio": 0.0,
        "bad_cjk_boundary_ratio": 0.0,
        "weak_cjk_anchor_ratio": 0.0,
    }


def association_quality_metrics(associations: Mapping[str, Any]) -> dict[str, Any]:
    terms = associations.get("terms")
    if not isinstance(terms, Mapping):
        return _empty_association_metrics()
    term_count = 0
    related_term_count = 0
    cjk_term_count = 0
    low_value_cjk_rejection_count = 0
    low_accessor_variety_rejection_count = 0
    bad_cjk_boundary_rejection_count = 0
    weak_cjk_anchor_rejection_count = 0
    cjk_terms_with_av_count = 0
    av_buckets: dict[str, int] = {}
    rejection_reasons: dict[str, int] = {}

    for item in terms.values():
        if not isinstance(item, Mapping):
            continue
        label = item.get("term")
        if not label:
            continue
        term_count += 1
        cjk = has_cjk_ideograph(str(label))
        if cjk:
            cjk_term_count += 1
        context = TermQualityContext(
            ingress="association",
            source_backed=bool(item.get("threads")),
            hit_count=int(item.get("hit_count") or 0),
            thread_count=_thread_count(item),
            phrase_stat=_term_quality(item),
        )
        decision = assess_concept_term(label, context)
        av_buckets[decision.av_bucket] = int(av_buckets.get(decision.av_bucket) or 0) + 1
        if decision.av_bucket != "unknown" and decision.cjk:
            cjk_terms_with_av_count += 1
        if not decision.accepted:
            rejection_reasons[decision.reason] = int(rejection_reasons.get(decision.reason) or 0) + 1
            if decision.reason == "low_value_cjk_fragment":
                low_value_cjk_rejection_count += 1
            if decision.reason == "low_accessor_variety":
                low_accessor_variety_rejection_count += 1
            if decision.reason == "bad_cjk_boundary":
                bad_cjk_boundary_rejection_count += 1
            if decision.reason == "weak_cjk_anchor":
                weak_cjk_anchor_rejection_count += 1
        related_values = [value for value in item.get("related_terms") or [] if value]
        related_term_count += len(related_values)
        for related in related_values:
            related_decision = assess_concept_term(
                related,
                TermQualityContext(
                    ingress="related_term",
                    source_backed=bool(item.get("threads")),
                    hit_count=int(item.get("hit_count") or 0),
                    thread_count=_thread_count(item),
                ),
            )
            if not related_decision.accepted:
                rejection_reasons[related_decision.reason] = (
                    int(rejection_reasons.get(related_decision.reason) or 0) + 1
                )
                if related_decision.reason == "bad_cjk_boundary":
                    bad_cjk_boundary_rejection_count += 1
                if related_decision.reason == "weak_cjk_anchor":
                    weak_cjk_anchor_rejection_count += 1

    candidate_total = term_count + related_term_count
    return {
        "status": "present",
        "term_count": term_count,
        "related_term_count": related_term_count,
        "cjk_term_count": cjk_term_count,
        "low_value_cjk_rejection_count": low_value_cjk_rejection_count,
        "low_accessor_variety_rejection_count": low_accessor_variety_rejection_count,
        "bad_cjk_boundary_rejection_count": bad_cjk_boundary_rejection_count,
        "weak_cjk_anchor_rejection_count": weak_cjk_anchor_rejection_count,
        "cjk_terms_with_av_count": cjk_terms_with_av_count,
        "low_value_cjk_ratio": _ratio(low_value_cjk_rejection_count, max(1, cjk_term_count)),
        "low_accessor_variety_ratio": _ratio(
            low_accessor_variety_rejection_count,
            max(1, cjk_terms_with_av_count),
        ),
        "bad_cjk_boundary_ratio": _ratio(bad_cjk_boundary_rejection_count, max(1, candidate_total)),
        "weak_cjk_anchor_ratio": _ratio(weak_cjk_anchor_rejection_count, max(1, candidate_total)),
        "accessor_variety_buckets": dict(sorted(av_buckets.items())),
        "rejection_reason_counts": dict(sorted(rejection_reasons.items())),
    }


def _threshold_findings(
    metrics: Mapping[str, Any],
    *,
    max_low_value_cjk_ratio: float,
    max_low_av_ratio: float,
    max_bad_cjk_boundary_ratio: float,
    max_weak_cjk_anchor_ratio: float,
    graph_health: Mapping[str, Any] | None = None,
    max_graph_low_value_cjk_fragments: int = DEFAULT_MAX_GRAPH_LOW_VALUE_CJK_FRAGMENTS,
    max_subconscious_collapsed_hubs: int = DEFAULT_MAX_SUBCONSCIOUS_COLLAPSED_HUBS,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    low_value_ratio = float(metrics.get("low_value_cjk_ratio") or 0.0)
    if low_value_ratio > max_low_value_cjk_ratio:
        findings.append(
            {
                "kind": "association_low_value_cjk_ratio",
                "severity": "warning",
                "ratio": low_value_ratio,
                "threshold": max_low_value_cjk_ratio,
            }
        )
    low_av_ratio = float(metrics.get("low_accessor_variety_ratio") or 0.0)
    if low_av_ratio > max_low_av_ratio:
        findings.append(
            {
                "kind": "association_low_accessor_variety_ratio",
                "severity": "warning",
                "ratio": low_av_ratio,
                "threshold": max_low_av_ratio,
            }
        )
    bad_boundary_ratio = float(metrics.get("bad_cjk_boundary_ratio") or 0.0)
    if bad_boundary_ratio > max_bad_cjk_boundary_ratio:
        findings.append(
            {
                "kind": "association_bad_cjk_boundary_ratio",
                "severity": "warning",
                "ratio": bad_boundary_ratio,
                "threshold": max_bad_cjk_boundary_ratio,
            }
        )
    weak_anchor_ratio = float(metrics.get("weak_cjk_anchor_ratio") or 0.0)
    if weak_anchor_ratio > max_weak_cjk_anchor_ratio:
        findings.append(
            {
                "kind": "association_weak_cjk_anchor_ratio",
                "severity": "warning",
                "ratio": weak_anchor_ratio,
                "threshold": max_weak_cjk_anchor_ratio,
            }
        )
    graph_health = graph_health or {}
    cjk_indicators = graph_health.get("cjk_fragment_indicators")
    if isinstance(cjk_indicators, Mapping):
        graph_low_value = int(cjk_indicators.get("low_value_cjk_fragment_count") or 0)
        if graph_low_value > max_graph_low_value_cjk_fragments:
            findings.append(
                {
                    "kind": "concept_graph_low_value_cjk_fragments",
                    "severity": "warning",
                    "count": graph_low_value,
                    "threshold": max_graph_low_value_cjk_fragments,
                }
            )
    hub_quality = graph_health.get("subconscious_hub_quality")
    if isinstance(hub_quality, Mapping):
        collapsed_hub_count = int(hub_quality.get("collapsed_hub_count") or 0)
        if collapsed_hub_count > max_subconscious_collapsed_hubs:
            findings.append(
                {
                    "kind": "concept_graph_subconscious_hub_collapse",
                    "severity": "warning",
                    "collapsed_hub_count": collapsed_hub_count,
                    "parked_edge_group_count": int(
                        hub_quality.get("parked_edge_group_count") or 0
                    ),
                    "threshold": max_subconscious_collapsed_hubs,
                }
            )
    for warning in graph_health.get("warnings") or []:
        if isinstance(warning, Mapping):
            findings.append(
                {
                    "kind": "concept_graph_health_warning",
                    "severity": "warning",
                    "code": warning.get("code") or "unknown",
                }
            )
    return findings


def build_report(
    *,
    associations_path: Path | None,
    concept_graph_path: Path | None,
    max_low_value_cjk_ratio: float = DEFAULT_MAX_LOW_VALUE_CJK_RATIO,
    max_low_av_ratio: float = DEFAULT_MAX_LOW_AV_RATIO,
    max_bad_cjk_boundary_ratio: float = DEFAULT_MAX_BAD_CJK_BOUNDARY_RATIO,
    max_weak_cjk_anchor_ratio: float = DEFAULT_MAX_WEAK_CJK_ANCHOR_RATIO,
    max_graph_low_value_cjk_fragments: int = DEFAULT_MAX_GRAPH_LOW_VALUE_CJK_FRAGMENTS,
    max_subconscious_collapsed_hubs: int = DEFAULT_MAX_SUBCONSCIOUS_COLLAPSED_HUBS,
) -> dict[str, Any]:
    associations_metrics = _empty_association_metrics()
    if associations_path and associations_path.exists():
        associations_metrics = association_quality_metrics(load_associations(associations_path))
    graph_health = (
        concept_graph_health(concept_graph_path)
        if concept_graph_path and concept_graph_path.exists()
        else {
            "kind": "aippocampus_concept_graph_health",
            "ok": False,
            "status": "missing",
        }
    )
    findings = _threshold_findings(
        associations_metrics,
        max_low_value_cjk_ratio=max_low_value_cjk_ratio,
        max_low_av_ratio=max_low_av_ratio,
        max_bad_cjk_boundary_ratio=max_bad_cjk_boundary_ratio,
        max_weak_cjk_anchor_ratio=max_weak_cjk_anchor_ratio,
        graph_health=graph_health,
        max_graph_low_value_cjk_fragments=max_graph_low_value_cjk_fragments,
        max_subconscious_collapsed_hubs=max_subconscious_collapsed_hubs,
    )
    return {
        "kind": "aippocampus_navigation_data_quality_guard",
        "schema_version": SCHEMA_VERSION,
        "mode": "advisory",
        "ok": True,
        "advisory_status": "warning" if findings else "clear",
        "associations_path_present": bool(associations_path and associations_path.exists()),
        "concept_graph_path_present": bool(concept_graph_path and concept_graph_path.exists()),
        "associations": associations_metrics,
        "concept_graph": {
            "status": graph_health.get("status"),
            "concept_count": graph_health.get("concept_count", 0),
            "edge_count": graph_health.get("edge_count", 0),
            "cjk_fragment_indicators": graph_health.get("cjk_fragment_indicators", {}),
            "source_diversity_buckets": graph_health.get("source_diversity_buckets", {}),
            "evidence_count_buckets": graph_health.get("evidence_count_buckets", {}),
            "edge_type_status_counts": graph_health.get("edge_type_status_counts", {}),
            "term_quality_gate": graph_health.get("term_quality_gate", {}),
            "subconscious_hub_quality": graph_health.get("subconscious_hub_quality", {}),
            "warnings": graph_health.get("warnings", []),
        },
        "findings": findings,
        "thresholds": {
            "max_low_value_cjk_ratio": max_low_value_cjk_ratio,
            "max_low_accessor_variety_ratio": max_low_av_ratio,
            "max_bad_cjk_boundary_ratio": max_bad_cjk_boundary_ratio,
            "max_weak_cjk_anchor_ratio": max_weak_cjk_anchor_ratio,
            "max_graph_low_value_cjk_fragments": max_graph_low_value_cjk_fragments,
            "max_subconscious_collapsed_hubs": max_subconscious_collapsed_hubs,
        },
        "privacy": {
            "raw_labels_default": "omitted",
            "source_paths_reported_as_presence_only": True,
        },
    }


def _default_paths(args: argparse.Namespace) -> tuple[Path | None, Path | None]:
    if not (args.registry or args.registry_dir or args.associations or args.concept_graph):
        return None, None
    registry_path = None
    if args.registry or args.registry_dir:
        registry_path = (
            Path(args.registry).resolve()
            if args.registry
            else registry_paths(Path(args.registry_dir).resolve())[0]
        )
    return (
        Path(args.associations).resolve()
        if args.associations
        else default_associations_path(registry_path=registry_path)
        if registry_path
        else None,
        Path(args.concept_graph).resolve()
        if args.concept_graph
        else default_concept_graph_path(registry_path=registry_path)
        if registry_path
        else None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--associations")
    parser.add_argument("--concept-graph")
    parser.add_argument("--max-low-value-cjk-ratio", type=float, default=DEFAULT_MAX_LOW_VALUE_CJK_RATIO)
    parser.add_argument("--max-low-av-ratio", type=float, default=DEFAULT_MAX_LOW_AV_RATIO)
    parser.add_argument(
        "--max-bad-cjk-boundary-ratio",
        type=float,
        default=DEFAULT_MAX_BAD_CJK_BOUNDARY_RATIO,
    )
    parser.add_argument(
        "--max-weak-cjk-anchor-ratio",
        type=float,
        default=DEFAULT_MAX_WEAK_CJK_ANCHOR_RATIO,
    )
    parser.add_argument(
        "--max-graph-low-value-cjk-fragments",
        type=int,
        default=DEFAULT_MAX_GRAPH_LOW_VALUE_CJK_FRAGMENTS,
    )
    parser.add_argument(
        "--max-subconscious-collapsed-hubs",
        type=int,
        default=DEFAULT_MAX_SUBCONSCIOUS_COLLAPSED_HUBS,
    )
    parser.add_argument("--fail-on-warnings", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    associations_path, concept_graph_path = _default_paths(args)
    report = build_report(
        associations_path=associations_path,
        concept_graph_path=concept_graph_path,
        max_low_value_cjk_ratio=args.max_low_value_cjk_ratio,
        max_low_av_ratio=args.max_low_av_ratio,
        max_bad_cjk_boundary_ratio=args.max_bad_cjk_boundary_ratio,
        max_weak_cjk_anchor_ratio=args.max_weak_cjk_anchor_ratio,
        max_graph_low_value_cjk_fragments=args.max_graph_low_value_cjk_fragments,
        max_subconscious_collapsed_hubs=args.max_subconscious_collapsed_hubs,
    )
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"navigation data quality: {report['advisory_status']}")
        print(f"association terms: {report['associations']['term_count']}")
        print(f"concept graph concepts: {report['concept_graph'].get('concept_count', 0)}")
    if args.fail_on_warnings and report["findings"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
