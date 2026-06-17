"""Task-aware usefulness helpers for AIppo activation packets."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.recall import continuity_usefulness

TASK_FAMILY_TERMS = {
    "issue_writing": ("issue", "upstream issue", "write upstream", "closeout", "triage", "github"),
    "benchmark_reporting": ("benchmark", "report", "evidence", "claim"),
    "PR_review": ("pr", "review", "pull request"),
    "coding": ("code", "coding", "patch", "implementation", "test"),
    "fresh_thread_recall": (
        "fresh agent",
        "fresh thread",
        "old vague context",
        "vague context",
        "remember old",
        "recall old",
        "continuity recall",
        "before answering",
    ),
    "host_readiness": (
        "install plugin",
        "plugin install",
        "plugin packaging",
        "plugin package",
        "plugin cache",
        "mcp host",
        "mcp health",
        "host readiness",
        "verify mcp",
        "plugin readiness",
        "tools visible",
        "hook install",
        "hook status",
        "install ux",
        "cache readiness",
        "status readiness",
        "current thread visibility",
    ),
    "product_workflow": (
        # This term list is only a deterministic foreground front door for
        # project workflow guidance. It keeps recurring AIppocampus product/UX
        # work from falling into an empty contract, but it is not a replacement
        # for source-backed recall or semantic routing.
        "action-time",
        "action time",
        "action hint",
        "action-hint",
        "agent surface",
        "agent-surface",
        "agent-unfriendly",
        "audit",
        "cli",
        "critique",
        "hook cache",
        "hook readiness",
        "disclaimer wall",
        "fake command",
        "foreground action",
        "foreground contract",
        "foreground json",
        "foreground surface",
        "public safe",
        "public-safe",
        "python3",
        "macos",
        "mcp",
        "provider auth",
        "operator json",
        "over-conservative",
        "placeholder cue",
        "product surface",
        "product-surface",
        "semantic auth",
        "semantic gate",
        "attention router",
        "mcp health",
        "memory_health",
        "recall diagnostic",
        "source-backed attention",
        "working contract",
    ),
}

DIRECT_GUIDANCE_FAMILIES = {"fresh_thread_recall", "host_readiness", "product_workflow"}


def _text(value: Any, limit: int = 240) -> str:
    return compact_text(str(value or "").strip(), limit)


def _strings(value: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _text(item, 160)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def json_bytes(value: Mapping[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def task_families(task: str) -> list[str]:
    task_text = _text(task, 240).casefold()
    scored: list[tuple[int, str]] = []
    for family, terms in TASK_FAMILY_TERMS.items():
        score = sum(1 for term in terms if term in task_text)
        if family.replace("_", " ").casefold() in task_text:
            score += 4
        if score:
            scored.append((score, family))
    return [family for _, family in sorted(scored, reverse=True)]


def _is_active_clause(clause: Mapping[str, Any]) -> bool:
    lifecycle_raw = clause.get("lifecycle")
    activation_raw = clause.get("activation")
    lifecycle: Mapping[str, Any] = lifecycle_raw if isinstance(lifecycle_raw, Mapping) else {}
    activation: Mapping[str, Any] = activation_raw if isinstance(activation_raw, Mapping) else {}
    return lifecycle.get("status") == "ripe" and bool(activation.get("foreground_eligible"))


def _lifecycle_status(clause: Mapping[str, Any]) -> str | None:
    lifecycle_raw = clause.get("lifecycle")
    lifecycle: Mapping[str, Any] = lifecycle_raw if isinstance(lifecycle_raw, Mapping) else {}
    status = lifecycle.get("status")
    return str(status) if status is not None else None


def selected_active_clauses(
    clauses: Sequence[Mapping[str, Any]],
    task: str,
    *,
    limit: int = 2,
) -> list[dict[str, Any]]:
    families = task_families(task)
    if not families:
        return []
    active = [dict(clause) for clause in clauses if _is_active_clause(clause)]

    def score(clause: Mapping[str, Any]) -> tuple[int, str]:
        applies = {str(item).casefold() for item in clause.get("applies_when") or []}
        guidance = _text(clause.get("guidance"), 320).casefold()
        family_hits = sum(
            1
            for family in families
            if family.casefold() in applies or family.casefold() in guidance
        )
        term_hits = sum(
            1
            for family in families
            for term in TASK_FAMILY_TERMS.get(family, ())
            if term in guidance or term in applies
        )
        return family_hits * 4 + term_hits, str(clause.get("clause_id") or "")

    ranked = sorted(active, key=score, reverse=True)
    selected = [clause for clause in ranked if score(clause)[0] > 0][:limit]
    if DIRECT_GUIDANCE_FAMILIES.intersection(families):
        return selected
    return selected or ranked[:limit]


def guidance_snippets(clauses: Sequence[Mapping[str, Any]]) -> list[str]:
    return [_text(clause.get("guidance"), 128) for clause in clauses if clause.get("guidance")]


def usefulness_metrics(
    contract: Mapping[str, Any],
    activation: Mapping[str, Any],
) -> dict[str, Any]:
    clauses = [clause for clause in contract.get("clauses") or [] if isinstance(clause, Mapping)]
    selected_guidance = _strings(activation.get("use_guidance"), limit=6)
    stale_or_challenged = {
        str(clause.get("clause_id"))
        for clause in clauses
        if _lifecycle_status(clause) in {"stale", "challenged"}
    }
    active_ids = {str(item) for item in activation.get("active_clause_ids") or []}
    info_tokens = sum(len(item.split()) for item in selected_guidance)
    active_count = len(active_ids) if active_ids else int(activation.get("active_clause_count") or 0)
    generic_only = int(
        not selected_guidance
        or activation.get("display_hint") == "Scope slice, verify, reopen before claims."
    )
    return {
        "active_clause_information_density": round(info_tokens / max(1, json_bytes(activation)), 4),
        "generic_safety_posture_only_count": generic_only,
        "stable_workflow_search_avoided_count": active_count if selected_guidance else 0,
        "aippo_next_action_delta_count": int(
            bool(selected_guidance) and activation.get("next_action") == "use_hint"
        ),
        "stale_clause_suppressed_count": len(stale_or_challenged - active_ids),
        "low_risk_guidance_allowed_without_reopen_count": active_count if selected_guidance else 0,
        "usefulness_gate_ok": generic_only == 0 and bool(selected_guidance),
    }


def continuity_usefulness_for_activation(
    activation: Mapping[str, Any],
    red_lines: Mapping[str, Any],
) -> dict[str, Any]:
    guidance = [str(item) for item in activation.get("use_guidance") or []]
    active_ids = [item for item in activation.get("active_clause_ids") or [] if str(item).strip()]
    active_count = len(active_ids) if active_ids else int(activation.get("active_clause_count") or 0)
    return continuity_usefulness.continuity_usefulness_metrics(
        {
            "red_line_counts": red_lines,
            "manual_query_invention_count": 0,
            "blind_deepen_required_count": 0,
            "packet_triage_distinctiveness": 0.8 if active_count > 1 else 1.0,
            "wrong_route_drag_count": 0,
            "useful_packet_count": active_count,
            "packet_count": max(1, active_count),
            "foreground_protocol_noise_bytes": 48,
            "useful_guidance_bytes": sum(len(item.encode("utf-8")) for item in guidance),
            "time_to_first_useful_packet_ms_proxy": 120,
        }
    )
