"""Shared public-boundary vocabulary for AIppocampus runtime surfaces.

This module is deliberately small. It gives CLI, MCP, hook, ops, and generated
report owners a common language without forcing precise internal sidecars into a
generic schema. Source authority still belongs to clean source, source refs, and
domain-specific gates; these constants only classify observable runtime state.
"""

from __future__ import annotations

PUBLIC_RUNTIME_ENVELOPE_FIELDS = (
    "ok",
    "status",
    "data",
    "warnings",
    "errors",
    "next",
    "meta",
    "cannot_claim",
)

PUBLIC_RUNTIME_STATUSES = (
    "ok",
    "partial",
    "skipped",
    "degraded",
    "blocked",
    "error",
)

RUNTIME_FAILURE_FAMILIES = (
    "source_missing",
    "source_stale",
    "privacy_blocked",
    "permission_blocked",
    "provider_unavailable",
    "foreground_budget",
    "partial_failure",
    "degraded_fallback",
    "schema_invalid",
    "writer_busy",
    "unsupported_mode",
    "no_evidence",
)

PUBLIC_RUNTIME_SURFACE_CLASSES = (
    "public_api",
    "package_owner_cli",
    "generated_sidecar",
    "internal_helper",
)

FOREGROUND_ACTION_CONTRACT_VERSION = "foreground-action-v1"

FOREGROUND_ACTION_SURFACE_CLASSES = (
    "foreground_agent_action",
    "foreground_recovery_card",
    "foreground_chooser_card",
    "operator_only_diagnostic",
    "benchmark_or_report",
    "source_reopen_surface",
)

PUBLIC_CONTRACT_SUBPACKAGES = (
    "cli",
    "config",
    "hooks",
    "mcp",
    "onboarding",
    "ops",
    "registry",
    "source",
    "sync",
    "update",
)


def public_envelope(
    *,
    ok: bool,
    status: str,
    data: object | None = None,
    warnings: list[dict[str, object]] | None = None,
    errors: list[dict[str, object]] | None = None,
    next: list[dict[str, object]] | None = None,
    meta: dict[str, object] | None = None,
    cannot_claim: list[str] | None = None,
) -> dict[str, object]:
    """Build a public runtime envelope without changing source authority."""

    normalized = status if status in PUBLIC_RUNTIME_STATUSES else "error"
    return {
        "ok": bool(ok) and normalized in {"ok", "partial", "skipped", "degraded"},
        "status": normalized,
        "data": data,
        "warnings": list(warnings or []),
        "errors": list(errors or []),
        "next": list(next or []),
        "meta": dict(meta or {}),
        "cannot_claim": list(cannot_claim or []),
    }


def foreground_shell_action(
    *,
    action_id: str,
    command: str,
    label: str | None = None,
    why: str | None = None,
    mutation_risk: str = "read_only",
    claim_boundary: str = "source_reopen_required_before_claims",
) -> dict[str, object]:
    """Build one executable foreground command without changing source authority.

    Keep this helper small: domain modules still own evidence levels, privacy
    gates, and source reopening. This only prevents every CLI/MCP surface from
    inventing a different shape for "what should a foreground agent do next?".
    """

    payload: dict[str, object] = {
        "id": action_id,
        "command": command,
        "mutation_risk": mutation_risk,
        "claim_boundary": claim_boundary,
    }
    if label:
        payload["label"] = label
    if why:
        payload["why"] = why
    return payload


def foreground_recovery_card(
    *,
    kind: str,
    error_code: str,
    message: str,
    safe_next_actions: list[dict[str, object]],
    status: str = "needs_input",
    surface_class: str = "foreground_recovery_card",
    source_boundary: dict[str, object] | None = None,
) -> dict[str, object]:
    primary = safe_next_actions[0] if safe_next_actions else {}
    return {
        "kind": kind,
        "ok": False,
        "status": status,
        "surface_class": surface_class,
        "foreground_action_contract": FOREGROUND_ACTION_CONTRACT_VERSION,
        "error": {"code": error_code, "message": message},
        "agent_next_action": primary,
        "safe_next_actions": list(safe_next_actions),
        "source_boundary": dict(
            source_boundary
            or {
                "source_backed_claim_allowed": False,
                "source_reopen_required_before_claims": True,
            }
        ),
    }


def foreground_chooser_card(
    *,
    kind: str,
    decision: str,
    choices: list[dict[str, object]],
    status: str = "choose_action",
    surface_class: str = "foreground_chooser_card",
    no_write_happened: bool = True,
) -> dict[str, object]:
    primary = choices[0] if choices else {}
    return {
        "kind": kind,
        "ok": True,
        "status": status,
        "surface_class": surface_class,
        "foreground_action_contract": FOREGROUND_ACTION_CONTRACT_VERSION,
        "decision": decision,
        "agent_next_action": primary,
        "choices": list(choices),
        "write_boundary": {
            "written": False,
            "no_write_happened": bool(no_write_happened),
            "explicit_write_required": True,
        },
    }
