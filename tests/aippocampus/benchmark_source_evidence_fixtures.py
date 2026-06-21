from __future__ import annotations


def fake_fts5_payload(*, ok: bool = True) -> dict:
    return {
        "schema_version": 1,
        "kind": "aippocampus_fts5_recall_benchmark",
        "generated_at": "2026-05-27T00:00:00Z",
        "registry": "FAKE_TEST_PRIVATE_REGISTRY_PATH",
        "config": {
            "requested_cases": 2,
            "min_cases": 1,
            "seed": 123,
            "top_k": 10,
            "candidate_limit": 5,
            "include_private_text": False,
            "compare_production": True,
        },
        "corpus": {
            "registry_threads": 3,
            "eligible_threads": 2,
            "messages_scanned": 20,
        },
        "metrics": {
            "total_cases": 2,
            "case_types": {"source_phrase": 2},
            "fts5": {
                "hit_top1": 1,
                "miss_top1": 1,
                "hit_rate_top1": 0.5,
                "hit_top3": 2,
                "miss_top3": 0,
                "hit_rate_top3": 1.0,
                "hit_top5": 2,
                "miss_top5": 0,
                "hit_rate_top5": 1.0,
                "hit_top10": 2,
                "miss_top10": 0,
                "hit_rate_top10": 1.0,
                "mrr": 0.75,
            },
            "production_hybrid": {
                "hit_top10": 1,
                "miss_top10": 1,
                "hit_rate_top10": 0.5,
                "mrr": 0.5,
            },
        },
        "cases": [
            {
                "case_id": "case-a",
                "query_sha1": "hash-a",
                "fts5": {"rank": 1},
            },
            {
                "case_id": "case-b",
                "query": "private prompt text",
                "snippet": "private snippet",
                "clean_source": "FAKE_TEST_PRIVATE_CLEAN_SOURCE",
                "fts5": {"rank": 3},
            },
        ],
        "elapsed_ms": 12.3,
        "ok": ok,
    }

def fake_source_payload(*, ok: bool = True) -> dict:
    status = "sufficient" if ok else "insufficient_recall_hits"
    return {
        "ok": ok,
        "status": status,
        "claim_level": "selected_source_evidence_recall_eval",
        "cannot_claim": ["global_recall_quality"],
        "prompt_kind": "fuzzy_life_wide_source_evidence",
        "case_count": 2,
        "passed_count": 1 if ok else 0,
        "failed_count": 1 if ok else 2,
        "top_k": 5,
        "top_k_hit_rate": 0.5 if ok else 0.0,
        "rate_estimates": {
            "top_k_hit_rate": {
                "name": "top_k_hit_rate",
                "numerator": 1 if ok else 0,
                "denominator": 2,
                "point_estimate": 0.5 if ok else 0.0,
                "confidence_interval": {"method": "wilson_score"},
            }
        },
        "min_cases": 1,
        "min_hit_rate": 0.5,
        "label_coverage": ["casual_important"],
        "warning_count": 0,
        "ranking": "dynamic_source",
        "selection": {
            "mode": "semantic_sidecar_required",
            "require_semantic_sidecar": True,
            "deterministic_label_fallback": False,
        },
        "selection_explanation": {
            "mode": "semantic_sidecar_required",
            "selected_case_count": 2,
            "min_cases": 1,
            "sample_gap": 0,
            "next_action": "Semantic sidecar-selected sample is large enough; read quality diagnostics next.",
        },
        "cases": [
            {
                "case_id": "evidence:a",
                "prompt_kind": "fuzzy_life_wide_source_evidence",
                "scope_labels": ["casual_important"],
                "expected_evidence": "evidence:abc",
                "passed": True,
                "rank": 2,
            }
        ],
        "failure_diagnostics": {
            "failed_count": 1,
            "categories": {"rank_below_top_k": 1},
            "failed_cases": [
                {
                    "case_id": "evidence:miss",
                    "category": "rank_below_top_k",
                    "extended_rank": 12,
                }
            ],
        },
        "privacy_boundary": {
            "raw_text_emitted": False,
            "absolute_paths_emitted": False,
        },
    }

