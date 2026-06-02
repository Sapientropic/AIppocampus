#!/usr/bin/env python3
"""Thread-level ambient recall card cache.

This is a soft working surface. It stores compact card objects and hashed
thread/workspace identities, never raw prompt text. Foreground hooks may read
or update it, while later warm-scout work can reuse the same serial writer.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import (
    compact_text,
    now_utc,
    workspace_fingerprint,
    workspace_identity,
)
from aippocampus_runtime.recall.ambient_cards import cached_card_with_provenance
from aippocampus_runtime.registry.api import registry_paths, unique_preserve

CACHE_SCHEMA_VERSION = 1
RESIDUE_SCHEMA_VERSION = 1
DEFAULT_CACHE_NAME = "ambient_thread_cache.json"
DEFAULT_RESIDUE_NAME = "ambient_residue.jsonl"
DEFAULT_TTL_SECONDS = 6 * 60 * 60
DEFAULT_MAX_ENTRIES = 128
DEFAULT_MAX_CARDS = 8
DEFAULT_RESIDUE_REVIEW_AFTER_SECONDS = 7 * 24 * 60 * 60

RELATED_STRONG_PREFIXES = ("src_", "cand_", "sem_", "scope_", "topic_", "card_")
RELATED_WEAK_PREFIXES = ("alias_",)


def default_ambient_cache_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_CACHE_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_CACHE_NAME


def default_ambient_residue_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_RESIDUE_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_RESIDUE_NAME


def _fingerprint(value: str, *, prefix: str) -> str:
    digest = hashlib.sha256(str(value or "").casefold().encode("utf-8")).hexdigest()
    return prefix + "_" + digest[:16]


def cache_workspace_identity(workspace: str) -> str:
    return workspace_identity(workspace)


def cache_key(*, thread_id: str, workspace: str, topic_epoch: str) -> str:
    workspace_key = cache_workspace_identity(workspace)
    return _fingerprint(f"{thread_id}\n{workspace_key}\n{topic_epoch}", prefix="atc")


def topic_epoch_from_terms(terms: list[str], *, limit: int = 8) -> str:
    cleaned: list[str] = []
    for term in terms:
        text = compact_text(str(term or "").strip(), 80)
        if len(text) < 2:
            continue
        cleaned.append(text.casefold())
    stable_terms = sorted(unique_preserve(cleaned, limit=limit))
    if not stable_terms:
        return "epoch_empty"
    return _fingerprint("\n".join(stable_terms), prefix="epoch")


def _load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": CACHE_SCHEMA_VERSION, "updated_at": None, "entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": CACHE_SCHEMA_VERSION, "updated_at": None, "entries": {}}
    if not isinstance(data, dict):
        return {"schema_version": CACHE_SCHEMA_VERSION, "updated_at": None, "entries": {}}
    entries = data.get("entries")
    if not isinstance(entries, dict):
        data["entries"] = {}
    data["schema_version"] = CACHE_SCHEMA_VERSION
    return data


def _write_cache(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    tmp.replace(path)


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _existing_residue_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids: set[str] = set()
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            residue_id = str(item.get("residue_id") or "")
            if residue_id:
                ids.add(residue_id)
    return ids


def _future_utc(seconds: int) -> str:
    value = datetime.now(timezone.utc) + timedelta(seconds=max(0, seconds))
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _source_ref_fingerprint(ref: dict[str, Any]) -> str:
    return _fingerprint(
        "\n".join(
            [
                str(ref.get("thread_key") or ""),
                str(ref.get("line") or ""),
                str(ref.get("message_id") or ""),
            ]
        ),
        prefix="src",
    )


def _related_fingerprint(kind: str, value: Any) -> str:
    text = compact_text(str(value or "").strip(), 200)
    if not text:
        return ""
    return _fingerprint(text, prefix=kind)


def _candidate_related_fingerprints(items: Any) -> list[str]:
    values: list[str] = []
    if not isinstance(items, list):
        return []
    for item in items:
        if not isinstance(item, dict):
            continue
        thread_key = item.get("thread_key") or item.get("source_id") or item.get("thread")
        if thread_key:
            values.append(_related_fingerprint("cand", thread_key))
        for ref in item.get("source_refs") or []:
            if isinstance(ref, dict):
                values.append(_source_ref_fingerprint(ref))
        for label_key in ("scope_labels", "semantic_scope_labels", "labels"):
            labels = item.get(label_key)
            if isinstance(labels, list):
                values.extend(_related_fingerprint("scope", label) for label in labels)
    return [value for value in values if value]


def _semantic_related_fingerprints(semantic_gate: Any) -> list[str]:
    values: list[str] = []
    if not isinstance(semantic_gate, dict):
        return []
    for key in ("trigger_ids", "active_trigger_ids", "cue_ids", "active_cue_ids"):
        items = semantic_gate.get(key)
        if isinstance(items, list):
            values.extend(_related_fingerprint("sem", item) for item in items)
    for key in ("scope_labels", "semantic_scope_labels"):
        labels = semantic_gate.get(key)
        if isinstance(labels, list):
            values.extend(_related_fingerprint("scope", label) for label in labels)
    aliases = semantic_gate.get("query_aliases")
    if isinstance(aliases, list):
        values.extend(_related_fingerprint("alias", alias) for alias in aliases)
    return [value for value in values if value]


def related_signal_fingerprints(
    *,
    candidates: list[dict[str, Any]] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    working_memory: list[dict[str, Any]] | None = None,
    cards: list[dict[str, Any]] | None = None,
    semantic_gate: dict[str, Any] | None = None,
    query_aliases: list[str] | None = None,
    topic_epoch_decision: dict[str, Any] | None = None,
) -> list[str]:
    """Return privacy-safe related-cache signals for source/candidate overlap.

    These are hashed navigation signals, not semantic facts. Strong signals come
    from source refs, candidate thread keys, semantic trigger ids, scope labels,
    and model/scout topic labels. Query aliases are stored as weak evidence for
    diagnostics and future scoring, but a related-cache hit must not be based on
    alias overlap alone; otherwise paraphrase reuse would quietly regress into a
    prompt-text fuzzy matcher.
    """

    values: list[str] = []
    values.extend(_candidate_related_fingerprints(candidates or []))
    values.extend(_candidate_related_fingerprints(working_memory or []))
    if isinstance(evidence, list):
        for item in evidence:
            if not isinstance(item, dict):
                continue
            values.append(_source_ref_fingerprint(item))
            values.extend(_candidate_related_fingerprints([item]))
    if isinstance(cards, list):
        for card in cards:
            if not isinstance(card, dict):
                continue
            if card.get("card_id"):
                values.append(_related_fingerprint("card", card.get("card_id")))
            for ref in card.get("source_refs") or []:
                if isinstance(ref, dict):
                    values.append(_source_ref_fingerprint(ref))
    values.extend(_semantic_related_fingerprints(semantic_gate))
    for alias in query_aliases or []:
        values.append(_related_fingerprint("alias", alias))
    compact_decision = _compact_topic_epoch_decision(topic_epoch_decision)
    if compact_decision and compact_decision.get("label"):
        values.append(_related_fingerprint("topic", compact_decision.get("label")))
    return unique_preserve([value for value in values if value], limit=48)


def _source_ref_fingerprints(cards: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for card in cards:
        for ref in card.get("source_refs") or []:
            if isinstance(ref, dict):
                values.append(_source_ref_fingerprint(ref))
    return unique_preserve(values, limit=24)


def _compact_card(card: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "card_id",
        "theme",
        "resonance",
        "support_level",
        "visibility",
        "suggested_use",
        "nudge",
        "key_line",
        "matched_terms",
        "source_refs",
        "source_validation",
        "provenance_class",
        "cached_origin",
        "source_reopen_required",
        "reopenable_ref_count",
        "expand_if",
        "ambient_policy",
    }
    clean = {key: card.get(key) for key in allowed if key in card}
    for key in ("theme", "suggested_use", "nudge", "key_line", "expand_if"):
        if key in clean:
            clean[key] = compact_text(str(clean[key] or ""), 260)
    validation = clean.get("source_validation")
    if isinstance(validation, dict):
        clean["source_validation"] = {
            "status": compact_text(str(validation.get("status") or ""), 80),
            "checked_ref_count": _safe_int(validation.get("checked_ref_count")),
            "supported_ref_count": _safe_int(validation.get("supported_ref_count")),
            "missing_ref_count": _safe_int(validation.get("missing_ref_count")),
        }
    return clean


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _compact_topic_epoch_decision(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result = {
        "action": compact_text(str(value.get("action") or ""), 32),
        "label": compact_text(str(value.get("label") or ""), 120),
        "reason": compact_text(str(value.get("reason") or ""), 220),
        "confidence": value.get("confidence"),
        "source_scout": compact_text(str(value.get("source_scout") or ""), 120),
    }
    return {key: item for key, item in result.items() if item not in ("", None)}


def _residue_record(
    *,
    entry_key: str,
    entry: dict[str, Any],
    reason: str,
    review_after_seconds: int = DEFAULT_RESIDUE_REVIEW_AFTER_SECONDS,
) -> dict[str, Any] | None:
    cards = [card for card in entry.get("cards") or [] if isinstance(card, dict)]
    source_fingerprints = _source_ref_fingerprints(cards)
    if not source_fingerprints:
        return None
    card_ids = unique_preserve(
        [str(card.get("card_id") or "") for card in cards if card.get("card_id")], limit=16
    )
    support_levels = unique_preserve(
        [str(card.get("support_level") or "") for card in cards if card.get("support_level")],
        limit=8,
    )
    themes = unique_preserve(
        [compact_text(str(card.get("theme") or ""), 160) for card in cards if card.get("theme")],
        limit=8,
    )
    residue_id = _fingerprint(
        "\n".join([entry_key, "|".join(card_ids), "|".join(source_fingerprints)]),
        prefix="ares",
    )
    return {
        "kind": "aippocampus_ambient_residue",
        "schema_version": RESIDUE_SCHEMA_VERSION,
        "status": "dream_seed",
        "source": "ambient_thread_cache",
        "residue_id": residue_id,
        "created_at": now_utc(),
        "topic_epoch": entry.get("topic_epoch"),
        "reason": compact_text(str(reason or "manual_export"), 120),
        "mode": entry.get("mode"),
        "confidence": entry.get("confidence"),
        "card_ids": card_ids,
        "themes": themes,
        "support_levels": support_levels,
        "source_ref_fingerprints": source_fingerprints,
        "negative_contexts": entry.get("negative_contexts") or [],
        "downstream_use": ["dream_task_seed"],
        "expires_or_review_after": _future_utc(review_after_seconds),
        "dream_contract": "Seed only; not a dream finding, memory fact, or source-backed claim.",
    }


def export_thread_residue(
    cache_path: Path | str,
    residue_path: Path | str,
    *,
    thread_id: str,
    workspace: str,
    topic_epoch: str,
    reason: str = "manual_export",
    review_after_seconds: int = DEFAULT_RESIDUE_REVIEW_AFTER_SECONDS,
) -> dict[str, Any]:
    key = cache_key(thread_id=thread_id, workspace=workspace, topic_epoch=topic_epoch)
    data = _load_cache(Path(cache_path))
    entry = (data.get("entries") or {}).get(key)
    if not isinstance(entry, dict):
        return {"status": "miss", "topic_epoch": topic_epoch, "residue_count": 0}
    record = _residue_record(
        entry_key=key,
        entry=entry,
        reason=reason,
        review_after_seconds=review_after_seconds,
    )
    if record is None:
        return {"status": "skipped_no_source_refs", "topic_epoch": topic_epoch, "residue_count": 0}
    target = Path(residue_path)
    if record["residue_id"] in _existing_residue_ids(target):
        return {
            "status": "duplicate",
            "topic_epoch": topic_epoch,
            "residue_count": 0,
            "residue_id": record["residue_id"],
        }
    _append_jsonl(target, record)
    return {
        "status": "written",
        "topic_epoch": topic_epoch,
        "residue_count": 1,
        "residue_id": record["residue_id"],
        "output": str(target),
    }


def read_thread_cache(
    path: Path | str,
    *,
    thread_id: str,
    workspace: str,
    topic_epoch: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    target = Path(path)
    key = cache_key(thread_id=thread_id, workspace=workspace, topic_epoch=topic_epoch)
    data = _load_cache(target)
    entry = (data.get("entries") or {}).get(key)
    if not isinstance(entry, dict):
        return {"status": "miss", "topic_epoch": topic_epoch, "cards": []}
    updated_unix = float(entry.get("updated_unix") or 0.0)
    if ttl_seconds > 0 and updated_unix and time.time() - updated_unix > ttl_seconds:
        return {"status": "expired", "topic_epoch": topic_epoch, "cards": []}
    cards = [card for card in entry.get("cards") or [] if isinstance(card, dict)]
    return {
        "status": "hit",
        "topic_epoch": topic_epoch,
        "mode": entry.get("mode"),
        "confidence": entry.get("confidence"),
        "cards": cards,
        "source_ref_fingerprints": entry.get("source_ref_fingerprints") or [],
        "related_fingerprints": entry.get("related_fingerprints") or [],
        "query_aliases": entry.get("query_aliases") or [],
        "topic_epoch_decision": entry.get("topic_epoch_decision") or None,
        "visibility_bias": entry.get("visibility_bias") or None,
    }


def _same_thread_workspace_entries(
    data: dict[str, Any],
    *,
    thread_id: str,
    workspace: str,
    ttl_seconds: int,
) -> list[dict[str, Any]]:
    thread_fp = _fingerprint(thread_id, prefix="thread")
    workspace_fp = workspace_fingerprint(workspace)
    entries: list[dict[str, Any]] = []
    for entry in (data.get("entries") or {}).values():
        if not isinstance(entry, dict):
            continue
        if entry.get("thread_fingerprint") != thread_fp:
            continue
        if entry.get("workspace_fingerprint") != workspace_fp:
            continue
        updated_unix = float(entry.get("updated_unix") or 0.0)
        if ttl_seconds > 0 and updated_unix and time.time() - updated_unix > ttl_seconds:
            continue
        entries.append(entry)
    return entries


def _strong_related_overlap(
    left: set[str],
    right: set[str],
) -> set[str]:
    overlap = left & right
    return {value for value in overlap if value.startswith(RELATED_STRONG_PREFIXES)}


def _related_cache_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep related hits advisory until current-turn source is reopened.

    A related cache hit is pattern completion over source/candidate fingerprints,
    not a fresh source lookup. Downgrading cached evidence cards prevents an
    apparently helpful paraphrase match from surfacing old snippets as current
    evidence without reopening clean source in this turn.
    """

    out: list[dict[str, Any]] = []
    for card in cards:
        clean = cached_card_with_provenance(card)
        if clean.get("support_level") == "evidence" or clean.get("visibility") in {
            "source_backed_recall_card",
            "deep_archival_recall",
        }:
            clean["support_level"] = "candidate"
            clean["visibility"] = "active_gentle_nudge"
            clean["key_line"] = ""
            clean["suggested_use"] = (
                "Related cached source exists; reopen clean source before exact claims."
            )
            clean["expand_if"] = "Search clean source before presenting exact claims as facts."
        clean["source_reopen_required"] = True
        out.append(clean)
    return out


