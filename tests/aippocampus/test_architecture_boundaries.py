from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.aippocampus.import_coupling_helpers import same_dir_import_edges

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    REPO_ROOT,
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

from aippocampus_runtime.hooks import prompt as prompt_hook  # noqa: E402
from aippocampus_runtime.vault import sync as sync_vault  # noqa: E402

HIGH_RISK_MYPY_SCRIPTS = {
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/server.py",
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/lifecycle.py",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/ambient_cache.py",
    "skills/aippocampus/scripts/aippocampus_runtime/navigation/associations.py",
    "skills/aippocampus/scripts/aippocampus_runtime/navigation/project_timeline.py",
    "skills/aippocampus/scripts/aippocampus_runtime/subconscious/candidate_router.py",
    "skills/aippocampus/scripts/aippocampus_runtime/onboarding/codex.py",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_recall_core.py",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/retrieval.py",
    "skills/aippocampus/scripts/aippocampus_runtime/warm_ambient/recall.py",
}
DEBT_REGISTER = REPO_ROOT / "docs" / "architecture" / "architecture-debt-register.md"
DEBT_SNAPSHOT = (
    REPO_ROOT
    / "docs"
    / "evidence"
    / "reports"
    / "architecture-debt-snapshot-2026-06-04.md"
)
DEBT_REPORT = REPO_ROOT / "tools" / "aippocampus" / "docs" / "debt_report.py"
PROVIDER_ENTRYPOINT_INVENTORY = (
    REPO_ROOT / "docs" / "architecture" / "host" / "provider-entrypoint-inventory.md"
)
RUNTIME_SCRIPT_MAP = REPO_ROOT / "docs" / "architecture" / "runtime-script-map.md"
ENCRYPTED_SYNC_V2 = REPO_ROOT / "docs" / "architecture" / "ops" / "encrypted-sync-v2.md"
LARGE_RUNTIME_THRESHOLD = 600
LARGE_TEST_THRESHOLD = 1500
LARGE_BENCHMARK_THRESHOLD = 1200
LARGE_TOOL_THRESHOLD = 1100
OPS_DIRECT_RECALL_HOOK_IMPORT_ALLOWLIST = {
    "aippocampus_runtime.ops.activation_payload_compaction": {
        "aippocampus_runtime.recall.active_recall_lock_compaction",
        "aippocampus_runtime.recall.ambient_cache_compaction",
        "aippocampus_runtime.recall.semantic_trigger_compaction",
    },
    "aippocampus_runtime.ops.cognitive_observatory": {
        "aippocampus_runtime.recall.why_diagnostics",
    },
    "aippocampus_runtime.ops.presence_first_matrix_fixtures": {
        "aippocampus_runtime.recall",
        "aippocampus_runtime.recall.authority",
        "aippocampus_runtime.recall.prompt_context_render",
    },
    "aippocampus_runtime.ops.provider_doctor": {
        "aippocampus_runtime.recall.semantic_recall_gate",
    },
    "aippocampus_runtime.ops.provider_key_bridge": {
        "aippocampus_runtime.hooks",
        "aippocampus_runtime.hooks.install_lifecycle",
        "aippocampus_runtime.hooks.install_prompt",
    },
    "aippocampus_runtime.ops.uninstall": {
        "aippocampus_runtime.hooks",
        "aippocampus_runtime.hooks.claude_code",
    },
    "aippocampus_runtime.ops.recall_navigation_comparison": {
        "aippocampus_runtime.recall.authority",
    },
    "aippocampus_runtime.ops.recall_navigation_attention": {
        "aippocampus_runtime.recall.query_policy",
    },
    "aippocampus_runtime.ops.recall_navigation_comparison_fixtures": {
        "aippocampus_runtime.recall",
        "aippocampus_runtime.recall.ambient_cards",
        "aippocampus_runtime.recall.prompt_context_render",
        "aippocampus_runtime.recall.prompt_recall_decision",
    },
    "aippocampus_runtime.ops.recall_navigation_macro_fixture": {
        "aippocampus_runtime.recall",
        "aippocampus_runtime.recall.macro_live_recall",
    },
    "aippocampus_runtime.ops.recall_navigation_promotion": {
        "aippocampus_runtime.recall.continuity_usefulness",
    },
    "aippocampus_runtime.ops.source_joined_routing_decision": {
        "aippocampus_runtime.recall",
        "aippocampus_runtime.recall.score_fusion",
    },
    "aippocampus_runtime.ops.route_readiness": {
        "aippocampus_runtime.recall.active_recall_lock_lifecycle",
    },
    "aippocampus_runtime.ops.spend_doctor": {
        "aippocampus_runtime.recall.semantic_recall_gate",
    },
    "aippocampus_runtime.ops.worker_hook_handoff": {
        "aippocampus_runtime.hooks",
        "aippocampus_runtime.hooks.prompt",
        "aippocampus_runtime.recall",
        "aippocampus_runtime.recall.ambient_cache",
    },
}
OPS_STRING_ONLY_RECALL_COMMAND_MODULES = {
    "aippocampus_runtime.ops.graphify_corpus",
    "aippocampus_runtime.ops.maintenance",
    "aippocampus_runtime.ops.storage_governance_contract",
}


