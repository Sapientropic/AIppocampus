from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = REPO_ROOT / "skills" / "aippocampus" / "scripts" / "aippocampus_runtime"


def runtime_modules_importing_knowledge() -> list[str]:
    importers: list[str] = []
    for path in RUNTIME_ROOT.rglob("*.py"):
        rel = path.relative_to(RUNTIME_ROOT).as_posix()
        if rel.startswith("knowledge/"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "aippocampus_runtime.knowledge" or node.module.startswith(
                    "aippocampus_runtime.knowledge."
                ):
                    importers.append(rel)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "aippocampus_runtime.knowledge" or alias.name.startswith(
                        "aippocampus_runtime.knowledge."
                    ):
                        importers.append(rel)
    return sorted(set(importers))


class KnowledgeRuntimeBoundaryTests(unittest.TestCase):
    def test_knowledge_package_is_staged_until_runtime_caller_exists(self) -> None:
        self.assertEqual(runtime_modules_importing_knowledge(), [])

        high_risk_doc = (
            REPO_ROOT / "docs" / "architecture" / "host" / "high-risk-answer-gates.md"
        ).read_text(encoding="utf-8")
        public_api = (REPO_ROOT / "docs" / "guides" / "public-api.md").read_text(
            encoding="utf-8"
        )
        capability_doc = (
            REPO_ROOT
            / "docs"
            / "architecture"
            / "host"
            / "agent-skill-capability-contracts.md"
        ).read_text(encoding="utf-8")

        self.assertIn("## Adoption Status", high_risk_doc)
        self.assertIn("staged deterministic contract prototype", high_risk_doc)
        self.assertIn("no default foreground caller", high_risk_doc)
        self.assertIn("not live high-risk answer coverage", high_risk_doc)
        self.assertIn("staged deterministic contract prototype", public_api)
        self.assertIn("high-risk-answer-gates.md#adoption-status", capability_doc)


if __name__ == "__main__":
    unittest.main()
