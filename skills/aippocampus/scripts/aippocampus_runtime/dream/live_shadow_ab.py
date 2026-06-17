#!/usr/bin/env python3
"""Live shadow A/B ledger for dream-hypothesis recall reminders.

The natural-prompt eval answers whether dream rows can improve route matching.
This module measures the sharper product question: after a real user prompt,
does the user later need to explicitly remind the agent to recall prior context?

Default operation is shadow-only. It records hashed prompt/session identifiers,
baseline-vs-dream route decisions, and later reminder outcomes; it does not
change foreground recall. A real treatment rollout can set delivered arms later,
but reports clearly separate delivered A/B from shadow-only observations.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Callable

from aippocampus_runtime.core import now_utc, sanitize_external_model_text, stable_text_fingerprint
from aippocampus_runtime.dream import real_history_eval as dream_eval
from aippocampus_runtime.model.client import (
    ChatClientConfig,
    chat_json,
)
from aippocampus_runtime.model.routing import (
    DEFAULT_DEEPSEEK_API_KEY_ENV,
    is_default_deepseek_api_key_env,
    resolve_model_route,
    resolve_route_reasoning_effort,
    resolve_route_thinking,
    route_cache_contract,
    route_payload_with_effective_values,
    route_service_name,
)
from aippocampus_runtime.registry.store import (
    load_registry,
    registry_paths,
    registry_root,
    thread_store_dir,
)
from aippocampus_runtime.subconscious.candidate_router import (
    DREAM_HYPOTHESIS_TYPE,
    default_jobs_path,
    default_working_memory_path,
    iter_jsonl,
    load_working_memory,
    match_working_memory,
)

SCHEMA_VERSION = 1
EVENT_KIND = "aippocampus_dream_shadow_ab_event"
ANALYSIS_KIND = "aippocampus_dream_live_shadow_ab_analysis"
CLAIM_LEVEL = "live_shadow_ab_reminder_frequency"
DEFAULT_EVENT_LOG_NAME = "dream_shadow_ab_events.jsonl"
DEFAULT_SALT = "aippocampus_dream_shadow_ab_v1"
DEFAULT_DREAM_WORKER_MODE = "deterministic"
MODEL_BACKED_DREAM_WORKER_MODE = "model_backed"
DELIVERY_OFF = "off"
DELIVERY_SHADOW = "shadow"
DELIVERY_DRY_RUN = "dry_run"
DELIVERY_DELIVERED = "delivered"
ASSIGNMENT_PROMPT = "prompt"
ASSIGNMENT_THREAD_TOPIC_EPOCH = "thread_topic_epoch"
SemanticRelevanceModelCall = Callable[[list[dict[str, str]], ChatClientConfig], dict[str, Any]]

POSITIVE_PATTERNS = (
    ("forgotten_constraint", re.compile(r"(你忘了|你没记住|忘记了|漏了我们之前)", re.IGNORECASE)),
    ("explicit_recall_zh", re.compile(r"(回忆一下|找回|翻一下旧|旧线程|之前.*(说过|聊过|提过|约定|要求|讲过)|上次.*(说过|聊过|提过)|还记得.*吗)", re.IGNORECASE)),
    ("explicit_recall_en", re.compile(r"\b(recall|remember|forgot|forgotten)\b.*\b(before|earlier|previous|last time|old thread|we discussed|we talked)\b", re.IGNORECASE)),
    ("as_said_before", re.compile(r"\b(as i said before|as we discussed|we talked about this before|you forgot)\b", re.IGNORECASE)),
)
TEMPORAL_NOISE_PATTERNS = (
    re.compile(r"\bbefore (calling|running|render|using|writing|returning)\b", re.IGNORECASE),
    re.compile(r"\bprevious (commit|version|function|call|line|diff|patch)\b", re.IGNORECASE),
    re.compile(r"(之前的代码|之前版本|上一段 diff|上一段代码|上一个 commit|上个版本|前一个函数)", re.IGNORECASE),
    re.compile(r"(不用查旧对话|不用回忆|不需要回忆|not asking you to remember)", re.IGNORECASE),
)


def stable_hash(value: object, *, prefix: str, salt: str = DEFAULT_SALT, length: int = 16) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return stable_text_fingerprint(
        f"{salt}\n{raw}",
        namespace=f"dream-shadow-{prefix}",
        prefix=prefix,
        length=length,
    )


def prompt_sha1(prompt: str) -> str:
    sanitized, _ = sanitize_external_model_text(prompt)
    return stable_text_fingerprint(sanitized, namespace="dream-shadow-prompt", length=16)


def ratio(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def normalize_delivery_mode(value: object) -> str:
    text = str(value or "").strip().casefold().replace("-", "_")
    if text in {"", "none", "disabled", "false", "0"}:
        return DELIVERY_OFF
    if text in {"shadow", "shadow_only", "prompt_hook_shadow", "historical_shadow_replay", "benchmark_historical_shadow_replay", "true", "1", "on", "yes"}:
        return DELIVERY_SHADOW
    if text in {"dry_run", "dryrun", "would_deliver"}:
        return DELIVERY_DRY_RUN
    if text in {"delivered", "delivery", "treatment"}:
        return DELIVERY_DELIVERED
    return DELIVERY_OFF


def normalize_assignment_unit(value: object) -> str:
    text = str(value or "").strip().casefold().replace("-", "_")
    if text == ASSIGNMENT_THREAD_TOPIC_EPOCH:
        return ASSIGNMENT_THREAD_TOPIC_EPOCH
    return ASSIGNMENT_PROMPT


def clamped_rollout_rate(value: object) -> float:
    if value is None:
        return 1.0
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return 1.0
    if number != number:
        return 1.0
    return max(0.0, min(1.0, number))


def rollout_bucket_for(*parts: object, salt: str = DEFAULT_SALT) -> float:
    digest = stable_text_fingerprint(
        f"{salt}\n{json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)}",
        namespace="dream-shadow-rollout",
        length=8,
    )
    return round(int(digest[:8], 16) / 0xFFFFFFFF, 6)


def classify_recall_reminder(text: str) -> dict[str, Any]:
    lowered = str(text or "").strip()
    if not lowered:
        return {"is_reminder": False, "family": "", "strength": "none"}
    if any(pattern.search(lowered) for pattern in TEMPORAL_NOISE_PATTERNS):
        return {"is_reminder": False, "family": "temporal_or_code_noise", "strength": "none"}
    for family, pattern in POSITIVE_PATTERNS:
        if pattern.search(lowered):
            strength = "high" if family in {"forgotten_constraint", "as_said_before"} else "medium"
            return {"is_reminder": True, "family": family, "strength": strength}
    return {"is_reminder": False, "family": "", "strength": "none"}


def split_working_memory_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    baseline: list[dict[str, Any]] = []
    dream: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        if copy.get("candidate_type") == DREAM_HYPOTHESIS_TYPE:
            dream.append(copy)
        else:
            baseline.append(copy)
    return baseline, dream


def load_shadow_working_memory_rows(
    *,
    registry_dir: Path | None = None,
    working_memory_path: Path | None = None,
    generated_dream_max_packs: int = 0,
    dream_worker_mode: str = DEFAULT_DREAM_WORKER_MODE,
    model_config: ChatClientConfig | None = None,
    model_call: dream_eval.dream_worker.ModelCall | None = None,
    max_samples: int = 1,
) -> list[dict[str, Any]]:
    registry_path: Path | None = None
    if working_memory_path is None:
        registry_path, _ = registry_paths(registry_dir)
        rows = load_working_memory(default_working_memory_path(registry_path))
    else:
        rows = load_working_memory(working_memory_path)
    if generated_dream_max_packs > 0:
        if registry_path is None:
            registry_path, _ = registry_paths(registry_dir)
        jobs = iter_jsonl(default_jobs_path(registry_path))
        packs = dream_eval.select_real_history_packs(
            job_rows=jobs,
            working_memory_rows=rows,
            max_packs=generated_dream_max_packs,
        )
        worker_mode = str(dream_worker_mode or DEFAULT_DREAM_WORKER_MODE).strip().replace("-", "_")
        if worker_mode not in {DEFAULT_DREAM_WORKER_MODE, MODEL_BACKED_DREAM_WORKER_MODE}:
            raise ValueError("dream_worker_mode must be 'deterministic' or 'model_backed'")
        if worker_mode == MODEL_BACKED_DREAM_WORKER_MODE and model_config is None:
            raise ValueError("model_config is required when dream_worker_mode='model_backed'")
        rows = [
            *rows,
            *[
                row
                for pack in packs
                for row in (
                    dream_eval.run_pack_dream_worker(
                        pack,
                        model_config=model_config if worker_mode == MODEL_BACKED_DREAM_WORKER_MODE else None,
                        model_call=model_call,
                        no_write=False,
                        max_samples=max(1, int(max_samples)),
                    ).get("dream_working_memory_rows")
                    or []
                )
                if isinstance(row, dict)
            ],
        ]
    return rows


def source_finding_fanout(rows: Iterable[Mapping[str, Any]]) -> int:
    ids = {
        str(source_id)
        for row in rows
        for source_id in (row.get("source_finding_ids") or [])
        if source_id
    }
    return len(ids)


def dream_route_matches(
    prompt: str,
    dream_rows: list[dict[str, Any]],
    *,
    project_label: str | None,
) -> list[dict[str, Any]]:
    return [
        match
        for match in match_working_memory(prompt, dream_rows, project_label=project_label, limit=12)
        if match.get("candidate_type") == DREAM_HYPOTHESIS_TYPE
    ]


def semantic_relevance_candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_key": row.get("candidate_key"),
        "title": row.get("title"),
        "summary": row.get("summary"),
        "activation_cues": list(row.get("activation_cues") or row.get("trigger_terms") or [])[:8],
        "concepts": list(row.get("concepts") or [])[:8],
        "truth_boundary": row.get("truth_boundary"),
    }


def semantic_relevance_messages(
    *,
    prompt: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, str]]:
    payload = {
        "task": "Select dream hypotheses that are semantically relevant to the user prompt.",
        "rules": [
            "Be strict: only match if the dream hypothesis would change recall, reflection, or safety handling.",
            "Do not match merely because of generic words or broad project context.",
            "Return JSON only with matches: [{candidate_key, relevant, confidence, reason}].",
            "Use relevant=false or omit candidates when unsure.",
        ],
        "user_prompt": prompt,
        "dream_candidates": candidates,
    }
    return [
        {
            "role": "system",
            "content": "You are a strict semantic relevance gate for AIppocampus dream shadow A/B replay.",
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def model_response_payload(response: Mapping[str, Any]) -> dict[str, Any]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return {}
    message = choices[0].get("message") if isinstance(choices[0], Mapping) else None
    content = message.get("content") if isinstance(message, Mapping) else None
    if not isinstance(content, str):
        return {}
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def semantic_relevance_dream_matches(
    *,
    prompt: str,
    dream_rows: list[dict[str, Any]],
    config: ChatClientConfig,
    model_call: SemanticRelevanceModelCall = chat_json,
    project_label: str | None,
    min_confidence: float = 0.65,
    max_candidates: int = 32,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates = [
        row
        for row in dream_rows
        if row.get("status") == "active"
        and row.get("candidate_type") == DREAM_HYPOTHESIS_TYPE
        and (not row.get("project_label") or not project_label or str(row.get("project_label")).casefold() == project_label.casefold())
    ][: max(1, int(max_candidates))]
    diagnostic: dict[str, Any] = {
        "enabled": True,
        "model_call_count": 0,
        "candidate_count": len(candidates),
        "match_count": 0,
        "min_confidence": min_confidence,
        "raw_prompt_emitted": False,
        "external_prompt_sent": False,
    }
    if not candidates:
        return [], diagnostic
    messages = semantic_relevance_messages(
        prompt=prompt,
        candidates=[semantic_relevance_candidate(row) for row in candidates],
    )
    diagnostic["model_call_count"] = 1
    diagnostic["external_prompt_sent"] = True
    try:
        response = model_call(messages, config)
    except Exception as exc:
        diagnostic["match_count"] = 0
        diagnostic["error_type"] = type(exc).__name__
        diagnostic["error"] = str(exc)[:160]
        return [], diagnostic
    by_key = {str(row.get("candidate_key") or ""): row for row in candidates}
    matches: list[dict[str, Any]] = []
    payload = model_response_payload(response)
    for item in payload.get("matches") or []:
        if not isinstance(item, Mapping) or not item.get("relevant"):
            continue
        try:
            confidence = float(item.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < min_confidence:
            continue
        row = by_key.get(str(item.get("candidate_key") or ""))
        if not row:
            continue
        copy = dict(row)
        copy["semantic_relevance"] = {
            "confidence": round(confidence, 4),
            "reason": str(item.get("reason") or "")[:160],
        }
        matches.append(copy)
    diagnostic["match_count"] = len(matches)
    return matches, diagnostic


def assigned_arm_for(*parts: object, salt: str = DEFAULT_SALT) -> str:
    digest = stable_text_fingerprint(
        f"{salt}\n{json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)}",
        namespace="dream-shadow-assignment",
        length=2,
    )
    return "dream" if int(digest[:2], 16) % 2 else "control"


def assignment_parts(
    *,
    assignment_unit: str,
    session_id: str,
    topic_epoch: str | None,
    turn_id: str,
    prompt_hash: str,
) -> tuple[object, ...]:
    unit = normalize_assignment_unit(assignment_unit)
    if unit == ASSIGNMENT_THREAD_TOPIC_EPOCH:
        return (unit, session_id or "unknown", topic_epoch or "default")
    return (session_id or "unknown", turn_id or "", prompt_hash)


def delivery_block_reasons(
    *,
    reminder: Mapping[str, Any],
    baseline_matches: list[dict[str, Any]],
    dream_matches: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if reminder.get("is_reminder"):
        reasons.append("recall_reminder_prompt")
    if baseline_matches:
        reasons.append("baseline_match")
    if not dream_matches:
        reasons.append("dream_miss")
    return reasons


def delivery_decision_fields(
    *,
    delivery_mode: str,
    eligible: bool,
    assigned_arm: str,
    rollout_rate: float,
    rollout_bucket: float,
) -> dict[str, Any]:
    if delivery_mode == DELIVERY_OFF:
        return {
            "would_deliver_arm": None,
            "delivered_arm": None,
            "delivery_decision": "delivery_disabled",
        }
    if delivery_mode == DELIVERY_SHADOW:
        return {
            "would_deliver_arm": None,
            "delivered_arm": None,
            "delivery_decision": "shadow_only",
        }
    if not eligible:
        return {
            "would_deliver_arm": None,
            "delivered_arm": None,
            "delivery_decision": "not_eligible",
        }
    if rollout_bucket >= rollout_rate:
        return {
            "would_deliver_arm": None,
            "delivered_arm": None,
            "delivery_decision": "rollout_excluded",
        }
    treatment = "dream_treatment" if assigned_arm == "dream" else "control_holdback"
    if delivery_mode == DELIVERY_DRY_RUN:
        return {
            "would_deliver_arm": assigned_arm,
            "delivered_arm": None,
            "delivery_decision": f"dry_run_{treatment}",
        }
    if delivery_mode == DELIVERY_DELIVERED:
        return {
            "would_deliver_arm": assigned_arm,
            "delivered_arm": assigned_arm,
            "delivery_decision": f"delivered_{treatment}",
        }
    return {
        "would_deliver_arm": None,
        "delivered_arm": None,
        "delivery_decision": "delivery_disabled",
    }


def build_shadow_prompt_event(
    *,
    prompt: str,
    session_id: str,
    turn_id: str = "",
    topic_epoch: str | None = None,
    user_turn_index: int | None = None,
    baseline_rows: Iterable[Mapping[str, Any]],
    dream_rows: Iterable[Mapping[str, Any]],
    project_label: str | None = "AIppocampus",
    salt: str = DEFAULT_SALT,
    timestamp: str | None = None,
    source: str = "prompt_hook_shadow",
    delivery_mode: str = "shadow_only",
    delivered_arm: str | None = None,
    assignment_unit: str = ASSIGNMENT_PROMPT,
    rollout_rate: float = 1.0,
    semantic_relevance_config: ChatClientConfig | None = None,
    semantic_relevance_model_call: SemanticRelevanceModelCall | None = None,
    semantic_relevance_min_confidence: float = 0.65,
    semantic_relevance_max_candidates: int = 32,
) -> dict[str, Any]:
    baseline_list = [dict(row) for row in baseline_rows]
    dream_list = [dict(row) for row in dream_rows]
    baseline_matches = match_working_memory(prompt, baseline_list, project_label=project_label, limit=12)
    dream_matches = dream_route_matches(prompt, dream_list, project_label=project_label)
    reminder = classify_recall_reminder(prompt)
    semantic_diagnostic = {
        "enabled": semantic_relevance_config is not None,
        "model_call_count": 0,
        "candidate_count": 0,
        "match_count": 0,
        "raw_prompt_emitted": False,
        "external_prompt_sent": False,
    }
    if (
        semantic_relevance_config is not None
        and not reminder["is_reminder"]
        and not baseline_matches
        and not dream_matches
    ):
        semantic_matches, semantic_diagnostic = semantic_relevance_dream_matches(
            prompt=prompt,
            dream_rows=dream_list,
            config=semantic_relevance_config,
            model_call=semantic_relevance_model_call or chat_json,
            project_label=project_label,
            min_confidence=semantic_relevance_min_confidence,
            max_candidates=semantic_relevance_max_candidates,
        )
        dream_matches = semantic_matches
    prompt_hash = prompt_sha1(prompt)
    unit = normalize_assignment_unit(assignment_unit)
    assignment_key_parts = assignment_parts(
        assignment_unit=unit,
        session_id=session_id,
        topic_epoch=topic_epoch,
        turn_id=turn_id,
        prompt_hash=prompt_hash,
    )
    assigned_arm = assigned_arm_for(*assignment_key_parts, salt=salt)
    bucket = rollout_bucket_for(*assignment_key_parts, salt=salt)
    rate = clamped_rollout_rate(rollout_rate)
    block_reasons = delivery_block_reasons(
        reminder=reminder,
        baseline_matches=baseline_matches,
        dream_matches=dream_matches,
    )
    eligible = not block_reasons
    mode = normalize_delivery_mode(delivery_mode)
    delivery_fields = delivery_decision_fields(
        delivery_mode=mode,
        eligible=eligible,
        assigned_arm=assigned_arm,
        rollout_rate=rate,
        rollout_bucket=bucket,
    )
    explicit_delivered_arm = delivered_arm if delivered_arm in {"control", "dream"} else None
    if explicit_delivered_arm and mode == DELIVERY_DELIVERED:
        delivery_fields["delivered_arm"] = explicit_delivered_arm
    event = {
        "schema_version": SCHEMA_VERSION,
        "kind": EVENT_KIND,
        "created_at": timestamp or now_utc(),
        "source": source,
        "delivery_mode": mode,
        "delivery_decision": delivery_fields["delivery_decision"],
        "delivery_block_reasons": block_reasons
        + (["rollout_excluded"] if delivery_fields["delivery_decision"] == "rollout_excluded" else []),
        "event_id": stable_hash([session_id, turn_id, prompt_hash], prefix="shadowevt", salt=salt),
        "thread_fingerprint": stable_hash(session_id or "unknown", prefix="threadfp", salt=salt, length=12),
        "turn_fingerprint": stable_hash(turn_id or user_turn_index or prompt_hash, prefix="turnfp", salt=salt, length=12),
        "user_turn_index": user_turn_index,
        "prompt_sha1": prompt_hash,
        "assignment_unit": unit,
        "assignment_key_hash": stable_hash(assignment_key_parts, prefix="assign", salt=salt, length=12),
        "rollout_rate": rate,
        "rollout_bucket": bucket,
        "assigned_arm": assigned_arm,
        "would_deliver_arm": delivery_fields["would_deliver_arm"],
        "delivered_arm": delivery_fields["delivered_arm"],
        "eligible_exposure": eligible,
        "reminder": reminder,
        "baseline": {
            "match_count": len(baseline_matches),
            "decision": "match" if baseline_matches else "miss",
        },
        "dream": {
            "match_count": len(dream_matches),
            "decision": "match" if dream_matches else "miss",
            "semantic_match_count": int(semantic_diagnostic.get("match_count") or 0),
            "source_finding_fanout": source_finding_fanout(dream_matches),
        },
        "semantic_relevance": semantic_diagnostic,
        "privacy_boundary": {
            "raw_prompt_emitted": False,
            "raw_thread_id_emitted": False,
            "raw_turn_id_emitted": False,
        },
    }
    return event


def append_event(path: Path, event: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(dict(event), ensure_ascii=False) + "\n")


def load_events(path: Path) -> list[dict[str, Any]]:
    return [row for row in iter_jsonl(path) if row.get("kind") == EVENT_KIND]


def default_event_log(registry_dir: Path | None = None) -> Path:
    return registry_root(registry_dir) / DEFAULT_EVENT_LOG_NAME


def row_order(row: Mapping[str, Any], fallback: int) -> int:
    value = row.get("user_turn_index")
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return fallback


def effective_arm(row: Mapping[str, Any]) -> str:
    delivered = str(row.get("delivered_arm") or "")
    if delivered in {"control", "dream"}:
        return delivered
    assigned = str(row.get("assigned_arm") or "")
    return assigned if assigned in {"control", "dream"} else "control"


def empty_arm_metrics() -> dict[str, Any]:
    return {
        "eligible_exposures": 0,
        "reminder_outcomes": 0,
        "reminder_rate": 0.0,
    }


def analyze_shadow_events(
    events: Iterable[Mapping[str, Any]],
    *,
    window_user_turns: int = 4,
) -> dict[str, Any]:
    rows = [dict(row) for row in events if row.get("kind") == EVENT_KIND]
    has_live_delivery = any(row.get("delivered_arm") in {"control", "dream"} for row in rows)
    by_thread: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, row in enumerate(rows):
        thread = str(row.get("thread_fingerprint") or "thread_unknown")
        by_thread[thread].append((row_order(row, index), row))

    arms = {"control": empty_arm_metrics(), "dream": empty_arm_metrics()}
    total_reminders = 0
    attributed = 0
    unattributed = 0
    attributed_event_ids: set[str] = set()
    live_delivery_events = 0
    reminder_family_counts: dict[str, int] = defaultdict(int)
    reminder_strength_counts: dict[str, int] = defaultdict(int)
    baseline_match_events = 0
    dream_match_events = 0
    both_match_events = 0
    dream_only_non_reminder_events = 0
    dream_only_reminder_events = 0
    semantic_relevance_model_calls = 0
    semantic_relevance_match_events = 0
    would_delivery_events = 0
    delivery_mode_counts: dict[str, int] = defaultdict(int)
    delivery_decision_counts: dict[str, int] = defaultdict(int)

    for items in by_thread.values():
        items.sort(key=lambda item: item[0])
        for _, row in items:
            if row.get("delivered_arm") in {"control", "dream"}:
                live_delivery_events += 1
            if row.get("would_deliver_arm") in {"control", "dream"}:
                would_delivery_events += 1
            mode = str(row.get("delivery_mode") or "unknown")
            decision = str(row.get("delivery_decision") or "unknown")
            delivery_mode_counts[mode] += 1
            delivery_decision_counts[decision] += 1
            baseline_value = row.get("baseline")
            baseline = baseline_value if isinstance(baseline_value, Mapping) else {}
            dream_value = row.get("dream")
            dream = dream_value if isinstance(dream_value, Mapping) else {}
            reminder_value = row.get("reminder")
            reminder = reminder_value if isinstance(reminder_value, Mapping) else {}
            semantic_value = row.get("semantic_relevance")
            semantic = semantic_value if isinstance(semantic_value, Mapping) else {}
            baseline_matched = int(baseline.get("match_count") or 0) > 0
            dream_matched = int(dream.get("match_count") or 0) > 0
            semantic_relevance_model_calls += int(semantic.get("model_call_count") or 0)
            if int(semantic.get("match_count") or 0) > 0:
                semantic_relevance_match_events += 1
            if baseline_matched:
                baseline_match_events += 1
            if dream_matched:
                dream_match_events += 1
            if baseline_matched and dream_matched:
                both_match_events += 1
            if dream_matched and not baseline_matched:
                if reminder.get("is_reminder"):
                    dream_only_reminder_events += 1
                else:
                    dream_only_non_reminder_events += 1
            if row.get("eligible_exposure") and (
                not has_live_delivery or row.get("delivered_arm") in {"control", "dream"}
            ):
                arms[effective_arm(row)]["eligible_exposures"] += 1

        for position, (order, row) in enumerate(items):
            reminder_value = row.get("reminder")
            reminder = reminder_value if isinstance(reminder_value, Mapping) else {}
            if not reminder.get("is_reminder"):
                continue
            total_reminders += 1
            family = str(reminder.get("family") or "unknown")
            strength = str(reminder.get("strength") or "unknown")
            reminder_family_counts[family] += 1
            reminder_strength_counts[strength] += 1
            winner: dict[str, Any] | None = None
            for prior_order, candidate in reversed(items[:position]):
                if order - prior_order > window_user_turns:
                    break
                event_id = str(candidate.get("event_id") or "")
                if not candidate.get("eligible_exposure") or event_id in attributed_event_ids:
                    continue
                if has_live_delivery and candidate.get("delivered_arm") not in {"control", "dream"}:
                    continue
                winner = candidate
                break
            if winner is None:
                unattributed += 1
                continue
            attributed += 1
            attributed_event_ids.add(str(winner.get("event_id") or ""))
            arms[effective_arm(winner)]["reminder_outcomes"] += 1

    for arm in arms.values():
        arm["reminder_rate"] = ratio(arm["reminder_outcomes"], arm["eligible_exposures"])

    return {
        "event_count": len(rows),
        "thread_count": len(by_thread),
        "live_delivery_event_count": live_delivery_events,
        "would_delivery_event_count": would_delivery_events,
        "overall_reminder_rate": ratio(total_reminders, len(rows)),
        "eligible_exposure_rate": ratio(
            arms["control"]["eligible_exposures"] + arms["dream"]["eligible_exposures"],
            len(rows),
        ),
        "arms": arms,
        "rate_delta_dream_minus_control": round(
            arms["dream"]["reminder_rate"] - arms["control"]["reminder_rate"],
            4,
        ),
        "direction": "lower_is_better",
        "attribution": {
            "window_user_turns": window_user_turns,
            "total_reminder_count": total_reminders,
            "attributed_reminder_count": attributed,
            "unattributed_reminder_count": unattributed,
            "nearest_prior_eligible_exposure_only": True,
        },
        "reminder_family_counts": dict(sorted(reminder_family_counts.items())),
        "reminder_strength_counts": dict(sorted(reminder_strength_counts.items())),
        "delivery_mode_counts": dict(sorted(delivery_mode_counts.items())),
        "delivery_decision_counts": dict(sorted(delivery_decision_counts.items())),
        "match_diagnostics": {
            "baseline_match_event_count": baseline_match_events,
            "dream_match_event_count": dream_match_events,
            "both_match_event_count": both_match_events,
            "dream_only_non_reminder_event_count": dream_only_non_reminder_events,
            "dream_only_reminder_event_count": dream_only_reminder_events,
            "semantic_relevance_model_call_count": semantic_relevance_model_calls,
            "semantic_relevance_match_event_count": semantic_relevance_match_events,
        },
    }


def run_shadow_ab_analysis(
    *,
    event_log: Path,
    window_user_turns: int = 4,
) -> dict[str, Any]:
    metrics = analyze_shadow_events(load_events(event_log), window_user_turns=window_user_turns)
    live_delivery = int(metrics.get("live_delivery_event_count") or 0) > 0
    can_claim = [
        "explicit_recall_reminder_frequency_counted",
        "nearest_prior_exposure_attribution_used",
        "shadow_ab_log_is_sanitized",
    ]
    cannot_claim = [
        "general_dream_quality",
        "full_history_coverage",
    ]
    if live_delivery:
        can_claim.append("observed_delivered_arm_reminder_rates")
    else:
        cannot_claim.append("causal_real_user_behavior_lift_without_delivered_treatment")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ANALYSIS_KIND,
        "created_at": now_utc(),
        "status": "analyzed" if metrics["event_count"] else "no_events",
        "claim_level": CLAIM_LEVEL,
        "private_text_emitted": False,
        "metrics": metrics,
        "can_claim": can_claim,
        "cannot_claim": cannot_claim,
    }


def record_prompt_shadow_from_hook(
    *,
    prompt: str,
    hook_input: Mapping[str, Any],
    registry_dir: Path | None = None,
    registry_path: Path | None = None,
    working_memory_path: Path | None = None,
    event_log: Path | None = None,
    salt: str = DEFAULT_SALT,
    project_label: str | None = "AIppocampus",
    delivery_mode: str = DELIVERY_SHADOW,
    assignment_unit: str = ASSIGNMENT_PROMPT,
    topic_epoch: str | None = None,
    rollout_rate: float = 1.0,
) -> dict[str, Any]:
    resolved_registry_path = registry_path or registry_paths(registry_dir)[0]
    rows = load_working_memory(working_memory_path or default_working_memory_path(resolved_registry_path))
    baseline_rows, dream_rows = split_working_memory_rows(rows)
    event = build_shadow_prompt_event(
        prompt=prompt,
        session_id=str(hook_input.get("session_id") or hook_input.get("thread_id") or ""),
        turn_id=str(hook_input.get("turn_id") or ""),
        topic_epoch=topic_epoch or str(hook_input.get("topic_epoch") or ""),
        baseline_rows=baseline_rows,
        dream_rows=dream_rows,
        project_label=project_label,
        salt=salt,
        source="prompt_hook_shadow",
        delivery_mode=delivery_mode,
        assignment_unit=assignment_unit,
        rollout_rate=rollout_rate,
    )
    append_event(event_log or default_event_log(registry_dir), event)
    return event


def optional_path(value: object) -> Path | None:
    return Path(str(value)) if value else None


def record_prompt_shadow_from_hook_args(
    *,
    prompt: str,
    hook_input: Mapping[str, Any],
    args: Any,
) -> dict[str, Any]:
    return record_prompt_shadow_from_hook(
        prompt=prompt,
        hook_input=hook_input
        or {
            "session_id": getattr(args, "session_id", "") or "",
            "turn_id": getattr(args, "topic_epoch", "") or "",
            "topic_epoch": getattr(args, "topic_epoch", "") or "",
        },
        registry_dir=optional_path(getattr(args, "registry_dir", None)),
        registry_path=optional_path(getattr(args, "registry", None)),
        working_memory_path=optional_path(getattr(args, "working_memory", None)),
        event_log=optional_path(getattr(args, "dream_shadow_log", None)),
        salt=getattr(args, "dream_shadow_salt", None) or DEFAULT_SALT,
        delivery_mode=getattr(args, "dream_delivery_mode", DELIVERY_SHADOW),
        assignment_unit=getattr(args, "dream_assignment_unit", ASSIGNMENT_PROMPT),
        topic_epoch=getattr(args, "topic_epoch", None),
        rollout_rate=getattr(args, "dream_rollout_rate", 1.0),
    )


def clean_source_messages_path(entry: Mapping[str, Any], thread_key: str, registry_dir: Path | None) -> Path:
    paths = entry.get("paths") if isinstance(entry.get("paths"), Mapping) else {}
    explicit = paths.get("clean_source_messages_jsonl") if isinstance(paths, Mapping) else None
    if explicit:
        return Path(str(explicit))
    return thread_store_dir(thread_key, registry_dir) / "clean-source" / "messages.jsonl"


def clean_source_dir_messages_path(clean_source_dir: Path) -> Path:
    path = clean_source_dir / "messages.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"clean-source messages not found: {path}")
    return path


def clean_source_message_thread_key(message: Mapping[str, Any], *, dataset_id: str) -> str:
    source_id = str(
        message.get("source_id")
        or message.get("conversation_id")
        or message.get("thread_key")
        or message.get("session_id")
        or ""
    )
    if not source_id:
        source_id = stable_hash(
            [message.get("message_id"), message.get("turn_id"), message.get("source_line")],
            prefix="source",
            length=12,
        )
    return f"{dataset_id}:{source_id}"


def clean_source_message_order(message: Mapping[str, Any], fallback: int) -> int:
    for key in ("clean_ordinal", "source_line", "turn_index"):
        value = message.get(key)
        try:
            return int(str(value))
        except (TypeError, ValueError):
            continue
    return fallback


def replay_clean_source_dir_events(
    *,
    clean_source_dir: Path,
    dataset_id: str,
    registry_dir: Path | None = None,
    working_memory_path: Path | None = None,
    max_threads: int = 200,
    max_user_messages: int = 2000,
    salt: str = DEFAULT_SALT,
    project_label: str | None = "AIppocampus",
    generated_dream_max_packs: int = 0,
    dream_worker_mode: str = DEFAULT_DREAM_WORKER_MODE,
    model_config: ChatClientConfig | None = None,
    max_samples: int = 1,
    semantic_relevance_config: ChatClientConfig | None = None,
    semantic_relevance_min_confidence: float = 0.65,
    semantic_relevance_max_candidates: int = 32,
) -> list[dict[str, Any]]:
    rows = load_shadow_working_memory_rows(
        registry_dir=registry_dir,
        working_memory_path=working_memory_path,
        generated_dream_max_packs=generated_dream_max_packs,
        dream_worker_mode=dream_worker_mode,
        model_config=model_config,
        max_samples=max_samples,
    )
    baseline_rows, dream_rows = split_working_memory_rows(rows)
    events: list[dict[str, Any]] = []
    seen_threads: set[str] = set()
    per_thread_user_counts: dict[str, int] = defaultdict(int)
    messages_path = clean_source_dir_messages_path(clean_source_dir)
    target_thread_count = max(1, int(max_threads))
    target_message_count = max(1, int(max_user_messages))
    for message in iter_jsonl(messages_path):
        if len(events) >= target_message_count:
            break
        if str(message.get("role") or "") != "user":
            continue
        thread_key = clean_source_message_thread_key(message, dataset_id=dataset_id)
        if thread_key not in seen_threads:
            if len(seen_threads) >= target_thread_count:
                break
            seen_threads.add(thread_key)
        per_thread_user_counts[thread_key] += 1
        events.append(
            build_shadow_prompt_event(
                prompt=str(message.get("text") or ""),
                session_id=thread_key,
                turn_id=str(message.get("turn_id") or message.get("message_id") or ""),
                user_turn_index=clean_source_message_order(
                    message,
                    per_thread_user_counts[thread_key],
                ),
                baseline_rows=baseline_rows,
                dream_rows=dream_rows,
                project_label=project_label,
                salt=salt,
                timestamp=str(message.get("timestamp") or now_utc()),
                source="benchmark_clean_source_shadow_replay",
                delivery_mode="benchmark_historical_shadow_replay",
                semantic_relevance_config=semantic_relevance_config,
                semantic_relevance_min_confidence=semantic_relevance_min_confidence,
                semantic_relevance_max_candidates=semantic_relevance_max_candidates,
            )
        )
    return events


def replay_clean_source_events(
    *,
    registry_dir: Path | None = None,
    working_memory_path: Path | None = None,
    max_threads: int = 200,
    max_user_messages: int = 2000,
    salt: str = DEFAULT_SALT,
    project_label: str | None = "AIppocampus",
    generated_dream_max_packs: int = 0,
    dream_worker_mode: str = DEFAULT_DREAM_WORKER_MODE,
    model_config: ChatClientConfig | None = None,
    max_samples: int = 1,
    semantic_relevance_config: ChatClientConfig | None = None,
    semantic_relevance_min_confidence: float = 0.65,
    semantic_relevance_max_candidates: int = 32,
) -> list[dict[str, Any]]:
    registry_path, _ = registry_paths(registry_dir)
    registry = load_registry(registry_path)
    rows = load_shadow_working_memory_rows(
        registry_dir=registry_dir,
        working_memory_path=working_memory_path,
        generated_dream_max_packs=generated_dream_max_packs,
        dream_worker_mode=dream_worker_mode,
        model_config=model_config,
        max_samples=max_samples,
    )
    baseline_rows, dream_rows = split_working_memory_rows(rows)
    events: list[dict[str, Any]] = []
    for entry in registry.get("threads") or []:
        if len(events) >= max_user_messages or len({event["thread_fingerprint"] for event in events}) >= max_threads:
            break
        if not isinstance(entry, Mapping):
            continue
        thread_key = str(entry.get("thread_key") or "")
        if not thread_key:
            continue
        path = clean_source_messages_path(entry, thread_key, registry_dir)
        for message in iter_jsonl(path):
            if len(events) >= max_user_messages:
                break
            if str(message.get("role") or "") != "user":
                continue
            events.append(
                build_shadow_prompt_event(
                    prompt=str(message.get("text") or ""),
                    session_id=thread_key,
                    turn_id=str(message.get("turn_id") or message.get("message_id") or ""),
                    user_turn_index=int(message.get("turn_index") or len(events)),
                    baseline_rows=baseline_rows,
                    dream_rows=dream_rows,
                    project_label=project_label,
                    salt=salt,
                    timestamp=str(message.get("timestamp") or now_utc()),
                    source="clean_source_shadow_replay",
                    delivery_mode="historical_shadow_replay",
                    semantic_relevance_config=semantic_relevance_config,
                    semantic_relevance_min_confidence=semantic_relevance_min_confidence,
                    semantic_relevance_max_candidates=semantic_relevance_max_candidates,
                )
            )
    return events


def run_clean_source_replay_analysis(
    *,
    registry_dir: Path | None = None,
    working_memory_path: Path | None = None,
    max_threads: int = 200,
    max_user_messages: int = 2000,
    window_user_turns: int = 4,
    salt: str = DEFAULT_SALT,
    generated_dream_max_packs: int = 0,
    dream_worker_mode: str = DEFAULT_DREAM_WORKER_MODE,
    model_config: ChatClientConfig | None = None,
    max_samples: int = 1,
    semantic_relevance_config: ChatClientConfig | None = None,
    semantic_relevance_min_confidence: float = 0.65,
    semantic_relevance_max_candidates: int = 32,
) -> dict[str, Any]:
    events = replay_clean_source_events(
        registry_dir=registry_dir,
        working_memory_path=working_memory_path,
        max_threads=max_threads,
        max_user_messages=max_user_messages,
        salt=salt,
        generated_dream_max_packs=generated_dream_max_packs,
        dream_worker_mode=dream_worker_mode,
        model_config=model_config,
        max_samples=max_samples,
        semantic_relevance_config=semantic_relevance_config,
        semantic_relevance_min_confidence=semantic_relevance_min_confidence,
        semantic_relevance_max_candidates=semantic_relevance_max_candidates,
    )
    metrics = analyze_shadow_events(events, window_user_turns=window_user_turns)
    metrics["generated_dream_max_packs"] = generated_dream_max_packs
    metrics["dream_worker_mode"] = dream_worker_mode
    metrics["semantic_relevance_gate_enabled"] = semantic_relevance_config is not None
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ANALYSIS_KIND,
        "created_at": now_utc(),
        "status": "analyzed" if events else "no_events",
        "claim_level": "historical_shadow_replay_reminder_frequency",
        "private_text_emitted": False,
        "metrics": metrics,
        "can_claim": [
            "historical_clean_source_replay_counted_explicit_recall_reminders",
            "shadow_assignment_and_nearest_prior_attribution_ran",
        ],
        "cannot_claim": [
            "causal_real_user_behavior_lift_without_delivered_treatment",
            "time_causal_dream_availability_without_live_event_log",
            "general_dream_quality",
            "full_history_coverage",
        ],
    }


def run_clean_source_dir_replay_analysis(
    *,
    clean_source_dir: Path,
    dataset_id: str,
    registry_dir: Path | None = None,
    working_memory_path: Path | None = None,
    max_threads: int = 200,
    max_user_messages: int = 2000,
    window_user_turns: int = 4,
    salt: str = DEFAULT_SALT,
    generated_dream_max_packs: int = 0,
    dream_worker_mode: str = DEFAULT_DREAM_WORKER_MODE,
    model_config: ChatClientConfig | None = None,
    max_samples: int = 1,
    semantic_relevance_config: ChatClientConfig | None = None,
    semantic_relevance_min_confidence: float = 0.65,
    semantic_relevance_max_candidates: int = 32,
) -> dict[str, Any]:
    events = replay_clean_source_dir_events(
        clean_source_dir=clean_source_dir,
        dataset_id=dataset_id,
        registry_dir=registry_dir,
        working_memory_path=working_memory_path,
        max_threads=max_threads,
        max_user_messages=max_user_messages,
        salt=salt,
        generated_dream_max_packs=generated_dream_max_packs,
        dream_worker_mode=dream_worker_mode,
        model_config=model_config,
        max_samples=max_samples,
        semantic_relevance_config=semantic_relevance_config,
        semantic_relevance_min_confidence=semantic_relevance_min_confidence,
        semantic_relevance_max_candidates=semantic_relevance_max_candidates,
    )
    metrics = analyze_shadow_events(events, window_user_turns=window_user_turns)
    metrics["generated_dream_max_packs"] = generated_dream_max_packs
    metrics["dream_worker_mode"] = dream_worker_mode
    metrics["semantic_relevance_gate_enabled"] = semantic_relevance_config is not None
    metrics["benchmark_corpus"] = {
        "dataset_id": dataset_id,
        "clean_source_dir_name": clean_source_dir.name,
        "raw_clean_source_path_emitted": False,
        "source": "benchmark_corpus_clean_source_messages",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ANALYSIS_KIND,
        "created_at": now_utc(),
        "status": "analyzed" if events else "no_events",
        "claim_level": "benchmark_corpus_shadow_replay_reminder_frequency",
        "private_text_emitted": False,
        "metrics": metrics,
        "can_claim": [
            "benchmark_corpus_clean_source_replay_counted_explicit_recall_reminders",
            "benchmark_corpus_shadow_false_activation_rate_measured",
            "shadow_assignment_and_nearest_prior_attribution_ran",
        ],
        "cannot_claim": [
            "causal_real_user_behavior_lift_without_delivered_treatment",
            "private_real_history_behavior_lift",
            "time_causal_dream_availability_without_live_event_log",
            "general_dream_quality",
            "full_public_corpus_coverage_unless_limits_cover_manifest_counts",
        ],
    }


def normalized_worker_mode(value: str) -> str:
    mode = str(value or DEFAULT_DREAM_WORKER_MODE).strip().replace("-", "_")
    if mode not in {DEFAULT_DREAM_WORKER_MODE, MODEL_BACKED_DREAM_WORKER_MODE}:
        raise ValueError("dream worker mode must be deterministic or model_backed")
    return mode


def dream_model_config_from_args(args: Any) -> tuple[ChatClientConfig, dict[str, Any]]:
    route_name = getattr(args, "model_route", None)
    model = str(getattr(args, "model", "") or "")
    base_url = str(getattr(args, "base_url", "") or "")
    api_key_env_arg = str(getattr(args, "api_key_env", DEFAULT_DEEPSEEK_API_KEY_ENV) or DEFAULT_DEEPSEEK_API_KEY_ENV)
    explicit_model = model if model and not route_name else None
    explicit_base_url = base_url if base_url and not route_name else None
    explicit_api_key_env = (
        api_key_env_arg
        if not is_default_deepseek_api_key_env(api_key_env_arg) and not route_name
        else None
    )
    route = resolve_model_route(
        route_name,
        explicit_model=explicit_model,
        explicit_base_url=explicit_base_url,
        explicit_api_key_env=explicit_api_key_env,
    )
    resolved_model = route.model if not model else model
    resolved_base_url = route.base_url if not base_url else base_url
    resolved_api_key_env = (
        route.api_key_env
        if is_default_deepseek_api_key_env(api_key_env_arg)
        else api_key_env_arg
    )
    key_value = os.environ.get(resolved_api_key_env)
    if not key_value:
        raise RuntimeError(
            f"missing {route_service_name(route)} key; set {resolved_api_key_env} or pass --api-key-env"
        )
    capabilities = route.capabilities
    thinking_value = resolve_route_thinking(
        route,
        str(getattr(args, "dream_model_thinking", "auto") or "auto"),
    )
    reasoning_effort_value = resolve_route_reasoning_effort(
        route,
        str(getattr(args, "dream_model_reasoning_effort", "auto") or "auto"),
        thinking=thinking_value,
    )
    config = ChatClientConfig(
        api_key=str(key_value),
        model=resolved_model,
        base_url=resolved_base_url,
        max_tokens=getattr(args, "max_tokens", None),
        timeout=float(getattr(args, "dream_model_timeout", 60.0) or 60.0),
        temperature=float(getattr(args, "dream_model_temperature", 0.0) or 0.0),
        service_name=route_service_name(route),
        thinking=thinking_value,
        reasoning_effort=reasoning_effort_value,
        response_format_json=bool(getattr(capabilities, "supports_json_response", True)),
        cache_contract=route_cache_contract(route),
    )
    return config, route_payload_with_effective_values(
        route,
        model=resolved_model,
        base_url=resolved_base_url,
        api_key_env=resolved_api_key_env,
    )


def test_event(
    *,
    index: int,
    arm: str = "control",
    eligible: bool = True,
    reminder: bool = False,
    thread: str = "thread-a",
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EVENT_KIND,
        "created_at": f"2026-05-30T00:00:{index:02d}Z",
        "source": "unit_test",
        "event_id": f"event-{thread}-{index}",
        "thread_fingerprint": stable_hash(thread, prefix="threadfp", salt="unit-test"),
        "user_turn_index": index,
        "assigned_arm": arm,
        "delivered_arm": None,
        "eligible_exposure": eligible,
        "reminder": {"is_reminder": reminder, "family": "unit", "strength": "high" if reminder else "none"},
        "baseline": {"match_count": 0, "decision": "miss"},
        "dream": {"match_count": 1 if eligible else 0, "decision": "match" if eligible else "miss"},
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record or analyze dream live shadow A/B events.")
    parser.add_argument("--registry-dir", type=Path)
    parser.add_argument("--working-memory", type=Path)
    parser.add_argument("--event-log", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--window-user-turns", type=int, default=4)
    parser.add_argument("--salt", default=DEFAULT_SALT)
    sub = parser.add_mutually_exclusive_group()
    sub.add_argument("--analyze-log", action="store_true")
    sub.add_argument("--replay-clean-source", action="store_true")
    sub.add_argument("--replay-clean-source-dir", type=Path)
    parser.add_argument("--dataset-id", default="benchmark_corpus")
    parser.add_argument("--max-threads", type=int, default=200)
    parser.add_argument("--max-user-messages", type=int, default=2000)
    parser.add_argument(
        "--generate-dream-rows",
        type=int,
        default=0,
        help="For clean-source replay only, generate this many selected dream packs in memory.",
    )
    parser.add_argument(
        "--dream-worker-mode",
        choices=["deterministic", "model-backed", "model_backed"],
        default=DEFAULT_DREAM_WORKER_MODE,
        help="Dream row generation mode for --generate-dream-rows.",
    )
    parser.add_argument("--model-route", default=None)
    parser.add_argument("--model", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--api-key-env", default=DEFAULT_DEEPSEEK_API_KEY_ENV)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--dream-model-timeout", type=float, default=60.0)
    parser.add_argument("--dream-model-temperature", type=float, default=0.0)
    parser.add_argument(
        "--dream-model-thinking",
        choices=["auto", "enabled", "disabled", "provider"],
        default="auto",
    )
    parser.add_argument(
        "--dream-model-reasoning-effort",
        choices=["auto", "high", "max", "provider"],
        default="auto",
    )
    parser.add_argument("--dream-max-samples", type=int, default=1)
    parser.add_argument(
        "--semantic-relevance-gate",
        action="store_true",
        help="Opt-in model semantic relevance gate for shadow replay; sends replay prompts to the configured model.",
    )
    parser.add_argument("--semantic-relevance-min-confidence", type=float, default=0.65)
    parser.add_argument("--semantic-relevance-max-candidates", type=int, default=32)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    event_log = args.event_log or default_event_log(args.registry_dir)
    dream_worker_mode = normalized_worker_mode(args.dream_worker_mode)
    model_config = None
    model_route_payload = None
    if (
        dream_worker_mode == MODEL_BACKED_DREAM_WORKER_MODE
        and args.generate_dream_rows > 0
    ) or args.semantic_relevance_gate:
        model_config, model_route_payload = dream_model_config_from_args(args)
    semantic_relevance_config = model_config if args.semantic_relevance_gate else None
    if args.replay_clean_source_dir:
        payload = run_clean_source_dir_replay_analysis(
            clean_source_dir=args.replay_clean_source_dir,
            dataset_id=args.dataset_id,
            registry_dir=args.registry_dir,
            working_memory_path=args.working_memory,
            max_threads=args.max_threads,
            max_user_messages=args.max_user_messages,
            window_user_turns=args.window_user_turns,
            salt=args.salt,
            generated_dream_max_packs=args.generate_dream_rows,
            dream_worker_mode=dream_worker_mode,
            model_config=model_config,
            max_samples=args.dream_max_samples,
            semantic_relevance_config=semantic_relevance_config,
            semantic_relevance_min_confidence=args.semantic_relevance_min_confidence,
            semantic_relevance_max_candidates=args.semantic_relevance_max_candidates,
        )
    elif args.replay_clean_source:
        payload = run_clean_source_replay_analysis(
            registry_dir=args.registry_dir,
            working_memory_path=args.working_memory,
            max_threads=args.max_threads,
            max_user_messages=args.max_user_messages,
            window_user_turns=args.window_user_turns,
            salt=args.salt,
            generated_dream_max_packs=args.generate_dream_rows,
            dream_worker_mode=dream_worker_mode,
            model_config=model_config,
            max_samples=args.dream_max_samples,
            semantic_relevance_config=semantic_relevance_config,
            semantic_relevance_min_confidence=args.semantic_relevance_min_confidence,
            semantic_relevance_max_candidates=args.semantic_relevance_max_candidates,
        )
    else:
        payload = run_shadow_ab_analysis(event_log=event_log, window_user_turns=args.window_user_turns)
    if model_route_payload and isinstance(payload.get("metrics"), dict):
        if dream_worker_mode == MODEL_BACKED_DREAM_WORKER_MODE and args.generate_dream_rows > 0:
            payload["metrics"]["dream_model_route"] = model_route_payload
        if args.semantic_relevance_gate:
            payload["metrics"]["semantic_relevance_model_route"] = model_route_payload
    text = json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
