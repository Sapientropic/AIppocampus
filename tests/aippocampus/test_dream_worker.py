from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

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

from aippocampus_runtime.dream import worker as dream_worker  # noqa: E402
from aippocampus_runtime.model.client import (  # noqa: E402
    DEEPSEEK_PREFIX_CACHE_CONTRACT,
    ChatClientConfig,
)


def source_ref(thread_key: str, message_id: str, line: int) -> dict[str, object]:
    return {
        "thread_key": thread_key,
        "message_id": message_id,
        "line": line,
        "project_label": "AIppocampus",
    }


def ready_pack() -> dict[str, object]:
    refs = [source_ref("session:a", "msg-a", 10), source_ref("session:b", "msg-b", 20)]
    return {
        "schema_version": 1,
        "kind": "aippocampus_dream_input_pack",
        "pack_id": "dream_pack_test",
        "pack_kind": "cross_thread_resonance_pack",
        "status": "ready_for_dream_worker",
        "selection": {"resonance_term": "continuity"},
        "themes": ["continuity", "source refs"],
        "source_seed_ids": ["seed-a", "seed-b"],
        "source_seed_kinds": ["question_link", "working_memory"],
        "source_refs": refs,
        "source_ref_audit": {
            "status": "clean_source_refs_present",
            "source_ref_count": 2,
            "source_thread_count": 2,
        },
        "eligible_dream_functions": ["compensatory", "amplification"],
    }


def config() -> ChatClientConfig:
    return ChatClientConfig(
        api_key="test",
        model="deepseek-v4-flash",
        base_url="https://example.invalid",
        cache_contract=DEEPSEEK_PREFIX_CACHE_CONTRACT,
        timeout=11,
    )


