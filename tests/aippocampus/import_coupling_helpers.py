from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"


def load_module_from_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def script_modules() -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for path in SCRIPTS.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(SCRIPTS).with_suffix("")
        parts = rel.parts[:-1] if rel.name == "__init__" else rel.parts
        if parts:
            modules[".".join(parts)] = path
    return modules


def pyproject_py_modules() -> set[str]:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"(?ms)^py-modules\s*=\s*\[(.*?)^\]", text)
    if not match:
        return set()
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def import_targets_for_node(
    node: ast.AST,
    *,
    current_module: str,
    modules: dict[str, Path],
) -> set[str]:
    targets: set[str] = set()

    def add_if_known(name: str) -> None:
        if name in modules:
            targets.add(name)
        top_level = name.split(".", maxsplit=1)[0]
        if top_level in modules:
            targets.add(top_level)

    if isinstance(node, ast.Import):
        for alias in node.names:
            add_if_known(alias.name)
    elif isinstance(node, ast.ImportFrom) and node.module:
        if node.level:
            parent = current_module.split(".")[:-node.level]
            base = ".".join([*parent, node.module]) if parent else node.module
        else:
            base = node.module
        add_if_known(base)
        for alias in node.names:
            add_if_known(f"{base}.{alias.name}")
    elif isinstance(node, ast.ImportFrom) and node.level:
        parent = current_module.split(".")[:-node.level]
        for alias in node.names:
            add_if_known(".".join([*parent, alias.name]))
    return targets


def same_dir_import_edges(*, top_level_only: bool = False) -> dict[str, set[str]]:
    modules = script_modules()
    edges = {name: set() for name in modules}
    for name, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        nodes = tree.body if top_level_only else ast.walk(tree)
        for node in nodes:
            edges[name].update(
                import_targets_for_node(node, current_module=name, modules=modules)
            )
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
