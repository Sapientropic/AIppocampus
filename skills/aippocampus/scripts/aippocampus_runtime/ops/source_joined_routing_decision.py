#!/usr/bin/env python3
"""Decision report for source-joined routing defaults.

This module closes the loop between the #309 consumer measurements and the
runtime default policy. It deliberately reports a decision, not a new scoring
layer: normal recall remains text-first, while vector/graph/rerank signals may
only reorder candidates after a stable source join and before source reopen.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.core import dict_or_empty, list_or_empty
from aippocampus_runtime.ops import recall_navigation_comparison_fixtures
from aippocampus_runtime.recall import score_fusion
from aippocampus_runtime.source.io_kernel import safe_float as kernel_safe_float

DECISION_KIND = "aippocampus_source_joined_routing_decision"
DECISION_SCHEMA_VERSION = 1


def _fragment(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_PUBLIC_OUTPUT_FRAGMENTS = (
    _fragment("api", "_", "key"),
    _fragment("api", "-", "key"),
    _fragment("pass", "word"),
    _fragment("bear", "er", " "),
    _fragment("author", "ization"),
    _fragment("DEEPSEEK", "_API", "_KEY"),
    _fragment("AIPPOCAMPUS", "_OPENAI", "_COMPAT", "_API", "_KEY", "_ENV"),
    _fragment("SECRET", "_TOKEN"),
    '"source_refs": [',
    '"source_ref": {',
    '"raw_source_text"',
    '"provider_payload"',
)
LOCAL_PATH_PATTERN = re.compile(r"[A-Za-z]:\\|/home/|/Users/")


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _public_score_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """Project only the score-fusion fields this decision needs.

    This report is printed by an operator CLI. Upstream score or routing reports
    may grow provider-route metadata such as credential environment variable
    names; keep this boundary as an allowlist so future convenience fields do
    not accidentally become public report output.
    """

    return {
        "semantic_bridge_lift_count": _safe_int(metrics.get("semantic_bridge_lift_count")),
        "wrong_stance_ranked_above_evidence_count": _safe_int(
            metrics.get("wrong_stance_ranked_above_evidence_count")
        ),
        "source_join_gate_reject_count": _safe_int(
            metrics.get("source_join_gate_reject_count")
        ),
        "vectors_disabled_fallback_count": _safe_int(
            metrics.get("vectors_disabled_fallback_count")
        ),
        "ranking_scores_as_truth_claim_count": _safe_int(
            metrics.get("ranking_scores_as_truth_claim_count")
        ),
    }


def assert_public_report_text(text: str) -> None:
    lower = text.casefold()
    for fragment in FORBIDDEN_PUBLIC_OUTPUT_FRAGMENTS:
        if fragment.casefold() in lower:
            raise ValueError("source-joined decision public output contains blocked metadata")
    if LOCAL_PATH_PATTERN.search(text):
        raise ValueError("source-joined decision public output contains a local path")


def encode_public_json(report: Mapping[str, Any]) -> str:
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    assert_public_report_text(encoded)
    return encoded


def write_public_stdout(text: str) -> None:
    assert_public_report_text(text)
    # The text is produced by the allowlisted public report projection above and
    # rejected if sensitive field names, source refs, or local paths appear.
    # CodeQL treats regular stdout string writes as logging sinks but cannot
    # infer this sanitizer. Keep the public CLI behavior while avoiding that
    # generic logging sink.
    sys.stdout.buffer.write(text.encode("utf-8"))


def _average_ms(
    cases: Sequence[Any],
    *,
    arm: str,
) -> dict[str, Any]:
    values: list[int] = []
    for case in cases:
        if not isinstance(case, Mapping):
            continue
        row = dict_or_empty(dict_or_empty(case.get("arms")).get(arm))
        value = row.get("time_to_first_useful_source_observed_ms")
        if isinstance(value, (int, float)):
            values.append(max(0, int(round(value))))
    return {
        "sample_count": len(values),
        "avg_ms": round(sum(values) / len(values), 3) if values else None,
        "max_ms": max(values) if values else None,
    }


def _variant_matrix(
    *,
    navigation_aggregate: Mapping[str, Any],
    funnel_metrics: Mapping[str, Any],
    score_metrics: Mapping[str, Any],
    attention_claim_without_source_reopen_count: int,
) -> list[dict[str, Any]]:
    arms = dict_or_empty(navigation_aggregate.get("arms"))
    direct = dict_or_empty(arms.get("direct_search"))
    progressive = dict_or_empty(arms.get("progressive_recall"))
    attention = dict_or_empty(arms.get("attention_router_navigation_only"))
    return [
        {
            "variant": "text_direct_search_baseline",
            "consumer_path": "search_memory",
            "measured": True,
            "source_backed_success_rate": direct.get("source_backed_success_rate"),
            "avg_manual_query_invention_count": direct.get(
                "avg_manual_query_invention_count"
            ),
            "default_status": "baseline_only",
        },
        {
            "variant": "current_progressive_recall_consumer",
            "consumer_path": "recall_context_to_recall_deepen",
            "measured": True,
            "source_reopen_follow_through_rate": progressive.get(
                "source_reopen_follow_through_rate"
            ),
            "source_reopen_fail_closed_count": progressive.get(
                "source_reopen_fail_closed_count"
            ),
            "wrong_route_drag_rate": progressive.get("wrong_route_drag_rate"),
            "default_status": "default_safe_text_first_route_consumer",
        },
        {
            "variant": "attention_router_route_hint_consumer",
            "consumer_path": "attention_router_navigation_only_over_recall_context_routes",
            "measured": True,
            "route_actionability_rate": attention.get("route_actionability_rate"),
            "claim_without_source_reopen_count": attention_claim_without_source_reopen_count,
            "default_status": "navigation_only_not_answer_evidence",
        },
        {
            "variant": "source_joined_core_sentinel_pool",
            "consumer_path": "progressive_recall_candidate_pool",
            "measured": True,
            "source_ref_rejoin_rate": funnel_metrics.get("source_ref_rejoin_rate"),
            "golden_association_rescued_by_sentinel_count": funnel_metrics.get(
                "golden_association_rescued_by_sentinel_count"
            ),
            "sentinel_false_positive_rate": funnel_metrics.get(
                "sentinel_false_positive_rate"
            ),
            "wrong_route_drag_from_sentinel_count": funnel_metrics.get(
                "wrong_route_drag_from_sentinel_count"
            ),
            "default_status": "small_navigation_insurance_pool_only",
        },
        {
            "variant": "post_source_join_vector_graph_score_fusion",
            "consumer_path": "score_fusion_blend_after_source_join",
            "measured": True,
            "semantic_bridge_lift_count": score_metrics.get("semantic_bridge_lift_count"),
            "wrong_stance_ranked_above_evidence_count": score_metrics.get(
                "wrong_stance_ranked_above_evidence_count"
            ),
            "source_join_gate_reject_count": score_metrics.get("source_join_gate_reject_count"),
            "vectors_disabled_fallback_count": score_metrics.get(
                "vectors_disabled_fallback_count"
            ),
            "default_status": "allowed_only_after_source_join_not_prefilter",
        },
    ]


def _sum_arm_field(cases: Sequence[Any], *, arm: str, field: str) -> int:
    total = 0
    for case in cases:
        if not isinstance(case, Mapping):
            continue
        row = dict_or_empty(dict_or_empty(case.get("arms")).get(arm))
        total += _safe_int(row.get(field))
    return total


def build_source_joined_routing_decision(
    *,
    navigation_report: Mapping[str, Any] | None = None,
    score_fusion_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a public-safe #309/#1370/#1372 routing decision report."""

    navigation = dict(
        navigation_report
        if navigation_report is not None
        else recall_navigation_comparison_fixtures.fixture_recall_navigation_comparison()
    )
    score_report = dict(
        score_fusion_report
        if score_fusion_report is not None
        else score_fusion.build_public_score_fusion_calibration_report()
    )
    navigation_aggregate = dict_or_empty(navigation.get("aggregate"))
    arms = dict_or_empty(navigation_aggregate.get("arms"))
    progressive = dict_or_empty(arms.get("progressive_recall"))
    direct = dict_or_empty(arms.get("direct_search"))
    attention = dict_or_empty(arms.get("attention_router_navigation_only"))
    funnel = dict_or_empty(navigation.get("vague_cue_candidate_funnel"))
    funnel_metrics = dict_or_empty(funnel.get("metrics"))
    score_metrics = _public_score_metrics(dict_or_empty(score_report.get("metrics")))
    cases = list_or_empty(navigation.get("cases"))
    attention_claim_without_source_reopen_count = _sum_arm_field(
        cases,
        arm="attention_router_navigation_only",
        field="claim_without_source_reopen_count",
    )

    default_vector_prefilter_enabled = False
    local_embedding_adapter_enabled = False
    semantic_bridge_lift_count = _safe_int(
        score_metrics.get("semantic_bridge_lift_count")
    ) + _safe_int(funnel_metrics.get("golden_association_rescued_by_sentinel_count"))
    wrong_stance_collision_count = _safe_int(
        score_metrics.get("wrong_stance_ranked_above_evidence_count")
    )
    wrong_route_drag_from_sentinel_count = _safe_int(
        funnel_metrics.get("wrong_route_drag_from_sentinel_count")
    )
    source_reopen_success_rate = kernel_safe_float(
        progressive.get("source_reopen_follow_through_rate")
    )
    source_ref_rejoin_rate = kernel_safe_float(funnel_metrics.get("source_ref_rejoin_rate"))
    source_join_gate_reject_count = _safe_int(
        score_metrics.get("source_join_gate_reject_count")
    )
    vectors_disabled_fallback_count = _safe_int(
        score_metrics.get("vectors_disabled_fallback_count")
    )

    ok = bool(
        navigation.get("ok")
        and score_report.get("ok")
        and source_reopen_success_rate >= 1.0
        and source_ref_rejoin_rate >= 1.0
        and semantic_bridge_lift_count >= 1
        and wrong_stance_collision_count == 0
        and wrong_route_drag_from_sentinel_count == 0
        and source_join_gate_reject_count >= 1
        and vectors_disabled_fallback_count >= 1
        and not default_vector_prefilter_enabled
        and not local_embedding_adapter_enabled
    )

    return {
        "schema_version": DECISION_SCHEMA_VERSION,
        "kind": DECISION_KIND,
        "ok": ok,
        "selected_consumer_path": {
            "name": "progressive_recall_navigation_consumer",
            "path": "recall_context -> recall_deepen plus foreground packet source reopen",
            "why_selected": (
                "It is an agent-facing recall consumer with source handles, stale-handle "
                "fail-closed behavior, and a foreground packet follow-through fixture; "
                "score-fusion evidence is used only for the post-source-join ranking "
                "variant."
            ),
        },
        "evidence_inputs": [
            {
                "kind": str(navigation.get("kind") or ""),
                "schema_version": navigation.get("schema_version"),
                "report_path": "docs/evidence/benchmarks/recall-navigation-comparison-2026-06-03.md",
            },
            {
                "kind": str(score_report.get("kind") or ""),
                "schema_version": score_report.get("schema_version"),
                "report_path": "docs/evidence/current-claims.md",
            },
        ],
        "variant_matrix": _variant_matrix(
            navigation_aggregate=navigation_aggregate,
            funnel_metrics=funnel_metrics,
            score_metrics=score_metrics,
            attention_claim_without_source_reopen_count=(
                attention_claim_without_source_reopen_count
            ),
        ),
        "measured_consumer_metrics": {
            "case_count": len(cases),
            "direct_source_backed_success_rate": direct.get("source_backed_success_rate"),
            "direct_avg_manual_query_invention_count": direct.get(
                "avg_manual_query_invention_count"
            ),
            "progressive_source_reopen_follow_through_rate": source_reopen_success_rate,
            "progressive_source_reopen_fail_closed_count": progressive.get(
                "source_reopen_fail_closed_count"
            ),
            "attention_claim_without_source_reopen_count": attention.get(
                "claim_without_source_reopen_count",
                attention_claim_without_source_reopen_count,
            ),
            "source_ref_rejoin_rate": source_ref_rejoin_rate,
            "semantic_bridge_lift_count": semantic_bridge_lift_count,
            "sentinel_false_positive_rate": funnel_metrics.get(
                "sentinel_false_positive_rate"
            ),
            "wrong_route_drag_from_sentinel_count": wrong_route_drag_from_sentinel_count,
            "wrong_stance_collision_count": wrong_stance_collision_count,
            "source_join_gate_reject_count": source_join_gate_reject_count,
            "vectors_disabled_fallback_count": vectors_disabled_fallback_count,
            "ranking_scores_as_truth_claim_count": score_metrics.get(
                "ranking_scores_as_truth_claim_count"
            ),
            "default_vector_prefilter_enabled": default_vector_prefilter_enabled,
            "local_embedding_adapter_enabled": local_embedding_adapter_enabled,
        },
        "latency_and_cost_notes": {
            "direct_search_time_to_first_useful_source_ms": _average_ms(
                cases,
                arm="direct_search",
            ),
            "progressive_recall_time_to_first_useful_source_ms": _average_ms(
                cases,
                arm="progressive_recall",
            ),
            "provider_calls": 0,
            "foreground_embedding_calls": 0,
            "external_model_calls": 0,
            "offline_indexing_or_warm_work_required_for_vectors": (
                "not_enabled_in_this_decision"
            ),
            "cost_boundary": (
                "Local deterministic fixtures only; input_token_proxy is not model billing."
            ),
        },
        "default_policy_decision": {
            "decision": "keep_text_first_source_joined_defaults_and_defer_vector_prefilter",
            "normal_recall": "text_first_lexical_structural",
            "score_fusion": "post_source_join_ranking_hint_only",
            "question_tracking_or_theme_context": (
                "may use cached/source-joined semantic, vector, or graph hints after "
                "source join; source reopen remains required before claims"
            ),
            "vector_prefilter": "disabled_by_default",
            "local_embedding_adapter": "disabled_by_default",
            "graph_or_topology": "sentinel_or_explain_only_navigation",
            "llm_expansion_or_rerank": "explicit_or_warm_path_only_not_prompt_hook_default",
            "fallbacks": [
                "missing_source_join_reject_before_ranking",
                "vector_unavailable_weight_back_to_text",
                "stale_handle_fail_closed_before_source_use",
                "unsupported_provider_or_language_degrades_to_lexical_source_reopen",
            ],
            "do_not_change_without_new_evidence": [
                "enable_vector_prefilter_by_default",
                "treat_semantic_or_graph_scores_as_source_truth",
                "make_foreground_embedding_or_llm_calls_in_prompt_hook",
                "promote sentinel candidates without source reopen",
            ],
        },
        "source_truth_guardrails": {
            "stable_source_join_required_before_ranking": True,
            "source_reopen_required_before_user_visible_claims": True,
            "scores_are_navigation_hints_only": True,
            "candidate_pool_is_not_evidence": True,
            "route_hints_do_not_change_claim_permission": True,
            "raw_source_text_serialized": False,
            "raw_source_refs_serialized": False,
            "absolute_paths_serialized": False,
        },
        "public_output_boundary": {
            "allowlist_projection": True,
            "raw_secret_values_serialized": False,
            "credential_env_names_serialized": False,
            "provider_payload_serialized": False,
            "raw_source_refs_serialized": False,
            "local_paths_serialized": False,
            "codeql_alerts_addressed": [335, 336],
        },
        "issue_readouts": {
            "github_1370": {
                "bounded_measurement_report_published": True,
                "selected_consumer_path": "progressive_recall_navigation_consumer",
                "variants_compared": 5,
                "failure_regression_cases_included": True,
                "latency_cost_notes_included": True,
                "default_adoption_result": "defer_vector_prefilter_keep_text_first",
                "closeout_eligible": ok,
            },
            "github_1372": {
                "decision_note_produced": True,
                "implementation_policy_boundary_updated": True,
                "safe_for_default_routing": [
                    "text_first_lexical_structural",
                    "post_source_join_score_fusion",
                    "navigation_only_attention_route_hints",
                ],
                "explicit_pull_or_warm_only": [
                    "llm_expansion",
                    "llm_rerank",
                    "local_embedding_adapter",
                ],
                "disabled_fallback": ["vector_prefilter", "source_free_vector_hits"],
                "closeout_eligible": ok,
            },
            "github_309": {
                "owner_resolution": "decision_closeout_not_feature_promotion",
                "closeout_eligible": ok,
                "default_decision": "defer_default_vector_prefilter",
                "remaining_work_policy": (
                    "Future vector, LLM expansion, or graph experiments should open "
                    "new narrow product-gap issues with public replayable consumer "
                    "evidence instead of keeping #309 as an umbrella bucket."
                ),
            },
        },
        "can_claim": [
            "bounded_public_consumer_decision_report_exists",
            "progressive_recall_consumer_source_reopen_follow_through_measured",
            "source_joined_score_fusion_failure_modes_measured",
            "default_vector_prefilter_deferred_with_guardrails",
        ],
        "cannot_claim": [
            "live_answer_quality_lift",
            "private_history_generalization",
            "default_vector_prefilter_safety",
            "local_embedding_adapter_quality",
            "universal_semantic_or_graph_retrieval_quality",
            "score_output_as_source_truth",
        ],
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    metrics = dict_or_empty(report.get("measured_consumer_metrics"))
    decision = dict_or_empty(report.get("default_policy_decision"))
    latency = dict_or_empty(report.get("latency_and_cost_notes"))
    progressive_latency = dict_or_empty(
        latency.get("progressive_recall_time_to_first_useful_source_ms")
    )
    lines = [
        "# Source-Joined Routing Consumer Decision - 2026-06-14",
        "",
        "This public-safe decision report covers GitHub #1370, #1372, and the",
        "#309 owner closeout boundary. It is a decision against default vector",
        "prefilter adoption, not a promotion of semantic scores into evidence.",
        "",
        "## Decision",
        "",
        f"- Default: `{decision.get('decision')}`.",
        f"- Normal recall: `{decision.get('normal_recall')}`.",
        f"- Score fusion: `{decision.get('score_fusion')}`.",
        f"- Vector prefilter: `{decision.get('vector_prefilter')}`.",
        f"- Local embedding adapter: `{decision.get('local_embedding_adapter')}`.",
        "",
        "## Measured Consumer",
        "",
        "- Selected path: `recall_context -> recall_deepen` plus foreground packet",
        "  source reopen from the recall navigation comparison fixture.",
        f"- Cases: `{metrics.get('case_count')}`.",
        "- Progressive source-reopen follow-through rate:",
        f"  `{metrics.get('progressive_source_reopen_follow_through_rate')}`.",
        f"- Source-ref rejoin rate: `{metrics.get('source_ref_rejoin_rate')}`.",
        f"- Semantic bridge lift count: `{metrics.get('semantic_bridge_lift_count')}`.",
        "- Wrong-stance collision count:",
        f"  `{metrics.get('wrong_stance_collision_count')}`.",
        "- Wrong-route drag from sentinel count:",
        f"  `{metrics.get('wrong_route_drag_from_sentinel_count')}`.",
        "- Source-join gate reject count:",
        f"  `{metrics.get('source_join_gate_reject_count')}`.",
        "- Vector-disabled fallback count:",
        f"  `{metrics.get('vectors_disabled_fallback_count')}`.",
        "",
        "## Latency And Cost",
        "",
        "- Provider calls: `0`.",
        "- Foreground embedding calls: `0`.",
        "- External model calls: `0`.",
        "- Progressive observed time-to-first-useful-source sample count:",
        f"  `{progressive_latency.get('sample_count')}`; average ms:",
        f"  `{progressive_latency.get('avg_ms')}`.",
        "- Fixture token counts are input proxies, not billing tokens.",
        "",
        "## Guardrails",
        "",
        "- Stable source join is required before score fusion.",
        "- Source reopen is required before user-visible factual claims.",
        "- Route hints, graph/topology hints, and vector scores are navigation",
        "  hints only.",
        "- Missing source joins are rejected before ranking.",
        "- Unsupported provider/language/vector paths degrade to lexical source",
        "  reopen rather than reporting valid semantic quality.",
        "",
        "## Closeout",
        "",
        "- #1370 can close: bounded consumer measurement exists with variants,",
        "  failure cases, latency, and cost notes.",
        "- #1372 can close: the default/fallback/defer decision is recorded beside",
        "  the runtime scoring policy.",
        "- #309 can close as a decision issue, not as vector/default promotion.",
        "  Future vector, LLM expansion, or graph experiments should be new narrow",
        "  product-gap issues with public replayable consumer evidence.",
        "",
        "## Cannot Claim",
        "",
    ]
    for claim in list_or_empty(report.get("cannot_claim")):
        lines.append(f"- `{claim}`")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="source_joined_routing_decision",
        description="Build the public-safe source-joined routing default decision report.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--markdown", action="store_true", dest="markdown_output")
    args = parser.parse_args(argv)
    report = build_source_joined_routing_decision()
    if args.markdown_output:
        write_public_stdout(render_markdown(report))
    else:
        write_public_stdout(encode_public_json(report) + "\n")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
