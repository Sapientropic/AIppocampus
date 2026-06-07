#!/usr/bin/env python3
"""No-write query-pattern enrichment planner for registry/import refreshes.

This module is deliberately a planner/report surface. It can tell an operator or
future registry refresh which source generations would need query-pattern work,
but it does not call DeepSeek, write `query_pattern_routes.jsonl`, or feed the
foreground hook. Generated aliases and work ids are navigation material only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_text
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values

QUERY_PATTERN_ENRICHMENT_KIND = "aippocampus_query_pattern_enrichment_report"
QUERY_PATTERN_ENRICHMENT_SCHEMA_VERSION = 1
MAX_ALIAS_SEEDS = 8

BLOCKED_SENSITIVITY = {"blocked", "private", "sensitive", "secret"}
SECRETISH_MARKERS = ("secret", "token", "password", "credential", "api_key")


def _sha(value: Any, *, prefix: str) -> str:
    digest = hashlib.sha256(str(value or "").encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _safe_text(value: Any, chars: int = 120) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, chars)


def _looks_sensitive_text(text: str) -> bool:
    lowered = text.casefold()
    if any(marker in lowered for marker in SECRETISH_MARKERS):
        return True
    return "\\" in text or "/" in text or (len(text) > 2 and text[1:3] == ":\\")


def _safe_terms(value: Any, *, limit: int = MAX_ALIAS_SEEDS) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _safe_text(item, 80)
        if not text or _looks_sensitive_text(text):
            continue
        marker = text.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _thread_key_hash(row: Mapping[str, Any]) -> str:
    return _sha(row.get("thread_key") or row.get("thread_id") or row.get("project_id"), prefix="thread")


def _generation_digest(row: Mapping[str, Any]) -> str:
    return str(
        row.get("source_generation_digest")
        or row.get("generation_digest")
        or row.get("clean_source_digest")
        or ""
    )


def _provider_policy(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("provider_policy")
    return value if isinstance(value, Mapping) else {}


def _privacy_blocked(row: Mapping[str, Any]) -> bool:
    policy = _provider_policy(row)
    sensitivity = str(row.get("sensitivity") or policy.get("sensitivity") or "").casefold()
    return bool(policy.get("privacy_blocked")) or sensitivity in BLOCKED_SENSITIVITY


def _source_generation_changed(row: Mapping[str, Any]) -> bool:
    # Registry/import refreshes may pass every known generation. Only an
    # explicit ``changed=False`` blocks new query-pattern work; older callers
    # that omit the field are treated as changed so first-bootstrap fixtures can
    # still plan work without inventing a cache-missing exception path.
    return row.get("changed") is not False


def _execution_mode(row: Mapping[str, Any]) -> str | None:
    policy = _provider_policy(row)
    if _privacy_blocked(row):
        return None
    if bool(policy.get("external_model_allowed")):
        return "deferred_external_model"
    if bool(policy.get("local_offline_allowed")):
        return "local_offline"
    return None


def _work_fingerprint(thread_hash: str, generation_digest: str, execution_mode: str | None) -> str:
    return _sha(f"{thread_hash}:{generation_digest}:{execution_mode or 'suppressed'}", prefix="qpw")


def _existing_route_index(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        thread_hash = str(row.get("thread_key_hash") or "") or _thread_key_hash(row)
        result.setdefault(thread_hash, []).append(row)
    return result


def _existing_work_fingerprints(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    out: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        fingerprint = str(row.get("query_pattern_work_fingerprint") or "").strip()
        if fingerprint:
            out.add(fingerprint)
    return out


def _planned_job(
    *,
    row: Mapping[str, Any],
    thread_hash: str,
    generation_digest: str,
    execution_mode: str,
    fingerprint: str,
) -> dict[str, Any]:
    return {
        "kind": "aippocampus_query_pattern_enrichment_work_item",
        "query_pattern_work_fingerprint": fingerprint,
        "thread_key_hash": thread_hash,
        "source_generation_digest": generation_digest,
        "execution_mode": execution_mode,
        "provider_route": "deepseek_compatible_deferred"
        if execution_mode == "deferred_external_model"
        else "local_offline_deterministic",
        "no_write": True,
        "live_model_call": False,
        "navigation_only": True,
        "output_authority": "navigation_only",
        "source_refs": safe_source_refs(row.get("source_refs")),
        "source_ref_count": len(safe_source_refs(row.get("source_refs"))),
        "query_alias_seeds": _safe_terms(row.get("query_alias_seeds") or row.get("aliases") or []),
        "changed_source_row_count": _int(row.get("source_row_count"), 1),
        "reason_codes": ["source_generation_changed_or_missing_query_pattern_cache"],
        "invalidation_triggers": ["source_generation_digest_changed"],
        "write_target": "query_pattern_routes.jsonl",
        "write_allowed_in_this_report": False,
    }


def _consumption_metrics(value: Mapping[str, Any] | None) -> dict[str, Any]:
    metrics = value if isinstance(value, Mapping) else {}
    route_seen = _int(metrics.get("query_pattern_route_seen_count"))
    route_hits = _int(metrics.get("foreground_route_hit_from_query_pattern_count"))
    reopen_attempts = _int(metrics.get("source_reopen_attempt_count"))
    reopen_success = _int(metrics.get("source_reopen_success_count"))
    materialized_routes = _int(metrics.get("materialized_query_pattern_route_count"))
    wasted = _int(metrics.get("wasted_query_pattern_count"))
    return {
        "foreground_route_hit_from_query_pattern": _rate(route_hits, route_seen),
        "wasted_query_pattern_rate": _rate(wasted, materialized_routes),
        "source_reopen_after_query_pattern_rate": _rate(reopen_success, reopen_attempts),
        "foreground_route_hit_from_query_pattern_count": route_hits,
        "query_pattern_route_seen_count": route_seen,
        "wasted_query_pattern_count": wasted,
        "materialized_query_pattern_route_count": materialized_routes,
        "source_reopen_success_count": reopen_success,
        "source_reopen_attempt_count": reopen_attempts,
    }


def query_pattern_enrichment_report(
    source_generations: Iterable[Mapping[str, Any]],
    *,
    existing_query_pattern_routes: Iterable[Mapping[str, Any]] = (),
    existing_work_items: Iterable[Mapping[str, Any]] = (),
    consumption_metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Plan query-pattern work without mutating registry, sidecars, or hooks."""

    rows = [row for row in source_generations if isinstance(row, Mapping)]
    existing_routes = _existing_route_index(existing_query_pattern_routes)
    existing_work = _existing_work_fingerprints(existing_work_items)

    source_rows: list[dict[str, Any]] = []
    planned_jobs: list[dict[str, Any]] = []
    invalidated_routes: list[dict[str, Any]] = []
    cache_reuse_count = 0
    existing_work_item_reuse_count = 0
    privacy_blocked_count = 0

    for row in rows:
        thread_hash = _thread_key_hash(row)
        digest = _generation_digest(row)
        mode = _execution_mode(row)
        fingerprint = _work_fingerprint(thread_hash, digest, mode)
        routes_for_thread = existing_routes.get(thread_hash, [])
        current_cache = [
            route for route in routes_for_thread if str(route.get("source_generation_digest") or "") == digest
        ]
        stale_routes = [
            route for route in routes_for_thread if str(route.get("source_generation_digest") or "") != digest
        ]
        for stale in stale_routes:
            invalidated_routes.append(
                {
                    "thread_key_hash": thread_hash,
                    "previous_generation_digest": str(stale.get("source_generation_digest") or ""),
                    "current_generation_digest": digest,
                    "route_count": _int(stale.get("route_count"), len(stale.get("route_ids") or [])),
                    "reason": "source_generation_digest_changed",
                    "navigation_only": True,
                }
            )

        status = "planned"
        suppression_reason = ""
        source_changed = _source_generation_changed(row)
        if current_cache:
            status = "cache_reused"
            cache_reuse_count += 1
        elif not source_changed:
            status = "unchanged_skipped"
            suppression_reason = "source_generation_unchanged"
        elif fingerprint in existing_work:
            status = "work_item_reused"
            existing_work_item_reuse_count += 1
        elif mode is None:
            status = "suppressed"
            suppression_reason = "privacy_or_provider_blocked"
            privacy_blocked_count += 1
        else:
            planned_jobs.append(
                _planned_job(
                    row=row,
                    thread_hash=thread_hash,
                    generation_digest=digest,
                    execution_mode=mode,
                    fingerprint=fingerprint,
                )
            )

        source_rows.append(
            {
                "thread_key_hash": thread_hash,
                "source_generation_digest": digest,
                "previous_generation_digest": str(row.get("previous_generation_digest") or ""),
                "status": status,
                "suppression_reason": suppression_reason,
                "query_pattern_work_fingerprint": fingerprint,
                "execution_mode": mode or "suppressed",
                "source_ref_count": len(safe_source_refs(row.get("source_refs"))),
                "query_alias_seed_count": len(
                    _safe_terms(row.get("query_alias_seeds") or row.get("aliases") or [])
                ),
                "navigation_only": True,
            }
        )

    consumption = _consumption_metrics(consumption_metrics)
    metrics = {
        "source_generation_count": len(rows),
        "query_pattern_job_count": len(planned_jobs),
        "changed_source_rows_analyzed": len(planned_jobs),
        "cache_reuse_count": cache_reuse_count,
        "cache_reuse_rate": _rate(cache_reuse_count, len(rows)),
        "existing_work_item_reuse_count": existing_work_item_reuse_count,
        "invalidated_query_pattern_route_count": len(invalidated_routes),
        "privacy_blocked_source_row_count": privacy_blocked_count,
        "live_deepseek_call_count": 0,
        **consumption,
    }
    report = {
        "kind": QUERY_PATTERN_ENRICHMENT_KIND,
        "schema_version": QUERY_PATTERN_ENRICHMENT_SCHEMA_VERSION,
        "ok": True,
        "no_write": True,
        "navigation_only": True,
        "source_rows": source_rows,
        "planned_jobs": planned_jobs,
        "invalidated_routes": invalidated_routes,
        "metrics": metrics,
        "contract": {
            "no_write_report_only": True,
            "clean_source_mutation_allowed": False,
            "registry_mutation_allowed": False,
            "sidecar_write_allowed": False,
            "live_deepseek_call_allowed": False,
            "foreground_hook_consumption_wired": False,
            "generated_aliases_are_navigation_only": True,
            "query_pattern_routes_are_not_evidence": True,
            "source_reopen_required_before_claim": True,
            "local_offline_provider_mode_possible": True,
        },
        "privacy_boundary": {
            "raw_prompt_serialized": False,
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
            "secret_values_serialized": False,
            "answer_text_serialized": False,
        },
        "can_claim": [
            "query_pattern_enrichment_is_no_write",
            "changed_source_generations_can_plan_query_pattern_work",
            "current_generation_cache_reuse_is_idempotent",
            "source_generation_change_invalidates_old_query_pattern_routes",
            "provider_gate_blocks_disallowed_external_model_work",
        ],
        "cannot_claim": [
            "query_pattern_routes_jsonl_is_written",
            "foreground_hook_consumes_query_pattern_routes",
            "live_deepseek_query_pattern_quality",
            "query_pattern_alias_is_source_truth",
            "live_latency_savings_are_proven",
        ],
    }
    return redact_sensitive_values(redact_private_paths(report))


