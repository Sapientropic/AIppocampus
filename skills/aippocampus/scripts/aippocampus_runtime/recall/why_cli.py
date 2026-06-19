#!/usr/bin/env python3
"""CLI wrapper for recall why/why-not diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Mapping

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_shell_action,
    foreground_template_action,
    shell_quote,
)
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall.why_diagnostics import recall_diagnostic_report
from aippocampus_runtime.recall.why_reason_codes import DEFAULT_MAX_ROUTES


def _quoted(value: str) -> str:
    return shell_quote(value)


def _cue_for_command(cue: str) -> str:
    raw = str(cue or "")
    redacted = str(redact_sensitive_values(redact_private_paths(raw)))
    if redacted != raw:
        return "redacted cue from current prompt"
    return raw


def render_text(payload: Mapping[str, Any]) -> str:
    mode = str(payload.get("mode") or "why-recall")
    decision = str(payload.get("decision") or "unknown")
    diagnostic = str(payload.get("diagnostic_class") or "unknown")
    reasons = [str(item) for item in payload.get("reasons") or []][:3]
    specificity = payload.get("route_specificity") or "unknown"
    raw_action_card = payload.get("action_card")
    action_card: Mapping[str, Any] = raw_action_card if isinstance(raw_action_card, Mapping) else {}
    if mode == "why-not-recall" and diagnostic == "surfaced_but_low_specificity":
        happened = "A route did surface, but it was too broad to treat as a good recall answer."
        next_command = "aippocampus why-recall \"<more specific cue>\""
    elif decision == "surfaced":
        happened = "Recall surfaced a source route."
        next_command = "aippocampus agent recall \"<cue>\" --public"
    elif decision in {"suppressed", "silent"}:
        happened = "Recall stayed quiet or suppressed the route."
        next_command = "tighten the cue, then run aippocampus why-recall \"<cue>\""
    else:
        happened = f"Recall diagnostic returned {decision}."
        next_command = "aippocampus health --json"
    if action_card.get("next_command"):
        next_command = str(action_card["next_command"])
    elif payload.get("next_safe_action") == "reopen_source":
        next_command = "aippocampus agent recall \"<cue>\" --public; then deepen before claims"
    display_cue = str(payload.get("_display_cue") or "").strip()
    if display_cue:
        quoted = _quoted(display_cue)
        next_command = next_command.replace('"<cue>"', quoted)
        next_command = next_command.replace('"<distinctive exact phrase>"', quoted)
        next_command = next_command.replace('" <cue> "', f" {quoted} ")
        if "then deepen route 1" in next_command:
            next_command = next_command.replace(
                "then deepen route 1",
                "then aippocampus agent deepen --request 1 --last-recall --json",
            )
    lines = [
        f"AIppocampus {mode}",
        f"what happened: {happened}",
        f"specificity: {specificity}",
        f"why: {', '.join(reasons) or 'no blocking reason recorded'}",
        f"next: {next_command}",
        "boundary: this diagnostic is route guidance, not source evidence.",
    ]
    return "\n".join(lines)


def _description_for_prog(prog: str) -> str:
    if "why-not" in prog:
        return """What this command is for:
  Explain why memory did not help, or why a surfaced route is too broad to trust.
  Primary next action: refine cue first; deepen only if continuity genuinely matters.

Advanced/operator detail:
  Semantic, lock, cache, and handle flags are diagnostics for local investigation."""
    return """What this command is for:
  Explain why recall surfaced, stayed silent, or degraded before you rely on memory.
  Primary next action: deepen selected route before claims, or refine cue if no route surfaced.

