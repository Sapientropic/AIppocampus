from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.recall.agent_continuity_cli_support import feedback_lane_resolution
from aippocampus_runtime.recall.feedback_events import load_feedback_calibration_report

NEGATIVE_FEEDBACK_SIGNALS = {
    "blocked",
    "expired",
    "ignored",
    "superseded",
    "wrong_route_drag",
}
POSITIVE_FEEDBACK_SIGNALS = {
    "prevented_failure",
    "source_reopen_success",
    "user_confirmed",
}


def feedback_report_for_prompt(
    *,
    registry_path: Path,
    workspace: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        lane = feedback_lane_resolution(cwd=workspace, registry_dir=registry_path.parent)
        report = load_feedback_calibration_report(lane.get("path"))
    except Exception as exc:
        return None, {
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc)[:160],
        }
    return report, {
        "status": "loaded" if report is not None else "unavailable",
        "path_source": lane.get("path_source"),
        "scope": lane.get("scope"),
        "path_label": lane.get("path_label"),
        "raw_path_emitted": False,
    }


def _feedback_deltas(report: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not isinstance(report, Mapping):
        return []
    raw_payload = report.get("calibration")
    payload: Mapping[str, Any] = raw_payload if isinstance(raw_payload, Mapping) else report
    return [row for row in payload.get("deltas") or [] if isinstance(row, Mapping)]


def _id_variants(value: Any) -> set[str]:
    text = str(value or "").strip()
    if not text:
        return set()
    variants = {text}
    variants.add(text.removeprefix("deepen:") if text.startswith("deepen:") else f"deepen:{text}")
    return variants


def _quiet_feedback_route_ids(report: Mapping[str, Any] | None) -> set[str]:
    quiet: set[str] = set()
    for row in _feedback_deltas(report):
        raw_counts = row.get("signal_counts")
        counts: Mapping[str, Any] = raw_counts if isinstance(raw_counts, Mapping) else {}
        negative = sum(int(counts.get(signal) or 0) for signal in NEGATIVE_FEEDBACK_SIGNALS)
        positive = sum(int(counts.get(signal) or 0) for signal in POSITIVE_FEEDBACK_SIGNALS)
        route_id = str(row.get("route_id") or "").strip()
        if route_id and negative > 0 and positive == 0:
            quiet.update(_id_variants(route_id))
    return quiet


def _card_feedback_ids(card: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key in ("card_id", "route_id", "query_pattern_route_id", "domain_id", "lock_id", "path_id", "deepen_route_id"):
        ids.update(_id_variants(card.get(key)))
    for ref in card.get("source_refs") or []:
        if isinstance(ref, Mapping):
            for key in ("source_id", "thread_key", "message_id", "turn_id"):
                ids.update(_id_variants(ref.get(key)))
    return ids


def _lane_projection(lane: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        key: lane.get(key)
        for key in ("path_source", "scope", "path_label", "raw_path_emitted")
        if isinstance(lane, Mapping) and key in lane
    }


def apply_feedback_filter(
    ambient: dict[str, Any],
    *,
    feedback_report: Mapping[str, Any] | None,
    lane: Mapping[str, Any] | None,
) -> dict[str, Any]:
    quiet_ids = _quiet_feedback_route_ids(feedback_report)
    cards = [card for card in ambient.get("cards") or [] if isinstance(card, dict)]
    if not quiet_ids:
        return {
            "status": "no_quiet_routes",
            "load_status": (feedback_report or {}).get("load_status"),
            "event_count_loaded": (feedback_report or {}).get("event_count_loaded"),
            "quiet_route_count": 0,
            "quieted_card_count": 0,
            "lane": _lane_projection(lane),
        }
    kept: list[dict[str, Any]] = []
    quieted = 0
    for card in cards:
        if _card_feedback_ids(card) & quiet_ids:
            quieted += 1
        else:
            kept.append(card)
    ambient["cards"] = kept
    return {
        "status": "applied",
        "load_status": (feedback_report or {}).get("load_status"),
        "event_count_loaded": (feedback_report or {}).get("event_count_loaded"),
        "quiet_route_count": len(quiet_ids),
        "quieted_card_count": quieted,
        "lane": _lane_projection(lane),
        "policy_boundary": {
            "feedback_is_navigation_metadata_only": True,
            "feedback_score_is_not_evidence": True,
            "clean_source_mutation_allowed": False,
            "source_reopen_required_for_claims": True,
        },
    }
