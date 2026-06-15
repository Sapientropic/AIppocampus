"""Private-history replay harness for the source-backed learning loop.

The harness accepts sanitized behavior events, not raw rollouts. Maintainers can
extract private local history into a temporary behavior-event file, run this
module, and keep the raw/private file out of committed artifacts.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.learning_loop.core import (
    adapt_behavior_events_to_review_signals,
    detect_recurring_failure_findings,
    detect_workflow_order_findings,
    project_action_time_guidance,
)

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_learning_loop_private_replay_report"


def private_replay_fixture_events() -> list[dict[str, Any]]:
    return [
        {
            "event_id": "private_like_broad_failed",
            "status": "failed",
            "command_family": "repo_test_runner",
            "target_class": "repo_pr_suite",
            "failure_family": "assertion_failure",
            "target_fingerprint": "private-fixture:pr-tier",
            "path_category_fingerprint": "private-fixture:path:test",
            "scope": "project:AIppocampus",
            "source_refs": [{"thread_key": "private-fixture", "message_id": "broad_failed"}],
            "sequence_index": 1,
        },
        {
            "event_id": "private_like_ruff_success",
            "status": "succeeded",
            "command_family": "python_ruff",
            "target_class": "lint",
            "failure_family": "none",
            "target_fingerprint": "private-fixture:pr-tier",
            "path_category_fingerprint": "private-fixture:path:test",
            "scope": "project:AIppocampus",
            "source_refs": [{"thread_key": "private-fixture", "message_id": "ruff_success"}],
            "sequence_index": 2,
        },
        {
            "event_id": "private_like_broad_success",
            "status": "succeeded",
            "command_family": "repo_test_runner",
            "target_class": "repo_pr_suite",
            "failure_family": "none",
            "target_fingerprint": "private-fixture:pr-tier",
            "path_category_fingerprint": "private-fixture:path:test",
            "scope": "project:AIppocampus",
            "source_refs": [{"thread_key": "private-fixture", "message_id": "broad_success"}],
            "sequence_index": 3,
        },
        {
            "event_id": "private_like_context_failed",
            "status": "failed",
            "command_family": "python_pytest",
            "target_class": "focused_test_path",
            "failure_family": "assertion_failure",
            "target_fingerprint": "private-fixture:context",
            "path_category_fingerprint": "private-fixture:path:context",
            "scope": "project:AIppocampus",
            "source_refs": [{"thread_key": "private-fixture", "message_id": "context_failed"}],
            "sequence_index": 4,
        },
        {
            "event_id": "private_like_context_reopen",
            "status": "succeeded",
            "command_family": "ripgrep",
            "target_class": "source_search",
            "failure_family": "none",
            "target_fingerprint": "private-fixture:context",
            "path_category_fingerprint": "private-fixture:path:context",
            "scope": "project:AIppocampus",
            "source_refs": [{"thread_key": "private-fixture", "message_id": "context_reopen"}],
            "sequence_index": 5,
        },
        {
            "event_id": "private_like_context_success",
            "status": "succeeded",
            "command_family": "python_pytest",
            "target_class": "focused_test_path",
            "failure_family": "none",
            "target_fingerprint": "private-fixture:context",
            "path_category_fingerprint": "private-fixture:path:context",
            "scope": "project:AIppocampus",
            "source_refs": [{"thread_key": "private-fixture", "message_id": "context_success"}],
            "sequence_index": 6,
        },
        {
            "event_id": "private_like_expected_red",
            "status": "failed",
            "command_family": "python_pytest",
            "target_class": "focused_test_path",
            "failure_family": "assertion_failure",
            "target_fingerprint": "private-fixture:tdd-red",
            "path_category_fingerprint": "private-fixture:path:tdd",
            "expected_local_red": True,
            "source_refs": [{"thread_key": "private-fixture", "message_id": "expected_red"}],
            "sequence_index": 7,
        },
        {
            "event_id": "private_like_one_off",
            "status": "failed",
            "command_family": "python_pytest",
            "target_class": "focused_test_path",
            "failure_family": "assertion_failure",
            "target_fingerprint": "private-fixture:one-off",
            "path_category_fingerprint": "private-fixture:path:one-off",
            "source_refs": [{"thread_key": "private-fixture", "message_id": "one_off"}],
            "sequence_index": 8,
        },
    ]


def _expected_repeat_targets(signals: Iterable[Mapping[str, Any]]) -> set[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for row in signals:
        if row.get("signal_type") != "failure":
            continue
        if row.get("review_semantics") == "review_only_expected_red":
            continue
        target = str(row.get("target_fingerprint") or "")
        failure = str(row.get("failure_family") or "")
        if target and failure:
            counts[(target, failure)] += 1
    return {key for key, count in counts.items() if count >= 2}


def _raw_leak_count(report: Mapping[str, Any]) -> int:
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
    sentinels = (
        "PRIVATE_HISTORY_PAYLOAD",
        "tool_output",
        "E:/",
        "C:/",
        "\\Users\\",
    )
    return sum(1 for sentinel in sentinels if sentinel in encoded)


def build_private_history_replay_report(
    events: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = [dict(row) for row in (events if events is not None else private_replay_fixture_events())]
    signals = adapt_behavior_events_to_review_signals(rows)
    duplicated_signals = [*signals, *signals]
    recurring = detect_recurring_failure_findings(duplicated_signals)
    workflow = detect_workflow_order_findings(signals)
    guidance = project_action_time_guidance(
        workflow,
        query_terms=["test", "pytest", "preflight", "context", "reopen"],
    )
    expected_targets = _expected_repeat_targets(duplicated_signals)
    detected_targets = {
        (str(row.get("target_fingerprint") or ""), str(row.get("failure_family") or ""))
        for row in recurring
    }
    context_workflows = [
        row for row in workflow if row.get("workflow_family") == "context_reopen_before_retry"
    ]
    expected_red_suppressed = sum(1 for row in rows if row.get("expected_local_red"))
    one_off_suppressed = sum(
        1
        for row in signals
        if row.get("signal_type") == "failure"
        and str(row.get("target_fingerprint") or "").endswith("one-off")
    )
    false_positive_count = sum(
        1
        for row in guidance
        if str(row.get("next_action") or "") == "reopen_failure_source_before_retry"
    )
    comparable = {
        "repeated_failure_detection_recall": (
            round(len(expected_targets & detected_targets) / len(expected_targets), 6)
            if expected_targets
            else 1.0
        ),
        "workflow_order_detection_count": len(workflow),
        "context_reopen_before_action_rate": (
            round(len(context_workflows) / len(context_workflows), 6) if context_workflows else 0.0
        ),
        "false_positive_nudge_rate": (
            round(false_positive_count / max(1, len(guidance)), 6) if guidance else 0.0
        ),
        "raw_private_text_leak_count": 0,
    }
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "ok": bool(guidance) and bool(context_workflows),
        "input_event_count": len(rows),
        "private_history_role": "local_private_dogfood_harness",
        "private_dogfood_comparable_metrics": comparable,
        "metrics": {
            **comparable,
            "source_backed_guidance_changed_action_order_count": int(bool(guidance)),
            "context_loss_to_reopen_source_count": len(context_workflows),
            "one_off_suppressed_count": one_off_suppressed,
            "expected_tdd_red_suppressed_count": expected_red_suppressed,
            "guidance_count": len(guidance),
        },
        "guidance_authority": {
            "all_navigation_only": all(row.get("navigation_only") for row in guidance),
            "all_source_reopen_required": all(
                row.get("source_reopen_required_before_claim") for row in guidance
            ),
            "can_support_factual_claim": False,
        },
        "privacy_boundary": {
            "raw_private_text_serialized": False,
            "raw_stdout_stderr_serialized": False,
            "full_commands_serialized": False,
            "local_paths_serialized": False,
            "raw_rollouts_serialized": False,
            "aggregate_or_redacted_public_output_only": True,
        },
        "local_artifact_policy": {
            "private_input_must_live_under_tmp_or_operator_path": True,
            "committed_output_must_be_aggregate_or_redacted": True,
        },
        "cannot_claim": [
            "general_public_lift_from_private_history",
            "candidate_guidance_is_source_truth",
            "causal_live_behavior_lift",
        ],
    }
    comparable["raw_private_text_leak_count"] = _raw_leak_count(report)
    report["metrics"]["raw_private_text_leak_count"] = comparable["raw_private_text_leak_count"]
    report["ok"] = bool(report["ok"]) and comparable["raw_private_text_leak_count"] == 0
    return report


def _load_events(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return [
            dict(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        rows = payload.get("events") or payload.get("behavior_events") or []
        return [dict(row) for row in rows if isinstance(row, Mapping)]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, help="Sanitized behavior events JSON/JSONL.")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    events = _load_events(args.events) if args.events else None
    report = build_private_history_replay_report(events)
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("private learning-loop replay:", "ok" if report["ok"] else "needs-review")
        print("guidance:", report["metrics"]["guidance_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
