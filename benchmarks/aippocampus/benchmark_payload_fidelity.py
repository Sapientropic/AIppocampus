#!/usr/bin/env python3
"""Benchmark final hook payload fidelity for AIppocampus recall decisions."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.hooks import prompt as hook
from benchmark_memory_decision_gate import (
    EXPECTED_TO_ACTUAL,
    GateCase,
    SyntheticFixture,
    build_synthetic_fixture,
    normalize_actual_decision,
    safe_rate,
    sha1_text,
    summarize_memory_pain_fixtures,
)

SCHEMA_VERSION = 1
ABSOLUTE_PATH_RE = re.compile(r"[A-Za-z]:\\")
EXPECTED_LABELS = frozenset(EXPECTED_TO_ACTUAL)
ACTUAL_DECISIONS = frozenset(EXPECTED_TO_ACTUAL.values())


@dataclass(frozen=True)
class PayloadCase:
    gate_case: GateCase
    expected_source_line: int | None = None
    forbidden_terms: tuple[str, ...] = ()


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_parked_working_memory(fixture: SyntheticFixture) -> None:
    path = fixture.working_memory_path
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    parked = {
        "kind": "aippocampus_working_memory",
        "status": "parked",
        "route": "use_with_source",
        "ask_policy": "do_not_surface",
        "risk": "high",
        "candidate_type": "project_memory",
        "title": "ParkedSecret mutation rule",
        "summary": "This parked candidate must never be injected into foreground context.",
        "recommendation": "Do not use.",
        "confidence": 0.99,
        "project_label": "AIppocampus",
        "trigger_terms": ["ParkedSecret", "parked mutation"],
        "source_refs": [{"thread_key": "session:synthetic-memory", "line": 999}],
    }
    path.write_text(
        existing + json.dumps(parked, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def payload_cases(fixture: SyntheticFixture) -> list[PayloadCase]:
    append_parked_working_memory(fixture)
    cases = [
        PayloadCase(case)
        for case in fixture.cases
        if case.expected in {"should_skip", "should_scent", "should_evidence"}
    ]
    cases.append(
        PayloadCase(
            GateCase(
                case_id="synthetic_skip_parked_working_memory",
                case_type="parked_working_memory_trap",
                expected="should_skip",
                prompt="ParkedSecret mutation flow 现在怎么处理？",
                search_budget=0,
                working_memory=True,
            ),
            forbidden_terms=("ParkedSecret", "ParkedSecret mutation rule"),
        )
    )
    return [
        PayloadCase(
            case.gate_case,
            expected_source_line=190
            if case.gate_case.case_id == "synthetic_evidence_explicit_quote"
            else case.expected_source_line,
            forbidden_terms=case.forbidden_terms,
        )
        for case in cases
    ]


def run_prompt(case: GateCase, fixture: SyntheticFixture) -> dict[str, Any]:
    def semantic_gate_disabled(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "available": False,
            "decision": "skip",
            "confidence": 0.0,
            "query_aliases": [],
            "memory_scope": [],
            "reasons": ["synthetic payload benchmark disabled semantic gate"],
            "workers": [],
            "errors": [],
            "cached": False,
        }

    return hook.assess_prompt(
        case.prompt,
        cwd=fixture.workspace,
        registry_path=fixture.registry_path,
        working_memory_path=fixture.working_memory_path if case.working_memory else None,
        search_budget=case.search_budget,
        use_semantic_gate=case.use_semantic_gate,
        semantic_gate_fn=semantic_gate_disabled,
    )


def source_fidelity_ok(
    payload_case: PayloadCase,
    result: dict[str, Any],
    context: str | None,
) -> bool:
    if payload_case.expected_source_line is None:
        return True
    if not context:
        return False
    evidence = result.get("evidence") or []
    return any(int(item.get("line") or -1) == payload_case.expected_source_line for item in evidence)


def evidence_without_source(result: dict[str, Any], context: str | None) -> bool:
    evidence = result.get("evidence") or []
    if not evidence:
        return False
    has_source_line = any(item.get("line") for item in evidence)
    return not has_source_line or not context or "Ambient recall evidence" not in context


def payload_correct_for_expected(
    expected: str,
    actual: str,
    result: dict[str, Any],
    context: str | None,
) -> bool:
    expected_actual = EXPECTED_TO_ACTUAL[expected]
    if actual != expected_actual:
        return False
    evidence_count = len(result.get("evidence") or [])
    working_count = len(result.get("working_memory") or [])
    if expected == "should_skip":
        return context is None and evidence_count == 0 and working_count == 0
    if expected == "should_scent":
        return bool(context) and evidence_count == 0 and "Ambient recall evidence" not in context
    if expected == "should_evidence":
        return bool(context) and evidence_count > 0 and "Ambient recall evidence" in context
    return False


def evaluate_payload_case(
    payload_case: PayloadCase,
    fixture: SyntheticFixture,
    *,
    include_private_text: bool,
) -> dict[str, Any]:
    case = payload_case.gate_case
    if case.expected not in EXPECTED_LABELS:
        raise ValueError(f"unsupported expected label: {case.expected}")
    result = run_prompt(case, fixture)
    context = hook.context_for_hook(result)
    actual = normalize_actual_decision(result.get("decision"))
    if actual not in ACTUAL_DECISIONS:
        raise ValueError(f"unsupported actual decision: {actual}")
    decision_correct = actual == EXPECTED_TO_ACTUAL[case.expected]
    parked_injected = bool(
        context
        and any(term and term in context for term in payload_case.forbidden_terms)
    )
    evidence_missing_source = evidence_without_source(result, context)
    source_ok = source_fidelity_ok(payload_case, result, context)
    privacy_breach = bool(context and ABSOLUTE_PATH_RE.search(context))
    payload_correct = (
        payload_correct_for_expected(case.expected, actual, result, context)
        and source_ok
        and not parked_injected
        and not evidence_missing_source
        and not privacy_breach
    )
    row: dict[str, Any] = {
        "case_id": case.case_id,
        "case_type": case.case_type,
        "expected": case.expected,
        "actual": actual,
        "decision_correct": decision_correct,
        "payload_correct": payload_correct,
        "source_fidelity": source_ok,
        "privacy_breach": privacy_breach,
        "parked_memory_injected": parked_injected,
        "evidence_without_source": evidence_missing_source,
        "prompt_sha1": sha1_text(case.prompt)[:16],
        "context_sha1": sha1_text(context or "")[:16],
        "context_present": bool(context),
        "context_chars": len(context or ""),
        "evidence_count": len(result.get("evidence") or []),
        "working_memory_count": len(result.get("working_memory") or []),
        "expected_source_line_present": source_ok if payload_case.expected_source_line else None,
        "elapsed_ms": result.get("elapsed_ms"),
    }
    if case.memory_pain_family:
        row.update(case.to_result_stub(include_private_text=False))
    if include_private_text:
        row["prompt"] = case.prompt
        row["context"] = context
    return row


def summarize_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    payload_correct = sum(1 for row in rows if row.get("payload_correct"))
    decision_correct = sum(1 for row in rows if row.get("decision_correct"))
    source_ok = sum(1 for row in rows if row.get("source_fidelity"))
    privacy_breach = sum(1 for row in rows if row.get("privacy_breach"))
    parked = sum(1 for row in rows if row.get("parked_memory_injected"))
    evidence_without = sum(1 for row in rows if row.get("evidence_without_source"))
    by_type: dict[str, int] = {}
    for row in rows:
        case_type = str(row.get("case_type") or "unknown")
        by_type[case_type] = by_type.get(case_type, 0) + 1
    return {
        "total_cases": total,
        "case_types": by_type,
        "decision_correct_count": decision_correct,
        "decision_accuracy": safe_rate(decision_correct, total),
        "payload_correct_count": payload_correct,
        "payload_correct_rate": safe_rate(payload_correct, total),
        "source_fidelity_count": source_ok,
        "source_fidelity_rate": safe_rate(source_ok, total),
        "privacy_breach_count": privacy_breach,
        "privacy_breach_rate": safe_rate(privacy_breach, total),
        "parked_memory_injection_count": parked,
        "evidence_without_source_count": evidence_without,
    }


def run_benchmark(
    *,
    include_private_text: bool = False,
    case_limit: int | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="aippocampus-payload-benchmark-") as tmp:
        fixture = build_synthetic_fixture(Path(tmp))
        cases = payload_cases(fixture)
        if case_limit and case_limit > 0:
            cases = cases[:case_limit]
        rows = [
            evaluate_payload_case(case, fixture, include_private_text=include_private_text)
            for case in cases
        ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_payload_fidelity_benchmark",
        "generated_at": now_utc(),
        "config": {
            "case_set": "synthetic",
            "case_limit": case_limit,
            "include_private_text": include_private_text,
            "live_llm": False,
        },
        "metrics": summarize_results(rows),
        "memory_pain_fixtures": summarize_memory_pain_fixtures(
            rows,
            include_private_text=include_private_text,
        ),
        "cases": rows,
        "privacy_boundary": {
            "raw_prompt_emitted": bool(include_private_text),
            "raw_context_emitted": bool(include_private_text),
            "snippets_emitted": bool(include_private_text),
            "absolute_paths_emitted": False,
            "output_shape": "sanitized_payload_fidelity_aggregates",
        },
        "cannot_claim": [
            "real_history_payload_fidelity",
            "live_semantic_model_quality",
            "external_baseline_comparison",
            "competitor_superiority",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "ok": True,
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    metrics = payload["metrics"]
    print("AIppocampus payload fidelity benchmark")
    print(
        f"cases: {metrics['total_cases']} payload_correct: {metrics['payload_correct_rate']} "
        f"source_fidelity: {metrics['source_fidelity_rate']}"
    )
    print(
        "privacy_breach: {privacy} parked_injection: {parked} evidence_without_source: {evidence}".format(
            privacy=metrics["privacy_breach_count"],
            parked=metrics["parked_memory_injection_count"],
            evidence=metrics["evidence_without_source_count"],
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=None)
    parser.add_argument("--include-private-text", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payload = run_benchmark(
        include_private_text=args.include_private_text,
        case_limit=args.cases,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
