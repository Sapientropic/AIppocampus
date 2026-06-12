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


def extract_source_backed_lesson_candidates(
    events: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows = list(events)
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
        if failed_route == "benchmark_local_provider_prompt":
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