def debt_register_entries(*, prefixes: tuple[str, ...] | None = None) -> dict[str, int]:
    entries: dict[str, int] = {}
    for source in (DEBT_REGISTER, DEBT_SNAPSHOT):
        text = source.read_text(encoding="utf-8")
        for match in re.finditer(
            r"^\|\s*`(?P<path>[^`]+\.py)`\s*"
            r"\|\s*(?P<first>\d+)\s*\|(?:\s*(?P<second>\d+)\s*\|)?",
            text,
            flags=re.MULTILINE,
        ):
            if prefixes and not match.group("path").startswith(prefixes):
                continue
            entries[match.group("path")] = int(match.group("second") or match.group("first"))
    return entries


def workflow_python_entrypoints() -> set[str]:
    entrypoints: set[str] = set()
    for workflow in (REPO_ROOT / ".github" / "workflows").glob("*.yml"):
        text = workflow.read_text(encoding="utf-8")
        for match in re.finditer(r"\bpython\s+([^\s\"'`]+\.py)\b", text):
            path = match.group(1).replace("\\", "/")
            if (REPO_ROOT / path).is_file():
                entrypoints.add(path)
    return entrypoints


def source_text(module: object) -> str:
    return Path(module.__file__).read_text(encoding="utf-8")


def line_count(module: object) -> int:
    return len(source_text(module).splitlines())


