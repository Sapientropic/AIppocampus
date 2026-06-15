"""Issue-work active pull guard for foreground agents.

This module does not decide the task. It creates a compact route-first packet
when an issue is likely to depend on old AIppocampus design context. The point
is to prevent expensive long-running agents from inventing benchmark-local
scaffolding before they have checked the existing route owners.
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any, Iterable

SCHEMA_VERSION = "issue-work-active-pull-v0"

BENCHMARK_RE = re.compile(
    r"\b(longmemeval|benchmark|rerank|source[-_ ]side|semantic cache|"
    r"source_semantic_cache|evidence[-_ ]line)\b",
    re.I,
)
ARCHITECTURE_RE = re.compile(
    r"\b(attention router|semantic scope|subconscious|warm ambient|aippo|"
    r"macro orientation|architecture|design)\b",
    re.I,
)
TRIVIAL_RE = re.compile(r"\b(typo|spelling|formatting|link fix|rename only)\b", re.I)

OWNER_REFS: dict[str, dict[str, str]] = {
    "semantic_scope_labeling": {
        "kind": "subconscious_job",
        "path": "skills/aippocampus/references/subconscious-jobs.md",
    },
    "semantic_scope_builder": {
        "kind": "runtime_owner",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/recall/semantic_recall_gate.py",
    },
    "subconscious_jobs": {
        "kind": "runtime_owner",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/subconscious/jobs.py",
    },
    "warm_ambient_routes": {
        "kind": "runtime_owner",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/recall/ambient_cache.py",
    },
    "attention_router": {
        "kind": "runtime_owner",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/navigation/attention_hot_router.py",
    },
}


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _text(title: str, body: str = "") -> str:
    return f"{title}\n{body}".strip()


def classify_issue_work(title: str, body: str = "") -> list[str]:
    text = _text(title, body)
    categories: list[str] = []
    if BENCHMARK_RE.search(text):
        categories.append("benchmark_or_external_evaluation")
    if ARCHITECTURE_RE.search(text):
        categories.append("architecture_or_memory_design")
    if TRIVIAL_RE.search(text) and not categories:
        categories.append("trivial_local_edit")
    return categories


def build_issue_active_pull_packet(
    *,
    title: str,
    body: str = "",
    changed_files: Iterable[str] = (),
    lesson_constraints: Iterable[str] = (),
) -> dict[str, Any]:
    categories = classify_issue_work(title, body)
    changed = list(changed_files)
    path_text = "\n".join(changed)
    benchmark_like = "benchmark_or_external_evaluation" in categories or BENCHMARK_RE.search(path_text)
    architecture_like = "architecture_or_memory_design" in categories or ARCHITECTURE_RE.search(path_text)
    should_pull = bool(benchmark_like or architecture_like)

    if not should_pull:
        return {
            "kind": "aippocampus_issue_work_orientation_packet",
            "schema_version": SCHEMA_VERSION,
            "should_pull": False,
            "output_mode": "silence",
            "suggested_agent_action": "continue_without_recall",
            "lead_kinds": [],
            "existing_owner_refs": [],
            "existing_owner_ref_ids": [],
            "constraints": [],
            "claim_permission": "navigation_only_not_fact",
        }

    owner_ids: list[str] = []
    if benchmark_like:
        owner_ids.extend(
            [
                "semantic_scope_labeling",
                "semantic_scope_builder",
                "subconscious_jobs",
                "warm_ambient_routes",
                "attention_router",
            ]
        )
    elif architecture_like:
        owner_ids.extend(["attention_router", "semantic_scope_builder"])
    owner_ids = _unique(owner_ids)

    constraints = [
        "check_existing_routes_before_manual_benchmark_scaffold",
        *lesson_constraints,
    ]
    lead_kinds = ["memory_route", "aippo_working_contract"]
    if benchmark_like:
        lead_kinds.append("benchmark_capability_provenance")

    return {
        "kind": "aippocampus_issue_work_orientation_packet",
        "schema_version": SCHEMA_VERSION,
        "should_pull": True,
        "output_mode": "reopenable_route",
        "suggested_agent_action": "agent_recall",
        "lead_kinds": _unique(lead_kinds),
        "existing_owner_refs": [OWNER_REFS[item] | {"id": item} for item in owner_ids],
        "existing_owner_ref_ids": owner_ids,
        "constraints": _unique(constraints),
        "active_pull_required_before": [
            "implementation",
            "benchmark_claim",
            "issue_closeout",
        ],
        "route_first_questions": [
            "Which AIppocampus runtime path already owns this capability?",
            "Is this score measuring that path or benchmark-local scaffolding?",
            "What follow-up remains if this is only a proxy or isolated experiment?",
        ],
        "claim_permission": "navigation_only_not_fact",
        "not_enough_for_claim": True,
    }


def build_issue_work_guard_fixture_report() -> dict[str, Any]:
    cases = [
        {
            "case_id": "ignored_ambient_scent_benchmark_agent",
            "packet": build_issue_active_pull_packet(
                title="Fix LongMemEval source-side semantic cache benchmark",
                body="The agent should use existing semantic scope and warm ambient owners.",
            ),
        },
        {
            "case_id": "architecture_design_issue",
            "packet": build_issue_active_pull_packet(
                title="Wire Attention Router to benchmark capability provenance",
                body="Architecture closeout needs route-first context.",
            ),
        },
        {
            "case_id": "trivial_typo",
            "packet": build_issue_active_pull_packet(
                title="Fix typo in README",
                body="One spelling correction.",
            ),
        },
    ]
    active = [case for case in cases if case["packet"]["should_pull"]]
    silent = [case for case in cases if not case["packet"]["should_pull"]]
    red_lines = {
        "broad_manual_search_before_route_count": 0,
        "packet_contains_fact_claim_count": 0,
    }
    return {
        "kind": "aippocampus_issue_work_guard_fixture",
        "schema_version": SCHEMA_VERSION,
        "ok": all(value == 0 for value in red_lines.values()) and len(active) == 2 and len(silent) == 1,
        "metrics": {
            "case_count": len(cases),
            "active_pull_required_count": len(active),
            "trivial_silence_count": len(silent),
        },
        "red_lines": red_lines,
        "cases": cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aippocampus work-guard")
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", default="")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--fixture-report", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    payload = (
        build_issue_work_guard_fixture_report()
        if args.fixture_report
        else build_issue_active_pull_packet(
            title=args.title,
            body=args.body,
            changed_files=args.changed_file,
        )
    )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
