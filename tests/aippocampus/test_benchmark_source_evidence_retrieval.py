from __future__ import annotations

import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import benchmark_source_evidence_retrieval as benchmark  # noqa: E402


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


class SourceEvidenceRetrievalBenchmarkTests(unittest.TestCase):
    def test_track_b_runner_is_split_into_track_owned_modules(self) -> None:
        source_path = REPO_ROOT / "benchmarks" / "aippocampus" / "benchmark_source_evidence_retrieval.py"

        line_count = len(source_path.read_text(encoding="utf-8").splitlines())

        self.assertLess(line_count, 1800)
        for module_name in (
            "source_evidence.fts5_source_line",
            "source_evidence.selected_source",
            "source_evidence.sharegpt_public",
            "source_evidence.public_semantic",
            "source_evidence.standard_public",
        ):
            importlib.import_module(module_name)

    def write_jsonl(self, path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )

    def test_selected_source_evidence_defaults_use_100_case_slice(self) -> None:
        self.assertEqual(benchmark.DEFAULT_SOURCE_MAX_CASES, 100)
        self.assertEqual(benchmark.DEFAULT_SOURCE_MIN_CASES, 50)

    def test_track_b_help_explains_deterministic_label_fallback_boundary(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "benchmarks" / "aippocampus" / "benchmark_source_evidence_retrieval.py"),
                "--help",
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--allow-deterministic-labels", proc.stdout)
        self.assertIn("--only-standard-public", proc.stdout)
        self.assertIn("--skip-graph-extraction-boundary", proc.stdout)
        normalized_help = " ".join(proc.stdout.split())
        self.assertIn("cannot claim", normalized_help)
        self.assertIn("sidecar sample coverage", normalized_help)

    def test_sharegpt_manifest_marks_tiny_semantic_sidecar_pilot_diagnostic(self) -> None:
        manifest = json.loads(
            (REPO_ROOT / "benchmark_corpus" / "sharegpt_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        semantic_entry = next(
            item
            for item in manifest["benchmark_entrypoints"]
            if item["track"] == "Track B public semantic-sidecar pilot"
        )
        result = semantic_entry["latest_local_result"]

        self.assertEqual(result["status"], "diagnostic_only")
        self.assertEqual(result["claim_level"], "diagnostic_pilot")
        self.assertEqual(result["selected_case_count"], 3)
        self.assertGreater(
            result["minimum_empirical_case_count"],
            result["selected_case_count"],
        )
        self.assertIn(
            "empirical_public_semantic_sidecar_quality_below_minimum_case_count",
            result["sample_size_warning"]["cannot_claim"],
        )

    def test_track_b_report_wraps_existing_real_history_evals_without_private_text(self) -> None:
        with (
            patch.object(benchmark.fts5_benchmark, "run_benchmark", return_value=fake_fts5_payload())
            as fts_run,
            patch.object(
                benchmark.source_evidence_eval,
                "run_source_evidence_recall_eval",
                return_value=fake_source_payload(),
            ) as source_run,
        ):
            payload = benchmark.run_source_evidence_retrieval_benchmark(
                fts5_cases=2,
                fts5_min_cases=1,
                fts5_top_k=10,
                source_max_cases=2,
                source_min_cases=1,
                source_top_k=5,
                include_private_text=False,
            )

        self.assertEqual(payload["kind"], "aippocampus_source_evidence_retrieval_benchmark")
        self.assertTrue(payload["ok"])
        self.assertNotIn("registry", payload)
        self.assertEqual(payload["privacy_boundary"]["raw_text_emitted"], False)
        self.assertEqual(payload["privacy_boundary"]["absolute_paths_emitted"], False)
        self.assertEqual(payload["tracks"]["fts5_source_line"]["hit_rate_top10"], 1.0)
        self.assertIn("rate_estimates", payload["tracks"]["fts5_source_line"])
        self.assertEqual(
            payload["tracks"]["fts5_source_line"]["query_origin"]["category"],
            "source_derived_sparse",
        )
        self.assertEqual(
            payload["tracks"]["fts5_source_line"]["claim_boundary"]["measures"],
            "index_health_sanity",
        )
        self.assertEqual(payload["tracks"]["source_evidence"]["top_k_hit_rate"], 0.5)
        self.assertEqual(
            payload["tracks"]["source_evidence"]["query_origin"]["bucket"],
            "source_derived",
        )
        self.assertEqual(
            payload["tracks"]["source_evidence"]["rate_estimates"]["top_k_hit_rate"][
                "denominator"
            ],
            2,
        )
        self.assertEqual(
            payload["tracks"]["source_evidence"]["failure_diagnostics"]["failed_count"],
            1,
        )
        self.assertEqual(
            payload["tracks"]["source_evidence"]["selection"]["mode"],
            "semantic_sidecar_required",
        )
        self.assertEqual(
            payload["tracks"]["source_evidence"]["selection_explanation"]["sample_gap"],
            0,
        )
        self.assertEqual(
            payload["tracks"]["source_evidence"]["cannot_claim"],
            ["global_recall_quality"],
        )
        self.assertNotIn("query", payload["cases"]["fts5"][1])
        self.assertNotIn("snippet", payload["cases"]["fts5"][1])
        self.assertNotIn("clean_source", payload["cases"]["fts5"][1])
        self.assertNotIn("FAKE_TEST_PRIVATE_REGISTRY_PATH", json.dumps(payload))
        self.assertNotIn("FAKE_TEST_PRIVATE_CLEAN_SOURCE", json.dumps(payload))
        self.assertIn("real_history_gate_quality", payload["cannot_claim"])
        self.assertIn("natural_user_query_recall", payload["cannot_claim"])
        self.assertEqual(
            payload["query_origin_summary"]["source_derived"]["tracks"],
            ["fts5_source_line", "source_evidence"],
        )
        self.assertIn(
            "graph_extraction_boundary",
            payload["query_origin_summary"]["non_source_derived"]["tracks"],
        )
        self.assertIn("graph_sidecar_quality", payload["cannot_claim"])
        source_rates = payload["query_origin_summary"]["source_derived"]["hit_rates"]
        self.assertIn(
            {
                "track": "fts5_source_line",
                "metric": "hit_rate_top10",
                "value": 1.0,
            },
            source_rates,
        )
        fts_run.assert_called_once()
        self.assertEqual(fts_run.call_args.kwargs["include_private_text"], False)
        source_run.assert_called_once()

    def test_track_b_report_is_diagnostic_when_selected_source_evidence_fails(self) -> None:
        with (
            patch.object(benchmark.fts5_benchmark, "run_benchmark", return_value=fake_fts5_payload()),
            patch.object(
                benchmark.source_evidence_eval,
                "run_source_evidence_recall_eval",
                return_value=fake_source_payload(ok=False),
            ),
        ):
            payload = benchmark.run_source_evidence_retrieval_benchmark(
                fts5_cases=2,
                fts5_min_cases=1,
                source_max_cases=2,
                source_min_cases=1,
                source_min_hit_rate=0.5,
            )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "diagnostic_only")
        self.assertIn("selected_source_evidence_recall", payload["cannot_claim"])

    def test_track_b_reports_portable_smoke_hint_when_semantic_sidecar_cases_are_absent(
        self,
    ) -> None:
        source_payload = fake_source_payload(ok=False)
        source_payload.update(
            {
                "status": "insufficient_selected_cases",
                "case_count": 0,
                "passed_count": 0,
                "failed_count": 0,
                "top_k_hit_rate": 0.0,
                "selection": {
                    "mode": "semantic_sidecar_required",
                    "require_semantic_sidecar": True,
                    "deterministic_label_fallback": False,
                },
                "selection_explanation": {
                    "mode": "semantic_sidecar_required",
                    "selected_case_count": 0,
                    "min_cases": 1,
                    "sample_gap": 1,
                    "next_action": (
                        "Refresh semantic sidecars for the quality check, or rerun "
                        "with --allow-deterministic-labels as a wiring baseline."
                    ),
                },
                "cannot_claim": [
                    "selected_semantic_source_evidence",
                    "semantic_sidecar_sample_coverage",
                ],
            }
        )
        with (
            patch.object(benchmark.fts5_benchmark, "run_benchmark", return_value=fake_fts5_payload()),
            patch.object(
                benchmark.source_evidence_eval,
                "run_source_evidence_recall_eval",
                return_value=source_payload,
            ),
        ):
            payload = benchmark.run_source_evidence_retrieval_benchmark(
                fts5_cases=1,
                fts5_min_cases=1,
                source_max_cases=1,
                source_min_cases=1,
            )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "diagnostic_only")
        guidance = payload["validation_guidance"]["track_b_source_evidence"]
        self.assertEqual(guidance["problem"], "semantic_sidecar_selected_cases_absent")
        self.assertEqual(guidance["portable_smoke_mode"], "deterministic_label_fallback")
        self.assertIn("--allow-deterministic-labels", guidance["portable_smoke_command"])
        parent_claims = set(payload["cannot_claim"])
        self.assertIn("semantic_sidecar_sample_coverage", parent_claims)
        self.assertIn("selected_semantic_source_evidence", parent_claims)
        self.assertEqual(guidance["cannot_claim"], ["deterministic_label_fallback_is_not_semantic_sidecar_evidence"])
        self.assertEqual(
            guidance["inherited_boundaries"],
            {"source": "parent report", "count": 2},
        )
        self.assertIn("memory-decision-benchmark-plan.md#track-b-source-evidence-retrieval", guidance["boundary_ref"])

    def test_track_b_wrapper_can_include_sharegpt_public_track(self) -> None:
        with (
            patch.object(benchmark.fts5_benchmark, "run_benchmark", return_value=fake_fts5_payload()),
            patch.object(
                benchmark.source_evidence_eval,
                "run_source_evidence_recall_eval",
                return_value=fake_source_payload(),
            ),
            patch.object(
                benchmark,
                "run_sharegpt_public_source_evidence_benchmark",
                return_value=fake_sharegpt_public_payload(),
            ) as sharegpt_run,
        ):
            payload = benchmark.run_source_evidence_retrieval_benchmark(
                fts5_cases=2,
                fts5_min_cases=1,
                source_max_cases=2,
                source_min_cases=1,
                include_sharegpt_public=True,
                sharegpt_public_conversations=2,
                sharegpt_public_max_cases=4,
                sharegpt_public_min_cases=2,
                sharegpt_public_top_k=5,
            )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["config"]["include_sharegpt_public"])
        self.assertIn("sharegpt_public_source_evidence", payload["tracks"])
        self.assertEqual(
            payload["tracks"]["sharegpt_public_source_evidence"]["metrics"][
                "message_hit_rate_top5"
            ],
            1.0,
        )
        self.assertIn("sharegpt_public", payload["cases"])
        self.assertEqual(payload["cases"]["sharegpt_public"][0]["case_id"], "sharegpt-public-a")
        sharegpt_run.assert_called_once()
        self.assertEqual(sharegpt_run.call_args.kwargs["conversations"], 2)
        self.assertEqual(sharegpt_run.call_args.kwargs["max_cases"], 4)

    def test_track_b_wrapper_can_include_standard_public_retrieval_qa(self) -> None:
        with (
            patch.object(benchmark.fts5_benchmark, "run_benchmark", return_value=fake_fts5_payload()),
            patch.object(
                benchmark.source_evidence_eval,
                "run_source_evidence_recall_eval",
                return_value=fake_source_payload(),
            ),
            patch.object(
                benchmark,
                "run_standard_retrieval_qa_benchmark",
                return_value=fake_standard_public_payload(),
            ) as standard_run,
        ):
            payload = benchmark.run_source_evidence_retrieval_benchmark(
                fts5_cases=2,
                fts5_min_cases=1,
                source_max_cases=2,
                source_min_cases=1,
                include_standard_public=True,
                standard_dataset="locomo",
                standard_max_questions=2,
                standard_min_questions=1,
                standard_top_k=5,
            )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["config"]["include_standard_public"])
        self.assertIn("standard_public_retrieval_qa", payload["tracks"])
        self.assertEqual(
            payload["tracks"]["standard_public_retrieval_qa"]["query_origin"]["category"],
            "human_or_fixture_question",
        )
        self.assertEqual(
            payload["tracks"]["standard_public_retrieval_qa"]["query_origin"]["bucket"],
            "non_source_derived",
        )
        self.assertEqual(
            payload["tracks"]["standard_public_retrieval_qa"]["claim_boundary"]["measures"],
            "user_like_source_navigation",
        )
        self.assertEqual(
            payload["tracks"]["standard_public_retrieval_qa"]["metrics"][
                "session_hit_rate_top5"
            ],
            1.0,
        )
        self.assertIn("standard_public_retrieval_qa", payload["cases"])
        self.assertEqual(
            payload["cases"]["standard_public_retrieval_qa"][0]["case_id"],
            "standard-a",
        )
        standard_run.assert_called_once()
        self.assertEqual(standard_run.call_args.kwargs["dataset"], "locomo")
        self.assertEqual(standard_run.call_args.kwargs["max_questions"], 2)
        non_source = payload["query_origin_summary"]["non_source_derived"]
        self.assertIn("standard_public_retrieval_qa", non_source["tracks"])
        self.assertIn("graph_extraction_boundary", non_source["tracks"])
        self.assertIn(
            {
                "track": "standard_public_retrieval_qa",
                "metric": "session_hit_rate_top5",
                "value": 1.0,
            },
            non_source["hit_rates"],
        )
        self.assertNotIn("natural_user_query_recall", payload["cannot_claim"])

    def test_standard_public_only_mode_reports_selected_external_track_without_internal_failures(self) -> None:
        with (
            patch.object(benchmark.fts5_benchmark, "run_benchmark") as fts5_run,
            patch.object(benchmark.source_evidence_eval, "run_source_evidence_recall_eval")
            as source_run,
            patch.object(
                benchmark,
                "run_standard_retrieval_qa_benchmark",
                return_value=fake_standard_public_payload(),
            ) as standard_run,
        ):
            payload = benchmark.run_source_evidence_retrieval_benchmark(
                only_standard_public=True,
                standard_dataset="locomo",
                standard_max_questions=2,
                standard_min_questions=1,
                standard_top_k=5,
            )

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["status"], "standard_public_only_sufficient")
        self.assertTrue(payload["config"]["only_standard_public"])
        self.assertTrue(payload["config"]["include_standard_public"])
        self.assertEqual(list(payload["tracks"]), ["standard_public_retrieval_qa"])
        self.assertEqual(list(payload["cases"]), ["standard_public_retrieval_qa"])
        metrics = payload["tracks"]["standard_public_retrieval_qa"]["metrics"]
        self.assertEqual(metrics["session_hit_rate_top5"], 1.0)
        self.assertIn("full_mixed_track_b_bundle", payload["cannot_claim"])
        self.assertNotIn("selected_source_evidence_recall", payload["cannot_claim"])
        with patch("sys.stdout", new_callable=StringIO) as summary:
            benchmark.print_human_summary(payload)
        self.assertIn("- status: standard_public_only_sufficient", summary.getvalue())
        self.assertIn("- locomo retrieval-QA top-5:", summary.getvalue())
        fts5_run.assert_not_called()
        source_run.assert_not_called()
        standard_run.assert_called_once()

    def test_skipped_standard_public_arm_does_not_clear_user_query_boundary(self) -> None:
        with (
            patch.object(benchmark.fts5_benchmark, "run_benchmark", return_value=fake_fts5_payload()),
            patch.object(
                benchmark.source_evidence_eval,
                "run_source_evidence_recall_eval",
                return_value=fake_source_payload(),
            ),
            patch.object(
                benchmark,
                "run_standard_retrieval_qa_benchmark",
                return_value=fake_skipped_standard_public_payload(),
            ),
        ):
            payload = benchmark.run_source_evidence_retrieval_benchmark(
                fts5_cases=2,
                fts5_min_cases=1,
                source_max_cases=2,
                source_min_cases=1,
                include_standard_public=True,
                standard_dataset="locomo",
                standard_max_questions=2,
                standard_min_questions=1,
                standard_top_k=5,
            )

        self.assertEqual(
            payload["tracks"]["standard_public_retrieval_qa"]["query_origin"]["bucket"],
            "non_source_derived",
        )
        non_source_tracks = payload["query_origin_summary"]["non_source_derived"]["tracks"]
        self.assertIn("standard_public_retrieval_qa", non_source_tracks)
        self.assertIn("graph_extraction_boundary", non_source_tracks)
        self.assertIn("natural_user_query_recall", payload["cannot_claim"])
        self.assertIn("semantic_generalized_memory_recall", payload["cannot_claim"])

    def test_track_b_wrapper_can_include_public_semantic_sidecar_track(self) -> None:
        with (
            patch.object(benchmark.fts5_benchmark, "run_benchmark", return_value=fake_fts5_payload()),
            patch.object(
                benchmark.source_evidence_eval,
                "run_source_evidence_recall_eval",
                return_value=fake_source_payload(),
            ),
            patch.object(
                benchmark,
                "run_public_semantic_sidecar_benchmark",
                return_value=fake_public_semantic_sidecar_payload(),
            ) as public_semantic_run,
        ):
            payload = benchmark.run_source_evidence_retrieval_benchmark(
                fts5_cases=2,
                fts5_min_cases=1,
                source_max_cases=2,
                source_min_cases=1,
                include_public_semantic_sidecar=True,
                public_semantic_conversations=2,
                public_semantic_max_messages=4,
                public_semantic_min_cases=1,
                public_semantic_top_k=5,
            )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["config"]["include_public_semantic_sidecar"])
        self.assertIn("public_semantic_sidecar", payload["tracks"])
        self.assertEqual(
            payload["tracks"]["public_semantic_sidecar"]["status"],
            "diagnostic_only",
        )
        self.assertEqual(
            payload["tracks"]["public_semantic_sidecar"]["claim_level"],
            "diagnostic_pilot",
        )
        self.assertEqual(
            payload["tracks"]["public_semantic_sidecar"]["sample_size_warning"][
                "minimum_empirical_case_count"
            ],
            50,
        )
        self.assertEqual(
            payload["tracks"]["public_semantic_sidecar"]["metrics"]["top_k_hit_rate"],
            1.0,
        )
        self.assertIn("public_semantic_sidecar", payload["cases"])
        self.assertEqual(payload["cases"]["public_semantic_sidecar"][0]["case_id"], "public-semantic-a")
        public_semantic_run.assert_called_once()
        self.assertEqual(public_semantic_run.call_args.kwargs["conversations"], 2)
        self.assertEqual(public_semantic_run.call_args.kwargs["max_messages"], 4)

    def test_sharegpt_public_source_evidence_uses_message_and_turn_ground_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus_dir = root / "sharegpt_clean"
            self.write_jsonl(
                corpus_dir / "messages.jsonl",
                [
                    {
                        "message_id": "m1",
                        "turn_id": "t1",
                        "source_id": "conv-a",
                        "source_line": 1,
                        "role": "user",
                        "phase": "",
                        "turn_index": 1,
                        "is_final": False,
                        "text": "How do I debug a Rust lifetime error in an async parser?",
                    },
                    {
                        "message_id": "m2",
                        "turn_id": "t1",
                        "source_id": "conv-a",
                        "source_line": 2,
                        "role": "assistant",
                        "phase": "final_answer",
                        "turn_index": 1,
                        "is_final": True,
                        "text": "Use explicit lifetime bounds on the parser state and avoid holding borrowed references across await points.",
                    },
                    {
                        "message_id": "m3",
                        "turn_id": "t2",
                        "source_id": "conv-a",
                        "source_line": 3,
                        "role": "user",
                        "phase": "",
                        "turn_index": 2,
                        "is_final": False,
                        "text": "Can you continue from the lifetime bounds part?",
                    },
                    {
                        "message_id": "m4",
                        "turn_id": "t2",
                        "source_id": "conv-a",
                        "source_line": 4,
                        "role": "assistant",
                        "phase": "final_answer",
                        "turn_index": 2,
                        "is_final": True,
                        "text": "Continue by moving parser-owned buffers into the async task and returning owned tokens.",
                    },
                    {
                        "message_id": "m5",
                        "turn_id": "t3",
                        "source_id": "conv-b",
                        "source_line": 1,
                        "role": "user",
                        "phase": "",
                        "turn_index": 1,
                        "is_final": False,
                        "text": "继续讲 Python pandas groupby 聚合的时候怎么保留空值",
                    },
                    {
                        "message_id": "m6",
                        "turn_id": "t3",
                        "source_id": "conv-b",
                        "source_line": 2,
                        "role": "assistant",
                        "phase": "final_answer",
                        "turn_index": 1,
                        "is_final": True,
                        "text": "可以使用 dropna=False，并在聚合前显式填充需要保留的分类列。",
                    },
                ],
            )

            payload = benchmark.run_sharegpt_public_source_evidence_benchmark(
                corpus_dir=corpus_dir,
                conversations=2,
                max_cases=12,
                min_cases=3,
                top_k=5,
            )

        self.assertEqual(payload["kind"], "sharegpt_public_source_evidence_retrieval")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "sufficient")
        self.assertGreaterEqual(payload["metrics"]["total_cases"], 3)
        self.assertEqual(payload["metrics"]["message_hit_rate_top5"], 1.0)
        self.assertEqual(payload["metrics"]["turn_hit_rate_top5"], 1.0)
        self.assertEqual(
            payload["metrics"]["rate_estimates"]["message_hit_rate_top5"][
                "confidence_interval"
            ]["method"],
            "wilson_score",
        )
        self.assertIn("sharegpt_answer_source_evidence", payload["metrics"]["case_types"])
        self.assertIn("sharegpt_continuation_source_evidence", payload["metrics"]["case_types"])
        self.assertEqual(payload["privacy_boundary"]["raw_text_emitted"], False)
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("Rust lifetime error", dumped)
        self.assertNotIn("dropna=False", dumped)

    def test_sharegpt_public_sampling_is_seeded_and_summarized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus_dir = root / "sharegpt_clean"
            rows = []
            for conv_index in range(6):
                source_id = f"conv-seeded-{conv_index}"
                rows.extend(
                    [
                        {
                            "message_id": f"{source_id}-m1",
                            "turn_id": f"{source_id}-t1",
                            "source_id": source_id,
                            "source_line": 1,
                            "role": "user",
                            "turn_index": 1,
                            "text": f"How should I handle Python dataframe nulls {conv_index}?",
                            "_meta": {
                                "source_file": "public-sharegpt.jsonl",
                                "category": "program and code",
                            },
                        },
                        {
                            "message_id": f"{source_id}-m2",
                            "turn_id": f"{source_id}-t1",
                            "source_id": source_id,
                            "source_line": 2,
                            "role": "assistant",
                            "phase": "final_answer",
                            "turn_index": 1,
                            "is_final": True,
                            "text": f"Use dropna controls and explicit masks for dataframe nulls {conv_index}.",
                            "_meta": {
                                "source_file": "public-sharegpt.jsonl",
                                "category": "program and code",
                            },
                        },
                    ]
                )
            self.write_jsonl(corpus_dir / "messages.jsonl", rows)

            first = benchmark.run_sharegpt_public_source_evidence_benchmark(
                corpus_dir=corpus_dir,
                conversations=2,
                max_cases=4,
                min_cases=1,
                seed=218,
            )
            repeated = benchmark.run_sharegpt_public_source_evidence_benchmark(
                corpus_dir=corpus_dir,
                conversations=2,
                max_cases=4,
                min_cases=1,
                seed=218,
            )
            first_n = benchmark.run_sharegpt_public_source_evidence_benchmark(
                corpus_dir=corpus_dir,
                conversations=2,
                max_cases=4,
                min_cases=1,
                sampling_mode="first-n",
            )

        self.assertEqual(first["sampling"]["method"], "seeded_stratified")
        self.assertTrue(first["sampling"]["population_scan_complete"])
        self.assertEqual(first["sampling"]["eligible_population_count"], 6)
        self.assertEqual(first["sampling"]["selected_conversation_count"], 2)
        self.assertEqual(
            first["sampling"]["selected_conversation_ids"],
            repeated["sampling"]["selected_conversation_ids"],
        )
        summary = benchmark.summarize_sharegpt_public_payload(first)
        self.assertEqual(
            summary["sampling"]["selected_conversation_ids"],
            first["sampling"]["selected_conversation_ids"],
        )
        self.assertEqual(first_n["sampling"]["method"], "first_n")
        self.assertFalse(first_n["sampling"]["population_scan_complete"])
        self.assertIn("seeded_stratified_population_sampling", first_n["cannot_claim"])
        dumped = json.dumps(first, ensure_ascii=False)
        self.assertNotIn("dataframe nulls", dumped)
        self.assertNotIn("public-sharegpt.jsonl", dumped)

    def test_public_semantic_sidecar_builds_reviewed_bounded_subset(self) -> None:
        def fake_labeler(candidates: list[dict], **_: object) -> dict:
            target = next(item for item in candidates if item["message_id"] == "m1")
            return {
                "available": True,
                "findings": [
                    {
                        "finding_kind": "semantic_scope_labels",
                        "job": "semantic_scope_labeling",
                        "message_id": target["message_id"],
                        "turn_id": target["turn_id"],
                        "scope_labels": ["preference"],
                        "confidence": 0.95,
                        "summary": "The user states a stable preference about examples.",
                        "source_refs": [
                            {
                                "message_id": target["message_id"],
                                "turn_id": target["turn_id"],
                                "source_line": target["source_line"],
                                "role": target["role"],
                                "phase": target.get("phase") or "",
                            }
                        ],
                        "label_evidence": [
                            {
                                "label": "preference",
                                "reason": "The source says precise TypeScript examples are preferred.",
                                "confidence": 0.95,
                            }
                        ],
                    }
                ],
                "labeler_identity": "fixture_public_semantic_labeler",
                "review_status": "validator_reviewed",
                "human_reviewed": False,
                "usage": {"total_tokens": 11},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus_dir = root / "sharegpt_clean"
            output_dir = root / "public_semantic_sidecar"
            self.write_jsonl(
                corpus_dir / "messages.jsonl",
                [
                    {
                        "message_id": "m1",
                        "turn_id": "t1",
                        "source_id": "conv-a",
                        "clean_ordinal": 0,
                        "source_line": 1,
                        "role": "user",
                        "phase": "",
                        "turn_index": 1,
                        "is_final": False,
                        "text": "I prefer precise TypeScript examples because terse advice loses context.",
                    },
                    {
                        "message_id": "m2",
                        "turn_id": "t1",
                        "source_id": "conv-a",
                        "clean_ordinal": 1,
                        "source_line": 2,
                        "role": "assistant",
                        "phase": "final_answer",
                        "turn_index": 1,
                        "is_final": True,
                        "text": "Understood; I will include precise TypeScript examples.",
                    },
                ],
            )

            payload = benchmark.run_public_semantic_sidecar_benchmark(
                corpus_dir=corpus_dir,
                output_dir=output_dir,
                conversations=1,
                max_messages=2,
                min_cases=1,
                top_k=5,
                labeler_fn=fake_labeler,
            )

            sidecar_path = output_dir / "clean-source" / "semantic-scope-labels.jsonl"
            self.assertTrue(sidecar_path.exists())

        self.assertEqual(payload["kind"], "public_semantic_sidecar_source_evidence")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "diagnostic_only")
        self.assertEqual(payload["claim_level"], "diagnostic_pilot")
        self.assertEqual(payload["sample_case_count"], 1)
        self.assertGreater(payload["minimum_empirical_case_count"], payload["sample_case_count"])
        self.assertEqual(
            payload["sample_size_warning"]["sample_case_count"],
            payload["sample_case_count"],
        )
        self.assertIn(
            "empirical_public_semantic_sidecar_quality_below_minimum_case_count",
            payload["sample_size_warning"]["cannot_claim"],
        )
        self.assertIn(
            "empirical_public_semantic_sidecar_quality_below_minimum_case_count",
            payload["cannot_claim"],
        )
        self.assertEqual(payload["artifacts"]["sidecar_row_count"], 1)
        self.assertEqual(payload["artifacts"]["reviewed_sidecar_row_count"], 1)
        self.assertEqual(payload["labeler"]["identity"], "fixture_public_semantic_labeler")
        self.assertEqual(payload["labeler"]["review_status"], "validator_reviewed")
        self.assertFalse(payload["labeler"]["human_reviewed"])
        controls = payload["anti_circular_controls"]
        self.assertEqual(controls["sidecar"]["case_count"], 1)
        self.assertEqual(controls["no_sidecar_baseline"]["control_kind"], "no_sidecar")
        self.assertEqual(controls["wrong_message_negative"]["control_kind"], "wrong_message")
        self.assertFalse(controls["wrong_message_negative"]["quality_gate_ok"])
        self.assertTrue(controls["anti_circular_gate"]["passed"])
        self.assertIn(
            "sidecar_vs_no_sidecar_case_delta",
            controls["control_deltas"],
        )
        self.assertEqual(
            controls["label_review_boundary"]["human_reviewed"], False
        )
        self.assertEqual(payload["metrics"]["case_count"], 1)
        self.assertEqual(payload["metrics"]["top_k_hit_rate"], 1.0)
        self.assertEqual(payload["privacy_boundary"]["raw_text_emitted"], False)
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("precise TypeScript examples", dumped)
        self.assertNotIn(str(output_dir), dumped)

    def test_standard_locomo_retrieval_qa_uses_evidence_dialogue_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            locomo_path = root / "locomo10.json"
            locomo_path.write_text(
                json.dumps(
                    [
                        {
                            "sample_id": "conv-mini",
                            "qa": [
                                {
                                    "question": "Which dessert did Caroline bring?",
                                    "answer": "mango tart",
                                    "evidence": ["D1:2"],
                                    "category": 1,
                                }
                            ],
                            "conversation": {
                                "speaker_a": "Caroline",
                                "speaker_b": "Melanie",
                                "session_1_date_time": "1:00 pm on 8 May, 2023",
                                "session_1": [
                                    {
                                        "speaker": "Melanie",
                                        "dia_id": "D1:1",
                                        "text": "Thanks for coming over.",
                                    },
                                    {
                                        "speaker": "Caroline",
                                        "dia_id": "D1:2",
                                        "text": "I brought a mango tart for dessert.",
                                    },
                                ],
                            },
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = benchmark.run_standard_retrieval_qa_benchmark(
                dataset="locomo",
                corpus_path=locomo_path,
                max_questions=4,
                min_questions=1,
                top_k=5,
            )

        self.assertEqual(payload["kind"], "standard_public_retrieval_qa_source_evidence")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "sufficient")
        self.assertEqual(payload["config"]["dataset"], "locomo")
        self.assertEqual(payload["metrics"]["question_count"], 1)
        self.assertEqual(payload["metrics"]["evidence_hit_rate_top5"], 1.0)
        self.assertEqual(payload["metrics"]["session_hit_rate_top5"], 1.0)
        self.assertIn("session_hit_rate_top5", payload["metrics"]["rate_estimates"])
        self.assertEqual(payload["privacy_boundary"]["raw_text_emitted"], False)
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("mango tart", dumped)
        self.assertNotIn(str(locomo_path), dumped)

    def test_standard_longmemeval_v1_uses_answer_sessions_and_has_answer_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            longmem_path = root / "longmemeval_oracle.json"
            longmem_path.write_text(
                json.dumps(
                    [
                        {
                            "question_id": "q-mini",
                            "question_type": "single-session-user",
                            "question": "What degree did I graduate with?",
                            "answer": "Business Administration",
                            "question_date": "2023/05/30 (Tue) 23:40",
                            "haystack_dates": [
                                "2023/05/20 (Sat) 02:21",
                                "2023/05/21 (Sun) 03:24",
                            ],
                            "haystack_session_ids": ["distractor", "answer_session"],
                            "answer_session_ids": ["answer_session"],
                            "haystack_sessions": [
                                [
                                    {
                                        "role": "user",
                                        "content": "Let's talk about my favorite hiking trail.",
                                    }
                                ],
                                [
                                    {
                                        "role": "user",
                                        "content": "I graduated with a Business Administration degree.",
                                        "has_answer": True,
                                    }
                                ],
                            ],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = benchmark.run_standard_retrieval_qa_benchmark(
                dataset="longmemeval-v1-oracle",
                corpus_path=longmem_path,
                max_questions=4,
                min_questions=1,
                top_k=5,
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["metrics"]["question_count"], 1)
        self.assertEqual(payload["metrics"]["session_hit_rate_top5"], 1.0)
        self.assertEqual(payload["metrics"]["evidence_line_case_count"], 1)
        self.assertEqual(payload["metrics"]["evidence_hit_rate_top5"], 1.0)
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("Business Administration degree", dumped)

    def test_standard_retrieval_qa_reports_context_visible_line_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            locomo_path = root / "locomo10.json"
            locomo_path.write_text(
                json.dumps(
                    [
                        {
                            "sample_id": "conv-context",
                            "qa": [
                                {
                                    "question": "How long was the current support system active?",
                                    "answer": "4 years",
                                    "evidence": ["D1:2"],
                                    "category": 2,
                                }
                            ],
                            "conversation": {
                                "speaker_a": "Caroline",
                                "speaker_b": "Melanie",
                                "session_1_date_time": "7:55 pm on 9 June, 2023",
                                "session_1": [
                                    {
                                        "speaker": "Melanie",
                                        "dia_id": "D1:1",
                                        "text": "How long have you had such a great current support system?",
                                    },
                                    {
                                        "speaker": "Caroline",
                                        "dia_id": "D1:2",
                                        "text": "Four years.",
                                    },
                                ],
                            },
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = benchmark.run_standard_retrieval_qa_benchmark(
                dataset="locomo",
                corpus_path=locomo_path,
                max_questions=1,
                min_questions=1,
                top_k=5,
                context_radius=1,
            )

        metrics = payload["metrics"]
        self.assertEqual(metrics["evidence_hit_rate_top5"], 0.0)
        self.assertEqual(metrics["evidence_context_hit_rate_top5"], 1.0)
        self.assertEqual(metrics["evidence_context_radius"], 1)
        self.assertEqual(metrics["evidence_context_improved_count"], 1)
        self.assertEqual(metrics["evidence_context_rescued_top5"], 1)
        self.assertEqual(metrics["evidence_context_mrr_delta"], 1.0)

    def test_standard_retrieval_qa_can_use_injected_line_reranker(self) -> None:
        calls: list[dict] = []

        def fake_line_reranker(question: str, candidates: list[dict], **_: object) -> dict:
            calls.append({"question": question, "candidates": candidates})
            self.assertTrue(candidates)
            self.assertNotIn("has_answer", candidates[0])
            return {
                "available": True,
                "ranked_lines": [1],
                "confidence": 0.91,
                "usage": {"total_tokens": 7},
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            longmem_path = root / "longmemeval_oracle.json"
            longmem_path.write_text(
                json.dumps(
                    [
                        {
                            "question_id": "q-rerank",
                            "question": "Where did I buy my new tennis racket from?",
                            "question_type": "single-session-user-fact",
                            "answer_session_ids": ["answer-session"],
                            "haystack_session_ids": ["answer-session"],
                            "haystack_dates": ["2026/05/01"],
                            "haystack_sessions": [
                                [
                                    {
                                        "role": "user",
                                        "content": "I bought my racket from Court Shop.",
                                        "has_answer": True,
                                    },
                                    {
                                        "role": "assistant",
                                        "content": "Court Shop sounds like a good place for tennis gear.",
                                    },
                                ],
                            ],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = benchmark.run_standard_retrieval_qa_benchmark(
                dataset="longmemeval-v1-oracle",
                corpus_path=longmem_path,
                max_questions=1,
                min_questions=1,
                top_k=5,
                context_radius=1,
                line_reranker_mode="custom",
                line_reranker_fn=fake_line_reranker,
            )

        metrics = payload["metrics"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(metrics["reranked_evidence_hit_rate_top5"], 1.0)
        self.assertEqual(metrics["reranked_evidence_mrr"], 1.0)
        self.assertEqual(metrics["line_reranker_available_count"], 1)
        self.assertEqual(metrics["line_reranker_candidate_evidence_coverage_rate"], 1.0)
        self.assertEqual(metrics["line_reranker_usage"]["total_tokens"], 7)
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("Court Shop", dumped)

    def test_line_reranker_fusion_preserves_first_stage_exact_hits(self) -> None:
        def misleading_line_reranker(
            question: str,
            candidates: list[dict],
            **_: object,
        ) -> dict:
            self.assertIn("blue orchard", question)
            return {
                "available": True,
                "ranked_lines": [2],
                "confidence": 0.4,
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            longmem_path = root / "longmemeval_oracle.json"
            longmem_path.write_text(
                json.dumps(
                    [
                        {
                            "question_id": "q-fusion",
                            "question": "What was the blue orchard quantum code?",
                            "question_type": "single-session-user-fact",
                            "answer_session_ids": ["answer-session"],
                            "haystack_session_ids": ["answer-session"],
                            "haystack_dates": ["2026/05/01"],
                            "haystack_sessions": [
                                [
                                    {
                                        "role": "user",
                                        "content": "The blue orchard quantum code was 917.",
                                        "has_answer": True,
                                    },
                                    {
                                        "role": "assistant",
                                        "content": "I will remember that code context.",
                                    },
                                ],
                            ],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = benchmark.run_standard_retrieval_qa_benchmark(
                dataset="longmemeval-v1-oracle",
                corpus_path=longmem_path,
                max_questions=1,
                min_questions=1,
                top_k=1,
                context_radius=1,
                line_reranker_mode="custom",
                line_reranker_fn=misleading_line_reranker,
            )

        metrics = payload["metrics"]
        self.assertEqual(metrics["evidence_hit_rate_top1"], 1.0)
        self.assertEqual(metrics["semantic_only_evidence_hit_rate_top1"], 0.0)
        self.assertEqual(metrics["reranked_evidence_hit_rate_top1"], 1.0)

    def test_lexical_line_reranker_promotes_context_visible_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sqlite_path = Path(tmp) / "source_index.sqlite"
            messages = [
                benchmark.standard_message_for_sqlite(
                    source_id="source",
                    line=1,
                    role="assistant",
                    text="The blue badge location question was discussed in the notes.",
                ),
                benchmark.standard_message_for_sqlite(
                    source_id="source",
                    line=2,
                    role="user",
                    text="Look in drawer nine for the blue badge.",
                ),
            ]
            benchmark.make_sqlite(sqlite_path, messages, anchors=[], turns=[])
            case = {
                "case_id": "lexical-context-rescue",
                "dataset": "synthetic",
                "case_type": "context_visible_exact_line_miss",
                "source_id_sha1": "source",
                "question_id_sha1": "question",
                "query": "Where should I look for the blue badge?",
                "query_sha1": "query",
                "query_terms": ["blue", "badge", "location"],
                "sqlite_path": sqlite_path,
                "expected": {
                    "lines": [2],
                    "sessions": ["D1"],
                    "line_to_session": {"1": "D1", "2": "D1"},
                    "has_line_evidence": True,
                },
            }

            row = benchmark.evaluate_standard_retrieval_case(
                case,
                top_k=1,
                candidate_limit=8,
                context_radius=1,
                include_private_text=False,
                line_reranker_mode="lexical",
                line_reranker_top_sessions=0,
                line_reranker_max_candidates=8,
            )

        self.assertFalse(row["evidence_hit_top1"])
        self.assertTrue(row["evidence_context_hit_top1"])
        self.assertTrue(row["semantic_only_evidence_hit_top1"])
        self.assertTrue(row["semantic_bridge_lift_top1"])
        self.assertTrue(row["reranked_evidence_hit_top1"])
        self.assertEqual(row["line_reranker_mode"], "lexical")
        self.assertEqual(row["line_reranker_error_count"], 0)

    def test_structural_line_reranker_promotes_adjacent_answer_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sqlite_path = Path(tmp) / "source_index.sqlite"
            messages = [
                benchmark.standard_message_for_sqlite(
                    source_id="source", line=1, role="user", text="The blue badge note continues in the next line."
                ),
                benchmark.standard_message_for_sqlite(
                    source_id="source", line=2, role="assistant", text="The object is in drawer nine."
                ),
            ]
            benchmark.make_sqlite(sqlite_path, messages, anchors=[], turns=[])
            case = {
                "case_id": "structural-context-rescue",
                "dataset": "synthetic",
                "case_type": "context_visible_exact_line_miss",
                "source_id_sha1": "source",
                "question_id_sha1": "question",
                "query": "Where did the blue badge note say to look?",
                "query_sha1": "query",
                "query_terms": ["blue", "badge", "note"],
                "sqlite_path": sqlite_path,
                "expected": {
                    "lines": [2],
                    "sessions": ["D1"],
                    "line_to_session": {"1": "D1", "2": "D1"},
                    "has_line_evidence": True,
                },
            }

            row = benchmark.evaluate_standard_retrieval_case(
                case,
                top_k=1,
                candidate_limit=8,
                context_radius=1,
                include_private_text=False,
                line_reranker_mode="structural",
                line_reranker_top_sessions=0,
                line_reranker_max_candidates=8,
            )

        self.assertFalse(row["evidence_hit_top1"])
        self.assertTrue(row["evidence_context_hit_top1"])
        self.assertTrue(row["semantic_only_evidence_hit_top1"])
        self.assertTrue(row["semantic_bridge_lift_top1"])
        self.assertTrue(row["reranked_evidence_hit_top1"])
        self.assertEqual(row["line_reranker_mode"], "structural")
        dumped = json.dumps(row, ensure_ascii=False)
        self.assertNotIn("drawer nine", dumped)
        self.assertNotIn("blue badge note", dumped)

    def test_standard_content_query_terms_remove_generic_question_words(self) -> None:
        terms = benchmark.standard_content_query_terms(
            "When did Caroline go to the LGBTQ support group?"
        )

        self.assertIn("LGBTQ", terms)
        self.assertIn("support", terms)
        self.assertIn("group", terms)
        self.assertNotIn("When", terms)
        self.assertNotIn("did", terms)
        self.assertNotIn("the", terms)

    def test_line_reranker_candidates_can_use_content_query_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sqlite_path = Path(tmp) / "source_index.sqlite"
            messages = [
                benchmark.standard_message_for_sqlite(
                    source_id="source",
                    line=1,
                    role="speaker",
                    text="Generic setup line.",
                ),
                benchmark.standard_message_for_sqlite(
                    source_id="source",
                    line=2,
                    role="speaker",
                    text="Another setup line.",
                ),
                benchmark.standard_message_for_sqlite(
                    source_id="source",
                    line=3,
                    role="speaker",
                    text="Bridge line.",
                ),
                benchmark.standard_message_for_sqlite(
                    source_id="source",
                    line=4,
                    role="speaker",
                    text="The rare content evidence line.",
                ),
            ]
            benchmark.make_sqlite(sqlite_path, messages, anchors=[], turns=[])

            candidates = benchmark.build_standard_line_reranker_candidates(
                sqlite_path,
                [{"line": 1, "rank_score": -1.0}],
                extra_hit_lists=[("content", [{"line": 4, "rank_score": -2.0}])],
                line_to_session={str(line): "D1" for line in range(1, 5)},
                top_k=1,
                context_radius=0,
                top_sessions=0,
                max_candidates=4,
            )

        self.assertIn(4, [candidate["line"] for candidate in candidates])

    def test_standard_reranker_reports_semantic_bridge_lift_for_source_joined_candidates(
        self,
    ) -> None:
        def source_joined_reranker(
            question: str,
            candidates: list[dict],
            **_: object,
        ) -> dict:
            self.assertIn("login safety mechanism", question)
            self.assertEqual({1, 2}, {int(candidate["line"]) for candidate in candidates})
            return {
                "available": True,
                "ranked_lines": [2, 1],
                "confidence": 0.82,
            }

        with tempfile.TemporaryDirectory() as tmp:
            sqlite_path = Path(tmp) / "source_index.sqlite"
            messages = [
                benchmark.standard_message_for_sqlite(
                    source_id="source",
                    line=1,
                    role="user",
                    text="We kept calling this the login safety mechanism during planning.",
                ),
                benchmark.standard_message_for_sqlite(
                    source_id="source",
                    line=2,
                    role="assistant",
                    text="Current source truth: the adopted authentication flow uses rotating session tokens.",
                ),
            ]
            benchmark.make_sqlite(sqlite_path, messages, anchors=[], turns=[])
            case = {
                "case_id": "bridge-lift",
                "dataset": "synthetic",
                "case_type": "cross_vocabulary_vague_cue",
                "source_id_sha1": "source",
                "question_id_sha1": "question",
                "query": "Which login safety mechanism did we adopt?",
                "query_sha1": "query",
                "query_terms": ["login", "safety", "mechanism"],
                "sqlite_path": sqlite_path,
                "expected": {
                    "lines": [2],
                    "sessions": ["D1"],
                    "line_to_session": {"1": "D1", "2": "D1"},
                    "has_line_evidence": True,
                },
            }

            row = benchmark.evaluate_standard_retrieval_case(
                case,
                top_k=1,
                candidate_limit=8,
                context_radius=1,
                include_private_text=False,
                line_reranker_mode="custom",
                line_reranker_fn=source_joined_reranker,
                line_reranker_top_sessions=0,
                line_reranker_max_candidates=8,
            )

        self.assertFalse(row["evidence_hit_top1"])
        self.assertTrue(row["semantic_only_evidence_hit_top1"])
        self.assertTrue(row["semantic_bridge_lift_top1"])
        self.assertTrue(row["source_joined_candidate_contains_evidence"])
        metrics = benchmark.summarize_standard_retrieval_results(
            [row],
            top_k=1,
            context_radius=1,
        )
        self.assertEqual(metrics["semantic_bridge_lift_top1"], 1)
        self.assertEqual(metrics["semantic_bridge_lift_rate_top1"], 1.0)
        self.assertEqual(metrics["source_joined_candidate_evidence_coverage"], 1)
        self.assertEqual(metrics["source_joined_candidate_evidence_coverage_rate"], 1.0)

    def test_standard_reranker_reports_wrong_stance_ranked_above_correct_source(
        self,
    ) -> None:
        def stale_first_reranker(
            question: str,
            candidates: list[dict],
            **_: object,
        ) -> dict:
            self.assertIn("login safety mechanism", question)
            self.assertEqual({1, 2, 3}, {int(candidate["line"]) for candidate in candidates})
            return {
                "available": True,
                "ranked_lines": [3, 2, 1],
                "confidence": 0.77,
            }

        with tempfile.TemporaryDirectory() as tmp:
            sqlite_path = Path(tmp) / "source_index.sqlite"
            messages = [
                benchmark.standard_message_for_sqlite(
                    source_id="source",
                    line=1,
                    role="user",
                    text="The login safety mechanism came up again.",
                ),
                benchmark.standard_message_for_sqlite(
                    source_id="source",
                    line=2,
                    role="assistant",
                    text="Current source truth: we adopted the authentication flow with rotating tokens.",
                ),
                benchmark.standard_message_for_sqlite(
                    source_id="source",
                    line=3,
                    role="assistant",
                    text="Superseded source: we rejected the authentication flow as too heavy.",
                ),
            ]
            benchmark.make_sqlite(sqlite_path, messages, anchors=[], turns=[])
            case = {
                "case_id": "wrong-stance",
                "dataset": "synthetic",
                "case_type": "cross_vocabulary_wrong_stance_control",
                "source_id_sha1": "source",
                "question_id_sha1": "question",
                "query": "Which login safety mechanism did we adopt?",
                "query_sha1": "query",
                "query_terms": ["login", "safety", "mechanism"],
                "sqlite_path": sqlite_path,
                "expected": {
                    "lines": [2],
                    "sessions": ["D1"],
                    "wrong_stance_lines": [3],
                    "line_to_session": {"1": "D1", "2": "D1", "3": "D1"},
                    "has_line_evidence": True,
                },
            }

            row = benchmark.evaluate_standard_retrieval_case(
                case,
                top_k=2,
                candidate_limit=8,
                context_radius=2,
                include_private_text=False,
                line_reranker_mode="custom",
                line_reranker_fn=stale_first_reranker,
                line_reranker_top_sessions=0,
                line_reranker_max_candidates=8,
            )

        self.assertEqual(row["semantic_only_evidence_rank"], 2)
        self.assertEqual(row["wrong_stance_semantic_rank"], 1)
        self.assertTrue(row["wrong_stance_ranked_above_evidence"])
        self.assertTrue(row["wrong_stance_rerank_top2"])
        metrics = benchmark.summarize_standard_retrieval_results(
            [row],
            top_k=2,
            context_radius=2,
        )
        self.assertEqual(metrics["wrong_stance_control_case_count"], 1)
        self.assertEqual(metrics["wrong_stance_rerank_top2"], 1)
        self.assertEqual(metrics["wrong_stance_rerank_rate_top2"], 1.0)


if __name__ == "__main__":
    unittest.main()
