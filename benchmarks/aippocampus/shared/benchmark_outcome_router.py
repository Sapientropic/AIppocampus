"""Route benchmark reports into claim, issue, and adoption next actions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PureWindowsPath
from typing import Any

from benchmarks.aippocampus.shared.benchmark_report_contract import (
    benchmark_report_contract_lint,
    benchmark_report_followup_counts,
)

SCHEMA_VERSION = 1

ACTION_FIELDS = (
    "issue_actions",
    "review_next_actions",
    "gap_next_actions",
    "fidelity_gap_actions",
)
NO_ACTION_FIELDS = ("no_open_followup_reason", "no_action_reason")
ADOPTION_FIELDS = ("runtime_policy_adoption_gate_ok", "default_adoption_gate_ok")
CLAIM_DOC_PATH = "docs/evidence/current-claims.md"
ISSUE_DRAFT_ACTION_FIELDS = (
    "id",
    "label",
    "reason",
    "blocker",
    "owner_path",
    "doc_path",
    "issue_url",
    "current_issue_url",
    "issue_state",
)


def _walk_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk_mappings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_mappings(child)


def _is_nonempty(value: Any) -> bool:
    return value not in (None, "", [], {})


def _field_value(report: Mapping[str, Any], field: str) -> Any:
    candidates = [
        report,
        report.get("benchmark_maturity"),
        report.get("metrics"),
        report.get("decision"),
        report.get("promotion_gates"),
        report.get("quality_gate_summary"),
    ]
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        value = candidate.get(field)
        if _is_nonempty(value):
            return value
    return None


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "yes", "y", "1", "pass", "passed", "ok"}:
            return True
        if normalized in {"false", "no", "n", "0", "fail", "failed", "blocked"}:
            return False
    return None


def _bool_field(report: Mapping[str, Any], field: str) -> bool | None:
    return _bool_or_none(_field_value(report, field))


def _text_field(report: Mapping[str, Any], field: str, default: str = "") -> str:
    value = _field_value(report, field)
    return str(value).strip() if _is_nonempty(value) else default


def _compact_text(value: Any, *, fallback: str = "not_declared", limit: int = 180) -> str:
    if isinstance(value, (list, tuple)):
        text = "; ".join(str(item) for item in value if _is_nonempty(item))
    elif isinstance(value, Mapping):
        text = str(
            value.get("summary")
            or value.get("status")
            or value.get("result")
            or value.get("reason")
            or value
        )
    else:
        text = str(value) if _is_nonempty(value) else fallback
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def _report_path_text(report_path: str | Path | None) -> str:
    if report_path is None:
        return "inline_report"
    raw_path = str(report_path)
    windows_path = PureWindowsPath(raw_path)
    if windows_path.is_absolute():
        return windows_path.name
    path = Path(report_path)
    if path.is_absolute():
        # Outcome cards are often copied into PRs and issues. Keep absolute
        # local machine paths out of the public surface while preserving a
        # route-shaped filename for the operator.
        return path.name
    return path.as_posix()


def _iter_action_values(report: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for mapping in _walk_mappings(report):
        for field in ACTION_FIELDS:
            raw = mapping.get(field)
            if isinstance(raw, Mapping):
                values: Sequence[Any] = [raw]
            elif isinstance(raw, (list, tuple)):
                values = raw
            else:
                values = []
            for item in values:
                if isinstance(item, Mapping) and _is_nonempty(item):
                    yield item


def _explicit_no_open_followup(report: Mapping[str, Any]) -> bool:
    for mapping in _walk_mappings(report):
        if _is_nonempty(mapping.get("no_open_followup_reason")):
            return True
    return False


def _no_action_reasons(report: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for mapping in _walk_mappings(report):
        for field in NO_ACTION_FIELDS:
            value = mapping.get(field)
            if isinstance(value, (list, tuple)):
                reasons.extend(_compact_text(item) for item in value if _is_nonempty(item))
            elif _is_nonempty(value):
                reasons.append(_compact_text(value))
    return list(dict.fromkeys(reasons))


def _is_diagnostic_only(report: Mapping[str, Any]) -> bool:
    values = [
        _text_field(report, "decision_impact"),
        _text_field(report, "quality_gate_kind"),
        _text_field(report, "benchmark_maturity_level"),
        _text_field(report, "status"),
    ]
    return any("diagnostic" in value.casefold() for value in values)


def _first_adoption_gate(report: Mapping[str, Any]) -> tuple[str | None, bool | None]:
    for field in ADOPTION_FIELDS:
        value = _bool_field(report, field)
        if value is not None:
            return field, value
    return None, None


def _claim_action(report: Mapping[str, Any], lint: Mapping[str, Any]) -> dict[str, Any]:
    public_quality_gate = _bool_field(report, "public_quality_gate_ok")
    quality_gate = _bool_field(report, "quality_gate_ok")
    if public_quality_gate is True and bool(lint.get("ok")):
        return {
            "decision": "update_current_claims",
            "why": "Public quality gate and benchmark contract lint both pass.",
            "doc_path": CLAIM_DOC_PATH,
        }
    if public_quality_gate is True:
        return {
            "decision": "human_review",
            "why": "Public quality gate is true, but contract lint still has findings.",
            "findings": list(lint.get("findings") or [])[:6],
        }
    if quality_gate is True or _is_diagnostic_only(report):
        return {
            "decision": "dated_report_only",
            "why": "Result can be cited as a bounded dated report, not a current public claim.",
        }
    if bool(lint.get("findings")) and not _no_action_reasons(report):
        return {
            "decision": "human_review",
            "why": "Contract fields are incomplete or ambiguous; review before claim changes.",
            "findings": list(lint.get("findings") or [])[:6],
        }
    return {
        "decision": "no_claim",
        "why": "No passing public quality signal was declared.",
    }


def _owner_action(report: Mapping[str, Any]) -> dict[str, Any]:
    counts = benchmark_report_followup_counts(report)
    first_action = next(iter(_iter_action_values(report)), None)
    if counts["followup_action_count"] > 0:
        action = {
            "decision": "open_or_update_issue",
            "why": "Report carries owner/action routing that should enter the execution queue.",
            "followup_action_count": counts["followup_action_count"],
        }
        if first_action:
            action["sample_action"] = {
                key: first_action[key]
                for key in ("id", "label", "owner_path", "doc_path", "command", "issue_url")
                if _is_nonempty(first_action.get(key))
            }
        return action
    if counts["unqualified_followup_action_count"] > 0:
        return {
            "decision": "human_review",
            "why": "Report names follow-up work, but the action lacks a usable owner route.",
            "unqualified_followup_action_count": counts["unqualified_followup_action_count"],
        }
    if counts["no_action_reason_count"] > 0:
        return {
            "decision": "explicit_no_action",
            "why": "; ".join(_no_action_reasons(report)[:3]) or "Report declares no follow-up.",
        }
    return {
        "decision": "no_action",
        "why": "No owner follow-up or issue action was declared.",
    }


def _adoption_action(report: Mapping[str, Any], lint: Mapping[str, Any]) -> dict[str, Any]:
    gate_field, gate_value = _first_adoption_gate(report)
    decision_impact = _text_field(report, "decision_impact", "not_declared")
    if gate_value is True and not _is_diagnostic_only(report) and bool(lint.get("ok")):
        return {
            "decision": "allow_default_adoption",
            "why": f"{gate_field} is true and the report is not diagnostic-only.",
            "gate": gate_field,
        }
    if gate_value is True:
        return {
            "decision": "human_review",
            "why": (
                "An adoption gate is true, but diagnostic or lint boundary fields "
                "still need review before runtime/default changes."
            ),
            "gate": gate_field,
        }
    if gate_value is False:
        return {
            "decision": "block_default_adoption",
            "why": f"{gate_field} is false.",
            "gate": gate_field,
        }
    if "diagnostic" in decision_impact.casefold() or _is_diagnostic_only(report):
        return {
            "decision": "diagnostic_only",
            "why": "Report is diagnostic/readiness evidence, not a default-adoption gate.",
        }
    return {
        "decision": "human_review",
        "why": "No runtime/default adoption gate was declared.",
    }


def _safe_next_action(
    *,
    report_path: str,
    claim_action: Mapping[str, Any],
    owner_action: Mapping[str, Any],
    adoption_action: Mapping[str, Any],
) -> dict[str, Any]:
    if owner_action.get("decision") in {"open_or_update_issue", "human_review"}:
        return {
            "id": "draft_benchmark_owner_issue",
            "label": "Draft benchmark owner issue",
            "command": (
                "python tools/aippocampus/benchmark_outcomes.py "
                f"--report {report_path} --issue-drafts"
            ),
            "mutation_risk": "draft_only",
        }
    if adoption_action.get("decision") == "block_default_adoption":
        return {
            "id": "keep_default_adoption_blocked",
            "label": "Keep default adoption blocked",
            "command": (
                "python tools/aippocampus/benchmark_outcomes.py "
                f"--report {report_path} --json"
            ),
            "mutation_risk": "read_only",
        }
    if claim_action.get("decision") == "update_current_claims":
        return {
            "id": "review_current_claims_update",
            "label": "Review current-claims update",
            "doc_path": CLAIM_DOC_PATH,
            "mutation_risk": "review_then_edit",
        }
    return {
        "id": "open_benchmark_report",
        "label": "Open benchmark report before changing claims or defaults",
        "report_path": report_path,
        "mutation_risk": "read_only",
    }


def build_benchmark_outcome_card(
    report: Mapping[str, Any],
    *,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build the compact benchmark decision card consumed by PRs and CI."""

    route = _report_path_text(report_path)
    lint = benchmark_report_contract_lint(report)
    claim_action = _claim_action(report, lint)
    owner_action = _owner_action(report)
    adoption_action = _adoption_action(report, lint)
    return {
        "kind": "aippocampus_benchmark_outcome_card",
        "schema_version": SCHEMA_VERSION,
        "report_path": route,
        "report_kind": str(report.get("kind") or "unknown"),
        "status": str(report.get("status") or "unknown"),
        "runner_ok": bool(report.get("ok")),
        "contract_gate_ok": bool(_bool_field(report, "contract_gate_ok")),
        "quality_gate_ok": bool(_bool_field(report, "quality_gate_ok")),
        "public_quality_gate_ok": bool(_bool_field(report, "public_quality_gate_ok")),
        "default_adoption_gate_ok": _bool_field(report, "default_adoption_gate_ok"),
        "runtime_policy_adoption_gate_ok": _bool_field(
            report,
            "runtime_policy_adoption_gate_ok",
        ),
        "decision_impact": _text_field(report, "decision_impact", "not_declared"),
        "measured_result": _compact_text(_field_value(report, "measured_result")),
        "claim_action": claim_action,
        "owner_action": owner_action,
        "adoption_action": adoption_action,
        "safe_next_action": _safe_next_action(
            report_path=route,
            claim_action=claim_action,
            owner_action=owner_action,
            adoption_action=adoption_action,
        ),
        "contract_lint": {
            "ok": bool(lint.get("ok")),
            "findings": list(lint.get("findings") or [])[:8],
            "followup_action_count": lint.get("followup_action_count", 0),
            "no_action_reason_count": lint.get("no_action_reason_count", 0),
        },
        "source_boundary": (
            "Outcome cards route benchmark reports; reopen the report before "
            "public claims, default changes, or issue closeout."
        ),
    }


