#!/usr/bin/env python3
"""Public-safe worker-to-hook handoff diagnostic.

This smoke exercises the existing prompt hook and ambient cache path. It does
not introduce a new memory surface: worker/prewarm artifacts remain navigation
material until the foreground hook either reports why they are unusable or
reopens clean source into bounded evidence.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from aippocampus_runtime.hooks import prompt as prompt_hook
from aippocampus_runtime.recall import ambient_cache

KIND = "aippocampus_worker_hook_handoff_smoke"
SCHEMA_VERSION = 1
ROUTE_GRAMMARS = {"direction_with_ref", "reopenable_route", "bounded_evidence", "source_open"}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_fixture_registry(root: Path) -> Path:
    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    messages = root / "clean-source" / "messages.jsonl"
    _write_jsonl(
        messages,
        [
            {
                "message_id": "msg-worker-route",
                "turn_id": "turn-worker-route",
                "source_line": 42,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 1,
                "is_final": True,
                "text": (
                    "Clean source says a current worker route can be reopened "
                    "deterministically before foreground use."
                ),
            }
        ],
    )
    registry_path = root / "registry" / "threads.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "threads": [
                    {
                        "thread_key": "session:worker-route",
                        "title": "Continuity route source",
                        "workspace_name": "AIppocampus",
                        "project_label": "AIppocampus",
                        "keywords": ["clean source route"],
                        "summary": "Fixture source for worker handoff source reopen.",
                        "paths": {
                            "workspace": str(workspace),
                            "clean_source_messages_jsonl": str(messages),
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return registry_path


def _worker_source_ref() -> dict[str, Any]:
    return {
        "thread_key": "session:worker-route",
        "title": "Continuity route source",
        "message_id": "msg-worker-route",
        "line": 42,
    }


def _write_case_cache(
    cache_path: Path,
    *,
    case_id: str,
    workspace: Path,
    card: dict[str, Any],
) -> None:
    ambient_cache.write_thread_cache(
        cache_path,
        thread_id=f"thread-{case_id}",
        workspace=str(workspace),
        topic_epoch=f"epoch-{case_id}",
        cards=[card],
        mode=str(card.get("visibility") or "active_gentle_nudge"),
        confidence="medium",
        query_aliases=["worker hook handoff"],
        visibility_bias=str(card.get("visibility") or "active_gentle_nudge"),
    )


def _run_hook_case(
    *,
    case_id: str,
    root: Path,
    registry_path: Path,
    cache_path: Path,
) -> dict[str, Any]:
    workspace = root / "workspace"
    return prompt_hook.assess_prompt(
        "继续这个后台交接",
        cwd=workspace,
        registry_path=registry_path,
        thread_id=f"thread-{case_id}",
        topic_epoch=f"epoch-{case_id}",
        ambient_cache_path=cache_path,
        warm_background=False,
        search_budget=0,
        use_semantic_gate=False,
        use_cognitive_map=False,
        use_concept_graph=False,
    )


def _action_grammars(cards: list[dict[str, Any]]) -> list[str]:
    return [
        str(card.get("action_grammar") or "")
        for card in cards
        if isinstance(card, dict) and card.get("action_grammar")
    ]


def _manual_query_expected(cards: list[dict[str, Any]]) -> bool:
    for card in cards:
        contract = card.get("trust_contract") if isinstance(card, dict) else {}
        if isinstance(contract, dict) and contract.get("manual_query_invention_expected"):
            return True
    return False


def _suppression_reasons(
    *,
    worker_candidate_available: bool,
    cards: list[dict[str, Any]],
    source_reopen: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if not worker_candidate_available:
        return ["no_worker_artifact_available"]
    if any(str(card.get("action_grammar") or "") == "ignore_or_blocked" for card in cards):
        reasons.append("stale_or_blocked_worker_candidate")
    for card in cards:
        currentness = str(card.get("currentness") or card.get("freshness") or "").casefold()
        visibility = str(card.get("visibility") or "").casefold()
        if currentness in {"stale", "superseded"}:
            reasons.append("stale_worker_candidate")
        if visibility == "blocked":
            reasons.append("blocked_worker_candidate")
    for code, count in (source_reopen.get("failure_reason_counts") or {}).items():
        if count:
            reasons.append(str(code))
    if not reasons and not any(grammar in ROUTE_GRAMMARS for grammar in _action_grammars(cards)):
        reasons.append("plain_scent_after_worker_hit")
    return sorted(set(reasons))


def _case_report(case_id: str, result: dict[str, Any]) -> dict[str, Any]:
    ambient = _as_dict(result.get("ambient_recall"))
    cards = [card for card in ambient.get("cards") or [] if isinstance(card, dict)]
    cache_status = _as_dict(ambient.get("cache_status"))
    source_reopen = _as_dict(ambient.get("source_reopen"))
    grammars = _action_grammars(cards)
    worker_candidate_available = str(cache_status.get("status") or "") in {"hit", "related_hit"} and int(
        cache_status.get("card_count") or 0
    ) > 0
    foreground_route = any(grammar in ROUTE_GRAMMARS for grammar in grammars)
    hook_payload = prompt_hook.hook_stdout_payload(result)
    suppression_reasons = _suppression_reasons(
        worker_candidate_available=worker_candidate_available,
        cards=cards,
        source_reopen=source_reopen,
    )
    return {
        "case_id": case_id,
        "decision": result.get("decision"),
        "worker_candidate_available": worker_candidate_available,
        "hook_context_available": bool(hook_payload),
        "foreground_route_emitted": foreground_route and bool(hook_payload),
        "action_grammars": grammars,
        "card_count": len(cards),
        "cache_status": {
            "status": cache_status.get("status"),
            "card_count": int(cache_status.get("card_count") or 0),
        },
        "source_reopen": {
            "attempted_count": int(source_reopen.get("attempted_count") or 0),
            "success_count": int(source_reopen.get("success_count") or 0),
            "failure_count": int(source_reopen.get("failure_count") or 0),
            "failure_reason_counts": source_reopen.get("failure_reason_counts") or {},
        },
        "source_reopen_plan_emitted": bool(
            source_reopen.get("attempted_count")
            or any(card.get("source_refs") for card in cards)
        ),
        "bounded_evidence_after_worker_route": "bounded_evidence" in grammars and bool(hook_payload),
        "manual_query_invention_expected": _manual_query_expected(cards),
        "suppression_reasons": suppression_reasons,
    }


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    worker_cases = [case for case in cases if case["worker_candidate_available"]]
    route_cases = [case for case in worker_cases if case["foreground_route_emitted"]]
    bounded_cases = [case for case in worker_cases if case["bounded_evidence_after_worker_route"]]
    reasons: dict[str, int] = {}
    for case in cases:
        for reason in case["suppression_reasons"]:
            reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "case_count": len(cases),
        "worker_candidate_available_count": len(worker_cases),
        "worker_candidate_to_foreground_route_count": len(route_cases),
        "worker_candidate_to_foreground_route_rate": _rate(len(route_cases), len(worker_cases)),
        "plain_scent_after_worker_hit_count": reasons.get("plain_scent_after_worker_hit", 0),
        "manual_search_after_worker_hint_count": len(
            [case for case in worker_cases if case["manual_query_invention_expected"]]
        ),
        "source_reopen_plan_emitted_count": len(
            [case for case in cases if case["source_reopen_plan_emitted"]]
        ),
        "bounded_evidence_after_worker_route_count": len(bounded_cases),
        "bounded_evidence_after_worker_route_rate": _rate(len(bounded_cases), len(worker_cases)),
        "stale_or_blocked_worker_candidate_count": len(
            [
                case
                for case in worker_cases
                if "stale_or_blocked_worker_candidate" in case["suppression_reasons"]
            ]
        ),
        "foreground_suppression_reason_breakdown": reasons,
    }


def _ok(cases_by_id: dict[str, dict[str, Any]]) -> bool:
    no_worker = cases_by_id["no_worker_artifact"]
    blocked = cases_by_id["blocked_worker_artifact"]
    ready = cases_by_id["ready_worker_artifact"]
    return bool(
        not no_worker["worker_candidate_available"]
        and not no_worker["foreground_route_emitted"]
        and blocked["worker_candidate_available"]
        and not blocked["foreground_route_emitted"]
        and "stale_or_blocked_worker_candidate" in blocked["suppression_reasons"]
        and ready["worker_candidate_available"]
        and ready["foreground_route_emitted"]
        and ready["bounded_evidence_after_worker_route"]
        and not ready["manual_query_invention_expected"]
    )


def build_worker_hook_handoff_smoke() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        registry_path = _write_fixture_registry(root)
        workspace = root / "workspace"
        blocked_cache = root / "blocked-cache.json"
        ready_cache = root / "ready-cache.json"
        _write_case_cache(
            blocked_cache,
            case_id="blocked_worker_artifact",
            workspace=workspace,
            card={
                "card_id": "blocked-worker-card",
                "theme": "Blocked worker candidate",
                "support_level": "candidate",
                "visibility": "blocked",
                "freshness": "stale",
                "provenance_class": "warm_scout_proposal",
                "source_validation": {"status": "unsupported"},
                "source_refs": [_worker_source_ref()],
            },
        )
        _write_case_cache(
            ready_cache,
            case_id="ready_worker_artifact",
            workspace=workspace,
            card={
                "card_id": "ready-worker-card",
                "theme": "Ready worker source route",
                "support_level": "evidence",
                "visibility": "source_backed_recall_card",
                "provenance_class": "source_backed_reopen",
                "source_validation": {"status": "supported", "checked_ref_count": 1},
                "source_refs": [_worker_source_ref()],
            },
        )
        case_results = {
            "no_worker_artifact": _run_hook_case(
                case_id="no_worker_artifact",
                root=root,
                registry_path=registry_path,
                cache_path=root / "missing-cache.json",
            ),
            "blocked_worker_artifact": _run_hook_case(
                case_id="blocked_worker_artifact",
                root=root,
                registry_path=registry_path,
                cache_path=blocked_cache,
            ),
            "ready_worker_artifact": _run_hook_case(
                case_id="ready_worker_artifact",
                root=root,
                registry_path=registry_path,
                cache_path=ready_cache,
            ),
        }
        cases = [_case_report(case_id, result) for case_id, result in case_results.items()]
    cases_by_id = {case["case_id"]: case for case in cases}
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": _ok(cases_by_id),
        "issue_readout": {
            "github_issue": 909,
            "claim_level": "public_safe_deterministic_handoff_fixture",
            "live_second_user_quality": "not_measured",
        },
        "metrics": _metrics(cases),
        "cases": cases,
        "cases_by_id": cases_by_id,
        "contract": {
            "worker_output_is_not_source_truth": True,
            "plain_scent_is_not_evidence": True,
            "bounded_evidence_requires_clean_source_reopen": True,
            "blocked_or_stale_worker_candidates_stay_non_actionable": True,
            "raw_prompt_text_serialized": False,
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
        },
        "can_claim": [
            "worker_to_hook_handoff_fixture_exists",
            "ready_cached_worker_route_reaches_foreground_after_source_reopen",
            "blocked_or_stale_worker_artifact_reports_suppression_reason",
            "no_artifact_arm_does_not_fake_a_worker_route",
        ],
        "cannot_claim": [
            "live_second_user_hook_helpfulness",
            "background_worker_quality",
            "default_prewarm_roi_lift",
        ],
    }


def render_text(report: dict[str, Any]) -> str:
    metrics = _as_dict(report.get("metrics"))
    lines = [
        "AIppocampus worker-to-hook handoff smoke",
        f"ok: {bool(report.get('ok'))}",
        f"worker candidates: {metrics.get('worker_candidate_available_count', 0)}",
        f"foreground route rate: {metrics.get('worker_candidate_to_foreground_route_rate', 0.0)}",
        f"plain scent after worker hit: {metrics.get('plain_scent_after_worker_hit_count', 0)}",
        f"bounded evidence after worker route: {metrics.get('bounded_evidence_after_worker_route_count', 0)}",
    ]
    for case in report.get("cases") or []:
        lines.append(
            "- {case_id}: worker={worker} context={context} route={route} reasons={reasons}".format(
                case_id=case.get("case_id"),
                worker=case.get("worker_candidate_available"),
                context=case.get("hook_context_available"),
                route=case.get("foreground_route_emitted"),
                reasons=",".join(case.get("suppression_reasons") or []),
            )
        )
    return "\n".join(lines) + "\n"
