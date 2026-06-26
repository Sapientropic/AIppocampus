#!/usr/bin/env python3
"""Public-safe text and foreground projection for Episode/Arc readouts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.core import dict_or_empty


def render_text(report: dict[str, Any]) -> str:
    raw_metrics = report.get("metrics")
    metrics: Mapping[str, Any] = raw_metrics if isinstance(raw_metrics, Mapping) else {}
    raw_input_surface = report.get("input_surface")
    input_surface: Mapping[str, Any] = (
        raw_input_surface if isinstance(raw_input_surface, Mapping) else {}
    )
    raw_privacy = report.get("privacy_boundary")
    privacy: Mapping[str, Any] = raw_privacy if isinstance(raw_privacy, Mapping) else {}
    current_validity = dict_or_empty(report.get("current_validity_counts"))
    safe_use = dict_or_empty(report.get("safe_use_counts"))
    lines = [
        "AIppocampus episode-arcs",
        f"status: {'ok' if report.get('ok') else 'attention_needed'}",
        f"threads scanned: {input_surface.get('thread_count_scanned', 0)}",
        f"message rows scanned: {input_surface.get('message_rows_scanned', 0)}",
        f"episode arcs: {metrics.get('episode_arc_count', 0)}",
        "action card:",
        f"  complete: {metrics.get('complete_arc_count', 0)}",
        f"  gappy: {metrics.get('gappy_arc_count', 0)}",
        f"  needs_reopen: {current_validity.get('needs_reopen', 0)}",
        "  safe use: "
        + ", ".join(f"{key}={value}" for key, value in sorted(safe_use.items()))
        if safe_use
        else "  safe use: none",
        "next: use arcs as sequence-route hints; ask/refresh sources before acting.",
        "machine summary: aippocampus episode-arcs --summary-json",
        "audit details: aippocampus episode-arcs --json --detail full",
        "boundary: source text, thread ids, local paths, and source refs stay out of default output",
    ]
    if privacy:
        lines.append(
            f"privacy: raw_text={str(bool(privacy.get('raw_source_text_emitted'))).lower()}"
        )
    return "\n".join(lines)


def summary_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    metrics = dict_or_empty(report.get("metrics"))
    input_surface = dict_or_empty(report.get("input_surface"))
    counts_deferred = bool(report.get("counts_deferred"))
    episode_arc_count = None if counts_deferred else int(metrics.get("episode_arc_count") or 0)
    complete_arc_count = None if counts_deferred else metrics.get("complete_arc_count", 0)
    gappy_arc_count = None if counts_deferred else metrics.get("gappy_arc_count", 0)
    current_validity_counts = dict(dict_or_empty(report.get("current_validity_counts")))
    safe_use_counts = dict(dict_or_empty(report.get("safe_use_counts")))
    summary_metrics = {
        "episode_arc_count": episode_arc_count,
        "complete_arc_count": complete_arc_count,
        "gappy_arc_count": gappy_arc_count,
        "needs_reopen_count": (
            None if counts_deferred else current_validity_counts.get("needs_reopen", 0)
        ),
        "thread_count_scanned": (
            None if counts_deferred else input_surface.get("thread_count_scanned", 0)
        ),
        "message_rows_scanned": (
            None if counts_deferred else input_surface.get("message_rows_scanned", 0)
        ),
        "counts_status": "deferred_to_detail" if counts_deferred else "measured",
    }
    owner_route = {
        "id": "current_owner_route",
        "kind": "current_owner_route",
        "command": "aippocampus episode-arcs --json --detail full --top 5",
        "mutation_risk": "read_only",
        "claim_boundary": "sequence_hint_not_source_truth",
        "why": "Use this owner route when there are actionable arc handles to inspect.",
    }
    route_action = {
        "id": "retrieve_actionable_arc_handles",
        "kind": "retrieve_actionable_arc_handles",
        "command": "aippocampus episode-arcs --json --detail full --top 5",
        "mutation_risk": "read_only",
        "claim_boundary": "sequence_hint_not_source_truth",
        "why": "Aggregate counts are only a signal; retrieve a small redacted handle set before acting on an arc.",
    }
    no_op_action = {
        "id": "no_episode_arcs_to_route",
        "kind": "no_episode_arcs_to_route",
        "no_op": True,
        "continue_without_command": True,
        "mutation_risk": "none",
        "claim_boundary": "sequence_hint_not_source_truth",
        "why": "No episode arcs are currently present in the scoped aggregate readout.",
    }
    no_op = (not counts_deferred) and episode_arc_count == 0
    action = no_op_action if no_op else route_action
    action_fields = canonical_foreground_action_fields(
        action,
        safe_next_actions=[] if no_op else [owner_route],
    )
    return {
        "kind": "aippocampus_episode_arcs_summary",
        "ok": bool(report.get("ok")),
        "status": report.get("status"),
        "route_value": "navigation_only_sequence_hints_need_source_reopen",
        "current_uncertainty": (
            "no_episode_arcs_found_in_scope"
            if no_op
            else "arc_counts_deferred_to_keep_foreground_fast"
            if counts_deferred
            else "aggregate_arc_counts_do_not_prove_current_source_validity"
        ),
        "what_to_do": "no_episode_arcs_to_route" if no_op else "retrieve_actionable_arc_handles",
        "no_op": no_op,
        "owner_route": owner_route,
        **action_fields,
        "summary_metrics": summary_metrics,
        "summary_source": (
            "bounded_registry_scan_no_private_history_aggregation"
            if counts_deferred
            else "bounded_aggregate_scan_without_handles"
            if report.get("compact_aggregate_scan")
            else "private_history_aggregate"
        ),
        "episode_arc_count": episode_arc_count,
        "complete_arc_count": complete_arc_count,
        "gappy_arc_count": gappy_arc_count,
        "current_validity_counts": current_validity_counts,
        "safe_use_counts": safe_use_counts,
        "next_action": "Use arcs as navigation-only sequence hints; retrieve handles before source reopen.",
        "full_audit_flag": "--json --detail full",
        "privacy_boundary": report.get("privacy_boundary"),
        "claim_boundary": {
            "can_use_for": ["sequence_hint_triage", "source_reopen_target_selection"],
            "must_reopen_for": ["current_validity", "source_backed_claims", "truth_layer_claims"],
            "detail_available_with": "aippocampus episode-arcs --json --detail full",
        },
        "boundary_detail_available": True,
    }