def read_related_thread_cache(
    path: Path | str,
    *,
    thread_id: str,
    workspace: str,
    topic_epoch: str,
    related_fingerprints: list[str],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    max_scan: int = 16,
) -> dict[str, Any]:
    """Return a same-thread cache entry matched by stable hashed signals.

    This is intentionally narrower than fuzzy text matching: it only scans the
    same thread/workspace, respects TTL, and requires overlap in strong hashed
    signals such as candidate thread keys, source refs, semantic trigger ids,
    scope labels, card ids, or scout topic labels. Query-alias overlap is kept
    for diagnostics but is not enough to reuse cards.
    """

    requested = set(related_fingerprints or [])
    if not requested:
        return {"status": "miss", "topic_epoch": topic_epoch, "cards": []}
    data = _load_cache(Path(path))
    entries = sorted(
        _same_thread_workspace_entries(
            data,
            thread_id=thread_id,
            workspace=workspace,
            ttl_seconds=ttl_seconds,
        ),
        key=lambda item: float(item.get("updated_unix") or 0.0),
        reverse=True,
    )[: max(1, max_scan)]
    scored: list[tuple[int, float, set[str], dict[str, Any]]] = []
    for entry in entries:
        if entry.get("topic_epoch") == topic_epoch:
            continue
        stored = set(entry.get("related_fingerprints") or [])
        strong_overlap = _strong_related_overlap(requested, stored)
        if not strong_overlap:
            continue
        weak_overlap = {
            value
            for value in (requested & stored)
            if value.startswith(RELATED_WEAK_PREFIXES)
        }
        score = len(strong_overlap) * 10 + len(weak_overlap)
        scored.append((score, float(entry.get("updated_unix") or 0.0), strong_overlap, entry))
    if not scored:
        return {"status": "miss", "topic_epoch": topic_epoch, "cards": []}
    score, _updated, overlap, entry = sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)[0]
    cards = _related_cache_cards([card for card in entry.get("cards") or [] if isinstance(card, dict)])
    return {
        "status": "related_hit",
        "topic_epoch": topic_epoch,
        "matched_topic_epoch": entry.get("topic_epoch"),
        "mode": entry.get("mode"),
        "confidence": entry.get("confidence"),
        "cards": cards,
        "source_ref_fingerprints": entry.get("source_ref_fingerprints") or [],
        "related_fingerprints": entry.get("related_fingerprints") or [],
        "related_overlap_count": len(overlap),
        "related_score": score,
        "query_aliases": entry.get("query_aliases") or [],
        "topic_epoch_decision": entry.get("topic_epoch_decision") or None,
        "visibility_bias": entry.get("visibility_bias") or None,
    }


