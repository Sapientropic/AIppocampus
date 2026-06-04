#!/usr/bin/env python3
"""Opt-in deterministic evidence for repo familiarity foreground packets."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.navigation import repo_familiarity

EXPERIMENT_KIND = "aippocampus_repo_familiarity_foreground_experiment"
EXPERIMENT_SCHEMA_VERSION = 1
ARM_NO_CARD = "no_card"
ARM_SELECTED_CARD = "selected_card"
ARM_STALE_OR_IRRELEVANT = "stale_or_irrelevant_card"
ARMS = (ARM_NO_CARD, ARM_SELECTED_CARD, ARM_STALE_OR_IRRELEVANT)
DEFAULT_EXPERIMENT_MAX_CARDS = 1
DEFAULT_EXPERIMENT_MAX_PACKET_BYTES = repo_familiarity.DEFAULT_MAX_PACKET_BYTES


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _ratio(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


def _avg(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def _token_proxy(text: Any) -> int:
    return len(str(text or "").split())


def _step_input_proxy(step: Mapping[str, Any]) -> int:
    explicit = step.get("input_token_proxy")
    if isinstance(explicit, int):
        return max(0, explicit)
    return _token_proxy(step.get("query") or step.get("source_to_reopen"))


def _packet_input_proxy(packet: Mapping[str, Any]) -> int:
    # Byte-to-word proxy only. Real model token or billing deltas require live
    # arm instrumentation and must not be inferred from this deterministic run.
    packet_bytes = int(packet.get("packet_bytes") or 0)
    return max(0, round(packet_bytes / 6))


def _arm_base(arm: str) -> dict[str, Any]:
    return {
        "arm": arm,
        "route_quality_proxy": 0.0,
        "tool_call_count": 0,
        "input_token_proxy": 0,
        "elapsed_ms_proxy": 0,
        "stale_route_drag_count": 0,
        "fast_reject_count": 0,
        "selected_card_count": 0,
        "selected_landmarks": [],
        "source_reopen_count": 0,
        "deterministic_proxy_only": True,
    }


def _run_no_card_arm(case: Mapping[str, Any]) -> dict[str, Any]:
    steps = [step for step in _as_list(case.get("no_card_source_plan")) if isinstance(step, Mapping)]
    useful_count = sum(1 for step in steps if step.get("useful"))
    row = _arm_base(ARM_NO_CARD)
    row.update(
        {
            "route_quality_proxy": _ratio(useful_count, len(steps)),
            "tool_call_count": len(steps),
            "input_token_proxy": sum(_step_input_proxy(step) for step in steps),
            "elapsed_ms_proxy": sum(int(step.get("elapsed_ms_proxy") or 0) for step in steps),
            "stale_route_drag_count": sum(
                1 for step in steps if step.get("stale_or_irrelevant")
            ),
            "source_reopen_count": len(steps),
        }
    )
    return row


def _cards_for_case(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    manifest = {
        "repo_commit": str(case.get("repo_commit") or ""),
        "source_rows": _as_list(case.get("source_rows")),
    }
    return repo_familiarity.build_repo_familiarity_cards(manifest)


def _selected_card_quality(
    selected_cards: Sequence[Mapping[str, Any]],
    *,
    expected_landmark: str,
    expected_first_source: str,
) -> float:
    if not selected_cards:
        return 0.0
    useful_count = sum(
        1
        for card in selected_cards
        if str(card.get("landmark") or "") == expected_landmark
        and str(card.get("first_source_to_reopen") or "") == expected_first_source
    )
    return _ratio(useful_count, len(selected_cards))


def _run_packet_arm(
    case: Mapping[str, Any],
    *,
    arm: str,
    current_fingerprints: Mapping[str, str],
    current_commit: str,
    max_cards: int,
    max_packet_bytes: int,
) -> dict[str, Any]:
    packet = repo_familiarity.select_repo_familiarity_packet(
        _cards_for_case(case),
        task=str(case.get("task") or ""),
        current_fingerprints=current_fingerprints,
        current_commit=current_commit,
        max_cards=max_cards,
        max_packet_bytes=max_packet_bytes,
    )
    selected_cards = [
        card for card in _as_list(packet.get("selected_cards")) if isinstance(card, Mapping)
    ]
    fast_reject_count = int(
        _as_dict(packet.get("cost_delta_report")).get("fast_reject_count") or 0
    )
    quality_proxy = _selected_card_quality(
        selected_cards,
        expected_landmark=str(case.get("expected_landmark") or ""),
        expected_first_source=str(case.get("expected_first_source") or ""),
    )
    row = _arm_base(arm)
    row.update(
        {
            "route_quality_proxy": quality_proxy,
            "tool_call_count": len(selected_cards),
            "input_token_proxy": _packet_input_proxy(packet),
            "elapsed_ms_proxy": len(selected_cards) * 10,
            "stale_route_drag_count": (
                len(selected_cards) if selected_cards and quality_proxy <= 0 else 0
            ),
            "fast_reject_count": fast_reject_count,
            "selected_card_count": len(selected_cards),
            "selected_landmarks": [str(card.get("landmark") or "") for card in selected_cards],
            "source_reopen_count": len(
                [card for card in selected_cards if card.get("first_source_to_reopen")]
            ),
        }
    )
    return row


def _run_selected_card_arm(
    case: Mapping[str, Any],
    *,
    max_cards: int,
    max_packet_bytes: int,
) -> dict[str, Any]:
    return _run_packet_arm(
        case,
        arm=ARM_SELECTED_CARD,
        current_fingerprints={
            str(key): str(value)
            for key, value in _as_dict(case.get("current_fingerprints")).items()
        },
        current_commit=str(case.get("repo_commit") or ""),
        max_cards=max_cards,
        max_packet_bytes=max_packet_bytes,
    )


def _run_stale_or_irrelevant_arm(
    case: Mapping[str, Any],
    *,
    max_cards: int,
    max_packet_bytes: int,
) -> dict[str, Any]:
    return _run_packet_arm(
        case,
        arm=ARM_STALE_OR_IRRELEVANT,
        current_fingerprints={
            str(key): str(value)
            for key, value in _as_dict(case.get("stale_or_irrelevant_fingerprints")).items()
        },
        current_commit=str(case.get("repo_commit") or ""),
        max_cards=max_cards,
        max_packet_bytes=max_packet_bytes,
    )


def _aggregate(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    arms: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        rows = [_as_dict(_as_dict(case.get("arms")).get(arm)) for case in cases]
        arms[arm] = {
            "case_count": len(rows),
            "avg_route_quality_proxy": _avg(
                [float(row.get("route_quality_proxy") or 0) for row in rows]
            ),
            "avg_tool_call_count": _avg(
                [float(row.get("tool_call_count") or 0) for row in rows]
            ),
            "input_token_proxy_total": sum(
                int(row.get("input_token_proxy") or 0) for row in rows
            ),
            "elapsed_ms_proxy_total": sum(
                int(row.get("elapsed_ms_proxy") or 0) for row in rows
            ),
            "stale_route_drag_count": sum(
                int(row.get("stale_route_drag_count") or 0) for row in rows
            ),
            "fast_reject_count": sum(int(row.get("fast_reject_count") or 0) for row in rows),
            "avg_selected_card_count": _avg(
                [float(row.get("selected_card_count") or 0) for row in rows]
            ),
        }
    return {"arms": arms}


def _issue_readouts() -> dict[str, Any]:
    return {
        "github_250": {
            "no_card_vs_selected_card": "deterministic_proxy_only",
            "live_cost_reduction": "not_measured",
            "live_answer_quality_lift": "not_measured",
            "default_foreground_integration": "not_implemented",
            "multi_agent_persistence": "not_implemented",
            "closeout_eligible": False,
        }
    }


def build_repo_familiarity_foreground_experiment(
    cases: Sequence[Mapping[str, Any]],
    *,
    max_cards: int = DEFAULT_EXPERIMENT_MAX_CARDS,
    max_packet_bytes: int = DEFAULT_EXPERIMENT_MAX_PACKET_BYTES,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        arms = {
            ARM_NO_CARD: _run_no_card_arm(case),
            ARM_SELECTED_CARD: _run_selected_card_arm(
                case,
                max_cards=max_cards,
                max_packet_bytes=max_packet_bytes,
            ),
            ARM_STALE_OR_IRRELEVANT: _run_stale_or_irrelevant_arm(
                case,
                max_cards=max_cards,
                max_packet_bytes=max_packet_bytes,
            ),
        }
        rows.append(
            {
                "case_id": str(case.get("case_id") or "case"),
                "case_family": str(case.get("case_family") or "unspecified"),
                "expected_behavior": str(case.get("expected_behavior") or ""),
                "arms": arms,
            }
        )
    aggregate = _aggregate(rows)
    return {
        "kind": EXPERIMENT_KIND,
        "schema_version": EXPERIMENT_SCHEMA_VERSION,
        "ok": True,
        "cases": rows,
        "cases_by_id": {str(row["case_id"]): row for row in rows},
        "aggregate": aggregate,
        "issue_readouts": _issue_readouts(),
        "metric_notes": {
            "route_quality_proxy": (
                "Fixture-scored route usefulness after source reopen; not live answer quality."
            ),
            "input_token_proxy": (
                "Word/byte proxy over public fixture cues and packets; not model billing tokens."
            ),
            "elapsed_ms_proxy": "Deterministic elapsed proxy; not observed wall-clock latency.",
            "stale_route_drag_count": (
                "Wrong/stale routes that survived selection and would create extra verification work."
            ),
            "fast_reject_count": "Stale/irrelevant cards rejected before source use.",
        },
        "experiment_boundary": {
            "opt_in_only": True,
            "deterministic_proxy_only": True,
            "cannot_claim_live_cost_reduction": True,
            "cannot_claim_answer_quality_lift": True,
            "cannot_claim_default_foreground_lift": True,
            "no_multi_agent_persistence": True,
            "source_reopen_required_for_strong_claims": True,
            "navigation_not_truth": True,
            "no_external_model_calls": True,
            "no_write": True,
        },
        "privacy": {
            "raw_cues_serialized": False,
            "raw_source_snippets_serialized": False,
            "local_paths_serialized": False,
            "private_registry_serialized": False,
        },
    }


def render_text(report: Mapping[str, Any]) -> str:
    aggregate = _as_dict(report.get("aggregate"))
    arms = _as_dict(aggregate.get("arms"))
    lines = [
        "AIppocampus repo familiarity foreground experiment",
        f"- OK: {str(bool(report.get('ok'))).lower()}",
        f"- Cases: {len(_as_list(report.get('cases')))}",
    ]
    for arm in ARMS:
        row = _as_dict(arms.get(arm))
        lines.append(
            "- "
            + arm
            + ": route quality proxy "
            + str(row.get("avg_route_quality_proxy", 0))
            + "; avg tool calls "
            + str(row.get("avg_tool_call_count", 0))
            + "; token proxy total "
            + str(row.get("input_token_proxy_total", 0))
            + "; fast rejects "
            + str(row.get("fast_reject_count", 0))
            + "; stale-route drag "
            + str(row.get("stale_route_drag_count", 0))
        )
    lines.append("- Boundary: opt-in deterministic proxy only; source reopen remains required.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="repo_familiarity_foreground_experiment",
        description="Core builder for opt-in repo familiarity foreground experiment reports.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.parse_args(argv)
    parser.error(
        "repo_familiarity_foreground_experiment is the core builder; run "
        "tools/aippocampus/smoke/smoke_repo_familiarity_foreground_experiment.py "
        "for the public fixture smoke."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
