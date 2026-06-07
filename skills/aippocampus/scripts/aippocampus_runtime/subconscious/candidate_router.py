#!/usr/bin/env python3
"""Route subconscious promotion candidates into soft working memory.

Promotion candidates are useful before they become formal memory, but they
should not turn into another inbox the user must review. This router assigns a
bounded route:

- use_silently: low-risk recall/rerank helper
- use_with_source: current working hypothesis with source refs
- confirm_when_relevant: ask only if a current action depends on it
- park: keep the candidate, but do not feed foreground recall

The router is deterministic. It never calls a model and never promotes anything
to formal memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc
from aippocampus_runtime.dream.constructive_outputs import (
    prospective_invitation_block_reason,
    prospective_invitation_match_use,
)
from aippocampus_runtime.navigation.associations import (
    extract_terms_from_text,
    normalize_term,
    source_text_is_noise,
    term_is_noise,
)
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.registry.api import registry_paths, unique_preserve
from aippocampus_runtime.subconscious import match_terms

ROUTER_SCHEMA_VERSION = 1
DEFAULT_CANDIDATES_NAME = "promotion_candidates.jsonl"
DEFAULT_JOBS_NAME = "subconscious_jobs.jsonl"
DEFAULT_WORKING_MEMORY_NAME = "working_memory.jsonl"
DEFAULT_SUMMARY_NAME = "working_memory_summary.json"

USE_SILENTLY = "use_silently"
USE_WITH_SOURCE = "use_with_source"
CONFIRM_WHEN_RELEVANT = "confirm_when_relevant"
PARK = "park"
ACTIVE_ROUTES = {USE_SILENTLY, USE_WITH_SOURCE, CONFIRM_WHEN_RELEVANT}
DREAM_HYPOTHESIS_TYPE = "dream_hypothesis"

LOW_RISK_TYPES = {"concept_edge", "hook_trigger"}
PROJECT_FACT_TYPES = {"project_memory"}
PREFERENCE_TYPES = {"preference_review"}
REVIEW_TYPES = {"contradiction_review"}
QUESTION_SILENT_TYPES = {"question_candidate", "theme_candidate"}
QUESTION_LINK_TYPES = {"question_link"}
FRONTIER_TYPES = {"frontier_marker"}
PARK_TYPES = {"archive", "dedup_review"}

GENERIC_TRIGGER_TERMS = {
    "user",
    "project",
    "memory",
    "candidate",
    "preference",
    "review",
    "source",
    "agent",
    "app",
    "系统",
    "项目",
    "记忆",
    "候选",
    "偏好",
    "用户",
    "dashboard",
    "button",
    "buttons",
    "hover",
    "style",
    "styles",
    "test",
    "tests",
    "implement",
    "maintain",
    # Single generic action nouns should not wake a high-risk working-memory
    # item by themselves. Specific terms in the same row, such as a tool name or
    # consent gate phrase, remain enough to match.
    "flow",
    "mutation",
    "mutations",
    "按钮",
    "样式",
    "测试",
}


def activation_cues_for(candidate: dict[str, Any], *, limit: int = 12) -> list[str]:
    cues: list[str] = []
    for value in candidate.get("activation_cues") or []:
        cue = normalize_term(str(value or ""))
        if not cue or len(cue) > 96:
            continue
        if term_is_noise(cue) or source_text_is_noise(cue):
            continue
        cues.append(cue)
    return unique_preserve(cues, limit=limit)


def activation_cue_terms_for(candidate: dict[str, Any], *, limit: int = 18) -> list[str]:
    return unique_preserve(activation_cues_for(candidate, limit=limit), limit=limit)


def default_candidates_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_CANDIDATES_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_CANDIDATES_NAME


def default_jobs_path(registry_path: Path | None = None, registry_dir: Path | None = None) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_JOBS_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_JOBS_NAME


def default_working_memory_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_WORKING_MEMORY_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_WORKING_MEMORY_NAME


def default_summary_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_SUMMARY_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_SUMMARY_NAME


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    tmp.replace(path)


def candidate_key(candidate: dict[str, Any]) -> str:
    source_ids = "|".join(sorted(str(value) for value in candidate.get("source_finding_ids") or []))
    raw = "\n".join(
        [
            str(candidate.get("candidate_type") or ""),
            normalize_term(str(candidate.get("title") or "")).casefold(),
            normalize_term(str(candidate.get("summary") or "")).casefold(),
            source_ids,
        ]
    )
    return "wm_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:18]


def load_candidates(path: Path) -> list[dict[str, Any]]:
    return [row for row in iter_jsonl(path) if row.get("kind") == "aippocampus_promotion_candidate"]


def load_findings_by_id(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in iter_jsonl(path):
        if row.get("kind") != "aippocampus_subconscious_job_finding":
            continue
        key = str(row.get("fingerprint") or "")
        if key:
            out[key] = row
    return out


def load_thread_projects(path: Path) -> dict[str, str]:
    registry_path = path.parent / "threads.json"
    if not registry_path.exists():
        return {}
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, str] = {}
    for entry in data.get("threads") or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("thread_key") or "")
        label = str(entry.get("project_label") or entry.get("workspace_name") or "")
        if key and label:
            out[key] = label
    return out


def merged_source_refs(
    candidate: dict[str, Any],
    findings_by_id: dict[str, dict[str, Any]],
    thread_projects: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    refs.extend(ref for ref in candidate.get("source_refs") or [] if isinstance(ref, dict))
    for finding_id in candidate.get("source_finding_ids") or []:
        finding = findings_by_id.get(str(finding_id))
        if not finding:
            continue
        refs.extend(ref for ref in finding.get("source_refs") or [] if isinstance(ref, dict))
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for ref in refs:
        line = (
            ref.get("source_line")
            or ref.get("assistant_line")
            or ref.get("user_line")
            or ref.get("line")
        )
        thread_key = ref.get("thread_key")
        clean = {
            "thread_key": thread_key,
            "title": ref.get("title"),
            "project_label": ref.get("project_label")
            or (thread_projects or {}).get(str(thread_key or "")),
            "turn_index": ref.get("turn_index"),
            "line": line,
            "message_id": ref.get("message_id"),
        }
        key = (
            str(clean.get("thread_key") or ""),
            str(clean.get("line") or ""),
            str(clean.get("message_id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append({k: v for k, v in clean.items() if v not in {None, ""}})
    return out[:12]


def project_label_from_refs(refs: list[dict[str, Any]]) -> str | None:
    labels = unique_preserve(
        [str(ref.get("project_label") or "") for ref in refs if ref.get("project_label")], limit=3
    )
    return labels[0] if len(labels) == 1 else None


def concepts_from_findings(
    candidate: dict[str, Any], findings_by_id: dict[str, dict[str, Any]]
) -> list[str]:
    values: list[str] = []
    for finding_id in candidate.get("source_finding_ids") or []:
        finding = findings_by_id.get(str(finding_id))
        if not finding:
            continue
        values.extend(str(value) for value in finding.get("concepts") or [])
        for key in ("src", "dst"):
            if finding.get(key):
                values.append(str(finding.get(key)))
        for key in ("question_text", "question_short", "linked_question_short", "theme_label"):
            if finding.get(key):
                values.append(str(finding.get(key)))
        for question in finding.get("linked_questions") or []:
            if isinstance(question, dict):
                values.append(str(question.get("question_short") or ""))
                values.append(str(question.get("question_text") or ""))
    return unique_preserve(
        [normalize_term(value) for value in values if normalize_term(value)], limit=18
    )


def source_strength(candidate: dict[str, Any], refs: list[dict[str, Any]]) -> dict[str, Any]:
    source_threads = {str(ref.get("thread_key") or "") for ref in refs if ref.get("thread_key")}
    source_lines = [ref for ref in refs if ref.get("line")]
    source_finding_count = len(candidate.get("source_finding_ids") or [])
    score = min(
        1.0,
        0.45 * min(1.0, len(refs) / 3)
        + 0.35 * min(1.0, len(source_threads) / 2)
        + 0.20 * min(1.0, source_finding_count / 2),
    )
    return {
        "score": round(score, 4),
        "source_ref_count": len(refs),
        "source_thread_count": len(source_threads),
        "source_line_count": len(source_lines),
        "source_finding_count": source_finding_count,
    }


def route_candidate(candidate: dict[str, Any], strength: dict[str, Any]) -> tuple[str, str, str]:
    candidate_type = str(candidate.get("candidate_type") or "project_memory")
    confidence = float(candidate.get("confidence") or 0.0)
    ref_count = int(strength.get("source_ref_count") or 0)
    thread_count = int(strength.get("source_thread_count") or 0)
    if ref_count <= 0 or confidence < 0.45:
        return PARK, "high", "insufficient source support or low confidence"
    if candidate_type in PARK_TYPES:
        return PARK, "medium", f"{candidate_type} is not foreground recall material"
    if candidate_type in QUESTION_LINK_TYPES:
        if confidence >= 0.65 and ref_count >= 2:
            return (
                USE_WITH_SOURCE,
                "medium",
                "recurring question scent is useful with source refs when the prompt is relevant",
            )
        if confidence >= 0.55:
            return USE_SILENTLY, "low", "weak question link can help recall/rerank silently"
        return PARK, "low", "question link candidate too weak"
    if candidate_type in QUESTION_SILENT_TYPES:
        if confidence >= 0.55:
            return USE_SILENTLY, "low", "question/theme candidates are ambient navigation scent"
        return PARK, "low", f"{candidate_type} candidate too weak"
    if candidate_type in FRONTIER_TYPES:
        if confidence >= 0.60:
            return (
                USE_SILENTLY,
                "medium",
                "frontier markers stay quiet unless current prompt matches unresolved edges",
            )
        return PARK, "medium", "frontier marker candidate too weak"
    if candidate_type in REVIEW_TYPES:
        if confidence >= 0.55:
            return (
                CONFIRM_WHEN_RELEVANT,
                "high",
                "tension or contradiction should only interrupt when a current action depends on it",
            )
        return PARK, "high", "weak contradiction candidate"
    if candidate_type in PREFERENCE_TYPES:
        if confidence >= 0.85 and ref_count >= 3 and thread_count >= 2:
            return (
                USE_WITH_SOURCE,
                "medium",
                "well-supported preference; use as current working hypothesis, not permanent identity",
            )
        if confidence >= 0.65:
            return (
                CONFIRM_WHEN_RELEVANT,
                "high",
                "personal preference may drift, so confirm only when relevant",
            )
        return PARK, "high", "preference candidate too weak"
    if candidate_type in PROJECT_FACT_TYPES:
        if confidence >= 0.75 and ref_count >= 1:
            return (
                USE_WITH_SOURCE,
                "medium",
                "project fact is useful as source-backed working memory",
            )
        if confidence >= 0.60:
            return (
                CONFIRM_WHEN_RELEVANT,
                "medium",
                "project direction candidate needs relevant-situation confirmation",
            )
        return PARK, "medium", "project candidate too weak"
    if candidate_type in LOW_RISK_TYPES:
        if confidence >= 0.70:
            return USE_SILENTLY, "low", "low-risk recall/rerank helper"
        return PARK, "low", "low-risk candidate below confidence threshold"
    if confidence >= 0.80 and float(strength.get("score") or 0.0) >= 0.55:
        return USE_WITH_SOURCE, "medium", "strong generic candidate with source support"
    return PARK, "medium", "default conservative route"


def ask_policy_for(route: str) -> str:
    if route == USE_SILENTLY:
        return "never_ask; use only for recall/rerank and trigger expansion"
    if route == USE_WITH_SOURCE:
        return "do_not_ask_unless_contradicted_or_action_depends_on_uncertain_scope"
    if route == CONFIRM_WHEN_RELEVANT:
        return "ask_only_when_current_action_would_depend_on_this_or_sources_conflict"
    return "do_not_use_in_foreground"


def trigger_terms_for(
    candidate: dict[str, Any], concepts: list[str], project_label: str | None
) -> list[str]:
    activation_terms = activation_cue_terms_for(candidate, limit=18)
    if activation_terms:
        # When the subconscious/model layer authored activation cues, those cues
        # are the prompt-side route surface. Falling back to title/summary prose
        # here reintroduces broad lexical triggers and makes semantic judgment
        # look deterministic while hiding that it was guessed from prose.
        return activation_terms
    text = "\n".join(
        [
            str(candidate.get("title") or ""),
            str(candidate.get("summary") or ""),
            str(candidate.get("recommendation") or ""),
            " ".join(concepts),
        ]
    )
    terms = extract_terms_from_text(text, limit=24) + split_query_terms([text])
    out: list[str] = []
    project_low = (project_label or "").casefold()
    for term in terms:
        term = normalize_term(term)
        low = term.casefold()
        if not term or term_is_noise(term) or source_text_is_noise(term):
            continue
        if low in GENERIC_TRIGGER_TERMS or (project_low and low == project_low):
            continue
        if len(term) > 60:
            continue
        out.append(term)
    return unique_preserve(out, limit=18)


def route_entry(
    candidate: dict[str, Any],
    findings_by_id: dict[str, dict[str, Any]],
    thread_projects: dict[str, str] | None = None,
) -> dict[str, Any]:
    refs = merged_source_refs(candidate, findings_by_id, thread_projects)
    concepts = concepts_from_findings(candidate, findings_by_id)
    project_label = project_label_from_refs(refs)
    strength = source_strength(candidate, refs)
    route, risk, reason = route_candidate(candidate, strength)
    active = route in ACTIVE_ROUTES
    return {
        "schema_version": ROUTER_SCHEMA_VERSION,
        "kind": "aippocampus_working_memory",
        "created_at": now_utc(),
        "status": "active" if active else "parked",
        "route": route,
        "ask_policy": ask_policy_for(route),
        "risk": risk,
        "route_reason": reason,
        "candidate_key": candidate_key(candidate),
        "candidate_type": str(candidate.get("candidate_type") or "project_memory"),
        "title": compact_text(str(candidate.get("title") or ""), 180),
        "summary": compact_text(str(candidate.get("summary") or ""), 760),
        "recommendation": compact_text(str(candidate.get("recommendation") or ""), 420),
        "confidence": round(float(candidate.get("confidence") or 0.0), 4),
        "project_label": project_label,
        "trigger_terms": trigger_terms_for(candidate, concepts, project_label),
        "activation_cues": activation_cues_for(candidate),
        "concepts": concepts,
        "source_finding_ids": unique_preserve(
            [str(value) for value in candidate.get("source_finding_ids") or []], limit=12
        ),
        "source_refs": refs[:8],
        "source_strength": strength,
        "source_candidate_batch_id": candidate.get("batch_id"),
        "source_candidate_created_at": candidate.get("created_at"),
    }


def better_entry(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    a_rank = (
        a.get("status") == "active",
        float(a.get("confidence") or 0.0),
        float((a.get("source_strength") or {}).get("score") or 0.0),
        str(a.get("source_candidate_created_at") or ""),
    )
    b_rank = (
        b.get("status") == "active",
        float(b.get("confidence") or 0.0),
        float((b.get("source_strength") or {}).get("score") or 0.0),
        str(b.get("source_candidate_created_at") or ""),
    )
    return a if a_rank >= b_rank else b


def route_candidates(candidates_path: Path, jobs_path: Path) -> dict[str, Any]:
    findings_by_id = load_findings_by_id(jobs_path)
    thread_projects = load_thread_projects(candidates_path)
    routed_by_key: dict[str, dict[str, Any]] = {}
    for candidate in load_candidates(candidates_path):
        entry = route_entry(candidate, findings_by_id, thread_projects)
        key = entry["candidate_key"]
        if key in routed_by_key:
            routed_by_key[key] = better_entry(routed_by_key[key], entry)
        else:
            routed_by_key[key] = entry
    rows = sorted(
        routed_by_key.values(),
        key=lambda item: (
            item.get("status") == "active",
            item.get("route") != PARK,
            float(item.get("confidence") or 0.0),
            float((item.get("source_strength") or {}).get("score") or 0.0),
            str(item.get("source_candidate_created_at") or ""),
        ),
        reverse=True,
    )
    route_counts = Counter(str(row.get("route") or "") for row in rows)
    active_count = sum(1 for row in rows if row.get("status") == "active")
    return {
        "schema_version": ROUTER_SCHEMA_VERSION,
        "kind": "aippocampus_working_memory_routing",
        "created_at": now_utc(),
        "source_candidates": str(candidates_path),
        "source_jobs": str(jobs_path),
        "candidate_count": len(load_candidates(candidates_path)),
        "working_memory_count": len(rows),
        "active_count": active_count,
        "route_counts": dict(route_counts),
        "rows": rows,
    }


def load_working_memory(path: Path) -> list[dict[str, Any]]:
    return [row for row in iter_jsonl(path) if row.get("kind") == "aippocampus_working_memory"]


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None


def dream_horizon_timestamps(row: dict[str, Any], key: str) -> list[datetime]:
    horizon = row.get("trust_horizon") or {}
    invitation = row.get("prospective_invitation") or {}
    values = (
        row.get(key),
        horizon.get(key) if isinstance(horizon, dict) else None,
        invitation.get(key) if isinstance(invitation, dict) else None,
    )
    return [parsed for value in values if (parsed := parse_utc(str(value or "")))]


def dream_hypothesis_block_reason(row: dict[str, Any]) -> str:
    if row.get("candidate_type") != DREAM_HYPOTHESIS_TYPE:
        return ""
    if str(row.get("review_state") or "") not in (
        "accepted", "approved", "reviewed", "agent_adjudicated", "auto_adjudicated", "source_adjudicated"
    ):
        return "not_adjudicated"
    if (row.get("sensitive_use_gate") or {}).get("state") == "blocked" or row.get("human_review_required"):
        return "sensitive_review_required"
    now = datetime.now(timezone.utc)
    for key, reason in (
        ("expires_at", "dream_hypothesis_expired"),
        ("review_after", "trust_horizon_review_due"),
    ):
        if any(timestamp <= now for timestamp in dream_horizon_timestamps(row, key)):
            return reason
    invitation_block_reason = prospective_invitation_block_reason(row)
    if invitation_block_reason:
        return invitation_block_reason
    return ""


def match_working_memory(
    prompt: str,
    rows: list[dict[str, Any]],
    *,
    project_label: str | None = None,
    limit: int = 4,
) -> list[dict[str, Any]]:
    prompt_low = prompt.casefold()
    prompt_parts = match_terms.prompt_parts_for(prompt, generic_terms=GENERIC_TRIGGER_TERMS)
    matches: list[dict[str, Any]] = []
    for row in rows:
        if row.get("status") != "active" or row.get("route") not in ACTIVE_ROUTES:
            continue
        row_project = row.get("project_label")
        if (
            row_project
            and project_label
            and str(row_project).casefold() != project_label.casefold()
        ):
            continue
        if row_project and not project_label and str(row_project).casefold() not in prompt_low:
            continue
        matched: list[str] = []
        for term in row.get("trigger_terms") or []:
            if match_terms.trigger_matches_prompt(
                str(term),
                prompt_low=prompt_low,
                prompt_parts=prompt_parts,
                generic_terms=GENERIC_TRIGGER_TERMS,
                project_label=str(row_project or ""),
            ):
                matched.append(str(term))
        if not matched:
            continue
        if row.get("candidate_type") == DREAM_HYPOTHESIS_TYPE:
            block_reason = dream_hypothesis_block_reason(row)
            if block_reason:
                continue
        route_bonus = {USE_SILENTLY: 0.5, USE_WITH_SOURCE: 1.5, CONFIRM_WHEN_RELEVANT: 1.0}.get(
            str(row.get("route")), 0.0
        )
        score = min(
            20.0, len(matched) * 2.0 + float(row.get("confidence") or 0.0) * 6.0 + route_bonus
        )
        copy = dict(row)
        copy["matched_terms"] = unique_preserve(matched, limit=8)
        copy["score"] = round(score, 3)
        if copy.get("candidate_type") == DREAM_HYPOTHESIS_TYPE:
            invitation_use = prospective_invitation_match_use(copy)
            if invitation_use:
                copy["dream_hypothesis_use"] = invitation_use
                matches.append(copy)
                continue
            copy["dream_hypothesis_use"] = {
                "action": "use_quietly",
                "reason": "matched_working_memory_terms",
                "truth_boundary": copy.get("truth_boundary"),
                "strong_claim_requires_source_reopen": bool(
                    (copy.get("foreground_use") or {}).get("strong_claim_requires_source_reopen")
                ),
                "render_boundary": "dream_hypothesis_not_source_fact",
            }
        matches.append(copy)
    matches.sort(
        key=lambda item: (
            float(item.get("score") or 0.0),
            float(item.get("confidence") or 0.0),
            str(item.get("source_candidate_created_at") or ""),
        ),
        reverse=True,
    )
    return matches[:limit]


def strip_for_hook(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "route": row.get("route"),
                "ask_policy": row.get("ask_policy"),
                "risk": row.get("risk"),
                "candidate_key": row.get("candidate_key"),
                "candidate_type": row.get("candidate_type"),
                "title": row.get("title"),
                "summary": row.get("summary"),
                "recommendation": row.get("recommendation"),
                "confidence": row.get("confidence"),
                "project_label": row.get("project_label"),
                "matched_terms": row.get("matched_terms") or [],
                "source_finding_ids": row.get("source_finding_ids") or [],
                "source_refs": row.get("source_refs") or [],
                "score": row.get("score"),
                "truth_boundary": row.get("truth_boundary"),
                "dream_function": row.get("dream_function"),
                "foreground_use": row.get("foreground_use"),
                "sensitive_use_gate": row.get("sensitive_use_gate"),
                "dream_hypothesis_use": row.get("dream_hypothesis_use"),
                "constructive_artifact": row.get("constructive_artifact"),
                "prospective_invitation": row.get("prospective_invitation"),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry-dir")
    parser.add_argument("--registry")
    parser.add_argument("--candidates")
    parser.add_argument("--jobs")
    parser.add_argument("--output")
    parser.add_argument("--summary")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    registry_path = Path(args.registry).resolve() if args.registry else None
    registry_dir = Path(args.registry_dir).resolve() if args.registry_dir else None
    candidates = (
        Path(args.candidates).resolve()
        if args.candidates
        else default_candidates_path(registry_path, registry_dir)
    )
    jobs = (
        Path(args.jobs).resolve() if args.jobs else default_jobs_path(registry_path, registry_dir)
    )
    output = (
        Path(args.output).resolve()
        if args.output
        else default_working_memory_path(registry_path, registry_dir)
    )
    summary_path = (
        Path(args.summary).resolve()
        if args.summary
        else default_summary_path(registry_path, registry_dir)
    )
    result = route_candidates(candidates, jobs)
    rows = result.pop("rows")
    if not args.no_write:
        write_jsonl(output, rows)
        write_json(summary_path, {**result, "output": str(output), "summary": str(summary_path)})
    result = {**result, "output": str(output), "summary": str(summary_path)}
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"working memory: {output}")
        print(f"candidates: {result['candidate_count']}")
        print(f"active: {result['active_count']}")
        print(f"routes: {result['route_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
