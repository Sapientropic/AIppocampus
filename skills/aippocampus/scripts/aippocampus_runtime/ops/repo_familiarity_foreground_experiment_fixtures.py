#!/usr/bin/env python3
"""Public-safe fixtures for repo familiarity foreground experiment reports."""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.navigation import repo_familiarity
from aippocampus_runtime.ops.repo_familiarity_foreground_experiment import (
    build_repo_familiarity_foreground_experiment,
)


def _source_ref(path: str, line: int) -> dict[str, Any]:
    return {"path": path, "line": line}


def _source_row(
    *,
    kind: str,
    landmark: str,
    route_terms: list[str],
    boundary: str,
    route: dict[str, list[str]],
    source_path: str,
    source_line: int,
    first_source_to_reopen: str,
    source_hash: str = "",
    why_now: str,
    action_delta_required: str,
    stop_after: str,
    do_not_use_for: list[str] | None = None,
    repo_commit: str = "abc123",
    invalidation_files: list[dict[str, str]] | None = None,
    decision_shadow: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "landmark": landmark,
        "route_terms": route_terms,
        "boundary": boundary,
        "route": route,
        "decision_shadow": decision_shadow or {},
        "source_refs": [_source_ref(source_path, source_line)],
        "freshness": "current",
        "invalidation": {
            "commit": repo_commit,
            "files": invalidation_files
            or [{"path": first_source_to_reopen, "sha256": source_hash}],
        },
        "why_now": why_now,
        "action_delta_required": action_delta_required,
        "first_source_to_reopen": first_source_to_reopen,
        "stop_after": stop_after,
        "do_not_use_for": do_not_use_for or [],
    }


def fixture_source_rows() -> list[dict[str, Any]]:
    return [
        _source_row(
            kind="runtime_owner",
            landmark="foreground hook semantic budget",
            route_terms=["hook", "semantic", "budget"],
            boundary="Foreground hook must stay cheap and fail open.",
            route={
                "files": ["skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py"],
                "tests": ["tests/aippocampus/test_aippocampus_prompt_hook.py"],
            },
            source_path="docs/architecture/runtime/cognitive-runtime-architecture.md",
            source_line=160,
            first_source_to_reopen="skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py",
            source_hash="hash-hook",
            why_now="May affect hook timeout and route visibility decisions.",
            action_delta_required=(
                "Inspect hook prompt owner and hook tests before changing semantic budget."
            ),
            stop_after="Stop after hook owner and tests confirm the budget boundary.",
            do_not_use_for=["unrelated README/public readiness edits"],
        ),
        _source_row(
            kind="decision_shadow",
            landmark="rejected registry route card",
            route_terms=["registry", "rejected", "route"],
            boundary="Rejected-route hints require current source reopen before warning.",
            route={"tests": ["tests/aippocampus/test_coding_ticket_host_contract.py"]},
            source_path="docs/research/agent-coding-context-analysis.md",
            source_line=313,
            first_source_to_reopen="docs/research/agent-coding-context-analysis.md",
            source_hash="hash-coding",
            why_now="Relevant when a task may repeat an old rejected registry route.",
            action_delta_required="Check host contract before surfacing a rejected-route warning.",
            stop_after="Stop after source thickness and current visibility are checked.",
            do_not_use_for=["routine README edits"],
        ),
    ]


def _repo_rel(path: str | Path) -> str:
    return Path(path).as_posix()


