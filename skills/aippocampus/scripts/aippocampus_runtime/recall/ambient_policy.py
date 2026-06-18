#!/usr/bin/env python3
"""Dismissal and anti-nag policy for ambient working-memory recall.

This is a local overlay, not clean source and not formal memory. It records the
minimum state needed to stop repeating reviewed question/frontier scent in the
foreground hook. Keep it deterministic and cheap: foreground recall should fail
open when the overlay is missing, corrupt, or read-only.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc, workspace_fingerprint
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.registry.api import registry_paths, unique_preserve

POLICY_SCHEMA_VERSION = 1
DEFAULT_POLICY_NAME = "ambient_recall_policy.jsonl"
DEFAULT_POLICY_MAX_BYTES = 512 * 1024

SURFACE = "surface"
DISMISS = "dismiss"
REOPEN = "reopen"

QUESTION_CAP_SECONDS = 7 * 24 * 60 * 60
FRONTIER_CAP_SECONDS = 14 * 24 * 60 * 60

QUESTION_TYPES = {"question_link", "theme_candidate"}
FRONTIER_TYPES = {"frontier_marker"}
AMBIENT_CARD_TYPES = {"ambient_card"}
EVIDENCE_ROUTE_TYPES = {
    "bounded_evidence",
    "evidence_route",
    "reopenable_route",
    "source_backed_reopen",
    "source_open",
}
TRACKED_TYPES = QUESTION_TYPES | FRONTIER_TYPES | AMBIENT_CARD_TYPES
TRACKED_CARD_TYPES = TRACKED_TYPES | EVIDENCE_ROUTE_TYPES

DISMISS_PATTERNS = (
    r"\bstop tracking\b(?P<target>.*)",
    r"\bignore (?:the )?(?:question|frontier|topic)?(?: about)?\b(?P<target>.*)",
    r"\bdon't track\b(?P<target>.*)",
    r"\bdo not track\b(?P<target>.*)",
    r"\bdon't surface\b(?P<target>.*)",
    r"\bstop surfacing\b(?P<target>.*)",
    r"停止跟踪(?P<target>.*)",
    r"别再跟踪(?P<target>.*)",
    r"不要再跟踪(?P<target>.*)",
    r"忽略(?:这个|这条|关于)?(?P<target>.*)",
    r"别再提醒(?P<target>.*)",
    r"不要再提醒(?P<target>.*)",
)

REOPEN_PATTERNS = (
    r"\breopen tracking\b(?P<target>.*)",
    r"\btrack (?:it|this|that|again)\b(?P<target>.*)",
    r"\bresume tracking\b(?P<target>.*)",
    r"恢复跟踪(?P<target>.*)",
    r"重新跟踪(?P<target>.*)",
    r"取消忽略(?P<target>.*)",
)

THIS_TERMS = {"this", "it", "that", "这个", "这条", "这件事", "这个问题", "这"}
FRONTIER_INTENT_TERMS = {
    "resume",
    "revisit",
    "continue",
    "blocked",
    "blocker",
    "unresolved",
    "frontier",
    "boundary",
    "stuck",
    "handoff",
    "where did we stop",
    "继续",
    "续接",
    "恢复",
    "卡住",
    "阻塞",
    "未解决",
    "边界",
    "从哪继续",
    "下次从哪",
    "收尾",
}
CONTINUATION_INTENT_TERMS = {
    "continue",
    "resume",
    "revisit",
    "pick up",
    "keep going",
    "继续",
    "续接",
    "接着",
    "恢复",
}
CURRENT_TOPIC_POINTER_TERMS = THIS_TERMS | {
    "same",
    "current",
    "this topic",
    "this route",
    "this thread",
    "这个方向",
    "这个话题",
    "这件事",
    "这边",
}


@dataclass(frozen=True)
class AmbientPolicyIntent:
    action: str
    target_text: str
    this_reference: bool


def default_ambient_policy_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_POLICY_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_POLICY_NAME


def load_policy_events(path: Path | str | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        if target.stat().st_size > DEFAULT_POLICY_MAX_BYTES:
            # Foreground recall must stay fail-open. A giant local overlay means
            # compaction/maintenance is due; do not synchronously parse it inside
            # the prompt hook and risk making recall feel stuck.
            return []
        with target.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("kind") == "aippocampus_ambient_policy_event":
                    rows.append(item)
    except OSError:
        return []
    return rows


def append_policy_events(path: Path | str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def detect_policy_intent(prompt: str) -> AmbientPolicyIntent | None:
    text = str(prompt or "").strip()
    if not text:
        return None
    low = text.casefold()
    for action, patterns in ((REOPEN, REOPEN_PATTERNS), (DISMISS, DISMISS_PATTERNS)):
        for pattern in patterns:
            match = re.search(pattern, low, flags=re.IGNORECASE)
            if not match:
                continue
            if action == REOPEN and _reopen_match_has_negated_track_prefix(low, match.start()):
                continue
            target = _clean_target(match.groupdict().get("target") or "")
            return AmbientPolicyIntent(
                action=action,
                target_text=target,
                this_reference=not target or target in THIS_TERMS,
            )
    return None


def apply_working_memory_policy(
    prompt: str,
    rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    now: float | None = None,
) -> dict[str, Any]:
    now_unix = time.time() if now is None else now
    filtered: list[dict[str, Any]] = []
    diagnostics = {
        "dismissed": 0,
        "frequency_capped": 0,
        "frontier_not_requested": 0,
        "policy_event_count": len(events),
    }
    for row in rows:
        candidate_type = str(row.get("candidate_type") or "")
        target_key = target_key_for_row(row)
        if not target_key or candidate_type not in TRACKED_TYPES:
            filtered.append(row)
            continue
        if target_is_dismissed(target_key, events):
            diagnostics["dismissed"] += 1
            continue
        if candidate_type in FRONTIER_TYPES and not frontier_prompt_intent(prompt):
            diagnostics["frontier_not_requested"] += 1
            continue
        if frequency_cap_active(target_key, candidate_type, events, now_unix=now_unix):
            diagnostics["frequency_capped"] += 1
            continue
        filtered.append(row)
    return {"rows": filtered, "diagnostics": diagnostics}


def filter_ambient_cards(
    cards: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    prompt: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    now_unix = time.time() if now is None else now
    filtered: list[dict[str, Any]] = []
    diagnostics = {
        "dismissed": 0,
        "frequency_capped": 0,
        "frequency_cap_bypassed_for_current_continuation": 0,
        "frontier_not_requested": 0,
        "policy_event_count": len(events),
    }
    anti_nag_token_ids: list[str] = []
    current_continuation = current_topic_continuation_intent(prompt)
    for card in cards:
        keys = surface_keys_from_card(card)
        target_kind = surface_kind_from_card(card)
        if not keys or target_kind not in TRACKED_CARD_TYPES:
            filtered.append(card)
            continue
        if any(target_is_dismissed(key, events) for key in keys):
            diagnostics["dismissed"] += 1
            anti_nag_token_ids.extend(anti_nag_tokens_from_card(card))
            continue
        if target_kind in FRONTIER_TYPES and not frontier_prompt_intent(prompt):
            diagnostics["frontier_not_requested"] += 1
            anti_nag_token_ids.extend(anti_nag_tokens_from_card(card))
            continue
        if any(frequency_cap_active(key, target_kind, events, now_unix=now_unix) for key in keys):
            # Surface events are anti-nag hints, not hard dismissals. If the
            # user explicitly points back to "this/current" route, keep cached
            # ambient continuity available; otherwise the cap can swallow the
            # exact next-turn handoff it was meant to make less noisy.
            if target_kind in AMBIENT_CARD_TYPES and current_continuation:
                diagnostics["frequency_cap_bypassed_for_current_continuation"] += 1
                filtered.append(card)
                continue
            diagnostics["frequency_capped"] += 1
            anti_nag_token_ids.extend(anti_nag_tokens_from_card(card))
            continue
        filtered.append(card)
    return {
        "cards": filtered,
        "diagnostics": diagnostics,
        "anti_nag_token_ids": unique_preserve(anti_nag_token_ids, limit=64),
    }


def filter_evidence_cards(
    cards: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    prompt: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    """Apply anti-nag to source-backed foreground evidence routes.

    Evidence/source-open cards are stronger than weak ambient scent, but the
    live hook is still ambient foreground output. A route shown or dismissed in
    the local overlay should stay reachable through explicit recall/deepen while
    not re-emitting every prompt turn.
    """

    result = filter_ambient_cards(cards, events, prompt=prompt, now=now)
    result["diagnostics"] = {
        **result["diagnostics"],
        "evidence_route_policy": True,
    }
    return result


def surface_events_for_cards(
    cards: list[dict[str, Any]],
    *,
    thread_id: str | None,
    workspace: str,
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    timestamp = created_at or now_utc()
    seen: set[str] = set()
    for card in cards:
        target_kind = surface_kind_from_card(card)
        if target_kind not in TRACKED_CARD_TYPES:
            continue
        for target_key in surface_keys_from_card(card):
            if target_key in seen:
                continue
            seen.add(target_key)
            rows.append(
                _policy_event(
                    action=SURFACE,
                    target_key=target_key,
                    target_kind=target_kind,
                    target_title=str(card.get("theme") or ""),
                    source_finding_ids=policy_source_ids_from_card(card),
                    created_at=timestamp,
                    thread_id=thread_id,
                    workspace=workspace,
                    reason="foreground_ambient_card",
                )
            )
    return rows


def policy_update_for_prompt(
    *,
    prompt: str,
    rows: list[dict[str, Any]],
    cached_cards: list[dict[str, Any]],
    policy_path: Path | str,
    thread_id: str | None,
    workspace: str,
) -> dict[str, Any] | None:
    intent = detect_policy_intent(prompt)
    if intent is None:
        return None
    targets = policy_targets(intent, rows=rows, cached_cards=cached_cards)
    event_rows = [
        _policy_event(
            action=intent.action,
            target_key=target["target_key"],
            target_kind=target.get("target_kind") or "unknown",
            target_title=target.get("target_title") or "",
            source_finding_ids=target.get("source_finding_ids") or [],
            thread_id=thread_id,
            workspace=workspace,
            reason="user_escape_hatch",
            target_text_fingerprint=intent.target_text,
        )
        for target in targets
    ]
    try:
        append_policy_events(policy_path, event_rows)
        status = "written" if event_rows else "no_target"
    except Exception as exc:
        return {
            "action": intent.action,
            "target_count": len(event_rows),
            "target_keys": [row["target_key"] for row in event_rows],
            "this_reference": intent.this_reference,
            "policy_path": str(policy_path),
            "status": "write_error",
            "error_type": type(exc).__name__,
            "message": str(exc)[:160],
        }
    return {
        "action": intent.action,
        "target_count": len(event_rows),
        "target_keys": [row["target_key"] for row in event_rows],
        "this_reference": intent.this_reference,
        "policy_path": str(policy_path),
        "status": status,
    }


def policy_targets(
    intent: AmbientPolicyIntent,
    *,
    rows: list[dict[str, Any]],
    cached_cards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    if intent.this_reference:
        for card in cached_cards:
            target_kind = surface_kind_from_card(card)
            for key in surface_keys_from_card(card):
                targets.append(
                    {
                        "target_key": key,
                        "target_kind": target_kind,
                        "target_title": compact_text(str(card.get("theme") or ""), 180),
                        "source_finding_ids": policy_source_ids_from_card(card),
                    }
                )
        if targets:
            return _unique_targets(targets)
    if intent.target_text:
        terms = _target_terms(intent.target_text)
        for row in rows:
            if not _row_matches_terms(row, terms):
                continue
            target_key = target_key_for_row(row)
            if not target_key:
                continue
            targets.append(
                {
                    "target_key": target_key,
                    "target_kind": str(row.get("candidate_type") or ""),
                    "target_title": compact_text(str(row.get("title") or ""), 180),
                    "source_finding_ids": unique_preserve(
                        [str(value) for value in row.get("source_finding_ids") or [] if str(value)],
                        limit=12,
                    ),
                }
            )
    return _unique_targets(targets)


def target_key_for_row(row: dict[str, Any]) -> str:
    return compact_text(str(row.get("candidate_key") or ""), 120)


def policy_payload_for_working_memory(row: dict[str, Any]) -> dict[str, Any]:
    key = target_key_for_row(row)
    if not key:
        return {}
    return {
        "target_keys": [key],
        "target_kind": str(row.get("candidate_type") or ""),
        "source_finding_ids": unique_preserve(
            [str(value) for value in row.get("source_finding_ids") or [] if str(value)],
            limit=8,
        ),
        "dismissal_contract": "latest dismiss/reopen event wins; surface events enforce anti-nag caps",
    }


def policy_keys_from_card(card: dict[str, Any]) -> list[str]:
    policy = card.get("ambient_policy")
    if not isinstance(policy, dict):
        return []
    return unique_preserve(
        [compact_text(str(value or ""), 120) for value in policy.get("target_keys") or [] if str(value or "").strip()],
        limit=8,
    )


def fallback_surface_keys_from_card(card: dict[str, Any]) -> list[str]:
    """Return privacy-safe anti-nag keys for cards without explicit policy keys.

    Warm scout and cached ambient cards are often source-backed but not born
    from working-memory rows, so they lack ``ambient_policy.target_keys``. The
    fallback key is intentionally a hash over stable route/card/source handles:
    enough to avoid repeating the same foreground nudge, not enough to become a
    new memory fact or store raw prompt/source text in the policy overlay.
    """

    material: list[str] = []
    for key in (
        "card_id",
        "route_id",
        "query_pattern_route_id",
        "domain_id",
        "lock_id",
        "path_id",
    ):
        value = str(card.get(key) or "").strip()
        if value:
            material.append(f"{key}:{value}")
    for ref in card.get("source_refs") or []:
        if not isinstance(ref, dict):
            continue
        ref_parts = [
            str(ref.get(name) or "")
            for name in (
                "thread_key",
                "source_id",
                "message_id",
                "turn_id",
                "turn_index",
                "line",
            )
        ]
        if any(ref_parts):
            material.append("source_ref:" + "|".join(ref_parts))
    if not material:
        theme = compact_text(str(card.get("theme") or card.get("title") or ""), 160)
        support = compact_text(str(card.get("support_level") or ""), 40)
        if theme or support:
            material.append(f"theme:{theme}|support:{support}")
    if not material:
        return []
    digest = hashlib.sha256("\n".join(material).encode("utf-8", errors="replace")).hexdigest()
    return [f"ambient_card_{digest[:18]}"]


def surface_keys_from_card(card: dict[str, Any]) -> list[str]:
    keys = policy_keys_from_card(card)
    return keys if keys else fallback_surface_keys_from_card(card)


def anti_nag_tokens_from_card(card: dict[str, Any]) -> list[str]:
    """Return privacy-safe tokens that can suppress a card after it was quieted.

    Render-time anti-nag matching mostly sees route/card ids, while policy
    capping may only know hashed surface keys. Keep both in the local prompt
    result so a filtered cached card cannot be resurrected by raw reasons or
    weaker fallback routes on the next prompt.
    """

    tokens: list[str] = list(surface_keys_from_card(card))
    for key in (
        "card_id",
        "route_id",
        "query_pattern_route_id",
        "domain_id",
        "lock_id",
        "path_id",
        "deepen_route_id",
        "token_id",
        "id",
        "record_id",
    ):
        value = compact_text(str(card.get(key) or ""), 120)
        if value:
            tokens.append(value)
    return unique_preserve(tokens, limit=16)


def policy_kind_from_card(card: dict[str, Any]) -> str:
    policy = card.get("ambient_policy")
    return str((policy or {}).get("target_kind") or "") if isinstance(policy, dict) else ""


def surface_kind_from_card(card: dict[str, Any]) -> str:
    target_kind = policy_kind_from_card(card)
    return target_kind if target_kind else "ambient_card"


def policy_source_ids_from_card(card: dict[str, Any]) -> list[str]:
    policy = card.get("ambient_policy")
    if not isinstance(policy, dict):
        return []
    return unique_preserve(
        [str(value) for value in policy.get("source_finding_ids") or [] if str(value)],
        limit=12,
    )


def target_is_dismissed(target_key: str, events: list[dict[str, Any]]) -> bool:
    latest = _latest_event(target_key, events, actions={DISMISS, REOPEN})
    return bool(latest and latest.get("action") == DISMISS)


def frequency_cap_active(
    target_key: str,
    target_kind: str,
    events: list[dict[str, Any]],
    *,
    now_unix: float | None = None,
) -> bool:
    cap = FRONTIER_CAP_SECONDS if target_kind in FRONTIER_TYPES else QUESTION_CAP_SECONDS
    latest = _latest_event(target_key, events, actions={SURFACE})
    if not latest:
        return False
    surfaced = _parse_event_time(latest)
    if surfaced is None:
        return False
    reopened = _latest_event(target_key, events, actions={REOPEN})
    if reopened:
        reopened_at = _parse_event_time(reopened)
        if reopened_at is not None and surfaced <= reopened_at:
            return False
    current = time.time() if now_unix is None else now_unix
    return current - surfaced < cap


def frontier_prompt_intent(prompt: str) -> bool:
    low = str(prompt or "").casefold()
    return any(term in low for term in FRONTIER_INTENT_TERMS)


def current_topic_continuation_intent(prompt: str) -> bool:
    low = str(prompt or "").casefold()
    return any(term in low for term in CONTINUATION_INTENT_TERMS) and any(
        term in low for term in CURRENT_TOPIC_POINTER_TERMS
    )


def _policy_event(
    *,
    action: str,
    target_key: str,
    target_kind: str,
    target_title: str,
    thread_id: str | None,
    workspace: str,
    reason: str,
    created_at: str | None = None,
    target_text_fingerprint: str = "",
    source_finding_ids: list[str] | None = None,
) -> dict[str, Any]:
    # The overlay deliberately stores hashed prompt/workspace context plus the
    # reviewed target key. Do not add raw prompt text here: this file can live in
    # the private registry for a long time and only needs enough auditability to
    # explain why a candidate stopped surfacing.
    return {
        "kind": "aippocampus_ambient_policy_event",
        "schema_version": POLICY_SCHEMA_VERSION,
        "created_at": created_at or now_utc(),
        "action": action,
        "target_key": target_key,
        "target_kind": compact_text(target_kind, 80),
        "target_title": compact_text(target_title, 180),
        "source_finding_ids": unique_preserve(
            [str(value) for value in source_finding_ids or [] if str(value)],
            limit=12,
        ),
        # Legacy policy event fingerprints are durable registry fields. Do not
        # swap the digest in place; a future v2 needs dual-read/dual-write so
        # old dismissals continue suppressing the same ambient cards.
        "target_text_fingerprint": (
            _hash_value(target_text_fingerprint, "target", hashlib.sha1)
            if target_text_fingerprint
            else ""
        ),
        "reason": compact_text(reason, 120),
        # Same durable-event compatibility boundary as target_text_fingerprint.
        "thread_fingerprint": _hash_value(thread_id or "", "thread", hashlib.sha1),
        "workspace_fingerprint": workspace_fingerprint(workspace),
    }


def _hash_value(value: str, prefix: str, digest_fn: Any) -> str:
    return prefix + "_" + digest_fn(str(value or "").casefold().encode("utf-8")).hexdigest()[:16]


def _reopen_match_has_negated_track_prefix(text: str, start: int) -> bool:
    prefix = text[max(0, start - 40) : start]
    return bool(re.search(r"(?:don't|dont|do not|not to)(?:\s+\w+){0,3}\s+$", prefix))


def _latest_event(
    target_key: str, events: list[dict[str, Any]], *, actions: set[str]
) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    latest_time = -1.0
    for event in events:
        if event.get("target_key") != target_key or event.get("action") not in actions:
            continue
        timestamp = _parse_event_time(event)
        if timestamp is None:
            continue
        if timestamp >= latest_time:
            latest = event
            latest_time = timestamp
    return latest


def _parse_event_time(event: dict[str, Any]) -> float | None:
    text = str(event.get("created_at") or "")
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _clean_target(value: str) -> str:
    text = str(value or "").strip(" \t\r\n:：,，。.!！?？")
    for prefix in ("about ", "this ", "that ", "it ", "关于", "这个", "这条"):
        if text.casefold().startswith(prefix):
            text = text[len(prefix) :].strip(" \t\r\n:：,，。.!！?？")
    return compact_text(text, 120)


def _target_terms(text: str) -> list[str]:
    terms = [term.casefold() for term in split_query_terms([text]) if len(term) >= 3]
    if not terms and len(text.strip()) >= 2:
        terms = [text.strip().casefold()]
    return unique_preserve(terms, limit=8)


def _row_matches_terms(row: dict[str, Any], terms: list[str]) -> bool:
    if not terms:
        return False
    blob = "\n".join(
        [
            str(row.get("title") or ""),
            str(row.get("summary") or ""),
            str(row.get("recommendation") or ""),
            " ".join(str(value) for value in row.get("trigger_terms") or []),
            " ".join(str(value) for value in row.get("concepts") or []),
        ]
    ).casefold()
    return any(term and term in blob for term in terms)


def _unique_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for target in targets:
        key = str(target.get("target_key") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(target)
    return out
