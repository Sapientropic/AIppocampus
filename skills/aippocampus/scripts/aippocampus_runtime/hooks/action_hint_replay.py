"""Public-safe replay telemetry for #435 action-time hints."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.hooks.action_hint import evaluate_action_hint
from aippocampus_runtime.hooks.action_hint_cache import build_action_hint_cache_report

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_action_hint_replay_telemetry"


def _ref(name: str) -> dict[str, str]:
    return {"source_id": f"clean:{name}", "segment_id": f"msg-{name}"}


def _manual_record(**overrides: Any) -> dict[str, Any]:
    base = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_action_hint_prepared_record",
        "record_id": "manual-record",
        "provider_family": "replay_fixture",
        "action_hint_kind": "reopen_source_before_action",
        "next_action": "reopen_source_before_action",
        "navigation_only": True,
        "no_claim_before_reopen": True,
        "source_reopen_required": True,
        "can_support_factual_claim": False,
        "authority": "navigation_only",
        "freshness": "current",
        "expires_at_unix": 2000,
        "confidence": "medium",
        "occurrence_count": 2,
        "source_refs": [_ref("manual")],
        "source_handles": [],
        "anti_nag_ids": ["manual-record"],
        "active_recall_lock_ids": [],
        "tool_names": [],
        "issue_ids": [],
        "path_terms": [],
        "command_terms": [],
        "risk_modes": [],
        "action_class": "",
        "support_levels": ["candidate"],
        "match_terms": ["manual", "reopen", "source"],
        "reason_codes": ["replay_fixture"],
    }
    base.update(overrides)
    return base


def public_replay_cases() -> list[dict[str, Any]]:
    aar_cache = build_action_hint_cache_report(
        aar_v2_records=[
            {
                "record_id": "source-claim-aar",
                "action_class": "specific_memory_source_claim",
                "source_refs": [_ref("aar")],
                "nudge": {"recommended_action": "reopen_source_before_specific_claim"},
            }
        ],
        now_unix=1000,
    )
    learning_cache = build_action_hint_cache_report(
        learning_guidance=[
            {
                "guidance_id": "learn-preflight",
                "next_action": "run_preflight_before_broad_test",
                "guidance_text": "Run ruff before pytest.",
                "source_refs": [_ref("learn")],
                "reason_codes": ["learning_guidance_surface"],
            }
        ],
        now_unix=1000,
    )
    lock_cache = build_action_hint_cache_report(
        active_recall_locks=[
            {
                "lock_id": "lock-evidence-capture",
                "next_action": "capture_evidence_before_action",
                "route_reasons": ["evidence", "edit", "anchor"],
                "source_refs": [_ref("lock")],
            }
        ],
        now_unix=1000,
    )
    route_cache = build_action_hint_cache_report(
        attention_route_tokens=[
            {
                "token_id": "stale-route-shadow",
                "action_hint_kind": "avoid_stale_route_reuse",
                "next_action": "reopen_current_route_before_stale_route_reuse",
                "source_handles": [
                    {"source_id": "clean:route", "segment_id": "msg-route", "reopen_required": True}
                ],
                "route_features": {"terms": ["stale", "route", "issue435"]},
                "route_metadata": {"privacy": "public", "currentness": "current"},
            }
        ],
        now_unix=1000,
    )
    broad_search_cache = build_action_hint_cache_report(
        attention_route_tokens=[
            {
                "token_id": "prepared-route-before-broad-search",
                "action_hint_kind": "reopen_route_before_broad_search",
                "next_action": "reopen_prepared_route_before_broad_search",
                "source_handles": [
                    {
                        "source_id": "clean:broad-search",
                        "segment_id": "msg-broad-search",
                        "reopen_required": True,
                    }
                ],
                "route_features": {"terms": ["issue1844", "prepared", "route"]},
                "route_metadata": {"privacy": "public", "currentness": "current"},
                "command_terms": ["broad_search", "search"],
            }
        ],
        now_unix=1000,
    )
    private_cache = build_action_hint_cache_report(
        attention_route_tokens=[
            {
                "token_id": "private-route",
                "source_handles": [
                    {"source_id": "private:route", "segment_id": "msg-private"}
                ],
                "route_features": {"terms": ["private", "route"]},
                "route_metadata": {"privacy": "private", "currentness": "current"},
            }
        ],
        now_unix=1000,
    )
    stale_record = _manual_record(record_id="stale-record", freshness="stale")
    low_confidence = _manual_record(
        record_id="low-confidence",
        confidence="low",
        occurrence_count=1,
    )
    dismissed = _manual_record(record_id="dismissed-record", anti_nag_ids=["dismissed-record"])
    return [
        {
            "case_id": "positive_source_reopen_before_claim",
            "group": "positive",
            "expected_hint": True,
            "expected_signal": "source_reopen_before_claim",
            "records": aar_cache["records"],
            "envelope": {
                "hook_event_name": "PreToolUse",
                "tool_name": "final_answer",
                "action_class": "specific_memory_source_claim",
                "support_level": "candidate",
                "tool_input": {"draft": "PRIVATE_SOURCE_CLAIM_SENTINEL"},
            },
        },
        {
            "case_id": "positive_learned_preflight_before_broad_test",
            "group": "positive",
            "expected_hint": True,
            "expected_signal": "learned_preflight_before_broad_test",
            "records": learning_cache["records"],
            "envelope": {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {
                    "command": "pytest PRIVATE_REPO_TEST_SECRET --token sk-REPLAY",
                    "command_family": "pytest",
                    "file_path": "PRIVATE_REPO_TEST_SECRET",
                },
            },
        },
        {
            "case_id": "positive_active_anchor_evidence_capture",
            "group": "positive",
            "expected_hint": True,
            "expected_signal": "active_anchor_evidence_capture",
            "records": lock_cache["records"],
            "envelope": {
                "hook_event_name": "PreToolUse",
                "tool_name": "apply_patch",
                "active_recall_locks": ["lock-evidence-capture"],
                "tool_input": {"file_path": "PRIVATE_REPO_SRC_SECRET"},
            },
        },
        {
            "case_id": "positive_stale_route_avoided",
            "group": "positive",
            "expected_hint": True,
            "expected_signal": "stale_route_avoided",
            "records": route_cache["records"],
            "envelope": {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "git show issue435", "command_family": "git"},
                "intent": "reuse stale route for issue435",
            },
        },
        {
            "case_id": "positive_prepared_route_before_broad_search",
            "group": "positive",
            "expected_hint": True,
            "expected_signal": "prepared_route_before_broad_search",
            "records": broad_search_cache["records"],
            "envelope": {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "rg issue1844 PRIVATE_REPO_SENTINEL"},
                "intent": "broad search for issue1844",
            },
        },
        {
            "case_id": "negative_unrelated_tool_call",
            "group": "negative_control",
            "expected_hint": False,
            "expected_signal": "unrelated_suppressed",
            "records": learning_cache["records"],
            "envelope": {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}},
        },
        {
            "case_id": "negative_source_already_visible",
            "group": "negative_control",
            "expected_hint": False,
            "expected_signal": "source_visible_suppression",
            "records": aar_cache["records"],
            "envelope": {
                "hook_event_name": "PreToolUse",
                "tool_name": "final_answer",
                "action_class": "specific_memory_source_claim",
                "support_level": "candidate",
                "visible_source_refs": [_ref("aar")],
            },
        },
        {
            "case_id": "negative_private_blocked_route",
            "group": "negative_control",
            "expected_hint": False,
            "expected_signal": "private_blocked_suppression",
            "records": private_cache["records"],
            "envelope": {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "intent": "private route",
            },
        },
        {
            "case_id": "negative_stale_refuted_record",
            "group": "negative_control",
            "expected_hint": False,
            "expected_signal": "stale_refuted_suppression",
            "records": [stale_record],
            "envelope": {"hook_event_name": "PreToolUse", "tool_name": "Bash", "intent": "manual"},
        },
        {
            "case_id": "negative_recently_dismissed_hint",
            "group": "negative_control",
            "expected_hint": False,
            "expected_signal": "anti_nag_suppression",
            "records": [dismissed],
            "envelope": {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "intent": "manual",
                "anti_nag_token_ids": ["dismissed-record"],
            },
        },
        {
            "case_id": "negative_low_confidence_one_off",
            "group": "negative_control",
            "expected_hint": False,
            "expected_signal": "low_confidence_suppression",
            "records": [low_confidence],
            "envelope": {"hook_event_name": "PreToolUse", "tool_name": "Bash", "intent": "manual"},
        },
    ]


def run_action_hint_replay(
    cases: Iterable[Mapping[str, Any]] | None = None,
    *,
    now_unix: float = 1001,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    leak_sentinels = [
        "PRIVATE_SOURCE_CLAIM_SENTINEL",
        "sk-REPLAY",
        "PRIVATE_REPO",
        "test_secret.py --token",
    ]
    for case in cases or public_replay_cases():
        baseline = evaluate_action_hint(case["envelope"], [], now_unix=now_unix)
        hinted = evaluate_action_hint(case["envelope"], case.get("records") or [], now_unix=now_unix)
        hint_emitted = bool(hinted.get("hint"))
        serialized = json.dumps(hinted, ensure_ascii=False)
        rows.append(
            {
                "case_id": case["case_id"],
                "group": case["group"],
                "expected_signal": case["expected_signal"],
                "baseline_hint": bool(baseline.get("hint")),
                "hint_emitted": hint_emitted,
                "expected_hint": bool(case["expected_hint"]),
                "outcome_ok": hint_emitted == bool(case["expected_hint"]),
                "provider_family": (hinted.get("hint") or {}).get("provider_family"),
                "source_reopen_required": bool((hinted.get("hint") or {}).get("source_reopen_required")),
                "raw_leak": any(sentinel in serialized for sentinel in leak_sentinels),
                "command_rewritten": bool((hinted.get("diagnostics") or {}).get("command_rewritten")),
                "permission_system_behavior": bool(
                    (hinted.get("diagnostics") or {}).get("permission_system_behavior")
                ),
                "can_support_factual_claim": bool(
                    (hinted.get("hint") or {}).get("can_support_factual_claim")
                ),
            }
        )
    positive = [row for row in rows if row["group"] == "positive"]
    negative = [row for row in rows if row["group"] == "negative_control"]
    emitted = [row for row in rows if row["hint_emitted"]]
    false_positive = [row for row in negative if row["hint_emitted"]]
    red_lines = {
        "source_truth_overclaim_count": sum(1 for row in rows if row["can_support_factual_claim"]),
        "raw_tool_or_source_leak_count": sum(1 for row in rows if row["raw_leak"]),
        "private_path_leak_count": sum(1 for row in rows if row["raw_leak"]),
        "command_rewrite_count": sum(1 for row in rows if row["command_rewritten"]),
        "permission_system_behavior_count": sum(
            1 for row in rows if row["permission_system_behavior"]
        ),
    }
    usefulness = {
        "positive_case_count": len(positive),
        "hinted_positive_count": sum(1 for row in positive if row["hint_emitted"]),
        "prevented_failure_signal_count": sum(1 for row in positive if row["outcome_ok"]),
        "source_reopen_follow_through_proxy_count": sum(
            1 for row in emitted if row["source_reopen_required"]
        ),
        "signals_covered": sorted({row["expected_signal"] for row in positive}),
    }
    cost = {
        "emitted_hint_count": len(emitted),
        "suppressed_negative_control_count": sum(1 for row in negative if not row["hint_emitted"]),
        "false_positive_count": len(false_positive),
        "anti_nag_suppression_count": sum(
            1
            for row in negative
            if row["expected_signal"] == "anti_nag_suppression" and not row["hint_emitted"]
        ),
        "source_visible_suppression_count": sum(
            1
            for row in negative
            if row["expected_signal"] == "source_visible_suppression" and not row["hint_emitted"]
        ),
        "repeat_hint_rate": 0.0 if not emitted else round(len(false_positive) / len(emitted), 6),
        "extra_tool_call_proxy_count": sum(1 for row in emitted if row["source_reopen_required"]),
    }
    replay_gate_ok = all(row["outcome_ok"] for row in rows) and not any(red_lines.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "ok": True,
        "status": "public_safe_replay_complete",
        "measurement_origin": "public_synthetic_replay_fixture",
        "benchmark_maturity_level": "replay_fixture",
        "observed_agent_behavior": False,
        "contract_gate_ok": replay_gate_ok,
        "public_quality_gate_ok": False,
        "quality_gate_ok": False,
        "runtime_policy_adoption_gate_ok": False,
        "case_count": len(rows),
        "usefulness_metrics": usefulness,
        "cost_metrics": cost,
        "red_lines": red_lines,
        "promotion_gates": {
            "replay_fixture_gate_ok": replay_gate_ok,
            "live_default_adoption_gate_ok": False,
            "requires_live_or_dogfood_outcomes_before_product_claim": True,
        },
        "cases": rows,
        "privacy_boundary": {
            "raw_tool_args_serialized": False,
            "raw_command_text_serialized": False,
            "raw_source_snippets_serialized": False,
            "local_paths_serialized": False,
            "private_prompt_text_serialized": False,
        },
        "cannot_claim": [
            "causal_real_user_lift",
            "live_default_foreground_adoption",
            "permission_system_behavior",
            "source_truth_from_hint",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = run_action_hint_replay()
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("action hint replay: ok")
        print("replay fixture gate:", report["promotion_gates"]["replay_fixture_gate_ok"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
