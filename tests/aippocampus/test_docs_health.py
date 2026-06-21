from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_doc_tool_module

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"

architecture_index_guard = import_doc_tool_module("architecture_index_guard")
docs_health = import_doc_tool_module("check_docs_health")
classifier_policy_guard = import_doc_tool_module("classifier_policy_guard")
ia_pressure_guard = import_doc_tool_module("ia_pressure_guard")

from tests.aippocampus.docs_health_fixtures import (
    docs_health_repo,
    write_classifier_policy,
    write_classifier_release_checklist,
    write_development_status_pyproject,
    write_origin_essays,
)


class DocsHealthTests(unittest.TestCase):
    def test_skill_entrypoint_stays_slim_and_linked(self) -> None:
        result = docs_health.check_docs(ROOT)

        self.assertTrue(result["ok"], result["issues"])
        self.assertLessEqual(result["metrics"]["skill_lines"], docs_health.MAX_SKILL_LINES)
        self.assertLessEqual(result["metrics"]["skill_words"], docs_health.MAX_SKILL_WORDS)

    def test_diagnostics_are_not_first_recall_prerequisites(self) -> None:
        public_api = (REPO_ROOT / "docs" / "guides" / "public-api.md").read_text(
            encoding="utf-8"
        )
        first_recall = (
            REPO_ROOT / "docs" / "guides" / "first-recall-decision-card.md"
        ).read_text(encoding="utf-8")
        product_profiles = (
            REPO_ROOT / "docs" / "architecture" / "host" / "product-profiles.md"
        ).read_text(encoding="utf-8")

        self.assertNotIn("first-recall prerequisites: `", public_api)
        self.assertIn("recovery/explanation", public_api)
        self.assertIn("recall stayed silent", public_api)
        self.assertIn("route was surprising", public_api)
        self.assertIn("operator wants route-readiness", public_api)
        self.assertIn("agent recall", first_recall)
        self.assertIn("agent deepen", first_recall)
        self.assertIn("power_user_optional", product_profiles)

    def test_public_docs_keep_facade_first_success_before_diagnostics(self) -> None:
        public_api = (REPO_ROOT / "docs" / "guides" / "public-api.md").read_text(
            encoding="utf-8"
        )
        ten_minute = (
            REPO_ROOT / "docs" / "guides" / "ten-minute-public-path.md"
        ).read_text(encoding="utf-8")
        first_card = (
            REPO_ROOT / "docs" / "guides" / "first-recall-decision-card.md"
        ).read_text(encoding="utf-8")
        claude_skill = (
            REPO_ROOT / ".claude" / "skills" / "aippocampus" / "SKILL.md"
        ).read_text(encoding="utf-8")
        llms = (REPO_ROOT / "llms.txt").read_text(encoding="utf-8")

        self.assertLess(
            llms.index("## First Recall Agent Probe"),
            llms.index("## Good Fit"),
        )
        self.assertIn("agent_background", llms)
        self.assertLess(
            llms.index("use recall/deepen/background tools first"),
            llms.index("uvx aippocampus mcp status --json"),
        )
        self.assertLess(
            first_card.index("aippocampus search"),
            first_card.index("aippocampus health"),
        )
        self.assertIn("ten-minute-public-path.md", public_api)
        self.assertLess(
            ten_minute.index("uvx aippocampus search"),
            ten_minute.index("uvx aippocampus onboard --provider auto --status"),
        )
        self.assertIn("aippocampus mcp list-tools --json", public_api)
        self.assertNotIn(
            "python -m aippocampus_runtime.registry.api register-source --provider generic-jsonl",
            public_api,
        )
        self.assertLess(
            claude_skill.index("## First Success Path"),
            claude_skill.index("## Repair And Host Diagnostics"),
        )

    def test_start_here_and_examples_keep_packaged_recall_first(self) -> None:
        start_here = (REPO_ROOT / "docs" / "start-here.md").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        start_here_flat = " ".join(start_here.split())
        readme_flat = " ".join(readme.split())

        recall_command = 'aippocampus agent recall "old decision or handoff cue" --json'
        codex_write = "aippocampus onboard --provider codex --cwd . --json"
        claude_write = "aippocampus onboard --provider claude-code --cwd . --json"
        self.assertLess(readme.index(recall_command), readme.index("## Quick Start"))
        self.assertLess(start_here.index("## First Recall"), start_here.index("## See And Add To Memory"))
        self.assertLess(start_here.index(recall_command), start_here.index("aippocampus vault sync --json"))
        self.assertNotIn(codex_write, readme_flat)
        self.assertNotIn(claude_write, readme_flat)
        self.assertIn("First Recall Decision Card", readme)
        self.assertIn(codex_write, start_here_flat)
        self.assertIn(claude_write, start_here_flat)
        self.assertIn("aippocampus export --json", readme)
        self.assertIn("aippocampus sync --json", start_here)
        self.assertLess(start_here_flat.index(recall_command), start_here_flat.index(codex_write))
        self.assertLess(start_here_flat.index(recall_command), start_here_flat.index(claude_write))

        repo_issues = docs_health.foreground_continuity_doc_issues(REPO_ROOT)
        self.assertEqual([], repo_issues)

    def test_claim_and_report_router_cards_are_guarded(self) -> None:
        self.assertEqual([], docs_health.current_claims_foreground_issues(REPO_ROOT))
        self.assertEqual([], docs_health.benchmark_report_router_issues(REPO_ROOT))
        self.assertEqual([], docs_health.currentness_card_issues(REPO_ROOT))

        with docs_health_repo() as repo:
            current_claims = repo / "docs" / "evidence" / "current-claims.md"
            router = repo / "docs" / "evidence" / "benchmarks" / "reports" / "README.md"
            readiness = repo / "docs" / "evidence" / "readiness" / "stage-0-5-readiness.md"
            current_claims.parent.mkdir(parents=True)
            router.parent.mkdir(parents=True)
            readiness.parent.mkdir(parents=True)
            current_claims.write_text("# Current Evidence Claims\n", encoding="utf-8")
            router.write_text("# Benchmark Report Layer\n", encoding="utf-8")
            readiness.write_text("# Stage 0-5 Readiness Snapshot\n", encoding="utf-8")

            self.assertTrue(docs_health.current_claims_foreground_issues(repo))
            self.assertTrue(docs_health.benchmark_report_router_issues(repo))
            self.assertTrue(docs_health.currentness_card_issues(repo))

    def test_signed_benchmark_reports_have_actionable_followup_or_no_action_reason(self) -> None:
        warnings, metrics = docs_health.benchmark_report_followup_warnings(REPO_ROOT)

        self.assertGreaterEqual(metrics["json_reports_checked"], 2)
        self.assertGreaterEqual(metrics["explicit_no_open_followup_reports"], 1)
        warning_text = "\n".join(warnings)
        self.assertNotIn("public-reliability-gauntlet-2026-06-10.json", warning_text)
        self.assertNotIn(
            "longmemeval-post-factual-alias-rerank-closeout-500-2026-06-14.analysis.json",
            warning_text,
        )

        public_reliability = json.loads(
            (
                REPO_ROOT
                / "docs"
                / "evidence"
                / "benchmarks"
                / "reports"
                / "public-reliability"
                / "public-reliability-gauntlet-2026-06-10.json"
            ).read_text(encoding="utf-8")
        )
        self.assertIn("review_next_actions", public_reliability)
        self.assertTrue(public_reliability["review_next_actions"][0]["owner_path"])
        self.assertTrue(public_reliability["review_next_actions"][0]["issue_url"])
        self.assertEqual(public_reliability["review_next_actions"][0]["issue_state"], "closed_historical")
        self.assertIn("#2101 closed", public_reliability["no_open_followup_reason"])

    def test_provider_key_docs_prefer_visible_env_before_dotenv_fallbacks(self) -> None:
        safe_env = (
            REPO_ROOT / "docs" / "guides" / "setup" / "safe-environment.md"
        ).read_text(encoding="utf-8")
        install_guide = (REPO_ROOT / "docs" / "guides" / "install-guide.md").read_text(
            encoding="utf-8"
        )
        public_api = (REPO_ROOT / "docs" / "guides" / "public-api.md").read_text(
            encoding="utf-8"
        )
        safe_env_flat = " ".join(safe_env.split())
        install_guide_flat = " ".join(install_guide.split())
        public_api_flat = " ".join(public_api.split())

        self.assertIn("visible environment key is the normal first path", safe_env_flat)
        self.assertIn("Dotenv discovery is an alternate operator diagnostic", safe_env_flat)
        self.assertLess(
            safe_env_flat.index("visible environment key is the normal first path"),
            safe_env_flat.index("Dotenv discovery is an alternate operator diagnostic"),
        )

        self.assertIn("--source visible-env-key", install_guide)
        self.assertLess(
            install_guide.index("--source visible-env-key"),
            install_guide.index("--source explicit-dotenv"),
        )
        self.assertIn(
            "does not print, hash, persist, or validate the secret",
            install_guide_flat,
        )

        self.assertIn("--source visible-env-key --provider-env-var <NAME>", public_api)
        self.assertIn("Supported alternate source names are `explicit-dotenv`", public_api_flat)
        self.assertLess(
            public_api_flat.index("--source visible-env-key --provider-env-var <NAME>"),
            public_api_flat.index("Supported alternate source names are `explicit-dotenv`"),
        )

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

    def test_first_useful_recall_demo_is_copy_pasteable_and_agent_native(self) -> None:
        demo_text = (REPO_ROOT / "docs" / "guides" / "demo-scenarios.md").read_text(
            encoding="utf-8"
        )
        first_demo = demo_text.split("## Maintainer And Operator Scenario Catalog", 1)[0]

        self.assertIn("git clone https://github.com/Sapientropic/AIppocampus.git", first_demo)
        self.assertIn('python -m pip install -e ".[dev]"', first_demo)
        self.assertIn("aippocampus start --json", first_demo)
        self.assertIn(
            'aippocampus agent recall "can an agent catch up without pretending it has innate memory?"',
            first_demo,
        )
        self.assertLess(first_demo.index("aippocampus start --json"), first_demo.index("agent recall"))
        self.assertLess(first_demo.index("agent recall"), first_demo.index("agent deepen"))
        self.assertIn("First Useful Recall (Agent)", first_demo)
        self.assertIn("recall_context", first_demo)
        self.assertIn("recall_deepen", first_demo)

    def test_bilingual_docs_have_operational_bridge_and_glossary(self) -> None:
        glossary = REPO_ROOT / "docs" / "guides" / "glossary-bilingual.md"
        zh_first = REPO_ROOT / "docs" / "guides" / "zh" / "first-useful-recall.md"
        llms_text = (REPO_ROOT / "llms.txt").read_text(encoding="utf-8")
        origin_zh = (REPO_ROOT / "docs" / "未干的地图.md").read_text(encoding="utf-8")
        yi_contract = (
            REPO_ROOT / "docs" / "architecture" / "coordination" / "yi-macro-runtime-interfaces.md"
        ).read_text(encoding="utf-8")

        self.assertTrue(glossary.exists())
        self.assertTrue(zh_first.exists())
        glossary_text = glossary.read_text(encoding="utf-8")
        zh_text = zh_first.read_text(encoding="utf-8")
        for term in (
            "hippocampus",
            "continuity",
            "clean source",
            "recall",
            "deepen",
            "route",
            "layer",
            "scaffold",
            "foundation",
        ):
            self.assertIn(term, glossary_text)
        self.assertIn("Chinese origin essay is canonical", llms_text)
        self.assertIn("English transcreation", llms_text)
        self.assertIn("canonical Chinese origin essay", origin_zh[:500])
        self.assertIn("the-unfinished-map.md", origin_zh[:500])
        self.assertIn("aippocampus start --json", zh_text)
        self.assertIn("aippocampus agent recall", zh_text)
        for gloss in (
            "世 / 应 (Shi/Ying; host/response role positioning)",
            "消息卦 momentum (growth/decline phase)",
            "纳甲-like active-axis timing (Najia-style timing)",
            "卦气-like source-epoch cadence (hexagram-qi style cadence)",
            "乘 / 承 / 比 / 应 internal line topology",
            "当位 / 不当位 (proper/improper line position)",
            "本卦 -> changing lines -> 之卦 (original hexagram -> changed hexagram)",
            "Nuclear/互卦 basins (nuclear hexagram basins)",
        ):
            self.assertIn(gloss, yi_contract)

    def test_evidence_ledgers_stay_line_addressable(self) -> None:
        issues, metrics = docs_health.evidence_ledger_line_length_payload(REPO_ROOT)

        self.assertEqual([], issues)
        self.assertLessEqual(
            metrics["ledgers"]["docs/evidence/current-claims.md"]["max_line_length"],
            docs_health.EVIDENCE_LEDGER_LINE_LENGTH_LIMIT,
        )

        with docs_health_repo() as repo:
            ledger = repo / "docs" / "evidence" / "current-claims.md"
            ledger.parent.mkdir(parents=True)
            ledger.write_text("short\n" + ("x" * 1001) + "\n", encoding="utf-8")
            issues, metrics = docs_health.evidence_ledger_line_length_payload(repo)

        self.assertTrue(issues)
        self.assertEqual(
            1,
            metrics["ledgers"]["docs/evidence/current-claims.md"]["long_line_count"],
        )

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

    def test_agent_facing_ux_charter_is_discoverable(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        self.assertIsNotNone(repo_root)

        result = docs_health.agent_facing_ux_charter_issues(repo_root)

        self.assertEqual(result, [])

    def test_agent_facing_ux_charter_reports_missing_discovery_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            charter = repo / docs_health.AGENT_FACING_UX_CHARTER
            charter.parent.mkdir(parents=True)
            charter.write_text("# UX charter\n", encoding="utf-8")
            for rel_path, _ in docs_health.AGENT_FACING_UX_DISCOVERY_DOCS:
                path = repo / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Missing pointer\n", encoding="utf-8")

            issues = docs_health.agent_facing_ux_charter_issues(repo)

        self.assertIn(
            "recall architecture index missing agent-facing UX charter pointer",
            issues,
        )
        self.assertIn(
            "foreground memory UX budget missing agent-facing UX charter pointer",
            issues,
        )

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

    def test_github_templates_keep_product_path_separate_from_benchmark_closeout(self) -> None:
        repo_root = docs_health.find_repo_root(ROOT)
        assert repo_root is not None

        issue_dir = repo_root / ".github" / "ISSUE_TEMPLATE"
        product = (issue_dir / "product_cli_ux_fix.md").read_text(encoding="utf-8")
        benchmark = (issue_dir / "benchmark_readiness_public_claim.md").read_text(encoding="utf-8")
        pr = (repo_root / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")

        self.assertIn("Product / CLI / UX fix", product)
        self.assertIn("Expected Smooth Behavior", product)
        self.assertNotIn("Evidence Level / Verification Profile", product)
        self.assertNotIn("Closeout class", product)
        self.assertIn("Benchmark / readiness / public-claim work", benchmark)
        self.assertIn("Evidence Level / Verification Profile", benchmark)
        self.assertIn("Optional Benchmark / Readiness Closeout", pr)
        source_discipline = (repo_root / "docs/architecture/recall/source-backed-product-discipline.md").read_text(encoding="utf-8")
        guard_text = "\n".join([pr, product, source_discipline])
        guard_terms = ("Foreground Usefulness / De-Armor Check", "Foreground usefulness delta", "Foreground Usefulness Delta", "Load-bearing unknown", "load-bearing unknown", "Compact/default output remains action-shaped", "foreground usefulness", "smallest useful next action or reopen route")
        self.assertEqual([], [term for term in guard_terms if term not in guard_text])
        self.assertLess(pr.index("## Verification"), pr.index("## Optional Benchmark"))
        self.assertNotIn("feature_or_benchmark_proposal", "\n".join(path.name for path in issue_dir.glob("*.md")))

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
        self.assertIn("Claude Code MCP guide missing explicit hook install command", issues)
        self.assertIn("Claude Code MCP guide missing explicit hook uninstall command", issues)
        self.assertIn(
            "Claude Code project skill missing hook status/dry-run/install/uninstall/smoke boundary",
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
        self.assertIn("start-here missing 10-minute public path", issues)
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

    def test_install_guide_rejects_internal_object_sync_cli_as_primary_example(self) -> None:
        issues = docs_health.public_doc_command_issues(
            "docs/guides/install-guide.md",
            "\n".join(
                [
                    "## Object-Storage Sync",
                    "",
                    "```sh",
                    "PYTHONPATH=./skills/aippocampus/scripts python3 -m aippocampus_runtime.sync.object_storage.cli push --json",
                    "```",
                ]
            ),
        )

        self.assertTrue(any("internal object-storage sync CLI" in issue for issue in issues), issues)

    def test_write_like_memory_card_examples_stay_executable(self) -> None:
        card = (REPO_ROOT / "docs" / "guides" / "write-like-memory-decision-card.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("agent feedback <route_id> --outcome helped --json", card)
        self.assertIn("do-not-use-here <route-or-ticket-id> --json", card)
        self.assertIn("--feedback-jsonl", card)
        self.assertIn("advanced/operator override", card)
        self.assertNotIn("--feedback-jsonl <local-feedback.jsonl>", card)
        self.assertIn("hooks action refresh-cache --write --json", card)
        self.assertNotIn("agent feedback <route_id> --outcome helped --json` | receipt only", card)
        self.assertNotIn("durable only with an explicit path", card)
        self.assertNotIn("<local-cache.jsonl>", card)

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
