from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
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

import aippocampus_prompt_hook as prompt_hook  # noqa: E402
import sync_vault  # noqa: E402

HIGH_RISK_MYPY_SCRIPTS = {
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/server.py",
    "skills/aippocampus/scripts/aippocampus_lifecycle_hook.py",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/ambient_cache.py",
    "skills/aippocampus/scripts/aippocampus_runtime/navigation/associations.py",
    "skills/aippocampus/scripts/aippocampus_runtime/navigation/project_timeline.py",
    "skills/aippocampus/scripts/aippocampus_runtime/subconscious/candidate_router.py",
    "skills/aippocampus/scripts/onboard_codex.py",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_recall_core.py",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/retrieval.py",
    "skills/aippocampus/scripts/aippocampus_runtime/warm_ambient/recall.py",
}
DEBT_REGISTER = REPO_ROOT / "docs" / "architecture" / "architecture-debt-register.md"
PROVIDER_ENTRYPOINT_INVENTORY = (
    REPO_ROOT / "docs" / "architecture" / "provider-entrypoint-inventory.md"
)
RUNTIME_SCRIPT_MAP = REPO_ROOT / "docs" / "architecture" / "runtime-script-map.md"


def debt_register_entries() -> dict[str, int]:
    text = DEBT_REGISTER.read_text(encoding="utf-8")
    entries: dict[str, int] = {}
    for match in re.finditer(
        r"^\|\s*`(?P<path>skills/aippocampus/scripts/[^`]+\.py)`\s*"
        r"\|\s*(?P<budget>\d+)\s*\|",
        text,
        flags=re.MULTILINE,
    ):
        entries[match.group("path")] = int(match.group("budget"))
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
            "onboard_frontier.py",
            "onboard_status.py",
            "prompt_recall_ambient.py",
            "prompt_recall_budget.py",
            "prompt_recall_evidence.py",
            "registry_search.py",
            "retrieval_query_policy.py",
            "subconscious_jobs_config.py",
            "warm_ambient_prompting.py",
            "warm_ambient_scout_profiles.py",
            "warm_ambient_source_validation.py",
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
        entries = debt_register_entries()
        large_scripts = {
            path.relative_to(REPO_ROOT).as_posix(): script_line_count(path)
            for path in runtime_python_files()
            if script_line_count(path) >= 600
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
        self.assertIn("Last counted: 2026-06-03", text)
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
            "#500 owns the behavior-preserving extraction",
            "A real split should accompany a focused semantic-gate change",
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

    def test_prompt_hook_exits_zero_when_split_helper_install_lags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            shutil.copy2(
                SCRIPTS / "aippocampus_prompt_hook.py", tmp_path / "aippocampus_prompt_hook.py"
            )
            shutil.copy2(SCRIPTS / "aippocampuslib.py", tmp_path / "aippocampuslib.py")
            env = {**os.environ, "CODEX_HOME": str(tmp_path / "codex-home")}
            payload = json.dumps({"prompt": "继续清债", "cwd": str(ROOT)}, ensure_ascii=False)

            proc = subprocess.run(
                [sys.executable, str(tmp_path / "aippocampus_prompt_hook.py")],
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
