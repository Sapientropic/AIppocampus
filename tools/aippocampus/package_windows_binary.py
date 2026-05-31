#!/usr/bin/env python3
"""Build and smoke a Windows standalone binary for the AIppocampus CLI facade."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
    tomllib = None  # type: ignore[assignment]


PRIVATE_DATA_GUARDS = (
    ".aippocampus",
    "aippocampus-registry",
    "transcripts",
    "rollouts",
    "registry",
)
PRIVATE_DATA_GUARDS_ANYWHERE = frozenset(
    name for name in PRIVATE_DATA_GUARDS if name != "registry"
)
PRIVATE_DATA_GUARDS_TOP_LEVEL = frozenset(PRIVATE_DATA_GUARDS)


@dataclass(frozen=True)
class PackagingPlan:
    repo_root: Path
    output_root: Path
    source_scripts: Path
    staged_scripts: Path
    entrypoint: Path
    artifact: Path
    command: list[str]
    private_data_policy: dict[str, Any]


@dataclass(frozen=True)
class SmokeSpec:
    name: str
    args: list[str]
    expected_returncodes: tuple[int, ...] = (0,)
    require_json: bool = False


def discover_repo_root(anchor: Path | None = None) -> Path:
    start = (anchor or Path(__file__)).resolve()
    if start.is_file():
        start = start.parent
    for candidate in (start, *start.parents):
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "skills" / "aippocampus" / "scripts").is_dir()
        ):
            return candidate
    raise RuntimeError(f"could not locate AIppocampus repo root from {start}")


def render_binary_entrypoint() -> str:
    return '''#!/usr/bin/env python3
"""PyInstaller entrypoint for the AIppocampus standalone binary."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def _bundled_scripts_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    bundled = base / "aippocampus_scripts"
    if bundled.is_dir():
        return bundled
    return Path(__file__).resolve().parent


def _run_script_in_process(script_name: str, args: list[str]) -> int:
    script_dir = _bundled_scripts_dir()
    script = script_dir / script_name
    old_argv = sys.argv[:]
    old_path = sys.path[:]
    sys.argv = [str(script), *args]
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(code, file=sys.stderr)
        return 1
    finally:
        sys.argv = old_argv
        sys.path[:] = old_path
    return 0


def main() -> int:
    script_dir = _bundled_scripts_dir()
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    from aippocampus_runtime.cli import facade as cli_facade

    cli_facade.SCRIPT_DIR = script_dir
    cli_facade.run_script = _run_script_in_process
    return int(cli_facade.main())


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _read_pyproject_imports(pyproject: Path) -> list[str]:
    data: dict[str, Any] = {}
    if tomllib is not None:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        setuptools = data.get("tool", {}).get("setuptools", {})
        return sorted(
            {
                *setuptools.get("packages", []),
                *setuptools.get("py-modules", []),
                "aippocampus_cli",
            }
        )

    text = pyproject.read_text(encoding="utf-8")
    imports = {"aippocampus_cli"}
    for key in ("packages", "py-modules"):
        match = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*\[(.*?)\]", text, re.DOTALL)
        if match is None:
            continue
        for value in re.findall(r"""["']([^"']+)["']""", match.group(1)):
            imports.add(value)
    return sorted(imports)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _private_data_policy(repo_root: Path, scripts_dir: Path) -> dict[str, Any]:
    guarded_roots = [repo_root / name for name in PRIVATE_DATA_GUARDS]
    for guarded in guarded_roots:
        if _is_relative_to(scripts_dir, guarded):
            raise RuntimeError(f"refusing to bundle private data root: {guarded}")
    return {
        "source_runtime": "skills/aippocampus/scripts",
        "bundled_source": "staged runtime copy",
        "not_bundled_repo_roots": [str(path.relative_to(repo_root)) for path in guarded_roots],
        "staging_excludes": list(PRIVATE_DATA_GUARDS),
        "reason": "PyInstaller receives a staged copy of the installable runtime scripts; repo-local registries, rollouts, and transcripts stay outside the artifact.",
    }


def stage_runtime_scripts(plan: PackagingPlan) -> None:
    if plan.staged_scripts.exists():
        shutil.rmtree(plan.staged_scripts)
    plan.staged_scripts.parent.mkdir(parents=True, exist_ok=True)

    def ignore_private_dirs(_dir: str, names: list[str]) -> set[str]:
        current = Path(_dir).resolve()
        guarded = set(PRIVATE_DATA_GUARDS_ANYWHERE)
        if current == plan.source_scripts.resolve():
            # `registry` is a private/generated root only at package-copy root.
            # Keep package owners such as `aippocampus_runtime/registry`; hiding
            # them produces a binary that passes shallow smoke but fails health,
            # onboarding, and MCP imports.
            guarded.update(PRIVATE_DATA_GUARDS_TOP_LEVEL)
        return {name for name in names if name in guarded}

    shutil.copytree(plan.source_scripts, plan.staged_scripts, ignore=ignore_private_dirs)


