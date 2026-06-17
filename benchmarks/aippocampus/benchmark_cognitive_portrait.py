#!/usr/bin/env python3
"""Benchmark structured-text cognitive portraits against fuller source context.

This near-term #70 runner intentionally stays in the black-box, source-backed
surface: it builds a compact portrait from question candidates, frontier
markers, question links, and theme candidates, then checks what that compact
prompt preserves or loses compared with fuller clean-source injection. It does
not test numerical activation codes, white-box steering, or live model behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import _paths

_paths.ensure_paths()

from aippocampus_runtime.core import benchmark_text_is_sensitive
from shared.report_actions import report_next_action

SCHEMA_VERSION = 1
PORTRAIT_KIND = "aippocampus_cognitive_portrait"
BENCHMARK_KIND = "aippocampus_cognitive_portrait_benchmark"
# This is a claim boundary, not a statistical power claim. The fixture can
# catch contract regressions with three deterministic prompts, but it must not
# be read as empirical portrait-quality evidence until the case pack is much
# denser and source-backed.
MINIMUM_EMPIRICAL_PROMPT_CASE_COUNT = 30
SOURCE_BACKED_FINDING_KINDS = {
    "question_candidate",
    "frontier_marker",
    "question_link",
    "theme_candidate",
}
RISKY_PROFILE_RE = re.compile(
    r"(?i)\b(the user|user|用户)\b.{0,48}\b(always|never|is|are|personality|identity|obsessed|"
    r"distrustful|prefers|likes|hates|本质|人格|总是|从不|喜欢|讨厌)\b"
)
FIDELITY_GAP_ACTIONS = {
    "Exact quote recovery still needs fuller clean-source injection.": {
        "gap_id": "exact_quote_recovery",
        "action": report_next_action(
            action_id="repair_exact_quote_clean_source_reopen",
            label="Map exact-quote loss to clean-source reopen owners",
            reason=(
                "The portrait omitted exact quote material that full source context "
                "can recover; repair should happen in clean-source/deepen source "
                "window projection, not by treating portrait text as source truth."
            ),
            command='aippocampus search "exact quote recovery" --json',
            owner_path=(
                "skills/aippocampus/scripts/aippocampus_runtime/mcp/recall_navigation.py"
            ),
        ),
    },
}


def fidelity_gap_actions(losses: Iterable[str]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for loss in losses:
        mapped = FIDELITY_GAP_ACTIONS.get(str(loss))
        if not mapped:
            continue
        action = dict(mapped["action"])
        action["gap_id"] = mapped["gap_id"]
        action["loss"] = str(loss)
        actions.append(action)
    return actions


@dataclass(frozen=True)
class PromptCase:
    case_id: str
    prompt: str
    expected_terms: tuple[str, ...]
    forbidden_terms: tuple[str, ...] = ()
    expects_portrait_equivalence: bool = True
    loss_reason: str | None = None


@dataclass(frozen=True)
class PortraitFixture:
    findings: tuple[dict[str, Any], ...]
    source_snippets: dict[str, str]
    prompt_cases: tuple[PromptCase, ...]


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()


def contains_secret_or_local_path(value: str) -> bool:
    return benchmark_text_is_sensitive(value)


def small_sample_warning(
    *,
    sample_case_count: int,
    minimum_empirical_case_count: int,
    claim_level: str,
    selection_method: str,
    cannot_claim: list[str],
) -> dict[str, Any] | None:
    if sample_case_count >= minimum_empirical_case_count:
        return None
    return {
        "sample_case_count": sample_case_count,
        "minimum_empirical_case_count": minimum_empirical_case_count,
        "claim_level": claim_level,
        "selection_method": selection_method,
        "cannot_claim": cannot_claim,
    }


def approx_token_count(text: str) -> int:
    if not text:
        return 0
    wordish = re.findall(r"[\w\u4e00-\u9fff]+|[^\s\w]", text, flags=re.UNICODE)
    char_estimate = math.ceil(len(text) / 4)
    return max(1, max(len(wordish), char_estimate))


def compact_text(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def stable_ref_token(ref: Mapping[str, Any]) -> str:
    parts = [
        str(ref.get("thread_key") or ref.get("thread") or "thread"),
        str(ref.get("turn_id") or ref.get("message_id") or ref.get("source_line") or "source"),
    ]
    safe = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", ":".join(parts)).strip("-")
    return f"ref:{safe or sha1_text(json.dumps(dict(ref), sort_keys=True))[:10]}"


def dedupe_refs(refs: Iterable[Mapping[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for ref in refs:
        token = stable_ref_token(ref)
        if token in seen:
            continue
        seen.add(token)
        ref_payload = dict(ref)
        ref_payload["ref_token"] = token
        out.append(ref_payload)
        if len(out) >= limit:
            break
    return out


def source_refs(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("source_refs")
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, Mapping)]
    return []


def row_id(row: Mapping[str, Any]) -> str:
    for key in ("fingerprint", "source_finding_id", "question_cluster_id", "theme_cluster_id", "id"):
        value = row.get(key)
        if value:
            return str(value)
    return "finding:" + sha1_text(json.dumps(dict(row), sort_keys=True, default=str))[:16]


def source_ref_tokens(refs: Iterable[Mapping[str, Any]]) -> list[str]:
    return [stable_ref_token(ref) for ref in refs]


def is_source_backed(row: Mapping[str, Any]) -> bool:
    return row.get("finding_kind") in SOURCE_BACKED_FINDING_KINDS and bool(source_refs(row))


def unique_preserve(values: Iterable[object], *, limit: int = 8) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = compact_text(value, 80)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def build_cognitive_portrait(findings: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    finding_rows = [dict(row) for row in findings]
    backed_rows: list[Mapping[str, Any]] = []
    skipped_unbacked: list[str] = []
    for row in finding_rows:
        if is_source_backed(row):
            backed_rows.append(row)
        elif row.get("finding_kind") in SOURCE_BACKED_FINDING_KINDS:
            skipped_unbacked.append(row_id(row))

    candidates = [row for row in backed_rows if row.get("finding_kind") == "question_candidate"]
    frontiers = [row for row in backed_rows if row.get("finding_kind") == "frontier_marker"]
    links = [row for row in backed_rows if row.get("finding_kind") == "question_link"]
    themes = [row for row in backed_rows if row.get("finding_kind") == "theme_candidate"]
    candidate_by_finding_id = {row_id(row): row for row in candidates}

    recurring_questions: list[dict[str, Any]] = []
    linked_candidate_ids: set[str] = set()
    for link in links:
        linked_questions = [
            item
            for item in link.get("linked_questions") or []
            if isinstance(item, Mapping)
        ]
        link_refs = dedupe_refs(source_refs(link))
        linked_source_finding_ids = [
            str(item.get("source_finding_id"))
            for item in linked_questions
            if item.get("source_finding_id")
        ]
        linked_candidate_ids.update(linked_source_finding_ids)
        candidate_rows = [
            candidate_by_finding_id[finding_id]
            for finding_id in linked_source_finding_ids
            if finding_id in candidate_by_finding_id
        ]
        all_refs = dedupe_refs(
            [*link_refs, *(ref for row in candidate_rows for ref in source_refs(row))],
            limit=12,
        )
        dimensions = unique_preserve(
            [
                *(link.get("concepts") or []),
                *(value for row in candidate_rows for value in row.get("what_features") or []),
            ],
            limit=10,
        )
        recurring_questions.append(
            {
                "cluster_id": str(link.get("question_cluster_id") or row_id(link)),
                "label": compact_text(
                    link.get("linked_question_short")
                    or link.get("title")
                    or "recurring question",
                    90,
                ),
                "link_type": compact_text(link.get("link_type") or "recurring", 40),
                "question_count": int(link.get("question_count") or len(linked_questions) or 1),
                "source_thread_count": int(link.get("source_thread_count") or 0),
                "dimensions": dimensions,
                "phase_contexts": unique_preserve(
                    item.get("phase_context") for item in linked_questions if item.get("phase_context")
                ),
                "intent_orientations": unique_preserve(
                    item.get("intent_orientation")
                    for item in linked_questions
                    if item.get("intent_orientation")
                ),
                "source_finding_ids": linked_source_finding_ids or [row_id(link)],
                "source_refs": all_refs,
                "source_ref_tokens": source_ref_tokens(all_refs),
                "evidence_note": compact_text(link.get("summary") or "", 220),
            }
        )

    for candidate_row in candidates:
        candidate_id = row_id(candidate_row)
        if candidate_id in linked_candidate_ids:
            continue
        refs = dedupe_refs(source_refs(candidate_row))
        recurring_questions.append(
            {
                "cluster_id": candidate_id,
                "label": compact_text(
                    candidate_row.get("question_short") or candidate_row.get("question_text"),
                    90,
                ),
                "link_type": "single_observation",
                "question_count": 1,
                "source_thread_count": len({ref.get("thread_key") for ref in refs}),
                "dimensions": unique_preserve(
                    [
                        *(candidate_row.get("what_features") or []),
                        *(candidate_row.get("concepts") or []),
                    ],
                    limit=10,
                ),
                "phase_contexts": unique_preserve([candidate_row.get("phase_context")]),
                "intent_orientations": unique_preserve([candidate_row.get("intent_orientation")]),
                "source_finding_ids": [candidate_id],
                "source_refs": refs,
                "source_ref_tokens": source_ref_tokens(refs),
                "evidence_note": compact_text(candidate_row.get("summary") or "", 220),
            }
        )

    frontier_items: list[dict[str, Any]] = []
    for frontier_row in frontiers:
        refs = dedupe_refs(source_refs(frontier_row))
        frontier_items.append(
            {
                "source_finding_id": row_id(frontier_row),
                "frontier_type": compact_text(frontier_row.get("frontier_type") or "unresolved", 60),
                "linked_question_short": compact_text(
                    frontier_row.get("linked_question_short") or "",
                    90,
                ),
                "boundary_reason": compact_text(
                    frontier_row.get("boundary_reason") or frontier_row.get("summary"),
                    240,
                ),
                "dimensions": unique_preserve(
                    [
                        *(frontier_row.get("concepts") or []),
                        *(frontier_row.get("shared_concepts") or []),
                    ],
                    limit=10,
                ),
                "source_refs": refs,
                "source_ref_tokens": source_ref_tokens(refs),
            }
        )

    theme_items: list[dict[str, Any]] = []
    for theme_row in themes:
        refs = dedupe_refs(source_refs(theme_row))
        dimensions = unique_preserve(
            [
                *(theme_row.get("shared_concepts") or []),
                *(theme_row.get("concepts") or []),
                theme_row.get("theme_short"),
            ],
            limit=12,
        )
        theme_items.append(
            {
                "theme_id": row_id(theme_row),
                "label": compact_text(
                    theme_row.get("theme_short")
                    or theme_row.get("theme_label")
                    or theme_row.get("title")
                    or "theme candidate",
                    90,
                ),
                "dimensions": dimensions,
                "source_refs": refs,
                "source_ref_tokens": source_ref_tokens(refs),
                "evidence_note": compact_text(
                    theme_row.get("summary") or theme_row.get("theme_label") or "",
                    220,
                ),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": PORTRAIT_KIND,
        "surface": "structured_text_question_portrait",
        "source_surface": "question_candidate_frontier_marker_question_link_theme_candidate",
        "source_policy": (
            "navigation_layer_only: every portrait item must carry source refs; "
            "full clean source is still required for quotes and final evidence"
        ),
        "recurring_questions": recurring_questions,
        "frontiers": frontier_items,
        "themes": theme_items,
        "diagnostics": {
            "input_finding_count": len(finding_rows),
            "source_backed_finding_count": len(backed_rows),
            "skipped_unbacked_finding_ids": skipped_unbacked,
            "question_candidate_count": len(candidates),
            "frontier_marker_count": len(frontiers),
            "question_link_count": len(links),
            "theme_candidate_count": len(themes),
        },
    }


def render_structured_portrait(portrait: Mapping[str, Any]) -> str:
    lines = [
        "Cognitive portrait: source-backed navigation only; full source required for quotes/evidence; avoid personality model claims beyond refs.",
        "",
        "Recurring:",
    ]
    for item in portrait.get("recurring_questions") or []:
        refs = ", ".join(item.get("source_ref_tokens") or [])
        dimensions = ", ".join(item.get("dimensions") or [])
        phases = ", ".join(item.get("phase_contexts") or [])
        orientations = ", ".join(item.get("intent_orientations") or [])
        lines.extend(
            [
                f"- {item.get('label')} [{refs}]",
                f"  type={item.get('link_type')}; obs={item.get('question_count')}; threads={item.get('source_thread_count')}",
                f"  dimensions={dimensions or 'unspecified'}; phase={phases or 'unspecified'}; orientation={orientations or 'unspecified'}",
            ]
        )
    if portrait.get("frontiers"):
        lines.append("")
        lines.append("Frontiers:")
        for frontier in portrait.get("frontiers") or []:
            refs = ", ".join(frontier.get("source_ref_tokens") or [])
            dimensions = ", ".join(frontier.get("dimensions") or [])
            lines.extend(
                [
                    f"- {frontier.get('frontier_type')} {frontier.get('linked_question_short')} [{refs}]",
                    f"  boundary={frontier.get('boundary_reason')}; dimensions={dimensions or 'unspecified'}.",
                ]
            )
    if portrait.get("themes"):
        lines.append("")
        lines.append("Themes:")
        for theme in portrait.get("themes") or []:
            refs = ", ".join(theme.get("source_ref_tokens") or [])
            dimensions = ", ".join(theme.get("dimensions") or [])
            lines.extend(
                [
                    f"- {theme.get('label')} [{refs}]",
                    f"  dimensions={dimensions or 'unspecified'}; theme candidate, not a profile claim.",
                ]
            )
    return "\n".join(lines).strip()


def render_full_source_context(fixture: PortraitFixture) -> str:
    lines = [
        "Full clean-source injection for the same slice.",
        "These snippets are the source of truth for quotes, evidence, and final claims.",
        "",
    ]
    for ref_token, snippet in sorted(fixture.source_snippets.items()):
        lines.append(f"[{ref_token}] {snippet}")
    lines.append("")
    lines.append("Structured findings:")
    for finding in fixture.findings:
        kind = finding.get("finding_kind")
        refs = ", ".join(source_ref_tokens(source_refs(finding)))
        label = (
            finding.get("question_short")
            or finding.get("linked_question_short")
            or finding.get("frontier_type")
            or finding.get("title")
        )
        lines.append(f"- {kind}: {compact_text(label, 120)} [{refs}]")
    return "\n".join(lines).strip()


def render_naive_trait_summary() -> str:
    return (
        "The user is distrustful about agent memory and always wants continuity. "
        "Their personality is source-obsessed, so every answer should center that identity."
    )


def term_coverage(context: str, expected_terms: Iterable[str]) -> tuple[int, int, list[str]]:
    terms = tuple(expected_terms)
    lowered = context.casefold()
    missing = [term for term in terms if term.casefold() not in lowered]
    expected_count = len(terms)
    return expected_count - len(missing), expected_count, missing


def score_prompt_case(case: PromptCase, *, full_context: str, portrait_context: str) -> dict[str, Any]:
    full_hits, total, full_missing = term_coverage(full_context, case.expected_terms)
    portrait_hits, _, portrait_missing = term_coverage(portrait_context, case.expected_terms)
    forbidden_hits = [
        term
        for term in case.forbidden_terms
        if term.casefold() in portrait_context.casefold()
    ]
    full_rate = 1.0 if total == 0 else full_hits / total
    portrait_rate = 1.0 if total == 0 else portrait_hits / total
    equivalent = (
        portrait_rate >= 0.8
        and not forbidden_hits
        if case.expects_portrait_equivalence
        else portrait_rate < full_rate
    )
    return {
        "case_id": case.case_id,
        "prompt_sha1": sha1_text(case.prompt)[:16],
        "expected_term_count": total,
        "full_context_coverage": round(full_rate, 4),
        "portrait_context_coverage": round(portrait_rate, 4),
        "portrait_equivalent_by_fixture": bool(equivalent),
        "expects_portrait_equivalence": case.expects_portrait_equivalence,
        "loss_reason": case.loss_reason,
        "full_missing_terms": full_missing,
        "portrait_missing_terms": portrait_missing,
        "portrait_forbidden_hits": forbidden_hits,
    }


def source_fidelity_metrics(portrait: Mapping[str, Any]) -> dict[str, Any]:
    items: list[Mapping[str, Any]] = []
    items.extend(item for item in portrait.get("recurring_questions") or [] if isinstance(item, Mapping))
    items.extend(item for item in portrait.get("frontiers") or [] if isinstance(item, Mapping))
    items.extend(item for item in portrait.get("themes") or [] if isinstance(item, Mapping))
    missing = [
        str(item.get("cluster_id") or item.get("source_finding_id") or item.get("label"))
        for item in items
        if not item.get("source_refs") or not item.get("source_ref_tokens")
    ]
    return {
        "portrait_item_count": len(items),
        "items_with_source_refs": len(items) - len(missing),
        "missing_source_ref_item_ids": missing,
        "source_fidelity_rate": 1.0 if not items else round((len(items) - len(missing)) / len(items), 4),
    }


def over_personalization_metrics(contexts: Mapping[str, str]) -> dict[str, Any]:
    risks: dict[str, list[str]] = {}
    for name, context in contexts.items():
        risky_lines = []
        for line in context.splitlines():
            if RISKY_PROFILE_RE.search(line) and "[ref:" not in line and "source refs" not in line.casefold():
                risky_lines.append(compact_text(line, 180))
        risks[name] = risky_lines
    return {
        "risk_counts": {name: len(lines) for name, lines in risks.items()},
        "risky_lines": risks,
        "structured_portrait_safe": len(risks.get("structured_portrait", [])) == 0,
    }


def build_fixture() -> PortraitFixture:
    ref_1 = {
        "thread_key": "session:context-continuity-a",
        "turn_id": "turn-1",
        "message_id": "msg-1",
        "source_line": 12,
    }
    ref_2 = {
        "thread_key": "session:context-continuity-b",
        "turn_id": "turn-2",
        "message_id": "msg-2",
        "source_line": 28,
    }
    ref_3 = {
        "thread_key": "session:profile-boundary",
        "turn_id": "turn-3",
        "message_id": "msg-3",
        "source_line": 44,
    }
    candidate_1 = {
        "finding_kind": "question_candidate",
        "fingerprint": "sf_question_context_a",
        "question_text": "How do I keep agent context across compaction?",
        "question_short": "agent context continuity",
        "summary": "The user is asking how agent context survives compaction.",
        "confidence": 0.88,
        "source_refs": [ref_1],
        "what_features": ["agent memory", "context continuity", "compaction"],
        "where_context": ["AIppocampus"],
        "phase_context": "post_compaction",
        "intent_orientation": "implementation",
        "concepts": ["source-backed continuity", "agent handoff"],
    }
    candidate_2 = {
        "finding_kind": "question_candidate",
        "fingerprint": "sf_question_context_b",
        "question_text": "How should Codex resume after context was lost?",
        "question_short": "resume after context loss",
        "summary": "The user wants source-backed recovery after context loss.",
        "confidence": 0.9,
        "source_refs": [ref_2],
        "what_features": ["agent memory", "resume boundary", "source refs"],
        "where_context": ["AIppocampus"],
        "phase_context": "post_compaction",
        "intent_orientation": "implementation",
        "concepts": ["source-backed continuity", "resume point"],
    }
    candidate_3 = {
        "finding_kind": "question_candidate",
        "fingerprint": "sf_question_profile_boundary",
        "question_text": "How do we avoid turning memory into personality inference?",
        "question_short": "avoid personality inference",
        "summary": "The user draws a boundary around profile-like inference.",
        "confidence": 0.84,
        "source_refs": [ref_3],
        "what_features": ["source truth", "profile boundary", "over-personalization"],
        "where_context": ["AIppocampus"],
        "phase_context": "architecture_review",
        "intent_orientation": "safety",
        "concepts": ["source fidelity", "anti over-personalization"],
    }
    link = {
        "finding_kind": "question_link",
        "question_cluster_id": "ql_context_continuity",
        "linked_question_short": "agent context continuity",
        "question_count": 2,
        "source_thread_count": 2,
        "link_type": "recurring",
        "summary": "Tracked source-backed context-continuity questions across compaction-related turns.",
        "source_refs": [ref_1, ref_2],
        "concepts": ["agent memory", "source-backed continuity", "compaction"],
        "linked_questions": [
            {
                "source_finding_id": "sf_question_context_a",
                "question_short": "agent context continuity",
                "phase_context": "post_compaction",
                "intent_orientation": "implementation",
            },
            {
                "source_finding_id": "sf_question_context_b",
                "question_short": "resume after context loss",
                "phase_context": "post_compaction",
                "intent_orientation": "implementation",
            },
        ],
    }
    frontier = {
        "finding_kind": "frontier_marker",
        "fingerprint": "sf_frontier_compaction_resume",
        "frontier_type": "blocked",
        "linked_question_short": "agent context continuity",
        "summary": "The next agent must resume from a source-carrying boundary after compaction.",
        "boundary_reason": "Continuity claims were blocked until source refs and the current boundary survived handoff.",
        "concepts": ["source refs", "resume boundary", "handoff"],
        "source_refs": [ref_2],
    }
    findings = (candidate_1, candidate_2, candidate_3, link, frontier)
    source_snippets = {
        stable_ref_token(ref_1): (
            'User asked: "How do I keep agent context across compaction?" '
            "They wanted source refs preserved before the agent claimed continuity."
        ),
        stable_ref_token(ref_2): (
            'User correction: "Do not claim continuity unless source refs survive." '
            "The handoff was blocked at a resume boundary."
        ),
        stable_ref_token(ref_3): (
            'User boundary: "Do not turn this into a personality model." '
            "Use source truth, not profile inference."
        ),
    }
    prompt_cases = (
        PromptCase(
            case_id="resume_after_compaction",
            prompt="How should an agent resume after compaction in this track?",
            expected_terms=("source refs", "boundary", "compaction"),
        ),
        PromptCase(
            case_id="profile_boundary",
            prompt="What guardrail applies to interpreting this as a user profile?",
            expected_terms=("personality model", "source truth"),
            forbidden_terms=("always", "personality is"),
        ),
        PromptCase(
            case_id="exact_quote_recovery",
            prompt="Can you quote the exact correction about continuity claims?",
            expected_terms=("Do not claim continuity unless source refs survive",),
            expects_portrait_equivalence=False,
            loss_reason="Exact quote recovery still needs fuller clean-source injection.",
        ),
    )
    return PortraitFixture(
        findings=findings,
        source_snippets=source_snippets,
        prompt_cases=prompt_cases,
    )


def sanitized_portrait(portrait: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": portrait.get("schema_version"),
        "kind": portrait.get("kind"),
        "surface": portrait.get("surface"),
        "source_surface": portrait.get("source_surface"),
        "source_policy": portrait.get("source_policy"),
        "recurring_questions": [
            {
                "cluster_id": item.get("cluster_id"),
                "label": item.get("label"),
                "link_type": item.get("link_type"),
                "question_count": item.get("question_count"),
                "source_thread_count": item.get("source_thread_count"),
                "dimensions": item.get("dimensions"),
                "phase_contexts": item.get("phase_contexts"),
                "intent_orientations": item.get("intent_orientations"),
                "source_finding_ids": item.get("source_finding_ids"),
                "source_ref_tokens": item.get("source_ref_tokens"),
            }
            for item in portrait.get("recurring_questions") or []
        ],
        "frontiers": [
            {
                "source_finding_id": item.get("source_finding_id"),
                "frontier_type": item.get("frontier_type"),
                "linked_question_short": item.get("linked_question_short"),
                "dimensions": item.get("dimensions"),
                "source_ref_tokens": item.get("source_ref_tokens"),
            }
            for item in portrait.get("frontiers") or []
        ],
        "themes": [
            {
                "theme_id": item.get("theme_id"),
                "label": item.get("label"),
                "dimensions": item.get("dimensions"),
                "source_ref_tokens": item.get("source_ref_tokens"),
            }
            for item in portrait.get("themes") or []
        ],
        "diagnostics": portrait.get("diagnostics"),
    }


def run_benchmark(
    *,
    include_private_text: bool = False,
    findings: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    fixture = build_fixture()
    source_findings = fixture.findings if findings is None else findings
    effective_findings = tuple(dict(row) for row in source_findings)
    portrait = build_cognitive_portrait(effective_findings)
    portrait_context = render_structured_portrait(portrait)
    full_context = render_full_source_context(fixture)
    unsafe_summary = render_naive_trait_summary()
    cases = [
        score_prompt_case(case, full_context=full_context, portrait_context=portrait_context)
        for case in fixture.prompt_cases
    ]
    fidelity = source_fidelity_metrics(portrait)
    personalization = over_personalization_metrics(
        {
            "structured_portrait": portrait_context,
            "naive_trait_summary": unsafe_summary,
        }
    )
    full_tokens = approx_token_count(full_context)
    portrait_tokens = approx_token_count(portrait_context)
    expected_equivalence_cases = [
        case for case in cases if case["expects_portrait_equivalence"]
    ]
    equivalent_expected = [
        case for case in expected_equivalence_cases if case["portrait_equivalent_by_fixture"]
    ]
    expected_loss_cases = [
        case for case in cases if not case["expects_portrait_equivalence"]
    ]
    observed_loss_cases = [
        case for case in expected_loss_cases if case["portrait_equivalent_by_fixture"]
    ]
    compression_ratio = 0.0 if full_tokens == 0 else portrait_tokens / full_tokens
    quality_gate_ok = (
        portrait_tokens < full_tokens
        and fidelity["source_fidelity_rate"] == 1.0
        and personalization["structured_portrait_safe"]
        and len(equivalent_expected) == len(expected_equivalence_cases)
        and len(observed_loss_cases) == len(expected_loss_cases)
    )
    sample_case_count = len(fixture.prompt_cases)
    if not quality_gate_ok:
        claim_level = "diagnostic_only"
    elif sample_case_count >= MINIMUM_EMPIRICAL_PROMPT_CASE_COUNT:
        claim_level = "empirical_benchmark"
    else:
        claim_level = "contract_smoke"
    if claim_level == "empirical_benchmark":
        status = "sufficient"
    elif quality_gate_ok:
        status = "contract_smoke"
    else:
        status = "diagnostic_only"
    cannot_claim = [
        "live_model_behavioral_equivalence",
        "cross_model_activation_steering",
        "private_real_history_portrait_quality",
        "personality_or_identity_inference_validity",
    ]
    warning_cannot_claim = ["statistically_meaningful_cognitive_portrait_quality"]
    sample_warning = small_sample_warning(
        sample_case_count=sample_case_count,
        minimum_empirical_case_count=MINIMUM_EMPIRICAL_PROMPT_CASE_COUNT,
        claim_level=claim_level,
        selection_method="fixed deterministic source-backed prompt fixture",
        cannot_claim=warning_cannot_claim,
    )
    if sample_warning:
        cannot_claim.extend(warning_cannot_claim)
    emitted_contexts = [portrait_context, full_context, unsafe_summary] if include_private_text else []
    loses_fidelity = [
        case["loss_reason"]
        for case in cases
        if case["loss_reason"] and case["portrait_missing_terms"]
    ]
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": BENCHMARK_KIND,
        "created_at": now_utc(),
        "ok": True,
        "quality_gate_ok": quality_gate_ok,
        "status": status,
        "claim_level": claim_level,
        "sample_case_count": sample_case_count,
        "minimum_empirical_case_count": MINIMUM_EMPIRICAL_PROMPT_CASE_COUNT,
        "selection_method": "fixed deterministic source-backed prompt fixture",
        "sample_size_warning": sample_warning,
        "metrics": {
            "full_context_approx_tokens": full_tokens,
            "portrait_context_approx_tokens": portrait_tokens,
            "portrait_to_full_token_ratio": round(compression_ratio, 4),
            "token_savings_ratio": round(max(0.0, 1.0 - compression_ratio), 4),
            "source_fidelity_rate": fidelity["source_fidelity_rate"],
            "structured_over_personalization_risk_count": personalization["risk_counts"][
                "structured_portrait"
            ],
            "naive_summary_over_personalization_risk_count": personalization["risk_counts"][
                "naive_trait_summary"
            ],
            "expected_equivalence_case_count": len(expected_equivalence_cases),
            "expected_equivalence_pass_count": len(equivalent_expected),
            "expected_loss_case_count": len(expected_loss_cases),
            "expected_loss_observed_count": len(observed_loss_cases),
            "duration_seconds": round(time.perf_counter() - started, 4),
        },
        "cases": cases,
        "source_fidelity": fidelity,
        "over_personalization": personalization,
        "portrait": sanitized_portrait(portrait),
        "report": {
            "helps": [
                "Structured portrait preserves resume/guardrail cues while reducing the deterministic prompt footprint."
            ],
            "loses_fidelity": loses_fidelity,
            "over_personalization": [
                "Naive trait summaries can create unsupported profile claims; the structured portrait keeps observations tied to source refs."
            ],
        },
        "fidelity_gap_actions": fidelity_gap_actions(loses_fidelity),
        "privacy_boundary": {
            "raw_context_emitted": include_private_text,
            "raw_source_text_emitted": include_private_text,
            "absolute_paths_emitted": any(
                contains_secret_or_local_path(context) for context in emitted_contexts
            ),
            "case_selection_filters_active": True,
            "case_selection_filter_policy": (
                "aippocampus_runtime.safety.benchmark_sensitive_text_policy"
            ),
            "case_selection_action": "synthetic_cases_checked_for_sensitive_debug_text",
            "include_private_text_scope": "local_debug_only",
            "output_shape": "sanitized_cognitive_portrait_benchmark",
        },
        "can_claim": [
            "deterministic_structured_portrait_fixture_compares_compact_prompt_to_full_source_context",
            "portrait_items_keep_source_ref_back_pointers_in_the_checked_fixture",
        ],
        "cannot_claim": sorted(set(cannot_claim)),
    }
    if include_private_text:
        payload["debug_contexts"] = {
            "structured_portrait": portrait_context,
            "full_source_context": full_context,
            "naive_trait_summary": unsafe_summary,
        }
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the deterministic cognitive-portrait structured-text benchmark."
    )
    parser.add_argument("--json", action="store_true", help="Emit compact JSON.")
    parser.add_argument("--output", type=Path, help="Optional output JSON path.")
    parser.add_argument(
        "--include-private-text",
        action="store_true",
        help="Include raw synthetic source/debug prompt text in the JSON output.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = run_benchmark(include_private_text=bool(args.include_private_text))
    text = json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
