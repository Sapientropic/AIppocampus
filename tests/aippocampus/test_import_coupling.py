from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"


def script_modules() -> dict[str, Path]:
    return {path.stem: path for path in SCRIPTS.glob("*.py")}


def same_dir_import_edges(*, top_level_only: bool = False) -> dict[str, set[str]]:
    modules = script_modules()
    edges = {name: set() for name in modules}
    for name, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        nodes = tree.body if top_level_only else ast.walk(tree)
        for node in nodes:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported = alias.name.split(".", maxsplit=1)[0]
                    if imported in modules:
                        edges[name].add(imported)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported = node.module.split(".", maxsplit=1)[0]
                if imported in modules:
                    edges[name].add(imported)
    return edges


def strongly_connected_components(edges: dict[str, set[str]]) -> list[list[str]]:
    index_by_node: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(node: str) -> None:
        index_by_node[node] = len(index_by_node)
        lowlink[node] = index_by_node[node]
        stack.append(node)
        on_stack.add(node)
        for target in edges[node]:
            if target not in index_by_node:
                visit(target)
                lowlink[node] = min(lowlink[node], lowlink[target])
            elif target in on_stack:
                lowlink[node] = min(lowlink[node], index_by_node[target])
        if lowlink[node] != index_by_node[node]:
            return
        component: list[str] = []
        while True:
            current = stack.pop()
            on_stack.remove(current)
            component.append(current)
            if current == node:
                break
        components.append(sorted(component))

    for node in edges:
        if node not in index_by_node:
            visit(node)
    return components


class ImportCouplingTests(unittest.TestCase):
    def test_scripts_have_no_same_dir_import_cycles(self) -> None:
        edges = same_dir_import_edges()
        cycles = [
            component
            for component in strongly_connected_components(edges)
            if len(component) > 1 or any(node in edges[node] for node in component)
        ]
        self.assertEqual(cycles, [])

    def test_registry_does_not_import_retrieval_at_module_load(self) -> None:
        edges = same_dir_import_edges(top_level_only=True)
        self.assertNotIn("retrieval", edges["registry"])

    def test_registry_storage_is_separate_from_registry_runner(self) -> None:
        store_path = SCRIPTS / "registry_store.py"
        self.assertTrue(store_path.exists())
        edges = same_dir_import_edges(top_level_only=True)

        self.assertIn("registry_store", edges["registry"])
        self.assertNotIn("registry", edges["registry_store"])

        registry_source = (SCRIPTS / "registry.py").read_text(encoding="utf-8")
        store_source = store_path.read_text(encoding="utf-8")
        self.assertNotIn("def load_registry", registry_source)
        self.assertIn("def load_registry", store_source)
        self.assertNotIn("def save_registry", registry_source)
        self.assertIn("def save_registry", store_source)

    def test_prompt_recall_core_stays_small_foreground_gate(self) -> None:
        edges = same_dir_import_edges()
        forbidden = {
            "build_associations",
            "build_cognitive_map",
            "build_concept_graph",
            "memory_candidate_router",
            "semantic_recall_gate",
        }
        self.assertLessEqual(len(edges["prompt_recall_core"]), 4)
        self.assertFalse(forbidden & edges["prompt_recall_core"])

    def test_prompt_recall_cues_are_separate_from_scoring_policy(self) -> None:
        cues_path = SCRIPTS / "prompt_cues.py"
        self.assertTrue(cues_path.exists())
        edges = same_dir_import_edges(top_level_only=True)

        self.assertIn("prompt_cues", edges["prompt_recall_core"])
        self.assertFalse(
            {
                "prompt_recall_core",
                "registry",
                "search_clean_source",
                "semantic_recall_gate",
            }
            & edges["prompt_cues"]
        )

        core_source = (SCRIPTS / "prompt_recall_core.py").read_text(encoding="utf-8")
        cues_source = cues_path.read_text(encoding="utf-8")
        self.assertIn("CUE_COMPAT_EXPORTS", core_source)
        self.assertNotIn("def matched_terms", core_source)
        self.assertIn("def matched_terms", cues_source)
        self.assertNotIn("CODE_SURFACE_CUES = {", core_source)
        self.assertIn("CODE_SURFACE_CUES =", cues_source)

        cue_compat_names = {
            "ASSOCIATIVE_CUES",
            "CONCEPT_EXPANSION_MAX_TERMS",
            "IMPORTANCE_CUES",
            "association_term_is_generic",
            "concept_expansion_terms",
            "expand_query_terms",
            "explicit_recall_terms",
            "is_decision_continuation",
            "matched_terms",
            "semantic_gate_can_request_evidence",
            "semantic_gate_is_memory_cue",
            "semantic_gate_terms",
            "should_run_semantic_gate",
            "working_memory_terms",
        }
        for rel_path in ("prompt_recall_context.py", "prompt_recall_decision.py"):
            tree = ast.parse((SCRIPTS / rel_path).read_text(encoding="utf-8"))
            imported_from_core = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module == "prompt_recall_core"
                for alias in node.names
            }
            self.assertFalse(cue_compat_names & imported_from_core)

    def test_subconscious_jobs_do_not_depend_on_agent_runner(self) -> None:
        runtime_path = SCRIPTS / "subconscious_runtime.py"
        loop_path = SCRIPTS / "subconscious_tool_loop.py"
        self.assertTrue(runtime_path.exists())
        self.assertTrue(loop_path.exists())
        edges = same_dir_import_edges(top_level_only=True)

        self.assertIn("subconscious_runtime", edges["subconscious_agent"])
        self.assertIn("subconscious_runtime", edges["subconscious_jobs"])
        self.assertIn("subconscious_tool_loop", edges["subconscious_agent"])
        self.assertIn("subconscious_tool_loop", edges["subconscious_jobs"])
        self.assertNotIn("subconscious_agent", edges["subconscious_jobs"])
        self.assertFalse({"subconscious_agent", "subconscious_jobs"} & edges["subconscious_runtime"])
        self.assertFalse(
            {"subconscious_agent", "subconscious_jobs"} & edges["subconscious_tool_loop"]
        )

    def test_runtime_scripts_do_not_import_smoke_modules(self) -> None:
        edges = same_dir_import_edges()
        offenders = {
            source: sorted(target for target in targets if target.startswith("smoke_"))
            for source, targets in edges.items()
            if not source.startswith(("benchmark_", "smoke_")) and source != "run_stage_0_5_smoke"
        }
        offenders = {source: targets for source, targets in offenders.items() if targets}

        self.assertEqual(offenders, {})


if __name__ == "__main__":
    unittest.main()
