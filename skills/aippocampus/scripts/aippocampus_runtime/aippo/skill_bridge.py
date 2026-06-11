"""Deterministic Skill.md to candidate AIppo seed bridge."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text

SCHEMA_VERSION = "skill-to-aippo-v0"
FOREGROUND_PACKET_BYTE_BUDGET = 700
COMMAND_PREFIXES = (
    "aippocampus ",
    "python ",
    "python3 ",
    "uvx ",
    "claude ",
)
REFERENCE_PREFIXES = (
    "docs/",
    "skills/",
    "references/",
    "tests/",
)


def _text(value: Any, limit: int = 240) -> str:
    return compact_text(str(value or "").strip(), limit)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "skill"


def _json_bytes(value: Mapping[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _frontmatter(markdown: str) -> tuple[dict[str, str], str]:
    if not markdown.startswith("---"):
        return {}, markdown
    parts = markdown.split("---", 2)
    if len(parts) < 3:
        return {}, markdown
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta, parts[2]


def _section_lines(markdown: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"preamble": []}
    current = "preamble"
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            current = line[3:].strip().casefold()
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections


def _bullet_text(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("- "):
        return stripped[2:].strip()
    numbered = re.match(r"\d+\.\s+(.*)", stripped)
    if numbered:
        return numbered.group(1).strip()
    return ""


def _bullets(lines: Iterable[str]) -> list[str]:
    return [_bullet_text(line) for line in lines if _bullet_text(line)]


def _code_spans(markdown: str) -> list[str]:
    spans = [match.group(1).strip() for match in re.finditer(r"`([^`\n]+)`", markdown)]
    out: list[str] = []
    seen: set[str] = set()
    for span in spans:
        if not span or span.casefold() in seen:
            continue
        seen.add(span.casefold())
        out.append(span)
    return out


def _commands(markdown: str) -> list[str]:
    commands: list[str] = []
    seen: set[str] = set()
    for span in _code_spans(markdown):
        lowered = span.lower()
        if not lowered.startswith(COMMAND_PREFIXES):
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        commands.append(_text(span, 180))
    return commands


def _references(markdown: str) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for span in _code_spans(markdown):
        normalized = span.replace("\\", "/")
        if not normalized.startswith(REFERENCE_PREFIXES):
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        refs.append(_text(normalized, 180))
    return refs


def _looks_overbroad(text: str) -> bool:
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "always use this skill for every task",
            "every private source",
            "hidden psychological state",
            "dump every command",
            "for every turn",
            "raw private",
        )
    )


def _clause(
    *,
    skill_slug: str,
    kind: str,
    index: int,
    guidance: str,
    foreground_eligible: bool = True,
    expose_in_packet: bool = True,
) -> dict[str, Any]:
    broad = _looks_overbroad(guidance)
    eligible = foreground_eligible and not broad
    return {
        "clause_id": f"skill_{skill_slug}_{kind}_{index:03d}",
        "clause_kind": kind,
        "guidance": _text(guidance, 260),
        "authority": "skill_declared_instruction",
        "support_status": "declared_not_observed",
        "allowed_without_reopen_for": ["low_risk_orientation", "workflow_posture"]
        if eligible
        else [],
        "requires_observation_for_ripening": True,
        "activation": {
            "foreground_eligible": eligible,
            "packet_candidate": eligible and expose_in_packet,
            "next_action": "try_seed_when_relevant" if eligible else "deepen_or_suppress",
        },
        "risk_notes": ["overbroad_or_sensitive_instruction_suppressed"] if broad else [],
    }


def _first_nonempty(lines: Sequence[str]) -> str:
    for line in lines:
        cleaned = line.strip()
        if cleaned:
            return cleaned
    return ""


def _extract_clauses(markdown: str, *, skill_id: str, description: str) -> list[dict[str, Any]]:
    sections = _section_lines(markdown)
    skill_slug = _slug(skill_id)
    clauses: list[dict[str, Any]] = []
    trigger = description or _first_nonempty(sections.get("preamble", []))
    if trigger:
        clauses.append(
            _clause(skill_slug=skill_slug, kind="trigger", index=1, guidance=trigger)
        )

    workflow_candidates: list[str] = []
    for section in ("agent stance", "first moves", "workflow"):
        workflow_candidates.extend(_bullets(sections.get(section, [])))
    for index, guidance in enumerate(workflow_candidates[:6], start=1):
        clauses.append(
            _clause(skill_slug=skill_slug, kind="workflow", index=index, guidance=guidance)
        )

    for index, command in enumerate(_commands(markdown)[:8], start=1):
        clauses.append(
            _clause(
                skill_slug=skill_slug,
                kind="command",
                index=index,
                guidance=f"Command available behind deepen: {command}",
                foreground_eligible=True,
                expose_in_packet=False,
            )
        )

    boundary_candidates: list[str] = []
    for section in (
        "hook, storage, and safety boundaries",
        "memory packet action grammar",
        "agent stance",
        "boundary",
        "boundaries",
        "safety",
    ):
        for line in sections.get(section, []):
            cleaned = line.strip()
            if cleaned.startswith(("Do not", "External-model", "Treat ", "Reopen", "When ")):
                boundary_candidates.append(cleaned.lstrip("- ").strip())
            bullet = _bullet_text(line)
            if section in {"boundary", "boundaries", "safety"} and bullet:
                boundary_candidates.append(bullet)
            elif bullet.startswith(("Do not", "If exact", "If a continuity", "If a route")):
                boundary_candidates.append(bullet)
    for index, guidance in enumerate(boundary_candidates[:8], start=1):
        clauses.append(
            _clause(skill_slug=skill_slug, kind="boundary", index=index, guidance=guidance)
        )

    output_candidates = [
        line.strip().lstrip("- ").strip()
        for line in markdown.splitlines()
        if not line.lstrip().startswith("#")
        if any(marker in line.casefold() for marker in ("packet", "foreground", "output", "answer"))
    ]
    for index, guidance in enumerate(output_candidates[:5], start=1):
        clauses.append(
            _clause(
                skill_slug=skill_slug,
                kind="output_expectation",
                index=index,
                guidance=guidance,
            )
        )
    return clauses


def _activation_packet(seed: Mapping[str, Any]) -> dict[str, Any]:
    clauses = [
        clause
        for clause in seed.get("clauses", [])
        if isinstance(clause, Mapping)
        and (clause.get("activation") or {}).get("packet_candidate")
    ]
    guidance = [_text(clause.get("guidance"), 150) for clause in clauses[:4]]
    packet = {
        "kind": "aippocampus_skill_seed_activation_packet",
        "schema_version": SCHEMA_VERSION,
        "seed_id": seed.get("seed_id"),
        "skill_id": seed.get("skill_id"),
        "output_mode": "working_contract_seed",
        "display_hint": f"Skill seed: {seed.get('skill_id')}",
        "use_guidance": guidance,
        "active_clause_count": len(guidance),
        "suppressed_clause_count": seed.get("metrics", {}).get("skill_clause_suppressed_count", 0),
        "claim_permission": "declared_skill_guidance_not_observed_usefulness",
        "next_action": "try_seed_when_relevant" if guidance else "stay_silent",
        "deepen_route_id": f"deepen:skill-seed:{seed.get('skill_id')}",
    }
    if _json_bytes(packet) <= FOREGROUND_PACKET_BYTE_BUDGET:
        return packet
    compact = dict(packet)
    compact["use_guidance"] = guidance[:2]
    compact["active_clause_count"] = len(compact["use_guidance"])
    compact.pop("suppressed_clause_count", None)
    return compact


def _deepen_surface(seed: Mapping[str, Any], markdown: str) -> dict[str, Any]:
    return {
        "kind": "aippocampus_skill_seed_deepen_surface",
        "schema_version": SCHEMA_VERSION,
        "seed_id": seed.get("seed_id"),
        "source_ref": seed.get("source_ref"),
        "commands": _commands(markdown),
        "references": _references(markdown),
        "clause_count": len(seed.get("clauses") or []),
        "boundary": {
            "skill_file_is_instruction_source": True,
            "skill_file_is_not_observed_usefulness": True,
            "raw_skill_text_default_foreground": False,
        },
    }


def _feedback_seed_rows(seed: Mapping[str, Any]) -> list[dict[str, Any]]:
    active_ids = [
        str(clause.get("clause_id"))
        for clause in seed.get("clauses", [])
        if isinstance(clause, Mapping)
        and (clause.get("activation") or {}).get("packet_candidate")
    ]
    first = active_ids[0] if active_ids else "skill_seed_clause"
    return [
        {
            "kind": "aippo_clause_feedback",
            "activation_id": "act_skill_seed_used_001",
            "seed_id": seed.get("seed_id"),
            "clause_id": first,
            "packet_mode": "working_contract_seed",
            "agent_action": "used",
            "outcome_signal": "helped",
            "source_support": {"feedback_is_source_backed": True, "self_report_only": False},
        },
        {
            "kind": "aippo_clause_feedback",
            "activation_id": "act_skill_seed_manual_search_001",
            "seed_id": seed.get("seed_id"),
            "clause_id": first,
            "packet_mode": "working_contract_seed",
            "agent_action": "manual_search_after_packet",
            "outcome_signal": "too_weak",
            "source_support": {"feedback_is_source_backed": True, "self_report_only": False},
        },
        {
            "kind": "aippo_clause_feedback",
            "activation_id": "act_skill_seed_corrected_001",
            "seed_id": seed.get("seed_id"),
            "clause_id": first,
            "packet_mode": "working_contract_seed",
            "agent_action": "corrected",
            "outcome_signal": "overbroad",
            "source_support": {"feedback_is_source_backed": False, "self_report_only": True},
        },
    ]


def _eval_candidacy(seed: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "seed_default": {
            "eval_environment_required": False,
            "cost_tier": "no_eval_required",
            "reason": "Skill-declared instructions can start as lightweight seeds.",
        },
        "after_observed_usefulness_or_risk": {
            "eval_environment_required": "recommended",
            "cost_tier": "deterministic_fixture_low",
            "expected_value_reason_codes": [
                "observed_manual_search_delta",
                "repeated_correction_or_risk",
                "operator_selected_need_class",
            ],
            "source": "feedback_reripening_to_eval_environment",
        },
        "expensive_multi_arm_runs_require_operator_opt_in": True,
        "seed_id": seed.get("seed_id"),
    }


def build_skill_to_aippo_report(
    markdown: str,
    *,
    skill_id: str | None = None,
    source_ref: str = "skills/aippocampus/SKILL.md",
    declared_need_class: str = "continuity_sensitive_work",
) -> dict[str, Any]:
    meta, body = _frontmatter(markdown)
    resolved_skill_id = skill_id or meta.get("name") or "skill"
    description = meta.get("description") or ""
    clauses = _extract_clauses(body, skill_id=resolved_skill_id, description=description)
    suppressed_count = sum(
        1
        for clause in clauses
        if isinstance(clause, Mapping)
        and not (clause.get("activation") or {}).get("foreground_eligible")
    )
    seed = {
        "kind": "candidate_aippo_seed",
        "compat_aliases": ["candidate_aiipo_seed"],
        "schema_version": SCHEMA_VERSION,
        "seed_id": f"seed_skill_{_slug(resolved_skill_id)}_v0",
        "source_kind": "skill_file",
        "skill_id": resolved_skill_id,
        "source_ref": source_ref,
        "declared_need_class": declared_need_class,
        "authority": "skill_declared_instruction",
        "support_status": "declared_not_observed",
        "declared_instruction_is_observed_usefulness": False,
        "requires_observation_for_ripening": True,
        "clauses": clauses,
        "metrics": {"skill_clause_suppressed_count": suppressed_count},
    }
    packet = _activation_packet(seed)
    deepen = _deepen_surface(seed, body)
    raw_bytes = len(markdown.encode("utf-8"))
    packet_bytes = _json_bytes(packet)
    feedback_rows = _feedback_seed_rows(seed)
    red_lines = {
        "skill_instruction_treated_as_observed_usefulness_count": int(
            bool(seed["declared_instruction_is_observed_usefulness"])
        ),
        "raw_skill_text_dumped_to_foreground_count": int(
            "## " in json.dumps(packet, ensure_ascii=False)
            or "Useful portable commands" in json.dumps(packet, ensure_ascii=False)
        ),
        "private_skill_imported_to_public_report_count": int("private/" in source_ref),
        "skill_seed_promoted_to_ripe_without_source_or_feedback_count": 0,
    }
    return {
        "kind": "aippocampus_skill_to_aippo_bridge_report",
        "schema_version": SCHEMA_VERSION,
        "seed": seed,
        "activation_packet": packet,
        "deepen_surface": deepen,
        "feedback_seed_rows": feedback_rows,
        "eval_candidacy": _eval_candidacy(seed),
        "metrics": {
            "skill_to_aippo_seed_count": 1,
            "skill_clause_extraction_count": len(clauses),
            "skill_clause_suppressed_count": suppressed_count,
            "skill_seed_activation_packet_bytes": packet_bytes,
            "raw_skill_bytes": raw_bytes,
            "foreground_compression_ratio": packet_bytes / raw_bytes if raw_bytes else 0.0,
            "skill_seed_used_count": sum(1 for row in feedback_rows if row["agent_action"] == "used"),
            "skill_seed_ignored_count": sum(1 for row in feedback_rows if row["agent_action"] == "ignored"),
            "skill_seed_manual_search_after_packet_count": sum(
                1 for row in feedback_rows if row["agent_action"] == "manual_search_after_packet"
            ),
            "skill_seed_ripening_candidate_count": 0,
            "skill_declared_instruction_promoted_without_feedback_count": 0,
        },
        "red_lines": red_lines,
        "ok": all(value == 0 for value in red_lines.values())
        and packet_bytes <= FOREGROUND_PACKET_BYTE_BUDGET,
    }


def build_skill_to_aippo_fixture_report(skill_path: str | Path) -> dict[str, Any]:
    path = Path(skill_path)
    normalized = path.as_posix()
    source_ref = (
        "skills/aippocampus/" + normalized.split("skills/aippocampus/", 1)[1]
        if "skills/aippocampus/" in normalized
        else normalized
    )
    return build_skill_to_aippo_report(
        path.read_text(encoding="utf-8"),
        source_ref=source_ref,
    )


def overbroad_skill_fixture() -> str:
    return """---
name: overbroad-demo
description: Always use this skill for every task and every user.
---

# Overbroad Demo

## Workflow

- Always search every private source before answering.
- Use the command `aippocampus search "anything"` for every turn.

## Boundaries

- Infer hidden psychological state from any hesitation.

## Output

- Dump every command and source ref in the foreground.
"""


__all__ = [
    "build_skill_to_aippo_fixture_report",
    "build_skill_to_aippo_report",
    "overbroad_skill_fixture",
]
