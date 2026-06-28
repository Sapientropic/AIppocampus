#!/usr/bin/env python3
"""Build the repo-local AIppocampus Codex plugin package."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

PLUGIN_SOURCE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = Path("dist") / "aippocampus-plugin"
RUNTIME_GENERATION_MARKER = ".aippocampus-runtime-generation.json"
IGNORED_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".eggs",
    ".aippocampus",
    "aippocampus-registry",
    "clean-source",
    "raw-rollouts",
    "graphify-out",
    "exports",
    "exported-bundles",
    "sync-bundles",
    "build",
    "dist",
}


def ignore_distribution_noise(directory: str, names: list[str]) -> set[str]:
    ignored = {
        name
        for name in names
        if name in IGNORED_NAMES
        or name.endswith(".egg-info")
        or name.endswith(".pyc")
        or name.endswith(".pyo")
    }
    if Path(directory).resolve() == PLUGIN_SOURCE_DIR.resolve():
        ignored.add("build_plugin_package.py")
    return ignored


def safe_replace_dir(output_dir: Path, repo_root: Path) -> None:
    resolved = output_dir.resolve()
    dist_root = (repo_root / "dist").resolve()
    forbidden = {
        repo_root.resolve(),
        PLUGIN_SOURCE_DIR.resolve(),
        (repo_root / "skills" / "aippocampus").resolve(),
    }
    if resolved in forbidden or len(resolved.parts) <= 1:
        raise ValueError(f"refusing to replace unsafe plugin output directory: {resolved}")
    if resolved != dist_root and dist_root not in resolved.parents:
        raise ValueError("plugin package output must stay under the repository dist/ directory")
    if output_dir.exists():
        shutil.rmtree(output_dir)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_generation_hash(package_root: Path) -> tuple[str, int]:
    runtime_root = (
        package_root
        / "skills"
        / "aippocampus"
        / "scripts"
        / "aippocampus_runtime"
    )
    rows: list[str] = []
    if runtime_root.exists():
        for path in sorted(runtime_root.rglob("*.py")):
            rel = path.relative_to(runtime_root)
            if any(part in IGNORED_NAMES for part in rel.parts):
                continue
            rows.append(f"{rel.as_posix()}:{_file_hash(path)}")
    digest = hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()
    return digest, len(rows)


def runtime_generation_marker_payload(package_root: Path) -> dict:
    generation, file_count = runtime_generation_hash(package_root)
    return {
        "kind": "aippocampus_runtime_generation",
        "schema_version": 1,
        "generation": generation,
        "runtime_file_count": file_count,
        "claim_boundary": "runtime generation supports MCP transport refresh only; it is not source evidence",
    }


def write_runtime_generation_marker(package_root: Path) -> dict:
    marker = runtime_generation_marker_payload(package_root)
    (package_root / RUNTIME_GENERATION_MARKER).write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return marker


def build_package(repo_root: str | Path, output_dir: str | Path | None = None) -> dict:
    repo_root = Path(repo_root).resolve()
    output = Path(output_dir or repo_root / DEFAULT_OUTPUT)
    if not output.is_absolute():
        output = repo_root / output

    skill_source = repo_root / "skills" / "aippocampus"
    if not skill_source.exists():
        raise FileNotFoundError(f"missing skill package: {skill_source}")

    safe_replace_dir(output, repo_root)
    output.mkdir(parents=True)

    for item in PLUGIN_SOURCE_DIR.iterdir():
        if item.name == "build_plugin_package.py" or item.name in ignore_distribution_noise(
            str(PLUGIN_SOURCE_DIR), [item.name]
        ):
            continue
        target = output / item.name
        if item.is_dir():
            shutil.copytree(item, target, ignore=ignore_distribution_noise)
        else:
            shutil.copy2(item, target)

    skill_target = output / "skills" / "aippocampus"
    shutil.copytree(skill_source, skill_target, ignore=ignore_distribution_noise)
    runtime_generation = write_runtime_generation_marker(output)

    copied_files = sum(1 for item in output.rglob("*") if item.is_file())
    manifest_path = output / ".codex-plugin" / "plugin.json"
    mcp_path = output / ".mcp.json"
    result = {
        "ok": True,
        "output_dir": str(output),
        "manifest": str(manifest_path),
        "mcp_config": str(mcp_path),
        "skill": str(skill_target),
        "copied_files": copied_files,
        "runtime_generation": {
            "generation": runtime_generation["generation"],
            "runtime_file_count": runtime_generation["runtime_file_count"],
        },
        "hooks_auto_enabled": False,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(PLUGIN_SOURCE_DIR.parents[1]))
    parser.add_argument("--output", default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = build_package(args.repo_root, args.output)
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"plugin package: {result['output_dir']}")
        print(f"files: {result['copied_files']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