def _git_commit(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return ""
    return result.stdout.strip()


def _file_sha256(repo_root: Path, repo_relative: str) -> str:
    return hashlib.sha256((repo_root / repo_relative).read_bytes()).hexdigest()


def _current_invalidation_files(repo_root: Path, *repo_relative_paths: str) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for repo_relative in sorted({_repo_rel(path) for path in repo_relative_paths}):
        if (repo_root / repo_relative).is_file():
            files.append(
                {
                    "path": repo_relative,
                    "sha256": _file_sha256(repo_root, repo_relative),
                }
            )
    return files


def _fingerprints_from_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    for row in rows:
        invalidation = row.get("invalidation")
        if not isinstance(invalidation, Mapping):
            continue
        files = invalidation.get("files")
        if not isinstance(files, list):
            continue
        for item in files:
            if not isinstance(item, Mapping):
                continue
            path = str(item.get("path") or "")
            digest = str(item.get("sha256") or "")
            if path and digest:
                fingerprints[path] = digest
    return fingerprints


def current_checkout_source_rows(
    repo_root: str | Path,
    *,
    repo_commit: str | None = None,
) -> list[dict[str, Any]]:
    return repo_familiarity.current_checkout_source_rows(
        repo_root,
        repo_commit=repo_commit,
    )


def current_checkout_cases(
    repo_root: str | Path,
    *,
    repo_commit: str | None = None,
) -> list[dict[str, Any]]:
    root = Path(repo_root).resolve()
    commit = repo_commit if repo_commit is not None else _git_commit(root)
    rows = current_checkout_source_rows(root, repo_commit=commit)
    fingerprints = _fingerprints_from_rows(rows)
    hook_path = _repo_rel("skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py")
    stale_fingerprints = dict(fingerprints)
    stale_fingerprints[hook_path] = "stale"
    return [
        {
            "case_id": "current_checkout_hook_budget_semantic_gate",
            "case_family": "repo_familiarity_current_checkout_orientation",
            "task": "Change prompt hook semantic budget without increasing foreground latency",
            "repo_commit": commit,
            "source_rows": rows,
            "expected_landmark": "foreground hook semantic budget",
            "expected_first_source": hook_path,
            "current_fingerprints": fingerprints,
            "stale_or_irrelevant_fingerprints": stale_fingerprints,
            "no_card_source_plan": [
                {
                    "query": "foreground prompt hook defaults",
                    "source_to_reopen": _repo_rel("docs/architecture/runtime-script-map.md"),
                    "useful": False,
                    "input_token_proxy": 6,
                    "elapsed_ms_proxy": 20,
                },
                {
                    "query": "hook semantic budget owner tests",
                    "source_to_reopen": hook_path,
                    "useful": True,
                    "input_token_proxy": 5,
                    "elapsed_ms_proxy": 20,
                },
            ],
            "expected_behavior": (
                "The current checkout case should select the same hook owner card from "
                "real public repo fingerprints and fast-reject it when the checkout hash "
                "is stale."
            ),
        }
    ]


def fixture_cases() -> list[dict[str, Any]]:
    rows = fixture_source_rows()
    return [
        {
            "case_id": "hook_budget_semantic_gate",
            "case_family": "repo_familiarity_foreground_orientation",
            "task": "Change prompt hook semantic budget without increasing foreground latency",
            "repo_commit": "abc123",
            "source_rows": rows,
            "expected_landmark": "foreground hook semantic budget",
            "expected_first_source": (
                "skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py"
            ),
            "current_fingerprints": {
                "skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py": "hash-hook"
            },
            "stale_or_irrelevant_fingerprints": {
                "skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py": "stale"
            },
            "no_card_source_plan": [
                {
                    "query": "foreground prompt hook defaults",
                    "source_to_reopen": "docs/architecture/runtime-script-map.md",
                    "useful": False,
                    "input_token_proxy": 6,
                    "elapsed_ms_proxy": 20,
                },
                {
                    "query": "hook semantic budget owner tests",
                    "source_to_reopen": (
                        "skills/aippocampus/scripts/aippocampus_runtime/hooks/prompt.py"
                    ),
                    "useful": True,
                    "input_token_proxy": 5,
                    "elapsed_ms_proxy": 20,
                },
            ],
            "expected_behavior": (
                "A selected familiarity card should name the hook owner first; a stale "
                "card should be rejected before becoming verification work."
            ),
        }
    ]


def fixture_foreground_experiment(
    *,
    max_cards: int = 1,
    max_packet_bytes: int = 1800,
) -> dict[str, Any]:
    return build_repo_familiarity_foreground_experiment(
        fixture_cases(),
        max_cards=max_cards,
        max_packet_bytes=max_packet_bytes,
    )


def current_checkout_foreground_experiment(
    repo_root: str | Path,
    *,
    max_cards: int = 1,
    max_packet_bytes: int = 1800,
) -> dict[str, Any]:
    return build_repo_familiarity_foreground_experiment(
        [*fixture_cases(), *current_checkout_cases(repo_root)],
        max_cards=max_cards,
        max_packet_bytes=max_packet_bytes,
    )


def case_by_id(cases: list[Mapping[str, Any]], case_id: str) -> Mapping[str, Any]:
    for case in cases:
        if str(case.get("case_id") or "") == case_id:
            return case
    return {}