def private_data_guard(plan: PackagingPlan) -> dict[str, Any]:
    """Prove the artifact build input is the staged runtime, not local history.

    PyInstaller may embed build paths in diagnostics, so this guard focuses on
    the stronger privacy boundary: private repository roots are never copied
    into the staged runtime and are never passed as PyInstaller inputs.
    """

    staged_private_entries: list[str] = []
    if plan.staged_scripts.exists():
        for root, dirs, _files in os.walk(plan.staged_scripts):
            for dirname in dirs:
                path = Path(root) / dirname
                relative = path.relative_to(plan.staged_scripts)
                if dirname in PRIVATE_DATA_GUARDS_ANYWHERE or (
                    dirname in PRIVATE_DATA_GUARDS_TOP_LEVEL and str(relative) == dirname
                ):
                    staged_private_entries.append(
                        str(relative)
                    )
    private_roots = [str((plan.repo_root / name).resolve()) for name in PRIVATE_DATA_GUARDS]
    command_text = "\n".join(str(part) for part in plan.command)
    command_private_roots = [root for root in private_roots if root in command_text]
    return {
        "ok": not staged_private_entries and not command_private_roots,
        "staged_private_entries": staged_private_entries,
        "command_private_roots": command_private_roots,
    }


def make_packaging_plan(
    *,
    repo_root: Path | None = None,
    output_root: Path | None = None,
    python_executable: Path | None = None,
) -> PackagingPlan:
    root = discover_repo_root(repo_root).resolve() if repo_root else discover_repo_root().resolve()
    scripts_dir = root / "skills" / "aippocampus" / "scripts"
    if not scripts_dir.is_dir():
        raise RuntimeError(f"missing script runtime: {scripts_dir}")
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        raise RuntimeError(f"missing pyproject.toml: {pyproject}")

    out = (output_root or Path(tempfile.mkdtemp(prefix="aippocampus-pyinstaller-"))).resolve()
    entrypoint = out / "entrypoint" / "aippocampus_binary_entry.py"
    staged_scripts = out / "runtime" / "aippocampus_scripts"
    dist_dir = out / "dist"
    artifact_name = "aippocampus.exe" if platform.system() == "Windows" else "aippocampus"
    artifact = dist_dir / artifact_name
    hidden_imports = _read_pyproject_imports(pyproject)
    data_sep = os.pathsep

    command = [
        str(python_executable or Path(sys.executable)),
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--onefile",
        "--name",
        "aippocampus",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(out / "build"),
        "--specpath",
        str(out / "spec"),
        "--paths",
        str(staged_scripts),
        f"--add-data={staged_scripts}{data_sep}aippocampus_scripts",
        *[f"--hidden-import={name}" for name in hidden_imports],
        str(entrypoint),
    ]
    return PackagingPlan(
        repo_root=root,
        output_root=out,
        source_scripts=scripts_dir,
        staged_scripts=staged_scripts,
        entrypoint=entrypoint,
        artifact=artifact,
        command=command,
        private_data_policy=_private_data_policy(root, scripts_dir),
    )


def _pyinstaller_available() -> bool:
    return importlib.util.find_spec("PyInstaller") is not None


def _smoke_specs(plan: PackagingPlan) -> list[SmokeSpec]:
    smoke_root = plan.output_root / "smoke"
    empty_sync_dir = smoke_root / "empty-sync"
    hooks_json = smoke_root / "hooks.json"
    clean_source = plan.repo_root / "examples" / "public-memory-bundle" / "clean-source"
    return [
        SmokeSpec("help", ["--help"]),
        SmokeSpec("health_help", ["health", "--help"]),
        SmokeSpec(
            "search_public_bundle",
            [
                "search",
                "casual sparks",
                "--cwd",
                str(plan.repo_root),
                "--clean-source-dir",
                str(clean_source),
                "--json",
            ],
            require_json=True,
        ),
        SmokeSpec(
            "mcp_list_tools",
            ["mcp", "list-tools"],
            require_json=True,
        ),
        SmokeSpec(
            "onboard_status",
            ["onboard", "--status", "--format", "json", "--cwd", str(plan.repo_root)],
            require_json=True,
        ),
        SmokeSpec(
            "sync_empty_status",
            ["sync", "status", "--sync-dir", str(empty_sync_dir), "--json"],
            expected_returncodes=(1,),
            require_json=True,
        ),
        SmokeSpec(
            "hooks_status",
            ["hooks", "status", "--hooks-json", str(hooks_json), "--json"],
            require_json=True,
        ),
    ]


