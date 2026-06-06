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
