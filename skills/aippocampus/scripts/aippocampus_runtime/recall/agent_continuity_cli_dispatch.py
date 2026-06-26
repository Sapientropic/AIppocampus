"""Parsed-command handlers for the agent-continuity CLI.

The parser module owns the public argparse contract. This module owns execution
stages so recovery branches do not keep accreting inside one giant `main`.
"""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.cli.human_io import exit_code_for_payload
from aippocampus_runtime.cli.recovery import action_command_text
from aippocampus_runtime.mcp.agent_deepen_projection import compact_agent_deepen_payload
from aippocampus_runtime.mcp.agent_explain_projection import project_agent_explain_cli_payload
from aippocampus_runtime.public_output import emit_public_text
from aippocampus_runtime.recall import (
    agent_deepen_requests,
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

JsonOut = Callable[[Mapping[str, Any]], None]


def _run_recall_command(args: Namespace, json_out: JsonOut) -> int:
    query = args.query_flag or " ".join(args.query)
    if not str(query or "").strip():
        payload = agent_recall_missing_query_payload(
            schema_version=SCHEMA_VERSION,
            kind=KIND,
        )
        if args.json:
            json_out(payload)
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
        json_out(payload)
    else:
        print(render_recall_human(payload))
    # A recall miss is still a successful orientation report: it carries
    # recovery actions and attention diagnostics. Hard source/read errors
    # continue through the shared exit-code helper below.
    if payload.get("mode") == "recall" and payload.get("status") in {"ok", "no_routes"}:
        return 0
    return exit_code_for_payload(payload)


def _run_aippo_command(args: Namespace, json_out: JsonOut) -> int:
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
        json_out(payload)
    else:
        print(render_aippo_human(payload))
    return 2 if payload.get("status") == "needs_input" else 0


def _run_background_command(args: Namespace, json_out: JsonOut) -> int:
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
        json_out(payload)
    else:
        print(
            "AIppocampus agent background: "
            + str(payload.get("status") or "unknown")
            + "\nfindings: "
            + str(payload.get("finding_count") or 0)
        )
        action = payload.get("foreground_action")
        if isinstance(action, Mapping):
            print(
                "next: "
                + str(action.get("command") or action.get("command_template") or action.get("id"))
            )
        print("boundary: background findings are navigation only until source is reopened.")
    return 2 if payload.get("status") == "needs_input" else 0


def _run_macro_command(args: Namespace, json_out: JsonOut) -> int:
    macro_cue = " ".join(args.cue).strip()
    if macro_cue and not args.init_template and not args.explain_schema:
        payload = _macro_positional_cue_payload(macro_cue, project=args.project)
        if args.json:
            json_out(payload)
        else:
            print(_render_macro_recovery_text(payload))
        return 2
    if args.init_template:
        payload = macro_state_template(args.project)
        if args.json:
            json_out(payload)
        else:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    if args.explain_schema:
        payload = macro_schema_help(
            args.project,
            schema_version=MACRO_PACKET_SCHEMA_VERSION,
        )
        if args.json:
            json_out(payload)
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
        json_out(payload)
    else:
        print(render_macro_human(payload))
    return 0


def _load_request_handle(args: Namespace, mode: str) -> tuple[Any, dict[str, Any], str | Path | None, int | None, dict[str, Any] | None]:
    handle = args.handle_option or args.handle
    cached_context: dict[str, Any] = {}
    has_request_selector = bool(args.recall_selector or args.last_recall or args.request is not None)
    selector_cache_path: str | Path | None = args.last_recall_path
    request_index = int(args.request or 1) if has_request_selector else None
    if not has_request_selector:
        return handle, cached_context, selector_cache_path, request_index, None
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
        recovery = last_recall_unavailable_payload(
            mode=mode,
            exc=exc,
            schema_version=SCHEMA_VERSION,
            kind=KIND,
            cue=query_from_last_recall_cache(selector_cache_path),
        )
        return handle, cached_context, selector_cache_path, request_index, recovery
    return handle, cached_context, selector_cache_path, request_index, None


def _run_deepen_command(args: Namespace, json_out: JsonOut) -> int:
    handle, cached_context, selector_cache_path, request_index, recovery_payload = (
        _load_request_handle(args, "deepen")
    )
    if recovery_payload is not None:
        if args.json:
            if args.detail == "full":
                recovery_payload = {
                    "detail": "full",
                    "output_boundary": "local_private_diagnostic_full",
                    **recovery_payload,
                }
            else:
                recovery_payload = compact_agent_deepen_payload(
                    recovery_payload,
                    request_index=int(args.request or 1),
                    last_recall=True,
                    recall_selector=str(args.recall_selector or ""),
                    surface="agent_cli_source_court_compact",
                )
            json_out(recovery_payload)
        else:
            print(render_deepen_human(recovery_payload))
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
        json_out(payload)
    else:
        print(render_deepen_human(payload))
    return 2 if payload.get("status") == "cannot_verify" or payload.get("ok") is False else 0


def _render_explain_cache_recovery_text(projected: Mapping[str, Any]) -> None:
    raw_error = projected.get("error")
    error_map: Mapping[str, Any] = raw_error if isinstance(raw_error, Mapping) else {}
    raw_action = projected.get("foreground_action")
    foreground_action: Mapping[str, Any] = raw_action if isinstance(raw_action, Mapping) else {}
    print("AIppocampus agent explain: cannot verify last recall cache")
    print("Reason: " + str(error_map.get("code") or "last_recall_unavailable"))
    next_template = foreground_action.get("command_template") or foreground_action.get(
        "cli_command_template"
    )
    next_command = foreground_action.get("command") or foreground_action.get("cli_command")
    if next_template:
        print("Next: " + str(next_template))
    elif next_command:
        print("Next: " + str(next_command))
    else:
        print('Next: rerun `aippocampus agent recall "<cue>" --json`, then explain a request number.')


def _run_explain_command(args: Namespace, json_out: JsonOut) -> int:
    handle, cached_context, _selector_cache_path, _request_index, recovery_payload = (
        _load_request_handle(args, "explain")
    )
    if recovery_payload is not None:
        projected = project_agent_explain_cli_payload(
            recovery_payload,
            args,
            surface="agent_cli_route_explain_compact",
        )
        if args.json:
            json_out(projected)
        else:
            _render_explain_cache_recovery_text(projected)
        return 2
    payload = explain(
        handle,
        macro_state_path=args.macro_state_jsonl or cached_context.get("macro_state_jsonl"),
        project=args.project or cached_context.get("project") or "AIppocampus",
    )
    if args.json:
        json_out(project_agent_explain_cli_payload(payload, args, surface="agent_cli_route_explain_compact"))
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


def _run_feedback_command(args: Namespace, json_out: JsonOut) -> int:
    if not args.route_id:
        payload = missing_feedback_route_payload(
            schema_version=SCHEMA_VERSION,
            kind=KIND,
        )
        if args.json:
            json_out(payload)
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
        json_out(payload)
        return 2
    if args.json or args.operator_json:
        json_out(
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


def dispatch_agent_command(args: Namespace, json_out: JsonOut) -> int:
    """Dispatch an already parsed `aippocampus agent` command."""

    if args.command == "recall":
        return _run_recall_command(args, json_out)
    if args.command == "orient":
        return task_orientation.run_agent_command(args, json_out)
    if args.command == "aippo":
        return _run_aippo_command(args, json_out)
    if args.command == "background":
        return _run_background_command(args, json_out)
    if args.command == "macro":
        return _run_macro_command(args, json_out)
    if args.command == "deepen":
        return _run_deepen_command(args, json_out)
    if args.command == "explain":
        return _run_explain_command(args, json_out)
    if args.command == "feedback":
        return _run_feedback_command(args, json_out)
    return 2


__all__ = ["dispatch_agent_command"]
