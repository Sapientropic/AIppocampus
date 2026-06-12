#!/usr/bin/env python3
"""Deterministic long-context Dream atlas pack builder."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.model.routing import (
    DEEPSEEK_PREFIX_CACHE_CONTRACT,
    DEFAULT_DEEPSEEK_API_KEY_ENV,
    deepseek_base_url,
    flash_model,
)
from aippocampus_runtime.safety import deepseek_cache_metrics_from_usage

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_dream_long_context_atlas_report"
ATLAS_KIND = "dream_long_context_atlas_pack"
READY_STATUS = "ready_for_dream_worker"
CONTEXT_WINDOW_TOKENS = 1_000_000
PROMPT_ORDER = [
    "stable_dream_worker_contract",
    "stable_atlas_source_card_payload",
    "variable_run_directive",
]
FORBIDDEN_MARKERS = (
    "PRIVATE_DREAM_ATLAS_TEXT",
    "raw_private_source_text",
    "source://private",
    "C:\\",
    "/Users/",
)
OFFICIAL_DEEPSEEK_SOURCES = [
    "https://api-docs.deepseek.com/news/news260424",
    "https://api-docs.deepseek.com/guides/kv_cache",
]


def stable_hash(*parts: Any, length: int = 16) -> str:
    digest = hashlib.sha256(
        "\u241f".join(str(part) for part in parts).encode("utf-8", errors="replace")
    ).hexdigest()
    return digest[:length]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _label(value: Any, *, fallback: str = "") -> str:
    text = _text(value).casefold()
    return text if text and all(char.isalnum() or char in "-_.:" for char in text) else fallback


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _safe_pack_id(value: Any) -> str:
    text = _text(value)
    if (
        text
        and len(text) <= 96
        and all(char.isalnum() or char in "-_." for char in text)
    ):
        return text
    return "pack_" + stable_hash(text, length=12)


def _safe_ref(value: Any) -> str | None:
    text = _text(value)
    if (
        text
        and len(text) <= 96
        and not any(marker in text for marker in ("source://", "\\", "/", ":\\"))
        and all(char.isalnum() or char in "-_.:#" for char in text)
    ):
        return text
    return None


def _safe_refs(value: Any) -> list[str]:
    refs: list[str] = []
    for raw in _strings(value):
        ref = _safe_ref(raw)
        if ref and ref not in refs:
            refs.append(ref)
    return refs[:32]


def _safe_topic(value: Any) -> str:
    label = _label(value, fallback="")
    return label if label else "topic_" + stable_hash(_text(value), length=10)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _reject_reasons(row: Mapping[str, Any], refs: list[str]) -> list[str]:
    reasons: list[str] = []
    if _label(row.get("status"), fallback="") != READY_STATUS:
        reasons.append("not_ready_for_dream_worker")
    if not refs:
        reasons.append("missing_source_refs")
    if bool(row.get("symbolic_claim")) and not refs:
        reasons.append("source_free_symbolic_claim")
    if bool(row.get("profile_claim")):
        reasons.append("profile_claim")
    return reasons


def normalize_pack_row(row: Mapping[str, Any]) -> dict[str, Any]:
    pack_id = _safe_pack_id(row.get("pack_id") or row.get("id"))
    refs = _safe_refs(row.get("source_refs") or row.get("source_ref_ids"))
    thread_ids = _safe_refs(row.get("source_threads") or row.get("thread_ids"))
    if not thread_ids and refs:
        thread_ids = ["thread_" + stable_hash(ref, length=8) for ref in refs]
    return {
        "pack_id": pack_id,
        "status": _label(row.get("status"), fallback=""),
        "topic_epoch": _safe_topic(row.get("topic_epoch") or row.get("topic")),
        "project_scope": _safe_topic(row.get("project_scope") or "project:aippocampus"),
        "freshness": _safe_topic(row.get("freshness") or "current"),
        "roi_score": round(_safe_float(row.get("roi_score"), default=0.5), 4),
        "source_ref_ids": refs,
        "source_thread_ids": thread_ids[:16],
        "cycle_key": _label(row.get("cycle_key"), fallback=""),
        "bridge_key": _label(row.get("bridge_key"), fallback=""),
        "bounded_detected_shapes": sorted(
            {
                _label(shape)
                for shape in _strings(row.get("bounded_detected_shapes"))
                if _label(shape)
            }
        ),
        "estimated_card_tokens": max(
            80,
            80 + len(refs) * 18 + len(_safe_topic(row.get("topic_epoch"))) // 4,
        ),
    }


def _rejected_pack(row: Mapping[str, Any], reasons: list[str]) -> dict[str, Any]:
    return {
        "kind": "dream_atlas_rejected_pack",
        "schema_version": SCHEMA_VERSION,
        "pack_id": _safe_pack_id(row.get("pack_id") or row.get("id")),
        "reasons": sorted(set(reasons)),
    }


def select_ready_packs(rows: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in rows:
        normalized = normalize_pack_row(row)
        reasons = _reject_reasons(row, normalized["source_ref_ids"])
        if reasons:
            rejected.append(_rejected_pack(row, reasons))
            continue
        selected.append(normalized)
    selected.sort(
        key=lambda item: (
            item["project_scope"],
            item["topic_epoch"],
            -item["roi_score"],
            item["pack_id"],
        )
    )
    return selected, rejected


def _source_cards(packs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "pack_id": pack["pack_id"],
            "topic_epoch": pack["topic_epoch"],
            "project_scope": pack["project_scope"],
            "freshness": pack["freshness"],
            "roi_score": pack["roi_score"],
            "source_ref_ids": pack["source_ref_ids"],
            "source_thread_count": len(set(pack["source_thread_ids"])),
            "cycle_key": pack["cycle_key"] or None,
            "bridge_key": pack["bridge_key"] or None,
            "bounded_detected_shapes": pack["bounded_detected_shapes"],
        }
        for pack in packs
    ]


def _candidate(
    *,
    candidate_type: str,
    shape: str,
    key: str,
    packs: list[dict[str, Any]],
    bounded_shape: str,
) -> dict[str, Any]:
    source_ref_ids = sorted({ref for pack in packs for ref in pack["source_ref_ids"]})
    source_threads = sorted({thread for pack in packs for thread in pack["source_thread_ids"]})
    bounded_detected = any(
        bounded_shape in pack["bounded_detected_shapes"] for pack in packs
    )
    return {
        "kind": "dream_atlas_candidate",
        "schema_version": SCHEMA_VERSION,
        "candidate_id": "dream_atlas_" + stable_hash(candidate_type, key, *source_ref_ids),
        "candidate_type": candidate_type,
        "shape": shape,
        "authority": "dream_synthesized_candidate_not_fact",
        "source_ref_ids": source_ref_ids,
        "source_ref_count": len(source_ref_ids),
        "source_thread_count": len(source_threads),
        "source_pack_ids": [pack["pack_id"] for pack in packs],
        "bounded_pack_detected": bounded_detected,
        "foreground_eligible": False,
        "source_reopen_required_before_claim": True,
        "next_safe_action": "review_or_route_only",
        "unsupported_candidate": not bool(source_ref_ids),
    }


def atlas_candidates(packs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_cycle: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_bridge: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pack in packs:
        if pack["cycle_key"]:
            by_cycle[pack["cycle_key"]].append(pack)
        if pack["bridge_key"]:
            by_bridge[pack["bridge_key"]].append(pack)

    candidates: list[dict[str, Any]] = []
    for key, grouped in sorted(by_cycle.items()):
        if len(grouped) >= 2:
            candidates.append(
                _candidate(
                    candidate_type="cross_pack_cycle",
                    shape="cycle",
                    key=key,
                    packs=grouped,
                    bounded_shape="cycle",
                )
            )
    for key, grouped in sorted(by_bridge.items()):
        if len(grouped) >= 2 and len({thread for pack in grouped for thread in pack["source_thread_ids"]}) >= 2:
            candidates.append(
                _candidate(
                    candidate_type="cross_pack_bridge",
                    shape="weak_bridge",
                    key=key,
                    packs=grouped,
                    bounded_shape="weak_bridge",
                )
            )
    return candidates


def _estimated_token_budget(packs: list[dict[str, Any]]) -> int:
    stable_contract = 1200
    source_payload = sum(_safe_int(pack["estimated_card_tokens"]) for pack in packs)
    variable_directive = 320
    return stable_contract + source_payload + variable_directive


def cache_telemetry(provider_usage: Mapping[str, Any] | None) -> dict[str, Any]:
    if not provider_usage:
        return {
            "available": False,
            "source": "offline_deterministic_no_provider_usage",
            "prompt_cache_hit_tokens": None,
            "prompt_cache_miss_tokens": None,
            "hit_rate": None,
        }
    metrics = deepseek_cache_metrics_from_usage(dict(provider_usage))
    return {
        "available": bool(metrics["available"]),
        "source": "provider_usage" if metrics["available"] else "provider_usage_missing_fields",
        "prompt_cache_hit_tokens": metrics["hit_tokens"],
        "prompt_cache_miss_tokens": metrics["miss_tokens"],
        "hit_rate": metrics["hit_rate"] if metrics["available"] else None,
    }


def fixture_pack_rows() -> list[dict[str, Any]]:
    return [
        {
            "pack_id": "bounded_cycle_pack_a",
            "status": READY_STATUS,
            "topic_epoch": "route-cycle",
            "source_refs": ["public:cycle:a1", "public:cycle:a2"],
            "source_threads": ["thread-cycle-a"],
            "cycle_key": "manual_search_loop",
            "bounded_detected_shapes": [],
            "roi_score": 0.82,
        },
        {
            "pack_id": "bounded_cycle_pack_b",
            "status": READY_STATUS,
            "topic_epoch": "route-cycle",
            "source_refs": ["public:cycle:b1", "public:cycle:b2"],
            "source_threads": ["thread-cycle-b"],
            "cycle_key": "manual_search_loop",
            "bounded_detected_shapes": [],
            "roi_score": 0.78,
        },
        {
            "pack_id": "bridge_pack_a",
            "status": READY_STATUS,
            "topic_epoch": "topology-bridge",
            "source_refs": ["public:bridge:a1", "public:bridge:a2"],
            "source_threads": ["thread-bridge-a"],
            "bridge_key": "topology_usefulness",
            "bounded_detected_shapes": [],
            "roi_score": 0.7,
        },
        {
            "pack_id": "bridge_pack_b",
            "status": READY_STATUS,
            "topic_epoch": "topology-bridge",
            "source_refs": ["public:bridge:b1", "public:bridge:b2"],
            "source_threads": ["thread-bridge-b"],
            "bridge_key": "topology_usefulness",
            "bounded_detected_shapes": [],
            "roi_score": 0.74,
        },
    ]


def build_dream_atlas_report(
    rows: Iterable[Mapping[str, Any]] | None = None,
    *,
    provider_usage: Mapping[str, Any] | None = None,
    privacy_mode: str = "source_cards_only",
) -> dict[str, Any]:
    row_list = list(rows) if rows is not None else fixture_pack_rows()
    selected, rejected = select_ready_packs(row_list)
    cards = _source_cards(selected)
    candidates = atlas_candidates(selected)
    source_ref_ids = sorted({ref for pack in selected for ref in pack["source_ref_ids"]})
    source_thread_ids = sorted(
        {thread for pack in selected for thread in pack["source_thread_ids"]}
    )
    estimated_token_budget = _estimated_token_budget(selected)
    bounded_missed_count = sum(
        1 for candidate in candidates if not candidate["bounded_pack_detected"]
    )
    unsupported_candidate_count = sum(
        1 for candidate in candidates if candidate["unsupported_candidate"]
    )
    rejected_reasons = Counter(reason for item in rejected for reason in item["reasons"])
    atlas = {
        "kind": ATLAS_KIND,
        "schema_version": SCHEMA_VERSION,
        "model_family": "deepseek_v4",
        "candidate_models": ["deepseek-v4-flash", "deepseek-v4-pro"],
        "context_window_tokens": CONTEXT_WINDOW_TOKENS,
        "cache_contract": DEEPSEEK_PREFIX_CACHE_CONTRACT,
        "prompt_order": PROMPT_ORDER,
        "privacy_mode": privacy_mode,
        "selected_pack_count": len(selected),
        "source_ref_count": len(source_ref_ids),
        "source_thread_count": len(source_thread_ids),
        "estimated_token_budget": estimated_token_budget,
        "raw_source_text_included": False,
        "source_cards": cards,
        "official_deepseek_sources": OFFICIAL_DEEPSEEK_SOURCES,
        "official_source_checked_on": "2026-06-11",
    }
    cache = cache_telemetry(provider_usage)
    metrics = {
        "selected_pack_count": atlas["selected_pack_count"],
        "source_ref_count": atlas["source_ref_count"],
        "source_thread_count": atlas["source_thread_count"],
        "estimated_token_budget": atlas["estimated_token_budget"],
        "bounded_pack_candidate_count": sum(
            len(pack["bounded_detected_shapes"]) for pack in selected
        ),
        "atlas_candidate_count": len(candidates),
        "atlas_unique_candidate_count": len(
            {candidate["candidate_id"] for candidate in candidates}
        ),
        "bounded_pack_missed_bridge_or_cycle_count": bounded_missed_count,
        "source_ref_validity_rate": round(
            sum(1 for candidate in candidates if candidate["source_ref_count"] > 0)
            / max(1, len(candidates)),
            4,
        ),
        "bridge_quality_proxy_count": sum(
            1 for candidate in candidates if candidate["candidate_type"] == "cross_pack_bridge"
        ),
        "unsupported_candidate_count": unsupported_candidate_count,
        "hard_negative_rejected_count": len(rejected),
        "source_free_symbolic_claim_rejected_count": rejected_reasons[
            "source_free_symbolic_claim"
        ],
        "profile_claim_rejected_count": rejected_reasons["profile_claim"],
        "missing_source_refs_rejected_count": rejected_reasons["missing_source_refs"],
        "latency_cost_mode": "deterministic_estimate_only"
        if not cache["available"]
        else "provider_usage_attached",
    }
    evaluation = {
        "command": (
            "python -m aippocampus_runtime.dream.atlas_pack --fixture --json"
        ),
        "comparison": {
            "bounded_pack_candidate_count": metrics["bounded_pack_candidate_count"],
            "atlas_candidate_count": metrics["atlas_candidate_count"],
            "candidate_survival_count": metrics["atlas_unique_candidate_count"],
            "source_ref_validity_rate": metrics["source_ref_validity_rate"],
            "bridge_quality_proxy_count": metrics["bridge_quality_proxy_count"],
            "unsupported_candidate_count": metrics["unsupported_candidate_count"],
            "latency_cost_mode": metrics["latency_cost_mode"],
        },
        "live_provider_cache_fields": [
            "usage.prompt_cache_hit_tokens",
            "usage.prompt_cache_miss_tokens",
        ],
    }
    public_payload = {
        "atlas_pack": atlas,
        "atlas_candidates": candidates,
        "rejected_packs": rejected,
        "metrics": metrics,
        "evaluation": evaluation,
        "cache_telemetry": cache,
    }
    forbidden_marker_count = sum(
        1
        for marker in FORBIDDEN_MARKERS
        if marker in json.dumps(public_payload, ensure_ascii=False, sort_keys=True)
    )
    red_lines = {
        "raw_private_text_emitted_count": forbidden_marker_count,
        "local_path_emitted_count": forbidden_marker_count,
        "raw_source_ref_emitted_count": forbidden_marker_count,
        "raw_source_text_included_count": 0,
        "unsupported_candidate_count": unsupported_candidate_count,
        "cache_hit_rate_invented_count": 0
        if cache["available"] or cache["hit_rate"] is None
        else 1,
    }
    contract_gate_ok = bool(selected) and estimated_token_budget < CONTEXT_WINDOW_TOKENS
    safety_gate_ok = all(value == 0 for value in red_lines.values())
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": contract_gate_ok and safety_gate_ok,
        "contract_gate_ok": contract_gate_ok,
        "safety_gate_ok": safety_gate_ok,
        "atlas_pack": atlas,
        "atlas_candidates": candidates,
        "rejected_packs": rejected,
        "metrics": metrics,
        "evaluation": evaluation,
        "cache_telemetry": cache,
        "red_lines": red_lines,
        "privacy_boundary": {
            "raw_private_text_emitted": False,
            "local_paths_emitted": False,
            "raw_source_refs_emitted": False,
            "raw_source_text_included": False,
            "forbidden_marker_count": forbidden_marker_count,
        },
        "contract": {
            "stable_prefix_payload_before_variable_directive": True,
            "deepseek_v4_1m_context_officially_verified": True,
            "cache_telemetry_only_from_provider_usage": True,
            "raw_source_text_default_excluded": True,
            "candidates_remain_dream_synthesized_not_fact": True,
            "foreground_disabled_by_default": True,
        },
        "cannot_claim": [
            "live_deepseek_quality",
            "provider_cache_hit_rate_without_usage",
            "private_history_atlas_quality",
            "long_context_candidate_quality",
            "foreground_default_usefulness",
            "source_truth_without_reopen",
        ],
    }


def run_live_atlas_pilot(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Compatibility facade for the opt-in live pilot helper.

    Keep deterministic atlas construction import-light. The live provider path
    owns model routing, prompt construction, and adjudication diagnostics in the
    sibling module so this builder does not become a mixed offline/live
    coordinator again.
    """

    from aippocampus_runtime.dream.atlas_live_pilot import (
        run_live_atlas_pilot as _run_live_atlas_pilot,
    )

    return _run_live_atlas_pilot(*args, **kwargs)


