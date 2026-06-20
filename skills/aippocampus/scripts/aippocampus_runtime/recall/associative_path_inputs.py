"""Input packs and opt-in diagnostics for Associative Path Walker.

The APW input pack is a read-only bridge from existing recall/navigation
sidecars into the deterministic walker. It is deliberately not a source of
truth and it does not write caches, change default recall ranking, or promote
feedback into evidence.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall.associative_path_walker import walk_associative_paths
from aippocampus_runtime.recall.query_policy import unique_preserve

KIND = "aippocampus_associative_path_input_pack"
DIAGNOSTIC_KIND = "aippocampus_associative_path_diagnostic"
SCHEMA_VERSION = 1
DEFAULT_SIDECAR_DIR_NAME = ".aippocampus"

BRIDGE_FILENAMES = ("semantic-bridges.jsonl", "semantic_bridges.jsonl")
NAVIGATION_FILENAMES = ("navigation-potential.jsonl", "navigation_potential.jsonl")
FEEDBACK_FILENAMES = ("route-feedback.jsonl", "route_feedback.jsonl", "feedback.jsonl")
ACTIVE_LOCK_FILENAMES = ("active_recall_locks.json", "active-recall-locks.json")
PRIVATE_BUCKETS = {"private", "restricted", "personal", "user_private", "machine_private"}
STALE_STATUSES = {"stale", "superseded", "refuted", "retired", "archived", "expired"}


def _public_payload(payload: Any) -> Any:
    return redact_sensitive_values(redact_private_paths(payload))


def _compact(value: Any, limit: int = 120) -> str:
    sanitized, _ = core.sanitize_external_model_text(str(value or ""))
    return core.compact_text(sanitized, limit)


def _terms(values: Any, *, limit: int = 16) -> list[str]:
    raw: list[str] = []
    if isinstance(values, str):
        raw.append(values)
    elif isinstance(values, Mapping):
        raw.extend(str(value) for value in values.values())
    elif isinstance(values, Iterable):
        for value in values:
            raw.extend(_terms(value, limit=limit))
    out: list[str] = []
    for value in raw:
        text = _compact(value, 96)
        if not text:
            continue
        low = text.casefold()
        if any(marker in low for marker in ("api_key", "apikey", "password", "secret", "token=")):
            continue
        out.append(text)
    return unique_preserve(out, limit=limit)


def _safe_refs(value: Any) -> list[dict[str, Any]]:
    rows = value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []
    refs: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        clean = {
            str(key): row.get(key)
            for key in (
                "thread_key",
                "source_id",
                "message_id",
                "turn_id",
                "turn_index",
                "line",
                "source_line",
                "event_id",
            )
            if row.get(key) not in (None, "", [])
        }
        if clean:
            refs.append(clean)
    return refs[:8]


def _sidecar_root(cwd: str | Path | None, sidecar_dir: str | Path | None) -> Path:
    if sidecar_dir:
        return Path(sidecar_dir).expanduser().resolve()
    root = Path(cwd).expanduser().resolve() if cwd else Path.cwd().resolve()
    return root / DEFAULT_SIDECAR_DIR_NAME


def _first_existing(root: Path, filenames: Sequence[str]) -> Path | None:
    for filename in filenames:
        path = root / filename
        if path.is_file():
            return path
    return None


def _read_rows(path: Path | None) -> tuple[list[dict[str, Any]], int, str]:
    if path is None:
        return [], 0, "missing"
    if not path.is_file():
        return [], 0, "missing"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return [], 0, "unreadable"
    if not text:
        return [], 0, "empty"
    rows: list[dict[str, Any]] = []
    malformed = 0
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if data is None:
            for line in text.splitlines():
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    continue
                if isinstance(item, Mapping):
                    rows.append(dict(item))
                else:
                    malformed += 1
            return rows, malformed, "loaded" if rows else "malformed"
        if not isinstance(data, Mapping):
            return [], 1, "malformed"
        for key in ("rows", "candidates", "routes", "memory_packets"):
            value = data.get(key)
            if isinstance(value, list):
                rows.extend(dict(item) for item in value if isinstance(item, Mapping))
        entries = data.get("entries")
        if isinstance(entries, Mapping):
            rows.extend(dict(item) for item in entries.values() if isinstance(item, Mapping))
        if not rows and any(key in data for key in ("route_id", "candidate_id", "signal", "outcome", "source_refs")):
            rows.append(dict(data))
        if not rows:
            malformed = 1
        return rows, malformed, "loaded" if rows else "malformed"
    if text.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return [], 1, "malformed"
        if not isinstance(data, list):
            return [], 1, "malformed"
        rows.extend(dict(item) for item in data if isinstance(item, Mapping))
        malformed = sum(1 for item in data if not isinstance(item, Mapping))
        return rows, malformed, "loaded"
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(item, Mapping):
            rows.append(dict(item))
        else:
            malformed += 1
    return rows, malformed, "loaded" if rows or malformed == 0 else "malformed"


def _component(name: str, *, status: str, row_count: int, malformed_count: int = 0) -> dict[str, Any]:
    result = {
        "component": name,
        "status": status,
        "row_count": int(row_count),
        "malformed_row_count": int(malformed_count),
        "authority": "navigation_only_not_source_truth",
    }
    if status == "missing":
        result["next_action"] = "continue without this sidecar or pass an explicit path for local diagnostics"
    return result


def _bucket(row: Mapping[str, Any]) -> str:
    return str(row.get("scope_bucket") or row.get("privacy_partition") or row.get("privacy_domain") or "").casefold()


def _private_or_stale(row: Mapping[str, Any]) -> bool:
    status = str(row.get("freshness") or row.get("status") or row.get("currentness") or "").casefold()
    visibility = str(row.get("visibility") or "").casefold()
    return _bucket(row) in PRIVATE_BUCKETS or status in STALE_STATUSES or visibility == "blocked"


def _candidate_from_row(row: Mapping[str, Any], *, source: str) -> dict[str, Any] | None:
    source_refs = _safe_refs(row.get("source_refs") or row.get("candidate_refs"))
    terms = _terms(
        [
            row.get("route_terms"),
            row.get("terms"),
            row.get("query_terms"),
            row.get("query_aliases"),
            row.get("route_reasons"),
            row.get("title"),
            row.get("route_label"),
            row.get("summary"),
        ],
        limit=18,
    )
    route_id = _compact(
        row.get("route_id")
        or row.get("candidate_id")
        or row.get("lock_id")
        or row.get("id")
        or row.get("thread_key"),
        120,
    )
    if not route_id and not terms and not source_refs:
        return None
    candidate: dict[str, Any] = {
        "route_id": route_id or "route:sidecar",
        "candidate_id": _compact(row.get("candidate_id") or row.get("bridge_id") or "", 120),
        "thread_key": _compact(row.get("thread_key") or "", 120),
        "route_terms": terms,
        "source_refs": source_refs,
        "scope_bucket": _compact(_bucket(row), 80),
        "freshness": _compact(row.get("freshness") or row.get("status") or "", 80),
        "source": source,
    }
    return {key: value for key, value in candidate.items() if value not in ("", [], None)}


def _candidate_from_route(row: Mapping[str, Any], *, source: str) -> dict[str, Any] | None:
    route = dict(row)
    if not route.get("source_refs") and isinstance(route.get("memory_packet"), Mapping):
        packet = route["memory_packet"]
        route["source_refs"] = packet.get("source_refs")
        route["route_terms"] = packet.get("summary") or packet.get("title")
    if not route.get("source_refs") and isinstance(route.get("handle"), Mapping):
        route["source_refs"] = route["handle"].get("source_refs")
    return _candidate_from_row(route, source=source)


def _dedupe_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        marker = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(dict(row))
    return result


def build_associative_path_input_pack(
    *,
    query: str,
    cwd: str | Path | None = None,
    sidecar_dir: str | Path | None = None,
    candidates: Sequence[Mapping[str, Any]] | None = None,
    recall_context_payload: Mapping[str, Any] | None = None,
    memory_packets: Sequence[Mapping[str, Any]] | None = None,
    semantic_bridge_rows: Sequence[Mapping[str, Any]] | None = None,
    navigation_rows: Sequence[Mapping[str, Any]] | None = None,
    active_lock_rows: Sequence[Mapping[str, Any]] | None = None,
    feedback_rows: Sequence[Mapping[str, Any]] | None = None,
    semantic_bridge_path: str | Path | None = None,
    navigation_path: str | Path | None = None,
    active_lock_path: str | Path | None = None,
    feedback_path: str | Path | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    root = _sidecar_root(cwd, sidecar_dir)
    components: list[dict[str, Any]] = []
    malformed_count = 0

    def load_component(
        name: str,
        explicit_rows: Sequence[Mapping[str, Any]] | None,
        explicit_path: str | Path | None,
        filenames: Sequence[str],
    ) -> list[dict[str, Any]]:
        nonlocal malformed_count
        if explicit_rows is not None:
            rows = [dict(row) for row in explicit_rows if isinstance(row, Mapping)]
            malformed = len(explicit_rows) - len(rows)
            malformed_count += malformed
            components.append(_component(name, status="injected", row_count=len(rows), malformed_count=malformed))
            return rows
        path = Path(explicit_path).expanduser().resolve() if explicit_path else _first_existing(root, filenames)
        rows, malformed, status = _read_rows(path)
        malformed_count += malformed
        components.append(_component(name, status=status, row_count=len(rows), malformed_count=malformed))
        return rows

    bridge_rows = load_component(
        "semantic_bridge_rows", semantic_bridge_rows, semantic_bridge_path, BRIDGE_FILENAMES
    )
    nav_rows = load_component(
        "navigation_potential_rows", navigation_rows, navigation_path, NAVIGATION_FILENAMES
    )
    lock_rows = load_component("active_recall_locks", active_lock_rows, active_lock_path, ACTIVE_LOCK_FILENAMES)
    feedback = load_component("feedback_rows", feedback_rows, feedback_path, FEEDBACK_FILENAMES)

    candidate_rows: list[dict[str, Any]] = []
    for row in candidates or []:
        if isinstance(row, Mapping):
            candidate = _candidate_from_route(row, source="explicit_candidate")
            if candidate:
                candidate_rows.append(candidate)
    if recall_context_payload is not None:
        routes = recall_context_payload.get("routes") if isinstance(recall_context_payload, Mapping) else []
        for row in routes or []:
            if isinstance(row, Mapping):
                candidate = _candidate_from_route(row, source="recall_context")
                if candidate:
                    candidate_rows.append(candidate)
    for row in memory_packets or []:
        if isinstance(row, Mapping):
            candidate = _candidate_from_route(row, source="memory_packet")
            if candidate:
                candidate_rows.append(candidate)
    for row in nav_rows:
        candidate = _candidate_from_row(row, source="navigation_potential")
        if candidate:
            candidate_rows.append(candidate)
    for row in lock_rows:
        candidate = _candidate_from_row(row, source="active_recall_lock")
        if candidate:
            candidate_rows.append(candidate)
    candidates_clean = _dedupe_rows([row for row in candidate_rows if row])
    source_free_count = sum(1 for row in candidates_clean if not row.get("source_refs") and not row.get("thread_key"))
    private_or_stale_count = sum(
        1 for row in [*candidates_clean, *bridge_rows, *feedback, *nav_rows, *lock_rows] if _private_or_stale(row)
    )
    accepted_bridge_count = sum(
        1 for row in bridge_rows if str(row.get("status") or "accepted").casefold() == "accepted"
    )
    reason_codes = []
    if candidates_clean or accepted_bridge_count:
        reason_codes.append("associative_path_input_pack_ready")
    else:
        reason_codes.append("associative_path_input_pack_empty")
    if malformed_count:
        reason_codes.append("malformed_sidecar_rows_ignored")
    if private_or_stale_count:
        reason_codes.append("private_or_stale_rows_visible_to_guard")
    if source_free_count:
        reason_codes.append("source_free_candidates_will_evaporate")

    pack = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "query_term_count": len(_terms(query, limit=24)),
        "candidates": candidates_clean[: max(1, int(limit))],
        "semantic_bridge_rows": _dedupe_rows(bridge_rows)[: max(1, int(limit) * 2)],
        "navigation_rows": _dedupe_rows(nav_rows)[: max(1, int(limit) * 2)],
        "active_lock_rows": _dedupe_rows(lock_rows)[: max(1, int(limit) * 2)],
        "feedback_rows": _dedupe_rows(feedback)[: max(1, int(limit) * 2)],
        "components": components,
        "reason_codes": unique_preserve(reason_codes, limit=8),
        "metrics": {
            "candidate_count": len(candidates_clean),
            "semantic_bridge_row_count": len(bridge_rows),
            "accepted_semantic_bridge_row_count": accepted_bridge_count,
            "navigation_row_count": len(nav_rows),
            "active_lock_row_count": len(lock_rows),
            "feedback_row_count": len(feedback),
            "malformed_row_count": malformed_count,
            "private_or_stale_row_count": private_or_stale_count,
            "source_free_candidate_count": source_free_count,
        },
        "boundary": {
            "writes_files": False,
            "changes_default_recall_ranking": False,
            "feedback_is_not_source_truth": True,
            "source_reopen_required_before_claim": True,
        },
        "cannot_claim": ["associative_path_pack_as_source_truth"],
    }
    return _public_payload(pack)


def build_associative_path_diagnostic(
    *,
    query: str,
    input_pack: Mapping[str, Any] | None = None,
    max_routes: int = 3,
    **pack_kwargs: Any,
) -> dict[str, Any]:
    pack = (
        dict(input_pack)
        if isinstance(input_pack, Mapping)
        else build_associative_path_input_pack(query=query, limit=max_routes * 2, **pack_kwargs)
    )
    walk = walk_associative_paths(
        query=query,
        candidates=[row for row in pack.get("candidates") or [] if isinstance(row, Mapping)],
        bridge_rows=[row for row in pack.get("semantic_bridge_rows") or [] if isinstance(row, Mapping)],
        # The input-pack builder already materializes navigation and active-lock
        # sidecars into `candidates`. Passing the raw rows again would let the
        # walker materialize the same route twice, inflating route-count and
        # usefulness diagnostics without adding a new reopenable path.
        navigation_rows=[],
        active_locks=[],
        feedback_rows=[row for row in pack.get("feedback_rows") or [] if isinstance(row, Mapping)],
        limit=max_routes,
    )
    candidates = [row for row in walk.get("candidates") or [] if isinstance(row, Mapping)]
    next_actions = [
        {
            "id": "deepen_associative_path_candidate",
            "label": "Deepen APW route candidate",
            "route_id": candidate.get("route_id"),
            "mutation_risk": "read_only",
            "claim_boundary": "no_claim_before_reopen",
            "why": "APW found a navigation route; reopen source before using it.",
        }
        for candidate in candidates[:3]
    ]
    if not next_actions:
        next_actions.append(
            {
                "id": "tighten_cue_or_continue_without_apw",
                "label": "Tighten cue or continue",
                "mutation_risk": "read_only",
                "claim_boundary": "diagnostic_not_source_evidence",
                "why": "APW did not find a source-reopenable route from the available sidecars.",
            }
        )
    pack_metrics = dict(pack.get("metrics") or {})
    walk_metrics = dict(walk.get("metrics") or {})
    result = {
        "kind": DIAGNOSTIC_KIND,
        "schema_version": SCHEMA_VERSION,
        "opt_in_required": True,
        "applied_to_default_ranking": False,
        "decision": walk.get("decision"),
        "candidate_count": int(walk.get("candidate_count") or 0),
        "top_candidates": candidates[:3],
        "next_actions": next_actions,
        "reason_codes": unique_preserve(
            [*(pack.get("reason_codes") or []), *(walk.get("reason_codes") or [])],
            limit=12,
        ),
        "metrics": {
            **pack_metrics,
            **walk_metrics,
            "blocked_or_evaporated_count": int(walk_metrics.get("blocked_private_or_stale_count") or 0)
            + int(walk_metrics.get("evaporated_path_count") or 0),
        },
        "input_pack_summary": {
            "kind": pack.get("kind"),
            "components": pack.get("components") or [],
            "boundary": pack.get("boundary") or {},
        },
        "claim_boundary": "navigation_only_no_claim_before_reopen",
        "cannot_claim": [
            "associative_path_diagnostic_as_source_truth",
            "default_recall_quality_lift",
            "source_claim_without_reopen",
        ],
    }
    return _public_payload(result)
