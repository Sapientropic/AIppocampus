from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests.aippocampus.import_path_helpers import import_smoke_module

smoke = import_smoke_module("smoke_semantic_scope_real_history")

from aippocampus_runtime.navigation.project_timeline import (
    build_project_timeline,
    save_project_timeline,
)


class SemanticScopeRealHistorySmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry = self.root / "registry" / "threads.json"
        self.timeline = self.root / "registry" / "project_timeline.json"
        self.jobs = self.root / "registry" / "subconscious_jobs.jsonl"
        self.edges = self.root / "registry" / "subconscious_edges.jsonl"
        self.registry.parent.mkdir()
        self.old_key = os.environ.get("FAKE_DEEPSEEK_KEY")

    def tearDown(self) -> None:
        if self.old_key is None:
            os.environ.pop("FAKE_DEEPSEEK_KEY", None)
        else:
            os.environ["FAKE_DEEPSEEK_KEY"] = self.old_key
        self.tmp.cleanup()

    def _write_fixture(self) -> Path:
        clean = self.root / "thread-life" / "clean-source"
        clean.mkdir(parents=True)
        (clean / "manifest.json").write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
        (clean / "messages.jsonl").write_text(
            json.dumps(
                {
                    "message_id": "life-u",
                    "turn_id": "life-turn",
                    "source_line": 10,
                    "timestamp": "2026-05-27T00:00:00Z",
                    "role": "user",
                    "turn_index": 1,
                    "scope_labels": ["technical_work"],
                    "text": "private metaphor text should stay out of smoke output",
                },
                ensure_ascii=False,
            )
            + "\n"
            + json.dumps(
                {
                    "message_id": "life-a",
                    "turn_id": "life-turn",
                    "source_line": 12,
                    "timestamp": "2026-05-27T00:00:00Z",
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 1,
                    "is_final": True,
                    "scope_labels": [],
                    "text": "private answer text should stay out too",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (clean / "turns.jsonl").write_text(
            json.dumps(
                {
                    "turn_id": "life-turn",
                    "turn_index": 1,
                    "message_ids": ["life-u", "life-a"],
                    "scope_labels": ["technical_work"],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        self.registry.write_text(
            json.dumps(
                {
                    "threads": [
                        {
                            "thread_key": "session:life",
                            "title": "Private Life Title",
                            "project_key": "project:life",
                            "project_label": "Private Life",
                            "paths": {
                                "clean_source_messages_jsonl": str(clean / "messages.jsonl"),
                                "clean_source_turns_jsonl": str(clean / "turns.jsonl"),
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        save_project_timeline(
            self.timeline, build_project_timeline(self.registry, max_turns_per_thread=4)
        )
        return clean

    def _write_multi_turn_fixture(self, count: int = 3) -> Path:
        clean = self.root / "thread-life" / "clean-source"
        clean.mkdir(parents=True)
        (clean / "manifest.json").write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
        message_rows = []
        turn_rows = []
        for index in range(1, count + 1):
            message_id = f"life-u-{index}"
            turn_id = f"life-turn-{index}"
            message_rows.append(
                {
                    "message_id": message_id,
                    "turn_id": turn_id,
                    "source_line": 10 + index,
                    "timestamp": f"2026-05-27T00:0{index}:00Z",
                    "role": "user",
                    "turn_index": index,
                    "scope_labels": ["technical_work"],
                    "text": f"private life-wide candidate {index} should stay out of smoke output",
                }
            )
            turn_rows.append(
                {
                    "turn_id": turn_id,
                    "turn_index": index,
                    "message_ids": [message_id],
                    "scope_labels": ["technical_work"],
                }
            )
        (clean / "messages.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in message_rows),
            encoding="utf-8",
        )
        (clean / "turns.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in turn_rows),
            encoding="utf-8",
        )
        self.registry.write_text(
            json.dumps(
                {
                    "threads": [
                        {
                            "thread_key": "session:life",
                            "title": "Private Life Title",
                            "project_key": "project:life",
                            "project_label": "Private Life",
                            "paths": {
                                "clean_source_messages_jsonl": str(clean / "messages.jsonl"),
                                "clean_source_turns_jsonl": str(clean / "turns.jsonl"),
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        save_project_timeline(
            self.timeline, build_project_timeline(self.registry, max_turns_per_thread=count)
        )
        return clean

    def test_observe_only_reports_insufficient_without_external_model(self) -> None:
        self._write_fixture()

        result = smoke.run_semantic_scope_real_history_smoke(
            registry_path=self.registry,
            timeline_path=self.timeline,
            jobs_output_path=self.jobs,
            edges_output_path=self.edges,
            live=False,
            require_labels=False,
        )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["ok"])
        self.assertEqual(
            result["stage2_semantic_sidecar_status"], "insufficient_dynamic_sidecar_rows"
        )
        self.assertFalse(result["live_model_used"])
        self.assertFalse(
            result["semantic_evidence_diagnostics"]["high_risk_label_families"][
                "per_label_materialized_counts_available"
            ]
        )
        self.assertEqual(
            result["semantic_evidence_diagnostics"]["high_risk_label_families"][
                "missing_after_materialization"
            ],
            [],
        )
        self.assertNotIn("private metaphor text", rendered)
        self.assertNotIn("Private Life Title", rendered)
        self.assertNotIn(str(self.root), rendered)

    def test_public_json_projection_is_aggregate_only(self) -> None:
        internal_result = {
            "ok": False,
            "stage2_semantic_sidecar_status": "live_model_partial_failure",
            "claim_level": "failed_live_model_slice",
            "cannot_claim": ["semantic_completeness"],
            "live_model_used": True,
            "sidecars_written": False,
            "timeline_refreshed": False,
            "privacy_boundary": {
                "raw_text_emitted": False,
                "snippets_emitted": False,
                "titles_emitted": False,
                "source_reference_details_emitted": False,
                "absolute_paths_emitted": False,
                "output_shape": "aggregate_counts_only",
            },
            "before": {"semantic_sidecar_rows": 0, "semantic_sidecar_threads": 0},
            "after": {"semantic_sidecar_rows": 2, "semantic_sidecar_threads": 1},
            "coverage_ratios": {"semantic_sidecar_thread_ratio": 0.5},
            "job": {
                "ok": False,
                "job_count": 2,
                "successful_job_count": 1,
                "failure_count": 1,
                "partial_failure": True,
                "concurrency": 2,
                "samples_per_job": 1,
                "finding_count": 1,
                "wrote": False,
                "cache": {
                    "route": {
                        "api_key_env": "PRIVATE_MODEL_KEY_ENV",
                        "base_url": "https://private-model.example/v1",
                    }
                },
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                "label_evidence": {
                    "finding_count_with_labels": 1,
                    "accepted_label_count": 2,
                    "labels_with_sufficient_evidence": 2,
                    "weak_or_missing_evidence_label_count": 0,
                    "label_evidence_complete": True,
                    "label_coverage": ["idea_seed", "personal_reflection"],
                    "per_label_count": {"idea_seed": 1, "personal_reflection": 1},
                },
                "first_error": (
                    "private failure with token-like material at "
                    f"{self.root / 'thread-life' / 'clean-source' / 'messages.jsonl'}"
                ),
            },
            "materialization": {
                "ok": True,
                "target_count": 1,
                "row_count": 1,
                "wrote": True,
                "boundary": "Semantic scope labels are navigation hints.",
                "raw_path": str(self.root / "semantic-scope-labels.jsonl"),
            },
            "candidate_coverage": {
                "full_candidate_coverage_requested": True,
                "candidate_turn_count": 3,
                "evaluated_candidate_turn_count": 2,
                "unevaluated_candidate_turn_count": 1,
                "failed_batch_indexes": [2],
                "source_turn_cap": 5000,
            },
            "timeline_refresh": {
                "before_live_job": {"wrote": True, "path": str(self.timeline)},
                "after_materialization": {"wrote": True, "path": str(self.timeline)},
            },
            "semantic_candidate_source": {
                "candidate_turn_count": 3,
                "sample_title": "Private Life Title",
                "source_refs": [{"message_id": "life-u"}],
            },
            "thresholds": {"min_sidecar_rows": 1},
        }

        public = smoke.public_smoke_result(internal_result)

        rendered = json.dumps(public, ensure_ascii=False)
        self.assertTrue(public["job"]["cache"]["used"])
        self.assertNotIn("PRIVATE_MODEL_KEY_ENV", rendered)
        self.assertNotIn("private-model.example", rendered)
        self.assertNotIn("private failure", rendered)
        self.assertNotIn("messages.jsonl", rendered)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn("Private Life Title", rendered)
        self.assertNotIn("source_refs", rendered)
        self.assertNotIn("first_error", rendered)
        self.assertNotIn("failed_batch_indexes", rendered)
        self.assertNotIn("raw_path", rendered)

    def test_public_json_explains_sparse_semantic_funnel_and_high_risk_zeros(self) -> None:
        internal_result = {
            "ok": True,
            "stage2_semantic_sidecar_status": "sufficient",
            "claim_level": "dynamic_semantic_sidecar_slice",
            "cannot_claim": ["semantic_completeness"],
            "live_model_used": True,
            "sidecars_written": True,
            "privacy_boundary": {"output_shape": "aggregate_counts_only"},
            "before": {"semantic_sidecar_rows": 0, "semantic_sidecar_threads": 0},
            "after": {"semantic_sidecar_rows": 1, "semantic_sidecar_threads": 1},
            "job": {
                "finding_count": 1,
                "label_evidence": {
                    "finding_count_with_labels": 1,
                    "accepted_label_count": 1,
                    "labels_with_sufficient_evidence": 1,
                    "weak_or_missing_evidence_label_count": 0,
                    "label_evidence_complete": True,
                    "label_coverage": ["open_question"],
                    "per_label_count": {"open_question": 1},
                    "per_label_sufficient_evidence_count": {"open_question": 1},
                    "per_label_weak_or_missing_evidence_count": {},
                },
            },
            "materialization": {
                "ok": True,
                "target_count": 1,
                "row_count": 1,
                "per_label_row_count": {"open_question": 1},
            },
            "candidate_coverage": {
                "full_candidate_coverage_requested": True,
                "candidate_turn_count": 4,
                "evaluated_candidate_turn_count": 4,
                "unevaluated_candidate_turn_count": 0,
                "batch_count": 2,
                "successful_batch_count": 2,
                "failed_batch_count": 0,
                "full_candidate_coverage_passed": True,
            },
            "semantic_candidate_source": {
                "candidate_turn_count": 4,
                "candidate_thread_count": 2,
                "skipped_without_refs": 1,
                "skipped_already_semantic": 1,
            },
            "thresholds": {"min_sidecar_rows": 1},
        }

        public = smoke.public_smoke_result(internal_result)
        diagnostics = public["semantic_evidence_diagnostics"]

        self.assertEqual(diagnostics["funnel"]["selected_candidate_count"], 4)
        self.assertEqual(diagnostics["funnel"]["evaluated_candidate_turn_count"], 4)
        self.assertEqual(diagnostics["funnel"]["finding_count"], 1)
        self.assertEqual(diagnostics["funnel"]["materialized_row_count"], 1)
        self.assertEqual(diagnostics["funnel"]["materialized_thread_count"], 1)
        self.assertEqual(
            diagnostics["materialization_reason_buckets"]["model_abstained_or_no_finding"],
            3,
        )
        self.assertEqual(
            diagnostics["per_label"]["relationship_continuity"]["finding_label_count"],
            0,
        )
        self.assertEqual(
            diagnostics["per_label"]["relationship_continuity"]["materialized_label_count"],
            0,
        )
        self.assertEqual(diagnostics["per_label"]["open_question"]["materialized_label_count"], 1)
        self.assertIn(
            "relationship_continuity",
            diagnostics["high_risk_label_families"]["missing_after_materialization"],
        )
        self.assertIn("semantic_completeness", public["cannot_claim"])

    def test_main_json_uses_public_projection(self) -> None:
        internal_result = {
            "ok": False,
            "stage2_semantic_sidecar_status": "live_model_partial_failure",
            "claim_level": "failed_live_model_slice",
            "live_model_used": True,
            "privacy_boundary": {"output_shape": "aggregate_counts_only"},
            "job": {
                "cache": {"route": {"api_key_env": "PRIVATE_MODEL_KEY_ENV"}},
                "first_error": f"private failure at {self.root / 'messages.jsonl'}",
            },
            "semantic_candidate_source": {
                "sample_title": "Private Life Title",
                "source_refs": [{"message_id": "life-u"}],
            },
        }
        stdout = io.StringIO()

        with (
            mock.patch.object(
                smoke, "run_semantic_scope_real_history_smoke", return_value=internal_result
            ),
            mock.patch.object(sys, "argv", ["smoke_semantic_scope_real_history.py", "--json"]),
            contextlib.redirect_stdout(stdout),
        ):
            exit_code = smoke.main()

        self.assertEqual(exit_code, 1)
        rendered = stdout.getvalue()
        self.assertIn("live_model_partial_failure", rendered)
        self.assertNotIn("PRIVATE_MODEL_KEY_ENV", rendered)
        self.assertNotIn("private failure", rendered)
        self.assertNotIn("messages.jsonl", rendered)
        self.assertNotIn("Private Life Title", rendered)
        self.assertNotIn("source_refs", rendered)

    def test_observe_only_can_require_semantic_sidecar_thread_count(self) -> None:
        clean = self._write_fixture()
        (clean / "semantic-scope-labels.jsonl").write_text(
            json.dumps(
                {
                    "message_id": "life-u",
                    "source": "deepseek_subconscious_scope_labels",
                    "scope_labels": ["personal_reflection"],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = smoke.run_semantic_scope_real_history_smoke(
            registry_path=self.registry,
            timeline_path=self.timeline,
            jobs_output_path=self.jobs,
            edges_output_path=self.edges,
            live=False,
            require_labels=True,
            min_sidecar_rows=1,
            min_sidecar_threads=2,
            min_timeline_turns=1,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["stage2_semantic_sidecar_status"], "insufficient_dynamic_sidecar_threads"
        )

    def test_live_write_materializes_dynamic_sidecar_without_output_leak(self) -> None:
        clean = self._write_fixture()
        os.environ["FAKE_DEEPSEEK_KEY"] = "present"

        def fake_chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):  # noqa: ANN001
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "action": "final",
                                    "findings": [
                                        {
                                            "kind": "semantic_scope_labels",
                                            "title": "semantic life label",
                                            "summary": "semantic label for a casual-important turn",
                                            "confidence": 0.91,
                                            "message_id": "life-u",
                                            "scope_labels": ["personal_reflection", "idea_seed"],
                                            "label_evidence": [
                                                {
                                                    "label": "personal_reflection",
                                                    "reason": "The source is a personally meaningful metaphor.",
                                                    "confidence": 0.88,
                                                },
                                                {
                                                    "label": "idea_seed",
                                                    "reason": "The source frames the metaphor as a pivot idea.",
                                                    "confidence": 0.86,
                                                },
                                            ],
                                            "source_refs": [{"ref": "t0"}],
                                        }
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

        result = smoke.run_semantic_scope_real_history_smoke(
            registry_path=self.registry,
            timeline_path=self.timeline,
            jobs_output_path=self.jobs,
            edges_output_path=self.edges,
            live=True,
            write_sidecars=True,
            require_labels=True,
            api_key_env="FAKE_DEEPSEEK_KEY",
            max_turns=4,
            max_steps=1,
            min_tool_steps=0,
            chat_fn=fake_chat_fn,
        )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["ok"], rendered)
        self.assertEqual(result["stage2_semantic_sidecar_status"], "sufficient")
        self.assertTrue(result["live_model_used"])
        self.assertTrue(result["sidecars_written"])
        self.assertGreaterEqual(result["after"]["semantic_sidecar_rows"], 1)
        self.assertGreaterEqual(
            result["after"]["timeline_latest_turns_with_semantic_scope_labels"], 1
        )
        self.assertTrue((clean / "semantic-scope-labels.jsonl").exists())
        self.assertEqual(result["claim_level"], "dynamic_semantic_sidecar_slice")
        self.assertIn("semantic_completeness", result["cannot_claim"])
        self.assertEqual(result["coverage_ratios"]["semantic_sidecar_thread_ratio"], 1.0)
        self.assertEqual(result["coverage_ratios"]["semantic_sidecar_row_count"], 1)
        self.assertEqual(result["coverage_ratios"]["semantic_timeline_turn_ratio"], 1.0)
        self.assertTrue(result["job"]["label_evidence"]["label_evidence_complete"])
        self.assertEqual(result["job"]["label_evidence"]["accepted_label_count"], 4)
        self.assertEqual(result["job"]["label_evidence"]["weak_or_missing_evidence_label_count"], 0)
        self.assertEqual(
            result["job"]["label_evidence"]["label_coverage"], ["idea_seed", "personal_reflection"]
        )
        self.assertNotIn("private metaphor text", rendered)
        self.assertNotIn("Private Life Title", rendered)
        self.assertNotIn("source_refs", rendered)
        self.assertNotIn(str(self.root), rendered)

    def test_live_defaults_run_multiple_deepseek_samples_with_cache_warmup_order(self) -> None:
        self._write_fixture()
        os.environ["FAKE_DEEPSEEK_KEY"] = "present"
        calls: list[str] = []
        lock = threading.Lock()
        sample1_finished = threading.Event()
        sample2_started_before_warm = False

        def fake_chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):  # noqa: ANN001
            nonlocal sample2_started_before_warm
            payload = json.loads(messages[1]["content"])
            sample_two = "Diversity sample 2/2" in str(payload.get("objective") or "")
            with lock:
                calls.append(messages[1]["content"])
                if sample_two and not sample1_finished.is_set():
                    sample2_started_before_warm = True
            if not sample_two:
                sample1_finished.set()
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "action": "final",
                                    "findings": [
                                        {
                                            "kind": "semantic_scope_labels",
                                            "title": "parallel semantic label",
                                            "summary": "semantic label from a parallel DeepSeek sample",
                                            "confidence": 0.9,
                                            "message_id": "life-u",
                                            "scope_labels": ["personal_reflection", "idea_seed"],
                                            "label_evidence": [
                                                {
                                                    "label": "personal_reflection",
                                                    "reason": "The source is a personally meaningful metaphor.",
                                                    "confidence": 0.88,
                                                },
                                                {
                                                    "label": "idea_seed",
                                                    "reason": "The source frames the metaphor as a pivot idea.",
                                                    "confidence": 0.86,
                                                },
                                            ],
                                            "source_refs": [{"ref": "t0"}],
                                        }
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

        result = smoke.run_semantic_scope_real_history_smoke(
            registry_path=self.registry,
            timeline_path=self.timeline,
            jobs_output_path=self.jobs,
            edges_output_path=self.edges,
            live=True,
            write_sidecars=False,
            require_labels=False,
            api_key_env="FAKE_DEEPSEEK_KEY",
            max_turns=4,
            max_steps=1,
            min_tool_steps=0,
            chat_fn=fake_chat_fn,
        )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["ok"], rendered)
        self.assertEqual(len(calls), 2)
        self.assertFalse(sample2_started_before_warm)
        self.assertEqual(result["job"]["job_count"], 2)
        self.assertEqual(result["job"]["successful_job_count"], 2)
        self.assertEqual(result["job"]["failure_count"], 0)
        self.assertGreaterEqual(result["job"]["concurrency"], 2)
        self.assertEqual(result["job"]["samples_per_job"], 2)
        self.assertTrue(result["job"]["label_evidence"]["label_evidence_complete"])
        self.assertEqual(result["job"]["label_evidence"]["accepted_label_count"], 4)

    def test_semantic_candidate_timeline_prioritizes_unlabeled_life_wide_turns(self) -> None:
        timeline = {
            "life_wide": {
                "labels": {
                    "personal_reflection": {
                        "latest_turns": [
                            {
                                "thread_key": "session:already-labeled",
                                "turn_id": "turn_labeled",
                                "semantic_scope_labels": ["personal_reflection"],
                                "source_refs": [{"message_id": "msg_labeled"}],
                            },
                            {
                                "thread_key": "session:reflection",
                                "turn_id": "turn_reflection",
                                "scope_labels": ["personal_reflection"],
                                "source_refs": [{"message_id": "msg_reflection"}],
                            },
                        ]
                    },
                    "idea_seed": {
                        "latest_turns": [
                            {
                                "thread_key": "session:reflection",
                                "turn_id": "turn_reflection",
                                "scope_labels": ["personal_reflection"],
                                "source_refs": [{"message_id": "msg_reflection"}],
                            },
                            {
                                "thread_key": "session:idea",
                                "turn_id": "turn_idea",
                                "scope_labels": ["idea_seed"],
                                "source_refs": [{"message_id": "msg_idea"}],
                            },
                        ]
                    },
                }
            }
        }

        candidate = smoke.semantic_candidate_timeline_from_life_wide(timeline, max_turns=4)
        turns = candidate["projects"]["stage2_life_wide_semantic_candidates"]["latest_turns"]

        self.assertEqual(
            [turn["thread_key"] for turn in turns], ["session:reflection", "session:idea"]
        )
        self.assertEqual(candidate["candidate_metrics"]["candidate_turn_count"], 2)
        self.assertEqual(candidate["candidate_metrics"]["candidate_thread_count"], 2)

    def test_full_candidate_coverage_batches_evaluate_all_unlabeled_candidates(self) -> None:
        clean = self._write_multi_turn_fixture(count=3)
        os.environ["FAKE_DEEPSEEK_KEY"] = "present"
        seen_batches: list[list[str]] = []

        def fake_chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):  # noqa: ANN001
            payload = json.loads(messages[1]["content"])
            turns = payload["initial_turns"]
            message_ids = [turn["source_refs"][0]["message_id"] for turn in turns]
            seen_batches.append(message_ids)
            findings = [
                {
                    "kind": "semantic_scope_labels",
                    "title": "semantic candidate label",
                    "summary": "semantic label from full candidate coverage",
                    "confidence": 0.91,
                    "message_id": message_id,
                    "scope_labels": ["personal_reflection", "idea_seed"],
                    "label_evidence": [
                        {
                            "label": "personal_reflection",
                            "reason": "The source is a personally meaningful life-wide candidate.",
                            "confidence": 0.88,
                        },
                        {
                            "label": "idea_seed",
                            "reason": "The source records an early idea candidate.",
                            "confidence": 0.86,
                        },
                    ],
                    "source_refs": [{"ref": f"t{idx}"}],
                }
                for idx, message_id in enumerate(message_ids)
            ]
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"action": "final", "findings": findings}, ensure_ascii=False
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

        result = smoke.run_semantic_scope_real_history_smoke(
            registry_path=self.registry,
            timeline_path=self.timeline,
            jobs_output_path=self.jobs,
            edges_output_path=self.edges,
            live=True,
            write_sidecars=True,
            require_labels=True,
            api_key_env="FAKE_DEEPSEEK_KEY",
            max_turns=1,
            max_steps=1,
            min_tool_steps=0,
            full_candidate_coverage=True,
            candidate_batch_size=1,
            samples_per_job=1,
            min_sidecar_rows=3,
            min_timeline_turns=1,
            chat_fn=fake_chat_fn,
        )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["ok"], rendered)
        self.assertEqual(len(seen_batches), 3)
        self.assertEqual(
            sorted(message_id for batch in seen_batches for message_id in batch),
            ["life-u-1", "life-u-2", "life-u-3"],
        )
        self.assertEqual(result["candidate_coverage"]["candidate_turn_count"], 3)
        self.assertEqual(result["candidate_coverage"]["evaluated_candidate_turn_count"], 3)
        self.assertEqual(result["candidate_coverage"]["unevaluated_candidate_turn_count"], 0)
        self.assertEqual(result["candidate_coverage"]["batch_count"], 3)
        self.assertEqual(result["materialization"]["row_count"], 3)
        self.assertEqual(
            result["semantic_evidence_diagnostics"]["funnel"]["selected_candidate_count"],
            3,
        )
        self.assertEqual(
            result["semantic_evidence_diagnostics"]["per_label"]["idea_seed"][
                "materialized_label_count"
            ],
            3,
        )
        self.assertEqual(
            result["semantic_evidence_diagnostics"]["per_label"]["relationship_continuity"][
                "materialized_label_count"
            ],
            0,
        )
        self.assertTrue((clean / "semantic-scope-labels.jsonl").exists())
        self.assertNotIn("private life-wide candidate", rendered)
        self.assertNotIn("Private Life Title", rendered)

    def test_semantic_candidate_batch_repairs_missing_label_evidence_before_write(self) -> None:
        self._write_multi_turn_fixture(count=1)
        os.environ["FAKE_DEEPSEEK_KEY"] = "present"
        observed_messages: list[list[dict[str, str]]] = []

        def fake_chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):  # noqa: ANN001
            del api_key, model, base_url, max_tokens, timeout, temperature
            observed_messages.append([dict(message) for message in messages])
            payload = json.loads(messages[1]["content"])
            message_id = payload["initial_turns"][0]["source_refs"][0]["message_id"]
            finding = {
                "kind": "semantic_scope_labels",
                "title": "semantic candidate label",
                "summary": "semantic label from full candidate coverage",
                "confidence": 0.91,
                "message_id": message_id,
                "scope_labels": ["idea_seed"],
                "source_refs": [{"ref": "t0"}],
            }
            if len(observed_messages) > 1:
                finding["label_evidence"] = [
                    {
                        "label": "idea_seed",
                        "reason": "The source records an early idea candidate.",
                        "confidence": 0.91,
                    }
                ]
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"action": "final", "findings": [finding]},
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

        result = smoke.run_semantic_scope_real_history_smoke(
            registry_path=self.registry,
            timeline_path=self.timeline,
            jobs_output_path=self.jobs,
            edges_output_path=self.edges,
            live=True,
            write_sidecars=True,
            require_labels=True,
            api_key_env="FAKE_DEEPSEEK_KEY",
            max_turns=1,
            max_steps=2,
            min_tool_steps=0,
            full_candidate_coverage=True,
            candidate_batch_size=1,
            samples_per_job=1,
            min_sidecar_rows=1,
            min_timeline_turns=1,
            chat_fn=fake_chat_fn,
        )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["ok"], rendered)
        self.assertEqual(len(observed_messages), 2)
        feedback = json.loads(observed_messages[1][-1]["content"])
        self.assertIn("semantic_scope_labeling_requirements", feedback)
        self.assertIn("label_evidence", feedback["semantic_scope_labeling_requirements"])
        self.assertEqual(result["materialization"]["row_count"], 1)
        self.assertTrue(result["job"]["label_evidence"]["label_evidence_complete"])
        rows = [
            json.loads(line)
            for line in self.jobs.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["scope_labels"], ["idea_seed"])
        self.assertEqual(rows[0]["label_evidence"][0]["label"], "idea_seed")

    def test_full_candidate_coverage_warms_each_batch_before_followup_samples(self) -> None:
        self._write_multi_turn_fixture(count=2)
        os.environ["FAKE_DEEPSEEK_KEY"] = "present"
        sample1_finished_by_batch: dict[str, threading.Event] = {}
        sample2_started_before_warm: list[str] = []
        lock = threading.Lock()

        def fake_chat_fn(messages, api_key, model, base_url, max_tokens, timeout, temperature):  # noqa: ANN001
            del api_key, model, base_url, max_tokens, timeout, temperature
            payload = json.loads(messages[1]["content"])
            turns = payload["initial_turns"]
            batch_key = ",".join(turn["source_refs"][0]["message_id"] for turn in turns)
            sample_two = "Diversity sample 2/2" in str(payload.get("objective") or "")
            with lock:
                event = sample1_finished_by_batch.setdefault(batch_key, threading.Event())
                if sample_two and not event.is_set():
                    sample2_started_before_warm.append(batch_key)
            if not sample_two:
                sample1_finished_by_batch[batch_key].set()
            findings = [
                {
                    "kind": "semantic_scope_labels",
                    "title": "semantic candidate label",
                    "summary": "semantic label from full candidate coverage",
                    "confidence": 0.91,
                    "message_id": turn["source_refs"][0]["message_id"],
                    "scope_labels": ["idea_seed"],
                    "label_evidence": [
                        {
                            "label": "idea_seed",
                            "reason": "The source records an early idea candidate.",
                            "confidence": 0.86,
                        }
                    ],
                    "source_refs": [{"ref": f"t{idx}"}],
                }
                for idx, turn in enumerate(turns)
            ]
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"action": "final", "findings": findings}, ensure_ascii=False
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

        result = smoke.run_semantic_scope_real_history_smoke(
            registry_path=self.registry,
            timeline_path=self.timeline,
            jobs_output_path=self.jobs,
            edges_output_path=self.edges,
            live=True,
            write_sidecars=False,
            require_labels=False,
            api_key_env="FAKE_DEEPSEEK_KEY",
            full_candidate_coverage=True,
            candidate_batch_size=1,
            samples_per_job=2,
            concurrency=4,
            max_steps=1,
            min_tool_steps=0,
            chat_fn=fake_chat_fn,
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["candidate_coverage"]["batch_count"], 2)
        self.assertEqual(result["job"]["job_count"], 4)
        self.assertEqual(sample2_started_before_warm, [])

    def test_live_missing_api_key_fails_instead_of_falling_back_to_observe_only(self) -> None:
        self._write_fixture()
        os.environ.pop("FAKE_DEEPSEEK_KEY", None)

        diagnostic = smoke.run_semantic_scope_real_history_smoke(
            registry_path=self.registry,
            timeline_path=self.timeline,
            jobs_output_path=self.jobs,
            edges_output_path=self.edges,
            live=True,
            require_labels=False,
            api_key_env="FAKE_DEEPSEEK_KEY",
        )
        strict = smoke.run_semantic_scope_real_history_smoke(
            registry_path=self.registry,
            timeline_path=self.timeline,
            jobs_output_path=self.jobs,
            edges_output_path=self.edges,
            live=True,
            require_labels=True,
            api_key_env="FAKE_DEEPSEEK_KEY",
        )

        self.assertFalse(diagnostic["ok"])
        self.assertEqual(diagnostic["stage2_semantic_sidecar_status"], "live_model_missing_api_key")
        self.assertEqual(diagnostic["claim_level"], "blocked_live_model")
        self.assertIn("fresh_live_model_run", diagnostic["cannot_claim"])
        self.assertFalse(strict["ok"])

if __name__ == "__main__":
    unittest.main()
