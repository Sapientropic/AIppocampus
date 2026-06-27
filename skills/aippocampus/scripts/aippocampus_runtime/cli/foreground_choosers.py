"""Foreground chooser payloads for parent CLI surfaces."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from typing import Any, TextIO

from aippocampus_runtime.contracts import (
    foreground_chooser_card,
    foreground_shell_action,
)


def print_chooser_card(title: str, payload: Mapping[str, Any], *, file: TextIO | None = None) -> None:
    target = file or sys.stdout
    print(title, file=target)
    decision = payload.get("decision") or payload.get("status") or "choose a foreground action"
    print(f"decision: {decision}", file=target)
    raw_choices = payload.get("choices")
    if isinstance(raw_choices, list) and raw_choices:
        action_source = raw_choices
    else:
        action_source = [
            payload.get("foreground_action"),
            *(payload.get("safe_next_actions") or []),
        ]
    actions = [action for action in action_source if isinstance(action, Mapping)]
    for index, action in enumerate(actions[:3]):
        command = action.get("command") or action.get("command_template") or action.get("label")
        if not command:
            continue
        prefix = "Try" if index == 0 else "Then"
        print(f"{prefix}: {command}", file=target)
    print("boundary: compact chooser only; use --help for full command reference.", file=target)


def _template_action(
    *,
    action_id: str,
    command_template: str,
    label: str,
    why: str,
    mutation_risk: str = "read_only",
    claim_boundary: str = "source_reopen_required_before_claims",
    requires: str | Sequence[str] | None = None,
    operator_only: bool | None = None,
) -> dict[str, Any]:
    action: dict[str, Any] = {
        "id": action_id,
        "label": label,
        "command_template": command_template,
        "template_only": True,
        "mutation_risk": mutation_risk,
        "claim_boundary": claim_boundary,
        "why": why,
    }
    if requires:
        if isinstance(requires, str):
            action["requires"] = [requires]
        else:
            action["requires"] = [str(item) for item in requires if str(item).strip()]
    if operator_only is not None:
        action["operator_only"] = operator_only
    return action


def agent_chooser_payload() -> dict[str, Any]:
    payload = foreground_chooser_card(
        kind="aippocampus_agent_recovery",
        status="command_required",
        decision="choose the foreground continuity action",
        choices=[
            _template_action(
                action_id="recall",
                label="Recall old context from a cue",
                command_template='aippocampus agent recall "{continuity_cue}" --json',
                requires="continuity_cue",
                why="Use recall for fuzzy old context, unfinished work, corrections, or handoffs.",
                claim_boundary="no_claim_before_reopen",
            ),
            foreground_shell_action(
                action_id="aippo",
                label="Ask for AIppo working guidance",
                command="aippocampus agent aippo --json",
                why="Use AIppo for task-contract orientation; guidance is not source truth.",
                mutation_risk="read_only",
                claim_boundary="working_guidance_not_source_truth",
            ),
            _template_action(
                action_id="background",
                label="Review background findings",
                command_template='aippocampus agent background "{task_cue}" --json',
                requires="task_cue",
                why=(
                    "Use for reviewed Dream/subconscious findings relevant to this task; "
                    "they are navigation only until source is reopened."
                ),
                claim_boundary="background_navigation_not_source_truth",
            ),
            _template_action(
                action_id="deepen",
                label="Deepen the selected route",
                command_template=(
                    "aippocampus agent deepen --request {request_index} "
                    "--recall-selector {recall_selector} --json"
                ),
                requires=["request_index", "recall_selector"],
                why=(
                    "Use after recall chooses a route; prefer the emitted recall_selector. "
                    "--last-recall is a mutable-cache compatibility fallback."
                ),
                claim_boundary="source_reopen_required_before_claim",
            ),
            _template_action(
                action_id="feedback",
                label="Record scoped route feedback",
                command_template="aippocampus agent feedback {route_id} --outcome {feedback_outcome} --json",
                requires=["route_id", "feedback_outcome"],
                why="Feedback is a low-authority control lane; it is not source evidence.",
                mutation_risk="explicit_feedback_write",
                claim_boundary="feedback_is_not_source_truth",
            ),
        ],
    )
    payload["command_gradient"] = {
        "agent_recall": "fuzzy continuity route finding from an old cue",
        "agent_deepen": "open the selected recall route before claims",
        "search": "exact/source wording when the phrase is known",
        "agent_background": "reviewed Dream/subconscious navigation, not evidence",
    }
    return payload


def memory_chooser_payload() -> dict[str, Any]:
    payload = foreground_chooser_card(
        kind="aippocampus_memory_chooser",
        decision="choose a source-backed memory read path",
        choices=[
            _template_action(
                action_id="agent_recall",
                label="Recall fuzzy continuity",
                command_template='aippocampus agent recall "{continuity_cue}" --json',
                requires="continuity_cue",
                why="Use for old decisions, unfinished work, style preferences, corrections, or handoffs.",
                claim_boundary="no_claim_before_reopen",
            ),
            _template_action(
                action_id="search_exact_phrase",
                label="Search exact clean-source wording",
                command_template='aippocampus search "{exact_phrase}" --json',
                requires="exact_phrase",
                why="Use when the user or agent remembers wording and needs a source route.",
                claim_boundary="search_result_requires_source_boundary",
            ),
            foreground_shell_action(
                action_id="latest_reply",
                label="Inspect latest closeout",
                command="aippocampus latest-reply --cwd . --json",
                why="Use when continuing from the latest final assistant closeout.",
                mutation_risk="read_only",
                claim_boundary="latest_reply_is_navigation_not_memory_fact",
            ),
            foreground_shell_action(
                action_id="list_threads",
                label="List registered source threads",
                command="aippocampus onboard --provider auto --status --json",
                why="Use when no source appears available or registration needs checking.",
                mutation_risk="read_only",
                claim_boundary="setup_status_not_memory_evidence",
            ),
        ],
    )
    payload["command_gradient"] = {
        "agent_recall": "fuzzy continuity route finding from old decisions, corrections, or handoffs",
        "search": "exact/source wording search when a distinctive phrase is known",
        "latest_reply": "latest final closeout, useful for immediate continuation",
        "onboard_status": "source registration/status when no source route appears available",
    }
    payload["intent_gradient"] = payload["command_gradient"]
    return payload


CONTROL_GRADIENT = {
    "pause": "temporary or route-scoped quieting",
    "do_not_use_here": "current-scope exclusion for a bad route",
    "forget": "stronger explicit target workflow; no surprise deletion from the chooser",
    "why_not_recall": "diagnose why a route stayed silent",
}


def privacy_chooser_payload() -> dict[str, Any]:
    payload = foreground_chooser_card(
        kind="aippocampus_privacy_chooser",
        decision="choose a privacy or control surface",
        choices=[
            foreground_shell_action(
                action_id="open_controls",
                label="Open personal controls",
                command="aippocampus controls --json",
                why="Use when the user wants pause, forget, do-not-use-here, or why-not control lanes.",
                mutation_risk="read_only",
                claim_boundary="control_card_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="do_not_use_here",
                label="Quiet this context",
                command="aippocampus do-not-use-here --json",
                why="Shows the scoped no-use boundary before any feedback write.",
                mutation_risk="read_only",
                claim_boundary="feedback_is_not_source_truth",
            ),
            foreground_shell_action(
                action_id="export_boundary",
                label="Inspect export choices",
                command="aippocampus export --json",
                why="Use before moving local bundles or deciding public/private export scope.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="provider_key_boundary",
                label="Inspect provider-key boundary",
                command="aippocampus provider-key --json",
                why="Provider keys are optional and should not be printed by default.",
                mutation_risk="read_only",
                claim_boundary="provider_config_not_memory_evidence",
            ),
        ],
    )
    payload["control_gradient"] = CONTROL_GRADIENT
    payload["default_posture"] = {
        "same_user_conversation_source": "allow_with_boundary",
        "ordinary_memory_route": "private_route",
        "external_projection": "blocked_without_explicit_export",
        "secret_or_credential_material": "hard_block",
        "boundary": (
            "Privacy controls narrow or stop specific reuse; they should not make "
            "ordinary local source-backed continuity feel unavailable by default."
        ),
    }
    return payload


def controls_chooser_payload() -> dict[str, Any]:
    payload = foreground_chooser_card(
        kind="aippocampus_controls_chooser",
        decision="choose a scoped personal control",
        choices=[
            foreground_shell_action(
                action_id="pause_scope",
                label="Open pause scope card",
                command="aippocampus pause --json",
                why="Shows the scoped-control boundary before any feedback write.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="forget_scope",
                label="Open forget scope card",
                command="aippocampus forget --json",
                why="Shows the scoped-control boundary before any feedback write.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="do_not_use_here",
                label="Open do-not-use-here card",
                command="aippocampus do-not-use-here --json",
                why="Shows the scoped no-use boundary before any feedback write.",
                mutation_risk="read_only",
                claim_boundary="feedback_is_not_source_truth",
            ),
            _template_action(
                action_id="why_not_recall",
                label="Explain why recall stayed silent",
                command_template='aippocampus why-not-recall "{continuity_cue}" --json',
                requires="continuity_cue",
                why="Use when the question is why a route did not surface.",
                mutation_risk="read_only",
                claim_boundary="diagnostic_not_source_evidence",
            ),
            _template_action(
                action_id="find_control_target",
                label="Find a route id first",
                command_template='aippocampus agent recall "{route_to_quiet}" --json',
                requires="route_to_quiet",
                why="Use this if you do not yet have the concrete route id.",
                mutation_risk="read_only",
                claim_boundary="no_claim_before_reopen",
            ),
        ],
    )
    payload["control_gradient"] = CONTROL_GRADIENT
    return payload


def warm_chooser_payload() -> dict[str, Any]:
    payload = foreground_chooser_card(
        kind="aippocampus_warm_chooser",
        status="command_or_prompt_required",
        decision="inspect warm status before optional operator warming",
        choices=[
            foreground_shell_action(
                action_id="status",
                label="Inspect warm ambient status",
                command="aippocampus warm status --json",
                why="Read-only status should be the first path; it does not run warm jobs.",
                mutation_risk="read_only",
                claim_boundary="warm_status_not_source_evidence",
            ),
            _template_action(
                action_id="run_with_prompt",
                label="Run optional warm job with a prompt",
                command_template='aippocampus warm --prompt "{cue}" --json',
                requires="cue",
                why="Warm runs are operator paths and should not be started by the bare parent command.",
                mutation_risk="operator_model_job",
                claim_boundary="warm_output_is_navigation_until_source_reopen",
                operator_only=True,
            ),
            foreground_shell_action(
                action_id="repair_or_disable",
                label="Find repair or disable action",
                command="aippocampus warm status --json",
                why="When warm is blocked or stale, status is the safe surface for repair/disable actions.",
                mutation_risk="read_only",
                claim_boundary="warm_status_not_source_evidence",
            ),
            _template_action(
                action_id="ordinary_recall",
                label="Use ordinary source-backed recall",
                command_template='aippocampus agent recall "{continuity_cue}" --json',
                requires="continuity_cue",
                why="Warm ambient is optional; ordinary recall remains the primary continuity path.",
                claim_boundary="no_claim_before_reopen",
            ),
        ],
    )
    return payload
