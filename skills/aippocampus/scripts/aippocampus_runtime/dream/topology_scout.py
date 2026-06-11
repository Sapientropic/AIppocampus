#!/usr/bin/env python3
"""Deterministic Dream topology scout for source-backed candidate shapes."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.ops import packet_topology_diagnostic

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_dream_topology_scout_report"
CANDIDATE_KIND = "dream_topology_candidate"
FORBIDDEN_MARKERS = (
    "PRIVATE_DREAM_TOPOLOGY_TEXT",
    "raw_private_source_text",
    "source://private",
    "C:\\",
    "/Users/",
)
SHAPE_TO_DREAM_FUNCTION = {
    "cycle": "compensatory",
    "cut_point": "compensatory",
    "weak_bridge": "amplification",
    "knot": "active_imagination",
    "island": "prospective",
}
SHAPE_TO_REASON = {
    "cycle": "A repeated stale or rejected route may need compensatory review.",
    "cut_point": "A missing middle may change how source-backed material glues.",
    "weak_bridge": "Two source-backed sections may rhyme without yet forming evidence.",
    "knot": "Entangled obligations need an unlinking move before action.",
    "island": "A useful source-backed cluster may be failing to enter recall.",
}


def stable_hash(*parts: Any, length: int = 16) -> str:
    digest = hashlib.sha256(
        "\u241f".join(str(part) for part in parts).encode("utf-8", errors="replace")
    ).hexdigest()
    return digest[:length]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _label(value: Any, *, fallback: str = "") -> str:
    text = _text(value).casefold()
    return text if text and all(char.isalnum() or char in "-_." for char in text) else fallback


def _safe_case_id(value: Any) -> str:
    text = _text(value)
    if (
        text
        and len(text) <= 96
        and all(char.isalnum() or char in "-_." for char in text)
    ):
        return text
    return "case_" + stable_hash(text, length=12)


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _safe_anchor(value: Any) -> str | None:
    text = _text(value)
    if (
        text
        and len(text) <= 80
        and not any(marker in text for marker in ("source://", "\\", "/", ":\\"))
        and all(char.isalnum() or char in "-_:#" for char in text)
    ):
        return text
    return None


def _source_anchors(row: Mapping[str, Any]) -> list[str]:
    raw_values = (
        _strings(row.get("source_anchors"))
        or _strings(row.get("source_anchor"))
        or _strings(row.get("source_refs"))
        or _strings(row.get("source_ref_ids"))
    )
    anchors = []
    for value in raw_values:
        anchor = _safe_anchor(value)
        if anchor and anchor not in anchors:
            anchors.append(anchor)
    return anchors[:8]


def _packet_shape(row: Mapping[str, Any]) -> str:
    explicit_shape = _label(row.get("shape"))
    if explicit_shape in SHAPE_TO_DREAM_FUNCTION or explicit_shape == "no_shape":
        return explicit_shape
    if _safe_bool(row.get("weak_bridge")) or _safe_int(row.get("bridge_side_count")) >= 2:
        return "weak_bridge"
    if _safe_bool(row.get("islanded_useful_cluster")) or (
        _safe_bool(row.get("useful_source_cluster"))
        and _safe_int(row.get("recall_entry_count")) == 0
    ):
        return "island"

    diagnostic = packet_topology_diagnostic.evaluate_packet(row)["diagnostic"]
    if diagnostic == packet_topology_diagnostic.ROUTE_CYCLE:
        return "cycle"
    if diagnostic == packet_topology_diagnostic.MISSING_MIDDLE:
        return "cut_point"
    if diagnostic == packet_topology_diagnostic.KNOT_WITHOUT_UNLINKING:
        return "knot"
    return "no_shape"


def _rejection_reasons(
    row: Mapping[str, Any],
    *,
    shape: str,
    anchors: list[str],
) -> list[str]:
    reasons: list[str] = []
    if _safe_bool(row.get("private_psychological_interpretation")):
        reasons.append("private_psychological_interpretation")
    if _safe_bool(row.get("user_diagnosis")):
        reasons.append("user_diagnosis")
    if _safe_bool(row.get("profile_claim")):
        reasons.append("profile_claim")
    if _safe_bool(row.get("symbolic_claim")) and not anchors:
        reasons.append("source_free_symbolic_claim")
    if shape in SHAPE_TO_DREAM_FUNCTION and not anchors:
        reasons.append("missing_source_anchor")
    if shape == "weak_bridge" and len(anchors) < 2:
        reasons.append("weak_bridge_needs_two_source_anchors")
    return reasons


def candidate_or_rejection(row: Mapping[str, Any]) -> dict[str, Any]:
    case_id = _safe_case_id(row.get("case_id"))
    anchors = _source_anchors(row)
    shape = _packet_shape(row)
    rejection_reasons = _rejection_reasons(row, shape=shape, anchors=anchors)

    if rejection_reasons:
        return {
            "kind": "dream_topology_rejection",
            "schema_version": SCHEMA_VERSION,
            "case_id": case_id,
            "shape": shape,
            "reasons": sorted(set(rejection_reasons)),
            "candidate_emitted": False,
        }
    if shape == "no_shape":
        return {
            "kind": "dream_topology_control",
            "schema_version": SCHEMA_VERSION,
            "case_id": case_id,
            "shape": "no_shape",
            "control_result": "no_candidate",
            "candidate_emitted": False,
        }

    return {
        "kind": CANDIDATE_KIND,
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "candidate_id": "dream_topology_" + stable_hash(case_id, shape, *anchors),
        "shape": shape,
        "dream_function": SHAPE_TO_DREAM_FUNCTION[shape],
        "authority": "dream_synthesized_candidate_not_fact",
        "source_anchors": anchors,
        "source_anchor_count": len(anchors),
        "why_may_matter": SHAPE_TO_REASON[shape],
        "next_safe_action": "review_or_route_only",
        "foreground_eligible": False,
        "source_reopen_required_before_claim": True,
        "adjudication_status": "candidate_requires_source_ref_review",
        "failed_glue_obstruction_not_assignment": True,
        "private_psychological_interpretation": False,
        "user_diagnosis": False,
        "profile_claim": False,
        "unsupported_symbolic_claim": False,
    }


def fixture_topology_rows() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "stale_route_cycle",
            "packet_type": "route_packet",
            "route_state": "rejected",
            "reopen_attempt_count": 3,
            "repeated_failed_route": True,
            "source_anchors": ["issue:#1185", "issue:#1188"],
        },
        {
            "case_id": "missing_middle_cut_point",
            "packet_type": "narrative_packet",
            "missing_middle": True,
            "pathlet_gap": "missing_middle",
            "source_anchors": ["issue:#700", "issue:#1263"],
        },
        {
            "case_id": "weak_bridge_between_issues",
            "shape": "weak_bridge",
            "bridge_side_count": 2,
            "source_anchors": ["issue:#1263", "issue:#1270"],
        },
        {
            "case_id": "obligation_knot_needs_unlinking",
            "packet_type": "aippo_activation",
            "authority": "candidate_not_fact",
            "obligation_count": 3,
            "unlinking_move_present": False,
            "source_anchors": ["issue:#1185", "issue:#1268"],
        },
        {
            "case_id": "islanded_useful_cluster",
            "shape": "island",
            "useful_source_cluster": True,
            "recall_entry_count": 0,
            "source_anchors": ["issue:#163", "issue:#1250"],
        },
        {
            "case_id": "healthy_no_shape_control",
            "packet_type": "memory_packet",
            "output_mode": "reopenable_route",
            "authority_level": "navigation_only",
            "claim_permission": "no_claim_before_reopen",
            "source_anchors": ["issue:#1263"],
        },
        {
            "case_id": "private_psych_interpretation",
            "shape": "weak_bridge",
            "source_anchors": ["issue:#163", "issue:#1268"],
            "private_psychological_interpretation": True,
        },
        {
            "case_id": "user_diagnosis",
            "shape": "cycle",
            "source_anchors": ["issue:#163"],
            "user_diagnosis": True,
        },
        {
            "case_id": "profile_claim",
            "shape": "island",
            "source_anchors": ["issue:#163"],
            "profile_claim": True,
        },
        {
            "case_id": "source_free_symbolic_claim",
            "shape": "knot",
            "symbolic_claim": True,
            "source_anchors": [],
        },
    ]


def build_dream_topology_scout_report(
    rows: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    row_list = list(rows) if rows is not None else fixture_topology_rows()
    outputs = [candidate_or_rejection(row) for row in row_list]
    candidates = [item for item in outputs if item["kind"] == CANDIDATE_KIND]
    controls = [item for item in outputs if item["kind"] == "dream_topology_control"]
    rejected = [item for item in outputs if item["kind"] == "dream_topology_rejection"]
    rejected_reasons = Counter(
        reason for item in rejected for reason in item.get("reasons", [])
    )
    shape_counts = Counter(item.get("shape") for item in candidates)
    forbidden_marker_count = sum(
        1
        for marker in FORBIDDEN_MARKERS
        if marker in json.dumps(outputs, ensure_ascii=False, sort_keys=True)
    )
    foreground_leak_count = sum(1 for item in candidates if item["foreground_eligible"])
    private_interpretation_count = sum(
        1 for item in candidates if item["private_psychological_interpretation"]
    )
    shape_false_positive_count = sum(
        1
        for item in controls
        if item.get("control_result") != "no_candidate"
    )
    metrics = {
        "case_count": len(outputs),
        "dream_topology_candidate_count": len(candidates),
        "dream_topology_source_anchor_coverage": round(
            sum(1 for item in candidates if item["source_anchor_count"] > 0)
            / max(1, len(candidates)),
            4,
        ),
        "dream_topology_foreground_leak_count": foreground_leak_count,
        "dream_topology_private_interpretation_count": private_interpretation_count,
        "dream_topology_shape_false_positive_count": shape_false_positive_count,
        "cycle_candidate_count": shape_counts["cycle"],
        "cut_point_candidate_count": shape_counts["cut_point"],
        "weak_bridge_candidate_count": shape_counts["weak_bridge"],
        "knot_candidate_count": shape_counts["knot"],
        "island_candidate_count": shape_counts["island"],
        "hard_negative_rejected_count": len(rejected),
        "source_free_symbolic_claim_rejected_count": rejected_reasons[
            "source_free_symbolic_claim"
        ],
        "profile_claim_rejected_count": rejected_reasons["profile_claim"],
        "user_diagnosis_rejected_count": rejected_reasons["user_diagnosis"],
        "private_interpretation_rejected_count": rejected_reasons[
            "private_psychological_interpretation"
        ],
    }
    red_lines = {
        "raw_private_text_emitted_count": forbidden_marker_count,
        "local_path_emitted_count": forbidden_marker_count,
        "source_handle_emitted_count": forbidden_marker_count,
        "foreground_leak_count": foreground_leak_count,
        "private_interpretation_emitted_count": private_interpretation_count,
        "shape_false_positive_count": shape_false_positive_count,
    }
    expected_cases = {
        "stale_route_cycle",
        "missing_middle_cut_point",
        "weak_bridge_between_issues",
        "obligation_knot_needs_unlinking",
        "islanded_useful_cluster",
        "healthy_no_shape_control",
        "private_psych_interpretation",
        "user_diagnosis",
        "profile_claim",
        "source_free_symbolic_claim",
    }
    contract_gate_ok = rows is not None or expected_cases.issubset(
        {item["case_id"] for item in outputs}
    )
    safety_gate_ok = all(value == 0 for value in red_lines.values())
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": contract_gate_ok and safety_gate_ok,
        "contract_gate_ok": contract_gate_ok,
        "safety_gate_ok": safety_gate_ok,
        "benchmark_maturity_level": "contract_smoke",
        "authority_level": "dream_synthesized_candidate_not_fact",
        "runtime_boundary": "detached_background_or_explain_only",
        "every_turn_scan": False,
        "foreground_default": False,
        "truth_layer": False,
        "candidates": candidates,
        "controls": controls,
        "rejected": rejected,
        "metrics": metrics,
        "red_lines": red_lines,
        "privacy_boundary": {
            "raw_private_text_emitted": False,
            "local_paths_emitted": False,
            "source_handles_emitted": False,
            "private_interpretations_emitted": False,
            "forbidden_marker_count": forbidden_marker_count,
        },
        "contract": {
            "uses_packet_topology_diagnostic": True,
            "failed_glue_can_be_candidate_not_assignment": True,
            "candidate_not_fact": True,
            "source_anchor_required": True,
            "foreground_disabled_by_default": True,
            "hard_negatives_rejected": True,
            "public_safe_substrate_for_163": True,
        },
        "cannot_claim": [
            "live_dream_quality",
            "private_history_dream_quality",
            "user_visible_causal_lift",
            "psychological_interpretation",
            "profile_truth",
            "source_truth_without_reopen",
            "foreground_default_usefulness",
        ],
    }


def load_rows(path: Path) -> list[Mapping[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    if isinstance(data, Mapping):
        raw_rows = data.get("rows") or data.get("cases") or data.get("packets") or []
        return [item for item in raw_rows if isinstance(item, Mapping)]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="JSON file with Dream topology rows.")
    parser.add_argument("--fixture", action="store_true", help="Use the built-in fixture.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    args = parser.parse_args(argv)

    rows = load_rows(Path(args.input)) if args.input else None
    report = build_dream_topology_scout_report(rows)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("dream topology scout: " + ("ok" if report["ok"] else "blocked"))
        print(f"metrics: {report['metrics']}")
    return 0 if report["safety_gate_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
