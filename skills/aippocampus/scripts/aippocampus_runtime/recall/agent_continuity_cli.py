"""CLI parser and command dispatch for the agent-continuity facade."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.cli.human_io import exit_code_for_payload
from aippocampus_runtime.cli.recovery import action_command_text
from aippocampus_runtime.mcp.agent_deepen_projection import compact_agent_deepen_payload
from aippocampus_runtime.mcp.agent_explain_projection import project_agent_explain_cli_payload
from aippocampus_runtime.public_output import emit_public_text
from aippocampus_runtime.recall import (
    agent_deepen_requests,
    attention_router_policy,
    background_findings,
    feedback_events,
    task_orientation,
)
from aippocampus_runtime.recall import (
    associative_path_fallback as apw_fallback,
)
from aippocampus_runtime.recall.agent_continuity import (
    KIND,
    MACRO_PACKET_SCHEMA_VERSION,
    MAX_ROUTES,
    SCHEMA_VERSION,
    _macro_positional_cue_payload,
    _operator_aippo_payload_with_foreground_card,
    _public_payload,
    _render_macro_recovery_text,
    activate_aippo,
    capture_feedback,
    deepen,
    explain,
    macro_orientation,
    recall,
)
from aippocampus_runtime.recall.agent_continuity_cli_support import (
    agent_recall_missing_query_payload,
    attach_recall_gate_context_to_payload,
    compact_aippo_guidance_card,
    compact_feedback_receipt,
    feedback_lane_resolution,
    handle_from_last_recall_cache,
    last_recall_selector_recovery_fields,
    last_recall_unavailable_payload,
    macro_schema_help,
    macro_state_template,
    mark_last_recall_request_opened,
    missing_feedback_route_payload,
    normalize_route_limit,
    opened_route_keys_from_last_recall_cache,
    public_recall_projection,
    query_from_last_recall_cache,
    recall_selector_cache_candidates,
    render_aippo_human,
    render_deepen_human,
    render_macro_human,
    render_macro_schema_human,
    render_recall_human,
    write_last_recall_cache,
    write_recall_selector_snapshot,
)


def _json_out(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _route_limit_arg(value: str) -> int:
    try:
        return normalize_route_limit(value, default=MAX_ROUTES)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _parser() -> argparse.ArgumentParser:
    """aippocampus-stage-map: build argparse contract; command execution stays in main."""

    parser = argparse.ArgumentParser(
        prog="aippocampus agent",
        description=(
            "Agent continuity path: recall old context, deepen source, then use "
            "AIppo/background/explain/feedback as supporting actions."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "First useful loop:\n"
            '  aippocampus agent recall "old cue" --json\n'
            "  follow the emitted deepen action; when a recall_selector is present, prefer:\n"
            "  aippocampus agent deepen --request 1 --recall-selector <emitted-selector> --json\n"
            '  aippocampus agent aippo "task cue" --json\n'
            '  aippocampus agent background "task cue" --json\n'
            "  aippocampus agent feedback <route_id> --outcome source_reopen_success --json\n\n"
            "Default recall JSON is compact and foreground-safe. Use --detail full only for "
            "local diagnostics that may include private handles."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    recall_parser = sub.add_parser(
        "recall",
        usage="aippocampus agent recall \"old cue\" [--json] [options]",
        description=(
            "Agent recall task card:\n"
            "  Use for fuzzy continuity cues, old decisions, interrupted work, and handoffs.\n"
            "  Default compact JSON is the foreground-safe surface; --public is a compatibility alias.\n"
            "  Use `aippocampus search \"exact phrase\"` for exact wording lookup.\n"
            "  Treat recall packets as routes; deepen/reopen before factual, stale, or public claims.\n"
            "  Use --detail full only for local diagnostics that may expose private handles."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    recall_parser.add_argument("query", nargs="*")
    recall_parser.add_argument("--query", dest="query_flag")
    recall_parser.add_argument("--cwd")
    recall_parser.add_argument("--clean-source-dir")
    recall_parser.add_argument("--registry-dir")
    recall_parser.add_argument("--macro-state-jsonl")
    recall_parser.add_argument("--project", default="AIppocampus")
    recall_parser.add_argument("--max", type=_route_limit_arg, default=MAX_ROUTES)
    recall_parser.add_argument("--attention-router", action="store_true", help="Use attention router opt-in route sorting.")
    recall_parser.add_argument("--attention-router-mode", choices=attention_router_policy.VALID_MODES)
    recall_parser.add_argument(
        "--feedback-jsonl",
        help="Optional low-authority route feedback JSONL used only for bounded route ordering metadata.",
    )
    recall_parser.add_argument("--semantic", choices=["off", "auto", "on"])
    recall_parser.add_argument("--semantic-gate-mode", choices=["off", "auto", "on"])
    recall_parser.add_argument("--run-semantic-gate", action="store_true")
    recall_parser.add_argument("--semantic-timeout", type=int, default=12)
    apw_fallback.add_cli_arguments(recall_parser)
    recall_parser.add_argument("--last-recall-path")
    recall_parser.add_argument(
        "--public",
        "--compact-json",
        action="store_true",
        dest="public_json",
        help="Compatibility alias for the default compact JSON foreground surface.",
    )
    recall_parser.add_argument(
        "--detail",
        choices=["compact", "full"],
        default="compact",
        help="Use full only for local diagnostics that may include private reopen handles.",
    )
    recall_parser.add_argument("--json", action="store_true")

    task_orientation.add_agent_subparser(sub)

    aippo_parser = sub.add_parser(
        "aippo",
        description=(
            "AIppo guidance card:\n"
            "  Use when a project/workflow task might already have a low-risk working contract.\n"
            "  Default JSON is a compact foreground card, not the operator audit envelope.\n"
            "  Use guidance for planning/review/patch shape only; reopen source before claims.\n"
            "  If no contract matches, run agent recall instead of treating silence as failure."
        ),
        epilog=(
            "Examples:\n"
            "  aippocampus agent aippo --task \"fix hook install UX\" --json\n"
            "  aippocampus agent aippo \"semantic gate MCP health\" --json\n"
            "  aippocampus agent aippo <task> --json --operator-json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    aippo_parser.add_argument("task", nargs="*")
    aippo_parser.add_argument("--task", dest="task_flag")
    aippo_parser.add_argument(
        "--public",
        action="store_true",
        help="Compatibility no-op: AIppo activation output is already public-safe.",
    )
    aippo_parser.add_argument("--json", action="store_true")
    aippo_parser.add_argument(
        "--operator-json",
        action="store_true",
        help="Emit the full activation envelope for local diagnostics.",
    )
    background_parser = sub.add_parser(
        "background",
        usage='aippocampus agent background "task cue" --json [options]',
        description=(
            "Reviewed background findings card:\n"
            "  Surfaces already reviewed/source-linked Dream or subconscious working-memory rows.\n"
            "  Findings are navigation only; reopen source before claims; no jobs or raw paths."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    background_parser.add_argument("cue", nargs="*")
    background_parser.add_argument("--task", dest="task_flag")
    background_parser.add_argument("--registry-dir")
    background_parser.add_argument("--working-memory")
    background_parser.add_argument("--project", default="AIppocampus")
    background_parser.add_argument("--max", type=_route_limit_arg, default=4)
    background_parser.add_argument("--detail", choices=["compact", "detail", "full", "operator"], default="compact")
    background_parser.add_argument("--operator-json", action="store_true")
    background_parser.add_argument("--json", action="store_true")
    macro_parser = sub.add_parser(
        "macro",
        description=(
            "Macro-orientation navigation card:\n"
            "  Use when project motion, layer, or phase may change which source route to open first.\n"
            "  Do not use macro as source truth, proof, or a replacement for agent recall/deepen.\n"
            "  For exact wording, disputed facts, public claims, or release notes, run recall/deepen.\n"
            "  Schema/template commands are advanced operator setup for the navigation prior."
        ),
        epilog=(
            "Examples:\n"
            "  aippocampus agent macro --project AIppocampus\n"
            "  aippocampus agent recall \"old cue\" --json\n"
            "  aippocampus agent macro --explain-schema\n"
            "  aippocampus agent macro --init-template --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    macro_parser.add_argument("cue", nargs="*")
    macro_parser.add_argument("--project", default="AIppocampus")
    macro_parser.add_argument("--cwd")
    macro_parser.add_argument("--macro-state-jsonl")
    macro_parser.add_argument("--init-template", action="store_true")
    macro_parser.add_argument("--explain-schema", action="store_true")
    macro_parser.add_argument("--detail", choices=["compact", "full"], default="compact")
    macro_parser.add_argument("--operator-json", action="store_true", help="Emit full macro-orientation audit ledgers.")
    macro_parser.add_argument("--json", action="store_true")

    deepen_parser = sub.add_parser(
        "deepen",
        usage=(
            "aippocampus agent deepen --request 1 "
            "--recall-selector <emitted-selector> --json [options]"
        ),
        description=(
            "Agent deepen task card:\n"
            "  Ordinary path: run recall, then reopen a numbered request with the emitted recall_selector.\n"
            "  Copy-paste: aippocampus agent deepen --request 1 --recall-selector <emitted-selector> --json\n"
            "  Fallback: --last-recall reads a mutable same-machine cache; use only for compatibility.\n"
            "  Raw handles are local/private diagnostics; do not paste them into public output.\n"
            "  If the selector/cache is missing or stale, rerun agent recall or pass an explicit handle locally.\n"
            "  Deepen opens source windows; use it before exact wording, disputed, or high-risk claims."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    deepen_parser.add_argument("handle", nargs="?")
    deepen_parser.add_argument("--handle", dest="handle_option")
    deepen_parser.add_argument("--request", type=int)
    deepen_parser.add_argument("--last-recall", action="store_true")
    deepen_parser.add_argument("--last-recall-path")
    deepen_parser.add_argument(
        "--recall-selector",
        help="Opaque local selector id from compact agent recall output.",
    )
    deepen_parser.add_argument("--cwd")
    deepen_parser.add_argument("--clean-source-dir")
    deepen_parser.add_argument("--registry-dir")
    deepen_parser.add_argument("--macro-state-jsonl")
    deepen_parser.add_argument("--project", default="AIppocampus")
    deepen_parser.add_argument("--max", type=_route_limit_arg, default=MAX_ROUTES)
    deepen_parser.add_argument(
        "--detail", choices=["compact", "full"], default="compact",
        help="Use full only for local diagnostics that include source-window messages.",
    )
    deepen_parser.add_argument("--json", action="store_true")

    explain_parser = sub.add_parser(
        "explain",
        usage=(
            "aippocampus agent explain --request 1 "
            "--recall-selector <emitted-selector> --json [options]"
        ),
        description=(
            "Agent explain task card:\n"
            "  Ordinary path: explain a numbered route with the emitted recall_selector.\n"
            "  Copy-paste: aippocampus agent explain --request 1 --recall-selector <emitted-selector> --json\n"
            "  Fallback: --last-recall reads a mutable same-machine cache; use only for compatibility.\n"
            "  Raw handles remain local/private diagnostics; prefer request numbers in foreground output.\n"
            "  Explanation is routing context, not source evidence."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    explain_parser.add_argument("handle", nargs="?")
    explain_parser.add_argument("--handle", dest="handle_option")
    explain_parser.add_argument("--request", type=int)
    explain_parser.add_argument("--last-recall", action="store_true")
    explain_parser.add_argument("--last-recall-path")
    explain_parser.add_argument(
        "--recall-selector",
        help="Opaque local selector id from compact agent recall output.",
    )
    explain_parser.add_argument("--macro-state-jsonl")
    explain_parser.add_argument("--project", default="AIppocampus")
    explain_parser.add_argument("--detail", choices=["compact", "full"], default="compact")
    explain_parser.add_argument("--json", action="store_true")

    feedback_parser = sub.add_parser(
        "feedback",
        description=(
            "Record whether a recall/deepen route helped. By default this writes durable "
            "low-authority route calibration to a scoped local lane; --feedback-jsonl can "
            "override the lane explicitly. Feedback is never source truth."
        ),
        epilog=(
            "Default durable example:\n"
            "  aippocampus agent feedback <route_id> --outcome helped --json\n\n"
            "Explicit lane examples:\n"
            "  aippocampus agent feedback <route_id> --outcome helped --feedback-jsonl <local-feedback.jsonl> --json\n"
            "  aippocampus agent feedback <route_id> --outcome wrong --reason wrong-project --feedback-jsonl <local-feedback.jsonl> --json\n\n"
            "Use `aippocampus do-not-use-here <route_id> --json` "
            "when the user wants an explicit quieting control."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    feedback_parser.add_argument("route_id", nargs="?")
    feedback_parser.add_argument(
        "--outcome",
        default="candidate_delivered",
        help=(
            "What happened in plain words first: helped/useful, wrong/noisy, stale, "
            "prevented. Stored outcome values: "
            + ", ".join(sorted(feedback_events.ACTIVE_FLOW_SIGNALS))
            + "; aliases include helped=source_reopen_success, wrong=wrong_route_drag, "
            "stale=expired."
        ),
    )
    feedback_parser.add_argument(
        "--route-kind",
        default="active_path",
        help="Route kind: " + ", ".join(sorted(feedback_events.ROUTE_KINDS)) + ".",
    )
    feedback_parser.add_argument("--reason", default="")
    feedback_parser.add_argument("--feedback-jsonl")
    feedback_parser.add_argument("--cwd")
    feedback_parser.add_argument("--registry-dir")
    feedback_parser.add_argument("--json", action="store_true")
    feedback_parser.add_argument(
        "--operator-json",
        action="store_true",
        help="Emit full feedback report diagnostics instead of the compact receipt.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """aippocampus-stage-map: parse args -> dispatch command -> render compact/detail output."""

    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "recall":
        query = args.query_flag or " ".join(args.query)
        if not str(query or "").strip():
            payload = agent_recall_missing_query_payload(
                schema_version=SCHEMA_VERSION,
                kind=KIND,
            )
            if args.json:
                _json_out(payload)
            else:
                actions = [
                    action
                    for action in payload.get("safe_next_actions") or []
                    if isinstance(action, Mapping)
                ]
                lines = ["AIppocampus agent recall: cue required"]
                if actions:
                    lines.append(f"Try: {action_command_text(actions[0])}")
                if len(actions) > 1:
                    lines.append(f"Then: {action_command_text(actions[1])}")
                lines.append("Boundary: recovery guidance is not source evidence.")
                emit_public_text("\n".join(lines), stream=sys.stderr)
            return 2
        payload = recall(
            query,
            cwd=args.cwd,
            clean_source_dir=args.clean_source_dir,
            registry_dir=args.registry_dir,
            macro_state_path=args.macro_state_jsonl,
            project=args.project,
            max_routes=args.max,
            attention_router=args.attention_router_mode or args.attention_router,
            run_semantic_gate=args.run_semantic_gate,
            semantic_gate_mode=args.semantic or args.semantic_gate_mode or "off",
            semantic_timeout=args.semantic_timeout,
            feedback_path=feedback_lane_resolution(
                args.feedback_jsonl,
                cwd=args.cwd,
                registry_dir=args.registry_dir,
            )["path"],
            opened_route_keys=opened_route_keys_from_last_recall_cache(args.last_recall_path),
            **apw_fallback.cli_kwargs(args),
        )
        cache_written = write_last_recall_cache(
            payload.get("deepen_requests") or [],
            query=query,
            cwd=args.cwd,
            clean_source_dir=args.clean_source_dir,
            registry_dir=args.registry_dir,
            macro_state_path=args.macro_state_jsonl,
            project=args.project,
            max_matches=args.max,
            schema_version=SCHEMA_VERSION,
            path=args.last_recall_path,
        )
        selector_id = write_recall_selector_snapshot(args.last_recall_path) if cache_written else None
        if selector_id:
            agent_deepen_requests.attach_recall_selector_to_payload(payload, selector_id)
        payload = {
            **payload,
            "last_recall_cache_available": cache_written,
            "recall_selector_available": bool(selector_id),
            "recall_selector_id": selector_id,
        }
        if args.json:
            if args.public_json or args.detail != "full":
                payload = public_recall_projection(payload, query=query)
            else:
                payload = {
                    "detail": "full",
                    "output_boundary": "local_private_diagnostic_full",
                    "foreground_guidance": (
                        "Use --detail full only for local diagnostics; foreground agents should "
                        "prefer compact JSON or the human request-index action."
                    ),
                    **payload,
                }
            _json_out(payload)
        else:
            print(render_recall_human(payload))
        # A recall miss is still a successful orientation report: it carries
        # recovery actions and attention diagnostics. Hard source/read errors
        # continue through the shared exit-code helper below.
        if payload.get("mode") == "recall" and payload.get("status") in {"ok", "no_routes"}:
            return 0
        return exit_code_for_payload(payload)
    if args.command == "orient":
        return task_orientation.run_agent_command(args, _json_out)
    if args.command == "aippo":
        task = args.task_flag or " ".join(args.task)
        payload = activate_aippo(task=task)
        if args.json:
            guidance_card = compact_aippo_guidance_card(payload, task=task)
            if args.operator_json:
                payload = _operator_aippo_payload_with_foreground_card(
                    payload,
                    guidance_card,
                    task=task,
                )
            else:
                payload = guidance_card
            _json_out(payload)
        else:
            print(render_aippo_human(payload))
        return 2 if payload.get("status") == "needs_input" else 0
    if args.command == "background":
        cue = args.task_flag or " ".join(args.cue)
        payload = background_findings.background_findings_card(
            cue,
            registry_dir=args.registry_dir,
            working_memory_path=args.working_memory,
            project=args.project,
            limit=args.max,
            detail="operator" if args.operator_json else args.detail,
        )
        if args.json:
            _json_out(payload)
        else:
            print("AIppocampus agent background: " + str(payload.get("status") or "unknown") + "\nfindings: " + str(payload.get("finding_count") or 0))
            action = payload.get("foreground_action")
            if isinstance(action, Mapping):
                print("next: " + str(action.get("command") or action.get("command_template") or action.get("id")))
            print("boundary: background findings are navigation only until source is reopened.")
        return 2 if payload.get("status") == "needs_input" else 0
    if args.command == "macro":
        macro_cue = " ".join(args.cue).strip()
        if macro_cue and not args.init_template and not args.explain_schema:
            payload = _macro_positional_cue_payload(macro_cue, project=args.project)
            if args.json:
                _json_out(payload)
            else:
                print(_render_macro_recovery_text(payload))
            return 2
        if args.init_template:
            payload = macro_state_template(args.project)
            if args.json:
                _json_out(payload)
            else:
                print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            return 0
        if args.explain_schema:
            payload = macro_schema_help(
                args.project,
                schema_version=MACRO_PACKET_SCHEMA_VERSION,
            )
            if args.json:
                _json_out(payload)
            else:
                print(render_macro_schema_human(payload))
            return 0
        payload = macro_orientation(
            project=args.project,
            macro_state_path=args.macro_state_jsonl,
            cwd=args.cwd,
            detail="full" if args.operator_json else args.detail,
        )
        if args.json:
            _json_out(payload)
        else:
            print(render_macro_human(payload))
        return 0
    if args.command == "deepen":
        handle = args.handle_option or args.handle
        cached_context: dict[str, Any] = {}
        has_request_selector = bool(args.recall_selector or args.last_recall or args.request is not None)
        selector_cache_path: str | Path | None = args.last_recall_path
        if has_request_selector:
            try:
                if args.recall_selector:
                    selector_last_exc: Exception | None = None
                    for candidate in recall_selector_cache_candidates(
                        args.recall_selector,
                        last_recall_path_value=args.last_recall_path,
                    ):
                        try:
                            handle, cached_context = handle_from_last_recall_cache(
                                request_index=int(args.request or 1),
                                path=candidate,
                            )
                            selector_cache_path = candidate
                            break
                        except (OSError, ValueError, json.JSONDecodeError) as exc:
                            selector_last_exc = exc
                    if handle is None and selector_last_exc is not None:
                        raise selector_last_exc
                else:
                    handle, cached_context = handle_from_last_recall_cache(
                        request_index=int(args.request or 1),
                        path=selector_cache_path,
                    )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                payload = last_recall_unavailable_payload(
                    mode="deepen",
                    exc=exc,
                    schema_version=SCHEMA_VERSION,
                    kind=KIND,
                    cue=query_from_last_recall_cache(selector_cache_path),
                )
                if args.json:
                    _json_out(payload)
                else:
                    print(render_deepen_human(payload))
                return 2
        payload = deepen(
            handle,
            cwd=args.cwd or cached_context.get("cwd"),
            clean_source_dir=args.clean_source_dir or cached_context.get("clean_source_dir"),
            registry_dir=args.registry_dir or cached_context.get("registry_dir"),
            macro_state_path=args.macro_state_jsonl or cached_context.get("macro_state_jsonl"),
            project=args.project or cached_context.get("project") or "AIppocampus",
            max_matches=args.max,
        )
        apw_identity = cached_context.get("apw_route_identity")
        if isinstance(apw_identity, Mapping):
            payload["apw_route_identity"] = dict(apw_identity)
            result = payload.get("result")
            if isinstance(result, dict):
                result["apw_route_identity"] = dict(apw_identity)
        attach_recall_gate_context_to_payload(payload, cached_context)
        request_index = int(args.request or 1) if has_request_selector else None
        if request_index is not None and payload.get("status") == "cannot_verify":
            recovery_cue = (
                str(cached_context.get("query") or "").strip()
                or query_from_last_recall_cache(selector_cache_path)
            )
            payload.update(
                last_recall_selector_recovery_fields(
                    "deepen",
                    request_index=request_index,
                    cue=recovery_cue,
                )
            )
            payload.pop("policy_boundary", None)
            payload.pop("cannot_claim", None)
        if request_index is not None and payload.get("status") == "ok":
            try:
                mark_last_recall_request_opened(
                    request_index,
                    path=selector_cache_path,
                    outcome="source_open",
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                payload.setdefault("detail_warnings", []).append(
                    {
                        "code": "last_recall_opened_marker_unavailable",
                        "error_code": type(exc).__name__,
                        "recovery": "source_open_succeeded_marker_not_written",
                        "claim_boundary": "detail_only_cache_diagnostic",
                    }
                )
        if args.json:
            if args.detail == "full":
                payload = {"detail": "full", "output_boundary": "local_private_diagnostic_full", **payload}
            else:
                payload = compact_agent_deepen_payload(
                    payload,
                    request_index=request_index,
                    last_recall=request_index is not None,
                    recall_selector=str(args.recall_selector or ""),
                    surface="agent_cli_source_court_compact",
                )
            _json_out(payload)
        else:
            print(render_deepen_human(payload))
        return 2 if payload.get("status") == "cannot_verify" or payload.get("ok") is False else 0
    if args.command == "explain":
        handle = args.handle_option or args.handle
        explain_cached_context: dict[str, Any] = {}
        has_request_selector = bool(args.recall_selector or args.last_recall or args.request is not None)
        selector_cache_path = args.last_recall_path
        if has_request_selector:
            try:
                if args.recall_selector:
                    explain_selector_last_exc: Exception | None = None
                    for candidate in recall_selector_cache_candidates(
                        args.recall_selector,
                        last_recall_path_value=args.last_recall_path,
                    ):
                        try:
                            handle, explain_cached_context = handle_from_last_recall_cache(
                                request_index=int(args.request or 1),
                                path=candidate,
                            )
                            selector_cache_path = candidate
                            break
                        except (OSError, ValueError, json.JSONDecodeError) as exc:
                            explain_selector_last_exc = exc
                    if handle is None and explain_selector_last_exc is not None:
                        raise explain_selector_last_exc
                else:
                    handle, explain_cached_context = handle_from_last_recall_cache(
                        request_index=int(args.request or 1),
                        path=selector_cache_path,
                    )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                payload = last_recall_unavailable_payload(
                    mode="explain",
                    exc=exc,
                    schema_version=SCHEMA_VERSION,
                    kind=KIND,
                    cue=query_from_last_recall_cache(selector_cache_path),
                )
                if args.json:
                    _json_out(project_agent_explain_cli_payload(payload, args, surface="agent_cli_route_explain_compact"))
                else:
                    projected = project_agent_explain_cli_payload(
                        payload,
                        args,
                        surface="agent_cli_route_explain_compact",
                    )
                    raw_error = projected.get("error")
                    error_map: Mapping[str, Any] = raw_error if isinstance(raw_error, Mapping) else {}
                    raw_action = projected.get("foreground_action")
                    foreground_action: Mapping[str, Any] = (
                        raw_action if isinstance(raw_action, Mapping) else {}
                    )
                    print("AIppocampus agent explain: cannot verify last recall cache")
                    print("Reason: " + str(error_map.get("code") or "last_recall_unavailable"))
                    next_template = foreground_action.get("command_template") or foreground_action.get("cli_command_template")
                    next_command = foreground_action.get("command") or foreground_action.get("cli_command")
                    if next_template:
                        print("Next: " + str(next_template))
                    elif next_command:
                        print("Next: " + str(next_command))
                    else:
                        print('Next: rerun `aippocampus agent recall "<cue>" --json`, then explain a request number.')
                return 2
        payload = explain(
            handle,
            macro_state_path=args.macro_state_jsonl or explain_cached_context.get("macro_state_jsonl"),
            project=args.project or explain_cached_context.get("project") or "AIppocampus",
        )
        if args.json:
            _json_out(project_agent_explain_cli_payload(payload, args, surface="agent_cli_route_explain_compact"))
        else:
            status = str(payload.get("status") or "unknown")
            explanation = payload.get("explanation")
            data = explanation if isinstance(explanation, Mapping) else {}
            raw_error = data.get("error")
            error = raw_error if isinstance(raw_error, Mapping) else {}
            if status == "cannot_verify":
                print("AIppocampus agent explain: cannot verify handle")
                print("Reason: " + str(error.get("code") or "malformed recall handle"))
                print(
                    "Use: run `aippocampus agent recall --json --detail full ...` and pass "
                    "`deepen_requests[].handle`, or use the emitted "
                    "`agent deepen --request N --recall-selector ...` command."
                )
            else:
                print("AIppocampus agent explain: ok")
                print("next_safe_action: " + str(data.get("next_safe_action") or "reopen_source"))
        return 2 if payload.get("status") == "cannot_verify" or payload.get("ok") is False else 0
    if args.command == "feedback":
        if not args.route_id:
            payload = missing_feedback_route_payload(
                schema_version=SCHEMA_VERSION,
                kind=KIND,
            )
            if args.json:
                _json_out(payload)
            else:
                print("AIppocampus agent feedback: route_id required")
                next_action = payload.get("foreground_action")
                command = (
                    next_action.get("command")
                    or next_action.get("command_template")
                    or next_action.get("id")
                    if isinstance(next_action, Mapping)
                    else next_action
                )
                print("Next: " + str(command))
            return 2
        try:
            lane = feedback_lane_resolution(
                args.feedback_jsonl,
                cwd=args.cwd,
                registry_dir=args.registry_dir,
            )
            payload = capture_feedback(
                route_id=args.route_id,
                outcome=args.outcome,
                route_kind=args.route_kind,
                reason=args.reason,
                feedback_path=lane["path"],
                feedback_lane=lane,
                schema_version=SCHEMA_VERSION,
                kind=KIND,
            )
        except feedback_events.InvalidFeedbackValue as exc:
            payload = _public_payload(
                {
                    "kind": KIND,
                    "schema_version": SCHEMA_VERSION,
                    "mode": "feedback",
                    "status": "rejected",
                    "ok": False,
                    "error": {
                        "code": "invalid_feedback_value",
                        "field": exc.field,
                        "value": exc.value,
                        "valid_values": sorted(exc.accepted),
                        "aliases": dict(
                            sorted((exc.aliases or feedback_events.OUTCOME_ALIASES).items())
                        ),
                    },
                }
            )
            _json_out(payload)
            return 2
        if args.json or args.operator_json:
            _json_out(
                payload
                if args.operator_json
                else compact_feedback_receipt(payload, schema_version=SCHEMA_VERSION, kind=KIND)
            )
        else:
            compact = compact_feedback_receipt(
                payload,
                schema_version=SCHEMA_VERSION,
                kind=KIND,
            )
            print("AIppocampus agent feedback: captured")
            print("storage: " + str(compact["write_boundary"]["storage"]))
            print("next: " + str(compact["foreground_action"]))
        return 0
    return 2