def _run_smoke(artifact: Path, plan: PackagingPlan) -> list[dict[str, Any]]:
    (plan.output_root / "smoke" / "empty-sync").mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for spec in _smoke_specs(plan):
        proc = subprocess.run(
            [str(artifact), *spec.args],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        parsed_json = _parse_json(proc.stdout) if spec.require_json else None
        results.append(
            {
                "name": spec.name,
                "args": spec.args,
                "expected_returncodes": list(spec.expected_returncodes),
                "returncode": proc.returncode,
                "stdout_preview": _sanitize_preview(proc.stdout, plan)[:1000],
                "stderr_preview": _sanitize_preview(proc.stderr, plan)[:1000],
                "json_parse": parsed_json is not None if spec.require_json else None,
                "ok": proc.returncode in spec.expected_returncodes
                and (not spec.require_json or parsed_json is not None),
            }
        )
    return results


def _parse_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _sanitize_preview(text: str, plan: PackagingPlan) -> str:
    sanitized = text.replace(str(plan.repo_root), "<repo-root>")
    sanitized = sanitized.replace(str(plan.output_root), "<output-root>")
    sanitized = re.sub(r"[A-Za-z]:\\[^\s\"']+", "<local-path-redacted>", sanitized)
    sanitized = re.sub(r"/(?:Users|home|tmp|var|private|mnt)/[^\s\"']+", "<local-path-redacted>", sanitized)
    return sanitized


def run_packaging(
    *,
    repo_root: Path | None = None,
    output_root: Path | None = None,
    dry_run: bool = False,
    require_pyinstaller: bool = False,
) -> dict[str, Any]:
    plan = make_packaging_plan(repo_root=repo_root, output_root=output_root)
    result: dict[str, Any] = {
        "ok": False,
        "kind": "aippocampus_windows_binary_packaging",
        "status": "",
        "repo_root": str(plan.repo_root),
        "output_root": str(plan.output_root),
        "artifact": None,
        "command": plan.command,
        "private_data_policy": plan.private_data_policy,
        "pyinstaller_available": _pyinstaller_available(),
        "require_pyinstaller": require_pyinstaller,
        "artifact_smoke_passed": False,
        "python_free_support_claimed": False,
        "private_data_guard": None,
        "smoke": [],
    }
    if dry_run:
        # Dry-run is a cross-platform planning/report mode used by CI. Keeping
        # it before the Windows-only build gate avoids implying artifact support.
        result["private_data_guard"] = private_data_guard(plan)
        result["ok"] = True
        result["status"] = "dry_run"
        return result
    if platform.system() != "Windows":
        result["status"] = "unsupported_platform"
        result["error"] = "This packaging path is intentionally Windows-only."
        return result
    if not result["pyinstaller_available"]:
        result["status"] = "pyinstaller_missing"
        result["error"] = "PyInstaller is not installed in this Python environment."
        return result

    plan.entrypoint.parent.mkdir(parents=True, exist_ok=True)
    plan.entrypoint.write_text(render_binary_entrypoint(), encoding="utf-8", newline="\n")
    stage_runtime_scripts(plan)
    result["private_data_guard"] = private_data_guard(plan)
    if not result["private_data_guard"]["ok"]:
        result["status"] = "private_data_guard_failed"
        return result
    proc = subprocess.run(
        plan.command,
        cwd=plan.repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    result["build"] = {
        "returncode": proc.returncode,
        "stdout_preview": proc.stdout[-4000:],
        "stderr_preview": proc.stderr[-4000:],
    }
    if proc.returncode != 0:
        result["status"] = "build_failed"
        return result
    if not plan.artifact.is_file():
        result["status"] = "artifact_missing"
        result["error"] = f"expected artifact missing: {plan.artifact}"
        return result

    smoke = _run_smoke(plan.artifact, plan)
    result["artifact"] = str(plan.artifact)
    result["smoke"] = smoke
    result["artifact_smoke_passed"] = all(item["ok"] for item in smoke)
    result["python_free_support_claimed"] = bool(result["artifact_smoke_passed"])
    result["ok"] = bool(result["artifact_smoke_passed"])
    result["status"] = "smoke_passed" if result["ok"] else "smoke_failed"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--require-pyinstaller", action="store_true")
    parser.add_argument("--json", action="store_true", help="Emit JSON. Kept explicit for script callers.")
    args = parser.parse_args(argv)

    result = run_packaging(
        repo_root=args.repo_root,
        output_root=args.output_root,
        dry_run=args.dry_run,
        require_pyinstaller=args.require_pyinstaller,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
