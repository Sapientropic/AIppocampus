from __future__ import annotations

import ast
import sys
import unittest
from subprocess import run

from tests.aippocampus.import_coupling_helpers import (
    REPO_ROOT,
    SCRIPTS,
    pyproject_py_modules,
    same_dir_import_edges,
    strongly_connected_components,
)

FORMER_FLAT_MODULES = {
    path.stem
    for path in (REPO_ROOT / "skills" / "aippocampus" / "scripts").glob("*.py")
}


class ImportCouplingTests(unittest.TestCase):
    def test_runtime_has_no_top_level_flat_script_shims(self) -> None:
        top_level_scripts = sorted(SCRIPTS.glob("*.py"))

        self.assertEqual(top_level_scripts, [])
        self.assertEqual(pyproject_py_modules(), set())

    def test_scripts_have_no_same_dir_import_cycles(self) -> None:
        edges = same_dir_import_edges()
        cycles = [
            component
            for component in strongly_connected_components(edges)
            if len(component) > 1 or any(node in edges[node] for node in component)
        ]
        self.assertEqual(cycles, [])

    def test_registry_does_not_import_retrieval_at_module_load(self) -> None:
        edges = same_dir_import_edges()

        self.assertNotIn("aippocampus_runtime.recall.retrieval", edges["aippocampus_runtime.registry.api"])

    def test_first_party_python_does_not_import_top_level_runtime_modules(self) -> None:
        roots = [
            REPO_ROOT / "tests" / "aippocampus",
            REPO_ROOT / "tools" / "aippocampus",
            REPO_ROOT / "benchmarks" / "aippocampus",
            SCRIPTS / "aippocampus_runtime",
        ]
        offenders: dict[str, list[str]] = {}
        package_names = {
            path.name
            for path in SCRIPTS.iterdir()
            if path.is_dir() and not path.name.startswith("__")
        }
        allowed_top_level = package_names | {"tests", "tools", "benchmarks", "plugins"}

        for root in roots:
            for path in root.rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                bad: list[str] = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        candidates = [alias.name.split(".", maxsplit=1)[0] for alias in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                        candidates = [node.module.split(".", maxsplit=1)[0]]
                    else:
                        continue
                    bad.extend(
                        name
                        for name in candidates
                        if name not in allowed_top_level
                        and (SCRIPTS / f"{name}.py").exists()
                    )
                if bad:
                    offenders[path.relative_to(REPO_ROOT).as_posix()] = sorted(set(bad))

        self.assertEqual(offenders, {})

    def test_cli_facade_uses_package_owners(self) -> None:
        from aippocampus_runtime.cli import facade

        self.assertEqual(
            facade.resolve_command(["health"]).__dict__,
            {
                "command": "health",
                "script_name": "aippocampus_health.py",
                "module_name": "aippocampus_runtime.health",
                "args": [],
            },
        )
        self.assertEqual(
            facade.resolve_command(["mcp", "list-tools"]).module_name,
            "aippocampus_runtime.mcp.server",
        )
        self.assertEqual(
            facade.resolve_command(["hooks", "lifecycle", "status"]).module_name,
            "aippocampus_runtime.hooks.install_lifecycle",
        )

    def test_representative_package_entrypoints_run_as_modules(self) -> None:
        commands = [
            [sys.executable, "-m", "aippocampus_runtime.health", "--help"],
            [sys.executable, "-m", "aippocampus_runtime.mcp.server", "--list-tools"],
            [sys.executable, "-m", "aippocampus_runtime.cli.facade", "why-not-recall", "nothing", "--json"],
        ]

        for command in commands:
            with self.subTest(command=command):
                result = run(
                    command,
                    cwd=str(SCRIPTS),
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