def fake_sharegpt_public_payload(*, ok: bool = True) -> dict:
    status = "sufficient" if ok else "insufficient_message_recall"
    return {
        "ok": ok,
        "status": status,
        "kind": "sharegpt_public_source_evidence_retrieval",
        "config": {
            "conversations": 2,
            "max_cases": 4,
            "top_k": 5,
            "include_private_text": False,
        },
        "corpus": {
            "conversation_count": 2,
            "messages_scanned": 6,
            "eligible_conversations": 2,
        },
        "metrics": {
            "total_cases": 4,
            "case_types": {"sharegpt_answer_source_evidence": 3},
            "message_hit_rate_top5": 1.0 if ok else 0.5,
            "turn_hit_rate_top5": 1.0,
        },
        "cases": [
            {
                "case_id": "sharegpt-public-a",
                "query_sha1": "hash",
                "message_rank": 1,
                "turn_rank": 1,
            }
        ],
        "privacy_boundary": {
            "raw_text_emitted": False,
            "absolute_paths_emitted": False,
        },
        "cannot_claim": ["private_real_history_source_evidence_quality"],
    }

def fake_standard_public_payload(*, ok: bool = True) -> dict:
    status = "sufficient" if ok else "insufficient_session_recall"
    return {
        "ok": ok,
        "status": status,
        "kind": "standard_public_retrieval_qa_source_evidence",
        "config": {
            "dataset": "locomo",
            "max_questions": 2,
            "top_k": 5,
            "include_private_text": False,
        },
        "corpus": {
            "dataset": "locomo",
            "questions_scanned": 2,
            "eligible_questions": 2,
        },
        "metrics": {
            "question_count": 2,
            "session_hit_rate_top5": 1.0 if ok else 0.5,
            "session_mrr": 1.0,
            "evidence_line_case_count": 2,
            "evidence_hit_rate_top5": 1.0 if ok else 0.5,
            "evidence_context_radius": 5,
            "evidence_context_hit_rate_top5": 1.0 if ok else 0.5,
        },
        "cases": [{"case_id": "standard-a", "query_sha1": "hash"}],
        "privacy_boundary": {
            "raw_text_emitted": False,
            "absolute_paths_emitted": False,
        },
        "cannot_claim": ["answer_generation_quality"],
    }

def fake_skipped_standard_public_payload() -> dict:
    payload = fake_standard_public_payload()
    payload.update(
        {
            "ok": True,
            "status": "skipped_missing_standard_corpus",
            "corpus": {
                "dataset": "locomo",
                "questions_scanned": 0,
                "eligible_questions": 0,
            },
            "metrics": {"question_count": 0, "case_types": {}},
            "cases": [],
            "cannot_claim": [
                "standard_retrieval_qa_score",
                "answer_generation_quality",
                "decision_gate_quality",
            ],
        }
    )
    return payload

def fake_public_semantic_sidecar_payload(*, ok: bool = True) -> dict:
    status = "diagnostic_only" if ok else "insufficient_recall_hits"
    claim_level = "diagnostic_pilot" if ok else "diagnostic_only"
    return {
        "ok": ok,
        "status": status,
        "claim_level": claim_level,
        "sample_case_count": 2,
        "minimum_empirical_case_count": 50,
        "selection_method": "bounded ShareGPT clean-source semantic-sidecar pilot",
        "sample_size_warning": {
            "sample_case_count": 2,
            "minimum_empirical_case_count": 50,
            "claim_level": claim_level,
            "selection_method": "bounded ShareGPT clean-source semantic-sidecar pilot",
            "cannot_claim": [
                "empirical_public_semantic_sidecar_quality_below_minimum_case_count"
            ],
        },
        "kind": "public_semantic_sidecar_source_evidence",
        "config": {
            "conversations": 2,
            "max_messages": 4,
            "min_cases": 1,
            "top_k": 5,
            "include_private_text": False,
        },
        "corpus": {
            "conversation_count": 2,
            "subset_message_count": 4,
            "candidate_message_count": 2,
        },
        "artifacts": {
            "sidecar_row_count": 2,
            "reviewed_sidecar_row_count": 2,
            "artifact_dir_sha1": "abc123",
            "absolute_paths_emitted": False,
        },
        "metrics": {
            "case_count": 2,
            "passed_count": 2,
            "failed_count": 0,
            "top_k_hit_rate": 1.0,
        },
        "cases": [{"case_id": "public-semantic-a", "passed": True, "rank": 1}],
        "privacy_boundary": {
            "raw_text_emitted": False,
            "absolute_paths_emitted": False,
        },
        "cannot_claim": [
            "private_real_history_source_evidence_quality",
            "empirical_public_semantic_sidecar_quality_below_minimum_case_count",
        ],
    }
