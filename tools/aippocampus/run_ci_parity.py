#!/usr/bin/env python3
"""Run an opt-in local test lane with the canonical CI Python minor."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
FALLBACK_CANONICAL_CI_PYTHON = "3.12"
KIND = "aippocampus_ci_python_parity"
CI_PYTHON_ENV = "AIPPOCAMPUS_CI_PYTHON"


def canonical_python_minor() -> str:
    try:
        data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return FALLBACK_CANONICAL_CI_PYTHON
    value = (
        data.get("tool", {})
        .get("mypy", {})
        .get("python_version")
    )
    if isinstance(value, str) and value.count(".") >= 1:
        return ".".join(value.split(".")[:2])
    return FALLBACK_CANONICAL_CI_PYTHON


def _configured_python_commands() -> list[list[str]]:
    configured = os.environ.get(CI_PYTHON_ENV)
    if not configured:
        return []
    executable = configured.strip().strip('"')
    return [[executable]] if executable else []


def _codex_bundled_python_commands() -> list[list[str]]:
    runtime_root = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "python"
    )
    candidates = [
        runtime_root / "python.exe",
        runtime_root / "bin" / "python",
        runtime_root / "bin" / "python3",
    ]
    return [[str(path)] for path in candidates if path.exists()]


def _candidate_python_commands(minor: str) -> list[list[str]]:
    candidates: list[list[str]] = []
    candidates.extend(_configured_python_commands())
    candidates.extend(_codex_bundled_python_commands())
    if os.name == "nt":
        candidates.append(["py", f"-{minor}"])
    candidates.extend(
        [
            [f"python{minor}"],
            [f"python{minor.replace('.', '')}"],
            ["python"],
        ]
    )
    return candidates


def _command_minor(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            [
                *command,
                "-c",
                "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def find_python_for_minor(minor: str) -> list[str] | None:
    for command in _candidate_python_commands(minor):
        if _command_minor(command) == minor:
            return command
    return None


def recovery_card(*, minor: str) -> dict[str, Any]:
    return {
        "kind": KIND,
        "ok": False,
        "status": "python_minor_unavailable",
        "canonical_python_minor": minor,
        "summary": f"Python {minor} was not found for the opt-in CI parity lane.",
        "recovery_actions": [
            f"Set {CI_PYTHON_ENV} to a Python {minor} executable if one is bundled by the host.",
            f"Install Python {minor} and rerun this command.",
            "Let GitHub Actions remain the platform compatibility authority.",
            "Use local ruff, mypy, focused tests, and PR gate for ordinary iteration.",
        ],
        "boundary": "This is an opt-in compatibility lane, not a default local matrix.",
    }


def parity_command(*, python_command: list[str], tier: str) -> list[str]:
    return [
        *python_command,
        str(REPO_ROOT / "tools" / "aippocampus" / "run_tests.py"),
        "--tier",
        tier,
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an opt-in AIppocampus local test lane with the canonical CI Python minor.",
    )
    parser.add_argument("--tier", default="pr", help="run_tests.py tier to execute; default: pr")
    parser.add_argument("--python-minor", default=canonical_python_minor())
    parser.add_argument("--dry-run", action="store_true", help="print the selected command without running it")
    parser.add_argument("--json", action="store_true", help="emit a JSON summary")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    minor = str(args.python_minor)
    python_command = find_python_for_minor(minor)
    if python_command is None:
        card = recovery_card(minor=minor)
        if args.json:
            print(json.dumps(card, ensure_ascii=False, indent=2))
        else:
            print(card["summary"])
            for action in card["recovery_actions"]:
                print(f"- {action}")
        return 2

    command = parity_command(python_command=python_command, tier=str(args.tier))
    payload = {
        "kind": KIND,
        "ok": True,
        "status": "ready" if args.dry_run else "running",
        "canonical_python_minor": minor,
        "command": command,
        "boundary": "Opt-in CI-minor parity lane; do not add it to ordinary local gates.",
    }
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else " ".join(command))
        return 0

    completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
    if args.json:
        payload["status"] = "passed" if completed.returncode == 0 else "failed"
        payload["exit_code"] = completed.returncode
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
