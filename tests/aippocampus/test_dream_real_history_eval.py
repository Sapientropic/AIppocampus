from __future__ import annotations

import json
import os
import sys
import unittest
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

import dream_real_history_eval as dream_eval  # noqa: E402
from model_client import DEEPSEEK_PREFIX_CACHE_CONTRACT, ChatClientConfig  # noqa: E402


def source_ref(thread_key: str, message_id: str, line: int) -> dict[str, object]:
    return {
        "thread_key": thread_key,
        "message_id": message_id,
        "line": line,
        "project_label": "AIppocampus",
    }


def fixture_rows() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    job_rows = [
        {
            "kind": "aippocampus_subconscious_job_finding",
            "finding_kind": "question_candidate",
            "fingerprint": "sf_q_continuity",
            "title": "Continuity after compaction",
            "question_text": "How can continuity survive compaction?",
            "question_short": "continuity after compaction",
            "summary": "A question about continuity and compaction.",
            "concepts": ["continuity", "compaction", "source refs"],
            "source_refs": [source_ref("session:a", "msg-a", 10)],
            "confidence": 0.88,
        },
        {
            "kind": "aippocampus_subconscious_job_finding",
            "finding_kind": "frontier_marker",
            "fingerprint": "sf_f_boundary",
            "title": "Source refs across thread changes",
            "summary": "A frontier about source refs surviving thread changes.",
            "boundary_reason": "Resume only after source refs survive the boundary.",
            "frontier_type": "blocked",
            "concepts": ["continuity", "source refs", "boundary"],
            "source_refs": [source_ref("session:b", "msg-b", 20)],
            "confidence": 0.84,
        },
        {
            "kind": "aippocampus_subconscious_job_finding",
            "finding_kind": "question_candidate",
            "fingerprint": "sf_single",
            "title": "Single thread implementation detail",
            "question_text": "How should this CLI flag be named?",
            "concepts": ["cli"],
            "source_refs": [source_ref("session:c", "msg-c", 30)],
            "confidence": 0.9,
        },
    ]
    working_rows = [
        {
            "kind": "aippocampus_working_memory",
            "status": "active",
            "route": "use_with_source",
            "candidate_key": "wm_continuity",
            "candidate_type": "project_memory",
            "title": "Continuity source refs",
            "summary": "Source refs must stay attached during continuity work.",
            "trigger_terms": ["continuity", "source refs"],
            "concepts": ["continuity", "source refs"],
            "source_refs": [source_ref("session:d", "msg-d", 40)],
            "confidence": 0.76,
            "project_label": "AIppocampus",
        }
    ]
    return job_rows, working_rows


