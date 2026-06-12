from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
for _path in (BENCHMARKS, REPO_ROOT / "tools" / "aippocampus" / "smoke"):
    sys.path.insert(0, str(_path))

import benchmark_longmemeval as benchmark  # noqa: E402
import provider_execution_budget  # noqa: E402
from source_evidence import standard_public  # noqa: E402


def write_oracle_fixture(path: Path, *, question_count: int = 1) -> None:
    fixture = []
    for index in range(question_count):
        fixture.append(
            {
                "question_id": f"q-mini-{index}",
                "question_type": "single-session-user",
                "question": f"Where did the retrieval marker {index} appear?",
                "answer": f"secret fixture answer marker {index}",
                "question_date": "2023/05/30 (Tue) 23:40",
                "haystack_dates": [
                    "2023/05/20 (Sat) 02:21",
                    "2023/05/21 (Sun) 03:24",
                ],
                "haystack_session_ids": [f"distractor-{index}", f"answer-session-{index}"],
                "answer_session_ids": [f"answer-session-{index}"],
                "haystack_sessions": [
                    [
                        {
                            "role": "user",
                            "content": f"Let's talk about an unrelated trail {index}.",
                        }
                    ],
                    [
                        {
                            "role": "user",
                            "content": f"The retrieval marker {index} appears in the answer session.",
                            "has_answer": True,
                        }
                    ],
                ],
            }
        )
    path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")


def write_context_visible_miss_fixture(path: Path) -> None:
    fixture = [
        {
            "question_id": "q-context-visible",
            "question_type": "single-session-user",
            "question": "Where did the blue badge note say to look?",
            "answer": "drawer nine",
            "question_date": "2023/05/30 (Tue) 23:40",
            "haystack_dates": ["2023/05/20 (Sat) 02:21"],
            "haystack_session_ids": ["answer-session"],
            "answer_session_ids": ["answer-session"],
            "haystack_sessions": [
                [
                    {
                        "role": "user",
                        "content": "The blue badge note continues in the next line.",
                    },
                    {
                        "role": "assistant",
                        "content": "The object is in drawer nine.",
                        "has_answer": True,
                    },
                ]
            ],
        }
    ]
    path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")


@contextmanager
def patched_oracle_split(path: Path) -> Iterator[None]:
    split = benchmark.LONGMEMEVAL_SPLITS["longmemeval-v1-oracle"]
    patched = benchmark.LongMemEvalSplit(
        dataset=split.dataset,
        filename=split.filename,
        expected_sha256=benchmark.file_sha256(path),
        expected_bytes=path.stat().st_size,
        benchmark_label=split.benchmark_label,
        default_role=split.default_role,
    )
    original = benchmark.LONGMEMEVAL_SPLITS["longmemeval-v1-oracle"]
    benchmark.LONGMEMEVAL_SPLITS["longmemeval-v1-oracle"] = patched
    try:
        yield
    finally:
        benchmark.LONGMEMEVAL_SPLITS["longmemeval-v1-oracle"] = original


