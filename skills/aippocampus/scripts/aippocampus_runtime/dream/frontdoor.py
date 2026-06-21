"""Read-only foreground Dream status commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_template_action,
)
from aippocampus_runtime.dream import sleep_cycle
from aippocampus_runtime.dream import status as dream_status
from aippocampus_runtime.registry.store import registry_root


def _row_status(row: dict[str, Any]) -> str:
    return str(row.get("status") or row.get("state") or "").strip()


def _retention_decision(row: dict[str, Any]) -> str:
    policy = row.get("retention_policy")
    if isinstance(policy, dict):
        return str(policy.get("decision") or "").strip()
    return ""


def _count_status_rows(rows: list[dict[str, Any]], statuses: set[str]) -> int:
    return sum(1 for row in rows if _row_status(row) in statuses)


def dream_status_payload(
    *,
    lane: str = "dream",
    registry_dir: Path | None = None,
    queue_jsonl: Path | None = None,
    findings_jsonl: Path | None = None,
    working_memory_jsonl: Path | None = None,
) -> dict[str, Any]:
    lane = "subconscious" if str(lane or "").strip() == "subconscious" else "dream"
    root = registry_root(registry_dir)
    queue_rows = sleep_cycle.iter_jsonl(queue_jsonl or root / "dream_queue.jsonl")
    finding_rows = sleep_cycle.iter_jsonl(findings_jsonl or root / "dream_findings.jsonl")
    working_rows = sleep_cycle.iter_jsonl(
        working_memory_jsonl or root / "dream_working_memory.jsonl"
    )
    accepted = sum(
        1
        for row in finding_rows
        if _retention_decision(row) == "retain_for_review"
        or _row_status(row) in {"accepted", "retained_for_review"}
    )
    parked = sum(
        1
        for row in finding_rows
        if _retention_decision(row) == "park_for_review"
        or _row_status(row) in {"parked", "parked_pending_review"}
    )
    rejected = sum(
        1
        for row in finding_rows
        if _retention_decision(row) == "drop_low_pressure"
        or _row_status(row) in {"rejected", "model_output_rejected", "dropped"}
    )
    payload: dict[str, Any] = {
        "kind": (
            "aippocampus_subconscious_status"
            if lane == "subconscious"
            else "aippocampus_dream_status"
        ),
        "ok": True,
        "read_only": True,
        "status": "status_card",
        "lane": lane,
        "status_alias": (
            "shared_dream_background_status"
            if lane == "subconscious"
            else "dream_background_status"
        ),
        "surface": "foreground_status_card",
        "counts": {
            "queue_items": len(queue_rows),
            "selected_items": _count_status_rows(queue_rows, sleep_cycle.RUNNABLE_STATUSES),
            "accepted": accepted,
            "parked": parked,
            "rejected": rejected,
            "written_findings": len(finding_rows),
            "written_working_memory": len(working_rows),
        },
        "adjudicated_findings": finding_rows,
        "write_mode": "status_only",
        "write_contract": {
            "status_command_is_read_only": True,
            "writes_performed": False,
            "working_memory_projection_requires_explicit_write_command": True,
        },
        "privacy_boundary": {
            "raw_candidate_text_emitted": False,
            "local_paths_emitted": False,
            "source_handles_emitted": False,
        },
    }
    payload["dream_output_status_card"] = dream_status.dream_output_status_card(payload)
    action = foreground_template_action(
        action_id="inspect_reviewed_background_guidance",
        label="Inspect reviewed background guidance",
        command_template='aippocampus agent background "{task_cue}" --json',
        requires=["task_cue"],
        why=(
            "Use a real task cue to inspect already reviewed Dream/subconscious "
            "findings; this does not start a broad Dream run."
        ),
        mutation_risk="read_only",
        claim_boundary="background_navigation_not_source_truth",
    )
    payload.update(canonical_foreground_action_fields(action, safe_next_actions=[action]))
    payload.pop("adjudicated_findings", None)
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aippocampus dream", description=__doc__)
    sub = parser.add_subparsers(dest="command")
    status_parser = sub.add_parser("status", help="Read Dream output status without running workers.")
    status_parser.add_argument("--registry-dir", type=Path)
    status_parser.add_argument("--queue-jsonl", type=Path)
    status_parser.add_argument("--findings-jsonl", type=Path)
    status_parser.add_argument("--working-memory-jsonl", type=Path)
    status_parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def _top_reason_bucket_lines(card: dict[str, Any], *, limit: int = 3) -> list[str]:
    buckets = card.get("reason_buckets")
    if not isinstance(buckets, dict):
        return []
    ordered = sorted(
        ((str(name), int(count or 0)) for name, count in buckets.items()),
        key=lambda item: (-item[1], item[0]),
    )
    return [f"{name}={count}" for name, count in ordered[:limit] if count > 0]


def main(argv: list[str] | None = None) -> int:
    raw_args = list(argv or [])
    lane = "dream"
    if raw_args and raw_args[0] in {"dream", "subconscious"}:
        lane = raw_args.pop(0)
    parser = build_arg_parser()
    args = parser.parse_args(raw_args if argv is not None else None)
    if args.command != "status":
        parser.print_help()
        return 2
    payload = dream_status_payload(
        lane=lane,
        registry_dir=args.registry_dir,
        queue_jsonl=args.queue_jsonl,
        findings_jsonl=args.findings_jsonl,
        working_memory_jsonl=args.working_memory_jsonl,
    )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        card = payload["dream_output_status_card"]
        print(
            "AIppocampus subconscious status"
            if payload.get("lane") == "subconscious"
            else "AIppocampus Dream status"
        )
        if payload.get("lane") == "subconscious":
            print("alias: shared Dream/background status surface")
        print(f"status: {card.get('status')}")
        reason_lines = _top_reason_bucket_lines(card)
        if reason_lines:
            print("why_no_output: " + ", ".join(reason_lines))
        print(f"primary_next_action: {card.get('primary_next_action')}")
        print('template: aippocampus agent background "{task_cue}" --json')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
