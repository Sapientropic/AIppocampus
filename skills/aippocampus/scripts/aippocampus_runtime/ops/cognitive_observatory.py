#!/usr/bin/env python3
"""Read-only Cognitive Observatory report over existing diagnostic surfaces."""

from __future__ import annotations

import argparse
import html as html_lib
import json
from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime.dream.sleep_cycle import public_sleep_cycle_summary
from aippocampus_runtime.ops import observatory_boundary
from aippocampus_runtime.ops.activation_authority_audit import (
    activation_surface_authority_audit,
)
from aippocampus_runtime.ops.observatory_cognitive_load import (
    cognitive_load_calibration_summary,
)
from aippocampus_runtime.ops.observatory_control_authority import (
    observatory_control_authority_audit,
)
from aippocampus_runtime.ops.route_readiness import (
    ROUTE_READINESS_KIND,
    fixture_route_readiness_report,
    route_readiness_report,
)
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.public_output import emit_public_text
from aippocampus_runtime.recall.why_diagnostics import recall_diagnostic_report
from aippocampus_runtime.warm_ambient.query_pattern_routes import query_pattern_routes_report

OBSERVATORY_KIND = "aippocampus_cognitive_observatory_readout"
OBSERVATORY_SCHEMA_VERSION = 1


def _codes(row: Mapping[str, Any]) -> list[str]:
    values = row.get("reason_codes")
    return [str(item) for item in values] if isinstance(values, list) else []


def _panel_item(
    *,
    surface: str,
    label: Any,
    next_action: str,
    reason_codes: list[str],
    authority: str = "navigation_only",
) -> dict[str, Any]:
    return {
        "surface": surface,
        "label": str(label or surface),
        "authority": authority,
        "next_action": next_action,
        "reason_codes": reason_codes[:6],
    }


