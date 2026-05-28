from __future__ import annotations

import importlib
import inspect
import json
import sys
import tempfile
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

import prompt_recall_decision as decision  # noqa: E402


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
            return importlib.import_module("prompt_recall_context")
        except ModuleNotFoundError:
            self.fail("prompt_recall_context helper module is missing")

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

        context = context_mod.build_recall_decision_context(
            "NeonMemory route-cue consent gate",
            cwd=self.workspace,
            registry_path=self.registry_path,
            associations_path=associations_path,
            cognitive_map_path=cognitive_map_path,
            concept_graph_path=concept_graph_path,
            working_memory_path=working_memory_path,
            semantic_triggers_path=semantic_triggers_path,
        )

        self.assertEqual(context.cwd_path, self.workspace.resolve())
        self.assertEqual(context.registry_path, self.registry_path.resolve())
        self.assertEqual(context.associations_path, associations_path.resolve())
        self.assertEqual(context.cognitive_map_path, cognitive_map_path.resolve())
        self.assertEqual(context.concept_graph_path, concept_graph_path.resolve())
        self.assertEqual(context.working_memory_path, working_memory_path.resolve())
        self.assertEqual(context.semantic_triggers_path, semantic_triggers_path.resolve())
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
            "cwd": str(self.workspace.resolve()),
            "registry": str(self.registry_path.resolve()),
            "associations": str((self.registry_dir / "associations.json").resolve()),
            "cognitive_map_path": str((self.registry_dir / "cognitive_map.json").resolve()),
            "concept_graph": str((self.registry_dir / "concept_index.sqlite").resolve()),
            "working_memory_path": str((self.registry_dir / "working_memory.jsonl").resolve()),
            "semantic_triggers_path": str(
                (self.registry_dir / "semantic_triggers.jsonl").resolve()
            ),
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

    def test_assess_prompt_keeps_orchestration_below_boundary(self) -> None:
        source = inspect.getsource(decision.assess_prompt)

        self.assertLessEqual(len(source.splitlines()), 255)

    def test_foreground_budget_helpers_are_split_from_decision_orchestration(self) -> None:
        decision_source = (SCRIPTS / "prompt_recall_decision.py").read_text(encoding="utf-8")
        boundary = SCRIPTS / "prompt_recall_budget.py"
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
            "semantic_budget_result",
        ):
            self.assertNotIn(f"def {function_name}(", decision_source)
            self.assertIn(f"def {function_name}(", boundary_source)

    def test_ambient_cache_and_warming_are_split_from_decision_policy(self) -> None:
        decision_source = (SCRIPTS / "prompt_recall_decision.py").read_text(encoding="utf-8")
        boundary = SCRIPTS / "prompt_recall_ambient.py"
        self.assertTrue(boundary.exists())
        boundary_source = boundary.read_text(encoding="utf-8")

        for import_line in (
            "from ambient_recall_cards import",
            "from ambient_thread_cache import",
            "from ambient_warm_scheduler import",
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