class DreamRealHistoryEvalTests(unittest.TestCase):
    def test_dream_model_config_uses_deepseek_thinking_contract_by_default(self) -> None:
        class Args:
            model_route = None
            model = ""
            base_url = ""
            api_key_env = "DEEPSEEK_API_KEY"
            max_tokens = None
            dream_model_timeout = 5.0
            dream_model_temperature = 0.0
            dream_model_thinking = "auto"
            dream_model_reasoning_effort = "auto"

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test"}, clear=False):
            config, route_payload = dream_eval.dream_model_config_from_args(Args())

        self.assertEqual(config.thinking, "enabled")
        self.assertEqual(config.reasoning_effort, "high")
        self.assertEqual(route_payload["provider"], "deepseek")

    def test_dream_model_config_omits_deepseek_fields_for_conservative_route(self) -> None:
        class Args:
            model_route = "local_dream_eval"
            model = ""
            base_url = ""
            api_key_env = "DEEPSEEK_API_KEY"
            max_tokens = None
            dream_model_timeout = 5.0
            dream_model_temperature = 0.0
            dream_model_thinking = "auto"
            dream_model_reasoning_effort = "auto"

        with patch.dict(
            os.environ,
            {
                "AIPPOCAMPUS_OPENAI_COMPAT_ROUTE": "local_dream_eval",
                "AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER": "local-test",
                "AIPPOCAMPUS_OPENAI_COMPAT_MODEL": "local-model",
                "AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL": "http://127.0.0.1:11434/v1",
                "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV": "LOCAL_DREAM_EVAL_KEY",
                "LOCAL_DREAM_EVAL_KEY": "test",
            },
            clear=False,
        ):
            config, route_payload = dream_eval.dream_model_config_from_args(Args())

        self.assertIsNone(config.thinking)
        self.assertIsNone(config.reasoning_effort)
        self.assertEqual(route_payload["provider"], "local-test")

    def test_select_real_history_packs_requires_cross_thread_source_pattern(self) -> None:
        job_rows, working_rows = fixture_rows()

        packs = dream_eval.select_real_history_packs(
            job_rows=job_rows,
            working_memory_rows=working_rows,
            max_packs=3,
        )

        self.assertEqual(len(packs), 1)
        pack = packs[0]
        self.assertEqual(pack["kind"], "aippocampus_dream_input_pack")
        self.assertEqual(pack["status"], "ready_for_dream_worker")
        self.assertEqual(pack["source_ref_audit"]["source_thread_count"], 3)
        self.assertEqual(pack["selection"]["resonance_term"], "continuity")
        self.assertIn("question_candidate", pack["source_seed_kinds"])
        self.assertIn("frontier_marker", pack["source_seed_kinds"])
        self.assertIn("working_memory", pack["source_seed_kinds"])
        self.assertNotIn("cli", pack["themes"])

    def test_small_worker_emits_adjudicated_compensatory_and_amplification_rows(self) -> None:
        job_rows, working_rows = fixture_rows()
        pack = dream_eval.select_real_history_packs(job_rows=job_rows, working_memory_rows=working_rows)[0]

        worker = dream_eval.run_pack_dream_worker(pack)

        self.assertEqual(worker["status"], "candidate_emitted")
        self.assertEqual(
            [finding["dream_function"] for finding in worker["findings"]],
            ["compensatory", "amplification"],
        )
        self.assertEqual(len(worker["adjudicated_findings"]), 2)
        self.assertEqual(
            {finding["review_state"] for finding in worker["adjudicated_findings"]},
            {"agent_adjudicated"},
        )
        self.assertEqual(len(worker["dream_working_memory_rows"]), 2)
        self.assertTrue(
            all(not row["human_review_required"] for row in worker["dream_working_memory_rows"])
        )
        self.assertTrue(
            all(row["candidate_type"] == "dream_hypothesis" for row in worker["dream_working_memory_rows"])
        )

    def test_pack_worker_can_use_model_backed_no_write_path(self) -> None:
        job_rows, working_rows = fixture_rows()
        pack = dream_eval.select_real_history_packs(job_rows=job_rows, working_memory_rows=working_rows)[0]
        calls: list[list[dict[str, str]]] = []

        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            calls.append(messages)
            directive = json.loads(messages[-1]["content"])
            dream_function = directive["dream_function"]
            candidate_kind = "blind_spot" if dream_function == "compensatory" else "cross_thread_resonance"
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": candidate_kind,
                                            "title": f"{dream_function} candidate",
                                            "summary": "A tentative model-backed dream hypothesis over selected source refs.",
                                            "activation_cues": [
                                                f"{dream_function} continuity source bridge",
                                                "selected source-ref dream hypothesis",
                                            ],
                                            "confidence": 0.68,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "The bridge cites selected source handles.",
                                                    "source_ref_ids": ["sr0", "sr1"],
                                                }
                                            ],
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_cache_hit_tokens": 4, "prompt_cache_miss_tokens": 2},
            }

        worker = dream_eval.run_pack_dream_worker(
            pack,
            model_config=ChatClientConfig(
                api_key="test",
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                cache_contract=DEEPSEEK_PREFIX_CACHE_CONTRACT,
            ),
            model_call=fake_model_call,
            no_write=True,
        )

        self.assertEqual(worker["status"], "candidate_emitted")
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            [finding["dream_function"] for finding in worker["findings"]],
            ["compensatory", "amplification"],
        )
        self.assertEqual(
            {finding["adjudication_result"]["status"] for finding in worker["adjudicated_findings"]},
            {"accepted"},
        )
        self.assertEqual(worker["dream_working_memory_rows"], [])
        self.assertTrue(worker["no_write"])
        self.assertEqual(worker["usage"]["prompt_cache_hit_tokens"], 8)
        self.assertEqual(worker["cache"]["kind"], "deepseek_prefix")

    def test_eval_quantifies_recall_and_reflection_lift_against_plain_rows(self) -> None:
        job_rows, working_rows = fixture_rows()

        payload = dream_eval.run_dream_real_history_eval(
            job_rows=job_rows,
            working_memory_rows=working_rows,
            max_packs=2,
            min_packs=1,
        )

        self.assertEqual(payload["kind"], "aippocampus_dream_real_history_eval")
        self.assertEqual(payload["status"], "lift_observed")
        self.assertEqual(payload["claim_level"], "selected_real_history_structural_eval")
        self.assertEqual(payload["metrics"]["pack_count"], 1)
        self.assertEqual(payload["metrics"]["dream_working_memory_count"], 2)
        self.assertGreater(payload["metrics"]["lift"]["source_thread_coverage_delta"], 0)
        self.assertGreater(payload["metrics"]["lift"]["reflection_ready_delta"], 0)
        self.assertGreaterEqual(payload["metrics"]["augmented"]["prompt_hit_rate"], payload["metrics"]["plain"]["prompt_hit_rate"])
        self.assertIn("private_real_history_dream_quality", payload["cannot_claim"])
        self.assertFalse(payload["private_text_emitted"])
        self.assertEqual(payload["packs"][0]["source_ref_audit"]["source_thread_count"], 3)
        self.assertNotIn("source_threads", payload["packs"][0]["source_ref_audit"])
        self.assertNotIn("question_text", payload["packs"][0])
        self.assertEqual(payload["packs"][0]["themes"], ["continuity"])
        self.assertEqual(payload["metrics"]["user_visible"]["claim_level"], "visibility_ablation_harness")
        self.assertIn("real_user_behavior", payload["metrics"]["user_visible"]["cannot_claim"])

    def test_eval_can_run_model_backed_worker_through_visibility_ablation(self) -> None:
        job_rows, working_rows = fixture_rows()
        calls: list[list[dict[str, str]]] = []

        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            calls.append(messages)
            directive = json.loads(messages[-1]["content"])
            dream_function = directive["dream_function"]
            candidate_kind = "blind_spot" if dream_function == "compensatory" else "cross_thread_resonance"
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": candidate_kind,
                                            "title": f"{dream_function} candidate",
                                            "summary": "A tentative model-backed dream hypothesis over selected source refs.",
                                            "activation_cues": [
                                                f"{dream_function} continuity source bridge",
                                                "selected source-ref dream hypothesis",
                                            ],
                                            "confidence": 0.68,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "The bridge cites selected source handles.",
                                                    "source_ref_ids": ["sr0", "sr1"],
                                                }
                                            ],
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_cache_hit_tokens": 4, "prompt_cache_miss_tokens": 2},
            }

        payload = dream_eval.run_dream_real_history_eval(
            job_rows=job_rows,
            working_memory_rows=working_rows,
            max_packs=2,
            min_packs=1,
            dream_worker_mode="model_backed",
            model_config=ChatClientConfig(
                api_key="test",
                model="deepseek-v4-flash",
                base_url="https://example.invalid",
                cache_contract=DEEPSEEK_PREFIX_CACHE_CONTRACT,
            ),
            model_call=fake_model_call,
        )

        self.assertEqual(payload["status"], "lift_observed")
        self.assertEqual(payload["metrics"]["dream_worker_mode"], "model_backed")
        self.assertEqual(len(calls), 2)
        self.assertEqual(payload["metrics"]["dream_working_memory_count"], 2)
        self.assertEqual(payload["metrics"]["user_visible"]["metrics"]["cost_cache"]["model_call_count"], 2)
        self.assertIn(
            "bounded_model_backed_dream_hypotheses_can_be_compared_against_plain_rows",
            payload["can_claim"],
        )

    def test_user_visible_lift_eval_reports_separate_sanitized_metrics(self) -> None:
        job_rows, working_rows = fixture_rows()
        pack = dream_eval.select_real_history_packs(job_rows=job_rows, working_memory_rows=working_rows)[0]
        worker = dream_eval.run_pack_dream_worker(pack)

        payload = dream_eval.evaluate_user_visible_dream_lift(
            packs=[pack],
            dream_working_memory_rows=worker["dream_working_memory_rows"],
            worker_runs=[worker],
            manual_source_review_rows=[
                {
                    "kind": "dream_manual_source_review",
                    "review_status": "supported",
                    "source_refs": [source_ref("session:review", "msg-review", 50)],
                }
            ],
        )
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["kind"], "aippocampus_dream_user_visible_lift_eval")
        self.assertIn("recall_lift", payload["metrics"])
        self.assertIn("reflection_lift", payload["metrics"])
        self.assertIn("unsupported_evidence_suppression", payload["metrics"])
        self.assertIn("source_support_correctness", payload["metrics"])
        self.assertIn("cost_cache", payload["metrics"])
        self.assertEqual(payload["metrics"]["manual_source_review"]["reviewed_count"], 1)
        self.assertEqual(payload["metrics"]["unsupported_evidence_suppression"]["suppression_rate"], 1.0)
        self.assertGreater(payload["metrics"]["reflection_lift"]["augmented_visible_reflection_count"], 0)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("message_id", encoded)
        self.assertNotIn("thread_key", encoded)

    def test_eval_exposes_deepseek_cache_contract_for_future_live_worker(self) -> None:
        job_rows, working_rows = fixture_rows()

        payload = dream_eval.run_dream_real_history_eval(
            job_rows=job_rows,
            working_memory_rows=working_rows,
        )

        contract = payload["live_worker_contract"]
        self.assertEqual(contract["status"], "required_before_live_model_worker")
        self.assertEqual(contract["provider"], "deepseek")
        self.assertEqual(contract["cache_contract"], "deepseek_prefix_v1")
        self.assertEqual(
            contract["message_order"],
            ["stable_dream_worker_contract", "source_pack_payload", "variable_run_directive"],
        )
        self.assertIn("prompt_cache_hit_tokens", contract["usage_fields"])
        self.assertIn("prompt_cache_miss_tokens", contract["usage_fields"])
        self.assertIn("https://api-docs.deepseek.com/zh-cn/guides/kv_cache", contract["official_guide"])
        self.assertIn("do_not_claim_cache_hit_for_deterministic_worker", contract["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
