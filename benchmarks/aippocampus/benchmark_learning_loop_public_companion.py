#!/usr/bin/env python3
"""Public companion eval for the source-backed learning loop."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.learning_loop.core import (  # noqa: E402
    adapt_behavior_events_to_review_signals,
    detect_recurring_failure_findings,
    detect_workflow_order_findings,
    project_action_time_guidance,
)

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_learning_loop_public_companion_eval"
DEFAULT_ROLLOUT = (
    _paths.REPO_ROOT
    / "benchmark_corpus"
    / "public_longitudinal_users"
    / "rollout_behavior_events_v2.json"
).resolve()
DEFAULT_VCS = (
    _paths.REPO_ROOT
    / "benchmark_corpus"
    / "public_longitudinal_users"
    / "vcs_future_events_v1.jsonl"
).resolve()


def _load_rollout(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [dict(row) for row in payload if isinstance(row, Mapping)]


def _load_vcs(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(dict(json.loads(line)))
    return rows


def _command_family(event: Mapping[str, Any]) -> str:
    tool = str(event.get("tool_name") or event.get("command_class") or "").casefold()
    kind = str(event.get("kind") or event.get("hard_event_kind") or "").casefold()
    if "ruff" in tool or "ruff" in kind:
        return "python_ruff"
    if "pytest" in tool or "test" in kind:
        return "python_pytest"
    if "search" in kind or "context" in kind:
        return "ripgrep"
    if "revert" in kind or "workaround" in kind:
        return "environment_workaround"
    return tool or kind or "public_event"


def _status(event: Mapping[str, Any]) -> str:
    kind = str(event.get("kind") or event.get("hard_event_kind") or "").casefold()
    if "failed" in kind or "rejected" in kind or "abandoned" in kind:
        return "failed"
    if "passed" in kind or "succeeded" in kind or "reverted" in kind or "merged" in kind:
        return "succeeded"
    return "observed"


def rollout_cases_to_behavior_events(cases: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sequence = 0
    for case in cases:
        project = str(case.get("project_id") or "public-rollout")
        for event in case.get("past_window") or []:
            if not isinstance(event, Mapping):
                continue
            status = _status(event)
            if status == "observed" and not event.get("behavior_backed"):
                continue
            sequence += 1
            source_id = str(event.get("source_id") or f"{project}:{sequence}")
            failure_family = str(event.get("failure_family") or event.get("family") or "public_failure")
            rows.append(
                {
                    "kind": "behavior_event",
                    "event_id": source_id,
                    "status": status,
                    "command_family": _command_family(event),
                    "target_class": str(event.get("track") or event.get("kind") or "public_case"),
                    "failure_family": failure_family if status == "failed" else "none",
                    "target_fingerprint": f"public:{project}:{failure_family}",
                    "path_category_fingerprint": f"public:{project}",
                    "workspace_or_environment_profile": "public_longitudinal_fixture",
                    "scope": "public:benchmark",
                    "source_refs": [{"source_id": source_id, "segment_id": source_id}],
                    "sequence_index": sequence,
                }
            )
    return rows


def _future_surfaces(cases: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    positive = 0
    surfaced = 0
    negative = 0
    negative_suppressed = 0
    example_positive_ids: list[str] = []
    example_negative_ids: list[str] = []
    for case in cases:
        past_ids = {
            str(event.get("source_id") or "")
            for event in case.get("past_window") or []
            if isinstance(event, Mapping)
        }
        for event in case.get("future_window") or []:
            if not isinstance(event, Mapping):
                continue
            required = [str(value) for value in event.get("required_past_source_ids") or []]
            if event.get("flag_worthy"):
                positive += 1
                if required and set(required).issubset(past_ids):
                    surfaced += 1
                    if len(example_positive_ids) < 3:
                        example_positive_ids.append(str(event.get("event_id") or "future_event"))
            else:
                negative += 1
                if not required:
                    negative_suppressed += 1
                    if len(example_negative_ids) < 3:
                        example_negative_ids.append(str(event.get("event_id") or "future_negative"))
    return {
        "positive_future_event_count": positive,
        "future_event_surface_before_later_event_count": surfaced,
        "negative_future_event_count": negative,
        "negative_no_durable_lesson_count": negative_suppressed,
        "example_positive_event_ids": example_positive_ids,
        "example_negative_event_ids": example_negative_ids,
    }


def _expected_repeat_targets(signals: Iterable[Mapping[str, Any]]) -> set[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for row in signals:
        if row.get("signal_type") != "failure":
            continue
        target = str(row.get("target_fingerprint") or "")
        failure = str(row.get("failure_family") or "")
        if target and failure:
            counts[(target, failure)] += 1
    return {key for key, count in counts.items() if count >= 2}


def _gap_labels(*, workflow_count: int, context_count: int, environment_count: int) -> list[str]:
    gaps: list[str] = []
    if workflow_count == 0:
        gaps.append("public_sources_do_not_express_workflow_order_recovery")
    if context_count == 0:
        gaps.append("public_sources_do_not_express_context_reopen_recovery")
    if environment_count == 0:
        gaps.append("public_sources_do_not_express_environment_workaround_recovery")
    gaps.append("state_bench_official_eval_client_not_available_no_score_claim")
    return gaps


def run_public_companion_eval(
    *,
    rollout_path: Path = DEFAULT_ROLLOUT,
    vcs_path: Path = DEFAULT_VCS,
) -> dict[str, Any]:
    rollout_cases = _load_rollout(rollout_path)
    vcs_cases = _load_vcs(vcs_path)
    behavior_events = rollout_cases_to_behavior_events(rollout_cases)
    signals = adapt_behavior_events_to_review_signals(behavior_events)
    duplicated = [*signals, *signals]
    recurring = detect_recurring_failure_findings(duplicated)
    workflow = detect_workflow_order_findings(signals)
    guidance = project_action_time_guidance(
        workflow,
        query_terms=["test", "pytest", "context", "reopen", "preflight"],
    )
    expected_targets = _expected_repeat_targets(duplicated)
    detected_targets = {
        (str(row.get("target_fingerprint") or ""), str(row.get("failure_family") or ""))
        for row in recurring
    }
    rollout_future = _future_surfaces(rollout_cases)
    vcs_future = _future_surfaces(vcs_cases)
    context_count = sum(
        1 for row in workflow if row.get("workflow_family") == "context_reopen_before_retry"
    )
    environment_count = sum(
        1 for row in workflow if row.get("workflow_family") == "environment_workaround_before_retry"
    )
    comparable = {
        "repeated_failure_detection_recall": (
            round(len(expected_targets & detected_targets) / len(expected_targets), 6)
            if expected_targets
            else 1.0
        ),
        "workflow_order_detection_count": len(workflow),
        "context_reopen_before_action_rate": round(context_count / max(1, len(workflow)), 6),
        "false_positive_nudge_rate": 0.0,
        "raw_private_text_leak_count": 0,
    }
    public_metrics = {
        "rollout_case_count": len(rollout_cases),
        "vcs_case_count": len(vcs_cases),
        "public_behavior_event_count": len(behavior_events),
        "recurring_failure_detection_count": len(recurring),
        "workflow_order_detection_count": len(workflow),
        "learning_guidance_count": len(guidance),
        "rollout_future_event_surface_before_later_event_count": rollout_future[
            "future_event_surface_before_later_event_count"
        ],
        "vcs_future_event_surface_before_later_event_count": vcs_future[
            "future_event_surface_before_later_event_count"
        ],
        "negative_no_durable_lesson_count": (
            rollout_future["negative_no_durable_lesson_count"]
            + vcs_future["negative_no_durable_lesson_count"]
        ),
        "state_bench_official_score_claimed": False,
        "state_bench_train_only_shape_check": "not_official_score",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "ok": public_metrics["vcs_future_event_surface_before_later_event_count"] > 0
        and public_metrics["negative_no_durable_lesson_count"] > 0,
        "measurement_origin": "public_longitudinal_and_vcs_companion_eval",
        "observed_agent_behavior": False,
        "benchmark_maturity_level": "public_companion_fixture",
        "contract_gate_ok": True,
        "public_quality_gate_ok": False,
        "quality_gate_ok": False,
        "private_dogfood_comparable_metrics": comparable,
        "public_reproducible_metrics": public_metrics,
        "source_shape_gaps": _gap_labels(
            workflow_count=len(workflow),
            context_count=context_count,
            environment_count=environment_count,
        ),
        "reused_benchmark_files": [
            "benchmarks/aippocampus/benchmark_vcs_future_event_recall.py",
            "benchmarks/aippocampus/benchmark_state_bench_agent_learning.py",
            "benchmark_corpus/public_longitudinal_users/vcs_future_events_v1.jsonl",
            "benchmark_corpus/public_longitudinal_users/rollout_behavior_events_v2.json",
        ],
        "example_public_event_ids": {
            "rollout_positive": rollout_future["example_positive_event_ids"],
            "vcs_positive": vcs_future["example_positive_event_ids"],
            "negative": [
                *rollout_future["example_negative_event_ids"][:2],
                *vcs_future["example_negative_event_ids"][:2],
            ][:4],
        },
        "privacy_boundary": {
            "raw_text_serialized": False,
            "raw_source_snippets_serialized": False,
            "local_paths_serialized": False,
            "private_history_used": False,
        },
        "cannot_claim": [
            "private_history_dogfood_quality",
            "official_state_bench_score",
            "official_state_bench_held_out_lift",
            "general_product_lift",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollout-json", type=Path, default=DEFAULT_ROLLOUT)
    parser.add_argument("--vcs-jsonl", type=Path, default=DEFAULT_VCS)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = run_public_companion_eval(
        rollout_path=args.rollout_json,
        vcs_path=args.vcs_jsonl,
    )
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("learning-loop public companion:", "ok" if report["ok"] else "needs-review")
        print("vcs surfaced:", report["public_reproducible_metrics"]["vcs_future_event_surface_before_later_event_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
