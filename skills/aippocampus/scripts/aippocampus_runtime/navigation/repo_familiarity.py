#!/usr/bin/env python3
"""Source-backed repo familiarity cards.

This module is a deterministic pressure-test adapter for a broader familiarity
map. It produces navigation hints, not current-code truth: every foreground card
must name the source to reopen and the point where extra verification becomes
noise.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from aippocampus_runtime.core import compact_text

SCHEMA_VERSION = 1
CARD_KIND = "source_backed_familiarity_card"
PACKET_KIND = "aippocampus_repo_familiarity_packet"
DEFAULT_MAX_CARDS = 3
DEFAULT_MAX_PACKET_BYTES = 1800


def _stable_id(parts: Sequence[Any]) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    return "rfc_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:18]


def _text(value: Any, limit: int = 220) -> str:
    return compact_text(str(value or "").strip(), limit)


def _strings(value: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _text(item, 120)
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


def _terms(value: Any) -> set[str]:
    text = str(value or "").casefold()
    return {term for term in re.findall(r"[a-z0-9_]+", text) if len(term) > 2}


def _source_refs(value: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return refs
    for item in value:
        if not isinstance(item, Mapping):
            continue
        clean = {
            "path": _text(item.get("path"), 180),
            "line": item.get("line"),
            "kind": _text(item.get("kind"), 80),
            "source_id": _text(item.get("source_id"), 140),
        }
        refs.append({key: val for key, val in clean.items() if val not in {None, ""}})
    return refs


def _route(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, Mapping):
        return {}
    clean: dict[str, list[str]] = {}
    for key in ("files", "tests", "docs", "commands"):
        values = _strings(value.get(key), limit=8)
        if values:
            clean[key] = values
    return clean


def _invalidation(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    clean: dict[str, Any] = {}
    commit = _text(value.get("commit"), 80)
    if commit:
        clean["commit"] = commit
    files: list[dict[str, str]] = []
    raw_files = value.get("files")
    if isinstance(raw_files, Sequence) and not isinstance(raw_files, (str, bytes)):
        for item in raw_files:
            if not isinstance(item, Mapping):
                continue
            path = _text(item.get("path"), 220)
            digest = _text(item.get("sha256"), 120)
            if path and digest:
                files.append({"path": path, "sha256": digest})
    if files:
        clean["files"] = files
    return clean


def build_repo_familiarity_cards(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = manifest.get("source_rows") or []
    repo_commit = _text(manifest.get("repo_commit"), 80)
    if not isinstance(rows, Sequence):
        return []
    cards: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        source_refs = _source_refs(row.get("source_refs"))
        if not source_refs:
            continue
        landmark = _text(row.get("landmark"), 120)
        action_delta = _text(row.get("action_delta_required"), 260)
        first_source = _text(row.get("first_source_to_reopen"), 220)
        stop_after = _text(row.get("stop_after"), 260)
        if not landmark or not action_delta or not first_source or not stop_after:
            continue
        route_terms = sorted(
            _terms(" ".join(_strings(row.get("route_terms"), limit=16))) | _terms(landmark)
        )
        card = {
            "schema_version": SCHEMA_VERSION,
            "kind": CARD_KIND,
            "domain": "repo",
            "card_id": _stable_id([landmark, first_source, source_refs[0].get("path")]),
            "landmark": landmark,
            "category": _text(row.get("kind"), 80),
            "boundary": _text(row.get("boundary"), 320),
            "route": _route(row.get("route")),
            "route_terms": route_terms,
            "decision_shadow": row.get("decision_shadow") if isinstance(row.get("decision_shadow"), Mapping) else {},
            "source_refs": source_refs,
            "freshness": _text(row.get("freshness"), 80) or "unknown",
            "invalidation": _invalidation(row.get("invalidation")),
            "why_now": _text(row.get("why_now"), 260),
            "action_delta_required": action_delta,
            "first_source_to_reopen": first_source,
            "stop_after": stop_after,
            "do_not_use_for": _strings(row.get("do_not_use_for"), limit=8),
            "injection_policy": {
                "support_level": "navigation",
                "source_reopen_required": True,
                "max_foreground_cards": DEFAULT_MAX_CARDS,
                "never_claim_current_code_without_reopen": True,
                "repo_commit": repo_commit,
            },
        }
        cards.append(card)
    return cards


def _card_bytes(card: Mapping[str, Any]) -> int:
    return len(json.dumps(card, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _task_score(card: Mapping[str, Any], task_terms: set[str]) -> int:
    card_terms = set(card.get("route_terms") or [])
    card_terms |= _terms(card.get("landmark"))
    card_terms |= _terms(card.get("why_now"))
    return len(task_terms & card_terms)


def _stale_reason(
    card: Mapping[str, Any],
    *,
    current_fingerprints: Mapping[str, str],
    current_commit: str,
) -> str:
    invalidation = card.get("invalidation") if isinstance(card.get("invalidation"), Mapping) else {}
    expected_commit = str(invalidation.get("commit") or "").strip()
    if expected_commit and current_commit and expected_commit != current_commit:
        return "commit_mismatch"
    raw_files = invalidation.get("files") if isinstance(invalidation, Mapping) else []
    if isinstance(raw_files, Sequence) and not isinstance(raw_files, (str, bytes)):
        for item in raw_files:
            if not isinstance(item, Mapping):
                continue
            path = str(item.get("path") or "")
            expected = str(item.get("sha256") or "")
            actual = str(current_fingerprints.get(path) or "")
            if actual and expected and actual != expected:
                return "file_hash_mismatch"
    return ""


def _rejection(card: Mapping[str, Any], reason: str, detail: str = "") -> dict[str, str]:
    return {
        "card_id": str(card.get("card_id") or ""),
        "landmark": str(card.get("landmark") or ""),
        "reason": reason,
        "detail": detail,
    }


def select_repo_familiarity_packet(
    cards: Sequence[Mapping[str, Any]],
    *,
    task: str,
    current_fingerprints: Mapping[str, str] | None = None,
    current_commit: str = "",
    max_cards: int = DEFAULT_MAX_CARDS,
    max_packet_bytes: int = DEFAULT_MAX_PACKET_BYTES,
) -> dict[str, Any]:
    """Select a tiny packet that can change the next action.

    The selector rejects stale or irrelevant cards before budget selection so a
    stale familiarity map cannot become another route the foreground agent must
    audit. The report is only a deterministic cost proxy; live token or tool-call
    savings require a separate benchmark arm.
    """

    task_terms = _terms(task)
    current_fingerprints = current_fingerprints or {}
    rejected: list[dict[str, str]] = []
    candidates: list[tuple[int, Mapping[str, Any]]] = []
    for card in cards:
        if card.get("kind") != CARD_KIND:
            continue
        stale = _stale_reason(
            card,
            current_fingerprints=current_fingerprints,
            current_commit=current_commit,
        )
        if stale:
            rejected.append(_rejection(card, "stale_invalidation", stale))
            continue
        if not card.get("action_delta_required") or not card.get("stop_after"):
            rejected.append(_rejection(card, "missing_action_delta_contract"))
            continue
        score = _task_score(card, task_terms)
        if score <= 0:
            rejected.append(_rejection(card, "irrelevant_to_task"))
            continue
        candidates.append((score, card))

    candidates.sort(key=lambda item: (-item[0], str(item[1].get("card_id") or "")))
    selected: list[dict[str, Any]] = []
    packet_bytes = 0
    for _, card in candidates:
        if len(selected) >= max_cards:
            rejected.append(_rejection(card, "packet_card_budget_exceeded"))
            continue
        clean = dict(card)
        card_size = _card_bytes(clean)
        if packet_bytes + card_size > max_packet_bytes:
            rejected.append(_rejection(card, "packet_byte_budget_exceeded", str(card_size)))
            continue
        selected.append(clean)
        packet_bytes += card_size

    fast_reject_count = len([item for item in rejected if item["reason"] == "stale_invalidation"])
    irrelevant_count = len([item for item in rejected if item["reason"] == "irrelevant_to_task"])
    return {
        "ok": True,
        "kind": PACKET_KIND,
        "schema_version": SCHEMA_VERSION,
        "task_terms": sorted(task_terms),
        "selected_cards": selected,
        "rejected_cards": rejected,
        "packet_bytes": packet_bytes,
        "packet_budget": {
            "max_cards": max_cards,
            "max_packet_bytes": max_packet_bytes,
            "action_delta_required": True,
            "stop_rule_required": True,
        },
        "cost_delta_report": {
            "deterministic_proxy_only": True,
            "cannot_claim_live_cost_reduction": True,
            "selected_card_count": len(selected),
            "packet_bytes": packet_bytes,
            "estimated_reopen_count": len(
                [card for card in selected if card.get("first_source_to_reopen")]
            ),
            "fast_reject_count": fast_reject_count,
            "irrelevant_reject_count": irrelevant_count,
            "wrong_route_drag_count": 0,
        },
        "policy": {
            "source_backed_familiarity_map": True,
            "navigation_not_truth": True,
            "no_coding_only_pivot": True,
        },
    }
