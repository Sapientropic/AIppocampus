"""Typed compact-boundary helpers for MCP foreground cards.

MCP compact payloads are read by foreground agents as working context. This
module is intentionally narrower than the repo-wide runtime contracts: it only
guards the MCP compact card shape and the primary action's direct usability.
Detailed proof, provenance, and operator diagnostics stay in full/detail mode.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, TypedDict, cast

from aippocampus_runtime.contracts import normalize_foreground_action

MCP_COMPACT_BOUNDARY_VERSION = "mcp-compact-boundary-v1"


class MCPCompactBoundaryError(ValueError):
    """Raised when a compact MCP foreground card is unsafe to expose."""


class ForegroundActionContract(TypedDict, total=False):
    """Field-level public contract for primary foreground actions.

    Compact MCP cards are consumed directly by agents. A primary action may be a
    concrete command/tool call, or an explicitly non-actionable/template row, but
    it must not look executable while lacking the fields needed to follow it.
    """

    id: str
    label: NotRequired[str]
    command: NotRequired[str]
    tool_name: NotRequired[str]
    arguments: NotRequired[dict[str, Any]]
    command_template: NotRequired[str]
    arguments_template: NotRequired[dict[str, Any]]
    followup_arguments_template: NotRequired[dict[str, Any]]
    last_recall_fallback_command_template: NotRequired[str]
    template_only: NotRequired[bool]
    requires: NotRequired[list[str]]
    actionability: NotRequired[str]
    route_index: NotRequired[int]
    primary_route_relation: NotRequired[str]
    non_actionable: NotRequired[bool]
    continue_without_command: NotRequired[bool]
    no_op: NotRequired[bool]
    no_command_needed: NotRequired[bool]
    mutation_risk: NotRequired[str]
    claim_boundary: NotRequired[str]
    why: NotRequired[str]
    source_boundary: NotRequired[str]
    source_reopen_boundary: NotRequired[str]
    secondary_action: NotRequired["ForegroundActionContract"]


class SafeNextActionContract(ForegroundActionContract, total=False):
    """Secondary/follow-up foreground action contract."""


class MCPToolErrorContract(TypedDict, total=False):
    code: str
    message: str
    retryable: NotRequired[bool]
    foreground_action: NotRequired[ForegroundActionContract]


class MCPCompactResponseContract(TypedDict, total=False):
    """Shared field-level contract for compact MCP foreground cards."""

    detail: Literal["compact"]
    status: NotRequired[str]
    ok: NotRequired[bool]
    kind: NotRequired[str]
    schema_version: NotRequired[int | str]
    surface: NotRequired[str]
    surface_class: NotRequired[str]
    decision: NotRequired[str]
    summary: NotRequired[str]
    foreground_action: NotRequired[ForegroundActionContract]
    safe_next_actions: NotRequired[list[SafeNextActionContract]]
    follow_up_action: NotRequired[ForegroundActionContract]
    error: NotRequired[MCPToolErrorContract | dict[str, Any]]
    claim_boundary: NotRequired[str]
    source_boundary: NotRequired[str | dict[str, Any]]
    source_reopen_boundary: NotRequired[str]
    routes: NotRequired[list[dict[str, Any]]]
    source_hits: NotRequired[list[dict[str, Any]]]
    source_window_summary: NotRequired[dict[str, Any]]
    primary_source_snippet: NotRequired[str]
    source_window_preview: NotRequired[list[dict[str, Any]]]
    miss_recovery_card: NotRequired[dict[str, Any]]
    background_recovery_card: NotRequired[dict[str, Any]]
    repo_familiarity_fallback: NotRequired[dict[str, Any]]


class AgentRecallCompactCard(MCPCompactResponseContract, total=False):
    exact_wording_source_search_primary: NotRequired[bool]


class AgentDeepenCompactCard(MCPCompactResponseContract, total=False):
    mode: NotRequired[str]


class AgentExplainCompactCard(MCPCompactResponseContract, total=False):
    mode: NotRequired[str]


class SearchMemoryCompactCard(MCPCompactResponseContract, total=False):
    query_text: NotRequired[str]
    search_scope: NotRequired[str]
    mcp_search_scope: NotRequired[str]
    useful_target_hit: NotRequired[bool]
    match_count: NotRequired[int]


@dataclass(frozen=True)
class MCPCompactBoundaryViolation:
    field: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "reason": self.reason}


@dataclass(frozen=True)
class MCPCompactCard:
    surface: str
    payload: MCPCompactResponseContract


def build_mcp_compact_card(
    payload: Mapping[str, Any], *, surface: str
) -> MCPCompactResponseContract:
    """Return a compact MCP card only after the foreground boundary passes."""

    card = MCPCompactCard(
        surface=surface,
        payload=mcp_compact_response_contract(payload, surface=surface),
    )
    violations = mcp_compact_boundary_violations(card.payload, surface=card.surface)
    if violations:
        encoded = "; ".join(
            f"{violation.field}:{violation.reason}" for violation in violations
        )
        raise MCPCompactBoundaryError(
            f"{MCP_COMPACT_BOUNDARY_VERSION} rejected {card.surface}: {encoded}"
        )
    return card.payload


def without_internal_surface(payload: MCPCompactResponseContract) -> MCPCompactResponseContract:
    """Remove MCP's internal routing surface without widening the compact type.

    Some flagship foreground cards, notably agent recall, are consumed directly
    by CLI/MCP/public JSON callers. The internal `surface` label is useful while
    validating the card, but exposing it in the default card turns the foreground
    into a protocol-debug surface. Keep this as a typed boundary helper instead
    of letting call sites re-cast raw dictionaries.
    """

    public_payload: dict[str, Any] = dict(payload)
    public_payload.pop("surface", None)
    return cast(MCPCompactResponseContract, public_payload)


def foreground_action_contract(action: Mapping[str, Any]) -> ForegroundActionContract:
    """Normalize an action into the compact public foreground contract."""

    normalized = normalize_foreground_action(action)
    typed: dict[str, Any] = {}
    if "id" in normalized or "action_id" in normalized:
        typed["id"] = str(normalized.get("id") or normalized.get("action_id") or "")
    for key in ("label", "command", "tool_name", "mutation_risk", "claim_boundary", "why"):
        value = normalized.get(key)
        if value not in (None, ""):
            typed[key] = str(value)
    for key in ("command_template", "last_recall_fallback_command_template"):
        value = normalized.get(key)
        if isinstance(value, str) and value:
            typed[key] = value
    for key in ("arguments", "arguments_template", "followup_arguments_template"):
        value = normalized.get(key)
        if isinstance(value, Mapping):
            typed[key] = dict(value)
    for key in (
        "template_only",
        "non_actionable",
        "continue_without_command",
        "no_op",
        "no_command_needed",
    ):
        value = normalized.get(key)
        if isinstance(value, bool):
            typed[key] = value
    requires = normalized.get("requires")
    if isinstance(requires, Sequence) and not isinstance(requires, (str, bytes)):
        typed["requires"] = [str(item) for item in requires if str(item).strip()]
    actionability = normalized.get("actionability")
    if isinstance(actionability, str) and actionability:
        typed["actionability"] = actionability
    route_index = normalized.get("route_index")
    if isinstance(route_index, int):
        typed["route_index"] = route_index
    relation = normalized.get("primary_route_relation")
    if isinstance(relation, str) and relation:
        typed["primary_route_relation"] = relation
    secondary = normalized.get("secondary_action")
    if isinstance(secondary, Mapping):
        typed["secondary_action"] = foreground_action_contract(secondary)
    return cast(ForegroundActionContract, typed)


def _safe_next_action_contract(action: Mapping[str, Any]) -> SafeNextActionContract:
    return foreground_action_contract(action)


def mcp_compact_response_contract(
    payload: Mapping[str, Any], *, surface: str
) -> MCPCompactResponseContract:
    """Return a field-level typed MCP compact response without adding debug fields."""

    typed: dict[str, Any] = dict(payload)
    detail = str(payload.get("detail") or "compact")
    typed["detail"] = "compact" if detail == "compact" else "compact"
    typed.setdefault("surface", surface)
    foreground = payload.get("foreground_action")
    if isinstance(foreground, Mapping):
        typed["foreground_action"] = foreground_action_contract(foreground)
    raw_safe_next = payload.get("safe_next_actions")
    if isinstance(raw_safe_next, Sequence) and not isinstance(raw_safe_next, (str, bytes)):
        typed["safe_next_actions"] = [
            _safe_next_action_contract(action)
            for action in raw_safe_next
            if isinstance(action, Mapping)
        ]
    follow_up = payload.get("follow_up_action")
    if isinstance(follow_up, Mapping):
        typed["follow_up_action"] = foreground_action_contract(follow_up)
    error = payload.get("error")
    if isinstance(error, Mapping):
        typed["error"] = _tool_error_contract(error)
    return cast(MCPCompactResponseContract, typed)


def _tool_error_contract(error: Mapping[str, Any]) -> MCPToolErrorContract:
    typed: MCPToolErrorContract = {
        "code": str(error.get("code") or ""),
        "message": str(error.get("message") or ""),
    }
    if isinstance(error.get("retryable"), bool):
        typed["retryable"] = bool(error.get("retryable"))
    foreground = error.get("foreground_action")
    if isinstance(foreground, Mapping):
        typed["foreground_action"] = foreground_action_contract(foreground)
    return typed


def mcp_compact_boundary_violations(
    payload: Mapping[str, Any], *, surface: str
) -> list[MCPCompactBoundaryViolation]:
    """Return compact-card violations without mutating the public payload."""

    violations: list[MCPCompactBoundaryViolation] = []
    foreground = payload.get("foreground_action")
    if foreground is None:
        return violations
    if not isinstance(foreground, Mapping):
        return [
            MCPCompactBoundaryViolation(
                field="foreground_action",
                reason="primary_foreground_action_must_be_object",
            )
        ]
    action = normalize_foreground_action(foreground)
    violations.extend(_primary_template_action_violations(action))
    return violations


def _primary_template_action_violations(
    action: Mapping[str, Any],
) -> list[MCPCompactBoundaryViolation]:
    if not _is_template_action(action):
        return []
    if _has_required_input_marker(action) or _has_explicit_non_action_marker(action):
        return []
    return [
        MCPCompactBoundaryViolation(
            field="foreground_action.requires",
            reason="template_primary_must_mark_required_inputs_or_non_action",
        )
    ]


def _is_template_action(action: Mapping[str, Any]) -> bool:
    return bool(
        action.get("template_only") is True
        or isinstance(action.get("command_template"), str)
        or isinstance(action.get("arguments_template"), Mapping)
        or isinstance(action.get("followup_arguments_template"), Mapping)
    )


def _has_required_input_marker(action: Mapping[str, Any]) -> bool:
    requires = action.get("requires")
    return (
        isinstance(requires, Sequence)
        and not isinstance(requires, (str, bytes))
        and any(str(item).strip() for item in requires)
    )


def _has_explicit_non_action_marker(action: Mapping[str, Any]) -> bool:
    actionability = str(action.get("actionability") or "").strip()
    return bool(
        action.get("continue_without_command")
        or action.get("no_op")
        or action.get("no_command_needed")
        or action.get("non_actionable") is True
        or actionability in {
            "non_actionable",
            "requires_input",
            "template_requires_input",
        }
    )


__all__ = [
    "AgentDeepenCompactCard",
    "AgentExplainCompactCard",
    "AgentRecallCompactCard",
    "ForegroundActionContract",
    "MCP_COMPACT_BOUNDARY_VERSION",
    "MCPCompactBoundaryError",
    "MCPCompactBoundaryViolation",
    "MCPCompactResponseContract",
    "MCPToolErrorContract",
    "SafeNextActionContract",
    "SearchMemoryCompactCard",
    "build_mcp_compact_card",
    "foreground_action_contract",
    "mcp_compact_response_contract",
    "mcp_compact_boundary_violations",
]
