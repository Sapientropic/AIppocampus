#!/usr/bin/env python3
"""Project adjudicated dream findings onto soft working memory.

Dream synthesis and foreground recall delivery have different risk profiles.
This helper keeps the post-adjudication bridge small and explicit: raw dream
rows do not leave the holding queue, while background-adjudicated hypotheses
reuse the existing working-memory substrate instead of adding a parallel dream
channel or forcing the user to approve every dream.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampuslib import compact_text, now_utc
from memory_candidate_router import USE_WITH_SOURCE, ask_policy_for, trigger_terms_for

SCHEMA_VERSION = 1
DREAM_FINDING_KIND = "dream_synthesized"
WORKING_MEMORY_KIND = "aippocampus_working_memory"
DREAM_HYPOTHESIS_TYPE = "dream_hypothesis"
ADJUDICATED_REVIEW_STATES = {
    "accepted",
    "approved",
    "reviewed",
    "agent_adjudicated",
    "auto_adjudicated",
    "source_adjudicated",
}
ADJUDICATED_DREAM_DOWNSTREAM_USES = {
    "working_memory",
    "ambient_recall_card",
    "reflection_space",
}
LOW_SIGNAL_TERMS = {
    "question",
    "candidate",
    "thread",
    "source",
    "summary",
    "user",
    "work",
    "project",
}


def stable_digest(*parts: object, prefix: str, length: int = 16) -> str:
    raw = "\n".join(json.dumps(part, sort_keys=True, default=str) for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8', errors='replace')).hexdigest()[:length]}"


def is_present(value: object) -> bool:
    return value is not None and value != ""


def unique_preserve(values: Iterable[object], *, limit: int = 12) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = compact_text(str(value or ""), 90)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def text_terms(text: str) -> list[str]:
    terms = [
        token.casefold()
        for token in re.findall(r"[\w\u4e00-\u9fff]+", text, flags=re.UNICODE)
        if len(token) >= 3
    ]
    return [term for term in terms if term not in LOW_SIGNAL_TERMS]


def source_ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(ref.get("thread_key") or ref.get("thread_id") or ""),
        str(ref.get("message_id") or ""),
        str(ref.get("turn_id") or ""),
        str(
            ref.get("source_id")
            or ref.get("source_line")
            or ref.get("line")
            or ref.get("source_ref")
            or ""
        ),
    )


def normalize_source_refs(value: object) -> tuple[dict[str, Any], ...]:
    if isinstance(value, Mapping):
        raw_items: Iterable[object] = [value]
    elif isinstance(value, (list, tuple)):
        raw_items = value
    else:
        raw_items = []

    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        ref = dict(item)
        key = source_ref_key(ref)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        refs.append({k: v for k, v in ref.items() if is_present(v)})
    return tuple(refs)


def project_label_from_refs(refs: Iterable[Mapping[str, Any]]) -> str | None:
    labels = unique_preserve(
        [str(ref.get("project_label") or "") for ref in refs if ref.get("project_label")],
        limit=3,
    )
    return labels[0] if len(labels) == 1 else None


def clean_working_memory_refs(
    refs: Iterable[Mapping[str, Any]], *, limit: int = 8
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for ref in refs:
        line = (
            ref.get("source_line")
            or ref.get("assistant_line")
            or ref.get("user_line")
            or ref.get("line")
        )
        clean = {
            "thread_key": ref.get("thread_key") or ref.get("thread_id"),
            "title": ref.get("title"),
            "project_label": ref.get("project_label"),
            "turn_index": ref.get("turn_index"),
            "line": line,
            "message_id": ref.get("message_id"),
        }
        key = (
            str(clean.get("thread_key") or ""),
            str(clean.get("line") or ""),
            str(clean.get("message_id") or ""),
        )
        if not any(key) or key in seen:
            continue
        seen.add(key)
        out.append({k: v for k, v in clean.items() if is_present(v)})
        if len(out) >= limit:
            break
    return out


def adjudicated_dream_downstream_use(finding: Mapping[str, Any]) -> list[str]:
    requested = [
        str(item)
        for item in finding.get("downstream_use") or []
        if str(item) in ADJUDICATED_DREAM_DOWNSTREAM_USES
    ]
    return unique_preserve(requested or ["working_memory"], limit=3)


def adjudicated_dream_is_eligible(finding: Mapping[str, Any]) -> bool:
    if finding.get("finding_kind") != DREAM_FINDING_KIND:
        return False
    if str(finding.get("review_state") or "") not in ADJUDICATED_REVIEW_STATES:
        return False
    refs = normalize_source_refs(finding.get("source_refs"))
    if not refs:
        return False
    audit = finding.get("source_ref_audit") or {}
    if isinstance(audit, Mapping) and audit.get("status") == "failed":
        return False
    return True


def adjudicated_dream_findings_to_working_memory(
    findings: Iterable[Mapping[str, Any]],
    *,
    max_rows: int = 20,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for finding in findings:
        if len(rows) >= max_rows:
            break
        if not adjudicated_dream_is_eligible(finding):
            continue
        refs = clean_working_memory_refs(finding.get("source_refs") or [])
        if not refs:
            continue
        bridge_claims = [
            str(item.get("claim") or "")
            for item in finding.get("bridge_claims") or []
            if isinstance(item, Mapping)
        ]
        title = compact_text(str(finding.get("title") or "Adjudicated dream hypothesis"), 180)
        summary = compact_text(str(finding.get("summary") or ""), 760)
        project_label = project_label_from_refs(refs)
        source_finding_id = str(
            finding.get("dream_finding_id")
            or finding.get("fingerprint")
            or stable_digest(finding, prefix="dreamfinding", length=18)
        )
        concepts = unique_preserve(
            [
                str(finding.get("dream_function") or ""),
                str(finding.get("compensatory_kind") or ""),
                *text_terms(" ".join([title, summary, " ".join(bridge_claims)])),
            ],
            limit=18,
        )
        candidate = {
            "candidate_type": DREAM_HYPOTHESIS_TYPE,
            "title": title,
            "summary": summary,
            "recommendation": (
                "Use as an adjudicated dream hypothesis only when it changes the current answer; "
                "re-open clean source before factual claims."
            ),
        }
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": WORKING_MEMORY_KIND,
                "created_at": now_utc(),
                "status": "active",
                "route": USE_WITH_SOURCE,
                "ask_policy": ask_policy_for(USE_WITH_SOURCE),
                "risk": "medium",
                "route_reason": "adjudicated dream hypothesis with source refs can seed recall/reflection, but remains non-factual",
                "candidate_key": stable_digest(candidate, source_finding_id, prefix="wm_dream", length=18),
                "candidate_type": DREAM_HYPOTHESIS_TYPE,
                "title": title,
                "summary": summary,
                "recommendation": candidate["recommendation"],
                "confidence": round(float(finding.get("confidence") or 0.62), 4),
                "project_label": project_label,
                "trigger_terms": trigger_terms_for(candidate, concepts, project_label),
                "concepts": concepts,
                "source_finding_ids": [source_finding_id],
                "source_refs": refs,
                "source_strength": {
                    "score": 1.0 if len(refs) >= 2 else 0.75,
                    "source_ref_count": len(refs),
                    "source_thread_count": len({str(ref.get("thread_key") or "") for ref in refs}),
                    "source_line_count": sum(1 for ref in refs if ref.get("line")),
                    "source_finding_count": 1,
                },
                "source_candidate_batch_id": finding.get("batch_id"),
                "source_candidate_created_at": finding.get("created_at"),
                "review_state": finding.get("review_state"),
                "adjudication_source": finding.get("adjudication_source")
                or "background_dream_adjudication",
                "dream_function": finding.get("dream_function"),
                "dream_phase": finding.get("dream_phase"),
                "compensatory_kind": finding.get("compensatory_kind"),
                "downstream_use": adjudicated_dream_downstream_use(finding),
                "truth_boundary": "adjudicated_dream_hypothesis_not_fact",
                "human_review_required": bool(finding.get("human_review_required") or False),
                "formal_memory_eligible": False,
                "clean_source_mutation": False,
            }
        )
    return rows


def reviewed_dream_findings_to_working_memory(
    findings: Iterable[Mapping[str, Any]],
    *,
    max_rows: int = 20,
) -> list[dict[str, Any]]:
    return adjudicated_dream_findings_to_working_memory(findings, max_rows=max_rows)
