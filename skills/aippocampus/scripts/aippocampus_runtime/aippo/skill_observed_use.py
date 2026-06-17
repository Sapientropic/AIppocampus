"""Observed-use ripening for skill-derived AIppo seeds."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.aippo import (
    skill_bridge,
    skill_observed_feedback,
    usefulness,
    working_contract,
)
from aippocampus_runtime.core import compact_text

SCHEMA_VERSION = skill_bridge.SCHEMA_VERSION
FOREGROUND_PACKET_BYTE_BUDGET = skill_bridge.FOREGROUND_PACKET_BYTE_BUDGET
TRACE_BACKED_ORIGINS = skill_observed_feedback.TRACE_BACKED_ORIGINS
observed_use_rows_from_foreground_feedback = (
    skill_observed_feedback.observed_use_rows_from_foreground_feedback
)


def _text(value: Any, limit: int = 240) -> str:
    return compact_text(str(value or "").strip(), limit)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "skill"


def _json_bytes(value: Mapping[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _mapping_get_bool(value: Any, key: str) -> bool:
    return bool(value.get(key)) if isinstance(value, Mapping) else False


def _mapping_field(row: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = row.get(key)
    return value if isinstance(value, Mapping) else {}


def _observed_use_priority(clause: Mapping[str, Any]) -> tuple[int, str]:
    guidance = _text(clause.get("guidance"), 320).casefold()
    if guidance.startswith("if no, continue normally"):
        return (-10, str(clause.get("clause_id") or ""))
    score = 0
    if "follow it before broad manual search" in guidance:
        score += 8
    if "consume the smallest useful continuity packet" in guidance:
        score += 4
    for marker in (
        "route",
        "source",
        "packet",
        "deepen",
        "reopen",
        "broad manual search",
        "exact wording",
        "high-risk",
    ):
        if marker in guidance:
            score += 2
    if clause.get("clause_kind") in {"workflow", "boundary", "output_expectation"}:
        score += 1
    return (score, str(clause.get("clause_id") or ""))


def _is_packet_candidate(clause: Mapping[str, Any]) -> bool:
    return bool(_mapping_field(clause, "activation").get("packet_candidate"))


def _observed_use_rows(seed: Mapping[str, Any]) -> list[dict[str, Any]]:
    clauses = [clause for clause in seed.get("clauses", []) if isinstance(clause, Mapping)]
    promotable = sorted(
        [
            clause
            for clause in clauses
            if _is_packet_candidate(clause) and not clause.get("risk_notes")
        ],
        key=_observed_use_priority,
        reverse=True,
    )
    command = next(
        (clause for clause in clauses if clause.get("clause_kind") == "command"),
        promotable[0] if promotable else {},
    )
    rows: list[dict[str, Any]] = []
    for index, clause in enumerate(promotable[:2], start=1):
        rows.append(
            {
                "kind": "aippo_skill_observed_use",
                "activation_id": f"act_skill_seed_observed_{index:03d}",
                "seed_id": seed.get("seed_id"),
                "skill_id": seed.get("skill_id"),
                "clause_id": clause.get("clause_id"),
                "clause_kind": clause.get("clause_kind"),
                "packet_mode": "working_contract_seed",
                "evidence_origin": "synthetic_contract_fixture",
                "agent_action": "used",
                "outcome_signal": "helped",
                "source_support": {
                    "feedback_is_source_backed": True,
                    "self_report_only": False,
                    "source_ref_count": 1,
                },
                "usefulness": {
                    "next_action_was_clear": True,
                    "manual_search_avoided": True,
                    "unnecessary_deepen_avoided": True,
                },
            }
        )
    if command:
        rows.append(
            {
                "kind": "aippo_skill_observed_use",
                "activation_id": "act_skill_seed_corrected_self_report_001",
                "seed_id": seed.get("seed_id"),
                "skill_id": seed.get("skill_id"),
                "clause_id": command.get("clause_id"),
                "clause_kind": command.get("clause_kind"),
                "packet_mode": "working_contract_seed",
                "evidence_origin": "synthetic_contract_fixture",
                "agent_action": "corrected",
                "outcome_signal": "unsupported_or_too_specific",
                "source_support": {
                    "feedback_is_source_backed": False,
                    "self_report_only": True,
                    "source_ref_count": 0,
                },
                "usefulness": {
                    "next_action_was_clear": False,
                    "manual_search_avoided": False,
                    "unnecessary_deepen_avoided": False,
                },
            }
        )
    return rows


def _observed_row_by_clause(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    by_clause: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        clause_id = str(row.get("clause_id") or "")
        if clause_id and clause_id not in by_clause:
            by_clause[clause_id] = row
    return by_clause


def _is_source_backed_observed_use(row: Mapping[str, Any] | None) -> bool:
    if row is None:
        return False
    support = _mapping_field(row, "source_support")
    return (
        row.get("agent_action") == "used"
        and row.get("outcome_signal") == "helped"
        and bool(support.get("feedback_is_source_backed"))
        and not bool(support.get("self_report_only"))
    )


def _skill_clause_source_row(
    seed: Mapping[str, Any],
    clause: Mapping[str, Any],
    observed_row: Mapping[str, Any] | None,
    *,
    built_at: str,
) -> dict[str, Any]:
    clause_id = str(clause.get("clause_id") or "")
    clause_kind = str(clause.get("clause_kind") or "skill_clause")
    source_ref = _text(seed.get("source_ref"), 180)
    ripens = _is_source_backed_observed_use(observed_row) and not clause.get("risk_notes")
    status = "ripe" if ripens else "growing"
    support_grade = "source_supported" if ripens else "candidate_only"
    refs: list[dict[str, Any]] = []
    if ripens:
        observed = observed_row or {}
        support = _mapping_field(observed_row or {}, "source_support")
        feedback_source_ref = _text(
            support.get("source_ref") or observed.get("foreground_feedback_signal"), 180
        )
        refs = [
            {
                "source_ref": f"skill:{seed.get('skill_id')}:SKILL.md",
                "path": source_ref,
                "kind": "skill_instruction_source",
            },
            {
                "source_ref": f"feedback:{observed.get('activation_id') or 'missing'}",
                "path": feedback_source_ref or "foreground_feedback_event",
                "kind": "observed_use_feedback",
            },
        ]
    elif observed_row and (
        observed_row.get("agent_action") == "corrected"
        or _mapping_get_bool(observed_row.get("source_support"), "self_report_only")
    ):
        status = "challenged"

    # A skill declaration is only one source leg. Ripening requires a separate
    # source-backed observed-use row so command lists, self-report corrections,
    # and unsupported broad advice do not silently become AIppo truth.
    return {
        "clause_id": clause_id,
        "kind": clause_kind,
        "guidance": clause.get("guidance"),
        "applies_when": [
            seed.get("declared_need_class") or "continuity_sensitive_work",
            clause_kind,
            "coding",
            "issue_writing",
        ],
        "does_not_apply_when": [
            "exact_quote_or_public_claim_without_source_reopen",
            "private_or_sensitive_claim",
        ],
        "allowed_without_reopen_for": clause.get("allowed_without_reopen_for") or [],
        "requires_reopen_for": [
            "exact_quote",
            "numeric_claim",
            "public_claim",
            "sensitive_or_private",
            "stale_or_conflicted",
            "high_risk_action",
        ],
        "support_grade": support_grade,
        "source_refs": refs,
        "independent_trail_count": 2 if ripens else 0,
        "support_types": (
            ["skill_instruction_source", "observed_use_feedback"]
            if ripens
            else ["skill_declared_candidate"]
        ),
        "path_provenance": "complete" if ripens else "none",
        "review_state": "machine_checked" if ripens else "needs_review",
        "status": status,
        "built_at": built_at,
        "last_source_seen_at": built_at,
        "invalidators": ["newer_skill_revision", "negative_observed_use_feedback"],
    }


def _contract_from_observed_use(
    seed: Mapping[str, Any],
    observed_rows: Sequence[Mapping[str, Any]],
    *,
    built_at: str,
) -> dict[str, Any]:
    by_clause = _observed_row_by_clause(observed_rows)
    source_rows = [
        _skill_clause_source_row(
            seed,
            clause,
            by_clause.get(str(clause.get("clause_id") or "")),
            built_at=built_at,
        )
        for clause in seed.get("clauses", [])
        if isinstance(clause, Mapping)
    ]
    contract = working_contract.select_aippo_working_contract(
        working_contract.build_aippo_working_contracts(source_rows)
    )
    if contract:
        slug = _slug(str(seed.get("skill_id") or "skill"))
        contract["aippo_id"] = f"aippo_skill_{slug}_observed_use_v0"
        contract["source_support_ledger_id"] = f"aippo_skill_{slug}_support_ledger_v0"
        contract["scope"] = {
            "project": "AIppocampus",
            "domain": "skill_observed_use",
            "task_families": ["coding", "review", "issue_writing", "continuity_orientation"],
            "privacy_domain": "public_safe_fixture",
            "transfer": "warn",
        }
        contract["candidate_provenance"] = {
            "seed_id": seed.get("seed_id"),
            "skill_id": seed.get("skill_id"),
            "candidate_input": "candidate_aippo_seed",
            "candidate_inputs_are_truth": False,
        }
    return contract


def _packet_leak_count(packet: Mapping[str, Any], needles: Sequence[str]) -> int:
    encoded = json.dumps(packet, ensure_ascii=False, sort_keys=True)
    return sum(1 for needle in needles if needle in encoded)


def build_skill_observed_use_report(
    markdown: str,
    *,
    skill_id: str | None = None,
    source_ref: str = "skills/aippocampus/SKILL.md",
    declared_need_class: str = "continuity_sensitive_work",
    target_task: str = "coding issue closeout with continuity-sensitive context",
    observed_use_rows: Sequence[Mapping[str, Any]] | None = None,
    foreground_feedback_rows: Sequence[Mapping[str, Any]] | None = None,
    foreground_feedback_path: str | Path | None = None,
    built_at: str = "2026-06-12",
) -> dict[str, Any]:
    seed_report = skill_bridge.build_skill_to_aippo_report(
        markdown,
        skill_id=skill_id,
        source_ref=source_ref,
        declared_need_class=declared_need_class,
    )
    seed = seed_report["seed"]
    loaded_feedback_rows, invalid_feedback_line_count = skill_observed_feedback.load_jsonl_rows(
        foreground_feedback_path
    )
    observed_rows: Sequence[Mapping[str, Any]]
    if observed_use_rows is not None:
        observed_rows_are_synthetic = False
        observed_rows = list(observed_use_rows)
        observed_use_ingestion = {
            "source": "explicit_observed_use_rows",
            "foreground_feedback_row_count": 0,
            "invalid_feedback_line_count": invalid_feedback_line_count,
        }
    elif foreground_feedback_rows is not None or foreground_feedback_path:
        all_feedback_rows = [
            *(foreground_feedback_rows or []),
            *loaded_feedback_rows,
        ]
        observed_rows_are_synthetic = False
        observed_rows = skill_observed_feedback.observed_use_rows_from_foreground_feedback(
            seed,
            all_feedback_rows,
        )
        observed_use_ingestion = {
            "source": "foreground_feedback",
            "foreground_feedback_row_count": len(all_feedback_rows),
            "invalid_feedback_line_count": invalid_feedback_line_count,
            "observed_use_row_count": len(observed_rows),
        }
    else:
        observed_rows_are_synthetic = True
        observed_rows = _observed_use_rows(seed)
        observed_use_ingestion = {
            "source": "synthetic_contract_fixture",
            "foreground_feedback_row_count": 0,
            "invalid_feedback_line_count": invalid_feedback_line_count,
        }
    contract = _contract_from_observed_use(seed, observed_rows, built_at=built_at)
    packet = working_contract.activation_packet_from_working_contract(
        contract,
        task=target_task,
        max_packet_bytes=FOREGROUND_PACKET_BYTE_BUDGET,
    )
    deepen = working_contract.deepen_aippo_working_contract(contract)
    explain = working_contract.explain_aippo_working_contract(contract)
    usefulness_metrics = usefulness.usefulness_metrics(contract, packet)
    clauses = [clause for clause in contract.get("clauses") or [] if isinstance(clause, Mapping)]
    active_ids = {str(item) for item in packet.get("active_clause_ids") or []}
    observed_by_clause = _observed_row_by_clause(observed_rows)
    promotable_ids = {
        str(row.get("clause_id")) for row in observed_rows if _is_source_backed_observed_use(row)
    }
    source_backed_ids = {
        str(clause.get("clause_id"))
        for clause in clauses
        if _mapping_field(clause, "support").get("support_grade") == "source_supported"
    }
    candidate_only_ids = {
        str(clause.get("clause_id"))
        for clause in clauses
        if _mapping_field(clause, "support").get("support_grade") != "source_supported"
    }
    self_report_ids = {
        str(row.get("clause_id"))
        for row in observed_rows
        if _mapping_get_bool(row.get("source_support"), "self_report_only")
    }
    risk_clause_ids = {
        str(clause.get("clause_id"))
        for clause in seed.get("clauses", [])
        if isinstance(clause, Mapping) and clause.get("risk_notes")
    }
    packet_bytes = _json_bytes(packet)
    synthetic_observed_use_count = sum(
        1
        for row in observed_rows
        if str(row.get("evidence_origin") or "") == "synthetic_contract_fixture"
    )
    trace_backed_observed_use_count = sum(
        1
        for row in observed_rows
        if str(row.get("evidence_origin") or "") in {"trace_backed", "replay_backed"}
    )
    trace_backed_positive_observed_use_count = sum(
        1
        for row in observed_rows
        if str(row.get("evidence_origin") or "") in TRACE_BACKED_ORIGINS
        and row.get("agent_action") == "used"
        and row.get("outcome_signal") == "helped"
    )
    trace_backed_no_help_observed_use_count = sum(
        1
        for row in observed_rows
        if str(row.get("evidence_origin") or "") in TRACE_BACKED_ORIGINS
        and row.get("outcome_signal") == "unsupported_or_too_specific"
    )
    contract_smoke_gate_ok = bool(usefulness_metrics["usefulness_gate_ok"])
    product_usefulness_gate_ok = bool(
        usefulness_metrics["usefulness_gate_ok"]
        and trace_backed_observed_use_count > 0
        and not observed_rows_are_synthetic
    )
    red_lines = {
        "skill_instruction_promoted_without_observed_use_count": len(
            source_backed_ids - promotable_ids
        ),
        "self_report_promoted_to_source_supported_count": len(
            source_backed_ids & self_report_ids
        ),
        "overbroad_declared_clause_ripened_count": len(source_backed_ids & risk_clause_ids),
        "command_or_reference_foreground_leak_count": _packet_leak_count(
            packet,
            ["aippocampus ", "python -m ", "references/", "skills/aippocampus/"],
        ),
        "source_trail_foreground_leak_count": _packet_leak_count(
            packet,
            ["source_refs", "source_support_ledger", "fixtures/aippo/"],
        ),
        "raw_skill_text_dumped_to_foreground_count": _packet_leak_count(
            packet,
            ["Useful portable commands", "Hook, Storage, And Safety Boundaries"],
        ),
        "private_skill_imported_to_public_report_count": int("private/" in source_ref),
    }
    return {
        "kind": "aippocampus_skill_observed_use_ripening_report",
        "schema_version": SCHEMA_VERSION,
        "status": (
            "trace_backed_usefulness_candidate"
            if product_usefulness_gate_ok
            else "contract_smoke_only"
        ),
        "seed": seed,
        "observed_use_rows": observed_rows,
        "observed_use_ingestion": observed_use_ingestion,
        "ripened_contract": contract,
        "activation_packet": packet,
        "deepen_surface": deepen,
        "explain_surface": explain,
        "eval_candidacy": seed_report["eval_candidacy"],
        "metrics": {
            "skill_to_aippo_seed_count": 1,
            "skill_clause_extraction_count": len(seed.get("clauses") or []),
            "skill_clause_ripening_candidate_count": len(promotable_ids),
            "skill_clause_ripened_count": len(source_backed_ids),
            "source_backed_clause_count": len(source_backed_ids),
            "candidate_only_clause_count": len(candidate_only_ids),
            "activation_packet_bytes": packet_bytes,
            "raw_seed_packet_bytes": _json_bytes(seed_report["activation_packet"]),
            "activation_packet_smaller_than_raw_skill": packet_bytes
            < int(seed_report["metrics"]["raw_skill_bytes"]),
            "next_action_clarity_count": sum(
                1
                for clause_id in active_ids
                if _mapping_get_bool(
                    (observed_by_clause.get(clause_id) or {}).get("usefulness"),
                    "next_action_was_clear",
                )
            ),
            "unnecessary_command_foreground_count": sum(
                1
                for clause in clauses
                if clause.get("kind") == "command" and clause.get("clause_id") in active_ids
            ),
            "unnecessary_deepen_suppression_count": sum(
                1
                for clause_id in active_ids
                if _mapping_get_bool(
                    (observed_by_clause.get(clause_id) or {}).get("usefulness"),
                    "unnecessary_deepen_avoided",
                )
            ),
            "stable_workflow_search_avoided_count": usefulness_metrics[
                "stable_workflow_search_avoided_count"
            ],
            "trace_backed_observed_use_count": trace_backed_observed_use_count,
            "trace_backed_positive_observed_use_count": trace_backed_positive_observed_use_count,
            "trace_backed_no_help_observed_use_count": trace_backed_no_help_observed_use_count,
            "synthetic_observed_use_count": synthetic_observed_use_count,
            "manual_search_observed_delta": (
                usefulness_metrics["stable_workflow_search_avoided_count"]
                if product_usefulness_gate_ok
                else 0
            ),
            "next_action_selection_delta": (
                usefulness_metrics["aippo_next_action_delta_count"]
                if product_usefulness_gate_ok
                else 0
            ),
            "generic_safety_posture_only_count": usefulness_metrics[
                "generic_safety_posture_only_count"
            ],
            "aippo_next_action_delta_count": usefulness_metrics["aippo_next_action_delta_count"],
            "contract_smoke_gate_ok": contract_smoke_gate_ok,
            "usefulness_gate_ok": product_usefulness_gate_ok,
            "synthetic_rows_count_as_product_usefulness": False,
        },
        "red_lines": red_lines,
        "cannot_claim": [
            "automatic_conversion_of_arbitrary_skills_into_ripe_aippos",
            "proof_that_the_skill_is_generally_useful",
            "private_skill_generalization",
            "skill_marketplace_readiness",
            "eval_environments_as_default_cost_for_every_skill",
            *(
                ["product_quality_ripening_from_synthetic_observed_use_rows"]
                if synthetic_observed_use_count or observed_rows_are_synthetic
                else []
            ),
        ],
        "ok": all(value == 0 for value in red_lines.values())
        and packet_bytes <= FOREGROUND_PACKET_BYTE_BUDGET
        and contract_smoke_gate_ok,
    }


def build_skill_observed_use_fixture_report(
    skill_path: str | Path,
    *,
    target_task: str = "coding issue closeout with continuity-sensitive context",
) -> dict[str, Any]:
    path = Path(skill_path)
    normalized = path.as_posix()
    source_ref = (
        "skills/aippocampus/" + normalized.split("skills/aippocampus/", 1)[1]
        if "skills/aippocampus/" in normalized
        else normalized
    )
    return build_skill_observed_use_report(
        path.read_text(encoding="utf-8"),
        source_ref=source_ref,
        target_task=target_task,
    )


__all__ = [
    "build_skill_observed_use_fixture_report",
    "build_skill_observed_use_report",
    "observed_use_rows_from_foreground_feedback",
]
