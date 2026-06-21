"""Compact-safe identity helpers for Associative Path Walker routes.

APW routes cross diagnostics, foreground recall actions, selector caches,
source reopen, and low-authority feedback. Keep their identity rules in one
place so a route label cannot drift away from the source ref that will be
opened later. Raw refs may be used locally for matching, but public envelopes
carry only ids, cue anchors, and a source-ref digest.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

SOURCE_REF_KEYS = (
    "thread_key",
    "source_id",
    "message_id",
    "turn_id",
    "turn_index",
    "line",
    "source_line",
    "event_id",
)

IDENTITY_ID_KEYS = (
    "route_id",
    "candidate_id",
    "bridge_id",
    "id",
    "apw_candidate_route_id",
    "apw_candidate_id",
    "source_ref_digest",
    "source_id",
)


def clean_source_refs(value: Any, *, limit: int = 8) -> list[dict[str, Any]]:
    rows = value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []
    refs: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        clean = {
            key: row.get(key)
            for key in SOURCE_REF_KEYS
            if row.get(key) not in (None, "", [])
        }
        if not clean:
            continue
        marker = tuple(sorted((key, str(value)) for key, value in clean.items()))
        if marker in seen:
            continue
        seen.add(marker)
        refs.append(clean)
        if len(refs) >= limit:
            break
    return refs


def source_ref_digest(refs: Sequence[Mapping[str, Any]]) -> str:
    clean = clean_source_refs(refs)
    if not clean:
        return ""
    raw = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def id_variants(value: Any) -> set[str]:
    text = str(value or "").strip()
    if not text:
        return set()
    variants = {text}
    if text.startswith("apw:"):
        variants.add(text[len("apw:") :])
    else:
        variants.add(f"apw:{text}")
    if text.startswith("source-ref-digest:"):
        variants.add(text[len("source-ref-digest:") :])
    elif len(text) == 16 and all(ch in "0123456789abcdef" for ch in text.casefold()):
        variants.add(f"source-ref-digest:{text}")
    return {item for item in variants if item}


def source_ref_identity_keys(refs: Sequence[Mapping[str, Any]]) -> set[str]:
    keys: set[str] = set()
    clean_refs = clean_source_refs(refs)
    for ref in clean_refs:
        for key in ("source_id", "message_id"):
            keys.update(id_variants(ref.get(key)))
    digest = source_ref_digest(clean_refs)
    if digest:
        keys.update(id_variants(digest))
    return keys


def identity_keys(route_id: Any, row: Mapping[str, Any]) -> set[str]:
    keys: set[str] = set()
    for value in (route_id, *(row.get(key) for key in IDENTITY_ID_KEYS)):
        keys.update(id_variants(value))
    refs = clean_source_refs(row.get("source_refs")) or clean_source_refs(row.get("event_refs"))
    keys.update(source_ref_identity_keys(refs))
    return keys


def feedback_aliases(
    *,
    public_route_id: Any = "",
    apw_candidate_route_id: Any = "",
    apw_candidate_id: Any = "",
    source_ref_digest_value: Any = "",
    limit: int = 8,
) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for value in (
        public_route_id,
        apw_candidate_route_id,
        apw_candidate_id,
        source_ref_digest_value,
    ):
        for alias in sorted(id_variants(value)):
            if alias in seen:
                continue
            seen.add(alias)
            aliases.append(alias)
            if len(aliases) >= limit:
                return aliases
    return aliases


def _looks_local_source_id(value: Any) -> bool:
    text = str(value or "").strip().casefold()
    return (
        "current-clean-source:" in text
        or text.startswith(("msg-", "msg_", "src-", "src_", "turn-", "turn_"))
    )


def _public_identity_id(value: Any, *, digest: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if digest and _looks_local_source_id(text):
        return f"apw:source-ref-digest:{digest}"
    return text


def route_identity_envelope(
    *,
    public_route_id: Any,
    apw_candidate_route_id: Any = "",
    apw_candidate_id: Any = "",
    source_refs: Sequence[Mapping[str, Any]] | None = None,
    source_ref_digest_value: Any = "",
    matched_cue_anchors: Sequence[Any] | None = None,
    candidate_source_kind: Any = "",
    source_shape_posture: Any = "",
    request_index: Any = None,
    recall_selector: Any = "",
) -> dict[str, Any]:
    refs = clean_source_refs(source_refs or [])
    digest = str(source_ref_digest_value or source_ref_digest(refs)).strip()
    public_id = _public_identity_id(public_route_id, digest=digest)
    candidate_route_id = _public_identity_id(apw_candidate_route_id, digest=digest)
    candidate_id = _public_identity_id(apw_candidate_id, digest=digest)
    anchors: list[str] = []
    for anchor in matched_cue_anchors or []:
        text = str(anchor or "").strip()
        if text and text not in anchors:
            anchors.append(text[:80])
        if len(anchors) >= 6:
            break
    envelope = {
        "kind": "aippocampus_apw_route_identity",
        "schema_version": 1,
        "public_route_id": public_id,
        "apw_candidate_route_id": candidate_route_id,
        "apw_candidate_id": candidate_id,
        "source_ref_digest": digest,
        "selected_source_ref_count": len(refs),
        "matched_cue_anchors": anchors,
        "candidate_source_kind": str(candidate_source_kind or "").strip(),
        "source_shape_posture": str(source_shape_posture or "").strip(),
        "feedback_target_id": public_id,
        "feedback_aliases": feedback_aliases(
            public_route_id=public_id,
            apw_candidate_route_id=candidate_route_id,
            apw_candidate_id=candidate_id,
            source_ref_digest_value=digest,
        ),
        "raw_refs_redacted_from_compact_output": True,
    }
    if request_index not in (None, ""):
        envelope["request_index"] = request_index
    if recall_selector:
        envelope["recall_selector"] = str(recall_selector)
    return {
        key: value
        for key, value in envelope.items()
        if value not in (None, "", [], {})
    }
