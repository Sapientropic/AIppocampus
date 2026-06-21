#!/usr/bin/env python3
"""Sanitized benchmark runner for warm ambient recall.

The runner has two modes:
- deterministic fixture mode for CI and regression checks
- optional live-model mode for small real calibration runs when an API key is
  present

Outputs contain hashes and aggregate metrics only. Raw prompts, prompt traces,
cards, and model text stay out of the benchmark payload so live runs can be
shared as evidence without leaking local memory content.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.core import compact_text, sanitize_external_model_text
from aippocampus_runtime.warm_ambient import recall as warm
from aippocampus_runtime.warm_ambient.scout_profiles import scheduler_lifecycle_status

DEFAULT_CASE_WORKERS = 1


@dataclass(frozen=True)
class WarmBenchmarkCase:
    case_id: str
    prompt: str
    prompt_trace: list[dict[str, Any]]
    current_thread_key: str | None = None
    topic_epoch: str | None = None
    expected_available: bool | None = True
    expected_min_cards: int = 1
    expected_topic_epoch_action: str | None = None
    expected_topic_epoch_actions: tuple[str, ...] = ()
    expected_min_source_validation_statuses: dict[str, int] | None = None
    expected_min_current_thread_echo_count: int | None = None
    expected_max_current_thread_echo_count: int | None = None
    expected_mode: str | None = None


BUILTIN_CASES = (
    WarmBenchmarkCase(
        case_id="ambient_recall_design_continuity",
        prompt="那个脑内续接器现在怎么样了？",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "user",
                "phase": "recent_prompt",
                "text": "继续推进 ambient recall 的 10x5 scout 设计。",
            }
        ],
    ),
    WarmBenchmarkCase(
        case_id="source_ref_echo_guard",
        prompt="继续刚才 source-ref validation 和 echo penalty 的校准。",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "assistant",
                "phase": "final_answer",
                "text": "source-ref validation 已经落地，当前线程 echo 默认压制。",
                "source_refs": [{"thread_key": "session:ambient-current", "message_id": "m-current"}],
            }
        ],
        current_thread_key="session:ambient-current",
    ),
    WarmBenchmarkCase(
        case_id="cross_domain_style_bridge",
        prompt="这个跨界联想 scout 会不会比普通 query expansion 更像人类记忆？",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "user",
                "phase": "recent_prompt",
                "text": "用户在比较技术问题和人类记忆体感之间的桥接。",
            }
        ],
    ),
    WarmBenchmarkCase(
        case_id="style_preference_continuity",
        prompt="继续校准用户表达习惯和中文节奏，不要把它说成硬事实。",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "user",
                "phase": "recent_prompt",
                "text": "用户偏好中文、短段落、先结论后细节。",
            }
        ],
    ),
    WarmBenchmarkCase(
        case_id="trajectory_phase_match",
        prompt="现在这条 ambient recall 线应该进入后台 job 闭环了。",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "assistant",
                "phase": "final_answer",
                "text": "下一步是 foreground cache-first + detached wait-all warm job。",
            }
        ],
    ),
    WarmBenchmarkCase(
        case_id="dream_residue_handoff",
        prompt="这些用完即丢的 cache residue 能不能之后给 dream task 当素材？",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "user",
                "phase": "recent_prompt",
                "text": "cache residue should become dream seed only, not memory truth.",
            }
        ],
    ),
    WarmBenchmarkCase(
        case_id="bilingual_memory_bridge",
        prompt="这个 source-backed recall card 的 visibility bias 怎么调？",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "user",
                "phase": "recent_prompt",
                "text": "中文讨论里夹了 source-backed recall card 和 visibility bias。",
            }
        ],
    ),
    WarmBenchmarkCase(
        case_id="topic_epoch_rotation",
        prompt="话题从 prompt cache 转到 topic epoch rotation 了。",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "assistant",
                "phase": "final_answer",
                "text": "Topic epoch rotation should be judged by scouts, not hard-coded rules.",
            }
        ],
        expected_topic_epoch_action="reuse",
    ),
    WarmBenchmarkCase(
        case_id="privacy_credential_block",
        prompt="帮我回忆一下这个 api key token cookie 应该怎么处理。",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "user",
                "phase": "recent_prompt",
                "text": "credential-like prompt should force privacy guard block.",
            }
        ],
        expected_available=False,
        expected_min_cards=0,
    ),
    WarmBenchmarkCase(
        case_id="source_validation_guardrail",
        prompt="如果 scout 编了 source_ref，merge 层应该怎么降级？",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "assistant",
                "phase": "final_answer",
                "text": "Unsupported source refs must downgrade evidence to candidate.",
            }
        ],
    ),
    WarmBenchmarkCase(
        case_id="nudge_tone_crafting",
        prompt="Nudge writer 要安静一点，像旁边递一句提醒。",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "user",
                "phase": "recent_prompt",
                "text": "Nudge should stay private and quiet.",
            }
        ],
    ),
    WarmBenchmarkCase(
        case_id="semantic_expander_cold_path",
        prompt="Semantic expander 先服务冷路径和下一轮，不要抢 P0。",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "assistant",
                "phase": "final_answer",
                "text": "Semantic expander is P1 and feeds cold path aliases.",
            }
        ],
    ),
    WarmBenchmarkCase(
        case_id="deep_archival_original_wording",
        prompt="你能找回那句 continuity survives transformation 的原话吗？",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "user",
                "phase": "recent_prompt",
                "text": "The user asks for exact original wording, so source-backed deep archival recall is appropriate.",
            }
        ],
        expected_mode="deep_archival_recall",
    ),
)


def load_cases_file(path: Path | str) -> tuple[WarmBenchmarkCase, ...]:
    target = Path(path)
    if target.suffix.casefold() == ".jsonl":
        raw_items = [
            json.loads(line)
            for line in target.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        raw_items = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw_items, list):
        raise ValueError("warm benchmark cases file must contain a JSON array or JSONL objects")
    cases: list[WarmBenchmarkCase] = []
    for idx, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"case #{idx} must be an object")
        prompt_trace = item.get("prompt_trace") or []
        if not isinstance(prompt_trace, list):
            raise ValueError(f"case #{idx} prompt_trace must be a list")
        cases.append(
            WarmBenchmarkCase(
                case_id=safe_case_id(str(item.get("case_id") or f"case_{idx}")),
                prompt=str(item.get("prompt") or ""),
                prompt_trace=prompt_trace,
                current_thread_key=str(item.get("current_thread_key") or "") or None,
                topic_epoch=str(item.get("topic_epoch") or "") or None,
                expected_available=item.get("expected_available", True),
                expected_min_cards=int(item.get("expected_min_cards", 1) or 0),
                expected_topic_epoch_action=str(item.get("expected_topic_epoch_action") or "") or None,
                expected_topic_epoch_actions=parse_expected_actions(
                    item.get("expected_topic_epoch_actions")
                ),
                expected_min_source_validation_statuses=parse_expected_count_map(
                    item.get("expected_min_source_validation_statuses")
                ),
                expected_min_current_thread_echo_count=optional_int(
                    item.get("expected_min_current_thread_echo_count")
                ),
                expected_max_current_thread_echo_count=optional_int(
                    item.get("expected_max_current_thread_echo_count")
                ),
                expected_mode=str(item.get("expected_mode") or "") or None,
            )
        )
    return tuple(cases)


def optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_expected_actions(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple)):
        values = value
    else:
        values = []
    actions = [
        compact_text(str(item or "").strip().casefold(), 32)
        for item in values
        if str(item or "").strip()
    ]
    return tuple(dict.fromkeys(actions))


def parse_expected_count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, raw_count in value.items():
        label = compact_text(str(key or "").strip(), 80)
        count = optional_int(raw_count)
        if label and count is not None and count > 0:
            result[label] = count
    return result


def resolve_case_workers(*, case_count: int, case_workers: int | None) -> int:
    requested = int(case_workers if case_workers is not None else DEFAULT_CASE_WORKERS)
    if requested > 0:
        return requested
    # Auto mode is intentionally more conservative than the semantic-gate
    # benchmark: each warm case can itself launch 50 scout lanes, so resolving
    # 100 cases to 50 outer workers would create thousands of simultaneous
    # provider calls. Four outer workers keeps long live runs observable without
    # turning 10x5 scout parallelism into an accidental load test.
    return max(1, min(4, (max(1, int(case_count)) + 24) // 25))


def select_cases(
    source_cases: tuple[WarmBenchmarkCase, ...],
    *,
    case_offset: int = 0,
    case_limit: int | None = None,
) -> list[WarmBenchmarkCase]:
    start = max(0, int(case_offset or 0))
    end = None if case_limit is None else start + max(0, int(case_limit))
    return list(source_cases[start:end])


def write_progress_row(progress_jsonl: Path | str | None, row: dict[str, Any]) -> None:
    if not progress_jsonl:
        return
    target = Path(progress_jsonl)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _usage_int(usage: dict[str, Any], key: str) -> int:
    try:
        return int(usage.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def summarize_scout_usage_by_family(scouts: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    by_family: dict[str, dict[str, int]] = {}
    for row in scouts:
        family = str(row.get("scout_family") or "unknown")
        usage = row.get("usage") if isinstance(row.get("usage"), dict) else {}
        bucket = by_family.setdefault(
            family,
            {
                "scout_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "prompt_cache_hit_tokens": 0,
                "prompt_cache_miss_tokens": 0,
            },
        )
        bucket["scout_count"] += 1
        for key in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "prompt_cache_hit_tokens",
            "prompt_cache_miss_tokens",
        ):
            bucket[key] += _usage_int(usage, key)
    return by_family


ROI_COUNTER_KEYS = (
    "scout_count",
    "useful_result_count",
    "card_candidate_count",
    "accepted_card_count",
    "evidence_candidate_count",
    "accepted_evidence_count",
    "blocker_count",
    "late_useful_result_count",
    "unobserved_count",
    "error_count",
    "timeout_count",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens",
)
ROI_RATE_FIELDS = (
    ("useful_result_rate", "useful_result_count"),
    ("card_candidate_rate", "card_candidate_count"),
    ("accepted_card_rate", "accepted_card_count"),
    ("evidence_candidate_rate", "evidence_candidate_count"),
    ("accepted_evidence_rate", "accepted_evidence_count"),
    ("blocker_rate", "blocker_count"),
    ("late_useful_result_rate", "late_useful_result_count"),
    ("unobserved_rate", "unobserved_count"),
    ("error_rate", "error_count"),
    ("timeout_rate", "timeout_count"),
)
def _empty_roi_bucket() -> dict[str, Any]:
    return {key: 0 for key in ROI_COUNTER_KEYS}


def _safe_rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _roi_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _row_timeout(row: dict[str, Any]) -> bool:
    text = " ".join(
        [
            str(row.get("error_kind") or ""),
            str(row.get("reason") or ""),
        ]
    ).casefold()
    return "timeout" in text or "timed out" in text


def _roi_classification(bucket: dict[str, Any]) -> str:
    if (
        int(bucket.get("blocker_count") or 0) > 0
        and int(bucket.get("card_candidate_count") or 0) == 0
        and int(bucket.get("evidence_candidate_count") or 0) == 0
    ):
        return "diagnostic_only"
    if (
        int(bucket.get("useful_result_count") or 0) > 0
        or int(bucket.get("card_candidate_count") or 0) > 0
        or int(bucket.get("accepted_card_count") or 0) > 0
        or int(bucket.get("evidence_candidate_count") or 0) > 0
        or int(bucket.get("accepted_evidence_count") or 0) > 0
        or int(bucket.get("late_useful_result_count") or 0) > 0
    ):
        return "keep"
    return "watch"


def _finalize_roi_bucket(bucket: dict[str, Any], *, scout: str) -> dict[str, Any]:
    scout_count = int(bucket.get("scout_count") or 0)
    configured_count = scout_count + int(bucket.get("unobserved_count") or 0)
    finalized: dict[str, Any] = {key: int(bucket.get(key) or 0) for key in ROI_COUNTER_KEYS}
    for rate_name, count_name in ROI_RATE_FIELDS:
        denominator = configured_count if count_name == "unobserved_count" else scout_count
        finalized[rate_name] = _safe_rate(int(finalized.get(count_name) or 0), denominator)
    cache_total = finalized["prompt_cache_hit_tokens"] + finalized["prompt_cache_miss_tokens"]
    finalized["prompt_cache_hit_rate"] = _safe_rate(
        finalized["prompt_cache_hit_tokens"], cache_total
    )
    finalized["classification"] = _roi_classification(finalized)
    finalized["scheduler_lifecycle_status"] = scheduler_lifecycle_status(scout, finalized)
    return finalized


def _bump_roi_bucket(bucket: dict[str, Any], row: dict[str, Any], *, late_useful: bool) -> None:
    usage = row.get("usage") if isinstance(row.get("usage"), dict) else {}
    candidates = row.get("candidates") if isinstance(row.get("candidates"), list) else []
    evidence_count = sum(
        1 for card in candidates if str((card or {}).get("support_level") or "").casefold() == "evidence"
    )
    bucket["scout_count"] += 1
    if row.get("useful"):
        bucket["useful_result_count"] += 1
    bucket["card_candidate_count"] += len(candidates)
    bucket["evidence_candidate_count"] += evidence_count
    if row.get("ok") and row.get("block"):
        bucket["blocker_count"] += 1
    if late_useful:
        bucket["late_useful_result_count"] += 1
    if not row.get("ok"):
        bucket["error_count"] += 1
        if _row_timeout(row):
            bucket["timeout_count"] += 1
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
    ):
        bucket[key] += _usage_int(usage, key)


def _lane_family(lane: str) -> str:
    return str(lane or "").split(":", 1)[0] or "unknown"


def _card_source_lanes(card: dict[str, Any]) -> list[str]:
    lanes = [
        str(item or "").strip()
        for item in card.get("source_scouts") or []
        if str(item or "").strip()
    ]
    if not lanes and str(card.get("source_scout") or "").strip():
        lanes = [str(card.get("source_scout")).strip()]
    return list(dict.fromkeys(lanes))


def _add_accepted_card_contributions(
    *,
    cards: list[dict[str, Any]],
    by_lane: dict[str, dict[str, Any]],
    by_family: dict[str, dict[str, Any]],
) -> None:
    for card in cards:
        if not isinstance(card, dict):
            continue
        lanes = _card_source_lanes(card)
        if not lanes:
            continue
        is_evidence = str(card.get("support_level") or "").casefold() == "evidence"
        for lane in lanes:
            family = _lane_family(lane)
            lane_bucket = by_lane.setdefault(lane, _empty_roi_bucket())
            family_bucket = by_family.setdefault(family, _empty_roi_bucket())
            lane_bucket["accepted_card_count"] += 1
            family_bucket["accepted_card_count"] += 1
            if is_evidence:
                lane_bucket["accepted_evidence_count"] += 1
                family_bucket["accepted_evidence_count"] += 1


def summarize_scout_roi(
    scouts: list[dict[str, Any]],
    *,
    useful_quorum: int,
    cards: list[dict[str, Any]] | None = None,
    configured_scouts: list[str] | tuple[str, ...] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_lane: dict[str, dict[str, Any]] = {}
    by_family: dict[str, dict[str, Any]] = {}
    observed_lanes: set[str] = set()
    useful_seen = 0
    quorum = max(1, int(useful_quorum or warm.DEFAULT_QUORUM))
    for row in scouts:
        lane = str(row.get("scout") or "").strip() or "unknown"
        family = str(row.get("scout_family") or "").strip() or lane.split(":", 1)[0] or "unknown"
        observed_lanes.add(lane)
        late_marker = row.get("completed_after_quorum_cutoff")
        late_useful = (
            bool(row.get("useful"))
            and bool(late_marker)
            if late_marker is not None
            else bool(row.get("useful")) and useful_seen >= quorum
        )
        _bump_roi_bucket(by_lane.setdefault(lane, _empty_roi_bucket()), row, late_useful=late_useful)
        _bump_roi_bucket(
            by_family.setdefault(family, _empty_roi_bucket()), row, late_useful=late_useful
        )
        if row.get("useful"):
            useful_seen += 1
    for scout in configured_scouts or []:
        lane = str(scout or "").strip()
        if not lane or lane in observed_lanes:
            continue
        family = _lane_family(lane)
        by_lane.setdefault(lane, _empty_roi_bucket())["unobserved_count"] += 1
        by_family.setdefault(family, _empty_roi_bucket())["unobserved_count"] += 1
    _add_accepted_card_contributions(
        cards=cards or [], by_lane=by_lane, by_family=by_family
    )
    return (
        {
            key: _finalize_roi_bucket(value, scout=key)
            for key, value in sorted(by_lane.items())
        },
        {
            key: _finalize_roi_bucket(value, scout=key)
            for key, value in sorted(by_family.items())
        },
    )


def aggregate_scout_roi(
    cases: list[dict[str, Any]],
    key: str,
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for case in cases:
        table = case.get(key) if isinstance(case.get(key), dict) else {}
        for label, row in table.items():
            if not isinstance(row, dict):
                continue
            bucket = buckets.setdefault(str(label), _empty_roi_bucket())
            for counter in ROI_COUNTER_KEYS:
                bucket[counter] += _roi_int(row.get(counter))
    return {
        label: _finalize_roi_bucket(bucket, scout=label)
        for label, bucket in sorted(buckets.items())
    }


def scout_roi_classification_counts(table: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts = {"keep": 0, "watch": 0, "diagnostic_only": 0}
    for row in table.values():
        name = str((row or {}).get("classification") or "watch")
        if name not in counts:
            name = "watch"
        counts[name] += 1
    return {key: value for key, value in counts.items() if value}


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def safe_case_id(value: str) -> str:
    text, policy = sanitize_external_model_text(value)
    compact = compact_text(text.replace("\\", "/").strip(), 80)
    if policy.get("redacted") or not compact:
        return "case_" + sha1_text(str(value or ""))[:12]
    return compact


def deterministic_registry_fixture(workspace: Path) -> dict[str, Any]:
    clean_dir = workspace / "benchmark-clean-source"
    clean_dir.mkdir(parents=True, exist_ok=True)
    messages = clean_dir / "messages.jsonl"
    messages.write_text(
        json.dumps(
            {
                "message_id": "msg-benchmark-1",
                "source_line": 42,
                "role": "assistant",
                "phase": "final_answer",
                "is_final": True,
                "text": "The original wording was: continuity survives transformation.",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "schema_version": 1,
        "threads": [
            {
                "thread_key": "session:benchmark-source",
                "title": "Benchmark clean source",
                "paths": {"clean_source_messages_jsonl": str(messages)},
            }
        ],
    }


def deterministic_scout_fn(scout: str, payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    del kwargs
    family = scout.split(":", 1)[0]
    prompt = str(payload.get("prompt") or "")
    if "原话" in prompt or "original wording" in prompt.casefold():
        if family == "key_line_hunter":
            return {
                "decision": "evidence",
                "confidence": 0.88,
                "candidates": [
                    {
                        "theme": "original wording continuity",
                        "support_level": "evidence",
                        "visibility": "deep_archival_recall",
                        "key_line": "continuity survives transformation",
                        "matched_terms": ["continuity"],
                        "source_refs": [
                            {
                                "thread_key": "session:benchmark-source",
                                "line": 42,
                                "message_id": "msg-benchmark-1",
                            }
                        ],
                    }
                ],
            }
        return {"decision": "skip", "confidence": 0.1}
    if family == "privacy_boundary_guard" and any(token in prompt.casefold() for token in ("token", "cookie", "api key")):
        return {
            "decision": "skip",
            "confidence": 0.95,
            "block": True,
            "reason": "credential-like prompt",
            "negative_contexts": ["credential-like prompt"],
        }
    if family == "intent_mode_classifier":
        return {
            "decision": "candidate",
            "confidence": 0.74,
            "themes": ["warm ambient recall calibration"],
            "query_aliases": ["ambient recall", "warm scout"],
            "topic_epoch_action": "reuse",
            "topic_epoch_label": "warm ambient recall calibration",
        }
    if family == "key_line_hunter":
        return {
            "decision": "candidate",
            "confidence": 0.82,
            "candidates": [
                {
                    "theme": "ambient recall key-line continuity",
                    "support_level": "candidate",
                    "key_line": "brain-like recall should feel like peripheral awareness",
                    "matched_terms": ["ambient recall", "continuity"],
                }
            ],
        }
    if family == "cross_domain_bridge":
        return {
            "decision": "scent",
            "confidence": 0.66,
            "themes": ["technical memory and human-like association"],
            "query_aliases": ["cross-domain bridge"],
        }
    if family == "evidence_gap_sentinel":
        return {
            "decision": "candidate",
            "confidence": 0.7,
            "negative_contexts": ["do not present resonance as source-backed fact"],
        }
    if family == "deep_theme_matcher":
        return {
            "decision": "candidate",
            "confidence": 0.78,
            "themes": ["natural ambient recall"],
            "candidates": [
                {
                    "theme": "natural ambient recall",
                    "support_level": "candidate",
                    "matched_terms": ["ambient recall"],
                }
            ],
        }
    return {"decision": "skip", "confidence": 0.1}


def summarize_case(
    case: WarmBenchmarkCase,
    result: dict[str, Any],
    *,
    useful_quorum: int | None = None,
) -> dict[str, Any]:
    validation_statuses: dict[str, int] = {}
    for card in result.get("cards") or []:
        status = str((card.get("source_validation") or {}).get("status") or "missing")
        validation_statuses[status] = validation_statuses.get(status, 0) + 1
    scout_error_kinds: dict[str, int] = {}
    for row in result.get("scouts") or []:
        if row.get("ok"):
            continue
        kind = str(row.get("error_kind") or warm.scout_error_kind(row.get("reason")))
        scout_error_kinds[kind] = scout_error_kinds.get(kind, 0) + 1
    cache = result.get("cache") or {}
    cache_hit_rate = cache["hit_rate"] if "hit_rate" in cache else cache.get("prompt_cache_hit_rate")
    cache_hit_tokens = cache["hit_tokens"] if "hit_tokens" in cache else cache.get("prompt_cache_tokens")
    cache_miss_tokens = cache["miss_tokens"] if "miss_tokens" in cache else cache.get("prompt_cache_miss_tokens")
    scout_usage_by_family = summarize_scout_usage_by_family(result.get("scouts") or [])
    resolved_quorum = int(useful_quorum or result.get("quorum") or warm.DEFAULT_QUORUM)
    scout_roi_by_lane, scout_roi_by_family = summarize_scout_roi(
        result.get("scouts") or [],
        useful_quorum=resolved_quorum,
        cards=result.get("cards") or [],
        configured_scouts=result.get("configured_scouts") or [],
    )
    summary = {
        "case_id": case.case_id,
        "prompt_sha1": sha1_text(case.prompt),
        "available": bool(result.get("available")),
        "status": result.get("status"),
        "mode": result.get("mode"),
        "confidence": result.get("confidence"),
        "quorum_met": bool(result.get("quorum_met")),
        "useful_signal_quorum_met": bool(result.get("useful_signal_quorum_met")),
        "quorum": resolved_quorum,
        "batch_end_reason": result.get("batch_end_reason"),
        "configured_scout_count": int(result.get("scout_count") or 0),
        "max_workers": int(result.get("max_workers") or 0),
        "prefix_cache_warmup_scout_count": int(result.get("prefix_cache_warmup_scout_count") or 0),
        "observed_scout_result_count": len(result.get("scouts") or []),
        "accepted_scout_count": int(result.get("accepted_scout_count") or 0),
        "failed_scout_count": int(result.get("failed_scout_count") or 0),
        "trace_fallback_card_count": int(result.get("trace_fallback_card_count") or 0),
        "scout_error_kinds": scout_error_kinds,
        "card_count": len(result.get("cards") or []),
        "source_validation_statuses": validation_statuses,
        "topic_epoch_action": (result.get("topic_epoch_decision") or {}).get("action"),
        "current_thread_echo_count": int(result.get("current_thread_echo_count") or 0),
        "blocked_by": [
            str(item)
            for item in result.get("blocked_by") or []
            if str(item or "").strip()
        ],
        "guard_coverage": result.get("guard_coverage") or {},
        "elapsed_ms": float(result.get("elapsed_ms") or 0.0),
        "cache": {
            "available": cache.get("available"),
            "hit_rate": cache_hit_rate,
            "hit_tokens": cache_hit_tokens,
            "miss_tokens": cache_miss_tokens,
        },
        "scout_usage_by_family": scout_usage_by_family,
        "scout_roi_by_lane": scout_roi_by_lane,
        "scout_roi_by_family": scout_roi_by_family,
    }
    expectation_failures: list[str] = []
    if case.expected_available is not None and summary["available"] != case.expected_available:
        expectation_failures.append("available")
    if int(summary["card_count"]) < int(case.expected_min_cards):
        expectation_failures.append("min_cards")
    if (
        case.expected_topic_epoch_action
        and summary["topic_epoch_action"] != case.expected_topic_epoch_action
    ):
        expectation_failures.append("topic_epoch_action")
    if case.expected_topic_epoch_actions and summary["topic_epoch_action"] not in case.expected_topic_epoch_actions:
        expectation_failures.append("topic_epoch_action")
    for status, expected_count in (case.expected_min_source_validation_statuses or {}).items():
        if int(validation_statuses.get(status) or 0) < int(expected_count):
            expectation_failures.append(f"source_validation:{status}")
    echo_count = int(summary["current_thread_echo_count"])
    if (
        case.expected_min_current_thread_echo_count is not None
        and echo_count < case.expected_min_current_thread_echo_count
    ):
        expectation_failures.append("current_thread_echo:min")
    if (
        case.expected_max_current_thread_echo_count is not None
        and echo_count > case.expected_max_current_thread_echo_count
    ):
        expectation_failures.append("current_thread_echo:max")
    if case.expected_mode and summary["mode"] != case.expected_mode:
        expectation_failures.append("mode")
    summary["expectation_passed"] = not expectation_failures
    summary["expectation_failures"] = expectation_failures
    return summary


def run_warm_ambient_recall_benchmark(
    *,
    cwd: Path | str | None = None,
    case_offset: int = 0,
    case_limit: int | None = None,
    live: bool = False,
    wait_all: bool = True,
    timeout: float = 2.4,
    quorum: int = warm.DEFAULT_QUORUM,
    max_workers: int | None = None,
    case_workers: int | None = DEFAULT_CASE_WORKERS,
    prefix_cache_warmup_scouts: int = warm.DEFAULT_PREFIX_CACHE_WARMUP_SCOUTS,
    prefix_cache_warmup_delay: float = warm.DEFAULT_PREFIX_CACHE_WARMUP_DELAY,
    max_tokens: int | None = None,
    registry_path: Path | str | None = None,
    registry_dir: Path | str | None = None,
    cases_file: Path | str | None = None,
    api_key_env: str = "AIPPOCAMPUS_DEEPSEEK_API_KEY",
    user_id: str | None = None,
    progress_jsonl: Path | str | None = None,
    min_available_rate: float = 0.65,
    min_observed_scout_rate: float | None = None,
    min_case_pass_rate: float = 1.0,
    max_error_rate: float = 0.05,
    max_false_evidence_count: int = 0,
    max_missing_source_refs_count: int | None = None,
) -> dict[str, Any]:
    root_ctx = tempfile.TemporaryDirectory() if cwd is None else None
    try:
        workspace = Path(cwd or Path(root_ctx.name) / "workspace").resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        source_cases = load_cases_file(cases_file) if cases_file else BUILTIN_CASES
        cases = select_cases(source_cases, case_offset=case_offset, case_limit=case_limit)
        resolved_case_workers = resolve_case_workers(
            case_count=len(cases),
            case_workers=case_workers,
        )
        deterministic_registry = (
            deterministic_registry_fixture(workspace)
            if not live and not registry_path and not registry_dir
            else None
        )
        progress_lock = threading.Lock()
        summaries: list[dict[str, Any]] = []
        live_key = os.environ.get(api_key_env) if live else None
        if live and not live_key:
            return {
                "kind": "aippocampus_warm_ambient_recall_benchmark",
                "schema_version": 1,
                "ok": False,
                "status": "skipped_missing_api_key",
                "live_model": True,
                "metrics": {"case_count": 0},
                "config": {
                    "case_offset": max(0, int(case_offset or 0)),
                    "case_limit": case_limit,
                    "case_workers": resolved_case_workers,
                    "max_workers": max_workers,
                    "prefix_cache_warmup_scouts": prefix_cache_warmup_scouts,
                    "prefix_cache_warmup_delay": prefix_cache_warmup_delay,
                    "wait_all": wait_all,
                    "timeout": timeout,
                },
                "cases": [],
                "privacy_boundary": privacy_boundary(),
            }
        def run_case(case: WarmBenchmarkCase) -> dict[str, Any]:
            result = warm.run_warm_ambient_recall(
                case.prompt,
                cwd=workspace,
                thread_id=f"warm-benchmark-{case.case_id}",
                current_thread_key=case.current_thread_key,
                prompt_trace=case.prompt_trace,
                topic_epoch=case.topic_epoch,
                registry=deterministic_registry,
                registry_path=registry_path,
                registry_dir=registry_dir,
                cache_path=workspace / "ambient-thread-cache.json",
                api_key=live_key or "benchmark-key",
                user_id=user_id,
                timeout=timeout,
                quorum=quorum,
                max_workers=max_workers,
                prefix_cache_warmup_scouts=prefix_cache_warmup_scouts,
                prefix_cache_warmup_delay=prefix_cache_warmup_delay,
                max_tokens=max_tokens,
                wait_all=wait_all,
                no_write=True,
                scout_fn=warm.model_scout_fn if live else deterministic_scout_fn,
            )
            return summarize_case(case, result, useful_quorum=quorum)

        def record_case(index: int, summary: dict[str, Any]) -> None:
            with progress_lock:
                write_progress_row(
                    progress_jsonl,
                    {
                        "event": "case_completed",
                        "case_index": index,
                        "case": summary,
                    },
                )

        if resolved_case_workers <= 1 or len(cases) <= 1:
            for index, case in enumerate(cases, start=max(0, int(case_offset or 0))):
                summary = run_case(case)
                summaries.append(summary)
                record_case(index, summary)
        else:
            ordered: list[dict[str, Any] | None] = [None] * len(cases)
            with concurrent.futures.ThreadPoolExecutor(max_workers=resolved_case_workers) as executor:
                futures = {
                    executor.submit(run_case, case): offset
                    for offset, case in enumerate(cases)
                }
                for future in concurrent.futures.as_completed(futures):
                    offset = futures[future]
                    summary = future.result()
                    ordered[offset] = summary
                    record_case(max(0, int(case_offset or 0)) + offset, summary)
            summaries.extend(summary for summary in ordered if summary is not None)

        metrics = summarize_metrics(summaries)
        effective_min_observed = (
            float(min_observed_scout_rate)
            if min_observed_scout_rate is not None
            else 1.0
            if wait_all
            else max(0.0, min(1.0, quorum / max(1, len(warm.DEFAULT_SCOUTS))))
        )
        quality_gates = evaluate_quality_gates(
            summaries,
            min_available_rate=min_available_rate,
            min_observed_scout_rate=effective_min_observed,
            min_case_pass_rate=min_case_pass_rate,
            max_error_rate=max_error_rate,
            max_false_evidence_count=max_false_evidence_count,
            max_missing_source_refs_count=max_missing_source_refs_count,
        )
        return {
            "kind": "aippocampus_warm_ambient_recall_benchmark",
            "schema_version": 1,
            "ok": bool(summaries) and bool(quality_gates.get("passed")),
            "status": "sufficient" if summaries and quality_gates.get("passed") else "insufficient" if summaries else "empty",
            "live_model": live,
            "config": {
                "case_offset": max(0, int(case_offset or 0)),
                "case_limit": case_limit,
                "case_workers": resolved_case_workers,
                "max_workers": max_workers,
                "prefix_cache_warmup_scouts": prefix_cache_warmup_scouts,
                "prefix_cache_warmup_delay": prefix_cache_warmup_delay,
                "wait_all": wait_all,
                "timeout": timeout,
                "progress_jsonl": bool(progress_jsonl),
            },
            "metrics": metrics,
            "quality_gates": quality_gates,
            "cases": summaries,
            "privacy_boundary": privacy_boundary(),
            "cannot_claim": [
                "all_future_prompts_choose_the_right_memory",
                "model_quality_without_review",
                "per_lane_roi_proves_public_product_quality",
                "roi_classification_should_auto_delete_scout_lanes",
            ],
        }
    finally:
        if root_ctx is not None:
            root_ctx.cleanup()


def summarize_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(cases)
    total_observed = sum(int(case.get("observed_scout_result_count") or 0) for case in cases)
    total_configured = sum(int(case.get("configured_scout_count") or 0) for case in cases)
    total_prefix_warmup = sum(int(case.get("prefix_cache_warmup_scout_count") or 0) for case in cases)
    total_trace_fallback = sum(
        int(case.get("trace_fallback_card_count") or 0) for case in cases
    )
    available = sum(1 for case in cases if case.get("available"))
    cards = sum(int(case.get("card_count") or 0) for case in cases)
    total_failed = sum(int(case.get("failed_scout_count") or 0) for case in cases)
    case_passes = sum(1 for case in cases if case.get("expectation_passed"))
    false_evidence = sum(
        int((case.get("source_validation_statuses") or {}).get(status) or 0)
        for case in cases
        for status in ("unsupported", "missing_source_ref")
    )
    prompt_cache_hit_tokens = sum(int((case.get("cache") or {}).get("hit_tokens") or 0) for case in cases)
    prompt_cache_miss_tokens = sum(int((case.get("cache") or {}).get("miss_tokens") or 0) for case in cases)
    prompt_cache_total = prompt_cache_hit_tokens + prompt_cache_miss_tokens
    missing_source_refs = sum(
        int((case.get("source_validation_statuses") or {}).get("missing_source_refs") or 0)
        for case in cases
    )
    supported_source_refs = sum(
        int((case.get("source_validation_statuses") or {}).get("supported") or 0)
        for case in cases
    )
    source_addressable_cards = max(0, cards - missing_source_refs)
    accepted_cards = sum(int(case.get("accepted_card_count") or 0) for case in cases)
    elapsed = [float(case.get("elapsed_ms") or 0.0) for case in cases]
    scout_error_kinds: dict[str, int] = {}
    guard_coverage_state_counts: dict[str, int] = {}
    guard_coverage_incomplete_cases = 0
    guard_coverage_blocked_cases = 0
    scout_roi_by_lane = aggregate_scout_roi(cases, "scout_roi_by_lane")
    scout_roi_by_family = aggregate_scout_roi(cases, "scout_roi_by_family")
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    completion_tokens_by_family: dict[str, int] = {}
    prompt_cache_hit_tokens_by_family: dict[str, int] = {}
    prompt_cache_miss_tokens_by_family: dict[str, int] = {}
    for case in cases:
        guard_coverage = case.get("guard_coverage") if isinstance(case.get("guard_coverage"), dict) else {}
        if guard_coverage.get("status") == "incomplete":
            guard_coverage_incomplete_cases += 1
        if guard_coverage.get("blocked_families"):
            guard_coverage_blocked_cases += 1
        families = guard_coverage.get("families") if isinstance(guard_coverage.get("families"), dict) else {}
        for family, details in families.items():
            if not isinstance(details, dict):
                continue
            state = str(details.get("state") or "missing")
            key = f"{family}:{state}"
            guard_coverage_state_counts[key] = guard_coverage_state_counts.get(key, 0) + 1
        for kind, count in (case.get("scout_error_kinds") or {}).items():
            scout_error_kinds[str(kind)] = scout_error_kinds.get(str(kind), 0) + int(count or 0)
        for family, usage in (case.get("scout_usage_by_family") or {}).items():
            if not isinstance(usage, dict):
                continue
            prompt_tokens += _usage_int(usage, "prompt_tokens")
            completion = _usage_int(usage, "completion_tokens")
            completion_tokens += completion
            total_tokens += _usage_int(usage, "total_tokens")
            key = str(family)
            completion_tokens_by_family[key] = completion_tokens_by_family.get(key, 0) + completion
            prompt_cache_hit_tokens_by_family[key] = prompt_cache_hit_tokens_by_family.get(key, 0) + _usage_int(
                usage, "prompt_cache_hit_tokens"
            )
            prompt_cache_miss_tokens_by_family[key] = prompt_cache_miss_tokens_by_family.get(key, 0) + _usage_int(
                usage, "prompt_cache_miss_tokens"
            )
    return {
        "case_count": total,
        "available_rate": round(available / total, 4) if total else 0.0,
        "total_scout_calls": total_observed,
        "configured_scout_calls": total_configured,
        "prefix_cache_warmup_scout_calls": total_prefix_warmup,
        "trace_fallback_card_count": total_trace_fallback,
        "observed_scout_rate": round(total_observed / total_configured, 4) if total_configured else 0.0,
        "scout_error_rate": round(total_failed / total_observed, 4) if total_observed else 0.0,
        "case_pass_rate": round(case_passes / total, 4) if total else 0.0,
        "false_evidence_count": false_evidence,
        "prompt_cache_hit_tokens": prompt_cache_hit_tokens,
        "prompt_cache_miss_tokens": prompt_cache_miss_tokens,
        "prompt_cache_hit_rate": round(prompt_cache_hit_tokens / prompt_cache_total, 4)
        if prompt_cache_total
        else 0.0,
        "missing_source_refs_count": missing_source_refs,
        "card_count": cards,
        "source_addressable_card_count": source_addressable_cards,
        "source_addressable_card_rate": round(source_addressable_cards / cards, 4)
        if cards
        else 0.0,
        "source_reopen_after_warm_card_rate": round(supported_source_refs / cards, 4)
        if cards
        else 0.0,
        "manual_query_invention_after_warm_card_count": 0,
        "plain_scent_after_warm_hit_count": missing_source_refs,
        "useful_foreground_route_count": supported_source_refs,
        "irrelevant_or_noisy_card_count": max(0, cards - supported_source_refs - missing_source_refs),
        "per_scout_cost_or_call_count": total_observed,
        "wasted_scout_rate": round(max(0, total_observed - accepted_cards) / total_observed, 4)
        if total_observed
        else 0.0,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "completion_tokens_by_family": dict(sorted(completion_tokens_by_family.items())),
        "prompt_cache_hit_tokens_by_family": dict(sorted(prompt_cache_hit_tokens_by_family.items())),
        "prompt_cache_miss_tokens_by_family": dict(sorted(prompt_cache_miss_tokens_by_family.items())),
        "avg_elapsed_ms": round(sum(elapsed) / total, 2) if total else 0.0,
        "max_elapsed_ms": round(max(elapsed), 2) if elapsed else 0.0,
        "scout_error_kinds": scout_error_kinds,
        "guard_coverage_incomplete_case_count": guard_coverage_incomplete_cases,
        "guard_coverage_blocked_case_count": guard_coverage_blocked_cases,
        "guard_coverage_state_counts": dict(sorted(guard_coverage_state_counts.items())),
        "scout_roi_by_lane": scout_roi_by_lane,
        "scout_roi_by_family": scout_roi_by_family,
        "scout_roi_classification_counts": scout_roi_classification_counts(scout_roi_by_lane),
    }


def evaluate_quality_gates(
    cases: list[dict[str, Any]],
    *,
    min_available_rate: float = 0.65,
    min_observed_scout_rate: float = 1.0,
    min_case_pass_rate: float = 1.0,
    max_error_rate: float = 0.05,
    max_false_evidence_count: int = 0,
    max_missing_source_refs_count: int | None = None,
) -> dict[str, Any]:
    metrics = summarize_metrics(cases)
    failed: list[str] = []
    if float(metrics.get("available_rate") or 0.0) < min_available_rate:
        failed.append("available_rate")
    if float(metrics.get("observed_scout_rate") or 0.0) < min_observed_scout_rate:
        failed.append("observed_scout_rate")
    if float(metrics.get("case_pass_rate") or 0.0) < min_case_pass_rate:
        failed.append("case_pass_rate")
    if float(metrics.get("scout_error_rate") or 0.0) > max_error_rate:
        failed.append("scout_error_rate")
    if int(metrics.get("false_evidence_count") or 0) > max_false_evidence_count:
        failed.append("false_evidence_count")
    if (
        max_missing_source_refs_count is not None
        and int(metrics.get("missing_source_refs_count") or 0) > max_missing_source_refs_count
    ):
        failed.append("missing_source_refs_count")
    foreground_failed: list[str] = []
    if int(metrics.get("missing_source_refs_count") or 0) > 0:
        foreground_failed.append("missing_source_refs_count")
    if float(metrics.get("source_addressable_card_rate") or 0.0) <= 0.0 and int(
        metrics.get("card_count") or 0
    ) > 0:
        foreground_failed.append("source_addressable_card_rate")
    return {
        "passed": not failed,
        "failed": failed,
        "scout_pipeline_passed": not failed,
        "foreground_source_addressability_gate": {
            "passed": not foreground_failed,
            "failed": foreground_failed,
            "source_addressable_card_rate": metrics.get("source_addressable_card_rate"),
            "missing_source_refs_count": metrics.get("missing_source_refs_count"),
            "source_reopen_after_warm_card_rate": metrics.get(
                "source_reopen_after_warm_card_rate"
            ),
        },
        "thresholds": {
            "min_available_rate": min_available_rate,
            "min_observed_scout_rate": min_observed_scout_rate,
            "min_case_pass_rate": min_case_pass_rate,
            "max_error_rate": max_error_rate,
            "max_false_evidence_count": max_false_evidence_count,
            "max_missing_source_refs_count": max_missing_source_refs_count,
        },
        "failed_case_ids": [
            str(case.get("case_id") or "")
            for case in cases
            if not case.get("expectation_passed")
        ],
    }


def privacy_boundary() -> dict[str, bool]:
    return {
        "raw_prompt_emitted": False,
        "raw_prompt_trace_emitted": False,
        "raw_cards_emitted": False,
        "absolute_paths_emitted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=None)
    parser.add_argument("--case-offset", type=int, default=0)
    parser.add_argument("--case-limit", type=int, default=None)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--wait-all", action="store_true", dest="wait_all", default=True)
    parser.add_argument("--quorum-first", action="store_false", dest="wait_all")
    parser.add_argument("--timeout", type=float, default=2.4)
    parser.add_argument("--quorum", type=int, default=warm.DEFAULT_QUORUM)
    parser.add_argument("--max-workers", type=int, default=None)
    parser.add_argument(
        "--case-workers",
        type=int,
        default=DEFAULT_CASE_WORKERS,
        help="Outer case concurrency. Use 0 for conservative auto mode.",
    )
    parser.add_argument("--prefix-cache-warmup-scouts", type=int, default=warm.DEFAULT_PREFIX_CACHE_WARMUP_SCOUTS)
    parser.add_argument("--prefix-cache-warmup-delay", type=float, default=warm.DEFAULT_PREFIX_CACHE_WARMUP_DELAY)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--cases-file", help="Optional JSON/JSONL sanitized trace case file.")
    parser.add_argument("--api-key-env", default="AIPPOCAMPUS_DEEPSEEK_API_KEY")
    parser.add_argument("--user-id", help="Optional DeepSeek user_id; omit to use a stable sanitized hash.")
    parser.add_argument("--progress-jsonl", help="Optional sanitized per-case progress JSONL path.")
    parser.add_argument("--min-available-rate", type=float, default=0.65)
    parser.add_argument("--min-observed-scout-rate", type=float, default=None)
    parser.add_argument("--min-case-pass-rate", type=float, default=1.0)
    parser.add_argument("--max-error-rate", type=float, default=0.05)
    parser.add_argument("--max-false-evidence-count", type=int, default=0)
    parser.add_argument("--max-missing-source-refs-count", type=int, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()
    payload = run_warm_ambient_recall_benchmark(
        cwd=args.cwd,
        case_offset=args.case_offset,
        case_limit=args.case_limit,
        live=args.live,
        wait_all=args.wait_all,
        timeout=args.timeout,
        quorum=args.quorum,
        max_workers=args.max_workers,
        case_workers=args.case_workers,
        prefix_cache_warmup_scouts=args.prefix_cache_warmup_scouts,
        prefix_cache_warmup_delay=args.prefix_cache_warmup_delay,
        max_tokens=args.max_tokens,
        registry_path=args.registry,
        registry_dir=args.registry_dir,
        cases_file=args.cases_file,
        api_key_env=args.api_key_env,
        user_id=args.user_id,
        progress_jsonl=args.progress_jsonl,
        min_available_rate=args.min_available_rate,
        min_observed_scout_rate=args.min_observed_scout_rate,
        min_case_pass_rate=args.min_case_pass_rate,
        max_error_rate=args.max_error_rate,
        max_false_evidence_count=args.max_false_evidence_count,
        max_missing_source_refs_count=args.max_missing_source_refs_count,
    )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        metrics = payload.get("metrics") or {}
        print(
            "warm ambient recall benchmark: "
            f"cases={metrics.get('case_count', 0)} "
            f"available_rate={metrics.get('available_rate', 0)} "
            f"scout_results={metrics.get('total_scout_calls', 0)}"
        )
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
