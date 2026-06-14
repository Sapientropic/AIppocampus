#!/usr/bin/env python3
"""Deterministic queue planning for background dream workers.

The queue is lifecycle metadata, not a source surface. It decides which ready
dream input packs may be handed to detached workers, records dedup/expiry/cost
boundaries, and reports aggregate diagnostics without exposing source refs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.dream.macro_guidance import priority_with_macro_momentum

QUEUE_KIND = "aippocampus_dream_queue"
QUEUE_ITEM_KIND = "aippocampus_dream_queue_item"
READY_STATUS = "ready_for_dream_worker"
CACHE_CONTRACT = "deepseek_prefix_v1"
EXECUTION_MODE = "detached_background"
PROMPT_ORDER = ["stable_dream_worker_contract", "source_pack_payload", "variable_run_directive"]
ADJUDICATED_STATES = {
    "accepted",
    "approved",
    "reviewed",
    "agent_adjudicated",
    "auto_adjudicated",
    "source_adjudicated",
}
PREVIOUS_DEDUP_STATUSES = {"queued", "running", "completed", "accepted", "parked"}
FUNCTION_ORDER = {
    "compensatory": 0,
    "amplification": 1,
    "prospective": 2,
    "active_imagination": 3,
}
RETENTION_LADDER_KIND = "aippocampus_dream_retention_ladder_policy"
JOURNEY_PROJECTION_KIND = "aippocampus_dream_journey_projection_policy"
FORBIDDEN_JOURNEY_PROJECTION_ACTIONS = [
    "rewrite_waypoints",
    "replace_journey_with_summary",
    "emit_user_profile_claim",
    "promote_model_synthesis_to_source_truth",
]


def stable_digest(*parts: object, prefix: str, length: int = 18) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True, default=str) for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8', errors='replace')).hexdigest()[:length]}"


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_now(now: str | datetime | None) -> datetime:
    if isinstance(now, datetime):
        return now.astimezone(timezone.utc)
    parsed = parse_utc(str(now)) if now else parse_utc(now_utc())
    return parsed or datetime.now(timezone.utc)


def string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value if item not in {None, ""}]
    return []


def dedup_key_for(pack_id: str, dream_function: str) -> str:
    return stable_digest(pack_id, dream_function, prefix="dream_dedup", length=20)


def trigger_family_for_pack(pack: Mapping[str, Any], explicit: str | None = None) -> str:
    if explicit:
        return explicit
    kinds = {str(kind) for kind in pack.get("source_seed_kinds") or []}
    if "recall_miss" in kinds:
        return "recall_miss_feedback"
    if "correction" in kinds:
        return "correction_outcome"
    if "ambient_residue" in kinds:
        return "topic_epoch_residue"
    if "journey" in kinds:
        return "journey_frontier"
    return "ready_source_pack"


def priority_for(trigger_family: str, dream_function: str) -> int:
    base = {
        "explicit_operator_request": 90,
        "correction_outcome": 70,
        "recall_miss_feedback": 65,
        "journey_frontier": 60,
        "topic_epoch_residue": 45,
        "ready_source_pack": 40,
        "periodic_maintenance": 20,
    }.get(trigger_family, 30)
    return base - FUNCTION_ORDER.get(dream_function, 9)


def journey_projection_policy_for(trigger_family: str) -> dict[str, Any]:
    """Describe how Dream queue output may touch Journey state.

    #299's anti-fossilization boundary is subtle enough to keep beside the
    runtime row: Dream work may create navigation candidates around a Journey,
    but it must not smooth append-only waypoints into a replacement summary or
    user profile.
    """

    if trigger_family == "journey_frontier":
        default_action = "append_waypoint_candidate"
        allowed_actions = [
            "append_waypoint_candidate",
            "update_current_frontier_candidate",
            "camp_or_revive_journey_candidate",
            "park_one_off_residue",
        ]
    elif trigger_family in {"topic_epoch_residue", "correction_outcome"}:
        default_action = "route_to_existing_journey_or_park"
        allowed_actions = [
            "route_to_existing_journey",
            "append_waypoint_candidate_after_source_review",
            "park_one_off_residue",
        ]
    else:
        default_action = "park_or_queue_for_source_review"
        allowed_actions = [
            "route_to_existing_journey_after_source_review",
            "park_one_off_residue",
        ]
    return {
        "kind": JOURNEY_PROJECTION_KIND,
        "default_action": default_action,
        "allowed_actions": allowed_actions,
        "forbidden_actions": list(FORBIDDEN_JOURNEY_PROJECTION_ACTIONS),
        "can_rewrite_waypoints": False,
        "can_emit_user_profile_claim": False,
        "requires_source_backed_waypoint": True,
        "requires_reconciliation_before_projection": True,
        "truth_boundary": "journey_projection_is_navigation_not_source_truth",
    }


def retention_ladder_policy_for(trigger_family: str, dream_function: str) -> dict[str, Any]:
    return {
        "kind": RETENTION_LADDER_KIND,
        "trigger_family": trigger_family,
        "dream_function": dream_function,
        "foreground_hot_cache_ttl": "0-6h",
        "dream_residue_buffer_ttl": "6-24h",
        "current_tier": "dream_queue_hypothesis_24h_7d",
        "weekly_monthly_role": "journey_review_view_not_summary_replacement",
        "quarterly_yearly_role": "source_backed_journey_index_and_decay_audit",
        "promotion_gate": "adjudication_and_source_reconciliation_only",
        "ordinary_foreground_use": "none_until_adjudicated_working_memory_projection",
        "journey_projection": journey_projection_policy_for(trigger_family),
        "truth_boundary": "retention_ladder_routes_residue_not_truth",
    }


def cost_budget_for(dream_function: str) -> dict[str, Any]:
    return {
        "max_model_calls": 1,
        "max_samples": 1,
        "timeout_seconds": 180,
        "cache_contract": CACHE_CONTRACT,
        "reason": f"bounded_{dream_function}_dream_worker",
    }


def active_previous_dedup_keys(
    previous_items: Iterable[Mapping[str, Any]],
    *,
    now_dt: datetime,
) -> tuple[set[str], list[dict[str, Any]]]:
    active: set[str] = set()
    expired: list[dict[str, Any]] = []
    for item in previous_items:
        if not isinstance(item, Mapping):
            continue
        dedup_key = str(item.get("dedup_key") or "")
        expires_at = parse_utc(str(item.get("expires_at") or ""))
        status = str(item.get("status") or "")
        if not dedup_key or status not in PREVIOUS_DEDUP_STATUSES:
            continue
        # Queue rows are lifecycle hints, not durable truth. Once they expire,
        # even completed rows stop suppressing fresh work; permanent suppression
        # must come from adjudicated or parked findings in clean-source space.
        if expires_at and expires_at <= now_dt:
            expired.append(
                {
                    "kind": QUEUE_ITEM_KIND,
                    "queue_item_id": item.get("queue_item_id"),
                    "pack_id": item.get("pack_id"),
                    "dream_function": item.get("dream_function"),
                    "status": "expired",
                    "dedup_key": dedup_key,
                    "expired_at": format_utc(now_dt),
                }
            )
            continue
        active.add(dedup_key)
    return active, expired


def finding_dedup_key(finding: Mapping[str, Any]) -> str:
    explicit = str(finding.get("dedup_key") or "")
    if explicit:
        return explicit
    pack_id = str(finding.get("source_pack_id") or finding.get("pack_id") or "")
    dream_function = str(finding.get("dream_function") or "")
    if pack_id and dream_function:
        return dedup_key_for(pack_id, dream_function)
    return ""


def existing_finding_diagnostics(
    findings: Iterable[Mapping[str, Any]],
) -> tuple[set[str], set[str], int]:
    adjudicated: set[str] = set()
    parked_keys: set[str] = set()
    parked = 0
    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        if finding.get("finding_kind") != "dream_synthesized":
            continue
        key = finding_dedup_key(finding)
        review_state = str(finding.get("review_state") or "")
        adjudication = finding.get("adjudication_result") or {}
        if isinstance(adjudication, Mapping) and adjudication.get("status") == "parked":
            parked += 1
            if key:
                parked_keys.add(key)
        if key and review_state in ADJUDICATED_STATES:
            adjudicated.add(key)
    return adjudicated, parked_keys, parked


def queue_item(
    *,
    pack: Mapping[str, Any],
    dream_function: str,
    trigger_family: str,
    macro_momentum_context: Mapping[str, Any] | None,
    now_dt: datetime,
    review_after_hours: int,
    expiry_hours: int,
) -> dict[str, Any]:
    pack_id = str(pack.get("pack_id") or "")
    dedup_key = dedup_key_for(pack_id, dream_function)
    review_after = now_dt + timedelta(hours=max(1, int(review_after_hours)))
    expires_at = now_dt + timedelta(hours=max(2, int(expiry_hours)))
    retention_ladder = retention_ladder_policy_for(trigger_family, dream_function)
    priority = priority_with_macro_momentum(
        base_priority=priority_for(trigger_family, dream_function),
        trigger_family=trigger_family,
        dream_function=dream_function,
        context=macro_momentum_context,
    )
    return {
        "schema_version": 1,
        "kind": QUEUE_ITEM_KIND,
        "queue_item_id": stable_digest(dedup_key, trigger_family, prefix="dreamq", length=20),
        "created_at": format_utc(now_dt),
        "status": "queued",
        "pack_id": pack_id,
        "dream_function": dream_function,
        "trigger_family": trigger_family,
        "priority": priority["priority"],
        "priority_components": {
            "trigger_family_base": priority["base_priority"],
            "macro_momentum": priority["macro_momentum"],
        },
        "dedup_key": dedup_key,
        "review_after": format_utc(review_after),
        "expires_at": format_utc(expires_at),
        "cost_budget": cost_budget_for(dream_function),
        "execution_mode": EXECUTION_MODE,
        "foreground_eligible": False,
        "live_model_allowed_in_foreground": False,
        "truth_boundary": "dream_queue_item_lifecycle_hint_not_source_truth",
        "retention_ladder": retention_ladder,
        "journey_projection": retention_ladder["journey_projection"],
        "cache_contract": CACHE_CONTRACT,
        "prompt_prefix_group": f"dream_worker:{dream_function}:{CACHE_CONTRACT}",
        "prompt_order": list(PROMPT_ORDER),
        "reason": f"{trigger_family}:{pack.get('pack_kind') or 'dream_input_pack'}",
        "source_seed_kinds": list(pack.get("source_seed_kinds") or []),
        "source_ref_audit": {
            "status": (pack.get("source_ref_audit") or {}).get("status"),
            "source_ref_count": (pack.get("source_ref_audit") or {}).get("source_ref_count"),
            "source_thread_count": (pack.get("source_ref_audit") or {}).get("source_thread_count"),
        },
    }


def build_dream_queue(
    packs: Iterable[Mapping[str, Any]],
    *,
    previous_items: Iterable[Mapping[str, Any]] | None = None,
    existing_findings: Iterable[Mapping[str, Any]] | None = None,
    trigger_family: str | None = None,
    macro_momentum_context: Mapping[str, Any] | None = None,
    now: str | datetime | None = None,
    review_after_hours: int = 24,
    expiry_hours: int = 7 * 24,
    max_items: int = 64,
) -> dict[str, Any]:
    now_dt = normalize_now(now)
    previous_keys, expired_items = active_previous_dedup_keys(
        previous_items or [],
        now_dt=now_dt,
    )
    adjudicated_keys, parked_keys, parked_count = existing_finding_diagnostics(existing_findings or [])
    items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []

    for pack in packs:
        if not isinstance(pack, Mapping):
            continue
        if pack.get("status") != READY_STATUS:
            skipped_items.append({"pack_id": pack.get("pack_id"), "reason": "pack_not_ready"})
            continue
        pack_id = str(pack.get("pack_id") or "")
        family = trigger_family_for_pack(pack, explicit=trigger_family)
        pack_momentum = (
            pack.get("macro_momentum_context")
            if isinstance(pack.get("macro_momentum_context"), Mapping)
            else macro_momentum_context
        )
        for dream_function in string_values(pack.get("eligible_dream_functions")):
            dedup_key = dedup_key_for(pack_id, dream_function)
            if dedup_key in previous_keys:
                skipped_items.append(
                    {"pack_id": pack_id, "dream_function": dream_function, "reason": "previous_queue"}
                )
                continue
            if dedup_key in parked_keys:
                skipped_items.append(
                    {
                        "pack_id": pack_id,
                        "dream_function": dream_function,
                        "reason": "existing_parked_finding",
                    }
                )
                continue
            if dedup_key in adjudicated_keys:
                skipped_items.append(
                    {
                        "pack_id": pack_id,
                        "dream_function": dream_function,
                        "reason": "existing_adjudicated_finding",
                    }
                )
                continue
            items.append(
                queue_item(
                    pack=pack,
                    dream_function=dream_function,
                    trigger_family=family,
                    macro_momentum_context=pack_momentum,
                    now_dt=now_dt,
                    review_after_hours=review_after_hours,
                    expiry_hours=expiry_hours,
                )
            )

    items.sort(
        key=lambda item: (
            -int(item.get("priority") or 0),
            FUNCTION_ORDER.get(str(item.get("dream_function") or ""), 99),
            str(item.get("prompt_prefix_group") or ""),
            str(item.get("pack_id") or ""),
        )
    )
    items = items[: max(0, int(max_items))]
    trigger_counts = Counter(str(item.get("trigger_family") or "") for item in items)
    skipped_counts = Counter(str(item.get("reason") or "") for item in skipped_items)
    return {
        "schema_version": 1,
        "kind": QUEUE_KIND,
        "created_at": format_utc(now_dt),
        "items": items,
        "expired_items": expired_items,
        "skipped_items": skipped_items,
        "counts": {
            "queued": len(items),
            "expired": len(expired_items),
            "parked_findings": parked_count,
            "skipped_duplicate": (
                skipped_counts.get("previous_queue", 0)
                + skipped_counts.get("existing_parked_finding", 0)
                + skipped_counts.get("existing_adjudicated_finding", 0)
            ),
            "skipped_not_ready": skipped_counts.get("pack_not_ready", 0),
            "trigger_families": dict(sorted(trigger_counts.items())),
        },
        "policy": {
            "foreground_model_calls_allowed": False,
            "execution_mode": EXECUTION_MODE,
            "default_trigger_frequency": "low_frequency_background_only",
            "human_operator_boundary": "explicit_operator_request_or_sensitive_review_only",
            "queue_state_is_not_clean_source": True,
        },
    }


def public_queue_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    counts = payload.get("counts") or {}
    return {
        "kind": "aippocampus_dream_queue_summary",
        "queued": int(counts.get("queued") or 0),
        "expired": int(counts.get("expired") or 0),
        "parked_findings": int(counts.get("parked_findings") or 0),
        "skipped_duplicate": int(counts.get("skipped_duplicate") or 0),
        "skipped_not_ready": int(counts.get("skipped_not_ready") or 0),
        "trigger_families": dict(counts.get("trigger_families") or {}),
        "foreground_model_calls_allowed": False,
        "execution_mode": EXECUTION_MODE,
    }


def iter_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan deterministic background dream queue items.")
    parser.add_argument("--packs-jsonl", type=Path, required=True)
    parser.add_argument("--previous-queue-jsonl", type=Path)
    parser.add_argument("--findings-jsonl", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--now")
    parser.add_argument("--summary", action="store_true", help="Emit sanitized aggregate summary only.")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    payload = build_dream_queue(
        iter_jsonl(args.packs_jsonl),
        previous_items=iter_jsonl(args.previous_queue_jsonl),
        existing_findings=iter_jsonl(args.findings_jsonl),
        now=args.now,
    )
    output_payload = public_queue_summary(payload) if args.summary else payload
    text = json.dumps(output_payload, ensure_ascii=False, indent=None if args.json_output else 2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