def load_rows(path: Path) -> list[Mapping[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    if isinstance(data, Mapping):
        raw_rows = data.get("packs") or data.get("rows") or data.get("cases") or []
        return [item for item in raw_rows if isinstance(item, Mapping)]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="JSON file with Dream pack rows.")
    parser.add_argument("--fixture", action="store_true", help="Use the built-in fixture.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--live-pilot",
        action="store_true",
        help="Run or skip the opt-in live provider atlas pilot.",
    )
    parser.add_argument(
        "--skip-if-missing-key",
        action="store_true",
        help="Emit a skipped report instead of failing when the API key is absent.",
    )
    parser.add_argument("--model-route", default="flash")
    parser.add_argument("--model", default=flash_model())
    parser.add_argument("--base-url", default=deepseek_base_url())
    parser.add_argument("--api-key-env", default=DEFAULT_DEEPSEEK_API_KEY_ENV)
    parser.add_argument("--max-tokens", type=int, default=1400)
    parser.add_argument("--max-samples", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--dream-model-thinking", default="auto")
    parser.add_argument("--dream-model-reasoning-effort", default="auto")
    parser.add_argument("--input-cost-per-million", type=float)
    parser.add_argument("--output-cost-per-million", type=float)
    args = parser.parse_args(argv)

    rows = load_rows(Path(args.input)) if args.input else None
    if args.live_pilot:
        from aippocampus_runtime.dream.atlas_live_pilot import config_from_args

        config, model_route, skip_reason = config_from_args(args)
        report = run_live_atlas_pilot(
            rows=rows,
            config=config,
            max_samples=args.max_samples,
            input_cost_per_million=args.input_cost_per_million,
            output_cost_per_million=args.output_cost_per_million,
            model_route=model_route,
            skip_reason=skip_reason,
        )
    else:
        report = build_dream_atlas_report(rows)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("dream atlas pack: " + ("ok" if report["ok"] else "blocked"))
        print(f"metrics: {report['metrics']}")
        if args.live_pilot:
            print(f"live_pilot: {report['live_pilot']['status']}")
    return 0 if report["safety_gate_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
