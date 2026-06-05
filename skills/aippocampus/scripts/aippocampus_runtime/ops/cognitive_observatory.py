#!/usr/bin/env python3
"""Read-only Cognitive Observatory report over existing diagnostic surfaces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime.dream.sleep_cycle import public_sleep_cycle_summary
from aippocampus_runtime.ops.activation_authority_audit import (
    activation_surface_authority_audit,
)
from aippocampus_runtime.ops.route_readiness import (
    ROUTE_READINESS_KIND,
    fixture_route_readiness_report,
    route_readiness_report,
)
from aippocampus_runtime.privacy import redact_private_paths
from aippocampus_runtime.recall.why_diagnostics import recall_diagnostic_report

OBSERVATORY_KIND = "aippocampus_cognitive_observatory_readout"
OBSERVATORY_SCHEMA_VERSION = 1


def _load_json(path: str | Path | None) -> Any:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


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
        cue="SECRET_TOKEN=abc123 route readiness observatory fixture",
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
    )


def cognitive_observatory_readout(
    *,
    route_candidates: list[dict[str, Any]] | None = None,
    route_readiness: Mapping[str, Any] | None = None,
    active_lock_roi: Mapping[str, Any] | None = None,
    activation_surfaces: list[dict[str, Any]] | None = None,
    recall_diagnostic: Mapping[str, Any] | None = None,
    sleep_cycle_payload: Mapping[str, Any] | None = None,
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
    metrics = {
        "route_ready_count": (readiness.get("metrics") or {}).get("ready_count", 0),
        "route_suppressed_count": (readiness.get("metrics") or {}).get("suppressed_count", 0),
        "activation_surface_count": len(authority.get("surfaces") or []),
        "activation_conflict_count": (authority.get("metrics") or {}).get("conflict_count", 0),
        "recall_diagnostic_present": diagnostic is not None,
        "sleep_summary_present": sleep_summary is not None,
    }
    surfaces = ["route_readiness", "activation_authority"]
    if diagnostic:
        surfaces.append("recall_diagnostic")
    if sleep_summary:
        surfaces.append("sleep_cycle")
    return redact_private_paths(
        {
            "kind": OBSERVATORY_KIND,
            "schema_version": OBSERVATORY_SCHEMA_VERSION,
            "ok": True,
            "no_write": True,
            "issues": [574, 576],
            "surfaces": surfaces,
            "route_readiness": readiness,
            "activation_authority": authority,
            "recall_diagnostic": diagnostic,
            "sleep_cycle": sleep_summary,
            "metrics": metrics,
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
                "secret_values_serialized": False,
            },
            "can_claim": [
                "public_safe_route_readiness_diagnostic_exists",
                "read_only_observatory_readout_exists",
                "suppressed_prewarm_reason_codes_are_reported",
            ],
            "cannot_claim": [
                "complete_cognitive_observatory_ui_exists",
                "prewarm_route_is_source_backed_evidence",
                "sleep_cycle_anticipatory_planner_is_live",
                "observatory_rows_can_mutate_control_state",
                "diagnostic_roi_proves_memory_quality",
            ],
        }
    )


def render_text(report: Mapping[str, Any]) -> str:
    metrics = report.get("metrics") or {}
    contract = report.get("contract") or {}
    return "\n".join(
        [
            "Cognitive Observatory readout",
            f"  route ready: {metrics.get('route_ready_count', 0)}",
            f"  route suppressed: {metrics.get('route_suppressed_count', 0)}",
            f"  activation surfaces: {metrics.get('activation_surface_count', 0)}",
            f"  no write: {str(report.get('no_write')).lower()}",
            f"  control plane: {str(not contract.get('not_control_plane')).lower()}",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit a public-safe, no-write Cognitive Observatory readout."
    )
    parser.add_argument("--fixture", action="store_true", help="Use deterministic fixture rows.")
    parser.add_argument("--route-candidates", help="JSON file/list with route candidates.")
    parser.add_argument("--route-readiness", help="JSON route-readiness report to embed.")
    parser.add_argument("--active-lock-roi", help="JSON active-recall lock ROI summary.")
    parser.add_argument("--activation-surfaces", help="JSON file/list with activation surfaces.")
    parser.add_argument("--recall-diagnostic", help="JSON recall diagnostic report to embed.")
    parser.add_argument("--sleep-cycle", help="JSON sleep-cycle report to summarize.")
    parser.add_argument("--min-roi-score", type=float, default=1.0)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

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
            min_roi_score=args.min_roi_score,
        )
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report), end="")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
