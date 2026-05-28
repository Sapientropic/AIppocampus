from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class ToolingContractTests(unittest.TestCase):
    def test_python_version_and_typing_contract_are_declared(self) -> None:
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        ci = (REPO_ROOT / ".github" / "workflows" / "aippocampus-ci.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn('requires-python = ">=3.10"', pyproject)
        self.assertIn('target-version = "py310"', pyproject)
        self.assertIn('"benchmark_corpus"', pyproject)
        self.assertIn("[tool.mypy]", pyproject)
        self.assertIn('python_version = "3.10"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/aippocampuslib.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/aippocampus_health.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/build_clean_source.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/build_cognitive_map.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/deepseek_model_routing.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/model_client.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/prompt_context_render.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/prompt_cues.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/prompt_recall_context.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/prompt_recall_decision.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/registry.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/registry_store.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/search_clean_source.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/semantic_recall_gate.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/semantic_scope_labels.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/subconscious_agent.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/subconscious_job_plan.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/subconscious_job_validation.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/subconscious_jobs.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/subconscious_runtime.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/subconscious_tool_loop.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/sync_bundle.py"', pyproject)
        self.assertIn('"skills/aippocampus/scripts/sync_object_storage.py"', pyproject)
        self.assertIn('python-version: ["3.10", "3.11"]', ci)
        self.assertIn("python -m pip install ruff mypy", ci)
        self.assertIn("ruff check skills plugins tests tools benchmarks benchmark_corpus", ci)
        self.assertIn("mypy", ci)


if __name__ == "__main__":
    unittest.main()
