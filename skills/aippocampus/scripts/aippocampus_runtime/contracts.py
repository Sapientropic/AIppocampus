"""Shared public-boundary vocabulary for AIppocampus runtime surfaces.

This module is deliberately small. It gives CLI, MCP, hook, ops, and generated
report owners a common language without forcing precise internal sidecars into a
generic schema. Source authority still belongs to clean source, source refs, and
domain-specific gates; these constants only classify observable runtime state.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

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

EXECUTABLE_COMMAND_FIELDS = {
    "command",
    "cli_command",
    "next_command",
    "apply_command",
    "preview_command",
    "write_command",
    "search_command",
    "recommended_public_command",
    "object_storage_command",
}

_NON_EXECUTABLE_FIELD_MARKERS = (
    "template",
    "example",
    "manual_instruction",
    "requires",
)

_ANGLE_PLACEHOLDER_RE = re.compile(r"<[^>\n]+>")
_BRACE_PLACEHOLDER_RE = re.compile(
    r"\{(?:cue|continuity_cue|exact_phrase|input_path|output_path|"
    r"request_index|task|query|note_text|card_id|arc_handle|scope|handle)\}"
)
_SAMPLE_COMMAND_PHRASES = (
    "old decision or handoff cue",
    "distinctive exact phrase",
    "distinctive old phrase",
    "old continuity cue",
    "old cue",
    "route to pause",
    "route to forget here",
    "route to quiet",
    "issue:#123",
    "issue title",
    "issue body",
)


def command_value_needs_input(value: object) -> bool:
    """Return whether a command-like value is not directly executable.

    Foreground JSON has a strong affordance: a field named ``command`` or
    ``cli_command`` tells an agent it can run the string now. Privacy redaction
    and sample cues are fine in templates, but putting them in executable slots
    creates copy/paste traps such as running ``<path>`` or a generic old-cue
    search. Keep this test centralized so new surfaces do not relearn the same
    boundary one at a time.
    """

    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    if _ANGLE_PLACEHOLDER_RE.search(text) or _BRACE_PLACEHOLDER_RE.search(text):
        return True
    lowered = text.casefold()
    if lowered.startswith("run `") or "`" in text:
        return True
    return any(phrase in lowered for phrase in _SAMPLE_COMMAND_PHRASES)


def foreground_template_action(
    *,
    action_id: str,
    command_template: str,
    requires: Sequence[str],
    label: str | None = None,
    why: str | None = None,
    mutation_risk: str = "read_only",
    claim_boundary: str = "source_reopen_required_before_claims",
) -> dict[str, object]:
    """Build a non-executable foreground action that needs caller input."""

    payload: dict[str, object] = {
        "id": action_id,
        "command_template": command_template,
        "requires": list(requires),
        "mutation_risk": mutation_risk,
        "claim_boundary": claim_boundary,
        "template_only": True,
    }
    if label:
        payload["label"] = label
    if why:
        payload["why"] = why
    return payload


def executable_command_violations(payload: object) -> list[dict[str, str]]:
    """Find placeholder/prose values in machine-executable fields."""

    violations: list[dict[str, str]] = []

    def allowed_context(path: tuple[str, ...]) -> bool:
        return any(any(marker in part for marker in _NON_EXECUTABLE_FIELD_MARKERS) for part in path)

    def walk(value: object, path: tuple[str, ...]) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                key_text = str(key)
                next_path = (*path, key_text)
                if key_text in EXECUTABLE_COMMAND_FIELDS and not allowed_context(next_path):
                    if command_value_needs_input(item):
                        violations.append(
                            {
                                "path": ".".join(next_path),
                                "field": key_text,
                                "reason": "executable_field_needs_input",
                                "value": str(item),
                            }
                        )
                if key_text == "arguments" and not allowed_context(next_path):
                    walk_machine_arguments(item, next_path)
                walk(item, next_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, (*path, str(index)))

    def walk_machine_arguments(value: object, path: tuple[str, ...]) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                next_path = (*path, str(key))
                if command_value_needs_input(item):
                    violations.append(
                        {
                            "path": ".".join(next_path),
                            "field": "arguments",
                            "reason": "machine_arguments_need_input",
                            "value": str(item),
                        }
                    )
                walk_machine_arguments(item, next_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk_machine_arguments(item, (*path, str(index)))

    walk(payload, ())
    return violations

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
