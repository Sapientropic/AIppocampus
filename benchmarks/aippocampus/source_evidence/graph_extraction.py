"""Synthetic graph-extraction boundary fixtures for Track B.

These fixtures model Graphiti-style scale and structured-output failure modes
without depending on Graphiti or any live LLM. The contract is deliberately
small: graph/semantic sidecars may navigate, but clean-source index retrieval
must still work when extraction is skipped, slow, stale, or structurally wrong.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __name__ == "__main__" and __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from benchmark_entrypoints import library_only_main

    raise SystemExit(
        library_only_main(
            module_path="benchmarks/aippocampus/source_evidence/graph_extraction.py",
            supported_runner="benchmarks/aippocampus/benchmark_source_evidence_retrieval.py",
            summary="It provides Track B graph-extraction boundary fixtures.",
        )
    )

from aippocampus_runtime.recall.index_builder import make_sqlite
from aippocampus_runtime.recall.retrieval import search_hybrid_index, split_query_terms

from .reporting import claim_boundary, query_origin, rank_metrics, sha1_text

GRAPH_EXTRACTION_CANNOT_CLAIM = [
    "graph_sidecar_quality",
    "graph_memory_speed_or_superiority",
    "unsupported_graph_facts_are_source_evidence",
    "foreground_llm_extraction_required",
    "live_graphiti_adapter_compatibility",
]
HOOK_LATENCY_BOUNDARY_MS = 250


@dataclass(frozen=True)
class GraphExtractionFixture:
    case_id: str
    doc_size_bucket: str
    target_bytes: int
    query: str
    sentinel: str
    graph_sidecar_status: str
    graph_failure_mode: str
    graph_sidecar_payload: dict[str, Any]
    expected_source_action: str


def _padded_doc(*, sentinel: str, target_bytes: int) -> str:
    preface = (
        "# Canonical public fixture\n\n"
        "This synthetic document is intentionally boring. It exists so local "
        "source-index retrieval can be tested without asking a foreground LLM "
        "to extract an entity graph before the source remains searchable.\n\n"
    )
    repeated = (
        "The canonical source substrate stays authoritative even when a graph "
        "sidecar is skipped, slow, stale, malformed, or merely advisory. "
        "Generated relations are navigation hints, not source-backed facts.\n"
    )
    body = preface
    while len((body + sentinel).encode("utf-8")) < target_bytes:
        body += repeated
    return body + "\n" + sentinel + "\n"


def graph_extraction_fixtures() -> list[GraphExtractionFixture]:
    return [
        GraphExtractionFixture(
            case_id="graph-scale-5kb-skip-extraction",
            doc_size_bucket="5kb",
            target_bytes=5 * 1024,
            query="skip extraction still source searchable kestrel boundary",
            sentinel=(
                "Kestrel boundary note: a 5KB canonical document must remain "
                "source searchable when graph extraction is skipped."
            ),
            graph_sidecar_status="skipped",
            graph_failure_mode="skip_extraction_requested",
            graph_sidecar_payload={"status": "skipped", "nodes": [], "edges": []},
            expected_source_action="use_source_index",
        ),
        GraphExtractionFixture(
            case_id="graph-scale-50kb-timeout",
            doc_size_bucket="50kb",
            target_bytes=50 * 1024,
            query="timeout graph extraction local source index lantern marker",
            sentinel=(
                "Lantern marker: a 50KB canonical document must be recoverable "
                "through the local source index after graph extraction times out."
            ),
            graph_sidecar_status="unavailable",
            graph_failure_mode="timeout",
            graph_sidecar_payload={"status": "timeout", "retryable": True},
            expected_source_action="use_source_index",
        ),
        GraphExtractionFixture(
            case_id="graph-invalid-unsupported-relation",
            doc_size_bucket="5kb",
            target_bytes=5 * 1024,
            query="Neon City residence unsupported relation source row",
            sentinel=(
                "Neon City source row: Neon City is a fictional example, not a "
                "source-backed residence or user profile fact."
            ),
            graph_sidecar_status="advisory",
            graph_failure_mode="unsupported_relation",
            graph_sidecar_payload={
                "status": "advisory",
                "relation": {
                    "subject": "user",
                    "predicate": "lives_in",
                    "object": "Neon City",
                    "source_refs": [],
                },
            },
            expected_source_action="downgrade_graph_fact_to_navigation",
        ),
        GraphExtractionFixture(
            case_id="graph-invalid-duplicate-entity-resolution",
            doc_size_bucket="5kb",
            target_bytes=5 * 1024,
            query="duplicate entity resolution source reopened cinder marker",
            sentinel=(
                "Cinder marker: duplicate entity resolution is malformed until "
                "the clean source is reopened and the source row is checked."
            ),
            graph_sidecar_status="advisory",
            graph_failure_mode="duplicate_or_malformed_entities",
            graph_sidecar_payload={
                "status": "malformed",
                "entities": [
                    {"id": "entity-a", "name": "Cinder"},
                    {"id": "entity-a", "name": "Cinder duplicate"},
                    {"name": None, "canonical_id": "missing"},
                ],
            },
            expected_source_action="downgrade_graph_fact_to_navigation",
        ),
    ]


def _message_for_index(case: GraphExtractionFixture, doc: str) -> dict[str, Any]:
    return {
        "line": 100,
        "timestamp": "2026-06-09T00:00:00Z",
        "role": "user",
        "kind": "message",
        "phase": "",
        "turn_index": 1,
        "is_final": False,
        "sha1": sha1_text(case.case_id + doc),
        "text": doc,
    }


def _rank_for_expected(results: list[dict[str, Any]], *, expected_line: int) -> int | None:
    for index, result in enumerate(results, start=1):
        if int(result.get("line") or 0) == expected_line:
            return index
    return None


def evaluate_graph_extraction_fixture(
    case: GraphExtractionFixture,
    *,
    top_k: int = 3,
    include_private_text: bool = False,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="aippocampus-graph-boundary-") as tmp:
        root = Path(tmp)
        sqlite_path = root / "source_index.sqlite"
        doc = _padded_doc(sentinel=case.sentinel, target_bytes=case.target_bytes)
        message = _message_for_index(case, doc)
        build_report = make_sqlite(
            sqlite_path,
            [message],
            [],
            [],
            rag_cache=True,
            publish_lock=False,
        )
        query_terms = split_query_terms([case.query])
        results = search_hybrid_index(
            sqlite_path,
            query_terms,
            query_terms,
            [],
            limit=top_k,
            candidate_limit=12,
            snippet_chars=220,
            use_rag_chunks=True,
        )
    rank = _rank_for_expected(results, expected_line=int(message["line"]))
    source_hit = rank is not None and rank <= top_k
    graph_fact_usable_as_evidence = False
    passed = source_hit and not graph_fact_usable_as_evidence
    payload: dict[str, Any] = {
        "case_id": case.case_id,
        "doc_size_bucket": case.doc_size_bucket,
        "doc_bytes": len(doc.encode("utf-8")),
        "query_sha1": sha1_text(case.query)[:16],
        "query_terms_count": len(query_terms),
        "expected_line": int(message["line"]),
        "source_hit": source_hit,
        "source_rank": rank,
        "source": {"rank": rank},
        "passed": passed,
        "graph_sidecar_status": case.graph_sidecar_status,
        "graph_failure_mode": case.graph_failure_mode,
        "graph_fact_action": case.expected_source_action,
        "graph_fact_usable_as_evidence": graph_fact_usable_as_evidence,
        "foreground_extraction_required": False,
        "hook_latency_boundary_ms": HOOK_LATENCY_BOUNDARY_MS,
        "index_build": {
            "fts_enabled": bool(build_report.get("fts_enabled")),
            "rag_enabled": bool((build_report.get("rag") or {}).get("enabled")),
            "rag_chunk_count": int((build_report.get("rag") or {}).get("chunk_count") or 0),
        },
        "cannot_claim": GRAPH_EXTRACTION_CANNOT_CLAIM,
    }
    if include_private_text:
        payload["query"] = case.query
        payload["sentinel"] = case.sentinel
        payload["top_result_snippets"] = [str(item.get("snippet") or "") for item in results]
        payload["graph_sidecar_payload"] = case.graph_sidecar_payload
    return payload


def summarize_graph_extraction_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": payload.get("kind") or "graph_extraction_boundary_source_evidence",
        "ok": bool(payload.get("ok")),
        "status": payload.get("status"),
        "config": payload.get("config") or {},
        "metrics": payload.get("metrics") or {},
        "query_origin": query_origin(
            "human_or_fixture_question",
            query_author="benchmark_fixture",
            notes=(
                "Synthetic graph-extraction failure prompts are authored outside "
                "the target source text and check local source-index fallback."
            ),
        ),
        "claim_boundary": claim_boundary(
            measures=(
                "source-index fallback and graph-sidecar authority boundary under "
                "synthetic extraction failure modes"
            ),
            can_claim=[
                "clean_source_index_remains_queryable_when_graph_extraction_is_not_evidence"
            ],
            cannot_claim=GRAPH_EXTRACTION_CANNOT_CLAIM,
        ),
        "cannot_claim": payload.get("cannot_claim") or GRAPH_EXTRACTION_CANNOT_CLAIM,
    }


def run_graph_extraction_boundary_benchmark(
    *,
    top_k: int = 3,
    include_private_text: bool = False,
) -> dict[str, Any]:
    cases = [
        evaluate_graph_extraction_fixture(
            case,
            top_k=top_k,
            include_private_text=include_private_text,
        )
        for case in graph_extraction_fixtures()
    ]
    metrics = rank_metrics(cases, "source", [top_k])
    metrics.update(
        {
            "case_count": len(cases),
            "passed_count": sum(1 for case in cases if case["passed"]),
            "failed_count": sum(1 for case in cases if not case["passed"]),
            "source_hit_rate_top_k": round(
                sum(1 for case in cases if case["source_hit"]) / len(cases),
                4,
            )
            if cases
            else 0.0,
            "graph_sidecar_status_counts": {
                status: sum(1 for case in cases if case["graph_sidecar_status"] == status)
                for status in sorted({str(case["graph_sidecar_status"]) for case in cases})
            },
            "graph_failure_mode_counts": {
                mode: sum(1 for case in cases if case["graph_failure_mode"] == mode)
                for mode in sorted({str(case["graph_failure_mode"]) for case in cases})
            },
            "unsupported_graph_facts_as_evidence_count": sum(
                1 for case in cases if case["graph_fact_usable_as_evidence"]
            ),
            "foreground_extraction_required_count": sum(
                1 for case in cases if case["foreground_extraction_required"]
            ),
            "max_doc_bytes": max((int(case["doc_bytes"]) for case in cases), default=0),
            "hook_latency_boundary_ms": HOOK_LATENCY_BOUNDARY_MS,
        }
    )
    ok = (
        bool(cases)
        and metrics["passed_count"] == len(cases)
        and metrics["unsupported_graph_facts_as_evidence_count"] == 0
        and metrics["foreground_extraction_required_count"] == 0
    )
    return {
        "schema_version": 1,
        "kind": "graph_extraction_boundary_source_evidence",
        "status": "sufficient" if ok else "diagnostic_only",
        "ok": ok,
        "config": {
            "top_k": int(top_k),
            "include_private_text": bool(include_private_text),
            "requires_external_llm": False,
            "requires_graph_adapter": False,
        },
        "metrics": metrics,
        "cases": cases,
        "privacy_boundary": {
            "raw_text_emitted": bool(include_private_text),
            "absolute_paths_emitted": False,
            "graph_payload_emitted": bool(include_private_text),
        },
        "cannot_claim": GRAPH_EXTRACTION_CANNOT_CLAIM,
    }


if __name__ == "__main__":
    from ..benchmark_entrypoints import library_only_main

    raise SystemExit(
        library_only_main(
            module_path="benchmarks/aippocampus/source_evidence/graph_extraction.py",
            supported_runner="benchmarks/aippocampus/benchmark_source_evidence_retrieval.py",
            summary="It provides Track B graph-extraction boundary fixtures.",
        )
    )
