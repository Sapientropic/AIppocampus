from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime.dream import live_shadow_ab as shadow
from aippocampus_runtime.dream import public_shadow_report
from aippocampus_runtime.model.client import ChatClientConfig


class DreamLiveShadowABTests(unittest.TestCase):
    def test_public_dream_vs_baseline_report_tracks_user_visible_axes(self) -> None:
        report = public_shadow_report.build_public_dream_vs_baseline_shadow_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        readout = report["issue_readouts"]["github_163"]

        self.assertEqual(report["kind"], "aippocampus_public_dream_vs_baseline_shadow_report")
        self.assertTrue(report["ok"])
        self.assertEqual(report["metrics"]["case_count"], 4)
        self.assertEqual(report["metrics"]["dream_route_lift_count"], 2)
        self.assertEqual(report["metrics"]["dream_win_count"], 2)
        self.assertEqual(report["metrics"]["dream_no_help_count"], 1)
        self.assertEqual(report["metrics"]["dream_regression_count"], 0)
        self.assertEqual(report["metrics"]["suppressed_regression_risk_count"], 1)
        self.assertEqual(report["metrics"]["dream_action_delta_useful_count"], 2)
        self.assertEqual(report["metrics"]["suppressed_wrong_hint_count"], 1)
        self.assertEqual(report["metrics"]["dream_wrong_hint_count"], 0)
        self.assertEqual(report["metrics"]["dream_wrong_hint_rate"], 0.0)
        self.assertEqual(report["metrics"]["dream_no_harm_count"], 2)
        self.assertLess(report["metrics"]["dream_verification_cost_delta_total"], 0)
        self.assertTrue(readout["public_dream_vs_baseline_shadow_measured"])
        self.assertEqual(readout["dream_route_lift_count"], 2)
        self.assertEqual(readout["dream_wrong_hint_rate"], 0.0)
        self.assertFalse(readout["live_delivered_quality_measured"])
        self.assertFalse(readout["closeout_eligible"])
        self.assertTrue(report["issue_readouts"]["github_1364"]["closeout_eligible"])
        self.assertEqual(report["issue_readouts"]["github_1364"]["claim_level"], "public_safe_shadow_not_live_default")
        review = report["candidate_quality_review"]
        self.assertEqual(review["metrics"]["reviewed_candidate_count"], 6)
        self.assertEqual(review["metrics"]["useful_candidate_count"], 2)
        self.assertEqual(review["metrics"]["quiet_no_help_candidate_count"], 1)
        self.assertEqual(review["metrics"]["false_positive_candidate_count"], 3)
        self.assertEqual(review["metrics"]["foreground_leak_count"], 0)
        self.assertIn("stale_route", review["metrics"]["false_positive_categories"])
        self.assertIn("noisy_generic_vocab", review["metrics"]["false_positive_categories"])
        self.assertIn("privacy_or_safety_boundary", review["metrics"]["false_positive_categories"])
        self.assertTrue(report["issue_readouts"]["github_1365"]["closeout_eligible"])
        self.assertTrue(report["policy_boundary"]["source_reopen_required_for_claims"])
        self.assertFalse(report["privacy"]["raw_case_text_serialized"])
        self.assertFalse(report["privacy"]["raw_source_refs_serialized"])
        self.assertFalse(report["privacy"]["absolute_paths_serialized"])
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn("C:\\", encoded)

    def test_live_shadow_model_config_uses_deepseek_thinking_contract(self) -> None:
        class Args:
            model_route = None
            model = ""
            base_url = ""
            api_key_env = "AIPPOCAMPUS_DEEPSEEK_API_KEY"
            max_tokens = None
            dream_model_timeout = 5.0
            dream_model_temperature = 0.0
            dream_model_thinking = "auto"
            dream_model_reasoning_effort = "auto"

        with patch.dict(os.environ, {"AIPPOCAMPUS_DEEPSEEK_API_KEY": "test"}, clear=False):
            config, route_payload = shadow.dream_model_config_from_args(Args())

        self.assertEqual(config.thinking, "enabled")
        self.assertEqual(config.reasoning_effort, "high")
        self.assertEqual(route_payload["provider"], "deepseek")

    def test_recall_reminder_classifier_is_strict_about_temporal_noise(self) -> None:
        positives = [
            "你忘了我们之前说过要先回忆旧线程。",
            "回忆一下上次那个 clean source 边界再继续。",
            "As I said before, you forgot the old constraint.",
            "还记得我们之前聊过的 dream hypothesis gate 吗？",
        ]
        negatives = [
            "before calling render, run the tests",
            "保留之前的代码风格，但这里不用查旧对话。",
            "previous commit changed this function name",
            "先把上一段 diff 格式整理一下。",
        ]

        self.assertTrue(all(shadow.classify_recall_reminder(text)["is_reminder"] for text in positives))
        self.assertFalse(any(shadow.classify_recall_reminder(text)["is_reminder"] for text in negatives))

    def test_shadow_event_output_is_hash_only_and_records_both_arms(self) -> None:
        baseline_rows: list[dict[str, object]] = []
        dream_rows = [
            {
                "kind": "aippocampus_working_memory",
                "status": "active",
                "route": "use_with_source",
                "candidate_type": "dream_hypothesis",
                "candidate_key": "wm_dream_continuity",
                "title": "Continuity source-ref bridge",
                "summary": "Use only as a route hint.",
                "trigger_terms": ["continuity"],
                "source_finding_ids": ["dreamfinding_continuity"],
                "confidence": 0.7,
                "project_label": "AIppocampus",
                "review_state": "agent_adjudicated",
                "sensitive_use_gate": {"state": "allowed"},
                "foreground_use": {"strong_claim_requires_source_reopen": True},
            }
        ]

        event = shadow.build_shadow_prompt_event(
            prompt="continuity 这条线下一步怎么收？",
            session_id="session-secret",
            turn_id="turn-secret",
            baseline_rows=baseline_rows,
            dream_rows=dream_rows,
            project_label="AIppocampus",
            salt="unit-test",
        )
        encoded = json.dumps(event, ensure_ascii=False)

        self.assertEqual(event["kind"], "aippocampus_dream_shadow_ab_event")
        self.assertTrue(event["eligible_exposure"])
        self.assertEqual(event["baseline"]["match_count"], 0)
        self.assertEqual(event["dream"]["match_count"], 1)
        self.assertIn(event["assigned_arm"], {"control", "dream"})
        self.assertNotIn("continuity 这条线", encoded)
        self.assertNotIn("session-secret", encoded)
        self.assertNotIn("turn-secret", encoded)

    def test_semantic_relevance_gate_can_create_dream_only_exposure(self) -> None:
        calls: list[list[dict[str, str]]] = []

        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            calls.append(messages)
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "matches": [
                                        {
                                            "candidate_key": "wm_dream_delivery_gate",
                                            "relevant": True,
                                            "confidence": 0.82,
                                            "reason": "same delivery-control concern",
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            }

        event = shadow.build_shadow_prompt_event(
            prompt="怎么避免重蹈旧 rollout 失控的问题？",
            session_id="session-secret",
            turn_id="turn-secret",
            baseline_rows=[],
            dream_rows=[
                {
                    "kind": "aippocampus_working_memory",
                    "status": "active",
                    "route": "use_with_source",
                    "candidate_type": "dream_hypothesis",
                    "candidate_key": "wm_dream_delivery_gate",
                    "title": "Opt-in treatment-control delivery gate",
                    "summary": "Use only when the current prompt is about controlled rollout safety.",
                    "trigger_terms": ["opt-in treatment control arms"],
                    "activation_cues": ["foreground delivery A/B requires explicit opt-in"],
                    "source_finding_ids": ["dreamfinding_delivery"],
                    "confidence": 0.7,
                    "project_label": "AIppocampus",
                    "review_state": "agent_adjudicated",
                    "sensitive_use_gate": {"state": "allowed"},
                    "foreground_use": {"strong_claim_requires_source_reopen": True},
                }
            ],
            semantic_relevance_config=ChatClientConfig(
                api_key="test",
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                cache_contract="deepseek_prefix_v1",
            ),
            semantic_relevance_model_call=fake_model_call,
            project_label="AIppocampus",
            salt="unit-test",
        )
        encoded = json.dumps(event, ensure_ascii=False)

        self.assertTrue(event["eligible_exposure"])
        self.assertEqual(event["dream"]["match_count"], 1)
        self.assertEqual(event["dream"]["semantic_match_count"], 1)
        self.assertEqual(event["semantic_relevance"]["model_call_count"], 1)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("怎么避免", encoded)
        self.assertNotIn("session-secret", encoded)
        metrics = shadow.analyze_shadow_events([event])
        self.assertEqual(metrics["match_diagnostics"]["semantic_relevance_model_call_count"], 1)
        self.assertEqual(metrics["match_diagnostics"]["semantic_relevance_match_event_count"], 1)
        self.assertEqual(metrics["match_diagnostics"]["dream_only_non_reminder_event_count"], 1)

    def test_dry_run_records_would_deliver_without_live_delivery(self) -> None:
        event = shadow.build_shadow_prompt_event(
            prompt="continuity 这条线下一步怎么收？",
            session_id="session-secret",
            turn_id="turn-secret",
            topic_epoch="epoch-dream",
            baseline_rows=[],
            dream_rows=[
                {
                    "kind": "aippocampus_working_memory",
                    "status": "active",
                    "route": "use_with_source",
                    "candidate_type": "dream_hypothesis",
                    "candidate_key": "wm_dream_continuity",
                    "title": "Continuity source-ref bridge",
                    "summary": "Use only as a route hint.",
                    "trigger_terms": ["continuity"],
                    "source_finding_ids": ["dreamfinding_continuity"],
                    "confidence": 0.7,
                    "project_label": "AIppocampus",
                    "review_state": "agent_adjudicated",
                    "sensitive_use_gate": {"state": "allowed"},
                }
            ],
            delivery_mode="dry_run",
            assignment_unit="thread_topic_epoch",
            rollout_rate=1.0,
            project_label="AIppocampus",
            salt="unit-test",
        )
        metrics = shadow.analyze_shadow_events([event])

        self.assertTrue(event["eligible_exposure"])
        self.assertEqual(event["assignment_unit"], "thread_topic_epoch")
        self.assertIn(event["would_deliver_arm"], {"control", "dream"})
        self.assertIsNone(event["delivered_arm"])
        self.assertIn("dry_run", event["delivery_decision"])
        self.assertEqual(event["delivery_block_reasons"], [])
        self.assertEqual(metrics["live_delivery_event_count"], 0)
        self.assertEqual(metrics["would_delivery_event_count"], 1)

    def test_delivered_assignment_is_stable_per_thread_topic_epoch(self) -> None:
        dream_rows = [
            {
                "kind": "aippocampus_working_memory",
                "status": "active",
                "route": "use_with_source",
                "candidate_type": "dream_hypothesis",
                "candidate_key": "wm_dream_continuity",
                "title": "Continuity source-ref bridge",
                "summary": "Use only as a route hint.",
                "trigger_terms": ["continuity"],
                "source_finding_ids": ["dreamfinding_continuity"],
                "confidence": 0.7,
                "project_label": "AIppocampus",
                "review_state": "agent_adjudicated",
                "sensitive_use_gate": {"state": "allowed"},
            }
        ]
        first = shadow.build_shadow_prompt_event(
            prompt="continuity 这条线下一步怎么收？",
            session_id="session-secret",
            turn_id="turn-a",
            topic_epoch="epoch-dream",
            baseline_rows=[],
            dream_rows=dream_rows,
            delivery_mode="delivered",
            assignment_unit="thread_topic_epoch",
            rollout_rate=1.0,
            project_label="AIppocampus",
            salt="unit-test",
        )
        second = shadow.build_shadow_prompt_event(
            prompt="continuity source refs 还在吗？",
            session_id="session-secret",
            turn_id="turn-b",
            topic_epoch="epoch-dream",
            baseline_rows=[],
            dream_rows=dream_rows,
            delivery_mode="delivered",
            assignment_unit="thread_topic_epoch",
            rollout_rate=1.0,
            project_label="AIppocampus",
            salt="unit-test",
        )
        metrics = shadow.analyze_shadow_events([first, second])

        self.assertEqual(first["assignment_unit"], "thread_topic_epoch")
        self.assertEqual(first["assigned_arm"], second["assigned_arm"])
        self.assertEqual(first["delivered_arm"], first["assigned_arm"])
        self.assertEqual(second["delivered_arm"], second["assigned_arm"])
        self.assertEqual(metrics["live_delivery_event_count"], 2)

    def test_semantic_relevance_error_fails_closed_for_delivery(self) -> None:
        def failing_model_call(
            messages: list[dict[str, str]], call_config: ChatClientConfig
        ) -> dict[str, object]:
            raise TimeoutError("semantic gate timed out")

        event = shadow.build_shadow_prompt_event(
            prompt="怎么避免重蹈旧 rollout 失控的问题？",
            session_id="session-secret",
            turn_id="turn-secret",
            baseline_rows=[],
            dream_rows=[
                {
                    "kind": "aippocampus_working_memory",
                    "status": "active",
                    "route": "use_with_source",
                    "candidate_type": "dream_hypothesis",
                    "candidate_key": "wm_dream_delivery_gate",
                    "title": "Opt-in treatment-control delivery gate",
                    "summary": "Use only when the current prompt is about controlled rollout safety.",
                    "trigger_terms": ["foreground delivery A/B requires explicit opt-in"],
                    "activation_cues": ["foreground delivery A/B requires explicit opt-in"],
                    "source_finding_ids": ["dreamfinding_delivery"],
                    "confidence": 0.7,
                    "project_label": "AIppocampus",
                    "review_state": "agent_adjudicated",
                    "sensitive_use_gate": {"state": "allowed"},
                }
            ],
            semantic_relevance_config=ChatClientConfig(
                api_key="test",
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                cache_contract="deepseek_prefix_v1",
            ),
            semantic_relevance_model_call=failing_model_call,
            delivery_mode="dry_run",
            assignment_unit="thread_topic_epoch",
            rollout_rate=1.0,
            project_label="AIppocampus",
            salt="unit-test",
        )

        self.assertFalse(event["eligible_exposure"])
        self.assertIsNone(event["would_deliver_arm"])
        self.assertIsNone(event["delivered_arm"])
        self.assertIn("dream_miss", event["delivery_block_reasons"])
        self.assertEqual(event["semantic_relevance"]["error_type"], "TimeoutError")

    def test_outcome_attribution_uses_nearest_prior_eligible_exposure_once(self) -> None:
        rows = [
            shadow.test_event(
                index=0,
                arm="control",
                eligible=True,
                reminder=False,
                thread="thread-a",
            ),
            shadow.test_event(
                index=1,
                arm="dream",
                eligible=True,
                reminder=False,
                thread="thread-a",
            ),
            shadow.test_event(
                index=2,
                arm="control",
                eligible=False,
                reminder=True,
                thread="thread-a",
            ),
            shadow.test_event(
                index=0,
                arm="dream",
                eligible=True,
                reminder=False,
                thread="thread-b",
            ),
            shadow.test_event(
                index=1,
                arm="control",
                eligible=False,
                reminder=False,
                thread="thread-b",
            ),
        ]

        metrics = shadow.analyze_shadow_events(rows, window_user_turns=3)

        self.assertEqual(metrics["arms"]["control"]["eligible_exposures"], 1)
        self.assertEqual(metrics["arms"]["control"]["reminder_outcomes"], 0)
        self.assertEqual(metrics["arms"]["dream"]["eligible_exposures"], 2)
        self.assertEqual(metrics["arms"]["dream"]["reminder_outcomes"], 1)
        self.assertEqual(metrics["attribution"]["attributed_reminder_count"], 1)
        self.assertEqual(metrics["attribution"]["unattributed_reminder_count"], 0)
        self.assertEqual(metrics["reminder_family_counts"], {"unit": 1})
        self.assertEqual(metrics["reminder_strength_counts"], {"high": 1})
        self.assertEqual(
            metrics["match_diagnostics"],
            {
                "baseline_match_event_count": 0,
                "dream_match_event_count": 3,
                "both_match_event_count": 0,
                "dream_only_non_reminder_event_count": 3,
                "dream_only_reminder_event_count": 0,
                "semantic_relevance_model_call_count": 0,
                "semantic_relevance_match_event_count": 0,
            },
        )

    def test_append_and_analyze_event_log_keeps_report_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shadow.jsonl"
            shadow.append_event(path, shadow.test_event(index=0, arm="control", eligible=True))
            shadow.append_event(path, shadow.test_event(index=1, arm="control", eligible=False, reminder=True))

            payload = shadow.run_shadow_ab_analysis(event_log=path, window_user_turns=2)
            encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["kind"], "aippocampus_dream_live_shadow_ab_analysis")
        self.assertEqual(payload["metrics"]["attribution"]["attributed_reminder_count"], 1)
        self.assertFalse(payload["private_text_emitted"])
        self.assertNotIn("prompt", encoded)
        self.assertNotIn("thread-a", encoded)

    def test_clean_source_dir_replay_streams_public_corpus_without_private_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean_dir = root / "clean-source"
            clean_dir.mkdir()
            (clean_dir / "messages.jsonl").write_text(
                "\n".join(
                    json.dumps(row, ensure_ascii=False)
                    for row in [
                        {
                            "message_id": "msg-a-1",
                            "turn_id": "turn-a-1",
                            "source_id": "source-a",
                            "role": "user",
                            "turn_index": 1,
                            "source_line": 1,
                            "text": "continuity 这条线下一步怎么收？",
                        },
                        {
                            "message_id": "msg-a-2",
                            "turn_id": "turn-a-2",
                            "source_id": "source-a",
                            "role": "user",
                            "turn_index": 2,
                            "source_line": 2,
                            "text": "你忘了我们之前说过要沿着 continuity 继续。",
                        },
                        {
                            "message_id": "msg-b-1",
                            "turn_id": "turn-b-1",
                            "source_id": "source-b",
                            "role": "user",
                            "turn_index": 1,
                            "source_line": 1,
                            "text": "before calling render, run the tests",
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            working_memory = root / "working_memory.jsonl"
            working_memory.write_text(
                json.dumps(
                    {
                        "kind": "aippocampus_working_memory",
                        "status": "active",
                        "route": "use_with_source",
                        "candidate_type": "dream_hypothesis",
                        "candidate_key": "wm_dream_continuity",
                        "title": "Continuity source-ref bridge",
                        "summary": "Use only as a route hint.",
                        "trigger_terms": ["continuity"],
                        "source_finding_ids": ["dreamfinding_continuity"],
                        "confidence": 0.7,
                        "project_label": "AIppocampus",
                        "review_state": "agent_adjudicated",
                        "sensitive_use_gate": {"state": "allowed"},
                        "foreground_use": {"strong_claim_requires_source_reopen": True},
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            payload = shadow.run_clean_source_dir_replay_analysis(
                clean_source_dir=clean_dir,
                dataset_id="fixture_public",
                working_memory_path=working_memory,
                max_threads=10,
                max_user_messages=10,
                window_user_turns=3,
                salt="unit-test-0",
            )
            encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["status"], "analyzed")
        self.assertEqual(payload["claim_level"], "benchmark_corpus_shadow_replay_reminder_frequency")
        self.assertEqual(payload["metrics"]["event_count"], 3)
        self.assertEqual(payload["metrics"]["thread_count"], 2)
        self.assertEqual(payload["metrics"]["arms"]["dream"]["eligible_exposures"], 1)
        self.assertEqual(payload["metrics"]["attribution"]["attributed_reminder_count"], 1)
        self.assertEqual(payload["metrics"]["match_diagnostics"]["dream_match_event_count"], 2)
        self.assertEqual(payload["metrics"]["match_diagnostics"]["dream_only_non_reminder_event_count"], 1)
        self.assertEqual(payload["metrics"]["match_diagnostics"]["dream_only_reminder_event_count"], 1)
        self.assertFalse(payload["private_text_emitted"])
        self.assertNotIn("continuity 这条线", encoded)
        self.assertNotIn("source-a", encoded)
        self.assertNotIn(str(clean_dir), encoded)

    def test_generated_dream_rows_can_use_model_backed_worker(self) -> None:
        seen: dict[str, object] = {}

        def fake_select_real_history_packs(**kwargs: object) -> list[dict[str, object]]:
            seen["select_kwargs"] = kwargs
            return [
                {
                    "kind": "aippocampus_dream_input_pack",
                    "status": "ready_for_dream_worker",
                    "pack_id": "pack-a",
                }
            ]

        def fake_run_pack_dream_worker(pack: object, **kwargs: object) -> dict[str, object]:
            seen["pack"] = pack
            seen["worker_kwargs"] = kwargs
            return {
                "dream_working_memory_rows": [
                    {
                        "kind": "aippocampus_working_memory",
                        "status": "active",
                        "candidate_type": "dream_hypothesis",
                        "candidate_key": "wm_dream_model",
                        "title": "Model-backed dream hypothesis",
                        "summary": "Use only as a route hint.",
                        "trigger_terms": ["continuity"],
                        "source_finding_ids": ["dreamfinding_model"],
                        "confidence": 0.7,
                        "project_label": "AIppocampus",
                    }
                ]
            }

        config = ChatClientConfig(
            api_key="test",
            model="deepseek-v4-flash",
            base_url="https://example.invalid",
            cache_contract="deepseek_prefix_v1",
        )

        with tempfile.TemporaryDirectory() as tmp:
            registry_dir = Path(tmp)
            (registry_dir / "threads.json").write_text(
                json.dumps({"schema_version": 1, "threads": []}),
                encoding="utf-8",
            )
            (registry_dir / "subconscious_jobs.jsonl").write_text("", encoding="utf-8")
            with (
                patch.object(shadow.dream_eval, "select_real_history_packs", fake_select_real_history_packs),
                patch.object(shadow.dream_eval, "run_pack_dream_worker", fake_run_pack_dream_worker),
            ):
                rows = shadow.load_shadow_working_memory_rows(
                    registry_dir=registry_dir,
                    working_memory_path=registry_dir / "missing-working-memory.jsonl",
                    generated_dream_max_packs=1,
                    dream_worker_mode="model_backed",
                    model_config=config,
                    max_samples=2,
                )

        worker_kwargs = seen["worker_kwargs"]
        self.assertEqual(len(rows), 1)
        self.assertIs(worker_kwargs["model_config"], config)
        self.assertEqual(worker_kwargs["max_samples"], 2)
        self.assertFalse(worker_kwargs["no_write"])

if __name__ == "__main__":
    unittest.main()
