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

import architecture_index_guard  # noqa: E402
import check_docs_health as docs_health  # noqa: E402
import classifier_policy_guard  # noqa: E402
import ia_pressure_guard  # noqa: E402


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


def write_development_status_pyproject(
    repo: Path,
    classifier: str = classifier_policy_guard.ALPHA_CLASSIFIER,
    version: str = "0.2.0",
) -> None:
    (repo / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                f'version = "{version}"',
                "classifiers = [",
                f'    "{classifier}",',
                "]",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_classifier_policy(repo: Path) -> None:
    path = repo / "docs" / "evidence" / "readiness" / "classifier-policy.md"
    path.parent.mkdir(parents=True)
    required_terms = "\n".join(
        [
            *classifier_policy_guard.CLASSIFIER_POLICY_REQUIRED_TERMS,
            *classifier_policy_guard.CURRENT_ALPHA_POLICY_TERMS,
        ]
    )
    path.write_text(
        "\n".join(
            [
                "# Alpha/Beta/Stable Classifier Policy",
                "",
                "```text",
                "current_classifier: Development Status :: 3 - Alpha",
                "beta_readiness_decision: not_approved",
                "earliest_beta_classifier_release: 0.3.0 or later",
                "approved_classifier_release: none",
                "decision_date: none",
                "```",
                "",
                required_terms,
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_classifier_release_checklist(repo: Path) -> None:
    path = repo / "docs" / "guides" / "setup" / "release-checklist.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "\n".join(classifier_policy_guard.CLASSIFIER_RELEASE_CHECKLIST_TERMS) + "\n",
        encoding="utf-8",
    )


class DocsHealthTests(unittest.TestCase):
    def test_skill_entrypoint_stays_slim_and_linked(self) -> None:
        result = docs_health.check_docs(ROOT)

        self.assertTrue(result["ok"], result["issues"])
        self.assertLessEqual(result["metrics"]["skill_lines"], docs_health.MAX_SKILL_LINES)
        self.assertLessEqual(result["metrics"]["skill_words"], docs_health.MAX_SKILL_WORDS)

    def test_agent_entrypoints_frame_early_route_first_continuity(self) -> None:
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        agent_context = (REPO_ROOT / "docs" / "agent-context.md").read_text(
            encoding="utf-8"
        )
        coding_lane = (
            REPO_ROOT / "docs" / "guides" / "coding-agent-memory.md"
        ).read_text(encoding="utf-8")
        coding_lane_flat = " ".join(coding_lane.split())

        self.assertIn("source-backed continuity scaffold", skill_text)
        self.assertIn("not innate model memory", skill_text)
        self.assertIn("when an agent knows it has AIppocampus", skill_text)
        self.assertIn("relationship continuity", skill_text)
        self.assertIn("action grammar", skill_text)
        self.assertIn("direction_only", skill_text)
        self.assertIn("reopenable_route", skill_text)
        self.assertIn("bounded_evidence", skill_text)
        self.assertIn("source_open", skill_text)
        self.assertIn("ignore_or_blocked", skill_text)
        self.assertIn("Active Path Packets", skill_text)
        self.assertIn("before broad manual search", " ".join(skill_text.split()))
        self.assertIn("suggested_agent_action", skill_text)
        self.assertIn("not_enough_for_claim", skill_text)
        self.assertIn("## Runtime Posture For Agents", agent_context)
        self.assertIn("cheap orientation", agent_context.lower())
        self.assertIn("explicit source reopen", agent_context.lower())
        self.assertIn("## Agent Runtime Posture", coding_lane)
        self.assertIn("before broad manual search", coding_lane_flat)

    def test_skill_hook_packet_decoder_maps_signals_to_actions(self) -> None:
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        start = skill_text.index("## Hook Packet Decoder")
        end = skill_text.index("## First Moves")
        decoder = skill_text[start:end]
        decoder_flat = " ".join(decoder.split())

        self.assertIn("| Signal | Default action | Do not do |", decoder)
        for phrase in (
            "suggested_agent_action=agent_recall",
            "not_enough_for_claim=true",
            "direction_with_ref",
            "reopenable_route",
            "bounded_evidence",
            "ignore_or_blocked",
            "before broad manual search",
            "deepen",
            "reopen",
        ):
            self.assertIn(phrase, decoder_flat)
        self.assertLessEqual(decoder.count("| `"), 8)
        self.assertNotIn("full packet schema", decoder.lower())

    def test_demo_scenarios_centralize_generic_claim_boundaries(self) -> None:
        demo_text = (REPO_ROOT / "docs" / "guides" / "demo-scenarios.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("docs/evidence/current-claims.md", demo_text)
        self.assertNotIn("Important limits:", demo_text)
        self.assertLessEqual(demo_text.count("Boundary:"), 14)
        for repeated_caveat in (
            "no full private-history coverage",
            "no real-history fresh-thread recall quality",
            "no competitor superiority",
            "no live host behavior",
        ):
            self.assertNotIn(repeated_caveat, demo_text)

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
        self.assertNotIn("missing public-readiness doc: docs/guides/community/privacy-security-checklist.md", result)
        self.assertNotIn(
            "missing public-readiness doc: "
            "docs/evidence/readiness/public-readiness-verification.md",
            result,
        )
        self.assertNotIn("missing public example memory bundle", result)
        self.assertFalse(any("scope_label_policy" in issue for issue in result), result)
        self.assertFalse(any("missing scope_labels" in issue for issue in result), result)

    def test_docs_health_exposes_ia_warnings_without_failing_current_repo(self) -> None:
        result = docs_health.check_docs(ROOT)

        ia = result["diagnostics"]["information_architecture"]
        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(ia["failures"], [])
        self.assertEqual(
            result["metrics"]["information_architecture_warning_count"],
            len(ia["warnings"]),
        )
        self.assertIsInstance(ia["warnings"], list)

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

    def test_architecture_index_covers_current_repo(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.architecture_index_issues(repo_root)

        self.assertEqual(result, [])

    def test_source_kernel_contract_covers_current_repo(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.source_kernel_contract_issues(repo_root)

        self.assertEqual(result, [])

    def test_source_kernel_contract_blocks_generated_findings_as_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            overview = repo / "docs" / "architecture" / "architecture-overview.md"
            overview.parent.mkdir(parents=True)
            overview.write_text(
                "\n".join(
                    [
                        "## Source-Backed Kernel Contract",
                        "ConversationProvider -> CleanSource -> SourceRef/Registry -> "
                        "Rebuildable Index -> RecallCandidate -> RecallDecision -> "
                        "SourceReopen -> BoundedEvidence",
                        "Clean source is the truth substrate.",
                        "Indexes are rebuildable caches, not truth.",
                        "Source reopen is the transition from route/context to "
                        "claim-supporting evidence.",
                        "Authority rings",
                        "Truth substrate",
                        "Rebuildable cache",
                        "Navigation sidecar",
                        "Foreground packet",
                        "Bounded / source-open evidence",
                        "Dream, Journey, subconscious jobs, semantic sidecars, ambient recall, sync,",
                        "vault, Observatory",
                        "Generated findings must not replace clean source.",
                    ]
                ),
                encoding="utf-8",
            )
            (repo / "docs" / "README.md").write_text(
                "source-backed-kernel-contract\n", encoding="utf-8"
            )
            (repo / "docs" / "architecture" / "README.md").write_text(
                "source-backed kernel contract\n", encoding="utf-8"
            )
            readiness = repo / "docs" / "evidence" / "readiness"
            readiness.mkdir(parents=True)
            (readiness / "stage-0-5-readiness.md").write_text(
                "source-backed-kernel-contract\n", encoding="utf-8"
            )
            (readiness / "proof-slice-maturity.md").write_text(
                "source-backed-kernel-contract\n", encoding="utf-8"
            )
            (repo / "docs" / "bad.md").write_text(
                "Generated findings replace clean source.\n", encoding="utf-8"
            )

            issues = docs_health.source_kernel_contract_issues(repo)

        self.assertIn(
            "docs claim generated findings replace clean source; route them as navigation: "
            "docs/bad.md",
            issues,
        )

    def test_architecture_index_reports_missing_doc_and_bad_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            architecture = repo / "docs" / "architecture"
            architecture.mkdir(parents=True)
            (architecture / "contract.md").write_text(
                "# Contract\n\nRole: vague.\n",
                encoding="utf-8",
            )
            topic = architecture / "topic"
            topic.mkdir()
            (topic / "contract.md").write_text(
                "# Topic Contract\n\nRole: current contract.\n",
                encoding="utf-8",
            )
            (architecture / "README.md").write_text(
                "\n".join(
                    [
                        "# Architecture Index",
                        "",
                        "## Topic Layers",
                        "",
                        "| Layer | Use |",
                        "| --- | --- |",
                        "| [missing/](missing/) | Missing topic. |",
                        "",
                        "## Roles",
                    ]
                ),
                encoding="utf-8",
            )

            issues = docs_health.architecture_index_issues(repo)

        self.assertIn(
            "architecture doc has unsupported Role for contract.md: vague; "
            "use one of "
            + str(sorted(architecture_index_guard.ARCHITECTURE_INDEX_ROLES)),
            issues,
        )
        self.assertIn(
            "architecture topic folder missing README: docs/architecture/topic/README.md",
            issues,
        )
        self.assertIn(
            "architecture index missing source-backed kernel contract pointer",
            issues,
        )
        self.assertIn(
            "architecture index missing source-shape spine pointer",
            issues,
        )

    def test_architecture_index_reports_missing_doc_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            architecture = repo / "docs" / "architecture"
            architecture.mkdir(parents=True)
            (architecture / "contract.md").write_text("# Contract\n", encoding="utf-8")
            (architecture / "README.md").write_text(
                "\n".join(
                    [
                        "# Architecture Index",
                        "",
                        "## Current Contracts",
                        "## Implementation Maps",
                        "## Inventories",
                        "## Active Designs",
                        "## Research Seeds",
                        "## Archives",
                        "",
                        "| File | Role | Use |",
                        "| --- | --- | --- |",
                        "| [contract.md](contract.md) | current contract | current truth |",
                    ]
                ),
                encoding="utf-8",
            )

            issues = docs_health.architecture_index_issues(repo)

        self.assertIn(
            "architecture doc missing Role line: docs/architecture/contract.md",
            issues,
        )

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

    def test_product_profile_contract_covers_current_repo(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.product_profile_contract_issues(repo_root)

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

    def test_legacy_alias_inventory_covers_current_repo(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.legacy_alias_inventory_issues(repo_root)

        self.assertEqual(result, [])

    def test_legacy_alias_inventory_reports_unclassified_env_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            alias = "CODEX_MEMORY_" + "NEW_THING"
            inventory = repo / "docs" / "architecture" / "ops" / "legacy-alias-inventory.md"
            inventory.parent.mkdir(parents=True)
            inventory.write_text("# Legacy Alias Inventory\n", encoding="utf-8")
            script = repo / "skills" / "aippocampus" / "scripts" / "new_surface.py"
            script.parent.mkdir(parents=True)
            script.write_text(f'os.environ.get("{alias}")\n', encoding="utf-8")

            issues = docs_health.legacy_alias_inventory_issues(repo)

        self.assertIn(
            "legacy/provider-specific env or path missing inventory classification: "
            f"{alias}; update docs/architecture/ops/legacy-alias-inventory.md",
            issues,
        )

    def test_legacy_alias_inventory_rejects_public_doc_first_choice_setup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            inventory = repo / "docs" / "architecture" / "ops" / "legacy-alias-inventory.md"
            inventory.parent.mkdir(parents=True)
            inventory.write_text("`CODEX_MEMORY_VAULT`\n", encoding="utf-8")
            install_doc = repo / "docs" / "guides" / "install-guide.md"
            install_doc.parent.mkdir(parents=True)
            install_doc.write_text("export CODEX_MEMORY_VAULT=/tmp/private\n", encoding="utf-8")

            issues = docs_health.legacy_alias_inventory_issues(repo)

        self.assertIn(
            "public docs present legacy alias as first-choice setup: "
            "CODEX_MEMORY_VAULT in docs/guides/install-guide.md:1; "
            "prefer canonical AIPPOCAMPUS_* docs and link "
            "docs/architecture/ops/legacy-alias-inventory.md",
            issues,
        )

    def test_legacy_alias_inventory_reports_incomplete_inventory_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            alias = "CODEX_MEMORY_" + "VAULT"
            inventory = repo / "docs" / "architecture" / "ops" / "legacy-alias-inventory.md"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "\n".join(
                    [
                        "# Legacy Alias Inventory",
                        "",
                        "| Alias | Canonical replacement | Why it exists | Classification | Diagnostic behavior | Removal stage |",
                        "| --- | --- | --- | --- | --- | --- |",
                        f"| `{alias}` | `AIPPOCAMPUS_VAULT` | old name |  | Active only when canonical unset. |  |",
                    ]
                ),
                encoding="utf-8",
            )
            script = repo / "skills" / "aippocampus" / "scripts" / "vault.py"
            script.parent.mkdir(parents=True)
            script.write_text(f'os.environ.get("{alias}")\n', encoding="utf-8")

            issues = docs_health.legacy_alias_inventory_issues(repo)

        self.assertIn(
            f"legacy/provider-specific env or path inventory row incomplete: {alias} "
            "(missing classification); update docs/architecture/ops/legacy-alias-inventory.md",
            issues,
        )

    def test_legacy_alias_inventory_reports_misspelled_aippocampus_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            inventory = repo / "docs" / "architecture" / "ops" / "legacy-alias-inventory.md"
            inventory.parent.mkdir(parents=True)
            inventory.write_text("# Legacy Alias Inventory\n", encoding="utf-8")
            script = repo / "skills" / "aippocampus" / "scripts" / "scheduler.py"
            script.parent.mkdir(parents=True)
            script.write_text(
                'os.environ.get("AIIPPOCAMPUS_SUBCONSCIOUS_HOOK")\n',
                encoding="utf-8",
            )

            issues = docs_health.legacy_alias_inventory_issues(repo)

        self.assertIn(
            "legacy/provider-specific env or path missing inventory classification: "
            "AIIPPOCAMPUS_SUBCONSCIOUS_HOOK; "
            "update docs/architecture/ops/legacy-alias-inventory.md",
            issues,
        )

    def test_legacy_alias_inventory_ignores_deepseek_non_env_constants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            alias = "CODEX_MEMORY_" + "NEW_THING"
            inventory = repo / "docs" / "architecture" / "ops" / "legacy-alias-inventory.md"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(
                "\n".join(
                    [
                        "# Legacy Alias Inventory",
                        "",
                        "| Alias | Canonical replacement | Why it exists | Classification | Diagnostic behavior | Removal stage |",
                        "| --- | --- | --- | --- | --- | --- |",
                        (
                            f"| `{alias}` | `AIPPOCAMPUS_NEW_THING` | old name | "
                            "Migration-only fallback | Active when canonical unset. | Remove after migration smoke. |"
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            script = repo / "skills" / "aippocampus" / "scripts" / "new_surface.py"
            script.parent.mkdir(parents=True)
            script.write_text(
                "\n".join(
                    [
                        f'os.environ.get("{alias}")',
                        'DEEPSEEK_PREFIX_CACHE_CONTRACT = "deepseek_prefix_v1"',
                        'DEEPSEEK_KV_CACHE_GUIDE_URL = "https://example.invalid"',
                    ]
                ),
                encoding="utf-8",
            )

            issues = docs_health.legacy_alias_inventory_issues(repo)

        self.assertEqual(issues, [])

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
        self.assertIn("public core schema doc missing runtime clean-source manifest contract", issues)

    def test_public_core_product_profile_boundary_is_guarded(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.public_core_product_profile_issues(repo_root)

        self.assertEqual(result, [])

    def test_public_core_product_profile_reports_missing_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            guides = repo / "docs" / "guides"
            guides.mkdir(parents=True)
            (guides / "public-core-boundary.md").write_text(
                "# Public Core Boundary\n\n"
                "Personal recall is useful, and enterprise governance exists.\n",
                encoding="utf-8",
            )

            issues = docs_health.public_core_product_profile_issues(repo)

        self.assertIn("public core boundary missing Personal/Core default profile", issues)
        self.assertIn("public core boundary missing Power-user optional profile", issues)
        self.assertIn("public core boundary missing Enterprise/high-risk governed profile", issues)
        self.assertIn(
            "public core boundary missing purpose-token opt-in boundary",
            issues,
        )

    def test_python_version_contract_covers_metadata_docs_and_ci(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.python_version_contract_issues(repo_root)

        self.assertEqual(result, [])

    def test_python_version_contract_reports_stale_contributing_floor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "README.md").write_text(
                "AIppocampus supports Python 3.12 and newer. Homebrew Python 3.12\n",
                encoding="utf-8",
            )
            (repo / "CONTRIBUTING.md").write_text(
                "AIppocampus supports Python 3.10 and newer.\n",
                encoding="utf-8",
            )
            guides = repo / "docs" / "guides"
            guides.mkdir(parents=True)
            (guides / "install-guide.md").write_text(
                "Install Python 3.12 or newer. Homebrew Python 3.12\n",
                encoding="utf-8",
            )
            (repo / ".github" / "workflows").mkdir(parents=True)
            (repo / ".github" / "workflows" / "aippocampus-ci.yml").write_text(
                'python-version: "3.12"\n'
                'python-version: "3.13"\n'
                "Python 3.13 quick compatibility tier\n",
                encoding="utf-8",
            )
            (repo / ".github" / "workflows" / "macos-install-smoke.yml").write_text(
                'default: "3.12"\n- "3.12"\n- "3.13"\n',
                encoding="utf-8",
            )
            (repo / "pyproject.toml").write_text(
                "\n".join(
                    [
                        "[project]",
                        'requires-python = ">=3.12"',
                        "classifiers = [",
                        '    "Programming Language :: Python :: 3.12",',
                        '    "Programming Language :: Python :: 3.13",',
                        "]",
                        "",
                        "[tool.ruff]",
                        'target-version = "py312"',
                        "",
                        "[tool.mypy]",
                        'python_version = "3.12"',
                    ]
                ),
                encoding="utf-8",
            )

            issues = docs_health.python_version_contract_issues(repo)

        self.assertIn(
            "CONTRIBUTING.md missing Python support contract term: "
            "public Python support floor is Python 3.12",
            issues,
        )
        self.assertIn(
            "CONTRIBUTING.md missing Python support contract term: "
            "unsupported public targets",
            issues,
        )
        self.assertIn(
            "CONTRIBUTING.md must not advertise Python 3.10/3.11 as supported",
            issues,
        )

    def test_development_status_classifier_contract_covers_current_repo(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.development_status_classifier_issues(repo_root)

        self.assertEqual(result, [])

    def test_development_status_classifier_contract_requires_policy_doc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            write_development_status_pyproject(repo)
            write_classifier_release_checklist(repo)

            issues = docs_health.development_status_classifier_issues(repo)

        self.assertIn(
            "missing classifier policy doc: docs/evidence/readiness/classifier-policy.md",
            issues,
        )

    def test_development_status_classifier_contract_blocks_unapproved_beta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            write_development_status_pyproject(
                repo,
                classifier=classifier_policy_guard.BETA_CLASSIFIER,
                version="0.3.0",
            )
            write_classifier_policy(repo)
            write_classifier_release_checklist(repo)

            issues = docs_health.development_status_classifier_issues(repo)

        self.assertIn(
            "pyproject.toml cannot advertise Development Status :: 4 - Beta without "
            "approved dated Beta readiness decision in "
            "docs/evidence/readiness/classifier-policy.md",
            issues,
        )
        self.assertIn("classifier policy must include a dated Beta readiness decision", issues)
        self.assertIn(
            "classifier policy must approve the exact pyproject release version before "
            "advertising Development Status :: 4 - Beta",
            issues,
        )

    def test_dependency_contract_covers_metadata_docs_and_ci(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.dependency_contract_issues(repo_root)

        self.assertEqual(result, [])

    def test_dependency_contract_reports_floating_dev_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "pyproject.toml").write_text(
                "\n".join(
                    [
                        "[project]",
                        "dependencies = []",
                        "[project.optional-dependencies]",
                        'dev = ["ruff==0.15.12"]',
                        'release = ["build==1.3.0", "check-jsonschema==0.37.2", "twine==6.2.0"]',
                        "benchmark = []",
                        'openai-agents = ["openai-agents>=0.17.4,<1"]',
                        'openai-agents-smoke = ["openai-agents==0.17.4"]',
                        "[build-system]",
                        'requires = ["setuptools==82.0.1"]',
                    ]
                ),
                encoding="utf-8",
            )
            (repo / "README.md").write_text(
                "python -m pip install --upgrade pip ruff mypy coverage\n",
                encoding="utf-8",
            )
            (repo / ".github" / "workflows").mkdir(parents=True)
            (repo / ".github" / "workflows" / "aippocampus-ci.yml").write_text(
                "python -m pip install ruff mypy coverage build\n",
                encoding="utf-8",
            )
            (repo / ".github" / "workflows" / "publish-agent-discovery.yml").write_text(
                "python -m pip install --upgrade build twine check-jsonschema\n",
                encoding="utf-8",
            )

            issues = docs_health.dependency_contract_issues(repo)

        self.assertIn(
            "pyproject.toml optional dependency 'dev' must be "
            "['build==1.3.0', 'coverage==7.14.1', 'mypy==2.1.0', 'ruff==0.15.12']",
            issues,
        )
        self.assertIn("README must not use floating Ruff/mypy/coverage install", issues)
        self.assertIn("aippocampus CI must not use floating dev tool install", issues)
        self.assertIn("publish workflow must not use floating release tool install", issues)

    def test_safe_environment_contract_covers_template_docs_and_plugin_boundary(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        assert repo_root is not None

        result = docs_health.safe_environment_issues(repo_root)

        self.assertEqual(result, [])

    def test_safe_environment_contract_reports_secret_values_and_plugin_env_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".gitignore").write_text(".env\n.env.*\n!.env.example\n", encoding="utf-8")
            (repo / ".env.example").write_text(
                "\n".join(
                    [
                        "AIPPOCAMPUS_HOME=",
                        "AIPPOCAMPUS_REGISTRY_DIR=",
                        "AIPPOCAMPUS_GENERIC_IMPORT_DIR=",
                        "CODEX_HOME=",
                        "AIPPOCAMPUS_OBJECT_STORE_URL=",
                        "AIPPOCAMPUS_OBJECT_STORE_TOKEN=sk-test-leak-abcdefghijklmnopqrstuvwxyz",
                        "AIPPOCAMPUS_OBJECT_ACCESS_KEY_ID=",
                        "AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY=",
                        "AIPPOCAMPUS_OBJECT_SESSION_TOKEN=",
                        "AIPPOCAMPUS_AGE_BIN=",
                        "AIPPOCAMPUS_AGE_KEYGEN_BIN=",
                        "AIPPOCAMPUS_SEMANTIC_GATE=off",
                        "AIPPOCAMPUS_DEEPSEEK_BASE_URL=",
                        "DEEPSEEK_API_KEY=",
                        "AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV=",
                        "LOCAL_OPENAI_COMPAT_API_KEY=",
                        "AIPPOCAMPUS_PROJECTS_TOKEN=",
                        "GH_TOKEN=",
                    ]
                ),
                encoding="utf-8",
            )
            plugin = repo / "plugins" / "aippocampus"
            plugin.mkdir(parents=True)
            (plugin / ".mcp.json").write_text(
                '{"mcpServers":{"aippocampus":{"command":"python","env":{"DEEPSEEK_API_KEY":"x"}}}}',
                encoding="utf-8",
            )

            issues = docs_health.safe_environment_issues(repo)

        self.assertIn(".env.example missing canonical public API env matrix pointer", issues)
        self.assertTrue(any("contains secret-like or local-path value" in issue for issue in issues), issues)
        self.assertIn(
            "plugin MCP manifest must not include public env block; configure aippocampus env privately",
            issues,
        )

    def test_host_hook_boundary_contract_covers_provider_and_claude_code_docs(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        assert repo_root is not None

        result = docs_health.host_hook_boundary_issues(repo_root)

        self.assertEqual(result, [])

    def test_host_hook_boundary_reports_missing_boundary_docs_and_code_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "docs" / "architecture" / "host").mkdir(parents=True)
            (repo / "docs" / "guides" / "setup").mkdir(parents=True)
            (repo / ".claude" / "skills" / "aippocampus").mkdir(parents=True)
            hooks = repo / "skills" / "aippocampus" / "scripts" / "aippocampus_runtime" / "hooks"
            hooks.mkdir(parents=True)
            (repo / "docs" / "architecture" / "host" / "provider-entrypoint-inventory.md").write_text(
                "# Provider Entrypoint Inventory\n", encoding="utf-8"
            )
            (repo / "docs" / "architecture" / "runtime-script-map.md").write_text(
                "# Runtime Script Map\n", encoding="utf-8"
            )
            (repo / "docs" / "guides" / "setup" / "claude-code-mcp.md").write_text(
                "# Claude Code\n", encoding="utf-8"
            )
            (repo / "docs" / "guides" / "public-api.md").write_text(
                "# Public API\n", encoding="utf-8"
            )
            (repo / ".claude" / "skills" / "aippocampus" / "SKILL.md").write_text(
                "# AIppocampus\n", encoding="utf-8"
            )
            for name in ("install_prompt.py", "install_lifecycle.py", "diagnose.py"):
                (hooks / name).write_text("# hook helper\n", encoding="utf-8")

            issues = docs_health.host_hook_boundary_issues(repo)

        self.assertIn("provider inventory missing host integration matrix", issues)
        self.assertIn("runtime script map missing Codex-only hook installer boundary", issues)
        self.assertIn(
            "Claude Code MCP guide missing Claude hook status command",
            issues,
        )
        self.assertIn(
            "Claude Code MCP guide missing no configuration-mutating installer boundary",
            issues,
        )
        self.assertIn(
            "Claude Code project skill missing hook status/dry-run/smoke boundary",
            issues,
        )
        self.assertIn("public API doc missing provider-support-vs-hook-support boundary", issues)
        self.assertIn(
            "hook helper missing host integration metadata: "
            "skills/aippocampus/scripts/aippocampus_runtime/hooks/install_prompt.py",
            issues,
        )

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

    def test_benchmark_evidence_map_requires_current_claims_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            docs = repo / "docs"
            evidence = docs / "evidence"
            evidence.mkdir(parents=True)
            (docs / "README.md").write_text(
                "# Docs\n\n- benchmark-evidence-map.md\n",
                encoding="utf-8",
            )
            old_required_terms = [
                term
                for term in docs_health.REQUIRED_BENCHMARK_EVIDENCE_MAP_TERMS
                if term != "docs/evidence/current-claims.md"
            ]
            (evidence / "benchmark-evidence-map.md").write_text(
                "\n".join(old_required_terms) + "\n",
                encoding="utf-8",
            )

            issues = docs_health.benchmark_evidence_map_issues(repo)

        self.assertIn("benchmark evidence map missing current claims snapshot pointer", issues)

    def test_evidence_index_guard_covers_current_repo(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        self.assertEqual(docs_health.evidence_index_issues(repo_root), [])

    def test_evidence_index_reports_missing_lanes_and_docs_readme_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            docs = repo / "docs"
            evidence = docs / "evidence"
            evidence.mkdir(parents=True)
            (docs / "README.md").write_text("# Docs\n", encoding="utf-8")
            (evidence / "README.md").write_text(
                "# Evidence\n\nOnly benchmark reports.\n",
                encoding="utf-8",
            )

            issues = docs_health.evidence_index_issues(repo)

        self.assertIn("evidence README missing current claim snapshot lane", issues)
        self.assertIn("evidence README missing dated verification ledger lane", issues)
        self.assertIn("docs README missing evidence README pointer", issues)

    def test_reader_path_guard_requires_start_here_entrypoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            docs = repo / "docs"
            docs.mkdir(parents=True)
            (repo / "README.md").write_text("# Project\n", encoding="utf-8")
            (docs / "README.md").write_text("# Docs\n\nstart-here.md\n", encoding="utf-8")
            (docs / "start-here.md").write_text(
                "# Start Here\n\nNo install path yet.\n",
                encoding="utf-8",
            )

            issues = docs_health.reader_path_issues(repo)

        self.assertIn("root README missing docs/start-here.md reader-path pointer", issues)
        self.assertIn("docs README missing first-recall reader path", issues)
        self.assertIn("start-here missing 10-minute public API path", issues)
        self.assertIn("start-here missing first-recall install path", issues)

    def test_current_claims_guard_reports_stale_evidence_wording(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            write_origin_essays(repo)
            readiness = repo / "docs" / "evidence" / "readiness"
            readiness.mkdir(parents=True)
            (readiness / "stage-0-5-readiness.md").write_text(
                "current strict sidecars at 2 threads/5 rows/5 timeline turns\n",
                encoding="utf-8",
            )
            (readiness / "public-readiness-verification.md").write_text(
                "the current strict re-materialized sidecars intentionally "
                "contain only 5 rows across 2 real clean-source threads\n",
                encoding="utf-8",
            )
            guides = repo / "docs" / "guides"
            guides.mkdir(parents=True)
            (guides / "demo-scenarios.md").write_text(
                "Cannot claim: all personal life-wide labels are complete in "
                "the current runtime.\n",
                encoding="utf-8",
            )

            issues, _ = docs_health.check_repo_docs(repo)

        self.assertIn("missing current claims snapshot: docs/evidence/current-claims.md", issues)
        self.assertIn(
            "stage readiness has stale semantic sidecar current wording: "
            "current strict sidecars at 2 threads/5 rows",
            issues,
        )
        self.assertIn(
            "public readiness ledger has stale semantic sidecar current wording: "
            "current strict re-materialized sidecars intentionally contain only 5 rows across 2",
            issues,
        )
        self.assertIn("demo scenarios missing current claims snapshot pointer", issues)

    def test_current_claims_guard_requires_actionable_owner_and_retirement(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            evidence = repo / "docs" / "evidence"
            evidence.mkdir(parents=True)
            (evidence / "current-claims.md").write_text(
                "\n".join(
                    [
                        "# Current Evidence Claims",
                        "## Current Claim Snapshot",
                        (
                            "metric_id run_date source_report claim_level cohort supersedes "
                            "supports material_limits cannot_claim"
                        ),
                        "semantic_sidecar.aggregate_materialized_rows",
                        "semantic_sidecar.strict_survival_snapshot",
                        "semantic_sidecar.source_review_green_gate",
                        "semantic_sidecar.source_review_diagnostic",
                        "track_b.private_semantic_sidecar_required",
                        "fts5.real_history_recall_2026_05_29",
                        "demo_scenarios.claim_boundaries",
                        "## Claim-Boundary Owner And Retirement Ledger",
                        "| Caveat | Category | Owner issue | Retirement condition | Next review |",
                        "| --- | --- | --- | --- | --- |",
                        "| Claude Code hooks | actionable | - | - | before Beta readiness update |",
                    ]
                ),
                encoding="utf-8",
            )

            issues = docs_health.current_claims_snapshot_issues(repo)

        self.assertIn(
            "current claims actionable cannot-claim missing owner issue: Claude Code hooks",
            issues,
        )
        self.assertIn(
            "current claims actionable cannot-claim missing retirement condition: Claude Code hooks",
            issues,
        )

    def test_proof_slice_maturity_board_guard_covers_status_vocabulary(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        assert repo_root is not None

        self.assertEqual(docs_health.proof_slice_maturity_board_issues(repo_root), [])

    def test_proof_slice_maturity_board_reports_missing_terms_and_pointers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            write_origin_essays(repo)
            readiness = repo / "docs" / "evidence" / "readiness"
            readiness.mkdir(parents=True)
            (readiness / "proof-slice-maturity.md").write_text(
                "# Proof Slice Maturity\n\n"
                "`design_only`\n"
                "`deterministic_smoke`\n",
                encoding="utf-8",
            )
            (repo / "docs" / "README.md").write_text("# Docs\n", encoding="utf-8")
            (readiness / "stage-0-5-readiness.md").write_text(
                "# Stage readiness\n",
                encoding="utf-8",
            )

            issues = docs_health.proof_slice_maturity_board_issues(repo)

        self.assertIn(
            "proof-slice maturity board missing public_safe_fixture status",
            issues,
        )
        self.assertIn(
            "proof-slice maturity board missing important-limits column",
            issues,
        )
        self.assertIn(
            "docs README missing proof-slice maturity board pointer",
            issues,
        )
        self.assertIn(
            "stage readiness missing proof-slice maturity board pointer",
            issues,
        )

    def test_proof_slice_maturity_board_guard_requires_cognitive_layer_gate(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        assert repo_root is not None

        self.assertEqual(docs_health.proof_slice_maturity_board_issues(repo_root), [])

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            write_origin_essays(repo)
            readiness = repo / "docs" / "evidence" / "readiness"
            readiness.mkdir(parents=True)
            (readiness / "proof-slice-maturity.md").write_text(
                "# Proof Slice Maturity\n\n"
                "`design_only`\n"
                "`deterministic_smoke`\n"
                "`public_safe_fixture`\n"
                "`second_user`\n"
                "`release_claimable`\n"
                "last_checked\n"
                "Cannot claim\n"
                "Owner / evidence\n",
                encoding="utf-8",
            )
            (repo / "docs" / "README.md").write_text(
                "proof-slice-maturity.md\n",
                encoding="utf-8",
            )
            (readiness / "stage-0-5-readiness.md").write_text(
                "proof-slice-maturity.md\n",
                encoding="utf-8",
            )

            issues = docs_health.proof_slice_maturity_board_issues(repo)

        self.assertIn(
            "proof-slice maturity board missing cognitive layer graduation ladder",
            issues,
        )
        self.assertIn(
            "proof-slice maturity board missing flagship cognitive mechanism gate",
            issues,
        )

    def test_public_docs_cognitive_mechanism_guard_flags_premature_default_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "docs" / "guides").mkdir(parents=True)
            (repo / "README.md").write_text(
                "AIppocampus implements Awake SWR as default behavior.\n",
                encoding="utf-8",
            )
            (repo / "docs" / "README.md").write_text("# Docs\n", encoding="utf-8")
            (repo / "docs" / "guides" / "public-api.md").write_text(
                "No premature claim here.\n",
                encoding="utf-8",
            )

            issues = docs_health.cognitive_mechanism_public_claim_issues(repo)

        self.assertIn(
            "README.md has premature cognitive mechanism claim: implements Awake SWR",
            issues,
        )

    def test_benchmark_evidence_map_requires_hippocampal_private_annotation_protocol(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            docs = repo / "docs"
            evidence = docs / "evidence"
            evidence.mkdir(parents=True)
            (docs / "README.md").write_text(
                "# Docs\n\n- benchmark-evidence-map.md\n",
                encoding="utf-8",
            )
            old_required_terms = [
                term
                for term in docs_health.REQUIRED_BENCHMARK_EVIDENCE_MAP_TERMS
                if term
                != "docs/evidence/benchmarks/hippocampal-private-annotation-protocol.md"
            ]
            (evidence / "benchmark-evidence-map.md").write_text(
                "\n".join(old_required_terms) + "\n",
                encoding="utf-8",
            )

            issues = docs_health.benchmark_evidence_map_issues(repo)

        self.assertIn(
            "benchmark evidence map missing hippocampal private annotation protocol pointer",
            issues,
        )

    def test_hippocampal_private_annotation_protocol_reports_missing_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            write_origin_essays(repo)
            benchmark_docs = repo / "docs" / "evidence" / "benchmarks"
            benchmark_docs.mkdir(parents=True)
            (benchmark_docs / "hippocampal-private-annotation-protocol.md").write_text(
                "# Private Annotation Protocol\n\nTruth-source independence.\n",
                encoding="utf-8",
            )

            issues, _ = docs_health.check_repo_docs(repo)

        self.assertIn(
            "hippocampal private annotation protocol missing reviewer/adjudication flow",
            issues,
        )
        self.assertIn(
            "hippocampal private annotation protocol missing sanitized report template",
            issues,
        )
        self.assertIn(
            "hippocampal private annotation protocol missing privacy exclusions",
            issues,
        )
        self.assertIn(
            "hippocampal private annotation protocol missing external-validity gate",
            issues,
        )

    def test_runtime_script_map_reports_missing_required_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            architecture = repo / "docs" / "architecture"
            architecture.mkdir(parents=True)
            (architecture / "runtime-script-map.md").write_text(
                "aippocampus_runtime/hooks/prompt.py\n", encoding="utf-8"
            )

            issues = docs_health.runtime_script_map_issues(repo)

        self.assertIn(
            "runtime script map missing high-risk runtime entry: "
            "aippocampus_runtime/sync/bundle.py",
            issues,
        )

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

    def test_ia_diagnostics_warn_for_missing_folder_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            guides = repo / "docs" / "guides"
            guides.mkdir(parents=True)
            for index in range(ia_pressure_guard.MISSING_INDEX_MARKDOWN_THRESHOLD):
                (guides / f"guide-{index}.md").write_text("# Guide\n", encoding="utf-8")

            report = ia_pressure_guard.information_architecture_diagnostics(
                repo,
                allowed_root_markdown=docs_health.DOCS_ROOT_ALLOWED_MARKDOWN,
                allowed_root_directories=docs_health.DOCS_ROOT_ALLOWED_DIRECTORIES,
            )

        warnings = report["warnings"]
        self.assertTrue(
            any(
                warning["code"] == "docs_folder_missing_index"
                and warning["path"] == "docs/guides"
                for warning in warnings
            ),
            warnings,
        )
        self.assertEqual(report["failures"], [])

    def test_ia_diagnostics_report_top_level_docs_sprawl_as_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            docs = repo / "docs"
            docs.mkdir(parents=True)
            (docs / "loose-status-report.md").write_text("# Loose\n", encoding="utf-8")

            report = ia_pressure_guard.information_architecture_diagnostics(
                repo,
                allowed_root_markdown=docs_health.DOCS_ROOT_ALLOWED_MARKDOWN,
                allowed_root_directories=docs_health.DOCS_ROOT_ALLOWED_DIRECTORIES,
            )

        self.assertIn(
            {
                "severity": "failure",
                "code": "docs_root_markdown_sprawl",
                "path": "docs/loose-status-report.md",
                "message": (
                    "docs root has unclassified markdown file: docs/loose-status-report.md; "
                    "move it under docs/architecture, docs/guides, docs/evidence, "
                    "docs/planning, or docs/research"
                ),
            },
            report["failures"],
        )

    def test_ia_diagnostics_warn_for_active_doc_missing_role_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            planning = repo / "docs" / "planning"
            planning.mkdir(parents=True)
            (planning / "next-slice.md").write_text(
                "# Next Slice\n\nThis is active planning context.\n",
                encoding="utf-8",
            )

            report = ia_pressure_guard.information_architecture_diagnostics(
                repo,
                allowed_root_markdown=docs_health.DOCS_ROOT_ALLOWED_MARKDOWN,
                allowed_root_directories=docs_health.DOCS_ROOT_ALLOWED_DIRECTORIES,
            )

        warnings = report["warnings"]
        self.assertTrue(
            any(
                warning["code"] == "active_doc_missing_role_status"
                and warning["path"] == "docs/planning/next-slice.md"
                for warning in warnings
            ),
            warnings,
        )

    def test_ia_diagnostics_warn_for_archive_without_current_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            archive = repo / "docs" / "archive"
            archive.mkdir(parents=True)
            (archive / "old-plan.md").write_text(
                "# Old Plan\n\nHistorical notes only.\n",
                encoding="utf-8",
            )

            report = ia_pressure_guard.information_architecture_diagnostics(
                repo,
                allowed_root_markdown=docs_health.DOCS_ROOT_ALLOWED_MARKDOWN,
                allowed_root_directories=docs_health.DOCS_ROOT_ALLOWED_DIRECTORIES,
            )

        warnings = report["warnings"]
        self.assertTrue(
            any(
                warning["code"] == "archive_doc_missing_current_pointer"
                and warning["path"] == "docs/archive/old-plan.md"
                for warning in warnings
            ),
            warnings,
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
        self.assertIn("missing public-readiness doc: docs/guides/community/privacy-security-checklist.md", issues)
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
