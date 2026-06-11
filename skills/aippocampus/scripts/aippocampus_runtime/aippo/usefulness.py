"""Task-aware usefulness helpers for AIppo activation packets."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.core import compact_text

TASK_FAMILY_TERMS = {
    "issue_writing": ("issue", "closeout", "triage", "github"),
    "benchmark_reporting": ("benchmark", "report", "evidence", "claim"),
    "PR_review": ("pr", "review", "pull request"),
    "coding": ("code", "coding", "patch", "implementation", "test"),
}


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
    return [family for _, family in sorted(scored, reverse=True)] or ["coding"]


def _is_active_clause(clause: Mapping[str, Any]) -> bool:
    lifecycle = clause.get("lifecycle") if isinstance(clause.get("lifecycle"), Mapping) else {}
    activation = clause.get("activation") if isinstance(clause.get("activation"), Mapping) else {}
    return lifecycle.get("status") == "ripe" and bool(activation.get("foreground_eligible"))


def selected_active_clauses(
    clauses: Sequence[Mapping[str, Any]],
    task: str,
    *,
    limit: int = 2,
) -> list[dict[str, Any]]:
    families = task_families(task)
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
        if (clause.get("lifecycle") or {}).get("status") in {"stale", "challenged"}
    }
    active_ids = {str(item) for item in activation.get("active_clause_ids") or []}
    info_tokens = sum(len(item.split()) for item in selected_guidance)
    active_count = max(
        len(active_ids),
        int(activation.get("active_clause_count") or 0),
    )
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
