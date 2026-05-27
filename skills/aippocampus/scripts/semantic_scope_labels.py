"""Dynamic semantic scope-label sidecar helpers.

The clean-source builder intentionally keeps deterministic labels conservative.
Fuzzy judgments such as metaphors, pivots, dissatisfaction, or excitement belong
to the background semantic layer, typically DeepSeek/subconscious jobs. This
module only validates and merges those source-backed sidecar labels; it never
infers them from text.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from aippocampuslib import compact_text
from build_clean_source import SCOPE_LABEL_ORDER

SEMANTIC_SCOPE_LABELS_FILENAME = "semantic-scope-labels.jsonl"
SEMANTIC_SCOPE_LABEL_FINDING_KIND = "semantic_scope_labels"
SEMANTIC_SCOPE_LABEL_JOB = "semantic_scope_labeling"
DEFAULT_SEMANTIC_SCOPE_LABEL_SOURCE = "deepseek_subconscious_scope_labels"
DEFAULT_SEMANTIC_SCOPE_LABEL_BOUNDARY = (
    "Navigation hint only; clean source text remains the memory truth."
)
SOURCE_REVIEW_FRAGILE_LABELS = {
    "personal_reflection",
    "relationship_continuity",
    "reading_notes",
    "idea_seed",
    "preference",
    "life_context",
    "technical_work",
    "open_question",
}
DEFAULT_LABEL_EVIDENCE_MIN_CONFIDENCE = 0.65
SOURCE_REVIEW_FRAGILE_LABEL_MIN_CONFIDENCE = {
    "personal_reflection": 0.82,
    "relationship_continuity": 0.96,
    "life_context": 0.93,
    "open_question": 0.93,
    "reading_notes": 0.9,
    "idea_seed": 0.82,
    "preference": 0.9,
    "technical_work": 0.8,
}


def canonical_scope_labels(values: list[Any]) -> list[str]:
    present = {str(value) for value in values if isinstance(value, str)}
    return [label for label in SCOPE_LABEL_ORDER if label in present]


def label_evidence_map(
    item: dict[str, Any], *, fallback_confidence: float | None = None
) -> dict[str, dict[str, Any]]:
    raw_evidence = (
        item.get("label_evidence")
        or item.get("label_support")
        or item.get("label_rationales")
        or {}
    )
    label_confidences = (
        item.get("label_confidences") if isinstance(item.get("label_confidences"), dict) else {}
    )
    out: dict[str, dict[str, Any]] = {}

    def add(label_value: Any, reason_value: Any = "", confidence_value: Any = None) -> None:
        label = str(label_value or "").strip()
        if label not in SCOPE_LABEL_ORDER:
            return
        reason = compact_text(str(reason_value or ""), 180)
        confidence = clamp_confidence(confidence_value)
        if confidence <= 0.0 and fallback_confidence is not None:
            confidence = clamp_confidence(fallback_confidence)
        if confidence <= 0.0 and label in label_confidences:
            confidence = clamp_confidence(label_confidences.get(label))
        out[label] = {
            "label": label,
            "reason": reason,
            "confidence": round(confidence, 4),
        }

    if isinstance(raw_evidence, list):
        for entry in raw_evidence:
            if not isinstance(entry, dict):
                continue
            add(
                entry.get("label"),
                entry.get("reason")
                or entry.get("rationale")
                or entry.get("summary")
                or entry.get("why")
                or entry.get("evidence"),
                entry.get("confidence"),
            )
    elif isinstance(raw_evidence, dict):
        for label, value in raw_evidence.items():
            if isinstance(value, dict):
                add(
                    label,
                    value.get("reason")
                    or value.get("rationale")
                    or value.get("summary")
                    or value.get("why")
                    or value.get("evidence"),
                    value.get("confidence"),
                )
            else:
                add(label, value, label_confidences.get(str(label)))

    for label, confidence in label_confidences.items():
        if label not in out:
            add(label, "", confidence)
    return out


def filtered_semantic_scope_labels(
    item: dict[str, Any], labels: list[Any] | None = None
) -> list[str]:
    canonical = canonical_scope_labels(
        list(labels if labels is not None else item.get("scope_labels") or item.get("labels") or [])
    )
    evidence = label_evidence_map(item)
    kept: list[str] = []
    for label in canonical:
        if not label_evidence_is_sufficient(label, evidence.get(label)):
            continue
        kept.append(label)
    return canonical_scope_labels(kept)


def label_evidence_min_confidence(label: str) -> float:
    return SOURCE_REVIEW_FRAGILE_LABEL_MIN_CONFIDENCE.get(
        label, DEFAULT_LABEL_EVIDENCE_MIN_CONFIDENCE
    )


def label_evidence_is_sufficient(label: str, evidence: dict[str, Any] | None) -> bool:
    if not evidence:
        return False
    if not str(evidence.get("reason") or "").strip():
        return False
    return float(evidence.get("confidence") or 0.0) >= label_evidence_min_confidence(label)


def label_evidence_for_labels(item: dict[str, Any], labels: list[str]) -> list[dict[str, Any]]:
    evidence = label_evidence_map(item)
    return [
        evidence[label]
        for label in labels
        if label in evidence and label_evidence_is_sufficient(label, evidence[label])
    ]


def load_semantic_scope_labels(clean_source_dir: Path) -> dict[str, dict[str, Any]]:
    path = clean_source_dir / SEMANTIC_SCOPE_LABELS_FILENAME
    if not path.exists():
        return {}
    messages_by_id = clean_messages_by_id(clean_source_dir)
    by_message_id: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            message_id = str(item.get("message_id") or item.get("id") or "").strip()
            if messages_by_id and message_id not in messages_by_id:
                continue
            if not message_id:
                continue
            confidence = clamp_confidence(item.get("confidence"))
            if confidence < 0.45:
                continue
            labels = filtered_semantic_scope_labels(item, list(item.get("scope_labels") or []))
            if not labels:
                continue
            if not matching_source_refs(item, message_id):
                continue
            by_message_id[message_id] = {
                **item,
                "message_id": message_id,
                "scope_labels": labels,
                "confidence": round(confidence, 4),
                "label_evidence": label_evidence_for_labels(item, labels),
            }
    return by_message_id


def semantic_labels_for_message(
    message: dict[str, Any], sidecar: dict[str, dict[str, Any]]
) -> list[str]:
    message_id = str(message.get("message_id") or message.get("id") or "").strip()
    item = sidecar.get(message_id) or {}
    return list(item.get("scope_labels") or [])


def merged_scope_labels(base_labels: list[Any], semantic_labels: list[Any]) -> list[str]:
    return canonical_scope_labels([*base_labels, *semantic_labels])


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def clean_messages_by_id(clean_source_dir: Path) -> dict[str, dict[str, Any]]:
    messages_path = clean_source_dir / "messages.jsonl"
    return {
        str(item.get("message_id") or item.get("id")): item
        for item in iter_jsonl(messages_path)
        if item.get("message_id") or item.get("id")
    }


def is_semantic_scope_label_finding(item: dict[str, Any]) -> bool:
    finding_kind = str(item.get("finding_kind") or item.get("kind") or "").strip()
    job = str(item.get("job") or "").strip()
    return finding_kind == SEMANTIC_SCOPE_LABEL_FINDING_KIND or job == SEMANTIC_SCOPE_LABEL_JOB


def clamp_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def matching_source_refs(item: dict[str, Any], message_id: str) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref in item.get("source_refs") or []:
        if not isinstance(ref, dict):
            continue
        if str(ref.get("message_id") or "").strip() != message_id:
            continue
        refs.append(
            {
                "ref": ref.get("ref"),
                "turn_ref": ref.get("turn_ref"),
                "thread_key": ref.get("thread_key"),
                "message_id": ref.get("message_id"),
                "turn_id": ref.get("turn_id"),
                "source_line": ref.get("source_line"),
                "role": ref.get("role"),
                "phase": ref.get("phase") or "",
            }
        )
    return refs[:5]


def semantic_scope_label_row_from_finding(
    item: dict[str, Any],
    messages_by_id: dict[str, dict[str, Any]],
    *,
    min_confidence: float = 0.45,
) -> dict[str, Any] | None:
    if not is_semantic_scope_label_finding(item):
        return None
    message_id = str(item.get("message_id") or "").strip()
    if not message_id or message_id not in messages_by_id:
        return None
    labels = filtered_semantic_scope_labels(
        item, list(item.get("scope_labels") or item.get("labels") or [])
    )
    if not labels:
        return None
    confidence = clamp_confidence(item.get("confidence"))
    if confidence < min_confidence:
        return None
    source_refs = matching_source_refs(item, message_id)
    if not source_refs:
        return None
    message = messages_by_id[message_id]
    return {
        "message_id": message_id,
        "turn_id": message.get("turn_id") or item.get("turn_id"),
        "source": DEFAULT_SEMANTIC_SCOPE_LABEL_SOURCE,
        "source_job": item.get("source") or "deepseek_subconscious_jobs",
        "scope_labels": labels,
        "confidence": round(confidence, 4),
        "source_refs": source_refs,
        "label_evidence": label_evidence_for_labels(item, labels),
        "rationale": compact_text(
            str(item.get("rationale") or item.get("summary") or item.get("why") or ""), 260
        ),
        "boundary": DEFAULT_SEMANTIC_SCOPE_LABEL_BOUNDARY,
    }


def semantic_scope_label_rows_from_findings(
    findings: list[dict[str, Any]],
    messages_by_id: dict[str, dict[str, Any]],
    *,
    min_confidence: float = 0.45,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in findings:
        row = semantic_scope_label_row_from_finding(
            item, messages_by_id, min_confidence=min_confidence
        )
        if not row:
            continue
        existing = merged.get(str(row["message_id"]))
        if not existing:
            merged[str(row["message_id"])] = row
            continue
        existing["scope_labels"] = merged_scope_labels(
            existing.get("scope_labels") or [], row.get("scope_labels") or []
        )
        evidence_by_label = {
            str(item.get("label") or ""): item
            for item in [
                *list(existing.get("label_evidence") or []),
                *list(row.get("label_evidence") or []),
            ]
            if isinstance(item, dict) and item.get("label")
        }
        existing["label_evidence"] = [
            evidence_by_label[label]
            for label in existing["scope_labels"]
            if label in evidence_by_label
            and label_evidence_is_sufficient(label, evidence_by_label[label])
        ]
        if float(row.get("confidence") or 0.0) > float(existing.get("confidence") or 0.0):
            existing["confidence"] = row["confidence"]
            existing["rationale"] = row.get("rationale") or existing.get("rationale") or ""
            existing["source_job"] = row.get("source_job") or existing.get("source_job")
        existing["source_refs"] = list(
            {
                str(ref.get("message_id") or "") + ":" + str(ref.get("source_line") or ""): ref
                for ref in [
                    *list(existing.get("source_refs") or []),
                    *list(row.get("source_refs") or []),
                ]
            }.values()
        )[:5]

    def sort_key(item: dict[str, Any]) -> tuple[int, str]:
        try:
            line = int(messages_by_id.get(str(item.get("message_id")), {}).get("source_line") or 0)
        except (TypeError, ValueError):
            line = 0
        return line, str(item.get("message_id") or "")

    return sorted(merged.values(), key=sort_key)


def write_semantic_scope_label_sidecar(clean_source_dir: Path, rows: list[dict[str, Any]]) -> Path:
    path = clean_source_dir / SEMANTIC_SCOPE_LABELS_FILENAME
    clean_source_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(path)
    return path