def benchmark_outcome_digest(
    cards: Sequence[Mapping[str, Any]],
    *,
    route_limit: int = 5,
) -> dict[str, Any]:
    """Summarize outcome cards for first-screen PR/CI consumption."""

    counts = {
        "report_count": len(cards),
        "runner_success": 0,
        "public_quality_promoted": 0,
        "diagnostic_only": 0,
        "blocked": 0,
        "adoption_eligible": 0,
        "adoption_blocked": 0,
        "owner_action": 0,
        "no_action": 0,
    }
    routes: list[dict[str, Any]] = []
    for card in cards:
        claim = (card.get("claim_action") or {}).get("decision")
        owner = (card.get("owner_action") or {}).get("decision")
        adoption = (card.get("adoption_action") or {}).get("decision")
        if card.get("runner_ok"):
            counts["runner_success"] += 1
        if claim == "update_current_claims":
            counts["public_quality_promoted"] += 1
        if adoption == "diagnostic_only":
            counts["diagnostic_only"] += 1
        if claim in {"human_review", "no_claim"} or adoption == "human_review":
            counts["blocked"] += 1
        if adoption == "allow_default_adoption":
            counts["adoption_eligible"] += 1
        if adoption == "block_default_adoption":
            counts["adoption_blocked"] += 1
        if owner in {"open_or_update_issue", "human_review"}:
            counts["owner_action"] += 1
        if owner in {"explicit_no_action", "no_action"}:
            counts["no_action"] += 1
        if (
            owner in {"open_or_update_issue", "human_review"}
            or adoption in {"block_default_adoption", "human_review"}
            or claim in {"update_current_claims", "human_review"}
        ):
            routes.append(
                {
                    "report_path": card.get("report_path"),
                    "why": (card.get("safe_next_action") or {}).get("label"),
                    "claim_action": claim,
                    "owner_action": owner,
                    "adoption_action": adoption,
                }
            )
    return {
        "kind": "aippocampus_benchmark_outcome_digest",
        "schema_version": SCHEMA_VERSION,
        "counts": counts,
        "top_report_routes": routes[:route_limit],
        "runner_vs_quality_boundary": (
            "runner_success means the benchmark ran; public_quality_promoted and "
            "adoption_eligible are separate product-decision gates."
        ),
    }


