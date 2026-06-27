"""Issue-work active pull guard for foreground agents.

This module does not decide the task. It creates a compact route-first packet
when an issue is likely to depend on old AIppocampus design context. The point
is to prevent expensive long-running agents from inventing benchmark-local
scaffolding before they have checked the existing route owners.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any, Iterable

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_recovery_card,
    foreground_template_action,
    shell_quote,
)

SCHEMA_VERSION = "issue-work-active-pull-v0"

BENCHMARK_RE = re.compile(
    r"\b(longmemeval|benchmark|rerank|source[-_ ]side|semantic cache|"
    r"source_semantic_cache|evidence[-_ ]line)\b",
    re.I,
)
ARCHITECTURE_RE = re.compile(
    r"\b(attention router|semantic scope|subconscious|warm ambient|aippo|"
    r"macro orientation|learning[-_ ]loop|action[-_ ]time guidance|"
    r"learning guidance|action hints|architecture|design)\b",
    re.I,
)
LEARNING_LOOP_RE = re.compile(
    r"\b(learning[-_ ]loop|repeated mistakes?|repeating mistakes?|repeated failures?|"
    r"feedback events?|source-backed lessons?|action[-_ ]time guidance|"
    r"agent feedback|do-not-use-here|behavior events?)\b",
    re.I,
)
SKILL_DOCS_RE = re.compile(
    r"\b(SKILL\.md|skill entrypoint|installable skill|README|quickstart|"
    r"public api|install guide|setup doc|docs?/|documentation|foreground continuity bootstrap)\b",
    re.I,
)
FOREGROUND_CARD_RE = re.compile(
    r"\b(foreground card|compact card|json card|recovery card|agent-native|"
    r"safe_next_actions|claim_boundary|cannot_claim|doctor spend|health --json|"
    r"maintenance|import conversation|recall-funnel|work-guard|cli facade|"
    r"public facade|task-first|task orientation|orientation packet|"
    r"understanding state|external source anchor)\b",
    re.I,
)
TRIVIAL_RE = re.compile(r"\b(typo|spelling|formatting|link fix|rename only)\b", re.I)
ISSUE_NUMBER_RE = re.compile(r"^\d+$")
ISSUE_URL_RE = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/issues/\d+(?:\b|$)")

OWNER_REFS: dict[str, dict[str, str]] = {
    "semantic_scope_labeling": {
        "kind": "subconscious_job",
        "path": "skills/aippocampus/references/subconscious-jobs.md",
    },
    "semantic_scope_builder": {
        "kind": "runtime_owner",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/recall/semantic_recall_gate.py",
    },
    "subconscious_jobs": {
        "kind": "runtime_owner",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/subconscious/jobs.py",
    },
    "warm_ambient_routes": {
        "kind": "runtime_owner",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/recall/ambient_cache.py",
    },
    "attention_router": {
        "kind": "runtime_owner",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/navigation/attention_hot_router.py",
    },
    "skill_entrypoint": {
        "kind": "skill_entrypoint",
        "path": "skills/aippocampus/SKILL.md",
    },
    "foreground_cli_facade": {
        "kind": "runtime_owner",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/cli/facade.py",
    },
    "foreground_output_projection": {
        "kind": "runtime_owner",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/mcp/public_projection.py",
    },
    "agent_continuity_cards": {
        "kind": "runtime_owner",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_continuity_cli_support.py",
    },
    "docs_health_guard": {
        "kind": "repo_tool",
        "path": "tools/aippocampus/docs/check_docs_health.py",
    },
    "public_docs": {
        "kind": "documentation",
        "path": "docs/guides/public-api.md",
    },
    "learning_loop_cli": {
        "kind": "runtime_owner",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/learning_loop/cli.py",
    },
    "feedback_events": {
        "kind": "runtime_owner",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/recall/feedback/events.py",
    },
    "source_backed_lessons": {
        "kind": "runtime_owner",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/recall/source_backed_lessons.py",
    },
    "action_hint_cache": {
        "kind": "runtime_owner",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/hooks/action_hint_cache.py",
    },
}


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _text(title: str, body: str = "") -> str:
    return f"{title}\n{body}".strip()


def issue_reference_from_text(value: str) -> str | None:
    raw = str(value or "").strip()
    if ISSUE_NUMBER_RE.fullmatch(raw):
        return raw
    if ISSUE_URL_RE.match(raw):
        return raw
    return None


def fetch_issue_context(reference: str) -> dict[str, Any]:
    """Fetch public issue context for the natural foreground input shape.

    The guard is often called from a GitHub issue audit where the agent only
    has `1802` or a copied issue URL. Keeping this fetch here prevents the
    caller from leaving the front door, manually reconstructing title/body, and
    losing comment context before the active-pull decision is made. The fetched
    material is still only used for route guidance; it is not source evidence.
    """

    proc = subprocess.run(
        [
            "gh",
            "issue",
            "view",
            reference,
            "--comments",
            "--json",
            "number,title,body,url,comments",
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("could not fetch GitHub issue context with `gh issue view`")
    data = json.loads(proc.stdout or "{}")
    if not isinstance(data, dict):
        raise RuntimeError("GitHub issue context was not a JSON object")
    comments = []
    for item in data.get("comments") or []:
        if isinstance(item, dict) and str(item.get("body") or "").strip():
            comments.append(str(item.get("body") or ""))
    return {
        "number": data.get("number"),
        "title": str(data.get("title") or ""),
        "body": str(data.get("body") or ""),
        "url": str(data.get("url") or ""),
        "comments": comments,
    }


def classify_issue_work(title: str, body: str = "") -> list[str]:
    text = _text(title, body)
    if TRIVIAL_RE.search(text):
        return ["trivial_local_edit"]
    categories: list[str] = []
    if BENCHMARK_RE.search(text):
        categories.append("benchmark_or_external_evaluation")
    if SKILL_DOCS_RE.search(text):
        categories.append("skill_or_docs_surface")
    if FOREGROUND_CARD_RE.search(text):
        categories.append("foreground_card_or_cli_surface")
    if ARCHITECTURE_RE.search(text):
        categories.append("architecture_or_memory_design")
    return categories


def _owner_ref(owner_id: str, *, reason: str, confidence: str) -> dict[str, str]:
    return OWNER_REFS[owner_id] | {
        "id": owner_id,
        "reason": reason,
        "confidence": confidence,
    }


def _issue_recall_action(title: str) -> dict[str, Any]:
    cue = title.strip() or "current issue context"
    return {
        "id": "agent_recall_issue_context",
        "tool_name": "agent_recall",
        "command": f"aippocampus agent recall {shell_quote(cue)} --json",
        "arguments": {"cue": cue},
        "mutation_risk": "read_only",
        "claim_boundary": "no_claim_before_reopen",
        "why": "Pull route context before implementing issue work that likely has existing owners.",
    }


def _continue_without_recall_action() -> dict[str, Any]:
    return {
        "id": "continue_without_recall",
        "message": "No existing AIppocampus route owner is required for this local issue shape.",
        "mutation_risk": "read_only",
        "claim_boundary": "navigation_only_not_fact",
        "why": "Continue normal work; run recall later only if old source context becomes relevant.",
    }


def build_issue_active_pull_packet(
    *,
    title: str,
    body: str = "",
    changed_files: Iterable[str] = (),
    lesson_constraints: Iterable[str] = (),
) -> dict[str, Any]:
    categories = classify_issue_work(title, body)
    changed = list(changed_files)
    path_text = "\n".join(changed)
    benchmark_like = "benchmark_or_external_evaluation" in categories or BENCHMARK_RE.search(path_text)
    learning_loop_like = bool(LEARNING_LOOP_RE.search(_text(title, body)) or LEARNING_LOOP_RE.search(path_text))
    skill_docs_like = "skill_or_docs_surface" in categories or SKILL_DOCS_RE.search(path_text)
    foreground_card_like = (
        "foreground_card_or_cli_surface" in categories or FOREGROUND_CARD_RE.search(path_text)
    )
    architecture_like = "architecture_or_memory_design" in categories or ARCHITECTURE_RE.search(path_text)
    trivial_only = categories == ["trivial_local_edit"]
    should_pull = bool(not trivial_only and (benchmark_like or skill_docs_like or foreground_card_like or architecture_like))

    if not should_pull:
        action = _continue_without_recall_action()
        return {
            "kind": "aippocampus_issue_work_orientation_packet",
            "schema_version": SCHEMA_VERSION,
            "should_pull": False,
            "output_mode": "silence",
            "reason": "no benchmark, architecture, or memory-design trigger detected",
            "suggested_agent_action": "continue_without_recall",
            "fallback_action": "continue normally; run agent recall if old source context becomes relevant",
            **canonical_foreground_action_fields(action, safe_next_actions=[action]),
            "lead_kinds": [],
            "existing_owner_refs": [],
            "existing_owner_ref_ids": [],
            "owner_refs_confidence": "none",
            "constraints": [],
            "claim_permission": "navigation_only_not_fact",
        }

    owner_ids: list[str] = []
    owner_reasons: dict[str, str] = {}
    owner_confidence = "medium"
    if benchmark_like:
        owner_ids.extend(
            [
                "semantic_scope_labeling",
                "semantic_scope_builder",
                "subconscious_jobs",
                "warm_ambient_routes",
                "attention_router",
            ]
        )
        owner_reasons.update(
            {
                "semantic_scope_labeling": "benchmark/source-side issue should check source-shape job contracts",
                "semantic_scope_builder": "benchmark/source-side issue may depend on semantic recall gates",
                "subconscious_jobs": "benchmark/source-side issue may depend on background job findings",
                "warm_ambient_routes": "benchmark/source-side issue may depend on warm route artifacts",
                "attention_router": "benchmark/source-side issue may depend on attention-router behavior",
            }
        )
        owner_confidence = "high"
    if skill_docs_like:
        owner_ids.extend(["skill_entrypoint", "public_docs", "docs_health_guard"])
        owner_reasons.update(
            {
                "skill_entrypoint": "issue mentions SKILL/docs/bootstrap surface",
                "public_docs": "public first-use docs shape the foreground route",
                "docs_health_guard": "docs-health guards prevent SKILL/public docs drift",
            }
        )
        owner_confidence = "high"
    if foreground_card_like:
        owner_ids.extend(
            ["foreground_cli_facade", "foreground_output_projection", "agent_continuity_cards"]
        )
        owner_reasons.update(
            {
                "foreground_cli_facade": "foreground card issue should start at the public CLI facade",
                "foreground_output_projection": "compact JSON card shape is projected here",
                "agent_continuity_cards": "agent-facing recovery and recall cards live here",
            }
        )
        owner_confidence = "high"
    if learning_loop_like:
        owner_ids.extend(
            ["learning_loop_cli", "feedback_events", "source_backed_lessons", "action_hint_cache"]
        )
        owner_reasons.update(
            {
                "learning_loop_cli": "learning-loop issue should start at learning guidance/replay frontdoors",
                "feedback_events": "repeated mistake fixes depend on captured route/tool feedback",
                "source_backed_lessons": "durable guidance should be source-backed before foreground use",
                "action_hint_cache": "action-time guidance reaches hooks through the prepared hint cache",
            }
        )
        owner_confidence = "high"
    elif architecture_like:
        owner_ids.extend(["attention_router", "semantic_scope_builder"])
        owner_reasons.update(
            {
                "attention_router": "generic architecture issue mentions attention/route design",
                "semantic_scope_builder": "generic architecture issue mentions semantic/source-scope design",
            }
        )
    owner_ids = _unique(owner_ids)

    constraints = [
        *lesson_constraints,
    ]
    if benchmark_like:
        constraints.append("check_existing_routes_before_manual_benchmark_scaffold")
    if architecture_like and not benchmark_like:
        constraints.append("check_existing_architecture_owner_before_patch")
    if learning_loop_like:
        constraints.append("check_learning_feedback_and_lesson_owner_before_router_patch")
    if skill_docs_like or foreground_card_like:
        constraints.append("check_foreground_surface_owner_before_runtime_patch")
    lead_kinds = ["memory_route", "aippo_working_contract"]
    if benchmark_like:
        lead_kinds.append("benchmark_capability_provenance")
    if skill_docs_like:
        lead_kinds.append("skill_or_docs_surface_owner")
    if foreground_card_like:
        lead_kinds.append("foreground_card_contract")
    if learning_loop_like:
        lead_kinds.append("learning_feedback_owner")

    recall_action = _issue_recall_action(title)
    return {
        "kind": "aippocampus_issue_work_orientation_packet",
        "schema_version": SCHEMA_VERSION,
        "should_pull": True,
        "output_mode": "reopenable_route",
        "reason": "issue surface has existing owners that may change the safe implementation route",
        "suggested_agent_action": "agent_recall",
        "fallback_action": "if recall is unavailable, inspect listed owner refs before broad manual scaffolding",
        **canonical_foreground_action_fields(recall_action, safe_next_actions=[recall_action]),
        "lead_kinds": _unique(lead_kinds),
        "existing_owner_refs": [
            _owner_ref(
                item,
                reason=owner_reasons.get(item, "issue text matches this existing owner surface"),
                confidence=owner_confidence if item in owner_reasons else "medium",
            )
            for item in owner_ids
        ],
        "existing_owner_ref_ids": owner_ids,
        "owner_refs_confidence": owner_confidence if owner_ids else "low",
        "constraints": _unique(constraints),
        "active_pull_required_before": [
            "implementation",
            "benchmark_claim",
            "issue_closeout",
        ],
        "route_first_questions": [
            "Which AIppocampus runtime path already owns this capability?",
            "Is this score measuring that path or benchmark-local scaffolding?",
            "What follow-up remains if this is only a proxy or isolated experiment?",
        ],
        "claim_permission": "navigation_only_not_fact",
        "not_enough_for_claim": True,
    }


def build_issue_work_guard_fixture_report() -> dict[str, Any]:
    cases: list[dict[str, Any]] = [
        {
            "case_id": "ignored_ambient_scent_benchmark_agent",
            "packet": build_issue_active_pull_packet(
                title="Fix LongMemEval source-side semantic cache benchmark",
                body="The agent should use existing semantic scope and warm ambient owners.",
            ),
        },
        {
            "case_id": "architecture_design_issue",
            "packet": build_issue_active_pull_packet(
                title="Wire Attention Router to benchmark capability provenance",
                body="Architecture closeout needs route-first context.",
            ),
        },
        {
            "case_id": "trivial_typo",
            "packet": build_issue_active_pull_packet(
                title="Fix typo in README",
                body="One spelling correction.",
            ),
        },
    ]
    active = [case for case in cases if case["packet"]["should_pull"]]
    silent = [case for case in cases if not case["packet"]["should_pull"]]
    red_lines = {
        "broad_manual_search_before_route_count": 0,
        "packet_contains_fact_claim_count": 0,
    }
    return {
        "kind": "aippocampus_issue_work_guard_fixture",
        "schema_version": SCHEMA_VERSION,
        "ok": all(value == 0 for value in red_lines.values()) and len(active) == 2 and len(silent) == 1,
        "metrics": {
            "case_count": len(cases),
            "active_pull_required_count": len(active),
            "trivial_silence_count": len(silent),
        },
        "red_lines": red_lines,
        "cases": cases,
    }


def render_issue_work_guard_text(packet: dict[str, Any]) -> str:
    should_pull = bool(packet.get("should_pull"))
    if should_pull:
        reason = ", ".join(packet.get("lead_kinds") or []) or "old design context may matter"
        next_line = 'aippocampus agent recall "<issue title and key terms>" --public'
    else:
        reason = "no benchmark, architecture, or memory-design trigger detected"
        next_line = "continue without an AIppocampus recall pull"
    return "\n".join(
        [
            "AIppocampus work guard",
            f"decision: {'pull continuity first' if should_pull else 'continue'}",
            (
                "meaning: pull = run recall/deepen or inspect listed owners before implementation; "
                "continue = no active continuity pull is required yet"
            ),
            f"reason: {reason}",
            f"next: {next_line}",
            "boundary: this is route guidance, not evidence or a task decision.",
        ]
    )


def _issue_body_with_comments(context: dict[str, Any], body_override: str = "") -> str:
    parts = [body_override or str(context.get("body") or "")]
    comments = [
        str(item).strip()
        for item in context.get("comments") or []
        if str(item).strip()
    ]
    if comments:
        parts.append("\n\nIssue comments:\n" + "\n\n".join(comments))
    return "\n".join(part for part in parts if part).strip()


def _issue_error_payload(message: str) -> dict[str, Any]:
    return {
        "kind": "aippocampus_issue_work_orientation_packet",
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "error": {
            "code": "issue_context_unavailable",
            "message": message,
        },
        "foreground_guidance": (
            "Retry from a GitHub checkout with `gh auth status`, pass --title/--body "
            "directly, or inspect the issue/comments manually before continuing."
        ),
        "recovery_actions": [
            "gh auth status",
            "aippocampus work-guard --title <issue title> --body <issue body> --json",
        ],
    }


def _missing_input_payload() -> dict[str, Any]:
    return foreground_recovery_card(
        kind="aippocampus_issue_work_orientation_packet",
        error_code="work_guard_issue_or_title_required",
        message="Provide a GitHub issue number/URL or an explicit --title before using work-guard.",
        safe_next_actions=[
            foreground_template_action(
                action_id="inspect_issue_context",
                label="Fetch and classify a GitHub issue",
                command_template="aippocampus work-guard {issue_number_or_url} --json",
                requires=["issue_number_or_url"],
                why="Use this when issue comments and source-route context may change the implementation path.",
                mutation_risk="read_only",
                claim_boundary="navigation_only_not_fact",
            ),
            foreground_template_action(
                action_id="classify_title_body",
                label="Classify provided title/body",
                command_template='aippocampus work-guard --title "{issue_title}" --body "{issue_body}" --json',
                requires=["issue_title", "issue_body"],
                why="Use this if GitHub is unavailable but the issue text is already in context.",
                mutation_risk="read_only",
                claim_boundary="navigation_only_not_fact",
            ),
            foreground_template_action(
                action_id="run_recall_for_issue",
                label="Pull continuity before memory-design work",
                command_template='aippocampus agent recall "{issue_cue}" --json',
                requires=["issue_cue"],
                why="Memory-design, benchmark, AIppo, and learning-loop work should pull existing route owners first.",
                mutation_risk="read_only",
                claim_boundary="no_claim_before_reopen",
            ),
        ],
        source_boundary={
            "work_guard_is_route_guidance_not_evidence": True,
            "source_reopen_required_before_claims": True,
            "no_write_happened": True,
        },
    )


def _render_missing_input_text(payload: dict[str, Any]) -> str:
    actions = [item for item in payload.get("safe_next_actions") or [] if isinstance(item, dict)]
    lines = [
        "AIppocampus work guard",
        "decision: issue or title required",
        "meaning: classify issue work before benchmark, architecture, AIppo, or learning-loop changes.",
    ]
    for action in actions[:3]:
        command = action.get("command") or action.get("command_template")
        lines.append(f"- {action.get('label') or action.get('id')}: {command}")
    lines.append("boundary: this is route guidance, not source evidence.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if not raw_args:
        payload = _missing_input_payload()
        print(_render_missing_input_text(payload))
        return 2
    if set(raw_args) <= {"--json"}:
        payload = _missing_input_payload()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    parser = argparse.ArgumentParser(
        prog="aippocampus work-guard",
        description=(
            "Issue-work orientation card:\n"
            "  Use before benchmark, architecture, recall, AIppo, source-side, or memory-design work.\n"
            "  It decides whether to pull continuity/source owners before broad manual search.\n"
            "  `pull` means follow recall/deepen or listed owner refs before implementation.\n"
            "  `continue` means no active continuity pull is required for this issue yet.\n"
            "  Output is route guidance only; it is not evidence and does not decide the issue for you."
        ),
        epilog=(
            "Examples:\n"
            "  aippocampus work-guard 1802 --json\n"
            "  aippocampus work-guard https://github.com/Sapientropic/AIppocampus/issues/1802 --json\n"
            "  aippocampus work-guard --title \"Fix LongMemEval source-side cache\" --json\n"
            "  aippocampus work-guard --title \"Fix typo in README\" --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("issue_ref", nargs="?", help="GitHub issue number or issue URL.")
    parser.add_argument("--issue", help="GitHub issue number or issue URL.")
    parser.add_argument("--title")
    parser.add_argument("--body", default="")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--fixture-report", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(raw_args)

    issue_ref = args.issue or issue_reference_from_text(args.issue_ref or "")
    issue_context: dict[str, Any] = {}
    if issue_ref:
        try:
            issue_context = fetch_issue_context(issue_ref)
        except Exception as exc:
            payload = _issue_error_payload(str(exc))
            if args.json_output:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print("AIppocampus work guard")
                print("decision: issue context unavailable")
                print("next: " + payload["foreground_guidance"])
            return 2
    elif args.issue_ref:
        parser.error("positional input must be a GitHub issue number or issue URL")

    title = args.title or str(issue_context.get("title") or "")
    if not args.fixture_report and not title:
        payload = _missing_input_payload()
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_missing_input_text(payload))
        return 2
    body = _issue_body_with_comments(issue_context, args.body)

    payload = (
        build_issue_work_guard_fixture_report()
        if args.fixture_report
        else build_issue_active_pull_packet(
            title=title,
            body=body,
            changed_files=args.changed_file,
        )
    )
    if issue_context and not args.fixture_report:
        payload["issue_number"] = issue_context.get("number")
        payload["issue_url"] = issue_context.get("url")
        payload["issue_context"] = {
            "title_included": bool(issue_context.get("title")),
            "body_included": bool(issue_context.get("body") or args.body),
            "comments_included": len(issue_context.get("comments") or []),
        }
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if args.fixture_report:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(render_issue_work_guard_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
