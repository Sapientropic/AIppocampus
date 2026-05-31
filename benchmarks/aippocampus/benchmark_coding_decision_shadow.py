#!/usr/bin/env python3
"""Deterministic coding-agent decision-shadow benchmark tracks A-E.

This runner measures the coding continuity wedge with source-backed synthetic
fixtures. It is not a real-history lift claim and does not need a code index:
the goal is to catch regressions in source citation, rejected-route warnings,
compaction boundary preservation, historical-decision selection, and anti-nag
suppression.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import _paths

_paths.ensure_paths()

import benchmark_compaction_continuity as compaction_benchmark
import coding_decision_events as decisions
import coding_ticket_host_contract as host_contract

SCHEMA_VERSION = 1


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()


def message(
    *,
    message_id: str,
    text: str,
    line: int,
    thread_key: str = "thread:decision-shadow-public",
) -> dict[str, object]:
    return {
        "message_id": message_id,
        "turn_id": f"turn-{message_id}",
        "source_id": "decision-shadow-public-fixture",
        "clean_ordinal": line,
        "source_line": line,
        "role": "user",
        "text": text,
        "thread_key": thread_key,
    }


def sanitized_refs(refs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "source_ref_count": len(refs),
        "source_ref_hashes": [
            sha1_text(
                "|".join(
                    [
                        str(ref.get("thread_key") or ""),
                        str(ref.get("message_id") or ""),
                        str(ref.get("source_line") or ref.get("line") or ""),
                    ]
                )
            )[:16]
            for ref in refs
        ],
    }


def status_for(passed: bool) -> str:
    return "sufficient" if passed else "failed"


def track_payload(
    *,
    track: str,
    goal: str,
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    passed = all(bool(case.get("passed")) for case in cases)
    return {
        "schema_version": SCHEMA_VERSION,
        "track": track,
        "goal": goal,
        "ok": passed,
        "quality_gate_ok": passed,
        "status": status_for(passed),
        "case_count": len(cases),
        "passed_count": sum(1 for case in cases if case.get("passed")),
        "cases": cases,
    }


def extract_candidates(rows: Sequence[Mapping[str, object]]) -> list[dict[str, Any]]:
    return decisions.review_decision_candidates(
        decisions.extract_decision_candidates(rows, thread_key="thread:decision-shadow-public")
    )


def case_stub(
    case_id: str,
    *,
    passed: bool,
    prompt: str,
    include_private_text: bool,
    **details: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "case_id": case_id,
        "passed": passed,
        "prompt_sha1": sha1_text(prompt)[:16],
        **details,
    }
    if include_private_text:
        payload["prompt"] = prompt
    return payload


def run_track_a(*, include_private_text: bool) -> dict[str, Any]:
    source_text = "Do not replace the registry_search split with generated summaries."
    rows = [message(message_id="track-a-source", text=source_text, line=10)]
    candidates = extract_candidates(rows)
    assessment = decisions.build_decision_state_assessment(candidates[0]) if candidates else {}
    refs = [ref for ref in assessment.get("basis_refs") or [] if isinstance(ref, Mapping)]
    passed = bool(refs) and assessment.get("truth_boundary") == "derived_weather_not_source_fact"
    case = case_stub(
        "track_a_original_source_ref",
        passed=passed,
        prompt="Can you cite the decision source for the registry split?",
        include_private_text=include_private_text,
        basis_ref_count=len(refs),
        truth_boundary=assessment.get("truth_boundary"),
        **sanitized_refs(refs),
    )
    if include_private_text:
        case["source_text"] = source_text
    return track_payload(
        track="A",
        goal="source-backed recall cites the original decision source, not a generated summary",
        cases=[case],
    )


def rejected_route_ticket(prompt: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = [
        message(
            message_id="track-b-source",
            text="Do not replace the registry_search.py split with direct registry imports.",
            line=20,
        )
    ]
    candidates = extract_candidates(rows)
    return candidates, decisions.render_coding_continuity_ticket(
        candidates,
        prompt=prompt,
        trigger="compaction_loss",
        visible_context_has_source=False,
    )


def run_track_b(*, include_private_text: bool) -> dict[str, Any]:
    prompt = "Patch registry_search.py by moving the split back into direct registry imports."
    _, tickets = rejected_route_ticket(prompt)
    ticket = tickets[0] if tickets else {}
    host_decision = host_contract.host_decision_for_ticket(ticket) if ticket else {}
    refs = [ref for ref in ticket.get("evidence_refs") or [] if isinstance(ref, Mapping)]
    passed = (
        ticket.get("proposed_use") == "warn"
        and ticket.get("intervention_level") == "warning"
        and host_decision.get("visibility") == "warning"
        and bool(refs)
    )
    return track_payload(
        track="B",
        goal="rejected-path protection warns with correct reason and source refs",
        cases=[
            case_stub(
                "track_b_rejected_route_warning",
                passed=passed,
                prompt=prompt,
                include_private_text=include_private_text,
                proposed_use=ticket.get("proposed_use"),
                intervention_level=ticket.get("intervention_level"),
                host_visibility=host_decision.get("visibility"),
                diagnostics=(ticket.get("diagnostics") or {}).get("decision"),
                **sanitized_refs(refs),
            )
        ],
    )


def run_track_c(*, include_private_text: bool) -> dict[str, Any]:
    payload = compaction_benchmark.run_benchmark(include_private_text=include_private_text)
    passed = bool(payload.get("ok")) and bool(payload.get("quality_gate_ok"))
    metrics = payload.get("metrics") or {}
    return track_payload(
        track="C",
        goal="compaction continuity preserves task boundary, correction, and definition of done",
        cases=[
            {
                "case_id": "track_c_compaction_continuity_runner",
                "passed": passed,
                "status": payload.get("status"),
                "case_count": metrics.get("total_cases") or payload.get("case_count"),
                "correction_anchor_recall": metrics.get("correction_anchor_recall"),
                "privacy_boundary": payload.get("privacy_boundary") or {},
            }
        ],
    )


def run_track_d(*, include_private_text: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    registry_prompt = "Patch registry_search.py and maybe restore direct registry imports."
    rows = [
        message(
            message_id="track-d-registry",
            text="Do not replace the registry_search.py split with direct registry imports.",
            line=30,
        ),
        message(
            message_id="track-d-readme",
            text="Do not make the README typography section longer than the install guide.",
            line=31,
        ),
    ]
    candidates = extract_candidates(rows)
    tickets = decisions.render_coding_continuity_ticket(
        candidates,
        prompt=registry_prompt,
        trigger="compaction_loss",
    )
    selected = str((tickets[0].get("relevant_decisions") or [""])[0]) if tickets else ""
    expected = str(candidates[0].get("decision_id") or "") if candidates else ""
    wrong_source_passed = selected == expected and "readme" not in selected.casefold()
    track = track_payload(
        track="D",
        goal="code-navigation partnership selects the relevant historical decision without repo-map authority",
        cases=[
            case_stub(
                "track_d_selects_registry_decision",
                passed=wrong_source_passed,
                prompt=registry_prompt,
                include_private_text=include_private_text,
                selected_decision_sha1=sha1_text(selected)[:16],
                expected_decision_sha1=sha1_text(expected)[:16],
                repo_map_required=False,
            )
        ],
    )
    negative = {
        "passed": wrong_source_passed,
        "control": "wrong_source_evidence",
        "selected_expected_decision": selected == expected,
    }
    return track, negative


def run_track_e(*, include_private_text: bool) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    prompt = "Patch registry_search.py by moving the split back into direct registry imports."
    candidates, _ = rejected_route_ticket(prompt)
    visible = decisions.render_coding_continuity_ticket(
        candidates,
        prompt=prompt,
        trigger="compaction_loss",
        visible_context_has_source=True,
    )
    unrelated = decisions.render_coding_continuity_ticket(
        candidates,
        prompt="Update README typography and button spacing.",
        trigger="compaction_loss",
        visible_context_has_source=False,
    )
    stale_rows = [
        message(
            message_id="track-e-stale",
            text="The old direct registry import route is superseded and no longer current.",
            line=40,
        )
    ]
    stale_candidates = extract_candidates(stale_rows)
    stale = decisions.render_coding_continuity_ticket(
        stale_candidates,
        prompt=prompt,
        trigger="compaction_loss",
    )
    visible_passed = visible == []
    unrelated_passed = unrelated == []
    stale_passed = stale == []
    track = track_payload(
        track="E",
        goal="anti-nag stays silent when source is visible or action would not change",
        cases=[
            case_stub(
                "track_e_visible_source_suppressed",
                passed=visible_passed,
                prompt=prompt,
                include_private_text=include_private_text,
                emitted_ticket_count=len(visible),
            ),
            case_stub(
                "track_e_unrelated_prompt_suppressed",
                passed=unrelated_passed,
                prompt="Update README typography and button spacing.",
                include_private_text=include_private_text,
                emitted_ticket_count=len(unrelated),
            ),
            case_stub(
                "track_e_stale_authority_suppressed",
                passed=stale_passed,
                prompt=prompt,
                include_private_text=include_private_text,
                emitted_ticket_count=len(stale),
            ),
        ],
    )
    return (
        track,
        {"passed": visible_passed, "control": "visible_source_suppression"},
        {"passed": stale_passed, "control": "stale_authority"},
    )


def run_benchmark(*, include_private_text: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    track_d, wrong_source = run_track_d(include_private_text=include_private_text)
    track_e, visible_source, stale_authority = run_track_e(include_private_text=include_private_text)
    tracks = {
        "track_a_source_evidence": run_track_a(include_private_text=include_private_text),
        "track_b_rejected_path": run_track_b(include_private_text=include_private_text),
        "track_c_compaction_boundary": run_track_c(include_private_text=include_private_text),
        "track_d_navigation_selection": track_d,
        "track_e_anti_nag": track_e,
    }
    track_statuses = {name: str(track.get("status") or "failed") for name, track in tracks.items()}
    quality_gate_ok = all(bool(track.get("quality_gate_ok")) for track in tracks.values())
    cannot_claim = [
        "private_real_history_behavior_lift",
        "full_code_index_navigation_quality",
        "live_host_timing_or_annoyance_lift",
    ]
    if include_private_text:
        cannot_claim.append("private_text_debug_mode_not_public_evidence")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_coding_decision_shadow_benchmark",
        "generated_at": now_utc(),
        "ok": quality_gate_ok,
        "quality_gate_ok": quality_gate_ok,
        "status": "quality_gate_passed" if quality_gate_ok else "baseline_captured_with_known_gaps",
        "track_statuses": track_statuses,
        "tracks": tracks,
        "negative_controls": {
            "wrong_source_evidence": wrong_source,
            "visible_source_suppression": visible_source,
            "stale_authority": stale_authority,
        },
        "privacy_boundary": {
            "raw_text_emitted": include_private_text,
            "raw_source_refs_emitted": False,
            "absolute_paths_emitted": False,
            "output_shape": "sanitized_coding_decision_shadow_benchmark",
        },
        "cannot_claim": sorted(cannot_claim),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-private-text", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = run_benchmark(include_private_text=args.include_private_text)
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"coding decision-shadow benchmark: {payload['status']}")
        for name, status in payload["track_statuses"].items():
            print(f"- {name}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
