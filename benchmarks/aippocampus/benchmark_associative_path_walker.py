#!/usr/bin/env python3
"""Public-safe Associative Path Walker quality gate."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.core import now_utc
from aippocampus_runtime.recall import (
    agent_continuity,
    agent_continuity_cli_support,
    associative_path_fallback,
)
from aippocampus_runtime.recall.associative_path_inputs import build_associative_path_diagnostic
from aippocampus_runtime.recall.associative_path_walker import walk_associative_paths

SCHEMA_VERSION = 1


def fixture_path_walker_cases() -> list[dict[str, Any]]:
    source_ref = {"thread_key": "fixture:path-walker", "source_id": "src-apw"}
    return [
        {
            "case_id": "unsupported_distinctive_anchor",
            "query": "slime mold exploratory recall",
            "candidates": [
                {
                    "route_id": "route:generic-memory",
                    "route_terms": ["memory", "recall", "search"],
                    "thread_key": "thread:generic",
                }
            ],
            "bridge_rows": [],
            "expectation": {
                "useful_route": False,
                "expected_decision": "abstain",
                "wrong_hop_drag_allowed": False,
            },
        },
        {
            "case_id": "source_backed_bridge_rescues_cross_vocab",
            "query": "slime mold exploratory recall",
            "candidates": [
                {
                    "route_id": "route:associative-path-walker",
                    "route_terms": ["associative path walker", "routing exploration"],
                    "thread_key": "thread:apw",
                }
            ],
            "bridge_rows": [
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["slime mold", "exploratory recall"],
                    "to_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [source_ref],
                    "scope_bucket": "project",
                }
            ],
            "expectation": {
                "useful_route": True,
                "expected_decision": "route_candidates",
                "wrong_hop_drag_allowed": False,
            },
        },
        {
            "case_id": "wrong_feedback_evaporates_path",
            "query": "slime mold exploratory recall",
            "candidates": [
                {
                    "route_id": "route:associative-path-walker",
                    "candidate_id": "bridge:apw",
                    "route_terms": ["associative path walker", "routing exploration"],
                    "thread_key": "thread:apw",
                }
            ],
            "bridge_rows": [
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["slime mold", "exploratory recall"],
                    "to_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [source_ref],
                    "scope_bucket": "project",
                }
            ],
            "feedback_rows": [
                {"candidate_id": "bridge:apw", "signal": "wrong_route_drag"},
            ],
            "expectation": {
                "useful_route": False,
                "expected_decision": "abstain",
                "wrong_hop_drag_allowed": False,
            },
        },
        {
            "case_id": "stale_route_stays_shadowed",
            "query": "slime mold exploratory recall",
            "candidates": [
                {
                    "route_id": "route:stale-apw",
                    "candidate_id": "bridge:stale-apw",
                    "route_terms": ["associative path walker", "routing exploration"],
                    "thread_key": "thread:apw",
                    "freshness": "stale",
                    "source_refs": [source_ref],
                }
            ],
            "bridge_rows": [
                {
                    "candidate_id": "bridge:stale-apw",
                    "from_terms": ["slime mold", "exploratory recall"],
                    "to_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [source_ref],
                    "scope_bucket": "project",
                }
            ],
            "expectation": {
                "useful_route": False,
                "expected_decision": "abstain",
                "wrong_hop_drag_allowed": False,
            },
        },
        {
            "case_id": "source_free_semantic_bridge_evaporates",
            "query": "slime mold exploratory recall",
            "candidates": [
                {
                    "route_terms": ["slime mold", "routing exploration"],
                    "scope_bucket": "project",
                }
            ],
            "bridge_rows": [
                {
                    "candidate_id": "bridge:source-free",
                    "from_terms": ["slime mold", "exploratory recall"],
                    "to_terms": ["routing exploration"],
                    "scope_bucket": "project",
                }
            ],
            "expectation": {
                "useful_route": False,
                "expected_decision": "abstain",
                "wrong_hop_drag_allowed": False,
            },
        },
        {
            "case_id": "cross_scope_positive_feedback_does_not_lift",
            "query": "slime mold exploratory recall",
            "candidates": [
                {
                    "route_id": "route:associative-path-walker",
                    "candidate_id": "bridge:apw",
                    "route_terms": ["associative path walker", "routing exploration"],
                    "thread_key": "thread:apw",
                    "scope_bucket": "project",
                }
            ],
            "bridge_rows": [
                {
                    "candidate_id": "bridge:apw",
                    "from_terms": ["slime mold", "exploratory recall"],
                    "to_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [source_ref],
                    "scope_bucket": "project",
                }
            ],
            "feedback_rows": [
                {
                    "candidate_id": "bridge:apw",
                    "signal": "source_reopen_success",
                    "scope_bucket": "user_private",
                },
            ],
            "expectation": {
                "useful_route": True,
                "expected_decision": "route_candidates",
                "wrong_hop_drag_allowed": False,
                "cross_scope_positive_must_not_lift": True,
            },
        },
        {
            "case_id": "chinese_dogfood_cue_bridge_rescue",
            "query": "黏菌 联想回忆 探索算法",
            "candidates": [
                {
                    "route_id": "route:associative-path-walker",
                    "candidate_id": "bridge:apw-cn",
                    "route_terms": ["associative path walker", "routing exploration"],
                    "thread_key": "thread:apw",
                    "scope_bucket": "project",
                }
            ],
            "bridge_rows": [
                {
                    "candidate_id": "bridge:apw-cn",
                    "from_terms": ["黏菌", "联想回忆", "探索算法"],
                    "to_terms": ["associative path walker", "routing exploration"],
                    "source_refs": [source_ref],
                    "scope_bucket": "project",
                }
            ],
            "expectation": {
                "useful_route": True,
                "expected_decision": "route_candidates",
                "wrong_hop_drag_allowed": False,
            },
        },
    ]


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")


def _opened_source_matches_ref(deepened: Mapping[str, Any], expected_ref: Mapping[str, Any]) -> bool:
    result = deepened.get("result") if isinstance(deepened.get("result"), Mapping) else {}
    for ref in result.get("source_refs") or []:
        if not isinstance(ref, Mapping):
            continue
        for key in ("message_id", "turn_id", "source_id"):
            expected = str(expected_ref.get(key) or "").strip()
            if expected and str(ref.get(key) or "").strip() != expected:
                return False
        return True
    return False


def _source_window_contains_anchors(deepened: Mapping[str, Any], anchors: Sequence[str]) -> bool:
    result = deepened.get("result") if isinstance(deepened.get("result"), Mapping) else {}
    source_window = result.get("source_window") if isinstance(result.get("source_window"), Mapping) else {}
    text = "\n".join(
        str(message.get("text") or "")
        for message in source_window.get("messages") or []
        if isinstance(message, Mapping)
    )
    return all(str(anchor) in text for anchor in anchors)


def _opened_source_primary_message_id(deepened: Mapping[str, Any]) -> str:
    result = deepened.get("result") if isinstance(deepened.get("result"), Mapping) else {}
    refs = result.get("source_refs") if isinstance(result.get("source_refs"), list) else []
    first = refs[0] if refs and isinstance(refs[0], Mapping) else {}
    return str(first.get("message_id") or "")


def evaluate_real_clean_source_parity_gate() -> dict[str, Any]:
    """Check diagnostic-to-agent APW parity on a real clean-source fixture."""

    cue = "黏菌 联想回忆 探索算法"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        clean = root / ".aippocampus" / "clean-source"
        registry = root / "registry"
        registry.mkdir()
        _write_jsonl(
            clean / "messages.jsonl",
            [
                {
                    "message_id": "msg-real-clean-control",
                    "turn_id": "turn-real-clean-apw",
                    "turn_index": 3,
                    "source_id": "src-real-clean-control",
                    "source_line": 8,
                    "role": "developer",
                    "phase": "commentary",
                    "source_use_class": "control_only",
                    "text": "<goal_context> 黏菌 联想回忆 探索算法 is a control fixture and must not bind the APW foreground action.",
                },
                {
                    "message_id": "msg-real-clean-apw",
                    "turn_id": "turn-real-clean-apw",
                    "turn_index": 3,
                    "source_id": "src-real-clean-apw",
                    "source_line": 9,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": "Public fixture: 黏菌 联想回忆 探索算法 should bridge APW diagnostics into agent fallback.",
                }
            ],
        )
        _write_jsonl(
            clean / "turns.jsonl",
            [
                {
                    "turn_id": "turn-real-clean-apw",
                    "turn_index": 3,
                    "message_ids": ["msg-real-clean-control", "msg-real-clean-apw"],
                    "assistant_phase": "final_answer",
                }
            ],
        )
        diagnostic = build_associative_path_diagnostic(
            query=cue,
            cwd=root,
            clean_source_dir=clean,
        )
        agent_payload = agent_continuity.recall(
            cue,
            cwd=root,
            clean_source_dir=clean,
            registry_dir=registry,
            include_associative_fallback=True,
        )
        diagnostic_candidates = [
            row for row in diagnostic.get("top_candidates") or [] if isinstance(row, Mapping)
        ]
        expected_ref = (
            diagnostic_candidates[0].get("source_refs", [{}])[0]
            if diagnostic_candidates and diagnostic_candidates[0].get("source_refs")
            else {}
        )
        cache_path = root / "last-recall.json"
        cache_written = agent_continuity_cli_support.write_last_recall_cache(
            agent_payload.get("deepen_requests") or [],
            query=cue,
            cwd=root,
            clean_source_dir=clean,
            registry_dir=registry,
            macro_state_path=None,
            project="AIppocampus",
            max_matches=5,
            schema_version=agent_continuity.SCHEMA_VERSION,
            path=cache_path,
        )
        selector_id = agent_continuity_cli_support.write_recall_selector_snapshot(cache_path)
        agent_payload["last_recall_cache_available"] = cache_written
        agent_payload["recall_selector_id"] = selector_id
        public_payload = agent_continuity_cli_support.public_recall_projection(
            agent_payload,
            query=cue,
        )
        foreground_action = public_payload.get("foreground_action")
        foreground_action = foreground_action if isinstance(foreground_action, Mapping) else {}
        action_args = foreground_action.get("arguments")
        action_args = action_args if isinstance(action_args, Mapping) else {}
        try:
            action_request_index = int(action_args.get("request_index") or 0)
        except (TypeError, ValueError):
            action_request_index = 0
        try:
            handle, context = agent_continuity_cli_support.handle_from_last_recall_cache(
                request_index=action_request_index,
                path=cache_path,
            )
            deepened = agent_continuity.deepen(
                handle,
                cwd=context.get("cwd") or root,
                clean_source_dir=context.get("clean_source_dir") or clean,
                registry_dir=context.get("registry_dir") or registry,
            )
        except Exception as exc:  # pragma: no cover - returned as gate diagnostics
            deepened = {"status": "cannot_verify", "error": {"type": type(exc).__name__, "message": str(exc)}}
        diagnostic_reopenable = int(
            (diagnostic.get("metrics") or {}).get("source_reopenable_candidate_count") or 0
        )
        policy = agent_payload.get("associative_path_policy")
        policy = policy if isinstance(policy, Mapping) else {}
        fallback = agent_payload.get("associative_path_fallback")
        fallback = fallback if isinstance(fallback, Mapping) else {}
        candidate_source_counts = dict((diagnostic.get("metrics") or {}).get("candidate_source_counts") or {})
        fallback_route = fallback.get("status") == "route_candidate"
        agent_candidate_input = bool(policy.get("apw_candidate_input_available"))
        missing_input_mismatch = bool(diagnostic_reopenable and not agent_candidate_input)
        source_kind = str(
            fallback.get("candidate_source_kind")
            or next(iter(candidate_source_counts), "")
            or "unknown"
        )
        action_binds_fallback = bool(
            foreground_action.get("id") == "deepen_associative_path_fallback"
            and action_request_index == int(fallback.get("request_index") or 0)
        )
        opened_source_matches_apw_candidate = _opened_source_matches_ref(deepened, expected_ref)
        opened_source_contains_safe_cue_anchors = _source_window_contains_anchors(
            deepened,
            ["黏菌", "联想回忆", "探索算法"],
        )
        foreground_action_roundtrip_ok = bool(
            action_binds_fallback
            and opened_source_matches_apw_candidate
            and opened_source_contains_safe_cue_anchors
        )
        apw_label_opened_source_mismatch_count = 0 if foreground_action_roundtrip_ok else 1
        opened_source_primary_message_id = _opened_source_primary_message_id(deepened)
        expected_apw_candidate_message_id = str(expected_ref.get("message_id") or "")
        ok = bool(
            diagnostic_reopenable
            and agent_candidate_input
            and fallback_route
            and source_kind == "current_clean_source"
            and foreground_action_roundtrip_ok
        )
    return {
        "kind": "aippocampus_real_clean_source_apw_parity_gate",
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "evidence_mode": "real-clean-source fixture",
        "query": cue,
        "diagnostic_source_reopenable_candidate_count": diagnostic_reopenable,
        "agent_candidate_input_available": agent_candidate_input,
        "agent_fallback_status": fallback.get("status"),
        "agent_run_reason": policy.get("run_reason"),
        "candidate_source_counts": candidate_source_counts,
        "candidate_source_kind": source_kind,
        "missing_input_mismatch": missing_input_mismatch,
        "foreground_action_roundtrip_ok": foreground_action_roundtrip_ok,
        "opened_source_matches_apw_candidate": opened_source_matches_apw_candidate,
        "opened_source_contains_safe_cue_anchors": opened_source_contains_safe_cue_anchors,
        "opened_source_primary_message_id": opened_source_primary_message_id,
        "expected_apw_candidate_message_id": expected_apw_candidate_message_id,
        "foreground_action_request_index": action_request_index,
        "foreground_action_recall_selector_present": bool(action_args.get("recall_selector")),
        "foreground_action_binds_fallback_request": action_binds_fallback,
        "source_ref_digest": fallback.get("source_ref_digest"),
        "foreground_recovery_available": bool(
            fallback_route and agent_payload.get("deepen_requests")
        ),
        "reason_codes": {
            "diagnostic": diagnostic.get("reason_codes") or [],
            "fallback": fallback.get("reason_codes") or [],
        },
        "red_lines": {
            "diagnostic_agent_fallback_parity_failure": not ok,
            "diagnostic_reopenable_but_agent_input_missing": missing_input_mismatch,
            "foreground_action_roundtrip_failure": not foreground_action_roundtrip_ok,
            "apw_label_opened_source_mismatch_count": apw_label_opened_source_mismatch_count,
        },
        "boundary": {
            "live_model_calls": 0,
            "default_ranking_influence_allowed": False,
            "source_reopen_required_before_claim": True,
        },
    }


def evaluate_path_walker_gate(
    cases: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = []
    for case in cases or fixture_path_walker_cases():
        baseline = walk_associative_paths(
            query=str(case.get("query") or ""),
            candidates=list(case.get("candidates") or []),
            bridge_rows=[],
            feedback_rows=[],
        )
        report = walk_associative_paths(
            query=str(case.get("query") or ""),
            candidates=list(case.get("candidates") or []),
            bridge_rows=case.get("bridge_rows") or [],
            feedback_rows=case.get("feedback_rows") or [],
        )
        diagnostic = build_associative_path_diagnostic(
            query=str(case.get("query") or ""),
            candidates=list(case.get("candidates") or []),
            semantic_bridge_rows=case.get("bridge_rows") or [],
            feedback_rows=case.get("feedback_rows") or [],
        )
        expectation = dict(case.get("expectation") or {})
        first_candidate = report["candidates"][0] if report.get("candidates") else {}
        candidate_reasons = first_candidate.get("reason_codes") if isinstance(first_candidate, Mapping) else []
        route_count = int(report.get("candidate_count") or 0)
        baseline_route_count = int(baseline.get("candidate_count") or 0)
        first_action = diagnostic["next_actions"][0] if diagnostic.get("next_actions") else {}
        apw_action_emitted = bool(route_count and first_action.get("id") == "open_apw_source_candidate_1")
        agent_followed_apw_action = bool(
            apw_action_emitted
            and first_action.get("mutation_risk") == "read_only"
            and (
                first_action.get("command")
                or first_action.get("tool_name")
                or first_action.get("source_reopen_args")
            )
        )
        source_reopen_success = bool(
            agent_followed_apw_action
            and route_count
            and report["candidates"][0].get("source_refs")
        )
        specificity_ok = "generic_only_path_evaporated" in report.get("reason_codes", []) or route_count > 0
        useful = bool(route_count) == bool(expectation.get("useful_route"))
        wrong_hop_drag = bool(
            route_count
            and not expectation.get("useful_route")
            and "path_found_reopenable" in report.get("reason_codes", [])
        )
        cross_scope_lift = bool(
            expectation.get("cross_scope_positive_must_not_lift")
            and "positive_feedback_same_scope" in candidate_reasons
        )
        top_action_specificity_ok = bool(
            not route_count
            or "source_backed_semantic_bridge" in candidate_reasons
            or baseline_route_count == route_count
        )
        task_usefulness_outcome = bool(source_reopen_success and expectation.get("useful_route"))
        manual_search_before_apw = bool(expectation.get("manual_search_before_apw"))
        expected_decision = str(expectation.get("expected_decision") or report["decision"])
        decision_ok = report["decision"] == expected_decision
        source_free_scent = bool(
            "source_free_path_evaporated" in report.get("reason_codes", [])
            or "source_free_candidates_will_evaporate" in diagnostic.get("reason_codes", [])
        )
        rows.append(
            {
                "case_id": str(case.get("case_id") or ""),
                "baseline_route_count": baseline_route_count,
                "decision": report["decision"],
                "expected_decision": expected_decision,
                "decision_ok": decision_ok,
                "route_count": route_count,
                "apw_action_emitted": apw_action_emitted,
                "agent_followed_apw_action": agent_followed_apw_action,
                "path_specificity_ok": specificity_ok,
                "top_action_specificity_ok": top_action_specificity_ok,
                "task_usefulness_ok": useful,
                "task_usefulness_outcome": task_usefulness_outcome,
                "wrong_hop_drag": wrong_hop_drag,
                "scope_violation": cross_scope_lift,
                "source_reopen_success": source_reopen_success,
                "manual_search_before_apw": manual_search_before_apw,
                "irrelevant_drag": bool(route_count and not expectation.get("useful_route")),
                "source_free_scent": source_free_scent,
                "source_free_scent_projected": bool(
                    source_free_scent and (route_count or apw_action_emitted)
                ),
                "unsupported_cue_abstain": bool(
                    not route_count and not expectation.get("useful_route")
                ),
                "first_action_id": str(first_action.get("id") or ""),
                "navigation_only": report["claim_permission"] == "no_claim_before_reopen",
                "reason_codes": report["reason_codes"],
                "candidate_reason_codes": list(candidate_reasons or []),
            }
        )
    parity_gate = evaluate_real_clean_source_parity_gate()
    red_lines = {
        "wrong_hop_drag_count": sum(1 for row in rows if row["wrong_hop_drag"]),
        "source_truth_claim_count": sum(1 for row in rows if not row["navigation_only"]),
        "scope_violation_count": sum(1 for row in rows if row["scope_violation"]),
        "diagnostic_agent_fallback_parity_failure_count": 0 if parity_gate["ok"] else 1,
        "foreground_action_roundtrip_failure_count": (
            0 if parity_gate.get("foreground_action_roundtrip_ok") else 1
        ),
        "apw_label_opened_source_mismatch_count": int(
            (parity_gate.get("red_lines") or {}).get("apw_label_opened_source_mismatch_count") or 0
        ),
        "default_ranking_influence_count": 0,
    }
    warnings = {
        "route_count_lift_without_usefulness_count": sum(
            1 for row in rows if row["route_count"] and not row["task_usefulness_ok"]
        ),
        "route_count_without_executable_action_count": sum(
            1 for row in rows if row["route_count"] and not row["apw_action_emitted"]
        ),
        "action_without_source_reopen_success_count": sum(
            1 for row in rows if row["apw_action_emitted"] and not row["source_reopen_success"]
        ),
        "specificity_failure_count": sum(1 for row in rows if not row["path_specificity_ok"]),
        "top_action_specificity_failure_count": sum(
            1 for row in rows if not row["top_action_specificity_ok"]
        ),
        "decision_mismatch_count": sum(1 for row in rows if not row["decision_ok"]),
    }
    ok = all(value == 0 for value in red_lines.values()) and all(
        row["task_usefulness_ok"] and row["decision_ok"] for row in rows
    )
    promotion_observed = {
        "wrong_hop_drag_count": red_lines["wrong_hop_drag_count"],
        "irrelevant_drag_count": sum(1 for row in rows if row["irrelevant_drag"]),
        "source_free_scent_projected_count": sum(
            1 for row in rows if row["source_free_scent_projected"]
        ),
        "manual_search_before_apw_count": sum(1 for row in rows if row["manual_search_before_apw"]),
        "route_count_without_executable_action_count": warnings[
            "route_count_without_executable_action_count"
        ],
        "action_without_source_reopen_success_count": warnings[
            "action_without_source_reopen_success_count"
        ],
        "decision_mismatch_count": warnings["decision_mismatch_count"],
        "default_ranking_influence_count": red_lines["default_ranking_influence_count"],
        "scope_violation_count": red_lines["scope_violation_count"],
        "diagnostic_agent_fallback_parity_failure_count": red_lines[
            "diagnostic_agent_fallback_parity_failure_count"
        ],
        "foreground_action_roundtrip_failure_count": red_lines[
            "foreground_action_roundtrip_failure_count"
        ],
        "apw_label_opened_source_mismatch_count": red_lines[
            "apw_label_opened_source_mismatch_count"
        ],
    }
    promotion_thresholds = {
        "wrong_hop_drag_count": 0,
        "irrelevant_drag_count": 0,
        "source_free_scent_projected_count": 0,
        "manual_search_before_apw_count": 0,
        "route_count_without_executable_action_count": 0,
        "action_without_source_reopen_success_count": 0,
        "decision_mismatch_count": 0,
        "default_ranking_influence_count": 0,
        "scope_violation_count": 0,
        "diagnostic_agent_fallback_parity_failure_count": 0,
        "foreground_action_roundtrip_failure_count": 0,
        "apw_label_opened_source_mismatch_count": 0,
    }
    promotion_checklist = [
        {
            "metric": metric,
            "observed": promotion_observed[metric],
            "threshold_max": threshold,
            "passed": promotion_observed[metric] <= threshold,
        }
        for metric, threshold in promotion_thresholds.items()
    ]
    promotion_gate_ok = ok and all(row["passed"] for row in promotion_checklist)
    return {
        "kind": "aippocampus_associative_path_walker_quality_gate",
        "schema_version": SCHEMA_VERSION,
        "run_at": now_utc(),
        "ok": ok,
        "quality_gate_ok": ok,
        "rows": rows,
        "metrics": {
            "case_count": len(rows),
            "real_clean_source_parity_gate_ok": bool(parity_gate["ok"]),
            "foreground_action_roundtrip_ok": bool(
                parity_gate.get("foreground_action_roundtrip_ok")
            ),
            "opened_source_matches_apw_candidate": bool(
                parity_gate.get("opened_source_matches_apw_candidate")
            ),
            "route_existence_count": sum(1 for row in rows if row["route_count"] > 0),
            "baseline_route_existence_count": sum(1 for row in rows if row["baseline_route_count"] > 0),
            "apw_action_emitted_count": sum(1 for row in rows if row["apw_action_emitted"]),
            "agent_followed_apw_action_count": sum(
                1 for row in rows if row["agent_followed_apw_action"]
            ),
            "top_action_specificity_ok_count": sum(1 for row in rows if row["top_action_specificity_ok"]),
            "source_reopen_success_count": sum(1 for row in rows if row["source_reopen_success"]),
            "task_usefulness_outcome_count": sum(1 for row in rows if row["task_usefulness_outcome"]),
            "task_usefulness_ok_count": sum(1 for row in rows if row["task_usefulness_ok"]),
            "manual_search_before_apw_count": sum(1 for row in rows if row["manual_search_before_apw"]),
            "wrong_hop_drag_count": red_lines["wrong_hop_drag_count"],
            "irrelevant_drag_count": sum(1 for row in rows if row["irrelevant_drag"]),
            "source_free_scent_count": sum(1 for row in rows if row["source_free_scent"]),
            "source_free_scent_projected_count": sum(
                1 for row in rows if row["source_free_scent_projected"]
            ),
            "unsupported_cue_abstain_count": sum(1 for row in rows if row["unsupported_cue_abstain"]),
            "scope_violation_count": red_lines["scope_violation_count"],
        },
        "real_clean_source_parity_gate": parity_gate,
        "promotion_gate": {
            "ok": promotion_gate_ok,
            "status": (
                "passed_for_semi_default_recovery"
                if promotion_gate_ok
                else "blocked_for_semi_default_recovery"
            ),
            "allowed_build_posture": "semi_default_recovery",
            "blocked_build_postures": ["default_ranking", "source_truth_claims_from_apw"],
            "checklist": promotion_checklist,
            "thresholds": promotion_thresholds,
            "observed": promotion_observed,
            "rollback_env": (
                f"{associative_path_fallback.PROMOTION_MODE_ENV}="
                f"{associative_path_fallback.MODE_OPT_IN}"
            ),
            "hard_off_env": (
                f"{associative_path_fallback.PROMOTION_MODE_ENV}="
                f"{associative_path_fallback.MODE_OFF}"
            ),
            "evidence_mode": "public_fixture_proxy_plus_real_clean_source_fixture",
            "live_model_calls": 0,
            "requires_live_history_before_default_ranking": True,
            "semi_default_surface": "secondary_recovery_action_for_no_route_or_weak_recall",
            "default_ranking_influence_allowed": False,
        },
        "warnings": warnings,
        "red_lines": red_lines,
        "boundary": {
            "navigation_lift_is_not_source_evidence": True,
            "ambient_readiness_not_claimed": True,
            "default_recall_influence_allowed": False,
            "proxy_gate_not_live_quality_claim": True,
            "follow_through_mode": "proxy_action_path",
            "live_model_calls": 0,
        },
        "cannot_claim": [
            "broad_live_recall_quality",
            "private_history_path_quality",
            "path_resonance_as_source_truth",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON report")
    args = parser.parse_args(argv)
    report = evaluate_path_walker_gate()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"associative path walker gate: {'ok' if report['ok'] else 'failed'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
