#!/usr/bin/env python3
"""Human-facing progressive recall funnel smoke.

This command is intentionally diagnostic-only. It runs the same MCP call path a
client would use (`recall_context` followed by `recall_deepen`) and the ordinary
agent path (`agent recall` followed by selector-backed `agent deepen`), then
reports counts, gate status, and boundary status without echoing the cue or
source text.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
)
from aippocampus_runtime.mcp import tool_handlers as mcp_tools
from aippocampus_runtime.mcp.compact_profile import mcp_tool_result_payload
from aippocampus_runtime.mcp.recall_navigation import NAVIGATION_SCHEMA_VERSION
from aippocampus_runtime.ops.recall_funnel_live_agent_gate import (
    build_live_agent_usefulness_gate,
)

SCHEMA_VERSION = 1


def cue_required_recovery_card() -> dict[str, Any]:
    primary = {
        "id": "run_smoke_recall_funnel",
        "label": "Run recall funnel smoke diagnostic",
        "command_template": 'aippocampus smoke recall-funnel "{cue}" --json',
        "requires": ["cue"],
        "template_only": True,
        "mutation_risk": "read_only",
        "claim_boundary": "smoke_diagnostic_not_source_evidence",
    }
    ordinary = {
        "id": "ordinary_agent_recall",
        "label": "Use ordinary continuity recall",
        "command_template": 'aippocampus agent recall "{cue}" --json',
        "requires": ["cue"],
        "template_only": True,
        "mutation_risk": "read_only",
        "claim_boundary": "no_claim_before_reopen",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_recall_funnel_smoke_recovery",
        "ok": False,
        "status": "needs_cue",
        "cue_required": True,
        "error": {
            "code": "cue_required",
            "message": "Provide a cue before running the recall funnel smoke diagnostic.",
        },
        **canonical_foreground_action_fields(primary, safe_next_actions=[ordinary]),
        "source_boundary": {
            "claim_boundary": "smoke output is diagnostic, not source evidence",
            "source_backed_claim_allowed": False,
            "source_reopen_required_before_claims": True,
        },
    }


def _tool_payload(result: dict[str, Any]) -> dict[str, Any]:
    return mcp_tool_result_payload(result)


def _field_names(payload: dict[str, Any], names: list[str]) -> list[str]:
    return [name for name in names if name in payload]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _recall_args(
    *,
    cue: str,
    cwd: str | Path,
    clean_source_dir: str | Path | None,
    registry_dir: str | Path | None,
    max_routes: int,
    include_private_paths: bool,
) -> dict[str, Any]:
    args: dict[str, Any] = {
        "intent": cue,
        "cwd": str(cwd),
        "max": max_routes,
        "detail": "full",
        "include_private_paths": include_private_paths,
    }
    if clean_source_dir is not None:
        args["clean_source_dir"] = str(clean_source_dir)
    if registry_dir is not None:
        args["registry_dir"] = str(registry_dir)
    return args


def _safe_error(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    if not result.get("isError") and not payload.get("error"):
        return None
    error = _as_dict(payload.get("error"))
    return {
        "code": error.get("code") or "tool_error",
        "message": error.get("message") or "MCP tool returned an error.",
    }


def _is_recall_deepen_route(route: dict[str, Any]) -> bool:
    suggested_next = route.get("suggested_next")
    suggested_tool = suggested_next.get("tool") if isinstance(suggested_next, dict) else None
    # Registry fallback routes also carry handle-shaped metadata, but their
    # public next step is search_memory. Passing those to recall_deepen would
    # hide the real boundary behind a misleading malformed-handle diagnostic.
    return bool(route.get("handle") and route.get("reopenable") and suggested_tool == "recall_deepen")


def _select_route(routes: list[Any]) -> tuple[int | None, dict[str, Any] | None]:
    for index, route in enumerate(routes):
        if isinstance(route, dict) and _is_recall_deepen_route(route):
            return index, route
    return None, None


def build_recall_funnel_smoke(
    cue: str,
    *,
    cwd: str | Path | None = None,
    clean_source_dir: str | Path | None = None,
    registry_dir: str | Path | None = None,
    max_routes: int = 5,
    max_deepen_matches: int = 5,
    include_private_paths: bool = False,
) -> dict[str, Any]:
    cwd_path = Path(cwd or os.getcwd()).resolve()
    context_args = _recall_args(
        cue=cue,
        cwd=cwd_path,
        clean_source_dir=clean_source_dir,
        registry_dir=registry_dir,
        max_routes=max_routes,
        include_private_paths=include_private_paths,
    )
    context_result = mcp_tools.call_recall_context(context_args)
    context_payload = _tool_payload(context_result)
    context_error = _safe_error(context_result, context_payload)
    routes = _as_list(context_payload.get("routes"))
    selected_index, selected_route = _select_route(routes)

    deepen_payload: dict[str, Any] = {}
    deepen_error: dict[str, Any] | None = None
    if context_error is None and selected_route is not None:
        deepen_args = {
            "handle": selected_route.get("handle"),
            "cwd": str(cwd_path),
            "max": max_deepen_matches,
            "include_private_paths": include_private_paths,
        }
        if clean_source_dir is not None:
            deepen_args["clean_source_dir"] = str(clean_source_dir)
        if registry_dir is not None:
            deepen_args["registry_dir"] = str(registry_dir)
        deepen_result = mcp_tools.call_recall_deepen(deepen_args)
        deepen_payload = _tool_payload(deepen_result)
        deepen_error = _safe_error(deepen_result, deepen_payload)
    elif context_error is None:
        deepen_error = {
            "code": "no_recall_deepen_route",
            "message": "recall_context returned no reopenable route handle for recall_deepen.",
        }

    source_window = _as_dict(deepen_payload.get("source_window"))
    source_refs = _as_list(deepen_payload.get("source_refs"))
    metrics = _as_dict(deepen_payload.get("metrics"))
    context_metrics = _as_dict(context_payload.get("metrics"))
    selected_suggested_next = _as_dict(selected_route.get("suggested_next")) if selected_route else {}
    wrong_or_stale = bool(
        metrics.get("wrong_or_stale_handle")
        or (deepen_error or {}).get("code") in {"stale_recall_handle", "source_ref_not_found"}
    )
    live_agent_gate = build_live_agent_usefulness_gate(
        cue,
        cwd=cwd_path,
        clean_source_dir=clean_source_dir,
        registry_dir=registry_dir,
        max_routes=max_routes,
        max_deepen_matches=max_deepen_matches,
    )
    ok = context_error is None and deepen_error is None and bool(live_agent_gate.get("ok"))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_recall_funnel_smoke",
        "ok": ok,
        "navigation_schema_version": NAVIGATION_SCHEMA_VERSION,
        "privacy": {
            "raw_cue_echoed": False,
            "source_window_text_included": False,
            "raw_source_refs_included": False,
            "local_paths_included": include_private_paths,
            "uses_mcp_public_redaction": not include_private_paths,
        },
        "context": {
            "status": context_payload.get("status") or ("error" if context_error else "unknown"),
            "is_error": context_error is not None,
            "error": context_error,
            "route_count": int(context_payload.get("route_count") or len(routes)),
            "handle_count": int(
                context_metrics.get("handle_count")
                or len([route for route in routes if isinstance(route, dict) and route.get("handle")])
            ),
            "field_names": _field_names(
                context_payload,
                ["routes", "metrics", "source_boundary", "suggested_next"],
            ),
        },
        "selected_route": {
            "index": selected_index,
            "available": selected_route is not None,
            "kind": selected_route.get("kind") if selected_route else None,
            "reopenable": bool(selected_route.get("reopenable")) if selected_route else False,
            "suggested_next_tool": selected_suggested_next.get("tool"),
            "handle_passed_to_recall_deepen": selected_route is not None,
        },
        "deepen": {
            "status": deepen_payload.get("status") or ("error" if deepen_error else "not_run"),
            "is_error": deepen_error is not None,
            "error": deepen_error,
            "support_level": deepen_payload.get("support_level"),
            "evidence_level": deepen_payload.get("evidence_level"),
            "source_ref_count": len(source_refs),
            "source_window_message_count": int(
                source_window.get("message_count") or len(source_window.get("messages") or [])
            ),
            "field_names": _field_names(
                deepen_payload,
                ["source_window", "source_refs", "metrics", "source_boundary"],
            ),
            "wrong_or_stale_handle": wrong_or_stale,
        },
        "live_agent_usefulness_gate": live_agent_gate,
        "source_boundary": (
            deepen_payload.get("source_boundary")
            if isinstance(deepen_payload.get("source_boundary"), dict)
            else context_payload.get("source_boundary")
            if isinstance(context_payload.get("source_boundary"), dict)
            else {}
        ),
        "notes": [
            "This smoke chooses the first reopenable recall_context route whose next tool is recall_deepen.",
            "It also runs agent recall -> selector-backed agent deepen through a temporary same-machine cache.",
            "Counts and field names are diagnostic only; source-backed claims still require inspecting reopened clean source.",
        ],
    }


def render_text(report: dict[str, Any]) -> str:
    context = report["context"]
    selected = report["selected_route"]
    deepen = report["deepen"]
    live_gate = _as_dict(report.get("live_agent_usefulness_gate"))
    lines = [
        "AIppocampus recall funnel smoke",
        f"- OK: {str(report['ok']).lower()}",
        f"- Context routes: {context['route_count']} (handles {context['handle_count']})",
        f"- Selected route: {selected['kind'] or 'none'}; reopenable {str(selected['reopenable']).lower()}",
        f"- Deepen status: {deepen['status']}; source refs {deepen['source_ref_count']}; source-window messages {deepen['source_window_message_count']}",
        f"- Wrong/stale handle: {str(deepen['wrong_or_stale_handle']).lower()}",
        (
            f"- Live agent usefulness: {live_gate.get('status')}; "
            f"route {_as_dict(live_gate.get('route_existence')).get('status')}, "
            f"specificity {_as_dict(live_gate.get('route_specificity')).get('status')}, "
            f"reopen {_as_dict(live_gate.get('source_reopen')).get('status')}"
        ),
        f"- Evidence fields: {', '.join(deepen['field_names']) or 'none'}",
        "- Privacy: cue not echoed; source text not printed; local paths redacted unless requested",
    ]
    if context["error"]:
        lines.append(f"- Context error: {context['error']['code']}")
    if deepen["error"]:
        lines.append(f"- Deepen error: {deepen['error']['code']}")
    lines.append("")
    return "\n".join(lines)


def render_cue_required_text(card: dict[str, Any]) -> str:
    primary = card["foreground_action"]
    alternatives = card["safe_next_actions"]
    ordinary = alternatives[0] if alternatives else primary
    return "\n".join(
        [
            "AIppocampus recall funnel smoke: cue required.",
            f"next: {primary['command_template']}",
            f"ordinary path: {ordinary['command_template']}",
            "boundary: smoke output is diagnostic, not source evidence.",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aippocampus smoke")
    subparsers = parser.add_subparsers(dest="command", required=True)
    recall_parser = subparsers.add_parser(
        "recall-funnel",
        usage="aippocampus smoke recall-funnel \"cue\" [--json] [options]",
        description=(
            "Recall funnel smoke task card:\n"
            "  No persistent-write diagnostic for progressive recall wiring.\n"
            "  Calls recall_context -> recall_deepen and agent recall -> selector-backed agent deepen.\n"
            "  Cue text, source text, and local/private paths are redacted by default.\n"
            "  Counts and statuses are diagnostics, not source-backed evidence for an answer.\n"
            "  For ordinary continuity work, use agent recall -> agent deepen."
        ),
        epilog=(
            "Try:\n"
            "  aippocampus smoke recall-funnel \"old cue\" --json\n"
            "  aippocampus agent recall \"old cue\" --json\n"
            "  aippocampus agent deepen --request 1 --recall-selector <emitted-selector> --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Run recall_context -> first reopenable recall_deepen route as a diagnostic.",
    )
    recall_parser.add_argument("cue", nargs="?")
    recall_parser.add_argument("--cwd", default=os.getcwd())
    recall_parser.add_argument("--clean-source-dir", default=None)
    recall_parser.add_argument("--registry-dir", default=None)
    recall_parser.add_argument("--max-routes", type=int, default=5)
    recall_parser.add_argument("--max-deepen-matches", type=int, default=5)
    recall_parser.add_argument("--include-private-paths", action="store_true")
    recall_parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    if args.command == "recall-funnel" and not (args.cue or "").strip():
        card = cue_required_recovery_card()
        if args.json_output:
            print(json.dumps(card, ensure_ascii=False, indent=2))
        else:
            print(render_cue_required_text(card))
        return 2

    report = build_recall_funnel_smoke(
        args.cue,
        cwd=args.cwd,
        clean_source_dir=args.clean_source_dir,
        registry_dir=args.registry_dir,
        max_routes=args.max_routes,
        max_deepen_matches=args.max_deepen_matches,
        include_private_paths=args.include_private_paths,
    )
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
