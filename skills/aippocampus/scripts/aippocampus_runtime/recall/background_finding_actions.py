"""Action handles for reviewed background finding cards.

These helpers keep the foreground ``agent background`` card action-oriented
without letting Dream/subconscious rows become source truth. Every action is
tied back to the selected finding id and its reviewed source-finding ids so a
later agent can deepen the exact route instead of looping on the broad cue.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.contracts import foreground_shell_action
from aippocampus_runtime.contracts import shell_quote as _shell_quote
from aippocampus_runtime.source.registry_source_routes import registry_source_window_command
from aippocampus_runtime.subconscious import candidate_router


def shell_quote(text: str) -> str:
    return _shell_quote(text)


def source_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    refs = [item for item in row.get("source_refs") or [] if isinstance(item, Mapping)]
    source_finding_ids = [
        str(item)
        for item in row.get("source_finding_ids") or []
        if str(item).strip()
    ]
    strength = row.get("source_strength")
    strength_map = strength if isinstance(strength, Mapping) else {}
    return {
        "source_ref_count": int(strength_map.get("source_ref_count") or len(refs)),
        "source_finding_ids": source_finding_ids[:4],
        "source_finding_count": len(source_finding_ids),
        "source_reopen_required_before_claims": True,
        "raw_source_refs_emitted": False,
    }


def route_action_grammar(row: Mapping[str, Any]) -> str:
    route = str(row.get("route") or "").strip()
    if route == candidate_router.USE_WITH_SOURCE:
        return "reopenable_route"
    if route in {candidate_router.USE_SILENTLY, candidate_router.CONFIRM_WHEN_RELEVANT}:
        return "direction_only"
    return "ignore_or_blocked"


def _is_action_hint_candidate(row: Mapping[str, Any]) -> bool:
    if str(row.get("candidate_type") or "") == "hook_trigger":
        return True
    haystack = " ".join(
        str(value or "")
        for value in (
            row.get("shape_label"),
            row.get("finding_type"),
            row.get("title"),
            row.get("summary"),
            row.get("route_reason"),
            *(row.get("activation_cues") or []),
            *(row.get("trigger_terms") or []),
        )
    ).casefold()
    return "action-time" in haystack or "action hint" in haystack


def _action_target(row: Mapping[str, Any]) -> dict[str, Any]:
    source = source_summary(row)
    return {
        "finding_id": str(row.get("candidate_key") or row.get("route_id") or "").strip(),
        "finding_type": str(row.get("candidate_type") or "working_memory"),
        "source_finding_ids": list(source["source_finding_ids"]),
        "source_ref_count": source["source_ref_count"],
        "action_grammar": route_action_grammar(row),
    }


def _first_reopenable_source_ref(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for ref in row.get("source_refs") or []:
        if not isinstance(ref, Mapping):
            continue
        thread_key = str(ref.get("thread_key") or "").strip()
        message_id = str(ref.get("message_id") or ref.get("id") or "").strip()
        line = ref.get("line") or ref.get("source_line")
        if thread_key and (message_id or line not in (None, "")):
            return ref
    return None


def _open_source_arguments(cue: str, ref: Mapping[str, Any]) -> dict[str, Any]:
    line = ref.get("line") or ref.get("source_line")
    arguments = {
        "query": cue,
        "scope": "all_registered_sources",
        "open_source": True,
        "thread_key": ref.get("thread_key"),
        "message_id": ref.get("message_id") or ref.get("id"),
        "line": line,
    }
    return {key: value for key, value in arguments.items() if value not in (None, "", [], {})}


def _background_source_action(
    row: Mapping[str, Any],
    *,
    cue: str,
) -> dict[str, object]:
    source_ref = _first_reopenable_source_ref(row)
    if route_action_grammar(row) == "reopenable_route" and source_ref is not None:
        command = registry_source_window_command(source_ref)
        if command:
            # Background findings are scent. When the reviewer preserved a
            # concrete clean-source handle, the foreground action should open
            # that handle directly; routing the agent back through recall lets
            # atlas/APW/familiarity layers steal the next step from the source.
            action = foreground_shell_action(
                action_id="reopen_background_finding_source_route",
                label="Open this finding's source window",
                command=command,
                why=(
                    "This reviewed background finding kept a clean-source handle; "
                    "open that bounded source window before using the scent."
                ),
                mutation_risk="read_only",
                claim_boundary="source_reopen_required_before_claim",
            )
            action["tool_name"] = "search_memory"
            action["arguments"] = _open_source_arguments(cue, source_ref)
            return action

    # Direction-only rows may be useful orientation, but their source refs are
    # often provenance for the reviewed finding rather than the target evidence
    # for the user's current cue. Searching the cue keeps the foreground path
    # source-led without letting background ids hijack recall ranking.
    why = (
        "This reviewed direction-only finding kept provenance refs, but they may not be "
        "target evidence for the current cue; search the cue instead of appending "
        "background ids to recall."
        if source_ref is not None
        else (
            "This reviewed background finding has no direct clean-source handle; "
            "search the original cue instead of appending background ids to recall."
        )
    )
    action = foreground_shell_action(
        action_id="search_sources_for_background_cue",
        label="Search sources for this background cue",
        command=f"aippocampus search --all {shell_quote(cue)} --json",
        why=why,
        mutation_risk="read_only",
        claim_boundary="background_scent_needs_source_search",
    )
    action["tool_name"] = "search_memory"
    action["arguments"] = {"query": cue, "scope": "all_registered_sources"}
    return action


def finding_next_actions(row: Mapping[str, Any], *, cue: str) -> list[dict[str, Any]]:
    target = _action_target(row)
    finding_id = str(target["finding_id"])
    quoted_finding_id = shell_quote(finding_id)
    actions = [
        _background_source_action(row, cue=cue),
        foreground_shell_action(
            action_id="mark_background_finding_helpful",
            label="Mark this route helpful",
            command=f"aippocampus agent feedback {quoted_finding_id} --outcome helped --json",
            why="Helpful/wrong feedback is low-authority calibration, not source truth.",
            mutation_risk="durable_low_authority_feedback_write",
            claim_boundary="feedback_is_not_source_truth",
        ),
        foreground_shell_action(
            action_id="mark_background_finding_wrong",
            label="Mark this route wrong",
            command=f"aippocampus agent feedback {quoted_finding_id} --outcome wrong --json",
            why="Use when the background route is distracting or irrelevant for this task.",
            mutation_risk="durable_low_authority_feedback_write",
            claim_boundary="feedback_is_not_source_truth",
        ),
        foreground_shell_action(
            action_id="keep_background_finding_quiet",
            label="Keep this route quiet",
            command=f"aippocampus agent feedback {quoted_finding_id} --outcome ignored --json",
            why="Use when the finding is not wrong, but should not keep interrupting this task shape.",
            mutation_risk="durable_low_authority_feedback_write",
            claim_boundary="feedback_is_not_source_truth",
        ),
    ]
    if _is_action_hint_candidate(row):
        # Cache writes stay explicit and narrow: ordinary Dream/subconscious
        # findings should not refresh action hints unless the reviewed row is
        # itself about action-time guidance.
        actions.append(
            foreground_shell_action(
                action_id="materialize_action_hint_from_finding",
                label="Materialize action-hint cache",
                command="aippocampus hooks action refresh-cache --write --json",
                why=(
                    "This reviewed finding looks action-time relevant; refresh the "
                    "prepared cache explicitly so the cache writer can apply its "
                    "source and privacy eligibility checks."
                ),
                mutation_risk="explicit_local_cache_write",
                claim_boundary="candidate_guidance_not_source_truth",
            )
        )
    return [{**dict(action), "target": dict(target)} for action in actions]


__all__ = ["finding_next_actions", "route_action_grammar", "shell_quote", "source_summary"]