Advanced/operator detail:
  Semantic, lock, cache, and handle flags are diagnostics for local investigation."""


def build_parser(prog: str = "aippocampus why-recall") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        usage=f"{prog} cue [--json] [advanced/operator flags]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=_description_for_prog(prog),
    )
    parser.add_argument("cue", nargs="?")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--clean-source-dir")
    parser.add_argument("--registry-dir")
    parser.add_argument("--registry")
    parser.add_argument("--max", type=int, default=DEFAULT_MAX_ROUTES)
    parser.add_argument("--handle")
    parser.add_argument("--thread-id")
    parser.add_argument("--topic-epoch")
    parser.add_argument("--lock-id")
    parser.add_argument("--lock-path")
    parser.add_argument("--cache-path")
    parser.add_argument("--semantic-result-json")
    parser.add_argument("--run-semantic-gate", action="store_true")
    parser.add_argument("--semantic-gate-mode", choices=["off", "auto", "on"], default="off")
    parser.add_argument("--semantic-timeout", type=int, default=12)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--detail",
        choices=["compact", "full"],
        default="compact",
        help="JSON detail level. Default JSON emits a compact foreground explanation card.",
    )
    parser.add_argument(
        "--operator-json",
        action="store_true",
        help="Emit the full diagnostic JSON for local investigation.",
    )
    return parser


def render_compact_help(mode: str) -> str:
    if mode == "why-not-recall":
        first_line = "Explain silence or no-help recall before you broaden search."
        example = 'aippocampus why-not-recall "old decision about setup"'
        when = "Use why-not-recall when recall stayed quiet or surfaced only broad/noisy routes."
    else:
        first_line = "Explain a surfaced, stale-looking, broad, or surprising recall route."
        example = 'aippocampus why-recall "old decision about setup"'
        when = "Use why-recall after recall/search when you need to understand a route before relying on it."
    return "\n".join(
        [
            f"usage: aippocampus {mode} \"<cue>\" [--json]",
            "",
            "What this command is for:",
            f"  {first_line}",
            "",
            "Useful shapes:",
            f"  {example}",
            '  aippocampus agent recall "old cue" --json',
            "  aippocampus agent deepen --request 1 --last-recall --json",
            "  primary next action: deepen selected route before claims, or refine cue if no route surfaced.",
            "",
            "When to use it:",
            f"  {when}",
            "  Use agent recall/deepen for the normal source-backed path.",
            "",
            "Boundary:",
            "  This is recovery/explanation guidance, not source evidence.",
            "  Reopen/deepen the selected route before claims.",
            "",
            "Advanced/operator flags:",
            f"  aippocampus {mode} --help-advanced",
        ]
    )


def _recovery_payload(mode: str) -> dict[str, Any]:
    actions = [
        foreground_template_action(
            action_id="diagnose_with_cue",
            label="Run recall diagnostic with a cue",
            command_template=f'aippocampus {mode} "{{cue}}" --json',
            requires=["cue"],
            mutation_risk="read_only",
            claim_boundary="diagnostic_not_source_evidence",
            why="Use when you have the cue whose recall behavior needs explanation.",
        ),
        foreground_shell_action(
            action_id="deepen_selected_route",
            label="Deepen selected route after recall",
            command="aippocampus agent deepen --request 1 --last-recall --json",
            mutation_risk="read_only",
            claim_boundary="no_claim_before_reopen",
            why="Use after recall has written a same-machine route request cache.",
        )
        | {"depends_on": "last_recall_cache"},
    ]
    return {
        "kind": "aippocampus_recall_diagnostic_recovery",
        "mode": mode,
        "ok": False,
        "error": {
            "code": "cue_required",
            "message": "Provide a cue so the diagnostic can explain a recall route or silence.",
        },
        "example_cue": "old decision about setup",
        "when_to_use": {
            "why-recall": "Use when recall surfaced a route that is surprising, stale-looking, broad, or needs explanation.",
            "why-not-recall": "Use when recall stayed silent or did not help for a cue you expected to work.",
        },
        **canonical_foreground_action_fields(actions[0], safe_next_actions=actions),
        "next_actions": actions,
        "claim_boundary": "Diagnostic output is route guidance, not source evidence; reopen source before claims.",
    }


def _attach_foreground_actions(payload: dict[str, Any], *, cue: str) -> dict[str, Any]:
    cue_arg = _quoted(_cue_for_command(cue))
    recall_command = f"aippocampus agent recall {cue_arg} --json"
    search_command = f"aippocampus search {cue_arg} --json"
    onboard_command = "aippocampus onboard --provider auto --status --json"
    deepen_command = "aippocampus agent deepen --request 1 --last-recall --json"
    next_safe = str(payload.get("next_safe_action") or "")
    decision = str(payload.get("decision") or "")
    diagnostic = str(payload.get("diagnostic_class") or "")
    specificity = str(payload.get("route_specificity") or "")
    primary: dict[str, Any]
    tighten_action: dict[str, Any] = foreground_template_action(
        action_id="tighten_cue",
        label="Tighten the diagnostic cue",
        command_template='aippocampus why-recall "{more_specific_cue}" --json',
        requires=["more_specific_cue"],
        why="The surfaced route was too broad; refine the cue before repeating recall.",
        mutation_risk="read_only",
        claim_boundary="diagnostic_not_source_evidence",
    )
    deepen_action = foreground_shell_action(
        action_id="deepen_after_recall",
        label="Deepen after recall",
        command=deepen_command,
        why="Routes already surfaced; inspect the selected route before using it.",
        mutation_risk="read_only",
        claim_boundary="no_claim_before_reopen",
    ) | {"depends_on": "last_recall_cache"}
    if next_safe == "run_onboard_or_build_clean_source":
        primary = foreground_shell_action(
            action_id="check_onboarding_status",
            label="Check onboarding status",
            command=onboard_command,
            why="Clean source or registration is missing; status is the next executable repair check.",
            mutation_risk="read_only",
            claim_boundary="diagnostic_not_source_evidence",
        )
    elif diagnostic == "surfaced_but_low_specificity" or specificity == "low":
        primary = tighten_action
    elif decision == "surfaced" or next_safe == "reopen_source":
        primary = deepen_action
    else:
        primary = foreground_shell_action(
            action_id="search_same_cue",
            label="Search same cue",
            command=search_command,
            why="No route is claim-ready; use the same cue as a bounded source search before broadening.",
            mutation_risk="read_only",
            claim_boundary="source_reopen_required_before_claim",
        )
    candidate_actions: list[dict[str, Any]] = [
        primary,
        foreground_shell_action(
            action_id="recall_same_cue",
            label="Recall same cue",
            command=recall_command,
            why="Use recall when the cue is fuzzy or route-shaped.",
            mutation_risk="read_only",
            claim_boundary="no_claim_before_reopen",
        ),
        deepen_action,
    ]
    if primary["id"] != "check_onboarding_status":
        candidate_actions.append(
            foreground_shell_action(
                action_id="check_onboarding_status",
                label="Check onboarding status",
                command=onboard_command,
                why="Use if clean source or registration appears missing.",
                mutation_risk="read_only",
                claim_boundary="diagnostic_not_source_evidence",
            )
        )
    actions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for action in candidate_actions:
        action_id = str(action.get("id") or "")
        if action_id in seen_ids:
            continue
        seen_ids.add(action_id)
        actions.append(action)
    action_card = payload.get("action_card")
    if isinstance(action_card, dict):
        next_command = primary.get("command") or primary.get("command_template")
        action_card["next_command"] = next_command
        action_card["primary_action"] = primary["id"]
        action_card["claim_boundary"] = "diagnostic_not_source_evidence"
    if next_safe:
        payload["authority_next_safe_action"] = next_safe
    payload.update(canonical_foreground_action_fields(primary, safe_next_actions=actions))
    payload["foreground_next_action"] = primary["id"]
    payload["next_safe_action"] = primary["id"]
    return payload


def attach_foreground_actions(payload: dict[str, Any], *, cue: str) -> dict[str, Any]:
    return _attach_foreground_actions(payload, cue=cue)


def _compact_json_payload(payload: Mapping[str, Any], *, cue: str) -> dict[str, Any]:
    """Project diagnostic internals into a foreground explanation card.

    The full report is still available for operator investigation, but default
    JSON should answer the agent's first question: what happened and what is the
    smallest safe next action? Raw route ids, surface reports, and observatory
    counters are deliberately kept behind `--detail full`.
    """

    mode = str(payload.get("mode") or "why-recall")
    reasons = [str(item) for item in payload.get("reasons") or [] if str(item)][:3]
    primary = payload.get("foreground_action")
    safe_actions = payload.get("safe_next_actions")
    if not isinstance(primary, Mapping):
        primary = foreground_template_action(
            action_id="diagnose_with_cue",
            label="Run recall diagnostic with a cue",
            command_template=f'aippocampus {mode} "{{cue}}" --json',
            requires=["cue"],
            why="Use when the diagnostic did not produce a concrete next action.",
            mutation_risk="read_only",
            claim_boundary="diagnostic_not_source_evidence",
        )
    actions = [
        action
        for action in (safe_actions if isinstance(safe_actions, list) else [primary])
        if isinstance(action, Mapping)
    ]
    compact = {
        "kind": "aippocampus_recall_diagnostic_compact",
        "mode": mode,
        "ok": bool(payload.get("ok", True)),
        "status": payload.get("status") or "ok",
        "cue": _cue_for_command(cue),
        "decision": payload.get("decision"),
        "diagnostic_class": payload.get("diagnostic_class"),
        "route_specificity": payload.get("route_specificity"),
        "explanation_card": {
            "what_happened": payload.get("decision")
            or payload.get("diagnostic_class")
            or "diagnostic_complete",
            "why": reasons,
            "next": payload.get("foreground_next_action") or payload.get("next_safe_action"),
        },
        **canonical_foreground_action_fields(primary, safe_next_actions=actions),
        "claim_boundary": "Diagnostic output is route guidance, not source evidence; reopen/deepen before claims.",
        "operator_detail_command": f"aippocampus {mode} {_quoted(_cue_for_command(cue))} --json --detail full",
    }
    return redact_sensitive_values(
        redact_private_paths({key: value for key, value in compact.items() if value not in (None, "", [])})
    )


def render_recovery_text(payload: Mapping[str, Any]) -> str:
    mode = str(payload.get("mode") or "why-recall")
    actions = [row for row in payload.get("next_actions") or [] if isinstance(row, Mapping)]
    lines = [
        f"AIppocampus {mode}",
        "what happened: no cue was provided, so no diagnostic ran.",
        "example cue: old decision about setup",
        "when to use why-recall: explain a surprising or broad surfaced route.",
        "when to use why-not-recall: explain silence or no-help recall.",
    ]
    if actions:
        lines.append("next: " + str(actions[0].get("command") or actions[0].get("command_template")))
        if len(actions) > 1:
            lines.append("then: " + str(actions[1].get("command") or actions[1].get("command_template")))
    lines.append("boundary: diagnostic route guidance is not source evidence.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    mode = "why-recall"
    if args_list and args_list[0] in {"why-recall", "why-not-recall", "why-not"}:
        raw_mode = args_list.pop(0)
        mode = "why-not-recall" if raw_mode == "why-not" else raw_mode
    prog = f"aippocampus {mode}"
    if args_list and args_list[0] in {"--help", "-h"}:
        print(render_compact_help(mode))
        return 0
    if args_list and args_list[0] in {"--help-advanced", "--advanced-help"}:
        build_parser(prog=prog).print_help()
        return 0
    args = build_parser(prog=prog).parse_args(args_list)
    if not args.cue:
        payload = _recovery_payload(mode)
        print(
            json.dumps(payload, ensure_ascii=False, indent=2)
            if args.json or args.operator_json
            else render_recovery_text(payload)
        )
        return 2
    payload = recall_diagnostic_report(
        cue=args.cue,
        mode=mode,
        cwd=args.cwd,
        clean_source_dir=args.clean_source_dir,
        registry_dir=args.registry_dir,
        registry_path=args.registry,
        max_routes=args.max,
        handle=args.handle,
        thread_id=args.thread_id,
        topic_epoch=args.topic_epoch,
        lock_id=args.lock_id,
        lock_path=args.lock_path,
        cache_path=args.cache_path,
        semantic_result_json=args.semantic_result_json,
        run_live_semantic_gate=args.run_semantic_gate,
        semantic_gate_mode=args.semantic_gate_mode,
        semantic_timeout=args.semantic_timeout,
    )
    payload = _attach_foreground_actions(payload, cue=args.cue)
    if args.json or args.operator_json:
        output_payload = payload if args.operator_json or args.detail == "full" else _compact_json_payload(payload, cue=args.cue)
        print(json.dumps(output_payload, ensure_ascii=False, indent=2))
    else:
        text_payload = dict(payload)
        text_payload["_display_cue"] = args.cue
        print(render_text(text_payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
