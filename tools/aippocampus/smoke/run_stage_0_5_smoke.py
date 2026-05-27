#!/usr/bin/env python3
"""Run the repo-level Stage 0-5 public-readiness smoke suite."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

SMOKE_TOOLS = Path(__file__).resolve().parent
SKILL_ROOT = _paths.SKILL_ROOT
REPO_ROOT = _paths.REPO_ROOT
EXCLUDED_SCAN_DIRS = {
    ".git",
    ".gitnexus",
    ".ruff_cache",
    ".tmp",
    ".aippocampus",
    "__pycache__",
    "build",
    "dist",
}
EXCLUDED_SCAN_PARTS = {
    ("skills", "aippocampus", "assets"),
    ("skills", "aippocampus", "scripts", "vault_dashboard_assets"),
}
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
    re.compile(r"[A-Za-z]:\\"),
)


@dataclass(frozen=True)
class SmokeCommand:
    label: str
    cmd: list[str]
    cwd: Path
    timeout: int = 180


def repo_root_from_arg(value: str | Path | None = None) -> Path:
    root = Path(value).resolve() if value else REPO_ROOT.resolve()
    required = [
        root / "docs" / "roadmap.md",
        root / "skills" / "aippocampus" / "SKILL.md",
        root / "plugins" / "aippocampus" / ".codex-plugin" / "plugin.json",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise ValueError(f"not an AIppocampus repository root: {root}")
    return root


def timeline_smoke_output(run_id: str) -> Path:
    return Path(".tmp") / f"stage-0-5-public-project-timeline-{run_id}.json"


def plugin_build_output(run_id: str) -> Path:
    return Path("dist") / f"aippocampus-plugin-{run_id}"


def semantic_scope_generation_dir(run_id: str) -> Path:
    return Path(".tmp") / f"stage-0-5-semantic-scope-clean-source-{run_id}"


def build_command_plan(
    repo_root: Path,
    run_id: str = "smoke",
    *,
    include_live_stage2_source_review: bool = False,
) -> list[SmokeCommand]:
    python = sys.executable
    smoke_tools = repo_root / "tools" / "aippocampus" / "smoke"
    docs_tools = repo_root / "tools" / "aippocampus" / "docs"
    timeline_output = repo_root / timeline_smoke_output(run_id)
    plugin_output = repo_root / plugin_build_output(run_id)
    commands = [
        SmokeCommand(
            "docs_health",
            [python, str(docs_tools / "check_docs_health.py"), "--json"],
            repo_root,
            60,
        ),
        SmokeCommand(
            "unit_suite",
            [python, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
            repo_root,
            240,
        ),
        SmokeCommand(
            "compileall",
            [
                python,
                "-m",
                "compileall",
                "-q",
                "skills",
                "plugins",
                "tests",
                "tools",
                "benchmarks",
                "benchmark_corpus",
            ],
            repo_root,
            120,
        ),
        SmokeCommand(
            "ruff",
            [
                python,
                "-m",
                "ruff",
                "check",
                "skills",
                "plugins",
                "tests",
                "tools",
                "benchmarks",
                "--config",
                "pyproject.toml",
            ],
            repo_root,
            120,
        ),
        SmokeCommand(
            "public_timeline",
            [
                python,
                str(repo_root / "skills" / "aippocampus" / "scripts" / "build_project_timeline.py"),
                "--registry",
                str(repo_root / "examples" / "public-memory-bundle" / "registry" / "threads.json"),
                "--output",
                str(timeline_output),
                "--json",
            ],
            repo_root,
            120,
        ),
        SmokeCommand(
            "scope_search",
            [
                python,
                str(repo_root / "skills" / "aippocampus" / "scripts" / "search_clean_source.py"),
                "casual sparks",
                "--cwd",
                str(repo_root),
                "--clean-source-dir",
                str(repo_root / "examples" / "public-memory-bundle" / "clean-source"),
                "--scope-label",
                "idea_seed",
                "--json",
            ],
            repo_root,
            120,
        ),
        SmokeCommand(
            "casual_important_search",
            [
                python,
                str(repo_root / "skills" / "aippocampus" / "scripts" / "search_clean_source.py"),
                "lighthouse metaphor pivot",
                "--cwd",
                str(repo_root),
                "--clean-source-dir",
                str(repo_root / "examples" / "public-memory-bundle" / "clean-source"),
                "--scope-label",
                "personal_reflection",
                "--scope-label",
                "idea_seed",
                "--json",
            ],
            repo_root,
            120,
        ),
        SmokeCommand(
            "life_wide_registry_smoke",
            [
                python,
                str(
                    smoke_tools / "smoke_life_wide_registry.py"
                ),
                "--json",
            ],
            repo_root,
            120,
        ),
        SmokeCommand(
            "semantic_scope_real_history_smoke",
            [
                python,
                str(
                    repo_root
                    / "tools"
                    / "aippocampus"
                    / "smoke"
                    / "smoke_semantic_scope_real_history.py"
                ),
                "--json",
            ],
            repo_root,
            120,
        ),
        SmokeCommand(
            "source_evidence_recall_eval",
            [
                python,
                str(
                    repo_root
                    / "tools"
                    / "aippocampus"
                    / "smoke"
                    / "smoke_source_evidence_recall_eval.py"
                ),
                "--max-cases",
                "24",
                "--min-cases",
                "12",
                "--top-k",
                "5",
                "--min-hit-rate",
                "0.85",
                "--json",
            ],
            repo_root,
            180,
        ),
        SmokeCommand(
            "mcp_tool_list",
            [
                python,
                str(repo_root / "skills" / "aippocampus" / "scripts" / "aippocampus_mcp_server.py"),
                "--list-tools",
            ],
            repo_root,
            60,
        ),
        SmokeCommand(
            "plugin_build",
            [
                python,
                str(repo_root / "plugins" / "aippocampus" / "build_plugin_package.py"),
                "--repo-root",
                str(repo_root),
                "--output",
                str(plugin_output),
                "--json",
            ],
            repo_root,
            120,
        ),
        SmokeCommand(
            "plugin_install_smoke",
            [
                python,
                str(repo_root / "plugins" / "aippocampus" / "smoke_plugin_install.py"),
                "--repo-root",
                str(repo_root),
                "--json",
            ],
            repo_root,
            120,
        ),
        SmokeCommand(
            "cross_device_sync_smoke",
            [
                python,
                str(
                    smoke_tools / "smoke_cross_device_sync.py"
                ),
                "--repo-root",
                str(repo_root),
                "--json",
            ],
            repo_root,
            120,
        ),
        SmokeCommand(
            "object_storage_sync_smoke",
            [
                python,
                str(
                    repo_root
                    / "tools"
                    / "aippocampus"
                    / "smoke"
                    / "smoke_object_storage_sync.py"
                ),
                "--repo-root",
                str(repo_root),
                "--json",
            ],
            repo_root,
            120,
        ),
        SmokeCommand(
            "alternate_runtime_sync_smoke",
            [
                python,
                str(
                    repo_root
                    / "tools"
                    / "aippocampus"
                    / "smoke"
                    / "smoke_alternate_runtime_sync.py"
                ),
                "--repo-root",
                str(repo_root),
                "--runtime",
                "all",
                "--json",
            ],
            repo_root,
            240,
        ),
    ]
    if include_live_stage2_source_review:
        commands.append(
            SmokeCommand(
                "semantic_scope_source_review_live",
                [
                    python,
                    str(
                        repo_root
                        / "tools"
                        / "aippocampus"
                        / "smoke"
                        / "smoke_semantic_scope_source_review.py"
                    ),
                    "--live",
                    "--max-cases",
                    "96",
                    "--min-cases",
                    "64",
                    "--min-pass-rate",
                    "0.75",
                    "--min-label-pass-rate",
                    "0.65",
                    "--concurrency",
                    "2",
                    "--timeout",
                    "200",
                    "--max-attempts",
                    "3",
                    "--json",
                ],
                repo_root,
                540,
            )
        )
    return commands


def path_is_within(root: Path, target: Path) -> bool:
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    return resolved_target == resolved_root or resolved_root in resolved_target.parents


def cleanup_targets(repo_root: Path, run_id: str) -> list[Path]:
    return [
        repo_root / plugin_build_output(run_id),
        repo_root / timeline_smoke_output(run_id),
        repo_root / semantic_scope_generation_dir(run_id),
    ]


def cleanup_smoke_outputs(repo_root: Path, run_id: str) -> list[str]:
    removed: list[str] = []
    for target in cleanup_targets(repo_root, run_id):
        if not target.exists():
            continue
        if not path_is_within(repo_root, target):
            raise ValueError(f"refusing to remove outside repo: {target}")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        removed.append(target.relative_to(repo_root).as_posix())
    return removed


def run_command(command: SmokeCommand) -> dict[str, Any]:
    proc = subprocess.run(
        command.cmd,
        cwd=command.cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=command.timeout,
        check=False,
    )
    return {
        "label": command.label,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "_stdout": proc.stdout,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def validate_casual_important_search(payload: dict[str, Any]) -> dict[str, Any]:
    matches = payload.get("matches") if isinstance(payload.get("matches"), list) else []
    top = matches[0] if matches and isinstance(matches[0], dict) else {}
    if top.get("message_id") != "msg_public_005":
        return {
            "ok": False,
            "message": "casual-important smoke must return msg_public_005 as the top sidecar-backed match",
        }
    semantic_labels = [
        str(label) for label in top.get("semantic_scope_labels") or [] if isinstance(label, str)
    ]
    required = {"personal_reflection", "idea_seed"}
    if not required.issubset(set(semantic_labels)):
        return {
            "ok": False,
            "message": "casual-important smoke top match must include semantic_scope_labels from the sidecar",
        }
    return {
        "ok": True,
        "top_message_id": top.get("message_id"),
        "semantic_scope_labels": semantic_labels,
    }


def validate_command_result(command: SmokeCommand, result: dict[str, Any]) -> dict[str, Any]:
    raw_stdout = str(result.pop("_stdout", ""))
    if not result.get("ok"):
        return result
    if command.label != "casual_important_search":
        return result
    try:
        payload = json.loads(raw_stdout or str(result.get("stdout_tail") or "{}"))
    except json.JSONDecodeError as exc:
        result["ok"] = False
        result["validation"] = {"ok": False, "message": f"invalid JSON output: {exc}"}
        return result
    validation = validate_casual_important_search(payload)
    result["validation"] = validation
    if not validation.get("ok"):
        result["ok"] = False
    return result


def run_json_command(args: list[str], *, cwd: Path, timeout: int = 120) -> dict[str, Any]:
    proc = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    payload: dict[str, Any] = {}
    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = {}
    return {
        "ok": proc.returncode == 0 and bool(payload.get("ok", proc.returncode == 0)),
        "returncode": proc.returncode,
        "payload": payload,
        "stdout_tail": proc.stdout[-1200:],
        "stderr_tail": proc.stderr[-1200:],
    }


def run_semantic_scope_generation_smoke(repo_root: Path, run_id: str) -> dict[str, Any]:
    python = sys.executable
    clean_source_dir = repo_root / semantic_scope_generation_dir(run_id)
    if clean_source_dir.exists():
        if not path_is_within(repo_root, clean_source_dir):
            raise ValueError(f"refusing to remove outside repo: {clean_source_dir}")
        shutil.rmtree(clean_source_dir)
    shutil.copytree(
        repo_root / "examples" / "public-memory-bundle" / "clean-source", clean_source_dir
    )
    sidecar_path = clean_source_dir / "semantic-scope-labels.jsonl"
    if sidecar_path.exists():
        sidecar_path.unlink()

    materialize = run_json_command(
        [
            python,
            str(
                repo_root / "skills" / "aippocampus" / "scripts" / "build_semantic_scope_labels.py"
            ),
            "--jobs-output",
            str(
                repo_root
                / "examples"
                / "public-memory-bundle"
                / "registry"
                / "subconscious_jobs.jsonl"
            ),
            "--clean-source-dir",
            str(clean_source_dir),
            "--json",
        ],
        cwd=repo_root,
        timeout=120,
    )
    search: dict[str, Any] | None = None
    validation: dict[str, Any] = {"ok": False, "message": "materializer did not run"}
    if materialize["ok"]:
        search = run_json_command(
            [
                python,
                str(repo_root / "skills" / "aippocampus" / "scripts" / "search_clean_source.py"),
                "lighthouse metaphor pivot",
                "--cwd",
                str(repo_root),
                "--clean-source-dir",
                str(clean_source_dir),
                "--scope-label",
                "personal_reflection",
                "--scope-label",
                "idea_seed",
                "--json",
            ],
            cwd=repo_root,
            timeout=120,
        )
        validation = validate_casual_important_search(search.get("payload") or {})
    ok = bool(
        materialize.get("ok")
        and materialize.get("payload", {}).get("row_count") == 1
        and search
        and search.get("ok")
        and validation.get("ok")
    )
    return {
        "label": "semantic_scope_label_generation_smoke",
        "ok": ok,
        "materialize": materialize,
        "search": search,
        "validation": validation,
    }


def run_sync_smoke(repo_root: Path) -> dict[str, Any]:
    python = sys.executable
    script = repo_root / "skills" / "aippocampus" / "scripts" / "sync_bundle.py"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source_registry = root / "source-registry"
        target_registry = root / "target-registry"
        sync_dir = root / "sync"
        source_registry.mkdir(parents=True)
        target_registry.mkdir()
        sync_dir.mkdir()
        shutil.copytree(
            repo_root / "examples" / "public-memory-bundle" / "registry",
            source_registry,
            dirs_exist_ok=True,
        )
        public_clean = repo_root / "examples" / "public-memory-bundle" / "clean-source"
        smoke_clean = source_registry / "threads" / "public-example-thread" / "clean-source"
        smoke_clean.mkdir(parents=True)
        for filename in (
            "manifest.json",
            "messages.jsonl",
            "turns.jsonl",
            "semantic-scope-labels.jsonl",
        ):
            shutil.copy2(public_clean / filename, smoke_clean / filename)
        results = []
        for command in ("push", "status", "repair", "pull"):
            args = [
                python,
                str(script),
                command,
                "--sync-dir",
                str(sync_dir),
                "--registry-dir",
                str(source_registry if command != "pull" else target_registry),
                "--json",
            ]
            proc = subprocess.run(
                args,
                cwd=repo_root,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=60,
                check=False,
            )
            payload = (
                json.loads(proc.stdout) if proc.returncode == 0 and proc.stdout.strip() else {}
            )
            results.append(
                {
                    "command": command,
                    "ok": proc.returncode == 0 and bool(payload.get("ok")),
                    "returncode": proc.returncode,
                    "payload": payload,
                    "stderr_tail": proc.stderr[-1000:],
                }
            )
    return {
        "label": "sync_local_folder_smoke",
        "ok": all(item["ok"] for item in results)
        and bool((results[-1].get("payload") or {}).get("path_repair", {}).get("ok")),
        "results": results,
        "raw_rollout_included": bool((results[0].get("payload") or {}).get("raw_rollout_included")),
    }


def excluded_scan_path(path: Path, repo_root: Path) -> bool:
    rel = path.relative_to(repo_root)
    parts = rel.parts
    if any(part in EXCLUDED_SCAN_DIRS for part in parts):
        return True
    return any(parts[: len(excluded)] == excluded for excluded in EXCLUDED_SCAN_PARTS)


def allowed_secret_like_line(line: str) -> bool:
    low = line.casefold()
    if "fake_test" in low and (
        "fake_test_openai_api_key" in low
        or "fake_test_local_path" in low
        or "fake_test_windows" in low
    ):
        return True
    if "api_key" in low and ("if not api_key" in low or "api_key=api_key" in low):
        return True
    return False


def scan_secret_like_strings(repo_root: Path) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for path in repo_root.rglob("*"):
        if not path.is_file() or excluded_scan_path(path, repo_root):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not any(pattern.search(line) for pattern in SECRET_PATTERNS):
                continue
            if allowed_secret_like_line(line):
                continue
            hits.append(
                {
                    "path": path.relative_to(repo_root).as_posix(),
                    "line_no": line_no,
                    "line": line[:240],
                }
            )
    return hits


def run_stage_0_5_smoke(
    repo_root: Path,
    *,
    run_id: str | None = None,
    include_live_stage2_source_review: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root_from_arg(repo_root)
    run_id = run_id or uuid.uuid4().hex[:10]
    command_results: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "ok": False,
        "commands": command_results,
        "sync": None,
        "secret_scan": {"ok": False, "hits": []},
        "cleanup": [],
    }
    try:
        for command in build_command_plan(
            repo_root,
            run_id,
            include_live_stage2_source_review=include_live_stage2_source_review,
        ):
            command_results.append(validate_command_result(command, run_command(command)))
            if not command_results[-1]["ok"]:
                break
        if all(item["ok"] for item in command_results):
            command_results.append(run_semantic_scope_generation_smoke(repo_root, run_id))
        sync_result = (
            run_sync_smoke(repo_root) if all(item["ok"] for item in command_results) else None
        )
        scan_hits = (
            scan_secret_like_strings(repo_root) if sync_result and sync_result.get("ok") else []
        )
        ok = (
            all(item["ok"] for item in command_results)
            and bool(sync_result and sync_result.get("ok"))
            and not scan_hits
        )
        result.update(
            {
                "ok": ok,
                "sync": sync_result,
                "secret_scan": {"ok": not scan_hits, "hits": scan_hits},
            }
        )
    finally:
        cleanup = cleanup_smoke_outputs(repo_root, run_id)
        result["cleanup"] = cleanup
        if command_results:
            command_results.append({"label": "cleanup", "ok": True, "removed": cleanup})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root")
    parser.add_argument(
        "--include-live-stage2-source-review",
        action="store_true",
        help="Also run the explicit live DeepSeek-compatible Stage 2 source-review smoke.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()
    repo_root = repo_root_from_arg(args.repo_root)
    result = run_stage_0_5_smoke(
        repo_root,
        include_live_stage2_source_review=args.include_live_stage2_source_review,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"stage 0-5 smoke: {'ok' if result.get('ok') else 'failed'}")
        for item in result.get("commands") or []:
            print(f"- {item.get('label')}: {'ok' if item.get('ok') else 'failed'}")
        if result.get("sync"):
            print(f"- sync_local_folder_smoke: {'ok' if result['sync'].get('ok') else 'failed'}")
        print(f"- secret_scan: {'ok' if (result.get('secret_scan') or {}).get('ok') else 'failed'}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
