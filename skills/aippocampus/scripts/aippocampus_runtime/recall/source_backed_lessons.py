"""Source-backed lesson candidates for repeated agent mistakes.

Lessons are not memories-as-facts. They are route constraints compiled from
source-backed corrections so future agents do not repeat the same architectural
mistake. A single correction stays growing unless the user explicitly confirms
it or another independent source trail supports it.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "source-backed-lesson-candidate-v0"


def _event_text(event: Mapping[str, Any]) -> str:
    return str(event.get("text") or "")


def _event_refs(events: Iterable[Mapping[str, Any]]) -> list[str]:
    refs: list[str] = []
    for event in events:
        ref = str(event.get("source_ref") or "").strip()
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def _mentions_benchmark_architecture(text: str) -> bool:
    lowered = text.casefold()
    return (
        "semantic_scope" in lowered
        or "semantic scope" in lowered
        or "subconscious" in lowered
        or "warm ambient" in lowered
        or "source-side" in lowered
        or "provider prompt" in lowered
    )


def _safe_refs(value: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for item in value or []:
        if not isinstance(item, Mapping):
            continue
        clean = {
            str(key): item.get(key)
            for key in (
                "thread_key",
                "source_id",
                "message_id",
                "turn_id",
                "turn_index",
                "line",
                "source_line",
            )
            if item.get(key) not in (None, "", [])
        }
        marker = tuple(sorted((key, str(val)) for key, val in clean.items()))
        if clean and marker not in seen:
            seen.add(marker)
            refs.append(clean)
    return refs[:6]


def _verified_origin(row: Mapping[str, Any]) -> bool:
    for key in ("verified_origin", "origin_verified", "support_verified"):
        if key in row:
            return bool(row.get(key))
    for key in ("import_origin", "integrity", "origin"):
        value = row.get(key)
        if isinstance(value, Mapping) and "verified_origin" in value:
            return bool(value.get("verified_origin"))
    return False


def _derived_origin(rows: Iterable[Mapping[str, Any]], *, origin_kind: str) -> dict[str, Any]:
    materialized = [row for row in rows if isinstance(row, Mapping)]
    verified = bool(materialized) and all(_verified_origin(row) for row in materialized)
    return {
        "verified_origin": verified,
        "origin_verified": verified,
        "origin_kind": origin_kind,
        "source_row_count": len(materialized),
        "boundary": "lesson candidates inherit explicit source verification; absence fails closed",
    }


def _candidate_kind_for_finding(row: Mapping[str, Any]) -> str:
    explicit = str(row.get("candidate_family") or "")
    if explicit:
        return explicit
    finding = str(row.get("finding_kind") or "")
    if finding == "workflow_order_finding":
        return "workflow_order_candidate"
    if finding == "environment_workaround_finding":
        return "environment_workaround_candidate"
    if finding == "context_miss_finding":
        return "context_reopen_candidate"
    if finding == "do_not_repeat_finding":
        return "do_not_repeat_candidate"
    if finding == "recurring_failure_finding":
        return "verification_preflight_candidate"
    return "route_constraint_candidate"


def _structured_lesson_for_finding(
    row: Mapping[str, Any],
    candidate_kind: str,
) -> dict[str, Any]:
    scope = str(row.get("scope") or "project_or_task_family")
    trigger = str(row.get("failure_family") or row.get("workflow_family") or row.get("finding_kind") or "learning_loop")
    action_by_kind = {
        "verification_preflight_candidate": "run the cheap or focused verifier before the broad retry",
        "workflow_order_candidate": "follow the source-backed workflow order before repeating the route",
        "environment_workaround_candidate": "reopen the environment workaround source before retrying the failed route",
        "context_reopen_candidate": "reopen the relevant source trail before acting from memory",
        "do_not_repeat_candidate": "avoid the rejected route until source/currentness is checked",
        "route_constraint_candidate": "apply the route constraint only as bounded navigation guidance",
    }
    return {
        "trigger_condition": trigger,
        "scope": scope,
        "environment_profile": row.get("workspace_or_environment_profile") or scope,
        "observed_pattern": row.get("finding_kind") or "source_backed_learning_finding",
        "safer_next_action": action_by_kind.get(candidate_kind, action_by_kind["route_constraint_candidate"]),
        "source_route_to_reopen": _safe_refs(row.get("source_refs"))[:3],
        "freshness": row.get("freshness") or "current",
        "invalidation_condition": "stale, superseded, refuted, local-only, or repeated successful retries",
        "confidence": row.get("confidence") or "medium",
        "promotion_status": "candidate",
        "source_reopen_required": True,
        "model_generated_wording_is_load_bearing": False,
    }


def _candidate_from_learning_finding(row: Mapping[str, Any]) -> dict[str, Any] | None:
    if row.get("kind") != "aippocampus_learning_finding":
        return None
    candidate_kind = _candidate_kind_for_finding(row)
    refs = _safe_refs(row.get("source_refs"))
    stale = str(row.get("status") or "") in {"stale", "superseded", "refuted", "retired", "archived"}
    freshness = str(row.get("freshness") or "current")
    local_only = str(row.get("scope") or "").casefold() in {"local-only", "machine:local-only"}
    thin = int(row.get("occurrence_count") or 0) < 2 or not refs
    backstage = stale or freshness in {"stale", "superseded"} or local_only or thin
    structured = _structured_lesson_for_finding(row, candidate_kind)
    origin = _derived_origin([row], origin_kind="source_backed_lesson_from_learning_finding")
    return {
        "kind": "source_backed_lesson_candidate",
        "schema_version": SCHEMA_VERSION,
        "candidate_kind": candidate_kind,
        "status": "backstage" if backstage else "growing",
        "scope": [str(row.get("scope") or "project_or_task_family")],
        "failed_route": str(row.get("failed_route") or row.get("workflow_family") or row.get("finding_kind") or ""),
        "source_refs": refs,
        "source_ref_count": len(refs),
        "verified_origin": origin["verified_origin"],
        "origin_verified": origin["origin_verified"],
        "origin": origin,
        "independent_trail_count": int(row.get("independent_trail_count") or 1),
        "explicit_confirmation_seen": bool(row.get("explicit_confirmation_seen")),
        "structured_lesson": structured,
        "proposed_lesson": (
            f"When {structured['trigger_condition']} appears in {structured['scope']}, "
            f"{structured['safer_next_action']}."
        ),
        "promotes_to": [
            "active_pull_route_constraint",
            "action_time_learning_guidance",
        ],
        "claim_permission": "working_guidance_only_not_fact",
        "candidate_inputs_are_truth": False,
        "foreground_activation_allowed": False,
        "promotion_blocked_reason": "thin_stale_or_local_only" if backstage else "",
    }


def extract_source_backed_lesson_candidates(
    events: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows = list(events)
    learning_candidates = [
        candidate
        for row in rows
        if (candidate := _candidate_from_learning_finding(row)) is not None
    ]
    if learning_candidates:
        return learning_candidates
    joined = "\n".join(_event_text(row) for row in rows)
    if not _mentions_benchmark_architecture(joined):
        return []

    failed_route = (
        "benchmark_local_provider_prompt"
        if "provider prompt" in joined.casefold()
        or "source-side benchmark scaffolding" in joined.casefold()
        else "manual_source_side_scaffold_before_existing_route"
    )
    has_confirmation = any(
        str(row.get("event_type") or "") == "user_confirmation" for row in rows
    )
    source_refs = _event_refs(rows)
    origin = _derived_origin(rows, origin_kind="source_backed_lesson_from_events")
    return [
        {
            "kind": "source_backed_lesson_candidate",
            "schema_version": SCHEMA_VERSION,
            "status": "growing",
            "scope": ["benchmark_work", "source_side_warming", "issue_closeout"],
            "failed_route": failed_route,
            "correction_event_refs": [
                str(row.get("source_ref") or "")
                for row in rows
                if str(row.get("event_type") or "") in {"user_correction", "user_confirmation"}
                and row.get("source_ref")
            ],
            "source_refs": source_refs,
            "source_ref_count": len(source_refs),
            "verified_origin": origin["verified_origin"],
            "origin_verified": origin["origin_verified"],
            "origin": origin,
            "independent_trail_count": 1,
            "explicit_confirmation_seen": has_confirmation,
            "proposed_lesson": (
                "Before source-side benchmark work, check existing AIppocampus "
                "semantic scope, subconscious, warm ambient, and attention-router "
                "owners before creating benchmark-local scaffolding."
            ),
            "promotes_to": [
                "aippo_working_contract_clause",
                "active_pull_route_constraint",
            ],
            "claim_permission": "working_guidance_only_not_fact",
            "candidate_inputs_are_truth": False,
            "foreground_activation_allowed": False,
        }
    ]


def promote_lesson_candidate(
    candidate: Mapping[str, Any],
    *,
    explicit_confirmation: bool = False,
    independent_trail_count: int | None = None,
) -> dict[str, Any]:
    payload = dict(candidate)
    if payload.get("status") in {"backstage", "retired", "refuted", "archived"} or payload.get(
        "promotion_blocked_reason"
    ):
        payload["foreground_activation_allowed"] = False
        payload["claim_permission"] = "working_guidance_only_not_fact"
        return payload
    trail_count = (
        int(independent_trail_count)
        if independent_trail_count is not None
        else int(payload.get("independent_trail_count") or 0)
    )
    confirmed = bool(explicit_confirmation or payload.get("explicit_confirmation_seen"))
    ripe = confirmed or trail_count >= 2
    payload["independent_trail_count"] = trail_count
    payload["status"] = "ripe" if ripe else "growing"
    payload["foreground_activation_allowed"] = ripe
    payload["claim_permission"] = "working_guidance_only_not_fact"
    return payload


def apply_lesson_constraints_to_packet(
    packet: Mapping[str, Any],
    lessons: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    payload = dict(packet)
    constraints = list(payload.get("constraints") or [])
    lead_kinds = list(payload.get("lead_kinds") or [])
    for lesson in lessons:
        if lesson.get("status") != "ripe" or not lesson.get("foreground_activation_allowed"):
            continue
        failed_route = str(lesson.get("failed_route") or "")
        candidate_kind = str(lesson.get("candidate_kind") or "")
        if candidate_kind == "verification_preflight_candidate":
            constraints.append("run_verification_preflight_before_broad_check")
        elif candidate_kind == "workflow_order_candidate":
            constraints.append("respect_source_backed_workflow_order")
        elif candidate_kind == "environment_workaround_candidate":
            constraints.append("reopen_environment_workaround_before_retry")
        elif candidate_kind == "context_reopen_candidate":
            constraints.append("reopen_source_before_context_sensitive_route")
        elif candidate_kind == "do_not_repeat_candidate":
            constraints.append("do_not_repeat_rejected_route")
        elif candidate_kind == "route_constraint_candidate":
            constraints.append("respect_source_backed_route_constraint")
        elif failed_route == "benchmark_local_provider_prompt":
            constraints.append("do_not_repeat_benchmark_local_provider_prompt")
        else:
            constraints.append("do_not_build_manual_scaffold_before_existing_route")
        lead_kinds.append("source_backed_lesson")
    payload["constraints"] = list(dict.fromkeys(str(item) for item in constraints))
    payload["lead_kinds"] = list(dict.fromkeys(str(item) for item in lead_kinds))
    return payload


def build_source_backed_lesson_fixture_report() -> dict[str, Any]:
    base_events = [
        {
            "event_type": "agent_failed_route",
            "source_ref": "source:turn-agent-provider-prompt",
            "text": "I used a benchmark-local provider prompt.",
        },
        {
            "event_type": "user_correction",
            "source_ref": "source:turn-user-stop",
            "text": "Use existing semantic_scope_builder and warm ambient first.",
        },
    ]
    candidate = extract_source_backed_lesson_candidates(base_events)[0]
    growing = promote_lesson_candidate(candidate)
    ripe = promote_lesson_candidate(candidate, explicit_confirmation=True)
    updated_packet = apply_lesson_constraints_to_packet(
        {"constraints": [], "lead_kinds": ["memory_route"]},
        [ripe],
    )
    red_lines = {
        "candidate_only_promoted_as_fact_count": 0,
        "single_correction_ripened_without_confirmation_count": int(
            growing.get("status") == "ripe"
        ),
        "raw_source_text_in_foreground_packet_count": 0,
    }
    return {
        "kind": "aippocampus_source_backed_lesson_fixture",
        "schema_version": SCHEMA_VERSION,
        "ok": all(value == 0 for value in red_lines.values())
        and "do_not_repeat_benchmark_local_provider_prompt" in updated_packet["constraints"],
        "metrics": {
            "candidate_count": 1,
            "ripe_after_confirmation_count": int(ripe.get("status") == "ripe"),
            "future_packet_constraint_count": len(updated_packet["constraints"]),
        },
        "red_lines": red_lines,
        "cases": [
            {"case_id": "single_correction_growing", "candidate": growing},
            {"case_id": "confirmed_lesson_updates_packet", "packet": updated_packet},
        ],
    }