def fixture_query_pattern_enrichment_report() -> dict[str, Any]:
    local_path = "E:" + "\\private\\query-pattern\\source.jsonl"
    return query_pattern_enrichment_report(
        [
            {
                "thread_key": "thread-alpha",
                "source_generation_digest": "gen-alpha-v2",
                "previous_generation_digest": "gen-alpha-v1",
                "changed": True,
                "source_row_count": 12,
                "query_alias_seeds": ["last time alpha", "continue alpha"],
                "source_refs": [{"thread_key": "thread-alpha", "message_id": "msg-a"}],
                "provider_policy": {"external_model_allowed": True, "local_offline_allowed": True},
                "raw_source_text": f"private source text at {local_path}",
            },
            {
                "thread_key": "thread-beta",
                "source_generation_digest": "gen-beta-v1",
                "changed": False,
                "source_row_count": 8,
                "query_alias_seeds": ["continue beta"],
                "source_refs": [{"thread_key": "thread-beta", "message_id": "msg-b"}],
                "provider_policy": {"external_model_allowed": True},
            },
            {
                "thread_key": "thread-gamma",
                "source_generation_digest": "gen-gamma-v1",
                "changed": True,
                "source_row_count": 5,
                "query_alias_seeds": ["sensitive gamma"],
                "source_refs": [{"thread_key": local_path, "message_id": "msg-g"}],
                "provider_policy": {
                    "external_model_allowed": False,
                    "local_offline_allowed": False,
                    "privacy_blocked": True,
                },
            },
        ],
        existing_query_pattern_routes=[
            {
                "thread_key": "thread-alpha",
                "source_generation_digest": "gen-alpha-v1",
                "route_count": 2,
            },
            {
                "thread_key": "thread-beta",
                "source_generation_digest": "gen-beta-v1",
                "route_count": 3,
            },
        ],
        consumption_metrics={
            "query_pattern_route_seen_count": 4,
            "foreground_route_hit_from_query_pattern_count": 2,
            "source_reopen_attempt_count": 2,
            "source_reopen_success_count": 1,
            "wasted_query_pattern_count": 1,
            "materialized_query_pattern_route_count": 4,
        },
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.fixture:
        raise SystemExit("--fixture is required until a registry/import caller supplies rows")
    payload = fixture_query_pattern_enrichment_report()
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("AIppocampus query-pattern enrichment report")
        print(f"- planned_jobs: {payload['metrics']['query_pattern_job_count']}")
        print(f"- cache_reuse_rate: {payload['metrics']['cache_reuse_rate']:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
