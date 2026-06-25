#!/usr/bin/env python3
"""Windows-safe advisory mutation smoke for product-semantics tests.

The smoke copies the installable runtime to a temporary overlay, mutates a tiny
target set there, and runs the real tests against that overlay. It never edits
the working tree and does not require fork support, so it can stay a manual
advisory lane on native Windows instead of pulling mutmut into the default loop.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_SOURCE_ROOT = REPO_ROOT / "skills" / "aippocampus" / "scripts"
RUNTIME_SOURCE_PREFIX = "skills/aippocampus/scripts/"
TARGET_TEST_MODULE = "tests.aippocampus.test_local_file_lock"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class MutantSpec:
    mutant_id: str
    issue: str
    target: str
    old: str
    new: str
    expected_test_module: str
    rationale: str


MUTANTS: tuple[MutantSpec, ...] = (
    MutantSpec(
        mutant_id="local_file_lock_release_owner_check_inverted",
        issue="#2691",
        target="skills/aippocampus/scripts/aippocampus_runtime/local_file_lock.py",
        old='        if payload.get("owner_token") != self.owner_token:\n',
        new='        if payload.get("owner_token") == self.owner_token:\n',
        expected_test_module=TARGET_TEST_MODULE,
        rationale=(
            "The lock tests must fail if release can delete or preserve the wrong "
            "owner generation."
        ),
    ),
    MutantSpec(
        mutant_id="local_file_lock_stale_threshold_direction_inverted",
        issue="#2691",
        target="skills/aippocampus/scripts/aippocampus_runtime/local_file_lock.py",
        old="                if age > self.stale_after_seconds:\n",
        new="                if age < self.stale_after_seconds:\n",
        expected_test_module=TARGET_TEST_MODULE,
        rationale=(
            "The lock tests must fail if active leases are recovered early or stale "
            "leases stay busy."
        ),
    ),
)


def _relative_runtime_target(target: str) -> Path:
    if not target.startswith(RUNTIME_SOURCE_PREFIX):
        raise ValueError(f"mutation target is outside runtime source root: {target}")
    return Path(target[len(RUNTIME_SOURCE_PREFIX) :])


def _copy_runtime_overlay(destination: Path) -> Path:
    overlay = destination / "scripts"
    shutil.copytree(
        RUNTIME_SOURCE_ROOT,
        overlay,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return overlay


def apply_mutation(overlay: Path, mutant: MutantSpec) -> dict[str, Any]:
    target = overlay / _relative_runtime_target(mutant.target)
    text = target.read_text(encoding="utf-8")
    occurrence_count = text.count(mutant.old)
    if occurrence_count != 1:
        return {
            "ok": False,
            "reason": "mutation_snippet_occurrence_count_not_one",
            "occurrence_count": occurrence_count,
            "target": mutant.target,
        }
    target.write_text(text.replace(mutant.old, mutant.new, 1), encoding="utf-8")
    return {"ok": True, "target": mutant.target}


def _tail(text: str, *, limit: int = 4000) -> str:
    return text[-limit:] if len(text) > limit else text


def _pythonpath_with_overlay(overlay: Path) -> str:
    parts = [str(overlay), str(REPO_ROOT)]
    existing = os.environ.get("PYTHONPATH")
    if existing:
        parts.append(existing)
    return os.pathsep.join(parts)


def run_mutant(mutant: MutantSpec, *, timeout_seconds: float) -> dict[str, Any]:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="aippocampus-mutation-smoke-") as tmp:
        overlay = _copy_runtime_overlay(Path(tmp))
        mutation = apply_mutation(overlay, mutant)
        if mutation.get("ok") is not True:
            return {
                **asdict(mutant),
                "status": "setup_failed",
                "killed": False,
                "duration_seconds": round(time.perf_counter() - started, 3),
                "mutation": mutation,
            }
        env = os.environ.copy()
        env["PYTHONPATH"] = _pythonpath_with_overlay(overlay)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", mutant.expected_test_module, "-v"],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    duration = round(time.perf_counter() - started, 3)
    killed = completed.returncode != 0
    return {
        **asdict(mutant),
        "status": "killed" if killed else "survived",
        "killed": killed,
        "returncode": completed.returncode,
        "duration_seconds": duration,
        "stdout_tail": _tail(completed.stdout),
        "stderr_tail": _tail(completed.stderr),
    }


def build_report(
    *,
    run: bool,
    mutant_ids: set[str] | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    selected = [
        mutant
        for mutant in MUTANTS
        if not mutant_ids or mutant.mutant_id in mutant_ids
    ]
    unknown = sorted((mutant_ids or set()) - {mutant.mutant_id for mutant in MUTANTS})
    if run:
        rows = [run_mutant(mutant, timeout_seconds=timeout_seconds) for mutant in selected]
    else:
        rows = [{**asdict(mutant), "status": "not_run", "killed": None} for mutant in selected]
    killed_count = sum(1 for row in rows if row.get("killed") is True)
    survived = [row for row in rows if row.get("killed") is False]
    setup_failed = [row for row in rows if row.get("status") == "setup_failed"]
    ok = not unknown and (not run or (not survived and killed_count == len(rows)))
    return {
        "kind": "aippocampus_mutation_smoke",
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "advisory": True,
        "mode": "run" if run else "dry_run",
        "platform_contract": {
            "windows_safe": True,
            "uses_fork": False,
            "working_tree_mutation": False,
            "default_gate": False,
        },
        "target_set": "local_file_lock_owner_identity",
        "test_command": f"{sys.executable} -m unittest {TARGET_TEST_MODULE} -v",
        "mutant_count": len(rows),
        "killed_count": killed_count,
        "survived_count": len(survived),
        "setup_failed_count": len(setup_failed),
        "unknown_mutants": unknown,
        "mutants": rows,
        "closeout_boundary": (
            "This is a tiny advisory smoke for test quality. Surviving mutants "
            "should become focused issue candidates, not unrelated PR failures."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AIppocampus advisory mutation smoke.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List selected mutants without running tests.",
    )
    parser.add_argument(
        "--mutant",
        action="append",
        choices=[mutant.mutant_id for mutant in MUTANTS],
        help="Run only a specific mutant id. May be repeated.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="Per-mutant subprocess timeout.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(
        run=not args.dry_run,
        mutant_ids=set(args.mutant or []),
        timeout_seconds=args.timeout_seconds,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"mutation smoke {report['mode']}: "
            f"killed={report['killed_count']}/{report['mutant_count']} "
            f"survived={report['survived_count']} setup_failed={report['setup_failed_count']}"
        )
        for row in report["mutants"]:
            print(f"- {row['mutant_id']}: {row['status']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
