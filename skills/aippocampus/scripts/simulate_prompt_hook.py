#!/usr/bin/env python3
"""Run a small regression suite against the ambient recall prompt hook."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from aippocampus_prompt_hook import assess_prompt


DEFAULT_CASES: list[dict[str, Any]] = [
    {
        "name": "go_runtime_decision",
        "prompt": "T-SENSE 现在是不是应该重写 Go runtime？",
        "allow_decisions": ["scent", "evidence"],
        "expect_candidate_contains": "T-Sense",
    },
    {
        "name": "gogram_gotd_choice",
        "prompt": "gogram 和 gotd/td 这两个库你觉得哪个更适合？",
        "allow_decisions": ["scent", "evidence"],
        "expect_candidate_contains": "T-Sense",
    },
    {
        "name": "runtime_language_natural",
        "prompt": "我还是觉得本地 runtime 现在换语言可能更好",
        "allow_decisions": ["scent", "evidence"],
    },
    {
        "name": "explicit_memory",
        "prompt": "你之前说过 T-SENSE 为什么不该正面做 Telegram 客户端吗？",
        "allow_decisions": ["evidence", "scent"],
    },
    {
        "name": "ordinary_code_surface",
        "prompt": "把 dashboard 的按钮 hover 样式改一下，顺手跑测试",
        "expect_decision": "skip",
    },
    {
        "name": "short_continue",
        "prompt": "好，继续",
        "expect_decision": "skip",
    },
    {
        "name": "unrelated_daily",
        "prompt": "晚上吃什么比较好？",
        "expect_decision": "skip",
    },
]


def load_cases(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return DEFAULT_CASES
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        rows = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        return rows
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("cases") or []
    return [item for item in data if isinstance(item, dict)]


def decision_ok(result: dict[str, Any], case: dict[str, Any]) -> tuple[bool, str]:
    decision = result.get("decision")
    if case.get("expect_decision") and decision != case.get("expect_decision"):
        return False, f"expected {case.get('expect_decision')}, got {decision}"
    allowed = case.get("allow_decisions")
    if allowed and decision not in allowed:
        return False, f"expected one of {allowed}, got {decision}"
    needle = str(case.get("expect_candidate_contains") or "").casefold()
    if needle:
        haystack = "\n".join(
            str(item.get("title") or "") + "\n" + " ".join(str(value) for value in item.get("matched_terms") or [])
            for item in result.get("candidates") or []
        ).casefold()
        if needle not in haystack:
            return False, f"candidate does not contain {case.get('expect_candidate_contains')!r}"
    return True, ""


def run_cases(
    cases: list[dict[str, Any]],
    *,
    cwd: Path,
    registry_path: Path | None,
    registry_dir: Path | None,
    associations_path: Path | None,
    concept_graph_path: Path | None,
    use_concept_graph: bool,
    search_budget: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        result = assess_prompt(
            str(case.get("prompt") or ""),
            cwd=cwd,
            registry_path=registry_path,
            registry_dir=registry_dir,
            associations_path=associations_path,
            concept_graph_path=concept_graph_path,
            use_concept_graph=use_concept_graph,
            search_budget=search_budget,
        )
        ok, reason = decision_ok(result, case)
        top = (result.get("candidates") or [{}])[0]
        rows.append(
            {
                "name": case.get("name") or case.get("prompt"),
                "ok": ok,
                "reason": reason,
                "decision": result.get("decision"),
                "score": result.get("score"),
                "top_candidate": top.get("title"),
                "top_thread_key": top.get("thread_key"),
                "evidence_count": len(result.get("evidence") or []),
                "concept_expansion_count": len(result.get("concept_expansions") or []),
                "concept_expansions": [
                    item.get("term")
                    for item in (result.get("concept_expansions") or [])[:5]
                ],
                "elapsed_ms": result.get("elapsed_ms"),
                "reasons": result.get("reasons") or [],
            }
        )
    failed = [row for row in rows if not row["ok"]]
    return {
        "case_count": len(rows),
        "passed": len(rows) - len(failed),
        "failed": len(failed),
        "rows": rows,
    }


def print_table(result: dict[str, Any]) -> None:
    print(f"cases: {result['case_count']} | passed: {result['passed']} | failed: {result['failed']}")
    for row in result["rows"]:
        mark = "OK" if row["ok"] else "FAIL"
        top = row.get("top_candidate") or "-"
        reason = f" | {row['reason']}" if row.get("reason") else ""
        print(f"- {mark} {row['name']} -> {row['decision']} ({row['score']}) | {top}{reason}")


def compare_results(enabled: dict[str, Any], disabled: dict[str, Any]) -> dict[str, Any]:
    disabled_by_name = {row["name"]: row for row in disabled.get("rows") or []}
    rows: list[dict[str, Any]] = []
    for row in enabled.get("rows") or []:
        base = disabled_by_name.get(row["name"]) or {}
        rows.append(
            {
                "name": row["name"],
                "decision_before": base.get("decision"),
                "decision_after": row.get("decision"),
                "top_before": base.get("top_candidate"),
                "top_after": row.get("top_candidate"),
                "score_before": base.get("score"),
                "score_after": row.get("score"),
                "concept_expansions": row.get("concept_expansions") or [],
                "changed": (
                    base.get("decision") != row.get("decision")
                    or base.get("top_candidate") != row.get("top_candidate")
                    or (row.get("concept_expansion_count") or 0) > 0
                ),
            }
        )
    return {
        "case_count": enabled.get("case_count"),
        "changed": sum(1 for row in rows if row["changed"]),
        "before": disabled,
        "after": enabled,
        "rows": rows,
    }


def print_compare(result: dict[str, Any]) -> None:
    print(f"cases: {result['case_count']} | changed/expanded: {result['changed']}")
    for row in result["rows"]:
        mark = "CHANGED" if row["changed"] else "same"
        expansions = ", ".join(str(item) for item in row.get("concept_expansions") or [])
        tail = f" | concepts: {expansions}" if expansions else ""
        print(
            f"- {mark} {row['name']}: "
            f"{row.get('decision_before')} -> {row.get('decision_after')} | "
            f"{row.get('top_before') or '-'} -> {row.get('top_after') or '-'}{tail}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", help="JSON or JSONL cases. Defaults to built-in smoke cases.")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--associations")
    parser.add_argument("--concept-graph")
    parser.add_argument("--no-concept-graph", action="store_true")
    parser.add_argument("--compare-concept-graph", action="store_true")
    parser.add_argument("--search-budget", type=int, default=3)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when any case fails.")
    args = parser.parse_args()

    cases = load_cases(Path(args.fixture).resolve() if args.fixture else None)
    common = {
        "cwd": Path(args.cwd).resolve(),
        "registry_path": Path(args.registry).resolve() if args.registry else None,
        "registry_dir": Path(args.registry_dir).resolve() if args.registry_dir else None,
        "associations_path": Path(args.associations).resolve() if args.associations else None,
        "concept_graph_path": Path(args.concept_graph).resolve() if args.concept_graph else None,
        "search_budget": args.search_budget,
    }
    if args.compare_concept_graph:
        disabled = run_cases(
            cases,
            use_concept_graph=False,
            **common,
        )
        enabled = run_cases(
            cases,
            use_concept_graph=not args.no_concept_graph,
            **common,
        )
        result = compare_results(enabled, disabled)
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print_compare(result)
        return 1 if args.strict and enabled["failed"] else 0

    result = run_cases(
        cases,
        use_concept_graph=not args.no_concept_graph,
        **common,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_table(result)
    return 1 if args.strict and result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