class LongMemEvalBenchmarkTests(unittest.TestCase):
    def test_provider_execution_budget_schema_requires_live_run_controls(self) -> None:
        deterministic = provider_execution_budget.build_provider_execution_budget(
            benchmark_id="deterministic-smoke",
            live_mode=False,
            max_units=0,
            per_case_timeout_seconds=None,
        )
        self.assertEqual(
            provider_execution_budget.validate_provider_execution_budget(deterministic),
            [],
        )

        live_missing = provider_execution_budget.build_provider_execution_budget(
            benchmark_id="live-smoke",
            live_mode=True,
            max_units=0,
            per_case_timeout_seconds=None,
        )
        self.assertEqual(
            provider_execution_budget.validate_provider_execution_budget(live_missing),
            [
                "missing_case_cap",
                "missing_per_case_timeout",
                "missing_provider_call_cap",
                "missing_token_or_cost_budget",
                "missing_checkpoint_path",
                "missing_partial_output_path",
            ],
        )

    def test_missing_dataset_returns_skipped_payload_with_claim_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing-longmemeval.json"

            payload = benchmark.run_longmemeval_benchmark(
                split_name="longmemeval-v1-oracle",
                data_file=path,
                max_questions=2,
                min_questions=1,
            )

        self.assertEqual(payload["kind"], "aippocampus_longmemeval_benchmark")
        self.assertEqual(payload["status"], "skipped_missing_dataset")
        self.assertTrue(payload["ok"])
        self.assertIn("longmemeval_retrieval_score", payload["cannot_claim"])
        self.assertEqual(payload["benchmark"]["verification"]["expected_bytes"], 15388478)
        self.assertEqual(
            payload["benchmark"]["verification"]["expected_sha256"],
            "821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c",
        )
        self.assertFalse(payload["privacy_boundary"]["raw_text_emitted"])

    def test_oracle_fixture_reports_sanitized_retrieval_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "longmemeval_oracle.json"
            write_oracle_fixture(path)
            with patched_oracle_split(path):
                payload = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=2,
                    min_questions=1,
                    top_k=5,
                )

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["status"], "retrieval_sufficient")
        self.assertEqual(payload["metrics"]["question_count"], 1)
        self.assertEqual(payload["metrics"]["session_hit_rate_top5"], 1.0)
        self.assertEqual(payload["metrics"]["evidence_hit_rate_top5"], 1.0)
        self.assertEqual(payload["metrics"]["evidence_line_recall_by_k"]["1"]["hit"], 1)
        self.assertEqual(payload["metrics"]["evidence_rank_bucket_counts"]["rank_1"], 1)
        self.assertEqual(
            payload["metrics"]["evidence_line_taxonomy_counts"]["exact_line_found_top_k"],
            1,
        )
        self.assertEqual(payload["metrics"]["evidence_miss_taxonomy_counts"], {})
        self.assertEqual(payload["cases"][0]["evidence_rank_bucket"], "rank_1")
        self.assertEqual(payload["cases"][0]["evidence_miss_category"], "exact_line_found_top_k")
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("secret fixture answer marker", dumped)
        self.assertIn("longmemeval_qa_score", payload["cannot_claim"])

    def test_context_visible_exact_line_miss_is_sanitized_and_categorized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "longmemeval_oracle.json"
            write_context_visible_miss_fixture(path)
            with patched_oracle_split(path):
                payload = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=1,
                    min_questions=1,
                    top_k=1,
                )

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["metrics"]["session_hit_rate_top1"], 1.0)
        self.assertEqual(payload["metrics"]["evidence_hit_rate_top1"], 0.0)
        self.assertEqual(payload["metrics"]["evidence_context_hit_rate_top1"], 1.0)
        self.assertEqual(
            payload["metrics"]["evidence_miss_taxonomy_counts"][
                "context_visible_exact_line_miss"
            ],
            1,
        )
        self.assertEqual(
            payload["metrics"]["evidence_context_rescue_distance_counts_top1"][
                "distance_1"
            ],
            1,
        )
        self.assertEqual(payload["cases"][0]["evidence_rank_bucket"], "rank_2_3")
        self.assertTrue(payload["cases"][0]["gold_line_near_miss_top1_to_20"])
        self.assertEqual(
            payload["cases"][0]["evidence_miss_category"],
            "context_visible_exact_line_miss",
        )
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("drawer nine", dumped)
        self.assertNotIn("blue badge note continues", dumped)

    def test_semantic_line_rerank_requires_live_budget_before_provider_call(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "longmemeval_oracle.json"
            write_oracle_fixture(path)
            with patched_oracle_split(path), patch.dict(
                "os.environ",
                {"DEEPSEEK_API_KEY": "test-key"},
            ), patch(
                "source_evidence.standard_public.call_chat_json",
                side_effect=AssertionError("provider should not be called"),
            ):
                payload = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=1,
                    min_questions=1,
                    top_k=5,
                    line_reranker_mode="semantic",
                    line_reranker_workers=1,
                )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "skipped_provider_budget_not_declared")
        budget = payload["provider_execution_budget"]
        self.assertFalse(budget["ok_to_start"])
        self.assertEqual(budget["stop_reason"], "provider_budget_preflight_failed")
        self.assertEqual(
            budget["validation_errors"],
            [
                "missing_provider_call_cap",
                "missing_token_or_cost_budget",
                "missing_checkpoint_path",
                "missing_partial_output_path",
            ],
        )
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("secret fixture answer marker", dumped)
        self.assertNotIn(str(path), dumped)

    def test_semantic_line_rerank_reports_llm_arm_metadata_without_raw_text(self) -> None:
        captured_messages: list[list[dict[str, str]]] = []

        def fake_call_chat_json(
            messages: list[dict[str, str]],
            api_key: str,
            model: str,
            base_url: str,
            max_tokens: int | None,
            timeout: float,
            temperature: float,
            **_: object,
        ) -> dict[str, Any]:
            captured_messages.append(messages)
            self.assertEqual(api_key, "test-key")
            self.assertTrue(model)
            self.assertTrue(base_url)
            self.assertIsNone(max_tokens)
            self.assertEqual(timeout, 12)
            self.assertEqual(temperature, 0.0)
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"ranked_lines": [2], "confidence": 0.84}
                            )
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "total_tokens": 12,
                    "prompt_cache_hit_tokens": 4,
                    "prompt_cache_miss_tokens": 6,
                },
            }

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "longmemeval_oracle.json"
            partial_path = Path(tmp) / "semantic.partial.json"
            checkpoint_path = Path(tmp) / "semantic-budget.json"
            write_oracle_fixture(path)
            with patched_oracle_split(path), patch.dict(
                "os.environ",
                {"DEEPSEEK_API_KEY": "test-key"},
            ), patch("source_evidence.standard_public.call_chat_json", fake_call_chat_json):
                payload = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=1,
                    min_questions=1,
                    top_k=5,
                    line_reranker_mode="semantic",
                    line_reranker_workers=1,
                    partial_output=partial_path,
                    provider_budget_checkpoint=checkpoint_path,
                    max_provider_calls=1,
                    max_provider_total_tokens=1000,
                    provider_cost_unknown=True,
                )
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(len(captured_messages), 1)
        arm = payload["evaluation"]["llm_rerank_arm"]
        self.assertEqual(arm["arm"], "llm_window_to_line_rerank")
        self.assertEqual(arm["prompt_version"], "llm-window-to-line-rerank-v1")
        self.assertFalse(arm["output_boundary"]["question_answering_allowed"])
        self.assertIn("gold_answer", arm["input_boundary"]["withheld_from_model"])
        provenance = payload["evaluation"]["capability_provenance"]
        self.assertEqual(
            provenance["mode_classification"],
            "query_time_llm_rerank_upper_bound",
        )
        self.assertFalse(provenance["can_claim_source_side_warming"])
        self.assertIn("temporary_provider_prompt", provenance["benchmark_local_scaffolding"])
        adapter_config = payload["standard_adapter"]["config"]
        self.assertTrue(adapter_config["line_reranker_external_model"])
        self.assertEqual(
            adapter_config["line_reranker_metadata"]["prompt_version"],
            "llm-window-to-line-rerank-v1",
        )
        metrics = payload["metrics"]
        self.assertEqual(metrics["line_reranker_available_count"], 1)
        self.assertEqual(metrics["line_reranker_usage"]["total_tokens"], 12)
        self.assertEqual(metrics["line_reranker_cache"]["hit_tokens"], 4)
        self.assertEqual(metrics["line_reranker_cache"]["miss_tokens"], 6)
        self.assertEqual(metrics["line_reranker_latency_ms"]["count"], 1)
        self.assertEqual(
            metrics["line_reranker_metadata"]["prompt_version"],
            "llm-window-to-line-rerank-v1",
        )
        budget = payload["provider_execution_budget"]
        self.assertTrue(budget["ok_to_start"])
        self.assertEqual(budget["completed_units"], 1)
        self.assertEqual(budget["token_usage"]["total_tokens"], 12)
        self.assertEqual(budget["cache_usage"]["hit_tokens"], 4)
        self.assertEqual(budget["cache_usage"]["miss_tokens"], 6)
        self.assertEqual(budget["cost_status"], "unknown_declared")
        self.assertEqual(
            budget["cost_unavailable_reason"],
            "provider_cost_not_reported_by_chat_completions_response",
        )
        self.assertEqual(
            checkpoint["provider_execution_budget"]["schema_version"],
            provider_execution_budget.SCHEMA_VERSION,
        )
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("secret fixture answer marker", dumped)
        self.assertNotIn("retrieval marker", dumped)
        self.assertNotIn(str(path), dumped)

    def test_source_semantic_cache_uses_aippocampus_worker_surface_without_provider(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "longmemeval_oracle.json"
            write_oracle_fixture(path)
            with patched_oracle_split(path), patch(
                "source_evidence.standard_public.call_chat_json",
                side_effect=AssertionError("source-side cache must not call provider"),
            ):
                payload = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=1,
                    min_questions=1,
                    top_k=5,
                    line_reranker_mode="source_semantic_cache",
                    line_reranker_workers=1,
                )

        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["evaluation"]["line_reranker_mode"], "source_semantic_cache")
        arm = payload["evaluation"]["source_semantic_cache_arm"]
        self.assertEqual(arm["builder"], "aippocampus_worker_surface")
        self.assertEqual(arm["provider"], "local_aippocampus_runtime")
        self.assertFalse(arm["output_boundary"]["question_answering_allowed"])
        self.assertTrue(arm["output_boundary"]["source_reopen_required_for_claims"])
        provenance = payload["evaluation"]["capability_provenance"]
        self.assertEqual(provenance["mode_classification"], "source_worker_surface_proxy")
        self.assertEqual(provenance["remaining_gap_issue"], "#1323")
        self.assertFalse(provenance["can_claim_source_side_warming"])
        adapter_config = payload["standard_adapter"]["config"]
        self.assertFalse(adapter_config["line_reranker_external_model"])
        self.assertEqual(
            adapter_config["line_reranker_metadata"]["cache_policy_version"],
            standard_public.SOURCE_SEMANTIC_CACHE_POLICY_VERSION,
        )
        metrics = payload["metrics"]
        self.assertEqual(metrics["line_reranker_usage"]["provider_call_count"], 0)
        self.assertEqual(metrics["source_semantic_cache_hot_query_provider_call_count"], 0)
        self.assertEqual(metrics["source_semantic_cache"]["provider_call_count"], 0)
        self.assertFalse(metrics["source_semantic_cache"]["raw_source_text_emitted"])
        self.assertFalse(metrics["source_semantic_cache"]["cache_values_emitted"])
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("secret fixture answer marker", dumped)
        self.assertNotIn("retrieval marker", dumped)
        self.assertNotIn(str(path), dumped)

    def test_source_semantic_cache_reuses_source_artifact_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "longmemeval_oracle.json"
            cache_dir = root / "standard-cache"
            write_oracle_fixture(path)
            with patched_oracle_split(path):
                first = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=1,
                    min_questions=1,
                    top_k=5,
                    line_reranker_mode="source_semantic_cache",
                    line_reranker_workers=1,
                    standard_cache_dir=cache_dir,
                )
                second = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=1,
                    min_questions=1,
                    top_k=5,
                    line_reranker_mode="source_semantic_cache",
                    line_reranker_workers=1,
                    standard_cache_dir=cache_dir,
                )

        self.assertTrue(first["ok"], first)
        self.assertTrue(second["ok"], second)
        first_artifacts = first["metrics"]["source_semantic_cache"]["source_artifact_cache"]
        second_artifacts = second["metrics"]["source_semantic_cache"]["source_artifact_cache"]
        self.assertTrue(first_artifacts["enabled"])
        self.assertEqual(first_artifacts["miss_count"], 1)
        self.assertEqual(first_artifacts["rebuild_count"], 1)
        self.assertEqual(first_artifacts["hit_count"], 0)
        self.assertEqual(second_artifacts["hit_count"], 1)
        self.assertEqual(second_artifacts["rebuild_count"], 0)
        dumped = json.dumps(second, ensure_ascii=False)
        self.assertNotIn(str(path), dumped)
        self.assertNotIn(str(cache_dir), dumped)
        self.assertNotIn("secret fixture answer marker", dumped)

    def test_source_semantic_cache_route_keys_are_cache_root_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            messages = [
                standard_public.standard_message_for_sqlite(
                    source_id="stable-question",
                    line=1,
                    role="user",
                    text="The stable marker belongs to this source row.",
                )
            ]
            manifest = standard_public.source_index_manifest(
                dataset="longmemeval-v1-small",
                source_id="stable-question",
                question_id="stable-question",
                messages=messages,
            )
            caches = []
            for name in ("cache-a", "cache-b"):
                sqlite_path = root / name / "source_index.sqlite"
                metrics = standard_public.new_standard_case_cache_metrics(
                    enabled=True,
                    cache_key=name,
                    rebuild_requested=False,
                )
                standard_public.prepare_standard_sqlite_index(
                    sqlite_path,
                    messages=messages,
                    manifest=manifest,
                    cache_metrics=metrics,
                    rebuild_cache=False,
                )
                caches.append(
                    standard_public.build_source_semantic_cache(
                        sqlite_path,
                        line_to_session={"1": "session-a"},
                    )
                )

        first_ref = caches[0]["working_memory_rows"][0]["source_refs"][0]
        second_ref = caches[1]["working_memory_rows"][0]["source_refs"][0]
        first_row = caches[0]["working_memory_rows"][0]
        second_row = caches[1]["working_memory_rows"][0]
        self.assertEqual(first_ref["message_id"], second_ref["message_id"])
        self.assertEqual(first_ref["thread_key"], second_ref["thread_key"])
        self.assertEqual(first_row["candidate_key"], second_row["candidate_key"])
        self.assertTrue(first_ref["message_id"].startswith("standard_public:"))
        self.assertEqual(
            caches[0]["manifest"]["source_identity"],
            caches[1]["manifest"]["source_identity"],
        )
        dumped = json.dumps(
            [
                {
                    "source_identity": cache["manifest"]["source_identity"],
                    "source_refs": cache["working_memory_rows"][0]["source_refs"],
                    "candidate_key": cache["working_memory_rows"][0]["candidate_key"],
                }
                for cache in caches
            ],
            ensure_ascii=False,
        )
        self.assertNotIn(str(root), dumped)

    def test_source_semantic_cache_consumes_canonical_semantic_scope_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "case" / "source_index.sqlite"
            messages = [
                standard_public.standard_message_for_sqlite(
                    source_id="semantic-sidecar-question",
                    line=1,
                    role="user",
                    text="The source row describes a concrete implementation path.",
                )
            ]
            manifest = standard_public.source_index_manifest(
                dataset="longmemeval-v1-small",
                source_id="semantic-sidecar-question",
                question_id="semantic-sidecar-question",
                messages=messages,
            )
            metrics = standard_public.new_standard_case_cache_metrics(
                enabled=True,
                cache_key="semantic-sidecar",
                rebuild_requested=False,
            )
            standard_public.prepare_standard_sqlite_index(
                sqlite_path,
                messages=messages,
                manifest=manifest,
                cache_metrics=metrics,
                rebuild_cache=False,
            )
            clean_messages_path = sqlite_path.with_name("messages.jsonl")
            self.assertTrue(clean_messages_path.exists())
            clean_message = json.loads(clean_messages_path.read_text(encoding="utf-8").splitlines()[0])
            message_id = clean_message["message_id"]
            self.assertTrue(message_id.startswith("standard_public:"))
            key_without_sidecar = standard_public.source_semantic_artifact_cache_key(
                sqlite_path,
                line_to_session={"1": "session-a"},
            )
            sidecar_path = sqlite_path.with_name("semantic-scope-labels.jsonl")
            sidecar_path.write_text(
                json.dumps(
                    {
                        "message_id": message_id,
                        "scope_labels": ["technical_work"],
                        "confidence": 0.82,
                        "label_evidence": [
                            {
                                "label": "technical_work",
                                "reason": "The source row describes implementation work.",
                                "confidence": 0.82,
                            }
                        ],
                        "source_refs": [
                            {
                                "ref": message_id,
                                "thread_key": "standard-public-fixture",
                                "message_id": message_id,
                                "turn_id": message_id,
                                "source_line": 1,
                                "role": "user",
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            key_with_sidecar = standard_public.source_semantic_artifact_cache_key(
                sqlite_path,
                line_to_session={"1": "session-a"},
            )
            cache = standard_public.build_source_semantic_cache(
                sqlite_path,
                line_to_session={"1": "session-a"},
            )

        self.assertNotEqual(key_without_sidecar, key_with_sidecar)
        profile = cache["profiles"][1]
        row = cache["working_memory_rows"][0]
        self.assertIn("technical_work", profile["labels"])
        self.assertIn("technical_work", profile["semantic_scope_labels"])
        self.assertIn("technical_work", row["semantic_scope_labels"])
        self.assertTrue(cache["manifest"]["semantic_scope_sidecar_loaded"])
        self.assertEqual(cache["manifest"]["semantic_scope_sidecar_row_count"], 1)
        self.assertEqual(cache["manifest"]["semantic_scope_label_row_count"], 1)

    def test_standard_case_cache_reuses_prepared_sqlite_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "longmemeval_oracle.json"
            cache_dir = root / "standard-cache"
            write_oracle_fixture(path, question_count=2)
            with patched_oracle_split(path):
                first = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=2,
                    min_questions=2,
                    top_k=5,
                    standard_cache_dir=cache_dir,
                )
                second = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=2,
                    min_questions=2,
                    top_k=5,
                    standard_cache_dir=cache_dir,
                )

        self.assertTrue(first["ok"], first)
        self.assertTrue(second["ok"], second)
        first_cache = first["standard_adapter"]["corpus"]["case_cache"]
        second_cache = second["standard_adapter"]["corpus"]["case_cache"]
        self.assertTrue(first_cache["enabled"])
        self.assertEqual(first_cache["source_index_hit_count"], 0)
        self.assertEqual(first_cache["source_index_rebuild_count"], 2)
        self.assertEqual(first_cache["source_index_hit_rate"], 0.0)
        self.assertEqual(second_cache["source_index_hit_count"], 2)
        self.assertEqual(second_cache["source_index_rebuild_count"], 0)
        self.assertEqual(second_cache["source_index_hit_rate"], 1.0)
        dumped = json.dumps(second, ensure_ascii=False)
        self.assertNotIn(str(path), dumped)
        self.assertNotIn(str(cache_dir), dumped)
        self.assertNotIn("secret fixture answer marker", dumped)

    def test_standard_case_cache_manifest_mismatch_rebuilds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "longmemeval_oracle.json"
            cache_dir = root / "standard-cache"
            write_oracle_fixture(path)
            with patched_oracle_split(path):
                first = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=1,
                    min_questions=1,
                    top_k=5,
                    standard_cache_dir=cache_dir,
                )
                manifest_path = next(cache_dir.rglob("source_index_manifest.json"))
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["policy_version"] = "stale-test-policy"
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                second = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=1,
                    min_questions=1,
                    top_k=5,
                    standard_cache_dir=cache_dir,
                )

        self.assertTrue(first["ok"], first)
        self.assertTrue(second["ok"], second)
        cache = second["standard_adapter"]["corpus"]["case_cache"]
        self.assertEqual(cache["source_index_manifest_mismatch_count"], 1)
        self.assertEqual(cache["source_index_rebuild_count"], 1)
        self.assertEqual(cache["source_index_hit_count"], 0)

    def test_standard_case_cache_forced_rebuild_skips_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "longmemeval_oracle.json"
            cache_dir = root / "standard-cache"
            write_oracle_fixture(path)
            with patched_oracle_split(path):
                benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=1,
                    min_questions=1,
                    top_k=5,
                    standard_cache_dir=cache_dir,
                )
                payload = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=1,
                    min_questions=1,
                    top_k=5,
                    standard_cache_dir=cache_dir,
                    rebuild_standard_cache=True,
                )

        self.assertTrue(payload["ok"], payload)
        cache = payload["standard_adapter"]["corpus"]["case_cache"]
        self.assertTrue(cache["rebuild_requested"])
        self.assertEqual(cache["source_index_forced_rebuild_count"], 1)
        self.assertEqual(cache["source_index_rebuild_count"], 1)
        self.assertEqual(cache["source_index_hit_count"], 0)

    def test_fixed_evidence_rank_buckets_cover_near_miss_diagnostics(self) -> None:
        self.assertEqual(standard_public.evidence_rank_bucket(1), "rank_1")
        self.assertEqual(standard_public.evidence_rank_bucket(4), "rank_4_5")
        self.assertEqual(standard_public.evidence_rank_bucket(12), "rank_11_20")
        self.assertEqual(standard_public.evidence_rank_bucket(34), "rank_21_50")
        self.assertEqual(standard_public.evidence_rank_bucket(None), "not_retrieved")

    def test_evidence_miss_category_distinguishes_partial_and_source_window_misses(
        self,
    ) -> None:
        partial_row = {
            "has_line_evidence": True,
            "expected_line_count": 2,
            "expected_lines_found_top10": 1,
            "evidence_hit_top10": True,
            "evidence_context_hit_top10": True,
            "session_hit_top10": True,
        }
        self.assertEqual(
            standard_public.evidence_miss_category(partial_row, top_k=10),
            "multi_evidence_partial_hit",
        )
        source_window_miss = {
            "has_line_evidence": True,
            "expected_line_count": 1,
            "expected_lines_found_top10": 0,
            "evidence_hit_top10": False,
            "evidence_context_hit_top10": False,
            "session_hit_top10": False,
            "evidence_rank": None,
            "session_rank": None,
        }
        self.assertEqual(
            standard_public.evidence_miss_category(source_window_miss, top_k=10),
            "source_window_not_recovered",
        )

    def test_progress_callback_reports_sanitized_phase_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "longmemeval_oracle.json"
            write_oracle_fixture(path, question_count=3)
            progress_events: list[dict[str, Any]] = []
            with patched_oracle_split(path):
                payload = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=3,
                    min_questions=3,
                    top_k=5,
                    progress_every=1,
                    progress_callback=progress_events.append,
                )

        self.assertTrue(payload["ok"], payload)
        phases = [event.get("phase") for event in progress_events]
        self.assertIn("dataset_verified", phases)
        self.assertIn("cases_building", phases)
        self.assertIn("cases_built", phases)
        self.assertIn("cases_evaluated", phases)
        building_counts = [
            int(event.get("cases_built") or 0)
            for event in progress_events
            if event.get("phase") == "cases_building"
        ]
        self.assertIn(1, building_counts)
        evaluated_counts = [
            int(event.get("cases_evaluated") or 0)
            for event in progress_events
            if event.get("phase") == "cases_evaluated"
        ]
        self.assertIn(3, evaluated_counts)
        dumped = json.dumps(progress_events, ensure_ascii=False)
        self.assertNotIn("secret fixture answer marker", dumped)
        self.assertNotIn(str(path), dumped)

    def test_partial_output_records_interrupted_diagnostic_without_raw_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "longmemeval_oracle.json"
            partial_path = Path(tmp) / "partial.json"
            write_oracle_fixture(path, question_count=3)

            def stop_after_first_eval(event: dict[str, Any]) -> None:
                if event.get("phase") == "cases_evaluated" and int(
                    event.get("cases_evaluated") or 0
                ) >= 1:
                    raise KeyboardInterrupt

            with patched_oracle_split(path):
                payload = benchmark.run_longmemeval_benchmark(
                    split_name="longmemeval-v1-oracle",
                    data_file=path,
                    max_questions=3,
                    min_questions=3,
                    top_k=5,
                    progress_every=1,
                    partial_output=partial_path,
                    progress_callback=stop_after_first_eval,
                )

            partial = json.loads(partial_path.read_text(encoding="utf-8"))

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "partial_diagnostic_interrupted")
        self.assertEqual(partial["status"], "partial_diagnostic_interrupted")
        self.assertGreaterEqual(partial["metrics"]["cases_built"], 1)
        self.assertGreaterEqual(partial["metrics"]["cases_evaluated"], 1)
        self.assertIn("longmemeval_retrieval_score", partial["cannot_claim"])
        dumped = json.dumps(partial, ensure_ascii=False)
        self.assertNotIn("secret fixture answer marker", dumped)
        self.assertNotIn(str(path), dumped)


if __name__ == "__main__":
    unittest.main()