class DreamWorkerTests(unittest.TestCase):
    def test_compensatory_model_worker_orders_messages_and_reports_cache(self) -> None:
        captured: dict[str, object] = {}

        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            captured["messages"] = messages
            captured["config"] = call_config
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": "blind_spot",
                                            "title": "Continuity may be too route-centric",
                                            "summary": "The pack suggests checking whether continuity is over-tied to routing.",
                                            "activation_cues": ["continuity route coupling", "source-ref continuity routing"],
                                            "confidence": 0.72,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "Both source handles point at continuity work.",
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
                "usage": {"prompt_cache_hit_tokens": 30, "prompt_cache_miss_tokens": 10},
            }

        payload = dream_worker.run_model_backed_dream_worker(
            ready_pack(),
            dream_function="compensatory",
            config=config(),
            model_call=fake_model_call,
            no_write=True,
        )

        self.assertEqual(payload["status"], "candidate_emitted")
        self.assertEqual(captured["config"].cache_contract, "deepseek_prefix_v1")
        messages = captured["messages"]
        self.assertEqual([message["role"] for message in messages], ["system", "user", "user"])
        self.assertIn("stable_dream_worker_contract", messages[0]["content"])
        self.assertIn("source_pack_payload", messages[1]["content"])
        self.assertIn("variable_run_directive", messages[2]["content"])
        self.assertEqual(payload["usage"]["prompt_cache_hit_tokens"], 30)
        self.assertEqual(payload["cache"]["kind"], "deepseek_prefix")
        self.assertEqual(payload["cache"]["hit_rate"], 0.75)
        self.assertEqual(payload["findings"][0]["dream_function"], "compensatory")
        self.assertEqual(payload["findings"][0]["candidate_kind"], "blind_spot")
        self.assertEqual(len(payload["findings"][0]["source_refs"]), 2)
        self.assertEqual(payload["adjudicated_findings"][0]["review_state"], "agent_adjudicated")
        self.assertEqual(payload["dream_working_memory_rows"], [])
        self.assertTrue(payload["no_write"])

    def test_model_worker_requires_llm_activation_cues_before_accepting_candidate(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": "blind_spot",
                                            "title": "Continuity may be too route-centric",
                                            "summary": "The pack suggests checking whether continuity is over-tied to routing.",
                                            "confidence": 0.72,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "Both source handles point at continuity work.",
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
                "usage": {},
            }

        payload = dream_worker.run_model_backed_dream_worker(
            ready_pack(),
            dream_function="compensatory",
            config=config(),
            model_call=fake_model_call,
            no_write=False,
        )

        self.assertEqual(payload["status"], "candidate_parked")
        self.assertIn(
            "missing_activation_cues",
            payload["findings"][0]["worker_validation"]["failed_checks"],
        )
        self.assertEqual(payload["dream_working_memory_rows"], [])

    def test_amplification_model_worker_accepts_cross_thread_resonance_candidate(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": "cross_thread_resonance",
                                            "title": "Continuity resonates across selected source handles",
                                            "summary": "The source pack can seed reflection on continuity across threads.",
                                            "activation_cues": ["continuity across source handles", "cross-thread continuity reflection"],
                                            "confidence": 0.69,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "The bridge remains a hypothesis over selected source refs.",
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
                "usage": {"prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 20},
            }

        payload = dream_worker.run_model_backed_dream_worker(
            ready_pack(),
            dream_function="amplification",
            config=config(),
            model_call=fake_model_call,
            no_write=False,
        )

        self.assertEqual(payload["status"], "candidate_emitted")
        self.assertEqual(payload["findings"][0]["candidate_kind"], "cross_thread_resonance")
        self.assertEqual(payload["adjudicated_findings"][0]["adjudication_result"]["status"], "accepted")
        self.assertEqual(len(payload["dream_working_memory_rows"]), 1)
        self.assertIn("reflection_space", payload["dream_working_memory_rows"][0]["downstream_use"])

    def test_prospective_model_worker_emits_hypothesis_not_prediction(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            directive = json.loads(messages[-1]["content"])
            self.assertEqual(directive["dream_function"], "prospective")
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": "emergence_signal",
                                            "title": "Continuity may be forming a source-review need",
                                            "summary": "Treat this as a possible next concern, not a prediction.",
                                            "emergence_signal": "source-review need forming around continuity",
                                            "trajectory_hint": "if the thread continues, source-review wording may matter next",
                                            "counter_evidence": ["no explicit user request yet"],
                                            "activation_cues": ["continuity source review need", "source-review wording around continuity"],
                                            "confidence": 0.64,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "The signal cites selected source handles only.",
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
                "usage": {"prompt_cache_hit_tokens": 3, "prompt_cache_miss_tokens": 1},
            }

        payload = dream_worker.run_model_backed_dream_worker(
            ready_pack(),
            dream_function="prospective",
            config=config(),
            model_call=fake_model_call,
            no_write=False,
        )

        finding = payload["findings"][0]
        self.assertEqual(payload["status"], "candidate_emitted")
        self.assertEqual(finding["dream_function"], "prospective")
        self.assertEqual(finding["candidate_kind"], "emergence_signal")
        self.assertEqual(finding["language_boundary"], "hypothesis_not_prediction")
        self.assertIn("emergence_signal", finding)
        self.assertIn("trajectory_hint", finding)
        self.assertIn("counter_evidence", finding)
        self.assertTrue(finding["expires_at"].endswith("Z"))
        self.assertEqual(payload["adjudicated_findings"][0]["adjudication_result"]["status"], "accepted")
        self.assertEqual(len(payload["dream_working_memory_rows"]), 1)

    def test_active_imagination_sandbox_accepts_audited_bridge_concept_without_writing(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            directive = json.loads(messages[-1]["content"])
            self.assertEqual(directive["dream_function"], "active_imagination")
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": "bridge_concept",
                                            "title": "Continuity as source stewardship",
                                            "summary": "A sandbox bridge concept between continuity and source review.",
                                            "why_this_is_not_fact": "It is a synthesis lens over selected sources, not a source claim.",
                                            "counter_evidence": ["the user may only need implementation details"],
                                            "activation_cues": ["continuity source stewardship", "source review bridge concept"],
                                            "confidence": 0.61,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "Both anchors point to continuity/source-ref work.",
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
                "usage": {},
            }

        payload = dream_worker.run_model_backed_dream_worker(
            ready_pack(),
            dream_function="active_imagination",
            config=config(),
            model_call=fake_model_call,
            no_write=True,
        )

        finding = payload["findings"][0]
        self.assertEqual(payload["status"], "candidate_emitted")
        self.assertEqual(finding["dream_function"], "active_imagination")
        self.assertEqual(finding["truth_boundary"], "dream_synthesized_candidate_not_fact")
        self.assertEqual(finding["sandbox_boundary"], "active_imagination_candidate_not_fact")
        self.assertIn("why_this_is_not_fact", finding)
        self.assertIn("counter_evidence", finding)
        self.assertEqual(payload["adjudicated_findings"][0]["adjudication_result"]["status"], "accepted")
        self.assertEqual(payload["dream_working_memory_rows"], [])

    def test_active_imagination_parks_unsourced_single_source_claimless_and_sensitive_outputs(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": "synthesis_hypothesis",
                                            "title": "Unsourced synthesis",
                                            "summary": "This has no source refs.",
                                            "why_this_is_not_fact": "No source-backed bridge.",
                                            "counter_evidence": ["missing anchors"],
                                            "confidence": 0.5,
                                        },
                                        {
                                            "candidate_kind": "bridge_concept",
                                            "title": "Single-anchor bridge",
                                            "summary": "This cites only one source anchor.",
                                            "why_this_is_not_fact": "Single-source bridges are weak.",
                                            "counter_evidence": ["only one anchor"],
                                            "confidence": 0.55,
                                            "source_ref_ids": ["sr0"],
                                            "bridge_claims": [{"claim": "Only one cited source.", "source_ref_ids": ["sr0"]}],
                                        },
                                        {
                                            "candidate_kind": "question_not_yet_asked",
                                            "title": "Claim without cited bridge",
                                            "summary": "The candidate has source refs, but the bridge claim does not.",
                                            "why_this_is_not_fact": "The bridge has not been source-audited.",
                                            "counter_evidence": ["claim citation missing"],
                                            "confidence": 0.56,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [{"claim": "This claim omits source_ref_ids."}],
                                        },
                                        {
                                            "candidate_kind": "synthesis_hypothesis",
                                            "title": "User personality diagnosis",
                                            "summary": "The user's personality means they secretly prefer this path.",
                                            "why_this_is_not_fact": "Sensitive interpretations need explicit review.",
                                            "counter_evidence": ["no explicit user-facing confirmation"],
                                            "confidence": 0.58,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "Even source-backed sensitive claims must stay parked.",
                                                    "source_ref_ids": ["sr0", "sr1"],
                                                }
                                            ],
                                        },
                                    ]
                                }
                            )
                        }
                    }
                ],
                "usage": {},
            }

        payload = dream_worker.run_model_backed_dream_worker(
            ready_pack(),
            dream_function="active_imagination",
            config=config(),
            model_call=fake_model_call,
            max_samples=4,
        )

        self.assertEqual(payload["status"], "candidate_parked")
        self.assertEqual(payload["counts"]["parked"], 4)
        failed = {
            failure
            for finding in payload["adjudicated_findings"]
            for failure in finding["adjudication_result"]["failed_checks"]
        }
        self.assertIn("source_refs_present", failed)
        worker_failures = {
            failure
            for finding in payload["findings"]
            for failure in finding["worker_validation"]["failed_checks"]
        }
        self.assertIn("insufficient_independent_source_anchors", worker_failures)
        self.assertIn("bridge_claims_missing_source_refs", worker_failures)
        self.assertIn("sensitive_or_profile_claim_requires_human_review", worker_failures)

    def test_malformed_unsourced_and_overconfident_model_outputs_are_parked_or_rejected(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": "blind_spot",
                                            "title": "No cited source",
                                            "summary": "This should park because it has no source refs.",
                                            "confidence": 0.7,
                                        },
                                        {
                                            "candidate_kind": "blind_spot",
                                            "title": "Too certain",
                                            "summary": "This should park because model dream claims must stay tentative.",
                                            "confidence": 0.97,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "A source-backed bridge is still not a fact.",
                                                    "source_ref_ids": ["sr0", "sr1"],
                                                }
                                            ],
                                        },
                                        {
                                            "candidate_kind": "unsupported_kind",
                                            "title": "Unsupported",
                                            "summary": "Unsupported candidate kinds are rejected before adjudication.",
                                            "confidence": 0.6,
                                            "source_ref_ids": ["sr0", "sr1"],
                                        },
                                    ]
                                }
                            )
                        }
                    }
                ],
                "usage": {},
            }

        payload = dream_worker.run_model_backed_dream_worker(
            ready_pack(),
            dream_function="compensatory",
            config=config(),
            model_call=fake_model_call,
            max_samples=3,
        )

        self.assertEqual(payload["status"], "candidate_parked")
        self.assertEqual(payload["counts"]["rejected"], 1)
        self.assertEqual(len(payload["adjudicated_findings"]), 2)
        self.assertEqual(
            {finding["adjudication_result"]["status"] for finding in payload["adjudicated_findings"]},
            {"parked"},
        )
        failed = {
            failure
            for finding in payload["adjudicated_findings"]
            for failure in finding["adjudication_result"]["failed_checks"]
        }
        self.assertIn("source_refs_present", failed)
        self.assertIn("source_ref_audit", failed)

    def test_model_worker_parks_candidate_missing_bridge_claim_reasoning(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": "blind_spot",
                                            "title": "Missing bridge claim",
                                            "summary": "This cites refs but does not explain the bridge.",
                                            "confidence": 0.65,
                                            "source_ref_ids": ["sr0", "sr1"],
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ],
                "usage": {},
            }

        payload = dream_worker.run_model_backed_dream_worker(
            ready_pack(),
            dream_function="compensatory",
            config=config(),
            model_call=fake_model_call,
        )

        self.assertEqual(payload["status"], "candidate_parked")
        self.assertIn(
            "bridge_claims_missing_source_refs",
            payload["findings"][0]["worker_validation"]["failed_checks"],
        )

    def test_prospective_candidate_missing_counter_evidence_is_parked(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": "emergence_signal",
                                            "title": "Unsupported emergence",
                                            "summary": "This should not pass without counter-evidence.",
                                            "emergence_signal": "continuity may become the next concern",
                                            "trajectory_hint": "watch source-review language",
                                            "confidence": 0.62,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "The hint is source-ref backed but still tentative.",
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
                "usage": {},
            }

        payload = dream_worker.run_model_backed_dream_worker(
            ready_pack(),
            dream_function="prospective",
            config=config(),
            model_call=fake_model_call,
        )

        self.assertEqual(payload["status"], "candidate_parked")
        self.assertIn(
            "missing_counter_evidence",
            payload["findings"][0]["worker_validation"]["failed_checks"],
        )

    def test_retrospective_validation_buckets_prospective_findings_without_term_only_evidence(self) -> None:
        supported = {
            "finding_kind": "dream_synthesized",
            "dream_function": "prospective",
            "fingerprint": "pf_supported",
            "expires_at": "2026-06-30T00:00:00Z",
        }
        refuted = {
            "finding_kind": "dream_synthesized",
            "dream_function": "prospective",
            "fingerprint": "pf_refuted",
            "expires_at": "2026-06-30T00:00:00Z",
        }
        stale = {
            "finding_kind": "dream_synthesized",
            "dream_function": "prospective",
            "fingerprint": "pf_stale",
            "expires_at": "2026-05-01T00:00:00Z",
        }
        unknown = {
            "finding_kind": "dream_synthesized",
            "dream_function": "prospective",
            "fingerprint": "pf_unknown",
            "title": "continuity may emerge",
            "expires_at": "2026-06-30T00:00:00Z",
        }
        later_rows = [
            {
                "kind": "prospective_validation_event",
                "target_finding_id": "pf_supported",
                "validation_status": "supported",
                "source_refs": [source_ref("session:support", "msg-support", 30)],
            },
            {
                "kind": "prospective_validation_event",
                "target_finding_id": "pf_refuted",
                "validation_status": "refuted",
                "source_refs": [source_ref("session:refute", "msg-refute", 40)],
            },
            {
                "kind": "prospective_validation_event",
                "target_finding_id": "pf_unknown",
                "validation_status": "supported",
                "source_refs": [],
            },
            {
                "kind": "aippocampus_working_memory",
                "title": "continuity may emerge",
                "concepts": ["continuity"],
                "source_refs": [source_ref("session:similar", "msg-similar", 50)],
            },
        ]

        payload = dream_worker.retrospective_validate_prospective_findings(
            [supported, refuted, stale, unknown],
            later_rows,
            now="2026-05-30T00:00:00Z",
        )

        self.assertEqual(payload["counts"], {"refuted": 1, "stale": 1, "supported": 1, "unknown": 1})
        by_id = {item["finding_id"]: item["validation_status"] for item in payload["items"]}
        self.assertEqual(by_id["pf_supported"], "supported")
        self.assertEqual(by_id["pf_refuted"], "refuted")
        self.assertEqual(by_id["pf_stale"], "stale")
        self.assertEqual(by_id["pf_unknown"], "unknown")
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("message_id", encoded)
        self.assertNotIn("thread_key", encoded)

    def test_public_summary_omits_source_refs_and_message_ids(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            return {
                "choices": [{"message": {"content": json.dumps({"findings": []})}}],
                "usage": {"prompt_cache_hit_tokens": 1, "prompt_cache_miss_tokens": 1},
            }

        payload = dream_worker.run_model_backed_dream_worker(
            ready_pack(),
            dream_function="amplification",
            config=config(),
            model_call=fake_model_call,
        )
        summary = dream_worker.public_worker_summary(payload)
        encoded = json.dumps(summary, ensure_ascii=False)

        self.assertEqual(summary["kind"], "aippocampus_dream_worker_summary")
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("message_id", encoded)
        self.assertNotIn("thread_key", encoded)


if __name__ == "__main__":
    unittest.main()
