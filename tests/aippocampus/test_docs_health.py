from __future__ import annotations

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

import check_docs_health as docs_health  # noqa: E402


def write_origin_essays(repo: Path) -> None:
    docs = repo / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "未干的地图.md").write_text(
        "生命还能变成什么，而我能不能在变化后仍然是我。",
        encoding="utf-8",
    )
    (docs / "the-unfinished-map.md").write_text(
        "What else can life become, and can I still be myself after the change?",
        encoding="utf-8",
    )


class DocsHealthTests(unittest.TestCase):
    def test_skill_entrypoint_stays_slim_and_linked(self) -> None:
        result = docs_health.check_docs(ROOT)

        self.assertTrue(result["ok"], result["issues"])
        self.assertLessEqual(result["metrics"]["skill_lines"], docs_health.MAX_SKILL_LINES)
        self.assertLessEqual(result["metrics"]["skill_words"], docs_health.MAX_SKILL_WORDS)

    def test_private_thread_anchor_artifact_is_gitignored(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("thread-anchors.md", gitignore)

    def test_public_readiness_docs_and_example_bundle_are_guarded(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.check_repo_docs(repo_root)[0]

        self.assertNotIn("missing public-readiness doc: CONTRIBUTING.md", result)
        self.assertNotIn("missing public-readiness doc: docs/architecture/architecture-overview.md", result)
        self.assertNotIn("missing public-readiness doc: docs/guides/install-guide.md", result)
        self.assertNotIn("missing public-readiness doc: docs/guides/demo-scenarios.md", result)
        self.assertNotIn("missing public-readiness doc: docs/guides/privacy-security-checklist.md", result)
        self.assertNotIn(
            "missing public-readiness doc: "
            "docs/evidence/readiness/public-readiness-verification.md",
            result,
        )
        self.assertNotIn("missing public example memory bundle", result)
        self.assertFalse(any("scope_label_policy" in issue for issue in result), result)
        self.assertFalse(any("missing scope_labels" in issue for issue in result), result)

    def test_research_index_is_complete_for_current_repo(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.check_repo_docs(repo_root)[0]

        self.assertFalse(any("research index" in issue for issue in result), result)

    def test_runtime_script_map_covers_high_risk_current_scripts(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.runtime_script_map_issues(repo_root)

        self.assertEqual(result, [])

    def test_llm_call_contract_covers_current_script_configs(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.llm_call_contract_issues(repo_root)

        self.assertEqual(result, [])

    def test_llm_call_contract_reports_missing_cache_contract_keyword(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            scripts = repo / "skills" / "aippocampus" / "scripts"
            scripts.mkdir(parents=True)
            (scripts / "new_worker.py").write_text(
                "\n".join(
                    [
                        "from model_client import ChatClientConfig",
                        "CONFIG = ChatClientConfig(",
                        "    api_key='x',",
                        "    model='deepseek-v4-flash',",
                        "    base_url='https://api.deepseek.com',",
                        ")",
                    ]
                ),
                encoding="utf-8",
            )

            issues = docs_health.llm_call_contract_issues(repo)

        self.assertIn(
            "LLM ChatClientConfig missing explicit cache_contract: "
            "skills/aippocampus/scripts/new_worker.py:2",
            issues,
        )

    def test_benchmark_evidence_map_covers_current_entrypoints(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.benchmark_evidence_map_issues(repo_root)

        self.assertEqual(result, [])

    def test_public_api_contract_covers_env_matrix_and_python_import_layers(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.public_api_contract_issues(repo_root)

        self.assertEqual(result, [])

    def test_public_api_contract_reports_missing_env_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            guides = repo / "docs" / "guides"
            guides.mkdir(parents=True)
            (guides / "public-api.md").write_text(
                "# Public API\n\n## Environment Variables\n\n`AIPPOCAMPUS_REGISTRY_DIR`\n",
                encoding="utf-8",
            )

            issues = docs_health.public_api_contract_issues(repo)

        self.assertIn("public API doc missing environment configuration matrix", issues)
        self.assertIn("public API doc missing Python import stability layers", issues)

    def test_public_api_contract_reports_missing_mcp_control_plane_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            guides = repo / "docs" / "guides"
            guides.mkdir(parents=True)
            (guides / "public-api.md").write_text(
                "\n".join(
                    [
                        "### Environment Configuration Matrix",
                        "| Variable / family | Group | Audience | Default / precedence | Sensitivity | Stability |",
                        "`AIPPOCAMPUS_PROJECTS_TOKEN`",
                        "### Python Import Stability Layers",
                        "Stable automation surfaces",
                        "Trusted-process runtime helpers",
                        "Internal helper imports",
                        "`aippocampus_runtime.public` is deferred",
                    ]
                ),
                encoding="utf-8",
            )

            issues = docs_health.public_api_contract_issues(repo)

        self.assertIn("public API doc missing MCP control-plane boundary", issues)
        self.assertIn("public API doc missing future MCP write review bar", issues)

    def test_public_api_contract_reports_missing_cli_json_error_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            guides = repo / "docs" / "guides"
            guides.mkdir(parents=True)
            (guides / "public-api.md").write_text(
                "\n".join(
                    [
                        "### MCP Control-Plane Boundary",
                        "Control-plane registration means",
                        "memory-write API",
                        "Future MCP write additions must prove",
                        "privacy, provenance, idempotence",
                        "### Environment Configuration Matrix",
                        "| Variable / family | Group | Audience | Default / precedence | Sensitivity | Stability |",
                        "`AIPPOCAMPUS_PROJECTS_TOKEN`",
                        "### Python Import Stability Layers",
                        "Stable automation surfaces",
                        "Trusted-process runtime helpers",
                        "Internal helper imports",
                        "`aippocampus_runtime.public` is deferred",
                    ]
                ),
                encoding="utf-8",
            )

            issues = docs_health.public_api_contract_issues(repo)

        self.assertIn("public API doc missing CLI JSON error contract", issues)
        self.assertIn("public API doc missing stable CLI error classes", issues)

    def test_public_core_schema_contract_covers_metadata_namespace_rules(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.public_core_schema_contract_issues(repo_root)

        self.assertEqual(result, [])

    def test_public_core_schema_contract_reports_missing_metadata_namespace_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            guides = repo / "docs" / "guides"
            guides.mkdir(parents=True)
            (guides / "public-core-boundary.md").write_text(
                "# Public Core\n\n## Minimal Public Schema Contract\n\nmetadata: {}\n",
                encoding="utf-8",
            )

            issues = docs_health.public_core_schema_contract_issues(repo)

        self.assertIn("public core schema doc missing metadata namespace rules", issues)
        self.assertIn("public core schema doc missing metadata privacy boundary", issues)

    def test_benchmark_evidence_map_reports_missing_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            docs = repo / "docs"
            evidence = docs / "evidence"
            evidence.mkdir(parents=True)
            (docs / "README.md").write_text(
                "# Docs\n\n- benchmark-evidence-map.md\n",
                encoding="utf-8",
            )
            (evidence / "benchmark-evidence-map.md").write_text(
                "\n".join(docs_health.REQUIRED_BENCHMARK_EVIDENCE_MAP_TERMS) + "\n",
                encoding="utf-8",
            )
            benchmark_dir = repo / "benchmarks" / "aippocampus"
            benchmark_dir.mkdir(parents=True)
            (benchmark_dir / "benchmark_new_surface.py").write_text(
                '"""New benchmark."""\n',
                encoding="utf-8",
            )

            issues = docs_health.benchmark_evidence_map_issues(repo)

        self.assertIn(
            "benchmark evidence map missing entrypoint: "
            "benchmarks/aippocampus/benchmark_new_surface.py",
            issues,
        )

    def test_runtime_script_map_reports_missing_required_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            architecture = repo / "docs" / "architecture"
            architecture.mkdir(parents=True)
            (architecture / "runtime-script-map.md").write_text(
                "aippocampus_prompt_hook.py\n", encoding="utf-8"
            )

            issues = docs_health.runtime_script_map_issues(repo)

        self.assertIn("runtime script map missing high-risk script: sync_bundle.py", issues)

    def test_runtime_script_map_reports_missing_navigation_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            architecture = repo / "docs" / "architecture"
            architecture.mkdir(parents=True)
            (architecture / "runtime-script-map.md").write_text(
                "\n".join(docs_health.REQUIRED_RUNTIME_MAP_SCRIPTS) + "\n",
                encoding="utf-8",
            )

            issues = docs_health.runtime_script_map_issues(repo)

        self.assertIn("runtime script map missing high-level runtime flow", issues)
        self.assertIn("runtime script map missing recall decision test map", issues)

    def test_dream_phase1_contract_reports_missing_schema_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            research = repo / "docs" / "research"
            research.mkdir(parents=True)
            (research / "dream-task-design.md").write_text(
                "# Dream Task Design\n\ncompensatory_dream.py\n",
                encoding="utf-8",
            )

            issues = docs_health.dream_phase1_contract_issues(repo)

        self.assertIn("dream task design missing implemented Phase 1 contract", issues)
        self.assertIn("dream task design missing executable contract test pointer", issues)

    def test_research_index_reports_unlinked_top_level_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            research = repo / "docs" / "research"
            research.mkdir(parents=True)
            (research / "README.md").write_text("# Research Notes\n", encoding="utf-8")
            (research / "unlisted.md").write_text("# Unlisted\n", encoding="utf-8")

            issues = docs_health.research_index_issues(repo)

        self.assertIn("research index does not link docs/research/unlisted.md", issues)

    def test_research_index_reports_unindexed_subdirectories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            research = repo / "docs" / "research"
            subdir = research / "topic-pack"
            subdir.mkdir(parents=True)
            (research / "README.md").write_text(
                "# Research Notes\n\n- [Topic Pack](topic-pack/README.md)\n",
                encoding="utf-8",
            )
            (subdir / "case.md").write_text("# Case\n", encoding="utf-8")

            issues = docs_health.research_index_issues(repo)

        self.assertIn(
            "research index subdirectory docs/research/topic-pack must include README.md",
            issues,
        )

    def test_docs_root_reports_unclassified_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            docs = repo / "docs"
            docs.mkdir(parents=True)
            (docs / "loose-status-report.md").write_text("# Loose\n", encoding="utf-8")

            issues, _ = docs_health.check_repo_docs(repo)

        self.assertIn(
            "docs root has unclassified markdown file: docs/loose-status-report.md; "
            "move it under docs/architecture, docs/guides, docs/evidence, "
            "docs/planning, or docs/research",
            issues,
        )

    def test_docs_root_reports_unclassified_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            docs = repo / "docs"
            (docs / "misc").mkdir(parents=True)

            issues, _ = docs_health.check_repo_docs(repo)

        self.assertIn(
            "docs root has unclassified directory: docs/misc; "
            "use docs/architecture, docs/guides, docs/evidence, "
            "docs/planning, docs/research, or docs/archive",
            issues,
        )

    def test_public_doc_command_lint_rejects_default_windows_only_blocks(self) -> None:
        issues = docs_health.public_doc_command_issues(
            "README.md",
            "\n".join(
                [
                    "## First Checks",
                    "",
                    "```powershell",
                    "python tools\\aippocampus\\docs\\check_docs_health.py --json",
                    "```",
                ]
            ),
        )

        self.assertTrue(any("Windows-only command block" in issue for issue in issues), issues)

    def test_public_doc_command_lint_allows_explicit_windows_section(self) -> None:
        issues = docs_health.public_doc_command_issues(
            "README.md",
            "\n".join(
                [
                    "### Windows PowerShell",
                    "",
                    "```powershell",
                    'python "$env:CODEX_HOME\\skills\\aippocampus\\scripts\\aippocampus_health.py"',
                    "```",
                ]
            ),
        )

        self.assertEqual(issues, [])

    def test_repo_markdown_scan_ignores_tmp_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "README.md").write_text("# Test\n", encoding="utf-8")
            (repo / "skills" / "aippocampus").mkdir(parents=True)
            (repo / ".gitignore").write_text(
                ".aippocampus/\naippocampus-registry/\nthread-anchors.md\n",
                encoding="utf-8",
            )
            write_origin_essays(repo)
            (repo / ".tmp").mkdir()
            (repo / ".tmp" / "review-prompt.md").write_text(
                "生命还能变成什么，而我能不能在变化后仍然是我。",
                encoding="utf-8",
            )

            issues, _ = docs_health.check_repo_docs(repo)

        self.assertFalse(any("origin phrase should live only" in issue for issue in issues), issues)

    def test_public_readiness_guard_reports_missing_docs_in_repo_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "README.md").write_text("# Test\n", encoding="utf-8")
            (repo / "skills" / "aippocampus").mkdir(parents=True)
            (repo / ".gitignore").write_text(
                ".aippocampus/\naippocampus-registry/\nthread-anchors.md\n",
                encoding="utf-8",
            )
            write_origin_essays(repo)

            issues, _ = docs_health.check_repo_docs(repo)

        self.assertIn("missing public-readiness doc: CONTRIBUTING.md", issues)
        self.assertIn("missing public-readiness doc: docs/architecture/architecture-overview.md", issues)
        self.assertIn("missing public-readiness doc: docs/guides/install-guide.md", issues)
        self.assertIn("missing public-readiness doc: docs/guides/demo-scenarios.md", issues)
        self.assertIn("missing public-readiness doc: docs/guides/privacy-security-checklist.md", issues)
        self.assertIn(
            "missing public-readiness doc: "
            "docs/evidence/readiness/public-readiness-verification.md",
            issues,
        )
        self.assertIn("missing public example memory bundle", issues)

    def test_public_example_guard_requires_scope_label_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "README.md").write_text("# Test\n", encoding="utf-8")
            (repo / "skills" / "aippocampus").mkdir(parents=True)
            (repo / ".gitignore").write_text(
                ".aippocampus/\naippocampus-registry/\nthread-anchors.md\n",
                encoding="utf-8",
            )
            write_origin_essays(repo)
            for rel_path in docs_health.REQUIRED_PUBLIC_READINESS_DOCS:
                path = repo / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Placeholder\n", encoding="utf-8")
            bundle = repo / "examples" / "public-memory-bundle"
            for rel_path in docs_health.PUBLIC_EXAMPLE_BUNDLE_FILES:
                path = bundle / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.suffix == ".jsonl":
                    path.write_text('{"message_id":"msg_missing_labels"}\n', encoding="utf-8")
                elif rel_path == "bundle_manifest.json":
                    path.write_text('{"raw_rollout_included":false}\n', encoding="utf-8")
                else:
                    path.write_text("{}\n", encoding="utf-8")

            issues, _ = docs_health.check_repo_docs(repo)

        self.assertIn(
            "public example clean-source manifest must document scope_label_policy", issues
        )
        self.assertTrue(any("missing scope_labels" in issue for issue in issues), issues)

    def test_public_example_guard_rejects_extra_files_and_stale_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "README.md").write_text("# Test\n", encoding="utf-8")
            (repo / "skills" / "aippocampus").mkdir(parents=True)
            (repo / ".gitignore").write_text(
                ".aippocampus/\naippocampus-registry/\nthread-anchors.md\n",
                encoding="utf-8",
            )
            write_origin_essays(repo)
            for rel_path in docs_health.REQUIRED_PUBLIC_READINESS_DOCS:
                path = repo / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Placeholder\n", encoding="utf-8")
            bundle = repo / "examples" / "public-memory-bundle"
            for rel_path in docs_health.PUBLIC_EXAMPLE_BUNDLE_FILES:
                path = bundle / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if rel_path == "bundle_manifest.json":
                    path.write_text('{"raw_rollout_included":false}\n', encoding="utf-8")
                elif rel_path == "clean-source/manifest.json":
                    path.write_text('{"scope_label_policy":{"version":"test"}}\n', encoding="utf-8")
                elif rel_path == "clean-source/messages.jsonl":
                    path.write_text(
                        '{"message_id":"msg_1","text":"Should I keep this?","scope_labels":["idea_seed"]}\n',
                        encoding="utf-8",
                    )
                elif rel_path == "clean-source/turns.jsonl":
                    path.write_text(
                        '{"turn_id":"turn_1","message_ids":["msg_1"],"scope_labels":["idea_seed"]}\n',
                        encoding="utf-8",
                    )
                elif path.suffix == ".jsonl":
                    path.write_text("{}\n", encoding="utf-8")
                else:
                    path.write_text("{}\n", encoding="utf-8")
            (bundle / "raw-rollouts").mkdir()
            (bundle / "raw-rollouts" / "private.jsonl").write_text("{}\n", encoding="utf-8")

            issues, _ = docs_health.check_repo_docs(repo)

        self.assertTrue(
            any("unexpected public example bundle file" in issue for issue in issues), issues
        )
        self.assertTrue(
            any("message scope_labels do not match current generator" in issue for issue in issues),
            issues,
        )


if __name__ == "__main__":
    unittest.main()
