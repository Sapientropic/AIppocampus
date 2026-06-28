from __future__ import annotations

import importlib
import inspect
import json
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"

from aippocampus_runtime.recall import (
    prompt_context_render,
    prompt_cues,
    prompt_recall_result_tiers,
    prompt_route_blocks,
)
from aippocampus_runtime.recall import prompt_recall_decision as decision


class PromptRecallDecisionBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.registry_dir = self.root / "registry"
        self.registry_dir.mkdir()
        self.registry_path = self.registry_dir / "threads.json"
        self.registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:boundary",
                            "title": "Boundary thread",
                            "project_label": "BoundaryProject",
                            "keywords": ["NeonMemory"],
                            "paths": {"workspace": str(self.workspace)},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _context_module(self):
        try:
            return importlib.import_module("aippocampus_runtime.recall.prompt_recall_context")
        except ModuleNotFoundError:
            self.fail("prompt_recall_context helper module is missing")

    def _projection_module(self):
        try:
            return importlib.import_module("aippocampus_runtime.recall.prompt_recall_projection")
        except ModuleNotFoundError:
            self.fail("prompt_recall_projection helper module is missing")

    def _result_tiers_module(self):
        try:
            return importlib.import_module("aippocampus_runtime.recall.prompt_recall_result_tiers")
        except ModuleNotFoundError:
            self.fail("prompt_recall_result_tiers helper module is missing")

    def test_cheap_casual_skip_default_keeps_diagnostics_out_of_top_level(self) -> None:
        tiers = self._result_tiers_module()

        result = decision.assess_prompt(
            "今天天气怎么样",
            cwd=self.workspace,
            registry_path=self.registry_path,
        )

        self.assertEqual(result["decision"], "skip")
        self.assertEqual(set(result["result_tiers"]), {"decision"})
        self.assertEqual(
            result["result_tiers"]["decision"]["foreground_lane"],
            "stay_silent",
        )
        self.assertNotIn("hot_path_funnel", result)
        self.assertNotIn("route_delivery_diagnostic", result)
        self.assertNotIn("agent_surface_intent", result)
        self.assertEqual(tiers.result_route_delivery_diagnostic(result), {})
        self.assertEqual(tiers.result_hot_path_funnel(result), {})

    def test_cheap_casual_skip_detail_and_trace_project_moved_fields(self) -> None:
        tiers = self._result_tiers_module()

        detail_result = decision.assess_prompt(
            "今天天气怎么样",
            cwd=self.workspace,
            registry_path=self.registry_path,
            detail="detail",
        )
        trace_result = decision.assess_prompt(
            "今天天气怎么样",
            cwd=self.workspace,
            registry_path=self.registry_path,
            detail="trace",
        )

        self.assertEqual(set(detail_result["result_tiers"]), {"decision", "diagnostics"})
        self.assertIn("route_delivery_diagnostic", detail_result["result_tiers"]["diagnostics"])
        self.assertIn("agent_surface_intent", detail_result["result_tiers"]["diagnostics"])
        self.assertNotIn("hot_path_funnel", detail_result)
        self.assertEqual(tiers.result_hot_path_funnel(detail_result), {})

        self.assertEqual(
            set(trace_result["result_tiers"]),
            {"decision", "diagnostics", "trace"},
        )
        self.assertNotIn("hot_path_funnel", trace_result)
        self.assertNotIn("route_delivery_diagnostic", trace_result)
        self.assertEqual(
            tiers.result_route_delivery_diagnostic(trace_result)["foreground_lane"],
            "stay_silent",
        )
        self.assertEqual(tiers.result_hot_path_funnel(trace_result)["decision"], "skip")

    def test_default_prompt_result_keeps_route_and_trace_out_of_top_level(self) -> None:
        tiers = self._result_tiers_module()

        compact_result = decision.assess_prompt(
            "还记得 NeonMemory 吗？",
            cwd=self.workspace,
            registry_path=self.registry_path,
            use_semantic_gate=False,
            search_budget=0,
        )
        trace_result = decision.assess_prompt(
            "还记得 NeonMemory 吗？",
            cwd=self.workspace,
            registry_path=self.registry_path,
            use_semantic_gate=False,
            search_budget=0,
            detail="trace",
        )

        self.assertEqual(compact_result["decision"], "scent")
        self.assertNotIn("hot_path_funnel", compact_result)
        self.assertNotIn("route_delivery_diagnostic", compact_result)
        self.assertNotIn("agent_surface_intent", compact_result)
        self.assertEqual(set(compact_result["result_tiers"]), {"decision"})
        self.assertEqual(tiers.result_route_delivery_diagnostic(compact_result), {})
        self.assertEqual(tiers.result_hot_path_funnel(compact_result), {})

        self.assertNotIn("hot_path_funnel", trace_result)
        self.assertNotIn("route_delivery_diagnostic", trace_result)
        self.assertNotIn("agent_surface_intent", trace_result)
        self.assertEqual(
            set(trace_result["result_tiers"]),
            {"decision", "diagnostics", "trace"},
        )
        self.assertEqual(
            tiers.result_route_delivery_diagnostic(trace_result)["foreground_profile"],
            "ambient_hot_path",
        )
        self.assertIn("decision", tiers.result_hot_path_funnel(trace_result))

    def test_prompt_cue_catalog_is_split_without_breaking_legacy_imports(self) -> None:
        catalog = importlib.import_module("aippocampus_runtime.recall.prompt_cue_catalog")

        self.assertIs(prompt_cues.ASSOCIATIVE_CUES, catalog.ASSOCIATIVE_CUES)
        self.assertIs(prompt_cues.CODE_SURFACE_CUES, catalog.CODE_SURFACE_CUES)
        self.assertIs(prompt_cues.SEMANTIC_EVIDENCE_TERMS, catalog.SEMANTIC_EVIDENCE_TERMS)
        self.assertTrue(prompt_cues.matched_terms("Use RAG-lite for recall.", {"rag"}))

    def _write_clean_source_registry(self) -> Path:
        clean_dir = self.root / "projection-clean-source"
        clean_dir.mkdir()
        messages_path = clean_dir / "messages.jsonl"
        messages_path.write_text(
            json.dumps(
                {
                    "message_id": "msg-projection",
                    "turn_id": "turn-projection",
                    "source_line": 27,
                    "timestamp": "2026-05-25T19:00:00Z",
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 3,
                    "is_final": True,
                    "text": (
                        "NeonMemory consent gate evidence: keep the consent gate "
                        "beside mutation flow before calling it durable memory."
                    ),
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        registry_path = self.root / "projection-registry" / "threads.json"
        registry_path.parent.mkdir()
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:projection",
                            "title": "NeonMemory consent gate source",
                            "project_label": "BoundaryProject",
                            "workspace_name": "BoundaryProject",
                            "updated_at": "2026-05-25T19:00:00Z",
                            "anchor_titles": ["NeonMemory consent gate"],
                            "keywords": ["NeonMemory", "consent gate"],
                            "summary": "Source-backed note about NeonMemory consent gate.",
                            "paths": {
                                "workspace": str(self.workspace),
                                "clean_source_messages_jsonl": str(messages_path),
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return registry_path

    @staticmethod
    def _projection_snapshot(result: dict) -> dict:
        return {
            "decision": result["decision"],
            "confidence": result["confidence"],
            "candidate_threads": [
                candidate.get("thread_key") for candidate in result.get("candidates") or []
            ],
            "evidence": [
                {
                    "thread_key": item.get("thread_key"),
                    "line": item.get("line"),
                    "source": item.get("source"),
                    "phase": item.get("phase"),
                    "is_final": item.get("is_final"),
                }
                for item in result.get("evidence") or []
            ],
            "semantic_bridge_diagnostic": (
                prompt_recall_result_tiers.result_semantic_bridge_diagnostic(result)
            ),
        }

    def test_context_helper_resolves_explicit_paths_and_loads_inputs(self) -> None:
        context_mod = self._context_module()
        associations_path = self.root / "custom-associations.json"
        associations_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "terms": {
                        "NeonMemory": {
                            "term": "NeonMemory",
                            "status": "verified",
                            "confidence": 0.91,
                            "threads": [{"thread_key": "session:boundary"}],
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cognitive_map_path = self.root / "custom-cognitive-map.json"
        cognitive_map_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "aippocampus_cognitive_map",
                    "status": "active",
                    "routes": [
                        {
                            "route_id": "route-boundary",
                            "route_cues": ["route-cue"],
                            "query_terms": ["NeonMemory"],
                            "thread_keys": ["session:boundary"],
                            "confidence": 0.8,
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        working_memory_path = self.root / "custom-working-memory.jsonl"
        working_memory_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_working_memory",
                    "status": "active",
                    "route": "confirm_when_relevant",
                    "ask_policy": "ask_only_when_current_action_would_depend_on_this_or_sources_conflict",
                    "risk": "medium",
                    "candidate_type": "boundary",
                    "title": "Consent gate",
                    "summary": "Use consent gate when NeonMemory touches mutation flow.",
                    "project_label": "BoundaryProject",
                    "trigger_terms": ["consent gate"],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        concept_graph_path = self.root / "custom-concept.sqlite"
        semantic_triggers_path = self.root / "custom-semantic-triggers.jsonl"
        semantic_triggers_path.write_text("", encoding="utf-8")
        semantic_cues_path = self.root / "custom-semantic-cues.jsonl"
        semantic_cues_path.write_text("", encoding="utf-8")

        context = context_mod.build_recall_decision_context(
            "NeonMemory route-cue consent gate",
            cwd=self.workspace,
            registry_path=self.registry_path,
            associations_path=associations_path,
            cognitive_map_path=cognitive_map_path,
            concept_graph_path=concept_graph_path,
            working_memory_path=working_memory_path,
            semantic_triggers_path=semantic_triggers_path,
            semantic_cues_path=semantic_cues_path,
        )

        self.assertEqual(context.cwd_path, self.workspace.resolve())
        self.assertEqual(context.registry_path, self.registry_path.resolve())
        self.assertEqual(context.associations_path, associations_path.resolve())
        self.assertEqual(context.cognitive_map_path, cognitive_map_path.resolve())
        self.assertEqual(context.concept_graph_path, concept_graph_path.resolve())
        self.assertEqual(context.working_memory_path, working_memory_path.resolve())
        self.assertEqual(context.semantic_triggers_path, semantic_triggers_path.resolve())
        self.assertEqual(context.semantic_cues_path, semantic_cues_path.resolve())
        self.assertEqual(context.registry["threads"][0]["thread_key"], "session:boundary")
        self.assertEqual(context.associations["terms"]["NeonMemory"]["status"], "verified")
        self.assertEqual(context.cognitive_map["routes"][0]["route_id"], "route-boundary")
        self.assertEqual(context.working_memory_rows[0]["title"], "Consent gate")
        self.assertTrue(context.association_matches)
        self.assertTrue(context.cognitive_map_matches)
        self.assertTrue(context.working_memory_matches)

    def test_context_helper_derives_default_asset_paths_from_registry_dir(self) -> None:
        context_mod = self._context_module()

        context = context_mod.build_recall_decision_context(
            "ordinary prompt",
            cwd=self.workspace,
            registry_dir=self.registry_dir,
        )

        self.assertEqual(context.registry_path, self.registry_path.resolve())
        self.assertEqual(
            context.associations_path, (self.registry_dir / "associations.json").resolve()
        )
        self.assertEqual(
            context.cognitive_map_path, (self.registry_dir / "cognitive_map.json").resolve()
        )
        self.assertEqual(
            context.concept_graph_path, (self.registry_dir / "concept_index.sqlite").resolve()
        )
        self.assertEqual(
            context.working_memory_path, (self.registry_dir / "working_memory.jsonl").resolve()
        )
        self.assertEqual(
            context.semantic_triggers_path,
            (self.registry_dir / "semantic_triggers.jsonl").resolve(),
        )
        self.assertEqual(
            context.semantic_cues_path,
            (self.registry_dir / "semantic_cues.jsonl").resolve(),
        )
        self.assertEqual(context.registry["threads"][0]["thread_key"], "session:boundary")
        self.assertEqual(context.association_matches, [])
        self.assertEqual(context.cognitive_map_matches, [])
        self.assertEqual(context.working_memory_matches, [])

    def test_assess_prompt_noise_return_fields_stay_stable(self) -> None:
        result = decision.assess_prompt(
            "Current goal for this thread: status ACTIVE, token budget remaining",
            cwd=self.workspace,
            registry_path=self.registry_path,
            search_budget=2,
        )

        expected_without_elapsed = {
            "decision": "skip",
            "score": 0.0,
            "confidence": "low",
            "result_tiers": {
                "decision": {
                    "outcome": "skip",
                    "score": 0.0,
                    "confidence": "low",
                    "foreground_lane": "stay_silent",
                    "agent_surface_intent": {},
                    "foreground_route_profile": "noise_suppressed",
                }
            },
            "cwd": str(self.workspace.resolve()),
            "registry": str(self.registry_path.resolve()),
            "associations": str((self.registry_dir / "associations.json").resolve()),
            "cognitive_map_path": str((self.registry_dir / "cognitive_map.json").resolve()),
            "concept_graph": str((self.registry_dir / "concept_index.sqlite").resolve()),
            "working_memory_path": str((self.registry_dir / "working_memory.jsonl").resolve()),
            "semantic_triggers_path": str(
                (self.registry_dir / "semantic_triggers.jsonl").resolve()
            ),
            "semantic_cues_path": str((self.registry_dir / "semantic_cues.jsonl").resolve()),
            "ambient_policy_path": str((self.registry_dir / "ambient_recall_policy.jsonl").resolve()),
            "query_terms": [],
            "cognitive_map": [],
            "concept_expansions": [],
            "reasons": ["suppressed system/goal noise"],
            "candidates": [],
            "evidence": [],
            "working_memory": [],
            "semantic_gate": None,
        }

        self.assertEqual(
            [key for key in result if key != "elapsed_ms"], list(expected_without_elapsed)
        )
        self.assertEqual(
            {key: value for key, value in result.items() if key != "elapsed_ms"},
            expected_without_elapsed,
        )
        self.assertIsInstance(result["elapsed_ms"], float)
        self.assertIsNone(
            prompt_recall_result_tiers.result_semantic_bridge_diagnostic(result)
        )

    def test_current_checkout_fact_cue_is_live_source_boundary(self) -> None:
        self.assertTrue(
            prompt_cues.current_checkout_live_fact_intent(
                "请给这个 repo 的 source-backed evidence：测试命令是什么？"
            )
        )
        self.assertFalse(
            prompt_cues.current_checkout_live_fact_intent(
                "上次关于当前 repo 的测试命令结论是什么？"
            )
        )

    def test_current_checkout_fact_blocks_old_history_evidence_upgrade(self) -> None:
        reasons: list[str] = []

        projection = self._projection_module()

        evidence = projection.source_intent_evidence(
            prompt="请给这个 repo 的 source-backed evidence：测试命令是什么？",
            candidates=[
                {
                    "thread_key": "session:old-project",
                    "title": "Old project test command",
                    "score": 0.9,
                }
            ],
            query_terms=["pytest", "测试命令"],
            search_budget=2,
            explicit=[],
            important=[],
            semantic_result={
                "available": True,
                "decision": "evidence",
                "confidence": 0.96,
                "intent": "source_recall",
                "query_aliases": ["pytest test command"],
            },
            natural_evidence=[],
            source_evidence=["source-backed"],
            ambiguous_evidence_request=False,
            start=time.perf_counter(),
            max_elapsed_ms=None,
            reasons=reasons,
        )

        self.assertEqual(evidence, [])
        self.assertIn("current checkout required: read current repo first", reasons)

    def test_explicit_old_source_block_suppresses_scent_and_evidence(self) -> None:
        clean_registry = self._write_clean_source_registry()
        prompt = (
            "Do not cite or reopen the old NeonMemory consent gate source; "
            "write a fresh unrelated packaging note."
        )

        result = decision.assess_prompt(
            prompt,
            cwd=self.workspace,
            registry_path=clean_registry,
            use_semantic_gate=False,
            search_budget=2,
        )

        self.assertTrue(prompt_route_blocks.memory_route_block_intent(prompt))
        self.assertEqual(result["decision"], "skip")
        self.assertEqual(result["evidence"], [])
        self.assertIn(
            "memory route blocked: user forbade old or superseded source route",
            result["reasons"],
        )

    def test_superseded_currentness_block_suppresses_source_evidence(self) -> None:
        clean_registry = self._write_clean_source_registry()
        prompt = (
            "The old NeonMemory consent gate note is superseded; do not "
            "treat it as current source evidence."
        )

        result = decision.assess_prompt(
            prompt,
            cwd=self.workspace,
            registry_path=clean_registry,
            use_semantic_gate=False,
            search_budget=2,
        )

        self.assertTrue(prompt_route_blocks.memory_route_block_intent(prompt))
        self.assertEqual(result["decision"], "skip")
        self.assertEqual(result["evidence"], [])
        self.assertIn(
            "memory route blocked: user forbade old or superseded source route",
            result["reasons"],
        )

    def test_scent_only_source_boundary_still_allows_navigation_scent(self) -> None:
        clean_registry = self._write_clean_source_registry()
        prompt = "还记得 NeonMemory consent gate 吗？先别引用原文。"

        result = decision.assess_prompt(
            prompt,
            cwd=self.workspace,
            registry_path=clean_registry,
            use_semantic_gate=False,
            search_budget=2,
        )

        self.assertFalse(prompt_route_blocks.memory_route_block_intent(prompt))
        self.assertTrue(prompt_cues.negative_evidence_intent(prompt))
        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["evidence"], [])

    def test_old_source_negation_without_fresh_redirect_still_allows_scent(self) -> None:
        clean_registry = self._write_clean_source_registry()
        prompt = "还记得 NeonMemory consent gate 吗？Do not cite the old source."

        result = decision.assess_prompt(
            prompt,
            cwd=self.workspace,
            registry_path=clean_registry,
            use_semantic_gate=False,
            search_budget=2,
        )

        self.assertFalse(prompt_route_blocks.memory_route_block_intent(prompt))
        self.assertTrue(prompt_cues.negative_evidence_intent(prompt))
        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["evidence"], [])

    def test_old_route_block_does_not_suppress_different_source_request(self) -> None:
        clean_registry = self._write_clean_source_registry()
        prompt = (
            "Do not cite or reopen the old Atlas dashboard source; can you cite "
            "source-backed evidence for NeonMemory consent gate?"
        )

        result = decision.assess_prompt(
            prompt,
            cwd=self.workspace,
            registry_path=clean_registry,
            use_semantic_gate=False,
            search_budget=2,
        )

        self.assertFalse(prompt_route_blocks.memory_route_block_intent(prompt))
        self.assertFalse(prompt_cues.negative_evidence_intent(prompt))
        self.assertEqual(result["decision"], "evidence")
        self.assertGreaterEqual(len(result["evidence"]), 1)

    def test_golden_foreground_projection_outputs_cover_skip_scent_evidence_and_bridge(self) -> None:
        clean_registry = self._write_clean_source_registry()

        def semantic_evidence_without_local_bridge(*args, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.93,
                "intent": "source_recall",
                "query_aliases": ["ZetaBridge exact wording"],
                "reasons": ["semantic route only"],
            }

        cases = {
            "noise_skip": decision.assess_prompt(
                "Current goal for this thread: status ACTIVE, token budget remaining",
                cwd=self.workspace,
                registry_path=self.registry_path,
                search_budget=1,
            ),
            "local_scent": decision.assess_prompt(
                "还记得 NeonMemory 吗？",
                cwd=self.workspace,
                registry_path=self.registry_path,
                use_semantic_gate=False,
                search_budget=0,
            ),
            "source_evidence": decision.assess_prompt(
                "请给 source-backed evidence：NeonMemory consent gate 的原话",
                cwd=self.workspace,
                registry_path=clean_registry,
                use_semantic_gate=False,
                search_budget=1,
            ),
            "semantic_bridge_scent": decision.assess_prompt(
                "请找一下 ZetaBridge exact wording 的原话",
                cwd=self.workspace,
                registry_path=self.registry_path,
                semantic_gate_fn=semantic_evidence_without_local_bridge,
                search_budget=1,
            ),
        }

        self.assertEqual(
            {name: self._projection_snapshot(result) for name, result in cases.items()},
            {
                "noise_skip": {
                    "decision": "skip",
                    "confidence": "low",
                    "candidate_threads": [],
                    "evidence": [],
                    "semantic_bridge_diagnostic": None,
                },
                "local_scent": {
                    "decision": "scent",
                    "confidence": "medium",
                    "candidate_threads": ["session:boundary"],
                    "evidence": [],
                    "semantic_bridge_diagnostic": None,
                },
                "source_evidence": {
                    "decision": "evidence",
                    "confidence": "high",
                    "candidate_threads": ["session:projection"],
                    "evidence": [
                        {
                            "thread_key": "session:projection",
                            "line": 27,
                            "source": "clean_source",
                            "phase": "final_answer",
                            "is_final": True,
                        }
                    ],
                    "semantic_bridge_diagnostic": None,
                },
                "semantic_bridge_scent": {
                    "decision": "scent",
                    "confidence": "medium",
                    "candidate_threads": [],
                    "evidence": [],
                    "semantic_bridge_diagnostic": None,
                },
            },
        )
        self.assertIn(
            "semantic evidence did not bridge to source-backed evidence",
            cases["semantic_bridge_scent"]["reasons"],
        )

    def test_route_delivery_diagnostic_marks_cached_semantic_bridge_gap(self) -> None:
        def cached_semantic_evidence_without_local_bridge(*args, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.95,
                "intent": "source_recall",
                "query_aliases": ["private bridge alias"],
                "cached": True,
                "cache_diagnostics": {"lookup": "hit"},
                "reasons": ["semantic cache route only"],
            }

        result = decision.assess_prompt(
            "请找一下 ZetaBridge exact wording 的原话",
            cwd=self.workspace,
            registry_path=self.registry_path,
            semantic_gate_fn=cached_semantic_evidence_without_local_bridge,
            search_budget=1,
            detail="detail",
        )

        diagnostic = self._result_tiers_module().result_route_delivery_diagnostic(result)
        self.assertEqual(result["decision"], "scent")
        self.assertEqual(
            self._result_tiers_module().result_semantic_bridge_diagnostic(result),
            "semantic_evidence_without_source_bridge",
        )
        self.assertEqual(diagnostic["foreground_profile"], "ambient_hot_path")
        self.assertTrue(diagnostic["semantic_gate_cache_hit_but_no_source_bridge"])
        self.assertEqual(diagnostic["semantic_reuse_source"], "exact_semantic_cache")
        self.assertEqual(diagnostic["hot_path_candidates_after_merge"], 0)
        self.assertEqual(diagnostic["final_candidate_count"], 0)
        self.assertFalse(diagnostic["cold_semantic_shadowed"])
        self.assertNotIn("private bridge alias", json.dumps(diagnostic, ensure_ascii=False))

    def test_recall_channels_mark_fast_only_local_candidate(self) -> None:
        result = decision.assess_prompt(
            "还记得 NeonMemory 吗？",
            cwd=self.workspace,
            registry_path=self.registry_path,
            use_semantic_gate=False,
            search_budget=0,
            detail="detail",
        )

        channels = self._result_tiers_module().result_recall_channels(result)

        self.assertEqual(result["decision"], "scent")
        self.assertNotIn("recall_channels", result)
        self.assertEqual(channels["fast"]["status"], "hit")
        self.assertEqual(channels["fast"]["candidate_count"], 1)
        self.assertEqual(channels["fast"]["candidates"][0]["channel"], "fast")
        self.assertEqual(channels["fast"]["candidates"][0]["thread_key"], "session:boundary")
        self.assertIn("registry_overlap", channels["fast"]["candidates"][0]["reason_codes"])
        self.assertEqual(channels["deep"]["status"], "skip")
        self.assertEqual(channels["deep"]["candidate_count"], 0)

    def test_recall_channels_show_deep_timeout_without_blocking_fast_candidate(self) -> None:
        def semantic_timeout(*args, **kwargs) -> dict:
            return {
                "available": False,
                "availability_reason": "semantic_worker_timeout",
                "diagnostic": "semantic_provider_read_timeout",
                "error_buckets": {"read_timeout": 1},
            }

        result = decision.assess_prompt(
            "还记得 NeonMemory 吗？",
            cwd=self.workspace,
            registry_path=self.registry_path,
            semantic_gate_fn=semantic_timeout,
            search_budget=0,
            detail="detail",
        )

        channels = self._result_tiers_module().result_recall_channels(result)

        self.assertEqual(result["decision"], "scent")
        self.assertNotIn("recall_channels", result)
        self.assertEqual(channels["fast"]["status"], "hit")
        self.assertEqual(channels["deep"]["status"], "timeout")
        self.assertIn("semantic_gate_timeout", channels["deep"]["reason_codes"])
        self.assertFalse(channels["deep"]["blocked_fast_channel"])
        self.assertEqual(channels["deep"]["deadline"]["status"], "degraded")

    def test_recall_channels_keep_source_free_deep_route_out_of_evidence(self) -> None:
        def semantic_source_free_evidence(*args, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.94,
                "intent": "source_recall",
                "query_aliases": ["NeonMemory consent gate exact quote"],
                "reasons": ["semantic route only"],
            }

        result = decision.assess_prompt(
            "请找一下 NeonMemory consent gate exact quote 的原话",
            cwd=self.workspace,
            registry_path=self.registry_path,
            semantic_gate_fn=semantic_source_free_evidence,
            search_budget=0,
            detail="detail",
        )

        channels = self._result_tiers_module().result_recall_channels(result)

        self.assertEqual(result["decision"], "scent")
        self.assertNotIn("recall_channels", result)
        self.assertEqual(result["evidence"], [])
        self.assertEqual(channels["fast"]["status"], "hit")
        self.assertEqual(channels["deep"]["status"], "hit")
        self.assertEqual(channels["deep"]["source_free_candidate_count"], 1)
        self.assertFalse(channels["deep"]["source_free_evidence_promotion"])
        self.assertIn("semantic_gate_source_free_route", channels["deep"]["reason_codes"])

    def test_semantic_evidence_with_local_candidate_becomes_source_required_route(self) -> None:
        clean_registry = self._write_clean_source_registry()

        def semantic_evidence_with_local_route(*args, **kwargs) -> dict:
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.93,
                "intent": "source_recall",
                "query_aliases": ["NeonMemory consent gate"],
                "reasons": ["semantic route found local source candidate"],
            }

        result = decision.assess_prompt(
            "还记得那段设计边界吗？",
            cwd=self.workspace,
            registry_path=clean_registry,
            semantic_gate_fn=semantic_evidence_with_local_route,
            search_budget=0,
            max_elapsed_ms=4300,
            detail="detail",
        )

        packet = result["ambient_recall"]["fresh_thread_packet"]
        diagnostic = self._result_tiers_module().result_route_delivery_diagnostic(result)
        context = prompt_context_render.context_for_hook(result)

        self.assertEqual(result["decision"], "scent")
        self.assertEqual(result["evidence"], [])
        self.assertTrue(result["semantic_source_reopen_route"])
        self.assertNotIn("semantic_bridge_diagnostic", result)
        self.assertIsNone(self._result_tiers_module().result_semantic_bridge_diagnostic(result))
        self.assertEqual(packet["support_level"], "source_required")
        self.assertEqual(packet["action_grammar"], "reopenable_route")
        self.assertEqual(packet["reopen_plan"]["status"], "ready")
        self.assertEqual(
            packet["reopen_plan"]["recommended_tool"],
            "reopen_registry_thread_source_index",
        )
        self.assertFalse(packet["reopen_plan"]["manual_query_invention_expected"])
        self.assertTrue(diagnostic["semantic_source_reopen_route"])
        self.assertEqual(diagnostic["semantic_source_reopen_candidate_count"], 1)
        self.assertEqual(
            packet["reopen_plan"]["arguments"],
            {"thread_key": "session:projection"},
        )
        self.assertIn("AIppocampus: prior context may matter.", context)
        self.assertIn(
            "Next: call agent_deepen when a selected route is available; otherwise call agent_recall first.",
            context,
        )
        self.assertNotIn("Source-required recall route", context)
        self.assertNotIn("reopen_registry_thread_source_index", context)
        self.assertNotIn("keep the consent gate beside mutation flow", context)

    def test_route_delivery_diagnostic_distinguishes_semantic_public_labels(self) -> None:
        projection = self._projection_module()
        base_state = {
            "decision": "scent",
            "semantic_gate_reuse": {"source": "cold_model_call"},
            "hot_path_funnel": {"decision": "scent"},
            "candidates": [],
            "evidence": [],
            "use_semantic_gate": True,
            "effective_use_semantic_gate": True,
        }
        cases = [
            (
                "operator_off",
                {
                    **base_state,
                    "semantic_gate_mode": "off",
                    "semantic_result": {
                        "available": False,
                        "availability_reason": "semantic_unavailable",
                        "diagnostic": "semantic_disabled_or_auth_unavailable",
                        "error_buckets": {"auth_error": 1},
                    },
                },
                "semantic_disabled_by_operator",
                False,
            ),
            (
                "missing_auth",
                {
                    **base_state,
                    "semantic_gate_mode": "auto",
                    "semantic_result": {
                        "available": False,
                        "availability_reason": "semantic_unavailable",
                        "diagnostic": "semantic_disabled_or_auth_unavailable",
                        "error_buckets": {"auth_error": 1},
                    },
                },
                "semantic_unavailable_missing_auth",
                False,
            ),
            (
                "provider_timeout",
                {
                    **base_state,
                    "semantic_gate_mode": "auto",
                    "semantic_result": {
                        "available": False,
                        "availability_reason": "semantic_worker_timeout",
                        "diagnostic": "semantic_provider_read_timeout",
                        "error_buckets": {"read_timeout": 1},
                    },
                },
                "semantic_provider_timeout",
                True,
            ),
            (
                "provider_partial_timeout",
                {
                    **base_state,
                    "semantic_gate_mode": "auto",
                    "semantic_result": {
                        "available": True,
                        "decision": "scent",
                        "error_buckets": {"read_timeout": 1},
                        "partial_success": True,
                        "successful_worker_count": 1,
                        "failed_worker_count": 1,
                    },
                },
                "semantic_provider_timeout",
                True,
            ),
            (
                "cold_attempted",
                {
                    **base_state,
                    "semantic_gate_mode": "on",
                    "semantic_result": {
                        "available": True,
                        "decision": "scent",
                        "workers": [{"worker": "gate"}],
                    },
                },
                "cold_semantic_attempted",
                True,
            ),
            (
                "cold_shadowed",
                {
                    **base_state,
                    "semantic_gate_reuse": {"source": "none"},
                    "semantic_gate_mode": "auto",
                    "semantic_result": None,
                    "effective_use_semantic_gate": False,
                },
                "cold_semantic_shadowed",
                False,
            ),
        ]

        for label, state, expected_source, expected_waited in cases:
            with self.subTest(label=label):
                diagnostic = projection.route_delivery_diagnostic(state=state)
                self.assertEqual(diagnostic["semantic_reuse_source"], expected_source)
                self.assertEqual(diagnostic["semantic_waited"], expected_waited)
                self.assertEqual(
                    diagnostic["semantic_partial_failure"],
                    label == "provider_partial_timeout",
                )
                encoded = json.dumps(diagnostic, ensure_ascii=False)
                self.assertNotIn("auth_error", encoded)
                self.assertNotIn("workers", encoded)

    def test_assess_prompt_keeps_orchestration_below_boundary(self) -> None:
        source = inspect.getsource(decision.assess_prompt)

        self.assertLessEqual(len(source.splitlines()), 255)

    def test_projection_stage_is_split_from_decision_orchestration(self) -> None:
        projection = self._projection_module()
        decision_source = (
            SCRIPTS / "aippocampus_runtime" / "recall" / "prompt_recall_decision.py"
        ).read_text(encoding="utf-8")
        boundary = SCRIPTS / "aippocampus_runtime" / "recall" / "prompt_recall_projection.py"
        self.assertTrue(boundary.exists())
        boundary_source = boundary.read_text(encoding="utf-8")

        for function_name in (
            "source_intent_evidence",
            "ambiguous_evidence_request",
            "choose_decision_evidence",
            "semantic_bridge_diagnostic",
        ):
            self.assertTrue(hasattr(projection, function_name))
            self.assertIn(f"def {function_name}(", boundary_source)

        for private_function_name in (
            "_source_intent_evidence",
            "_ambiguous_evidence_request",
            "_choose_decision_evidence",
            "_semantic_bridge_diagnostic",
            "_evidence_lite_continuation",
        ):
            self.assertNotIn(f"def {private_function_name}(", decision_source)

        self.assertNotIn("from aippocampus_runtime.recall.prompt_recall_ambiguity import", decision_source)
        self.assertIn("from aippocampus_runtime.recall.prompt_recall_ambiguity import", boundary_source)
        self.assertNotIn("collect_evidence(", decision_source)
        self.assertIn("collect_evidence(", boundary_source)

    def test_foreground_budget_helpers_are_split_from_decision_orchestration(self) -> None:
        decision_source = (
            SCRIPTS / "aippocampus_runtime" / "recall" / "prompt_recall_decision.py"
        ).read_text(encoding="utf-8")
        boundary = SCRIPTS / "aippocampus_runtime" / "recall" / "prompt_recall_budget.py"
        self.assertTrue(boundary.exists())
        boundary_source = boundary.read_text(encoding="utf-8")

        for symbol in (
            "POST_SEMANTIC_RESERVE_MS",
            "SEMANTIC_MIN_TIMEOUT_SECONDS",
            "PROBE_MIN_REMAINING_MS",
            "EVIDENCE_MIN_REMAINING_MS",
        ):
            self.assertNotIn(f"{symbol} =", decision_source)
            self.assertIn(f"{symbol} =", boundary_source)

        for function_name in (
            "budget_allows",
            "semantic_timeout_for_budget",
            "semantic_worker_timeout_for_deadline",
            "semantic_budget_result",
        ):
            self.assertNotIn(f"def {function_name}(", decision_source)
            self.assertIn(f"def {function_name}(", boundary_source)

    def test_ambient_cache_and_warming_are_split_from_decision_policy(self) -> None:
        decision_source = (
            SCRIPTS / "aippocampus_runtime" / "recall" / "prompt_recall_decision.py"
        ).read_text(encoding="utf-8")
        boundary = SCRIPTS / "aippocampus_runtime" / "recall" / "prompt_recall_ambient.py"
        self.assertTrue(boundary.exists())
        boundary_source = boundary.read_text(encoding="utf-8")

        for import_line in (
            "from aippocampus_runtime.recall.ambient_cards import",
            "from aippocampus_runtime.recall.ambient_cache import",
            "from aippocampus_runtime.warm_ambient.scheduler import",
        ):
            self.assertNotIn(import_line, decision_source)
            self.assertIn(import_line, boundary_source)

        for function_name in (
            "attach_ambient_recall",
            "current_thread_key_from_hook_thread_id",
            "warm_prompt_trace",
        ):
            self.assertNotIn(f"def {function_name}(", decision_source)
            self.assertIn(f"def {function_name}(", boundary_source)

if __name__ == "__main__":
    unittest.main()