def read_latest_thread_cache(
    path: Path | str,
    *,
    thread_id: str,
    workspace: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    """Return the newest cache entry for a thread/workspace without raw keys.

    The escape hatch uses this for phrases like "stop tracking this", where the
    prompt intentionally omits the old topic. Matching by hashed thread and
    workspace identity keeps that local control path from persisting the raw
    foreground prompt or absolute workspace in the policy overlay.
    """

    target = Path(path)
    data = _load_cache(target)
    entries = _same_thread_workspace_entries(
        data,
        thread_id=thread_id,
        workspace=workspace,
        ttl_seconds=ttl_seconds,
    )
    if not entries:
        return {"status": "miss", "cards": []}
    latest = sorted(entries, key=lambda item: float(item.get("updated_unix") or 0.0), reverse=True)[0]
    cards = [card for card in latest.get("cards") or [] if isinstance(card, dict)]
    return {
        "status": "hit",
        "topic_epoch": latest.get("topic_epoch"),
        "mode": latest.get("mode"),
        "confidence": latest.get("confidence"),
        "cards": cards,
        "source_ref_fingerprints": latest.get("source_ref_fingerprints") or [],
        "related_fingerprints": latest.get("related_fingerprints") or [],
        "query_aliases": latest.get("query_aliases") or [],
        "topic_epoch_decision": latest.get("topic_epoch_decision") or None,
        "visibility_bias": latest.get("visibility_bias") or None,
    }


def write_thread_cache(
    path: Path | str,
    *,
    thread_id: str,
    workspace: str,
    topic_epoch: str,
    cards: list[dict[str, Any]],
    mode: str = "active_gentle_nudge",
    confidence: str = "medium",
    negative_contexts: list[str] | None = None,
    query_aliases: list[str] | None = None,
    topic_epoch_decision: dict[str, Any] | None = None,
    visibility_bias: str | None = None,
    related_fingerprints: list[str] | None = None,
    residue_path: Path | str | None = None,
    residue_reason: str = "cache_write",
    max_cards: int = DEFAULT_MAX_CARDS,
    max_entries: int = DEFAULT_MAX_ENTRIES,
) -> dict[str, Any]:
    target = Path(path)
    compact_cards = [_compact_card(card) for card in cards if isinstance(card, dict)][:max_cards]
    if not compact_cards:
        return {"status": "empty", "topic_epoch": topic_epoch, "card_count": 0}
    data = _load_cache(target)
    entries: dict[str, Any] = dict(data.get("entries") or {})
    key = cache_key(thread_id=thread_id, workspace=workspace, topic_epoch=topic_epoch)
    source_ref_fingerprints = _source_ref_fingerprints(compact_cards)
    related_values = unique_preserve(
        [*source_ref_fingerprints, *(related_fingerprints or [])],
        limit=48,
    )
    entries[key] = {
        "updated_at": now_utc(),
        "updated_unix": time.time(),
        "thread_fingerprint": _fingerprint(thread_id, prefix="thread"),
        "workspace_fingerprint": workspace_fingerprint(workspace),
        "topic_epoch": topic_epoch,
        "mode": mode,
        "confidence": confidence,
        "cards": compact_cards,
        "negative_contexts": [compact_text(str(item or ""), 120) for item in (negative_contexts or [])[:8]],
        "source_ref_fingerprints": source_ref_fingerprints,
        "related_fingerprints": related_values,
        "query_aliases": unique_preserve(
            [compact_text(str(item or ""), 120) for item in (query_aliases or []) if str(item or "").strip()],
            limit=16,
        ),
        "topic_epoch_decision": _compact_topic_epoch_decision(topic_epoch_decision),
        "visibility_bias": compact_text(str(visibility_bias or ""), 80),
    }
    if len(entries) > max_entries:
        kept = sorted(
            entries.items(),
            key=lambda item: float((item[1] or {}).get("updated_unix") or 0.0),
            reverse=True,
        )[:max_entries]
        entries = dict(kept)
    data = {"schema_version": CACHE_SCHEMA_VERSION, "updated_at": now_utc(), "entries": entries}
    _write_cache(target, data)
    result = {
        "status": "written",
        "topic_epoch": topic_epoch,
        "card_count": len(compact_cards),
        "source_ref_fingerprints": entries[key].get("source_ref_fingerprints") or [],
        "related_fingerprints": entries[key].get("related_fingerprints") or [],
    }
    if residue_path is not None:
        result["residue_export"] = export_thread_residue(
            target,
            Path(residue_path),
            thread_id=thread_id,
            workspace=workspace,
            topic_epoch=topic_epoch,
            reason=residue_reason,
        )
    return result
