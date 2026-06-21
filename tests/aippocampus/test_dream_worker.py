from __future__ import annotations

import json
import unittest

from aippocampus_runtime.dream import worker as dream_worker
from aippocampus_runtime.dream import worker_validation as dream_worker_validation
from aippocampus_runtime.model.client import (
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

def single_thread_dense_pack() -> dict[str, object]:
    refs = [
        source_ref("session:long", "msg-a", 10),
        source_ref("session:long", "msg-b", 20),
        source_ref("session:long", "msg-c", 30),
    ]
    pack = dict(ready_pack())
    pack.update(
        {
            "pack_id": "dream_pack_single_thread",
            "source_refs": refs,
            "source_ref_audit": {
                "status": "clean_source_refs_present",
                "source_ref_count": 3,
                "source_thread_count": 1,
            },
        }
    )
    return pack

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
        contract = json.loads(messages[0]["content"])
        self.assertEqual(contract["worker_stance"]["role"], "source_body_dream_worker")
        self.assertEqual(contract["worker_stance"]["facing"], "future_foreground_agent")
        self.assertTrue(contract["worker_stance"]["same_source_body_not_same_persistent_self"])
        self.assertEqual(
            contract["worker_stance"]["boundary"],
            "hypothesis_and_navigation_never_source_truth",
        )
        self.assertEqual(payload["usage"]["prompt_cache_hit_tokens"], 30)
        self.assertEqual(payload["cache"]["kind"], "deepseek_prefix")
        self.assertEqual(payload["cache"]["hit_rate"], 0.75)
        self.assertEqual(payload["findings"][0]["dream_function"], "compensatory")
        self.assertEqual(payload["findings"][0]["candidate_kind"], "blind_spot")
        self.assertEqual(len(payload["findings"][0]["source_refs"]), 2)
        self.assertEqual(payload["adjudicated_findings"][0]["review_state"], "agent_adjudicated")
        self.assertEqual(payload["dream_working_memory_rows"], [])
        self.assertTrue(payload["no_write"])

    def test_worker_payload_includes_sanitized_texture_signals(self) -> None:
        pack = {
            **ready_pack(),
            "texture_signals": [
                {
                    "kind": "aippocampus_texture_signal",
                    "texture_id": "tex_worker",
                    "signal_kind": "tool_failure_texture",
                    "signal_detail": "verification_failure",
                    "signal_labels": [
                        "tool_failure",
                        r"E:\private\tool.txt",
                        "Bearer SECRET_TEXTURE_TOKEN",
                    ],
                    "suggested_use": "compensatory_dream_seed",
                    "texture_boundary": "texture_signal_not_source_fact",
                    "truth_boundary": "texture_signal_not_source_fact",
                    "source_refs": [source_ref("session:tex", "msg-texture", 88)],
                    "event_refs": [
                        {"event_id": "event-tex", "status": "failed", "stdout": "raw stdout"}
                    ],
                }
            ],
            "source_texture_consumption": {
                "consumer": "dream",
                "selected_count": 1,
                "signal_kinds": {"tool_failure_texture": 1},
            },
        }

        messages = dream_worker.build_worker_messages(pack, dream_function="compensatory")
        encoded = messages[1]["content"]

        self.assertIn("texture_signals", encoded)
        self.assertIn("tool_failure_texture", encoded)
        self.assertIn("texture_signal_not_source_fact", encoded)
        self.assertNotIn("raw stdout", encoded)
        self.assertNotIn("SECRET_TEXTURE_TOKEN", encoded)
        self.assertNotIn(r"E:\private\tool.txt", encoded)

    def test_macro_perturbation_strategy_tunes_worker_directive_with_caps(self) -> None:
        none_messages = dream_worker.build_worker_messages(
            ready_pack(),
            dream_function="compensatory",
            macro_perturbation_context={
                "band": "none",
                "fanout_hint": {"recommended_candidate_limit": 0},
                "source_refs": [source_ref("private-thread", "msg-secret", 1)],
                "raw_text": "SECRET_PRIVATE_CONTEXT",
            },
        )
        none_directive = json.loads(none_messages[-1]["content"])
        none_strategy = none_directive["macro_perturbation_strategy"]

        self.assertEqual(none_strategy["strategy"], "conservative_check")
        self.assertEqual(none_directive["max_samples"], 1)
        self.assertEqual(none_strategy["authority_level"], "direction_only")
        self.assertFalse(none_strategy["foreground_eligible"])
        self.assertNotIn("SECRET_PRIVATE_CONTEXT", json.dumps(none_directive, ensure_ascii=False))
        self.assertNotIn("private-thread", json.dumps(none_directive, ensure_ascii=False))

        large_messages = dream_worker.build_worker_messages(
            ready_pack(),
            dream_function="amplification",
            macro_perturbation_context={
                "band": "large",
                "fanout_hint": {"recommended_candidate_limit": 8},
            },
        )
        large_directive = json.loads(large_messages[-1]["content"])
        large_strategy = large_directive["macro_perturbation_strategy"]

        self.assertEqual(large_strategy["strategy"], "expanded_bounded")
        self.assertEqual(large_directive["max_samples"], 3)
        self.assertFalse(large_strategy["raw_foreground_fanout_copied"])
        self.assertEqual(large_strategy["recommended_candidate_limit_seen"], 8)

        inversion_messages = dream_worker.build_worker_messages(
            ready_pack(),
            dream_function="compensatory",
            macro_perturbation_context={
                "band": "inversion",
                "route_policy": "reopen_or_conflict_review",
                "conflict_review_required": True,
                "fanout_hint": {"candidate_limit_after_review": 8},
            },
        )
        inversion_directive = json.loads(inversion_messages[-1]["content"])
        inversion_strategy = inversion_directive["macro_perturbation_strategy"]

        self.assertEqual(inversion_strategy["strategy"], "conflict_review_first")
        self.assertTrue(inversion_strategy["requires_conflict_review_before_expand"])
        self.assertEqual(inversion_directive["max_samples"], 1)
        self.assertEqual(inversion_strategy["candidate_limit_after_review"], 3)
        self.assertEqual(
            inversion_strategy["reason_code"],
            "inversion_requires_source_reopen_before_dream_expand",
        )

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

    def test_amplification_worker_accepts_journey_bridge_unblock_probe(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            contract = json.loads(messages[0]["content"])
            directive = json.loads(messages[-1]["content"])
            self.assertIn("journey_bridge_hypothesis", contract["output_schema"]["findings"][0])
            self.assertIn("journey_bridge_hypothesis_rule", directive)
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": "journey_pattern_resonance",
                                            "title": "Two journeys camp at the same safety boundary",
                                            "summary": "Treat the bridge as a source-anchored unblock probe, not a fact.",
                                            "activation_cues": ["rollback boundary before rebuild", "camped journey safety condition"],
                                            "confidence": 0.64,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "Both source handles describe stalled route work around safety boundaries.",
                                                    "source_ref_ids": ["sr0", "sr1"],
                                                }
                                            ],
                                            "journey_bridge_hypothesis": {
                                                "bridge_kind": "shared_unblock_condition",
                                                "source_journey_refs": ["journey:docs-ia", "journey:dream-routing"],
                                                "shared_pattern": "both routes camp before replacing an old structure",
                                                "possible_reason": "each journey may be waiting for a reversible boundary before the next move is safe",
                                                "unblock_condition": "define the rollback, snapshot, or recovery boundary before rebuilding",
                                                "falsification_cues": [
                                                    "one journey moves after unrelated external approval",
                                                    "source shows the blockage was only missing time",
                                                ],
                                                "status": "dream_bridge_not_source_fact",
                                                "source_ref_ids": ["sr0", "sr1"],
                                            },
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
            dream_function="amplification",
            config=config(),
            model_call=fake_model_call,
            no_write=False,
        )

        finding = payload["findings"][0]
        bridge = finding["journey_bridge_hypothesis"]
        row = payload["dream_working_memory_rows"][0]

        self.assertEqual(payload["status"], "candidate_emitted")
        self.assertEqual(finding["worker_validation"]["status"], "passed")
        self.assertEqual(bridge["status"], "dream_bridge_not_source_fact")
        self.assertEqual(bridge["bridge_kind"], "shared_unblock_condition")
        self.assertEqual(bridge["source_journey_refs"], ["journey:docs-ia", "journey:dream-routing"])
        self.assertIn("reversible boundary", bridge["possible_reason"])
        self.assertIn("rollback", bridge["unblock_condition"])
        self.assertEqual(payload["adjudicated_findings"][0]["adjudication_result"]["status"], "accepted")
        self.assertEqual(row["journey_bridge_hypothesis"]["foreground_use"], "journey_unblock_probe_not_evidence")
        self.assertEqual(row["foreground_use"]["journey_bridge_action"], "optional_unblock_probe_on_trigger")

    def test_journey_bridge_requires_two_sided_refs_unblock_and_falsification(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": "journey_pattern_resonance",
                                            "title": "Weak similarity",
                                            "summary": "This only says two routes are similar.",
                                            "activation_cues": ["weak journey similarity"],
                                            "confidence": 0.63,
                                            "source_ref_ids": ["sr0"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "Only one source side is cited.",
                                                    "source_ref_ids": ["sr0"],
                                                }
                                            ],
                                            "journey_bridge_hypothesis": {
                                                "bridge_kind": "frontier_rhyme",
                                                "source_journey_refs": ["journey:one"],
                                                "shared_pattern": "similar",
                                                "possible_reason": "",
                                                "unblock_condition": "",
                                                "falsification_cues": [],
                                                "status": "dream_bridge_not_source_fact",
                                                "source_ref_ids": ["sr0"],
                                            },
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
            dream_function="amplification",
            config=config(),
            model_call=fake_model_call,
            no_write=False,
        )

        failures = payload["findings"][0]["worker_validation"]["failed_checks"]

        self.assertEqual(payload["status"], "candidate_parked")
        self.assertIn("journey_bridge_missing_source_refs_from_both_sides", failures)
        self.assertIn("journey_bridge_missing_source_journey_refs", failures)
        self.assertIn("journey_bridge_shared_pattern_too_weak", failures)
        self.assertIn("journey_bridge_missing_possible_reason", failures)
        self.assertIn("journey_bridge_missing_unblock_condition", failures)
        self.assertIn("journey_bridge_missing_falsification_cues", failures)
        self.assertEqual(payload["dream_working_memory_rows"], [])

    def test_sensitive_journey_bridge_explanation_requires_human_review(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": "journey_pattern_resonance",
                                            "title": "Overpersonalized bridge",
                                            "summary": "The bridge crosses into a profile-like explanation.",
                                            "activation_cues": ["profile-like bridge"],
                                            "confidence": 0.62,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "The candidate has source refs but the explanation is unsafe.",
                                                    "source_ref_ids": ["sr0", "sr1"],
                                                }
                                            ],
                                            "journey_bridge_hypothesis": {
                                                "bridge_kind": "shared_blockage",
                                                "source_journey_refs": ["journey:a", "journey:b"],
                                                "shared_pattern": "both journeys pause before a decisive route change",
                                                "possible_reason": "the user's durable personality secretly sabotages closure",
                                                "unblock_condition": "ask for human review before using this explanation",
                                                "falsification_cues": ["source shows external blockers only"],
                                                "status": "dream_bridge_not_source_fact",
                                                "source_ref_ids": ["sr0", "sr1"],
                                            },
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
            dream_function="amplification",
            config=config(),
            model_call=fake_model_call,
            no_write=False,
        )

        finding = payload["findings"][0]

        self.assertEqual(payload["status"], "candidate_parked")
        self.assertTrue(finding["human_review_required"])
        self.assertIn(
            "sensitive_or_profile_journey_bridge_requires_human_review",
            finding["worker_validation"]["failed_checks"],
        )
        self.assertEqual(payload["dream_working_memory_rows"], [])

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

    def test_active_imagination_accepts_constructive_draft_probe_not_source_fact(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            contract = json.loads(messages[0]["content"])
            self.assertIn("constructive_artifact", contract["output_schema"]["findings"][0])
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": "question_not_yet_asked",
                                            "title": "Compaction loss probe",
                                            "summary": "A source-anchored draft question can test the route without claiming the source already said it.",
                                            "why_this_is_not_fact": "The wording is synthesized from source handles, not quoted from them.",
                                            "counter_evidence": ["the source pack does not yet show a user asking this exact question"],
                                            "activation_cues": ["clean source compaction loss", "source refs missing after compaction"],
                                            "confidence": 0.61,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "Both source handles concern continuity and source refs.",
                                                    "source_ref_ids": ["sr0", "sr1"],
                                                }
                                            ],
                                            "constructive_artifact": {
                                                "artifact_kind": "draft_question",
                                                "draft_text": "If compaction lost the last crucial turn, what source handle would let us notice the loss?",
                                                "draft_origin": "active_imagination over source-ref continuity",
                                                "intended_use": "foreground_probe",
                                                "status": "dream_draft_not_source",
                                                "source_ref_ids": ["sr0", "sr1"],
                                                "counter_evidence": ["not an extractive quote"],
                                                "when_not_to_use": ["exact source claim", "sensitive personal interpretation"],
                                            },
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
            no_write=False,
        )

        finding = payload["findings"][0]
        artifact = finding["constructive_artifact"]
        row = payload["dream_working_memory_rows"][0]

        self.assertEqual(payload["status"], "candidate_emitted")
        self.assertEqual(finding["worker_validation"]["status"], "passed")
        self.assertEqual(artifact["status"], "dream_draft_not_source")
        self.assertEqual(artifact["truth_boundary"], "dream_draft_not_source")
        self.assertTrue(artifact["requires_source_reopen_before_claim"])
        self.assertEqual(artifact["artifact_kind"], "draft_question")
        self.assertIn("crucial turn", artifact["draft_text"])
        self.assertEqual(payload["adjudicated_findings"][0]["adjudication_result"]["status"], "accepted")
        self.assertEqual(row["constructive_artifact"]["status"], "dream_draft_not_source")
        self.assertEqual(row["foreground_use"]["draft_artifact_action"], "optional_probe")
        self.assertEqual(row["truth_boundary"], "adjudicated_dream_hypothesis_not_fact")

    def test_constructive_draft_parks_unsupported_factual_or_sensitive_artifact(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": "question_not_yet_asked",
                                            "title": "Unsupported draft",
                                            "summary": "The draft has no artifact source refs.",
                                            "why_this_is_not_fact": "It is missing artifact refs.",
                                            "counter_evidence": ["missing artifact anchors"],
                                            "activation_cues": ["missing draft refs"],
                                            "confidence": 0.59,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "The base finding is source-backed.",
                                                    "source_ref_ids": ["sr0", "sr1"],
                                                }
                                            ],
                                            "constructive_artifact": {
                                                "artifact_kind": "draft_probe",
                                                "draft_text": "The user secretly wants the agent to decide this for them.",
                                                "intended_use": "foreground_probe",
                                                "status": "dream_draft_not_source",
                                                "source_ref_ids": [],
                                                "counter_evidence": [],
                                                "when_not_to_use": [],
                                            },
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
            no_write=False,
        )

        self.assertEqual(payload["status"], "candidate_parked")
        failures = payload["findings"][0]["worker_validation"]["failed_checks"]
        self.assertIn("constructive_artifact_missing_source_refs", failures)
        self.assertIn("constructive_artifact_missing_counter_evidence", failures)
        self.assertIn("sensitive_or_profile_artifact_requires_human_review", failures)
        self.assertEqual(payload["dream_working_memory_rows"], [])

    def test_prospective_worker_emits_bounded_invitation_with_trigger_and_expiry(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            directive = json.loads(messages[-1]["content"])
            self.assertEqual(directive["dream_function"], "prospective")
            self.assertIn("prospective_invitation_rule", directive)
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": "emergence_signal",
                                            "title": "Blank-starting-point question is forming",
                                            "summary": "Treat this as a possible invitation, not a claim about hidden intent.",
                                            "emergence_signal": "blank starting point theme forming around memory and continuity",
                                            "trajectory_hint": "if the user returns to AGI, selfhood, or blankness, a light question may help",
                                            "counter_evidence": ["the user has not asked to discuss the theme yet"],
                                            "activation_cues": ["AGI blank starting point", "returning to infant imagery"],
                                            "confidence": 0.62,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "The invitation remains bounded to selected source refs.",
                                                    "source_ref_ids": ["sr0", "sr1"],
                                                }
                                            ],
                                            "prospective_invitation": {
                                                "emerging_theme": "AI as subconscious layer and blank starting point",
                                                "trigger_condition": "user next mentions AGI, selfhood, blankness, or returning-to-infant imagery",
                                                "suggested_opening": "Is the blank starting point question live here?",
                                                "invitation_type": "light_question",
                                                "expires_after": "14d",
                                                "annoyance_risk": "low",
                                                "status": "dream_invitation_not_source_fact",
                                                "source_ref_ids": ["sr0", "sr1"],
                                            },
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
            no_write=False,
        )

        finding = payload["findings"][0]
        invitation = finding["prospective_invitation"]
        row = payload["dream_working_memory_rows"][0]

        self.assertEqual(payload["status"], "candidate_emitted")
        self.assertEqual(invitation["status"], "dream_invitation_not_source_fact")
        self.assertEqual(invitation["invitation_type"], "light_question")
        self.assertTrue(invitation["expires_at"].endswith("Z"))
        self.assertTrue(invitation["requires_source_reopen_before_claim"])
        self.assertEqual(row["prospective_invitation"]["status"], "dream_invitation_not_source_fact")
        self.assertIn("AGI blank starting point", row["trigger_terms"])
        self.assertEqual(row["foreground_use"]["prospective_invitation_action"], "optional_question_on_trigger")

    def test_prospective_invitation_requires_trigger_opening_status_and_refs(self) -> None:
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
                                            "title": "Incomplete invitation",
                                            "summary": "This should park because the invitation cannot be delivered safely.",
                                            "emergence_signal": "something forming",
                                            "trajectory_hint": "maybe mention it later",
                                            "counter_evidence": ["not enough signal"],
                                            "activation_cues": ["some vague future theme"],
                                            "confidence": 0.62,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "The base finding cites sources.",
                                                    "source_ref_ids": ["sr0", "sr1"],
                                                }
                                            ],
                                            "prospective_invitation": {
                                                "emerging_theme": "too vague",
                                                "suggested_opening": "",
                                                "invitation_type": "assertion",
                                                "expires_after": "soon",
                                                "annoyance_risk": "low",
                                                "status": "source_fact",
                                                "source_ref_ids": [],
                                            },
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
            no_write=False,
        )

        self.assertEqual(payload["status"], "candidate_parked")
        failures = payload["findings"][0]["worker_validation"]["failed_checks"]
        self.assertIn("prospective_invitation_missing_trigger_condition", failures)
        self.assertIn("prospective_invitation_missing_suggested_opening", failures)
        self.assertIn("prospective_invitation_invalid_type", failures)
        self.assertIn("prospective_invitation_invalid_status", failures)
        self.assertIn("prospective_invitation_missing_source_refs", failures)
        self.assertEqual(payload["dream_working_memory_rows"], [])

    def test_worker_preserves_foreground_useful_stance_fields_without_evidence_upgrade(self) -> None:
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
                                            "title": "Continuity needs a source-body route",
                                            "summary": "The selected source handles can help a future agent recognize the route.",
                                            "foreground_affordance": "Helps the future agent choose a source reopen path before claiming.",
                                            "source_body_shape": "Two source handles circle continuity and source refs.",
                                            "agent_position": "arriving after the thread with source refs but no raw memory",
                                            "atmosphere_tags": ["source-body", "route-before-claim"],
                                            "waking_path": "source_reopen",
                                            "what_not_to_overclaim": "Do not treat this as proof of the user's stable preference.",
                                            "activation_cues": ["source body continuity route", "future agent source reopen"],
                                            "confidence": 0.63,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "The stance is grounded only in selected source handles.",
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
            dream_function="amplification",
            config=config(),
            model_call=fake_model_call,
            no_write=True,
        )

        finding = payload["findings"][0]
        self.assertEqual(payload["status"], "candidate_emitted")
        self.assertEqual(finding["foreground_affordance"], "Helps the future agent choose a source reopen path before claiming.")
        self.assertEqual(finding["source_body_shape"], "Two source handles circle continuity and source refs.")
        self.assertEqual(finding["agent_position"], "arriving after the thread with source refs but no raw memory")
        self.assertEqual(finding["atmosphere_tags"], ["source-body", "route-before-claim"])
        self.assertEqual(finding["waking_path"], "source_reopen")
        self.assertIn("stable preference", finding["what_not_to_overclaim"])
        self.assertEqual(finding["support_level"], "candidate")
        self.assertFalse(finding["foreground_eligible"])
        self.assertEqual(finding["truth_boundary"], "dream_synthesized_candidate_not_fact")
        self.assertEqual(finding["worker_validation"]["status"], "passed")

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

    def test_active_imagination_accepts_source_backed_preference_relationship_bridge(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": "bridge_concept",
                                            "title": "Preference and relationship route context",
                                            "summary": (
                                                "The source pack suggests a preference and relationship-context "
                                                "bridge that should stay a hypothesis."
                                            ),
                                            "why_this_is_not_fact": (
                                                "This is only route context over cited source handles, "
                                                "not a user profile fact."
                                            ),
                                            "counter_evidence": ["the user may revise the preference later"],
                                            "activation_cues": [
                                                "preference route context",
                                                "relationship route context",
                                            ],
                                            "confidence": 0.62,
                                            "source_ref_ids": ["sr0", "sr1"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "The bridge cites both source anchors.",
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
        self.assertEqual(finding["worker_validation"]["status"], "passed")
        self.assertFalse(finding["human_review_required"])
        self.assertNotIn(
            "sensitive_or_profile_claim_requires_human_review",
            finding["worker_validation"]["failed_checks"],
        )

    def test_active_imagination_single_thread_dense_output_becomes_optional_probe(self) -> None:
        def fake_model_call(messages: list[dict[str, str]], call_config: ChatClientConfig) -> dict[str, object]:
            del messages, call_config
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "findings": [
                                        {
                                            "candidate_kind": "bridge_concept",
                                            "title": "Single long thread probe",
                                            "summary": "A source-dense single thread can hold a sandbox continuity probe.",
                                            "why_this_is_not_fact": "It is one-thread synthesis, not independent corroboration.",
                                            "counter_evidence": ["another thread may frame the issue differently"],
                                            "activation_cues": ["single thread continuity probe"],
                                            "confidence": 0.6,
                                            "source_ref_ids": ["sr0", "sr1", "sr2"],
                                            "bridge_claims": [
                                                {
                                                    "claim": "The probe is anchored to several turns in one long thread.",
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
            single_thread_dense_pack(),
            dream_function="active_imagination",
            config=config(),
            model_call=fake_model_call,
            no_write=False,
        )

        finding = payload["findings"][0]
        row = payload["dream_working_memory_rows"][0]

        self.assertEqual(payload["status"], "candidate_emitted")
        self.assertEqual(finding["worker_validation"]["status"], "passed")
        self.assertEqual(finding["probe_authority"]["state"], "single_thread_source_dense_probe")
        self.assertEqual(finding["source_authority"], "source_reopen_required_probe")
        self.assertEqual(row["foreground_use"]["default_action"], "source_reopen_required_probe")
        self.assertEqual(row["foreground_use"]["single_thread_probe_action"], "optional_probe")
        self.assertTrue(row["source_authority"]["requires_source_reopen_before_claim"])

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

        payload = dream_worker_validation.retrospective_validate_prospective_findings(
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

    def test_retrospective_validation_tracks_invitation_adopted_ignored_and_still_unknown(self) -> None:
        invitation = {
            "finding_kind": "dream_synthesized",
            "dream_function": "prospective",
            "fingerprint": "pf_invitation",
            "expires_at": "2026-06-30T00:00:00Z",
            "prospective_invitation": {"status": "dream_invitation_not_source_fact"},
        }
        ignored = {
            **invitation,
            "fingerprint": "pf_ignored",
        }
        still_unknown = {
            **invitation,
            "fingerprint": "pf_still_unknown",
        }
        later_rows = [
            {
                "kind": "prospective_validation_event",
                "target_finding_id": "pf_invitation",
                "validation_status": "adopted",
                "source_refs": [source_ref("session:adopted", "msg-adopted", 30)],
            },
            {
                "kind": "prospective_validation_event",
                "target_finding_id": "pf_ignored",
                "validation_status": "ignored",
                "source_refs": [source_ref("session:ignored", "msg-ignored", 40)],
            },
        ]

        payload = dream_worker_validation.retrospective_validate_prospective_findings(
            [invitation, ignored, still_unknown],
            later_rows,
            now="2026-05-30T00:00:00Z",
        )

        by_id = {item["finding_id"]: item["validation_status"] for item in payload["items"]}
        self.assertEqual(by_id["pf_invitation"], "adopted")
        self.assertEqual(by_id["pf_ignored"], "ignored")
        self.assertEqual(by_id["pf_still_unknown"], "still_unknown")
        self.assertEqual(payload["counts"], {"adopted": 1, "ignored": 1, "still_unknown": 1})

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
