"""CLI parser and command dispatch for the agent-continuity facade."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.recall import (
    associative_path_fallback as apw_fallback,
)
from aippocampus_runtime.recall import (
    attention_router_policy,
    task_orientation,
)
from aippocampus_runtime.recall.agent_continuity import (
    MAX_ROUTES,
)
from aippocampus_runtime.recall.agent_continuity_cli_support import (
    normalize_route_limit,
)
from aippocampus_runtime.recall.feedback import events as feedback_events


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
    """Parse the CLI contract, then delegate execution to staged handlers."""

    parser = _parser()
    args = parser.parse_args(argv)
    from aippocampus_runtime.recall.agent_continuity_cli_dispatch import (
        dispatch_agent_command,
    )

    return dispatch_agent_command(args, _json_out)