def benchmark_report_outcome_digest(
    report: Mapping[str, Any],
    *,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    return benchmark_outcome_digest(
        [build_benchmark_outcome_card(report, report_path=report_path)]
    )


def _draft_title(action: Mapping[str, Any], card: Mapping[str, Any]) -> str:
    label = str(action.get("label") or action.get("id") or "").strip()
    if label:
        return label[:90]
    if card.get("adoption_action", {}).get("decision") == "block_default_adoption":
        return "Benchmark blocks default adoption follow-up"
    return "Benchmark outcome follow-up"


def _draft_key(action: Mapping[str, Any], card: Mapping[str, Any]) -> str:
    raw_owner = str(action.get("owner_path") or "").strip()
    owner = _report_path_text(raw_owner) if raw_owner else ""
    issue = str(action.get("issue_url") or action.get("current_issue_url") or "").strip()
    label = str(action.get("label") or action.get("id") or card.get("report_kind") or "")
    return "|".join([owner, issue, label]).casefold()


def _public_issue_action(action: Mapping[str, Any]) -> dict[str, Any]:
    public: dict[str, Any] = {}
    for key in ISSUE_DRAFT_ACTION_FIELDS:
        value = action.get(key)
        if not _is_nonempty(value):
            continue
        if key in {"owner_path", "doc_path"}:
            public[key] = _report_path_text(str(value))
        else:
            public[key] = _compact_text(value, limit=320)
    return public


def _issue_body(
    *,
    action: Mapping[str, Any],
    card: Mapping[str, Any],
    report_paths: Sequence[str],
) -> str:
    blocker = _compact_text(
        action.get("reason")
        or action.get("blocker")
        or (card.get("adoption_action") or {}).get("why")
        or (card.get("claim_action") or {}).get("why"),
        fallback="Benchmark outcome needs owner review.",
        limit=320,
    )
    measured = _compact_text(card.get("measured_result"), fallback=str(card.get("status")))
    source_lines = "\n".join(f"- `{path}`" for path in report_paths)
    return f"""## User-Visible Problem

Benchmark evidence produced an actionable outcome, but the execution queue does
not yet have a focused owner issue for it.

## Evidence

Source report:

{source_lines}

Measured result: {measured}

Blocker / owner signal: {blocker}

## Scope

- Route the benchmark outcome named in this issue into the smallest product,
  docs, or verification change that resolves the blocker.
- Reopen the source report before changing public claims or runtime defaults.
- Keep benchmark-local scaffolding separate from runtime/default capability.

## Non-Goals

- Do not turn every `cannot_claim` into an issue.
- Do not auto-edit `docs/evidence/current-claims.md` from this issue alone.
- Do not use diagnostic-only evidence to authorize broad defaults.

## Acceptance Criteria

- [ ] The blocker or owner action is either implemented, explicitly superseded,
      or closed with a trusted no-action reason.
- [ ] Any public claim/default-adoption change cites a benchmark outcome card or
      explains why this change is not benchmark-gated.
- [ ] Follow-up verification names the report path and the focused command or
      document route used.

## Privacy / Source Note

- [x] Does not expose raw private memory, credentials, local paths, or private
      conversation text.
- [x] Benchmark reports are routing evidence; reopen source before factual,
      stale, sensitive, or default-adoption claims.
"""


def build_benchmark_issue_drafts(
    reports: Sequence[tuple[str | Path | None, Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    """Return public-safe issue draft records without creating GitHub issues."""

    grouped: dict[str, dict[str, Any]] = {}
    for report_path, report in reports:
        if _explicit_no_open_followup(report):
            continue
        card = build_benchmark_outcome_card(report, report_path=report_path)
        actions = list(_iter_action_values(report))
        if not actions and card["owner_action"]["decision"] in {"human_review", "open_or_update_issue"}:
            actions = [{"label": "Review benchmark outcome", "reason": card["owner_action"]["why"]}]
        for action in actions:
            key = _draft_key(action, card)
            if key not in grouped:
                grouped[key] = {
                    "kind": "aippocampus_benchmark_issue_draft",
                    "schema_version": SCHEMA_VERSION,
                    "dedupe_key": key,
                    "title": _draft_title(action, card),
                    "action": _public_issue_action(action),
                    "card": card,
                    "source_report_paths": [],
                }
            route = _report_path_text(report_path)
            paths = grouped[key]["source_report_paths"]
            if route not in paths:
                paths.append(route)
    drafts: list[dict[str, Any]] = []
    for item in grouped.values():
        item["body"] = _issue_body(
            action=item["action"],
            card=item["card"],
            report_paths=item["source_report_paths"],
        )
        drafts.append(item)
    return sorted(drafts, key=lambda item: (item["title"], item["dedupe_key"]))
