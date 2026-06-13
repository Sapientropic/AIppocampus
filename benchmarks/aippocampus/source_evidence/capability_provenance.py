"""Capability provenance labels for public benchmark reports.

The same LongMemEval score can come from very different surfaces: the mature
deterministic source adapter, an opt-in query-time LLM reranker, a benchmark
local experiment, or an actual AIppocampus warming/materialization path.  Keep
that distinction machine-readable so future agents cannot close architecture
issues from a score whose path bypassed the architecture under test.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "benchmark-capability-provenance-v0"

_BASE_CAPABILITIES = [
    "clean_source_adapter",
    "standard_public_source_evidence_adapter",
    "fts5_source_line_retrieval",
]

_CANONICAL_SOURCE_SIDE_OWNER_REFS = [
    "semantic_scope_labeling",
    "semantic_scope_builder",
    "subconscious_jobs",
    "warm_ambient_routes",
    "attention_router",
]


def benchmark_capability_provenance(
    line_reranker_mode: str,
    *,
    source_semantic_sidecar_materializer: str = "off",
) -> dict[str, Any]:
    """Return what the benchmark mode actually exercised.

    This is intentionally descriptive rather than aspirational. A mode that is
    useful for exploration may still be unable to claim the canonical
    AIppocampus source-side semantic warming path.
    """

    mode = str(line_reranker_mode or "off").strip().casefold()
    materializer = str(source_semantic_sidecar_materializer or "off").strip().casefold()
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "line_reranker_mode": mode,
        "aippocampus_capabilities_used": list(_BASE_CAPABILITIES),
        "benchmark_local_scaffolding": [],
        "relevant_aippocampus_paths_not_used": [],
        "canonical_source_side_owner_refs": list(_CANONICAL_SOURCE_SIDE_OWNER_REFS),
        "can_claim_retrieval_adapter_evidence": True,
        "can_claim_source_side_warming": False,
        "source_reopen_required_for_claims": True,
    }

    if mode == "semantic":
        payload.update(
            {
                "mode_classification": "query_time_llm_rerank_upper_bound",
                "claim_level": "benchmark_local_experiment",
                "benchmark_local_scaffolding": [
                    "temporary_provider_prompt",
                    "query_time_candidate_window_to_line_rerank",
                    "provider_budget_checkpoint",
                ],
                "relevant_aippocampus_paths_not_used": list(
                    _CANONICAL_SOURCE_SIDE_OWNER_REFS
                ),
                "remaining_gap_issue": "#1323",
            }
        )
        return payload

    if mode == "source_semantic_cache" and materializer != "off":
        payload.update(
            {
                "mode_classification": "source_semantic_scope_sidecar_cache",
                "claim_level": "materialized_public_semantic_sidecar_benchmark",
                "aippocampus_capabilities_used": [
                    *_BASE_CAPABILITIES,
                    "semantic_scope_labeling",
                    "semantic_scope_builder",
                    "canonical_semantic_scope_sidecar",
                    "aippocampus_working_memory_rows",
                    "subconscious_candidate_matcher",
                    "source_artifact_cache",
                ],
                "benchmark_local_scaffolding": [
                    "longmemeval_public_source_candidate_batcher",
                    "worker_surface_rerank_fusion",
                ],
                "relevant_aippocampus_paths_not_used": [
                    "warm_ambient_routes",
                    "attention_router",
                ],
                "can_claim_source_side_warming": True,
                "measures_issue": "#1323",
                "source_semantic_sidecar_materializer": materializer,
            }
        )
        return payload

    if mode == "source_semantic_cache":
        payload.update(
            {
                "mode_classification": "source_worker_surface_proxy",
                "claim_level": "aippocampus_proxy_baseline",
                "aippocampus_capabilities_used": [
                    *_BASE_CAPABILITIES,
                    "aippocampus_working_memory_rows",
                    "subconscious_candidate_matcher",
                    "source_artifact_cache",
                ],
                "benchmark_local_scaffolding": [
                    "benchmark_case_source_artifact_materializer",
                    "worker_surface_rerank_fusion",
                ],
                "relevant_aippocampus_paths_not_used": list(
                    _CANONICAL_SOURCE_SIDE_OWNER_REFS
                ),
                "remaining_gap_issue": "#1323",
            }
        )
        return payload

    if mode in {"lexical", "structural"}:
        payload.update(
            {
                "mode_classification": f"{mode}_line_reranker_diagnostic",
                "claim_level": "deterministic_reranker_diagnostic",
                "benchmark_local_scaffolding": [f"{mode}_line_reranker"],
                "relevant_aippocampus_paths_not_used": list(
                    _CANONICAL_SOURCE_SIDE_OWNER_REFS
                ),
                "remaining_gap_issue": "#1323",
            }
        )
        return payload

    payload.update(
        {
            "mode_classification": "cold_deterministic_retrieval",
            "claim_level": "aippocampus_capability_measurement",
        }
    )
    return payload
