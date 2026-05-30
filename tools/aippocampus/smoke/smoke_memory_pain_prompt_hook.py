#!/usr/bin/env python3
"""Sanitized real-history smoke for memory-pain prompt-hook boundaries.

This runner is intentionally aggregate/hash-only. It may run against a private
real registry, so it must not print prompts, snippets, thread ids, candidate
titles, source refs, or hook reasons.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_prompt_hook import assess_prompt  # noqa: E402

DEFAULT_CASES: list[dict[str, Any]] = [
    {
        "name": "neg_structured_extraction_without_cited_row",
        "kind": "negative",
        "prompt": (
            "Could you keep the structured extraction about Neon City unsupported "
            "without a cited row?"
        ),
    },
    {
        "name": "neg_fake_fact_without_source_backing",
        "kind": "negative",
        "prompt": (
            "Treat the claim that the user moved to Neon City as unsupported "
            "unless there is source-backed evidence."
        ),
    },
    {
        "name": "neg_transient_status_without_clean_source",
        "kind": "negative",
        "prompt": (
            "The active task status says Atlas dashboard spacing is fixed; "
            "keep it unsupported without clean source evidence."
        ),
    },
    {
        "name": "neg_no_citation_context_only",
        "kind": "negative",
        "prompt": (
            "Memory-pain boundary check: continue the raw-history topic with no "
            "citation and no evidence."
        ),
    },
    {
        "name": "pos_natural_external_hippocampus_wording",
        "kind": "positive",
        "prompt": "找一下之前说外置海马体和触发式召回的那段怎么说的来着？",
    },
    {
        "name": "pos_raw_history_local_wording",
        "kind": "positive",
        "prompt": "上次说 raw history 明明在本地但压缩后不知道找什么，那句原话是什么？",
    },
    {
        "name": "vague_cross_project_last_solution",
        "kind": "vague",
        "prompt": "上次我们讨论的那个方案怎么说来着？",
    },
    {
        "name": "vague_current_thread_status",
        "kind": "vague",
        "prompt": "那个现在做到哪了？",
    },
]


def stable_hash(value: str, *, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def load_cases(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return DEFAULT_CASES
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        cases: list[dict[str, Any]] = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                cases.append(item)
        return cases
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("cases") or []
    return [item for item in data if isinstance(item, dict)]


def semantic_summary(result: dict[str, Any]) -> dict[str, Any]:
    semantic = result.get("semantic_gate") or {}
    return {
        "available": bool(semantic.get("available")),
        "decision": str(semantic.get("decision") or "none"),
        "availability_reason": semantic.get("availability_reason"),
        "diagnostic": semantic.get("diagnostic"),
        "error_buckets": semantic.get("error_buckets") or {},
    }


def safe_row(
    *,
    case: dict[str, Any],
    result: dict[str, Any],
    show_names: bool,
) -> dict[str, Any]:
    name = str(case.get("name") or "")
    prompt = str(case.get("prompt") or "")
    kind = str(case.get("kind") or "unspecified")
    row: dict[str, Any] = {
        "case_hash": stable_hash(name + "\n" + prompt),
        "kind": kind,
        "decision": result.get("decision"),
        "confidence": result.get("confidence"),
        "score": result.get("score"),
        "candidate_count": len(result.get("candidates") or []),
        "evidence_count": len(result.get("evidence") or []),
        "semantic_gate": semantic_summary(result),
        "semantic_bridge_diagnostic": result.get("semantic_bridge_diagnostic"),
        "elapsed_ms": result.get("elapsed_ms"),
    }
    if show_names:
        row["name"] = name
    return row


def classify_issues(row: dict[str, Any]) -> list[str]:
    kind = str(row.get("kind") or "")
    evidence_count = int(row.get("evidence_count") or 0)
    decision = str(row.get("decision") or "")
    issues: list[str] = []
    if kind == "negative" and evidence_count > 0:
        issues.append("negative_over_escalation")
    if kind == "vague" and evidence_count > 0:
        issues.append("vague_evidence")
    if kind == "positive" and decision != "evidence":
        issues.append("positive_miss")
    if row.get("semantic_bridge_diagnostic"):
        issues.append(str(row["semantic_bridge_diagnostic"]))
    return issues


def run_memory_pain_smoke(
    cases: list[dict[str, Any]],
    *,
    cwd: Path,
    registry_path: Path | None = None,
    registry_dir: Path | None = None,
    associations_path: Path | None = None,
    semantic_gate_mode: str = "off",
    semantic_timeout: float = 20.0,
    max_elapsed_ms: int | None = 4300,
    search_budget: int = 3,
    warm_background: bool = False,
    show_names: bool = False,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    issue_counts: Counter[str] = Counter()
    decision_counts: Counter[str] = Counter()
    semantic_decisions: Counter[str] = Counter()
    semantic_error_buckets: Counter[str] = Counter()
    semantic_available_count = 0
    evidence_total = 0

    for case in cases:
        try:
            result = assess_prompt(
                str(case.get("prompt") or ""),
                cwd=cwd,
                registry_path=registry_path,
                registry_dir=registry_dir,
                associations_path=associations_path,
                semantic_gate_mode=semantic_gate_mode,
                use_semantic_gate=semantic_gate_mode != "off",
                semantic_timeout=semantic_timeout,
                max_elapsed_ms=max_elapsed_ms,
                search_budget=search_budget,
                warm_background=warm_background,
            )
            row = safe_row(case=case, result=result, show_names=show_names)
        except Exception as exc:  # pragma: no cover - defensive CLI boundary
            row = {
                "case_hash": stable_hash(
                    str(case.get("name") or "") + "\n" + str(case.get("prompt") or "")
                ),
                "kind": str(case.get("kind") or "unspecified"),
                "decision": "error",
                "confidence": "low",
                "score": 0.0,
                "candidate_count": 0,
                "evidence_count": 0,
                "semantic_gate": {
                    "available": False,
                    "decision": "none",
                    "availability_reason": None,
                    "diagnostic": None,
                    "error_buckets": {},
                },
                "semantic_bridge_diagnostic": None,
                "elapsed_ms": None,
                "error_type": exc.__class__.__name__,
            }
            if show_names:
                row["name"] = str(case.get("name") or "")
        row["issues"] = classify_issues(row)
        rows.append(row)

        decision_counts.update([str(row.get("decision") or "none")])
        evidence_total += int(row.get("evidence_count") or 0)
        issue_counts.update(row["issues"])
        semantic = row.get("semantic_gate") or {}
        semantic_decisions.update([str(semantic.get("decision") or "none")])
        if semantic.get("available"):
            semantic_available_count += 1
        semantic_error_buckets.update(semantic.get("error_buckets") or {})

    unsafe_issue_count = sum(
        issue_counts[name] for name in ("negative_over_escalation", "vague_evidence")
    )
    return {
        "kind": "aippocampus_memory_pain_prompt_hook_smoke",
        "privacy": "aggregate_hash_only",
        "case_count": len(rows),
        "decision_counts": dict(sorted(decision_counts.items())),
        "evidence_total": evidence_total,
        "issue_counts": dict(sorted(issue_counts.items())),
        "unsafe_issue_count": unsafe_issue_count,
        "positive_miss_count": issue_counts.get("positive_miss", 0),
        "semantic": {
            "available_count": semantic_available_count,
            "decision_counts": dict(sorted(semantic_decisions.items())),
            "error_buckets": dict(sorted(semantic_error_buckets.items())),
        },
        "rows": rows,
        "ok": unsafe_issue_count == 0,
    }


def print_table(result: dict[str, Any]) -> None:
    print(
        "memory-pain prompt smoke: "
        f"{'ok' if result.get('ok') else 'failed'} | "
        f"cases={result['case_count']} | evidence={result['evidence_total']} | "
        f"unsafe={result['unsafe_issue_count']} | positive_misses={result['positive_miss_count']}"
    )
    for row in result.get("rows") or []:
        issues = ",".join(row.get("issues") or []) or "-"
        print(
            f"- {row['case_hash']} {row['kind']} -> {row['decision']} "
            f"evidence={row['evidence_count']} issues={issues}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", help="JSON or JSONL cases; output remains hash-only.")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--associations")
    parser.add_argument("--semantic-gate", choices=("off", "auto", "on"), default="off")
    parser.add_argument("--semantic-timeout", type=float, default=20.0)
    parser.add_argument("--max-elapsed-ms", type=int, default=4300)
    parser.add_argument("--search-budget", type=int, default=3)
    parser.add_argument("--warm-background", action="store_true")
    parser.add_argument("--show-names", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--require-positive-evidence",
        action="store_true",
        help="With --strict, also fail when positive probes do not reach evidence.",
    )
    args = parser.parse_args()

    cases = load_cases(Path(args.fixture).resolve() if args.fixture else None)
    result = run_memory_pain_smoke(
        cases,
        cwd=Path(args.cwd).resolve(),
        registry_path=Path(args.registry).resolve() if args.registry else None,
        registry_dir=Path(args.registry_dir).resolve() if args.registry_dir else None,
        associations_path=Path(args.associations).resolve() if args.associations else None,
        semantic_gate_mode=args.semantic_gate,
        semantic_timeout=args.semantic_timeout,
        max_elapsed_ms=args.max_elapsed_ms,
        search_budget=args.search_budget,
        warm_background=args.warm_background,
        show_names=args.show_names,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_table(result)
    strict_failed = not result["ok"] or (
        args.require_positive_evidence and result["positive_miss_count"] > 0
    )
    return 1 if args.strict and strict_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
