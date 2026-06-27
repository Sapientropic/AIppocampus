"""Typed compact-boundary helpers for MCP foreground cards.

MCP compact payloads are read by foreground agents as working context. This
module is intentionally narrower than the repo-wide runtime contracts: it only
guards the MCP compact card shape and the primary action's direct usability.
Detailed proof, provenance, and operator diagnostics stay in full/detail mode.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from aippocampus_runtime.contracts import normalize_foreground_action

MCP_COMPACT_BOUNDARY_VERSION = "mcp-compact-boundary-v1"


class MCPCompactBoundaryError(ValueError):
    """Raised when a compact MCP foreground card is unsafe to expose."""


@dataclass(frozen=True)
class MCPCompactBoundaryViolation:
    field: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "reason": self.reason}


@dataclass(frozen=True)
class MCPCompactCard:
    surface: str
    payload: dict[str, Any]


def build_mcp_compact_card(payload: Mapping[str, Any], *, surface: str) -> dict[str, Any]:
    """Return a compact MCP card only after the foreground boundary passes."""

    card = MCPCompactCard(surface=surface, payload=dict(payload))
    violations = mcp_compact_boundary_violations(card.payload, surface=card.surface)
    if violations:
        encoded = "; ".join(
            f"{violation.field}:{violation.reason}" for violation in violations
        )
        raise MCPCompactBoundaryError(
            f"{MCP_COMPACT_BOUNDARY_VERSION} rejected {card.surface}: {encoded}"
        )
    return card.payload


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
    "MCP_COMPACT_BOUNDARY_VERSION",
    "MCPCompactBoundaryError",
    "MCPCompactBoundaryViolation",
    "build_mcp_compact_card",
    "mcp_compact_boundary_violations",
]
