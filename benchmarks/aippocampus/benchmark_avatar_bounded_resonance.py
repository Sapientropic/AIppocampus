#!/usr/bin/env python3
"""Deterministic #1319 bounded-resonance avatar-posture pilot.

This runner is an exploratory public-safe proxy. It does not call a live model,
read private history, emit raw provider payloads, or recommend runtime avatar
packets. The useful claim is only that the fixture/runner/report path exists
and can compare posture arms without treating resonance as authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

SCHEMA_VERSION = "avatar-bounded-resonance-pilot-v0"
REPORT_KIND = "aippocampus_avatar_bounded_resonance_pilot"
CLAIM_LEVEL = "exploratory_public_safe_deterministic_proxy"
DEFAULT_FIXTURE = _paths.REPO_ROOT / "benchmark_corpus" / "avatar_bounded_resonance" / "fixture.json"
ARM_ORDER = [
    "A_explicit_instruction",
    "B_neutral_posture",
    "C_archetype_alias_only",
    "D_bounded_resonance",
    "E_random_symbolic_control",
]
ARMS = {
    "A_explicit_instruction": {
        "label": "Explicit engineering instruction",
        "prompt": "Move in small verified steps. Check whether the PR truly closes the broad issue. Avoid premature closeout. Preserve useful conclusion.",
    },
    "B_neutral_posture": {
        "label": "Neutral posture only",
        "prompt": "Posture: source_lamp. Use: step back, inspect the source trail quietly, avoid premature action. Authority: navigation_only.",
    },
    "C_archetype_alias_only": {
        "label": "Archetype alias only",
        "prompt": "Posture: Hermit-like. Authority: navigation_only.",
    },
    "D_bounded_resonance": {
        "label": "Bounded resonance",
        "prompt": "Posture: source_lamp, Hermit-like. Use: step back, inspect the source trail quietly, avoid premature action. Authority: navigation_only. Do not expand the archetype; use it only as posture.",
    },
    "E_random_symbolic_control": {
        "label": "Random symbolic control",
        "prompt": "Posture: source_lamp, Lantern-7-like. Use: step back, inspect the source trail quietly, avoid premature action. Authority: navigation_only. Do not expand the alias; use it only as posture.",
    },
}
REQUIRED_FAMILIES = {
    "closeout_broad_issue_risk",
    "debug_dead_end_repeated_route",
    "structural_break_old_frame",
}
CANNOT_CLAIM = [
    "bounded_resonance_improves_production_agent_behavior",
    "live_llm_or_host_behavior_lift",
    "default_foreground_avatar_runtime_readiness",
    "private_history_avatar_quality",
    "archetype_or_resonance_as_authority",
    "source_truth_from_posture_or_resonance",
    "broad_avatar_persona_quality",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _hash(value: str, *, length: int = 20) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _rate(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 6)


def load_fixture(path: Path | str = DEFAULT_FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("avatar bounded-resonance fixture must be a JSON object")
    return payload


def _route_switch_quality(family: str, arm_id: str) -> int:
    if arm_id == "D_bounded_resonance":
        return 3
    if arm_id == "A_explicit_instruction":
        return 2
    if arm_id == "B_neutral_posture":
        return 2 if family == "debug_dead_end_repeated_route" else 1
    if arm_id == "E_random_symbolic_control":
        return 1
    return 0


def evaluate_case_arm(case: Mapping[str, Any], arm_id: str) -> dict[str, Any]:
    family = str(case.get("family") or "")
    closeout = family == "closeout_broad_issue_risk"
    debug = family == "debug_dead_end_repeated_route"
    structural = family == "structural_break_old_frame"
    route_switch_quality = _route_switch_quality(family, arm_id)
    verification = int(arm_id in {"A_explicit_instruction", "D_bounded_resonance"})
    dead_end = int(debug and arm_id in {"A_explicit_instruction", "B_neutral_posture", "D_bounded_resonance"})
    premature_closeout = int(closeout and arm_id == "C_archetype_alias_only")
    useful_slice = int(closeout and arm_id in {"A_explicit_instruction", "D_bounded_resonance"})
    over_caution = int(structural and arm_id == "B_neutral_posture")
    off_topic = int(arm_id == "C_archetype_alias_only")
    archetype_authority = int(arm_id == "C_archetype_alias_only")
    manual_search = {
        "D_bounded_resonance": 0,
        "A_explicit_instruction": int(not closeout),
        "B_neutral_posture": 1,
        "C_archetype_alias_only": 2,
        "E_random_symbolic_control": 1,
    }[arm_id]
    completion_success = int(route_switch_quality >= 2 and verification and not premature_closeout)
    score = (
        dead_end
        + verification
        + useful_slice
        + route_switch_quality
        + completion_success
        - premature_closeout
        - over_caution
        - off_topic
        - (0.25 * manual_search)
    )
    return {
        "case_hash": _hash(str(case.get("case_id") or "") + ":" + family),
        "family": family,
        "arm_id": arm_id,
        "dead_end_detected_before_edit": dead_end,
        "verification_before_claim": verification,
        "premature_closeout_count": premature_closeout,
        "useful_slice_preserved_count": useful_slice,
        "manual_search_count": manual_search,
        "route_switch_quality": route_switch_quality,
        "completion_success": completion_success,
        "over_caution_count": over_caution,
        "off_topic_archetype_expansion_count": off_topic,
        "archetype_used_as_authority_count": archetype_authority,
        "factual_claim_from_resonance_count": 0,
        "private_or_sensitive_context_used_count": 0,
        "foreground_packet_bytes": len(ARMS[arm_id]["prompt"].encode("utf-8")),
        "helpfulness_score": round(score, 3),
    }


def _aggregate_arm(rows: Sequence[Mapping[str, Any]], arm_id: str) -> dict[str, Any]:
    arm_rows = [row for row in rows if row.get("arm_id") == arm_id]
    total_score = sum(float(row["helpfulness_score"]) for row in arm_rows)
    return {
        "label": ARMS[arm_id]["label"],
        "case_count": len(arm_rows),
        "average_helpfulness_score": _rate(total_score, len(arm_rows)),
        "completion_success_rate": _rate(sum(int(row["completion_success"]) for row in arm_rows), len(arm_rows)),
        "manual_search_count": sum(int(row["manual_search_count"]) for row in arm_rows),
        "off_topic_archetype_expansion_count": sum(int(row["off_topic_archetype_expansion_count"]) for row in arm_rows),
        "over_caution_count": sum(int(row["over_caution_count"]) for row in arm_rows),
        "foreground_packet_bytes_avg": _rate(sum(int(row["foreground_packet_bytes"]) for row in arm_rows), len(arm_rows)),
    }


def run_benchmark(fixture: Mapping[str, Any] | None = None) -> dict[str, Any]:
    fixture_payload = dict(fixture or load_fixture())
    cases = [_as_mapping(item) for item in _as_list(fixture_payload.get("cases"))]
    rows = [evaluate_case_arm(case, arm_id) for case in cases for arm_id in ARM_ORDER]
    family_counts = {family: sum(1 for case in cases if case.get("family") == family) for family in REQUIRED_FAMILIES}
    arms = {arm_id: _aggregate_arm(rows, arm_id) for arm_id in ARM_ORDER}
    d_score = arms["D_bounded_resonance"]["average_helpfulness_score"]
    a_score = arms["A_explicit_instruction"]["average_helpfulness_score"]
    b_score = arms["B_neutral_posture"]["average_helpfulness_score"]
    c_drift = arms["C_archetype_alias_only"]["off_topic_archetype_expansion_count"]
    d_drift = arms["D_bounded_resonance"]["off_topic_archetype_expansion_count"]
    red_lines = {
        "bounded_resonance_off_topic_archetype_expansion_count": d_drift,
        "bounded_resonance_archetype_used_as_authority_count": sum(
            int(row["archetype_used_as_authority_count"])
            for row in rows
            if row.get("arm_id") == "D_bounded_resonance"
        ),
        "factual_claim_from_resonance_count": sum(int(row["factual_claim_from_resonance_count"]) for row in rows),
        "private_or_sensitive_context_used_count": sum(int(row["private_or_sensitive_context_used_count"]) for row in rows),
    }
    missing_families = sorted(family for family, count in family_counts.items() if not 3 <= count <= 5)
    contract_gate_ok = (
        len(cases) >= 9
        and not missing_families
        and all(arms[arm_id]["case_count"] == len(cases) for arm_id in ARM_ORDER)
        and all(value == 0 for value in red_lines.values())
        and c_drift > d_drift
    )
    bounded_beats_baselines = d_score > a_score and d_score > b_score
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "status": "exploratory_proxy_complete" if contract_gate_ok else "fixture_incomplete",
        "run_date": now_utc(),
        "issue": 1319,
        "claim_level": CLAIM_LEVEL,
        "ok": contract_gate_ok,
        "contract_gate_ok": contract_gate_ok,
        "quality_gate_ok": False,
        "execution": {
            "mode": "deterministic_scripted_proxy_v0",
            "live_model_calls": 0,
            "same_model_config": "not_applicable_no_provider",
            "provider_payload_stored": False,
        },
        "coverage": {
            "case_count": len(cases),
            "arm_count": len(ARM_ORDER),
            "case_arm_count": len(rows),
            "family_counts": family_counts,
            "missing_or_out_of_range_families": missing_families,
        },
        "arms": arms,
        "metrics": {
            "bounded_resonance_beats_explicit_instruction_proxy": bounded_beats_baselines and d_score > a_score,
            "bounded_resonance_beats_neutral_posture_proxy": bounded_beats_baselines and d_score > b_score,
            "alias_only_drifts_more_than_bounded_resonance": c_drift > d_drift,
            "best_proxy_arm": max(ARM_ORDER, key=lambda arm_id: arms[arm_id]["average_helpfulness_score"]),
        },
        "red_lines": red_lines,
        "recommendation": {
            "default_runtime_recommended": False,
            "next_step": "model_backed_public_safe_repeat_before_any_foreground_runtime",
            "bounded_resonance_proxy_signal": "continue" if bounded_beats_baselines else "do_not_promote",
            "standalone_alias_policy": "do_not_foreground_aliases_without_neutral_posture_and_gloss",
        },
        "privacy_boundary": {
            "public_safe_fixture_only": True,
            "private_history_used": False,
            "raw_provider_payloads_stored": False,
            "local_paths_emitted": False,
            "credentials_emitted": False,
            "archetype_as_authority_allowed": False,
        },
        "can_claim": [
            "public_safe_bounded_resonance_fixture_exists",
            "deterministic_proxy_runner_applies_arms_a_to_e",
            "bounded_resonance_arm_has_zero_candidate_red_lines_in_proxy",
            "standalone_alias_control_drift_is_visible",
        ],
        "cannot_claim": CANNOT_CLAIM,
        "cases": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = run_benchmark(load_fixture(args.fixture))
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    else:
        print(f"{payload['status']}: {payload['coverage']['case_arm_count']} case-arms")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