def _campus_usefulness_panels(
    *,
    readiness: Mapping[str, Any],
    authority: Mapping[str, Any],
    query_routes: Mapping[str, Any] | None,
    cognitive_load: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Project usefulness-first Observatory panels without adding new scoring.

    These panels reuse existing diagnostics so Campus can expose product
    usefulness failures without becoming a planner, truth source, or foreground
    ranking layer. A row appears because an owner report already said it was
    ready, suppressed, blocked, stale, or noisy.
    """

    useful_now: list[dict[str, Any]] = []
    wasted_motion: list[dict[str, Any]] = []
    quiet_for_a_reason: list[dict[str, Any]] = []
    needs_ripening: list[dict[str, Any]] = []

    for row in readiness.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        codes = _codes(row)
        label = row.get("route_id") or row.get("surface_kind") or "route"
        if row.get("status") == "ready":
            useful_now.append(
                _panel_item(
                    surface=str(row.get("surface_kind") or "route_readiness"),
                    label=label,
                    next_action="reopen_source_before_claim",
                    reason_codes=["reduces_manual_search", *codes],
                )
            )
            continue
        code_text = " ".join(codes)
        if any(term in code_text for term in ("privacy", "secret", "stale", "deleted", "high_risk", "external")):
            quiet_for_a_reason.append(
                _panel_item(
                    surface=str(row.get("surface_kind") or "route_readiness"),
                    label=label,
                    next_action="stay_silent_or_refresh_source",
                    reason_codes=codes,
                )
            )
        elif any(term in code_text for term in ("low_value", "low_roi", "wrong_route", "generic", "drag")):
            wasted_motion.append(
                _panel_item(
                    surface=str(row.get("surface_kind") or "route_readiness"),
                    label=label,
                    next_action="do_not_surface_until_useful",
                    reason_codes=codes,
                )
            )
        else:
            needs_ripening.append(
                _panel_item(
                    surface=str(row.get("surface_kind") or "route_readiness"),
                    label=label,
                    next_action="add_source_support_or_review",
                    reason_codes=codes or ["candidate_needs_support"],
                )
            )

    for row in authority.get("surfaces") or []:
        if not isinstance(row, Mapping):
            continue
        label = row.get("surface_id") or row.get("surface_kind") or "activation_surface"
        surface_kind = str(row.get("surface_kind") or "activation_surface")
        authority_level = str(row.get("authority_level") or "navigation_only")
        if row.get("eligible_for_foreground") and row.get("source_ref_count"):
            useful_now.append(
                _panel_item(
                    surface=surface_kind,
                    label=label,
                    authority=authority_level,
                    next_action="use_as_low_authority_route_hint",
                    reason_codes=["active_and_source_reopenable"],
                )
            )
        if int(row.get("wrong_route_drag_count") or 0) > 0:
            wasted_motion.append(
                _panel_item(
                    surface=surface_kind,
                    label=label,
                    authority=authority_level,
                    next_action="suppress_or_rework_route",
                    reason_codes=["wrong_route_drag"],
                )
            )
        if row.get("pruning_action") in {"retire", "dead_letter", "park"}:
            quiet_for_a_reason.append(
                _panel_item(
                    surface=surface_kind,
                    label=label,
                    authority=authority_level,
                    next_action="keep_out_of_foreground",
                    reason_codes=[f"pruning_{row.get('pruning_action')}"],
                )
            )
        if authority_level in {"candidate", "review_required"}:
            needs_ripening.append(
                _panel_item(
                    surface=surface_kind,
                    label=label,
                    authority=authority_level,
                    next_action="review_before_activation",
                    reason_codes=["candidate_activation_needs_review"],
                )
            )

    if query_routes:
        metrics = query_routes.get("metrics") or {}
        if int(metrics.get("active_route_count") or 0) > 0:
            useful_now.append(
                _panel_item(
                    surface="query_pattern_routes",
                    label="active query-pattern routes",
                    next_action="reuse_route_handle_then_reopen_source",
                    reason_codes=["active_query_pattern_route"],
                )
            )
        if int(metrics.get("stale_suppressed_count") or 0) or int(
            metrics.get("privacy_suppressed_count") or 0
        ):
            quiet_for_a_reason.append(
                _panel_item(
                    surface="query_pattern_routes",
                    label="suppressed query-pattern routes",
                    next_action="stay_silent_or_refresh_source",
                    reason_codes=["stale_or_privacy_suppressed"],
                )
            )

    if cognitive_load:
        metrics = cognitive_load.get("metrics") or {}
        if int(metrics.get("irrelevant_load_drag_count") or 0) > 0:
            wasted_motion.append(
                _panel_item(
                    surface="cognitive_load_calibration",
                    label="irrelevant load drag",
                    next_action="do_not_boost_this_route",
                    reason_codes=["irrelevant_load_drag"],
                )
            )
        if int(metrics.get("helpful_caution_hint_count") or 0) > 0:
            useful_now.append(
                _panel_item(
                    surface="cognitive_load_calibration",
                    label="helpful caution hints",
                    next_action="keep_caution_hint_available",
                    reason_codes=["reviewed_helpful_caution"],
                )
            )

    panels = {
        "useful_now": useful_now[:12],
        "wasted_motion": wasted_motion[:12],
        "quiet_for_a_reason": quiet_for_a_reason[:12],
        "needs_ripening": needs_ripening[:12],
    }
    return {
        "kind": "aippocampus_campus_usefulness_panels",
        "read_only": True,
        "not_control_plane": True,
        "panels": panels,
        "metrics": {f"{name}_count": len(items) for name, items in panels.items()},
        "contract": {
            "uses_existing_diagnostics_only": True,
            "does_not_rank_or_activate_routes": True,
            "source_reopen_required_before_claim": True,
        },
    }


def _load_json(path: str | Path | None) -> Any:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_json_or_jsonl(path: str | Path | None) -> Any:
    if not path:
        return None
    source = Path(path)
    if source.suffix.casefold() == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line in source.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if isinstance(item, Mapping):
                rows.append(dict(item))
        return rows
    return _load_json(source)


def _as_list(value: Any, key: str) -> list[dict[str, Any]]:
    payload = value
    if isinstance(value, Mapping):
        payload = value.get(key) or value.get("rows") or value.get("route_candidates")
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, Mapping)]
    return []


def _as_mapping(value: Any, key: str | None = None) -> dict[str, Any] | None:
    payload = value.get(key) if key and isinstance(value, Mapping) else value
    return dict(payload) if isinstance(payload, Mapping) else None


def _recall_diagnostic_from_fixture() -> dict[str, Any]:
    return recall_diagnostic_report(
        cue="route readiness observatory fixture",
        mode="why-recall",
        recall_context_payload={
            "routes": [
                {
                    "route_id": "observatory-route",
                    "source_reopen_required": True,
                    "source_refs": [{"source_id": "clean:route-ready", "message_id": "m1"}],
                }
            ],
            "query_terms": ["route", "readiness"],
        },
        active_lock_payload={
            "state": "ready",
            "lock_id": "fixture-lock",
            "candidate_ref_count": 1,
            "reopenable_ref_count": 1,
            "source_reopen_required": True,
        },
        ambient_cache_payload={
            "status": "hit",
            "cards": [
                {
                    "support_level": "candidate",
                    "source_reopen_required": True,
                    "source_refs": [{"source_id": "clean:ambient", "message_id": "m2"}],
                }
            ],
        },
        semantic_gate_payload={
            "available": False,
            "decision": "skip",
            "availability_reason": "semantic_disabled_or_auth_unavailable",
            "error_buckets": {},
            "worker_count": 0,
        },
    )


def fixture_cognitive_observatory_readout() -> dict[str, Any]:
    fixed_route_readiness = fixture_route_readiness_report()
    activation_surfaces: list[dict[str, Any]] = [
        {
            "surface_id": "ready-active-lock",
            "surface_kind": "active_recall_lock",
            "conflict_key": "route-readiness",
            "freshness": "current",
            "source_refs": [{"source_id": "clean:route-ready", "message_id": "m1"}],
            "source_reopen_success_count": 1,
            "recent_helpful_count": 1,
        },
        {
            "surface_id": "stale-ambient-card",
            "surface_kind": "ambient_card",
            "conflict_key": "route-readiness",
            "freshness": "stale",
            "pruning_action": "retire",
            "wrong_route_drag_count": 3,
            "source_refs": [{"source_id": "clean:old", "message_id": "m2"}],
        },
        {
            "surface_id": "source-reopened-row",
            "surface_kind": "source_reopen_evidence",
            "conflict_key": "route-readiness",
            "source_refs": [{"source_id": "clean:route-ready", "message_id": "m1"}],
        },
        {
            "surface_id": "activation-pruning-row",
            "surface_kind": "pruning_row",
            "conflict_key": "route-readiness-pruning",
            "pruning_action": "park",
        },
    ]
    sleep_cycle_payload = {
        "execution_mode": "fixture",
        "no_write": True,
        "write_mode": "no_write",
        "run_ready": False,
        "counts": {
            "queue_items": 2,
            "selected_items": 0,
            "accepted": 0,
            "parked": 1,
            "rejected": 1,
            "written_findings": 0,
            "written_working_memory": 0,
        },
        "worker_statuses": {"deterministic_only": 1},
        "failure_buckets": {},
        "cache": {"hit": 0, "miss": 0},
    }
    return cognitive_observatory_readout(
        route_readiness=fixed_route_readiness,
        activation_surfaces=activation_surfaces,
        recall_diagnostic=_recall_diagnostic_from_fixture(),
        sleep_cycle_payload=sleep_cycle_payload,
        query_pattern_routes=[
            {
                "query_aliases": ["fixture query pattern route"],
                "source_generation_digest": "gen-observatory-v1",
                "thread_key_hash": "thread_observatory",
                "source_refs": [{"source_id": "clean:query-pattern", "message_id": "m3"}],
                "created_unix": 1_800_000_000,
                "ttl_seconds": 900,
                "confidence": 0.9,
            }
        ],
        now_unix=1_800_000_120,
    )


def cognitive_observatory_readout(
    *,
    route_candidates: list[dict[str, Any]] | None = None,
    route_readiness: Mapping[str, Any] | None = None,
    active_lock_roi: Mapping[str, Any] | None = None,
    activation_surfaces: list[dict[str, Any]] | None = None,
    recall_diagnostic: Mapping[str, Any] | None = None,
    sleep_cycle_payload: Mapping[str, Any] | None = None,
    query_pattern_routes: list[dict[str, Any]] | None = None,
    cognitive_load_calibration: Mapping[str, Any] | None = None,
    now_unix: float | None = None,
    min_roi_score: float = 1.0,
) -> dict[str, Any]:
    if route_readiness and route_readiness.get("kind") == ROUTE_READINESS_KIND:
        readiness = dict(route_readiness)
    else:
        readiness = route_readiness_report(
            route_candidates or [],
            active_lock_roi=active_lock_roi,
            min_roi_score=min_roi_score,
        )
    authority = activation_surface_authority_audit(activation_surfaces or [])
    diagnostic = dict(recall_diagnostic) if isinstance(recall_diagnostic, Mapping) else None
    sleep_summary = (
        public_sleep_cycle_summary(sleep_cycle_payload)
        if isinstance(sleep_cycle_payload, Mapping)
        else None
    )
    query_routes = (
        query_pattern_routes_report(query_pattern_routes, now_unix=now_unix)
        if query_pattern_routes is not None
        else None
    )
    cognitive_load = cognitive_load_calibration_summary(cognitive_load_calibration)
    campus_panels = _campus_usefulness_panels(
        readiness=readiness,
        authority=authority,
        query_routes=query_routes,
        cognitive_load=cognitive_load,
    )
    metrics = {
        "route_ready_count": (readiness.get("metrics") or {}).get("ready_count", 0),
        "route_suppressed_count": (readiness.get("metrics") or {}).get("suppressed_count", 0),
        "activation_surface_count": len(authority.get("surfaces") or []),
        "activation_conflict_count": (authority.get("metrics") or {}).get("conflict_count", 0),
        "recall_diagnostic_present": diagnostic is not None,
        "sleep_summary_present": sleep_summary is not None,
        "query_pattern_route_count": (query_routes or {}).get("metrics", {}).get("route_count", 0),
        "query_pattern_active_route_count": (query_routes or {})
        .get("metrics", {})
        .get("active_route_count", 0),
        "cognitive_load_calibration_present": cognitive_load is not None,
        "cognitive_load_signal_event_count": (cognitive_load or {})
        .get("metrics", {})
        .get("signal_event_count", 0),
        "cognitive_load_public_feedback_case_count": (cognitive_load or {})
        .get("metrics", {})
        .get("public_behavior_trace_case_count", 0),
        "campus_useful_now_count": campus_panels["metrics"]["useful_now_count"],
        "campus_wasted_motion_count": campus_panels["metrics"]["wasted_motion_count"],
        "campus_quiet_for_a_reason_count": campus_panels["metrics"][
            "quiet_for_a_reason_count"
        ],
        "campus_needs_ripening_count": campus_panels["metrics"]["needs_ripening_count"],
    }
    surfaces = ["route_readiness", "activation_authority"]
    surfaces.append("campus_usefulness_panels")
    if diagnostic:
        surfaces.append("recall_diagnostic")
    if sleep_summary:
        surfaces.append("sleep_cycle")
    if query_routes:
        surfaces.append("query_pattern_routes")
    if cognitive_load:
        surfaces.append("cognitive_load_calibration")
    control_authority = observatory_control_authority_audit(
        activation_surfaces=activation_surfaces or [],
        activation_authority=authority,
    )
    readiness = observatory_boundary.with_boundary_detail(readiness)
    control_authority = observatory_boundary.with_boundary_detail(control_authority)
    readout_state = observatory_boundary.readout_state(readiness, metrics)
    foreground_action = _foreground_action(no_rows=readout_state["status"] == "no_rows")
    report = {
        "kind": OBSERVATORY_KIND,
        "schema_version": OBSERVATORY_SCHEMA_VERSION,
        "ok": True,
        "no_write": True,
        "issues": [574, *([575] if cognitive_load else []), 576],
        "surfaces": surfaces,
        "route_readiness": readiness,
        "activation_authority": authority,
        "control_authority_audit": control_authority,
        "campus_usefulness_panels": campus_panels,
        "recall_diagnostic": diagnostic,
        "sleep_cycle": sleep_summary,
        "query_pattern_routes": query_routes,
        "cognitive_load_calibration": cognitive_load,
        "metrics": metrics,
        "readout_state": readout_state,
        "foreground_action": foreground_action,
        "agent_next_action": foreground_action,
        "safe_next_actions": [foreground_action],
        "claim_boundary": _compact_claim_boundary(),
        "boundary_detail": observatory_boundary.boundary_detail(route_readiness=readiness, control_authority=control_authority),
        "contract": {
            "read_only_report": True,
            "not_control_plane": True,
            "clean_source_mutation_allowed": False,
            "owner_surface_mutation_allowed": False,
            "foreground_hook_mutation_allowed": False,
            "route_readiness_is_navigation_only": True,
            "activation_pruning_changes_activation_eligibility_only": True,
            "source_reopen_required_before_claim": True,
        },
        "privacy_boundary": {
            "raw_prompt_serialized": False,
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
            "sensitive_values_serialized": False,
        },
        "can_claim": observatory_boundary.CAN_CLAIM,
    }

    return redact_sensitive_values(redact_private_paths(report))

def _html(value: Any) -> str:
    if value is True:
        text = "true"
    elif value is False:
        text = "false"
    elif value is None:
        text = ""
    else:
        text = str(value)
    return html_lib.escape(text, quote=True)


def _join_codes(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item or "").strip())
    return str(value or "")


def _metric_cards(metrics: Mapping[str, Any]) -> str:
    labels = [
        ("route_ready_count", "Ready routes"),
        ("route_suppressed_count", "Suppressed routes"),
        ("activation_surface_count", "Activation surfaces"),
        ("activation_conflict_count", "Authority conflicts"),
        ("recall_diagnostic_present", "Recall diagnostic"),
        ("sleep_summary_present", "Sleep summary"),
        ("query_pattern_active_route_count", "Query-pattern routes"),
        ("cognitive_load_signal_event_count", "Load signals"),
    ]
    cards = []
    for key, label in labels:
        cards.append(
            "<section class=\"metric\">"
            f"<span>{_html(label)}</span>"
            f"<strong>{_html(metrics.get(key, 0))}</strong>"
            "</section>"
        )
    return "\n".join(cards)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "<p class=\"muted\">No rows supplied.</p>"
    head = "".join(f"<th>{_html(header)}</th>" for header in headers)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{_html(cell)}</td>" for cell in row)
        body_rows.append(f"<tr>{cells}</tr>")
    return (
        "<div class=\"table-wrap\"><table>"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )


def _list_block(title: str, items: Any) -> str:
    values = [str(item) for item in items or [] if str(item or "").strip()]
    if not values:
        return ""
    rendered = "".join(f"<li>{_html(item)}</li>" for item in values)
    return f"<section><h2>{_html(title)}</h2><ul>{rendered}</ul></section>"


def _panel_table(title: str, rows: Any) -> str:
    items = [row for row in rows or [] if isinstance(row, Mapping)]
    return (
        f"<section><h2>{_html(title)}</h2>"
        + _table(
            ["surface", "label", "next action", "reason codes"],
            [
                [
                    row.get("surface"),
                    row.get("label"),
                    row.get("next_action"),
                    _join_codes(row.get("reason_codes")),
                ]
                for row in items[:12]
            ],
        )
        + "</section>"
    )


def render_html(report: Mapping[str, Any]) -> str:
    """Render a static, no-script Observatory view from a sanitized report.

    The HTML is an operator view over the same public-safe readout. It is not a
    control surface: rows remain navigation diagnostics, and source-backed
    claims still require reopening source through the referenced ids.
    """

    raw_metrics = report.get("metrics")
    metrics: Mapping[str, Any] = raw_metrics if isinstance(raw_metrics, Mapping) else {}
    raw_contract = report.get("contract")
    contract: Mapping[str, Any] = raw_contract if isinstance(raw_contract, Mapping) else {}
    raw_readiness = report.get("route_readiness")
    readiness: Mapping[str, Any] = (
        raw_readiness if isinstance(raw_readiness, Mapping) else {}
    )
    readiness_rows = [
        row for row in readiness.get("rows") or [] if isinstance(row, Mapping)
    ]
    raw_authority = report.get("activation_authority")
    authority: Mapping[str, Any] = (
        raw_authority if isinstance(raw_authority, Mapping) else {}
    )
    authority_rows = [
        row for row in authority.get("surfaces") or [] if isinstance(row, Mapping)
    ]
    raw_panels = report.get("campus_usefulness_panels")
    campus: Mapping[str, Any] = raw_panels if isinstance(raw_panels, Mapping) else {}
    raw_panel_rows = campus.get("panels")
    panel_rows: Mapping[str, Any] = raw_panel_rows if isinstance(raw_panel_rows, Mapping) else {}
    route_table = _table(
        [
            "status",
            "surface",
            "readiness",
            "freshness",
            "ttl",
            "roi",
            "refs",
            "reason codes",
        ],
        [
            [
                row.get("status"),
                row.get("surface_kind"),
                row.get("readiness_class"),
                row.get("freshness"),
                row.get("ttl_remaining_seconds"),
                row.get("roi_score"),
                row.get("source_ref_count"),
                _join_codes(row.get("reason_codes")),
            ]
            for row in readiness_rows[:24]
        ],
    )
    authority_table = _table(
        [
            "surface",
            "authority",
            "freshness",
            "pruning",
            "foreground",
            "refs",
        ],
        [
            [
                row.get("surface_kind"),
                row.get("authority_level"),
                row.get("freshness"),
                row.get("pruning_action"),
                row.get("eligible_for_foreground"),
                row.get("source_ref_count"),
            ]
            for row in authority_rows[:24]
        ],
    )
    surfaces = ", ".join(str(item) for item in report.get("surfaces") or [])
    source_reopen_required = bool(contract.get("source_reopen_required_before_claim"))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Cognitive Observatory</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f7f7f4;
      --ink: #1d2526;
      --muted: #5f6b6d;
      --line: #cfd8d5;
      --panel: #ffffff;
      --accent: #276a73;
      --warn: #8b4e1f;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #111615;
        --ink: #edf2ee;
        --muted: #a8b5b0;
        --line: #34423e;
        --panel: #18201e;
        --accent: #80c7cc;
        --warn: #e0a66b;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1120px, calc(100% - 32px));
      margin: 0 auto;
      padding: 32px 0 48px;
    }}
    header {{ margin-bottom: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; letter-spacing: 0; }}
    h2 {{ margin: 28px 0 10px; font-size: 18px; letter-spacing: 0; }}
    p {{ margin: 0 0 10px; }}
    .muted {{ color: var(--muted); }}
    .boundary {{
      border-left: 4px solid var(--accent);
      padding: 12px 14px;
      background: color-mix(in srgb, var(--panel) 92%, var(--accent));
      margin: 16px 0;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 10px;
      margin: 18px 0 10px;
    }}
    .metric {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 6px;
      padding: 12px;
      min-height: 74px;
    }}
    .metric span {{ display: block; color: var(--muted); font-size: 12px; }}
    .metric strong {{ display: block; margin-top: 6px; font-size: 22px; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 6px; }}
    table {{ width: 100%; border-collapse: collapse; background: var(--panel); }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ font-size: 12px; color: var(--muted); font-weight: 650; }}
    tr:last-child td {{ border-bottom: 0; }}
    ul {{ margin: 0; padding-left: 20px; }}
    .warn {{ color: var(--warn); font-weight: 650; }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>Cognitive Observatory</h1>
    <p class="muted">{_html(report.get("kind"))} v{_html(report.get("schema_version"))}</p>
  </header>
  <section class="boundary">
    <p><strong>Read-only diagnostic.</strong> This static view is not a control plane and is not source truth.</p>
    <p>Rows are navigation_only diagnostics. Source reopen is required before any specific memory-backed claim: <span class="warn">{_html(source_reopen_required)}</span>.</p>
    <p class="muted">Surfaces: {_html(surfaces)}</p>
  </section>
  <section class="grid">
    {_metric_cards(metrics)}
  </section>
  <section>
    <h2>Route Readiness</h2>
    {route_table}
  </section>
  <section>
    <h2>Activation Authority</h2>
    {authority_table}
  </section>
  {_panel_table("Useful Now", panel_rows.get("useful_now"))}
  {_panel_table("Wasted Motion", panel_rows.get("wasted_motion"))}
  {_panel_table("Quiet For A Reason", panel_rows.get("quiet_for_a_reason"))}
  {_panel_table("Needs Ripening", panel_rows.get("needs_ripening"))}
  {_list_block("Can Claim", report.get("can_claim"))}
  {_list_block("Cannot Claim", report.get("cannot_claim"))}
</main>
</body>
</html>
"""


def render_text(report: Mapping[str, Any]) -> str:
    metrics = report.get("metrics") or {}
    contract = report.get("contract") or {}
    next_action = "Use ready routes only as navigation; reopen source before claims."
    previews = _panel_previews(report)
    lines = [
        "Cognitive Observatory readout",
        f"  route ready: {metrics.get('route_ready_count', 0)}",
        f"  route suppressed: {metrics.get('route_suppressed_count', 0)}",
        f"  activation surfaces: {metrics.get('activation_surface_count', 0)}",
        f"  useful now: {metrics.get('campus_useful_now_count', 0)}",
        f"  wasted motion: {metrics.get('campus_wasted_motion_count', 0)}",
        f"  quiet for a reason: {metrics.get('campus_quiet_for_a_reason_count', 0)}",
    ]
    if not any(previews.values()):
        lines.extend(
            [
                "  no diagnostic inputs loaded: this is an empty readout, not evidence that no routes exist.",
                "  try: aippocampus observatory --fixture",
                "  try: aippocampus observatory --summary-json",
            ]
        )
    else:
        for panel in ("useful_now", "wasted_motion", "quiet_for_a_reason", "needs_ripening"):
            rows = previews.get(panel) or []
            lines.append(f"  {panel}:")
            for row in rows:
                reason = ",".join(row.get("reason_codes") or [])
                lines.append(
                    "    - "
                    + f"{row.get('surface')} / {row.get('label')}: "
                    + f"{row.get('next_action')} ({reason})"
                )
    lines.extend(
        [
            f"  next: {next_action}",
            f"  no write: {str(report.get('no_write')).lower()}",
            f"  control plane: {str(not contract.get('not_control_plane')).lower()}",
            "",
        ]
    )
    return "\n".join(lines)


def _panel_previews(report: Mapping[str, Any], *, limit: int = 3) -> dict[str, list[dict[str, Any]]]:
    raw_panels = report.get("campus_usefulness_panels")
    panel_container = raw_panels if isinstance(raw_panels, Mapping) else {}
    panels = panel_container.get("panels")
    panel_map = panels if isinstance(panels, Mapping) else {}
    previews: dict[str, list[dict[str, Any]]] = {}
    for name in ("useful_now", "wasted_motion", "quiet_for_a_reason", "needs_ripening"):
        rows: list[dict[str, Any]] = []
        for item in list(panel_map.get(name) or [])[:limit]:
            if not isinstance(item, Mapping):
                continue
            rows.append(
                {
                    "surface": str(item.get("surface") or "unknown"),
                    "label": str(item.get("label") or "row"),
                    "next_action": str(item.get("next_action") or "reopen_source_before_claim"),
                    "reason_codes": [str(code) for code in item.get("reason_codes") or []][:4],
                }
            )
        previews[name] = rows
    return previews


def _foreground_action(*, no_rows: bool = False) -> dict[str, Any]:
    if no_rows:
        return {
            "id": "no_observatory_rows_to_route",
            "kind": "no_op",
            "command": "no-op",
            "mutation_risk": "none",
            "claim_boundary": "observatory_readout_not_source_truth_or_control_plane",
            "why": "No ready/useful observatory rows are present in this compact readout.",
        }
    return {
        "id": "use_observatory_as_read_only_navigation",
        "kind": "shell_command",
        "command": "aippocampus observatory --summary-json",
        "mutation_risk": "read_only",
        "claim_boundary": "observatory_readout_not_source_truth_or_control_plane",
        "why": "Use ready/useful rows as navigation only; reopen source before claims and use owner tools for mutation.",
    }


def _compact_claim_boundary() -> dict[str, Any]:
    return {
        "can_use_for": ["route_readiness_triage", "observability_review"],
        "must_reopen_for": ["source_backed_claims", "control_state_changes"],
        "detail_available_with": "aippocampus observatory --json",
    }


def summary_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    metrics = report.get("metrics") or {}
    readout_state = report.get("readout_state")
    no_rows = (
        isinstance(readout_state, Mapping)
        and str(readout_state.get("status") or "") == "no_rows"
    )
    action = _foreground_action(no_rows=no_rows)
    return {
        "kind": "aippocampus_cognitive_observatory_summary",
        "ok": bool(report.get("ok")),
        "read_only": bool(report.get("no_write")),
        "not_control_plane": bool((report.get("contract") or {}).get("not_control_plane")),
        "route_ready_count": metrics.get("route_ready_count", 0),
        "route_suppressed_count": metrics.get("route_suppressed_count", 0),
        "activation_surface_count": metrics.get("activation_surface_count", 0),
        "useful_now_count": metrics.get("campus_useful_now_count", 0),
        "wasted_motion_count": metrics.get("campus_wasted_motion_count", 0),
        "quiet_for_a_reason_count": metrics.get("campus_quiet_for_a_reason_count", 0),
        "needs_ripening_count": metrics.get("campus_needs_ripening_count", 0),
        "panel_previews": _panel_previews(report),
        "surfaces": list(report.get("surfaces") or [])[:12],
        "full_audit_flag": "--json",
        "html_flag": "--html",
        "privacy_boundary": report.get("privacy_boundary"),
        "foreground_action": action,
        "claim_boundary": _compact_claim_boundary(),
        "agent_next_action": (
            "Use ready rows as navigation only, reopen source before claims, and treat suppressed rows as intentional silence."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aippocampus observatory",
        usage=(
            "aippocampus observatory [--summary-json|--json|--html] "
            "[--fixture] [operator/audit inputs]"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Foreground summary:
  aippocampus observatory --summary-json
  One-screen read-only card: useful now / quiet for a reason / needs ripening / wasted motion.

Operator/audit inputs:
  Pass route-readiness, activation, recall, sleep, query-pattern, or cognitive-load JSON
  only when inspecting the Observatory pipeline. Full audit remains behind --json.""",
    )
    parser.add_argument("--fixture", action="store_true", help="Use deterministic fixture rows.")
    parser.add_argument("--route-candidates", help="JSON file/list with route candidates.")
    parser.add_argument("--route-readiness", help="JSON route-readiness report to embed.")
    parser.add_argument("--active-lock-roi", help="JSON active-recall lock ROI summary.")
    parser.add_argument("--activation-surfaces", help="JSON file/list with activation surfaces.")
    parser.add_argument("--recall-diagnostic", help="JSON recall diagnostic report to embed.")
    parser.add_argument("--sleep-cycle", help="JSON sleep-cycle report to summarize.")
    parser.add_argument("--query-pattern-routes", help="JSON/JSONL query-pattern routes sidecar.")
    parser.add_argument("--cognitive-load-calibration", help="JSON cognitive-load calibration report.")
    parser.add_argument("--min-roi-score", type=float, default=1.0)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--summary-json",
        action="store_true",
        help="Emit a compact foreground summary instead of the full audit JSON.",
    )
    parser.add_argument("--html", action="store_true", dest="html_output")
    parser.add_argument("--output", type=Path, help="Write the selected output to a file.")
    args = parser.parse_args(argv)
    if sum(bool(item) for item in (args.json_output, args.summary_json, args.html_output)) > 1:
        parser.error("--json, --summary-json, and --html are mutually exclusive")

    if args.fixture:
        report = fixture_cognitive_observatory_readout()
    else:
        report = cognitive_observatory_readout(
            route_candidates=_as_list(_load_json(args.route_candidates), "candidates"),
            route_readiness=_as_mapping(_load_json(args.route_readiness)),
            active_lock_roi=_as_mapping(_load_json(args.active_lock_roi)),
            activation_surfaces=_as_list(_load_json(args.activation_surfaces), "surfaces"),
            recall_diagnostic=_as_mapping(_load_json(args.recall_diagnostic)),
            sleep_cycle_payload=_as_mapping(_load_json(args.sleep_cycle)),
            query_pattern_routes=(
                _as_list(_load_json_or_jsonl(args.query_pattern_routes), "routes")
                if args.query_pattern_routes
                else None
            ),
            cognitive_load_calibration=_as_mapping(
                _load_json(args.cognitive_load_calibration)
            ),
            min_roi_score=args.min_roi_score,
        )
    if args.summary_json:
        output = json.dumps(summary_projection(report), ensure_ascii=False, indent=2) + "\n"
    elif args.json_output:
        output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    elif args.html_output:
        output = render_html(report)
    else:
        output = render_text(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        emit_public_text(output, end="")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