def script_line_count(path: Path) -> int:
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def runtime_python_files() -> list[Path]:
    return sorted(
        path
        for path in SCRIPTS.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def test_python_files() -> list[Path]:
    return sorted((REPO_ROOT / "tests" / "aippocampus").glob("test_*.py"))


def benchmark_python_files() -> list[Path]:
    return sorted(
        path
        for path in (REPO_ROOT / "benchmarks" / "aippocampus").glob("*.py")
        if path.name != "_paths.py"
    )


def tool_python_files() -> list[Path]:
    return sorted(
        path
        for path in (REPO_ROOT / "tools" / "aippocampus").rglob("*.py")
        if "__pycache__" not in path.parts
    )


def claim_boundary_helper_files() -> list[Path]:
    files = [
        *benchmark_python_files(),
        *sorted((REPO_ROOT / "benchmarks" / "aippocampus" / "shared").glob("*.py")),
        *sorted((REPO_ROOT / "benchmarks" / "aippocampus" / "families").glob("*.py")),
        *sorted((REPO_ROOT / "benchmarks" / "aippocampus" / "source_evidence").glob("*.py")),
        *sorted((REPO_ROOT / "tools" / "aippocampus" / "smoke").glob("*.py")),
    ]
    helper_files: list[Path] = []
    for path in files:
        if path.name == "claim_boundary_refs.py":
            continue
        text = path.read_text(encoding="utf-8")
        helper_names = re.findall(r"^def\s+([A-Za-z_]\w*)\(", text, flags=re.MULTILINE)
        if any("cannot_claim" in name or "claim_boundary" in name for name in helper_names):
            helper_files.append(path)
    return sorted(set(helper_files))


def mypy_file_entries() -> set[str]:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"(?ms)^\[tool\.mypy\].*?^files\s*=\s*\[(.*?)^\]", text)
    if not match:
        return set()
    return set(re.findall(r'"([^"]+\.py)"', match.group(1)))


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_skill_package_does_not_carry_repo_development_surfaces(self) -> None:
        forbidden_prefixes = ("benchmark_", "smoke_", "simulate_")
        forbidden_names = {"check_docs_health.py", "run_stage_0_5_smoke.py"}
        offenders = sorted(
            path.relative_to(SCRIPTS).as_posix()
            for path in runtime_python_files()
            if path.name.startswith(forbidden_prefixes) or path.name in forbidden_names
        )

        self.assertEqual(offenders, [])

    def test_skill_package_does_not_carry_repository_test_tree(self) -> None:
        self.assertFalse((ROOT / "tests").exists())

    def test_sync_vault_is_orchestration_not_dashboard_renderer(self) -> None:
        text = source_text(sync_vault)

        self.assertLessEqual(line_count(sync_vault), 260)
        self.assertNotIn("def html_dashboard", text)
        self.assertNotIn("def dashboard_css", text)
        self.assertNotIn("def dashboard_interaction_script", text)
        self.assertNotIn("def anchor_note", text)
        self.assertNotIn("def health_note", text)

    def test_prompt_hook_entrypoint_is_glue_not_recall_engine(self) -> None:
        text = source_text(prompt_hook)

        self.assertLessEqual(line_count(prompt_hook), 260)
        self.assertNotIn("def score_candidates", text)
        self.assertNotIn("def collect_evidence", text)
        self.assertNotIn("def should_suppress", text)
        self.assertNotIn("def merge_timeline_candidates", text)
        self.assertNotIn("def should_run_semantic_gate", text)

    def test_prompt_decision_module_does_not_import_hook_glue(self) -> None:
        decision_path = SCRIPTS / "aippocampus_runtime" / "recall" / "prompt_recall_decision.py"
        text = decision_path.read_text(encoding="utf-8")

        self.assertNotIn("from aippocampus_prompt_hook import", text)
        self.assertNotIn("import aippocampus_prompt_hook", text)

    def test_runtime_boundary_helpers_remain_available(self) -> None:
        helper_paths = [
            "aippocampus_runtime/onboarding/frontier.py",
            "aippocampus_runtime/onboarding/status.py",
            "aippocampus_runtime/recall/prompt_recall_ambient.py",
            "aippocampus_runtime/recall/prompt_recall_budget.py",
            "aippocampus_runtime/recall/prompt_recall_evidence.py",
            "aippocampus_runtime/registry/search.py",
            "aippocampus_runtime/recall/query_policy.py",
            "aippocampus_runtime/subconscious/jobs_config.py",
            "aippocampus_runtime/warm_ambient/prompting.py",
            "aippocampus_runtime/warm_ambient/scout_profiles.py",
            "aippocampus_runtime/warm_ambient/source_validation.py",
        ]

        missing = sorted(path for path in helper_paths if not (SCRIPTS / path).is_file())

        self.assertEqual(missing, [])

    def test_protocol_first_ports_have_selective_architecture_rule(self) -> None:
        text = RUNTIME_SCRIPT_MAP.read_text(encoding="utf-8")

        for phrase in (
            "Protocol-First Ports",
            "real replacement pressure",
            "Do not introduce a port",
            "source ids/source refs",
            "not a tagless-final architecture",
            "`ConversationProvider`",
        ):
            self.assertIn(phrase, text)

    def test_ops_recall_hook_orchestration_boundary_is_documented_and_allowlisted(self) -> None:
        edges = same_dir_import_edges()
        observed = {
            module: {
                target
                for target in targets
                if target.startswith("aippocampus_runtime.recall")
                or target.startswith("aippocampus_runtime.hooks")
            }
            for module, targets in edges.items()
            if module.startswith("aippocampus_runtime.ops.")
        }
        observed = {module: targets for module, targets in observed.items() if targets}

        self.assertEqual(observed, OPS_DIRECT_RECALL_HOOK_IMPORT_ALLOWLIST)
        self.assertTrue(
            OPS_STRING_ONLY_RECALL_COMMAND_MODULES.isdisjoint(observed),
            "string-only command references must not be counted as direct runtime imports",
        )

        text = RUNTIME_SCRIPT_MAP.read_text(encoding="utf-8")
        for phrase in (
            "## Ops Orchestration Boundary",
            "maintenance CLI",
            "diagnostic/reporting",
            "fixture runner",
            "provider doctor",
            "hook handoff",
            "runtime-adjacent policy",
            "String-only `python -m aippocampus_runtime.recall",
            "must not become foreground recall policy",
            "tests/aippocampus/test_architecture_boundaries.py",
        ):
            self.assertIn(phrase, text)
        for module in sorted(
            set(OPS_DIRECT_RECALL_HOOK_IMPORT_ALLOWLIST)
            | OPS_STRING_ONLY_RECALL_COMMAND_MODULES
        ):
            self.assertIn(f"`{module}`", text)

    def test_encrypted_sync_v2_contract_records_deferred_decisions(self) -> None:
        self.assertTrue(ENCRYPTED_SYNC_V2.is_file(), "encrypted sync v2 design note is missing")
        text = ENCRYPTED_SYNC_V2.read_text(encoding="utf-8")

        for phrase in (
            "# Encrypted Sync V2 Decision Track",
            "## Decision Table",
            "## Threat Model Additions",
            "## Verification And Smoke Plan",
            "## Follow-Up Implementation Issues",
            "passphrase recovery",
            "offline recovery kit",
            "divergent_head",
            "future-recipient revocation",
            "historical ciphertext remains decryptable",
            "removed from future recipients",
            "manifest signing",
            "metadata padding",
            "plaintext debug path",
            "key-provider",
            "macos-keychain",
            "windows-credential-manager",
            "linux-secret-service",
            "vault-id recovery",
            "trusted recipient can author bundles",
        ):
            self.assertIn(phrase, text)

        for threat_row in (
            "storage provider",
            "network observer",
            "compromised object store",
            "revoked device",
            "compromised trusted device",
            "lost local identity",
            "lost vault id",
            "stale/replayed manifest",
            "partial migration",
        ):
            self.assertIn(threat_row, text)

        for smoke_plan in (
            "revoked-recipient status",
            "required re-encryption",
            "wrong-key pull",
            "stale/replayed manifest/head",
            "missing/corrupt vault-id",
            "age_missing",
            "partial migration recovery",
            "key-provider missing",
            "locked provider",
            "wrong identity",
            "export/backup warnings",
        ):
            self.assertIn(smoke_plan, text)

    def test_mypy_baseline_covers_high_risk_core_scripts(self) -> None:
        missing = sorted(HIGH_RISK_MYPY_SCRIPTS - mypy_file_entries())

        self.assertEqual(missing, [])

    def test_large_runtime_scripts_stay_in_mypy_baseline(self) -> None:
        typed = mypy_file_entries()
        missing = sorted(
            path.relative_to(REPO_ROOT).as_posix()
            for path in runtime_python_files()
            if script_line_count(path) >= 300
            and path.relative_to(REPO_ROOT).as_posix() not in typed
        )

        self.assertEqual(missing, [])

    def test_github_workflow_python_entrypoints_stay_in_mypy_baseline(self) -> None:
        typed = mypy_file_entries()
        missing = sorted(workflow_python_entrypoints() - typed)

        self.assertEqual(missing, [])

    def test_large_runtime_scripts_have_debt_register_budgets(self) -> None:
        entries = debt_register_entries(prefixes=("skills/aippocampus/scripts/",))
        large_scripts = {
            path.relative_to(REPO_ROOT).as_posix(): script_line_count(path)
            for path in runtime_python_files()
            if script_line_count(path) >= LARGE_RUNTIME_THRESHOLD
        }
        missing = sorted(set(large_scripts) - set(entries))
        runtime_scripts = {
            path.relative_to(REPO_ROOT).as_posix() for path in runtime_python_files()
        }
        stale = sorted(set(entries) - runtime_scripts)
        over_budget = {
            path: {"loc": large_scripts[path], "budget": entries[path]}
            for path in sorted(set(large_scripts) & set(entries))
            if large_scripts[path] > entries[path]
        }

        self.assertEqual(
            {"missing": missing, "stale": stale, "over_budget": over_budget},
            {"missing": [], "stale": [], "over_budget": {}},
        )

    def test_large_tests_benchmarks_and_tools_have_debt_register_budgets(self) -> None:
        entries = debt_register_entries(
            prefixes=("tests/aippocampus/", "benchmarks/aippocampus/", "tools/aippocampus/"),
        )
        tracked_files = {
            path.relative_to(REPO_ROOT).as_posix(): path
            for path in [
                *test_python_files(),
                *benchmark_python_files(),
                *tool_python_files(),
            ]
        }
        large_files = {
            rel: script_line_count(path)
            for rel, path in tracked_files.items()
            if (
                rel.startswith("tests/aippocampus/")
                and script_line_count(path) >= LARGE_TEST_THRESHOLD
            )
            or (
                rel.startswith("benchmarks/aippocampus/")
                and script_line_count(path) >= LARGE_BENCHMARK_THRESHOLD
            )
            or (
                rel.startswith("tools/aippocampus/")
                and script_line_count(path) >= LARGE_TOOL_THRESHOLD
            )
        }
        missing = sorted(set(large_files) - set(entries))
        stale = sorted(set(entries) - set(tracked_files))
        over_budget = {
            path: {"loc": large_files[path], "budget": entries[path]}
            for path in sorted(set(large_files) & set(entries))
            if large_files[path] > entries[path]
        }

        self.assertEqual(
            {"missing": missing, "stale": stale, "over_budget": over_budget},
            {"missing": [], "stale": [], "over_budget": {}},
        )

    def test_debt_register_documents_non_runtime_thresholds(self) -> None:
        text = DEBT_REGISTER.read_text(encoding="utf-8")

        for phrase in (
            "## Test, Benchmark, And Tool Debt Budgets",
            f"test modules: {LARGE_TEST_THRESHOLD}",
            f"benchmark runners: {LARGE_BENCHMARK_THRESHOLD}",
            f"repo tools and smokes: {LARGE_TOOL_THRESHOLD}",
            "docs/evidence/reports/architecture-debt-snapshot-2026-06-04.md",
            "not a scorecard",
            "At least one real boundary split",
            "test_import_coupling.py",
            "import_coupling_helpers.py",
        ):
            self.assertIn(phrase, text)

    def test_debt_register_records_near_budget_split_priority_queue(self) -> None:
        text = DEBT_REGISTER.read_text(encoding="utf-8")
        near_budget_paths = [
            "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_recall_decision.py",
            "skills/aippocampus/scripts/aippocampus_runtime/recall/semantic_recall_gate.py",
            "skills/aippocampus/scripts/aippocampus_runtime/warm_ambient/recall.py",
            "skills/aippocampus/scripts/aippocampus_runtime/dream/live_shadow_ab.py",
        ]

        self.assertIn("## Near-Budget Split Priority Queue", text)
        self.assertIn("Counting method: `script_line_count()`", text)
        self.assertRegex(text, r"Last counted: \d{4}-\d{2}-\d{2}\.")
        for path in near_budget_paths:
            count = script_line_count(REPO_ROOT / path)
            self.assertRegex(
                text,
                rf"\|\s*`{re.escape(path)}`\s*\|\s*{count}\s*\|",
                msg=f"{path} current count missing from near-budget queue",
            )
        positions = [text.index(f"`{path}`") for path in near_budget_paths]
        self.assertEqual(positions, sorted(positions))
        for phrase in (
            "#500 froze golden foreground projection fixtures",
            "source-evidence/final skip-scent-evidence projection",
            "#580 froze focused skip/scent/evidence fixtures",
            "moved worker response parsing, unavailable classification, and public projection",
            "another extraction would be speculative",
            "Split when a live-shadow feature touches one of those boundaries",
        ):
            self.assertIn(phrase, text)

    def test_debt_register_defines_budget_raise_policy(self) -> None:
        text = DEBT_REGISTER.read_text(encoding="utf-8")

        for phrase in (
            "## Guard Budget Change Policy",
            "Raise a guard budget only when",
            "Split before raising when",
            "Do not raise budgets as a routine way to make tests pass",
            "#500",
        ):
            self.assertIn(phrase, text)

    def test_claim_boundary_helper_pressure_is_registered(self) -> None:
        text = DEBT_REGISTER.read_text(encoding="utf-8")
        helper_paths = [
            path.relative_to(REPO_ROOT).as_posix()
            for path in claim_boundary_helper_files()
        ]
        missing = [path for path in helper_paths if f"`{path}`" not in text]

        self.assertIn("## Claim-Boundary Duplication Pressure", text)
        self.assertIn("Do not add new runner-local caveat catalogs by default", text)
        self.assertIn("prefer `claim_boundary_ref`", text)
        self.assertEqual(missing, [])

    def test_claim_boundary_helpers_share_canonical_ref(self) -> None:
        import importlib

        refs = importlib.import_module("benchmarks.aippocampus.shared.claim_boundary_refs")
        self.assertEqual(
            refs.CANONICAL_CANNOT_CLAIM_REF,
            "docs/architecture/runtime/schema-field-profiles.md#cannot-claim",
        )
        missing = [
            path.relative_to(REPO_ROOT).as_posix()
            for path in claim_boundary_helper_files()
            if path.name != "benchmark_suite.py"
            and "claim_boundary_refs import" not in path.read_text(encoding="utf-8")
        ]

        self.assertEqual(missing, [])

    def test_architecture_debt_report_emits_full_inventory(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(DEBT_REPORT), "--json"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        rows = {row["path"]: row for row in report["rows"]}

        self.assertTrue(report["ok"], report)
        self.assertIn("docs/architecture/architecture-debt-register.md", report["sources"])
        self.assertIn(
            "docs/evidence/reports/architecture-debt-snapshot-2026-06-04.md",
            report["sources"],
        )
        self.assertGreater(report["entry_count"], 40)
        system_weight = report["system_weight"]
        self.assertEqual(
            set(system_weight["layers"]),
            {"runtime", "tests", "benchmarks", "docs", "tools"},
        )
        self.assertGreater(system_weight["total_tracked_lines"], 0)
        self.assertIn("fresh_agent_load", system_weight)
        self.assertIn("archive_or_split_targets", system_weight)
        self.assertEqual(
            rows["tests/aippocampus/test_subconscious_jobs.py"]["current_count"],
            script_line_count(REPO_ROOT / "tests/aippocampus/test_subconscious_jobs.py"),
        )

    def test_codex_default_call_sites_are_classified_in_provider_inventory(self) -> None:
        inventory = PROVIDER_ENTRYPOINT_INVENTORY.read_text(encoding="utf-8")
        markers = (
            "locate_rollout(",
            "iter_rollouts(",
            "codex_home(",
            "provider or codex_provider",
        )
        call_sites = sorted(
            path.relative_to(SCRIPTS).as_posix()
            for path in runtime_python_files()
            if any(marker in path.read_text(encoding="utf-8") for marker in markers)
        )
        missing = [path for path in call_sites if f"`{path}`" not in inventory]

        self.assertEqual(missing, [])

    def test_registry_paths_owner_does_not_depend_on_core_codex_home(self) -> None:
        path = SCRIPTS / "aippocampus_runtime" / "registry" / "paths.py"
        text = path.read_text(encoding="utf-8")

        self.assertNotIn("from aippocampus_runtime.core import", text)
        self.assertNotIn("import aippocampus_runtime.core", text)
        self.assertNotIn("codex_home()", text)

    def test_prompt_hook_module_exits_zero_from_package_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env = {**os.environ, "CODEX_HOME": str(tmp_path / "codex-home")}
            payload = json.dumps({"prompt": "继续清债", "cwd": str(ROOT)}, ensure_ascii=False)

            proc = subprocess.run(
                [sys.executable, "-m", "aippocampus_runtime.hooks.prompt"],
                cwd=SCRIPTS,
                input=payload,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                env=env,
                check=False,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
