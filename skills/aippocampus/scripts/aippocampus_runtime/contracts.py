"""Shared public-boundary vocabulary for AIppocampus runtime surfaces.

This module is deliberately small. It gives CLI, MCP, hook, ops, and generated
report owners a common language without forcing precise internal sidecars into a
generic schema. Source authority still belongs to clean source, source refs, and
domain-specific gates; these constants only classify observable runtime state.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping, Sequence

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
READINESS_CARD_CONTRACT_VERSION = "readiness-card-v1"

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
_NON_RUNNABLE_COMMAND_MARKERS = {
    "no-op",
    "continue-without-cleanup",
}


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


def command_value_is_non_runnable_marker(value: object) -> bool:
    """Return whether a command-like field is a semantic marker, not a command.

    No-work choices are valid foreground actions, but they must be encoded with
    explicit `continue_without_command` / `no_op` markers. Putting prose sentinels
    such as `no-op` into `command` trains agents to copy-paste strings that can
    never succeed, and it hides the product distinction between "run this" and
    "continue without a command".
    """

    if not isinstance(value, str):
        return False
    return value.strip().casefold() in _NON_RUNNABLE_COMMAND_MARKERS


def shell_quote(value: object) -> str:
    """Quote one concrete value for copy-pasteable shell commands.

    JSON quoting is safe for JSON, not for shells: ``$()``, backticks, and other
    metacharacters still execute inside many double-quoted shells. Foreground
    command strings are meant to be copy-pasted, so every real user/source value
    interpolated into ``command`` must pass through this helper. Template-only
    commands keep placeholders instead of pretending to be executable.
    """

    return shlex.quote(str(value or ""))


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
                    marker_reason = (
                        "executable_field_is_non_runnable_marker"
                        if command_value_is_non_runnable_marker(item)
                        else ""
                    )
                    if marker_reason:
                        violations.append(
                            {
                                "path": ".".join(next_path),
                                "field": key_text,
                                "reason": marker_reason,
                                "value": str(item),
                            }
                        )
                    elif command_value_needs_input(item):
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


def normalize_foreground_action(action: Mapping[str, object]) -> dict[str, object]:
    """Return the canonical foreground-action vocabulary for one action object.

    Older recall/search and diagnostic surfaces used ``action_id`` plus
    ``cli_command`` names before ``foreground-action-v1`` settled on ``id`` and
    ``command``/``command_template``. Keep that compatibility at the boundary:
    action producers may still carry historical fields internally, but public
    compact cards should present one vocabulary so host agents do not have to
    special-case the flagship recall path.
    """

    payload = dict(action)
    if "id" not in payload and payload.get("action_id"):
        payload["id"] = payload.get("action_id")
    if "command" not in payload and payload.get("cli_command"):
        payload["command"] = payload.get("cli_command")
    if "command_template" not in payload and payload.get("cli_command_template"):
        payload["command_template"] = payload.get("cli_command_template")
    if "original_id" not in payload and payload.get("original_action_id"):
        payload["original_id"] = payload.get("original_action_id")

    for legacy_key in (
        "action_id",
        "cli_command",
        "cli_command_template",
        "original_action_id",
    ):
        payload.pop(legacy_key, None)

    for nested_key in ("secondary_action", "primary_action"):
        nested = payload.get(nested_key)
        if isinstance(nested, Mapping):
            payload[nested_key] = normalize_foreground_action(nested)
    template = payload.get("tighter_cue_template")
    if isinstance(template, Mapping):
        payload["tighter_cue_template"] = normalize_foreground_action(template)
    return payload


def canonical_foreground_action_fields(
    foreground_action: Mapping[str, object],
    *,
    safe_next_actions: Sequence[Mapping[str, object]] | None = None,
    include_compat_alias: bool = True,
) -> dict[str, object]:
    """Return the shared foreground action field set for compact cards.

    `foreground_action` is the authoritative field. The legacy
    `agent_next_action` alias remains only as a byte-for-byte compatibility
    mirror so host agents do not have to guess precedence while older clients
    migrate. Keep `safe_next_actions[0]` equal to the foreground action; put
    alternates after it.
    """

    primary = normalize_foreground_action(foreground_action)
    alternates = [
        normalize_foreground_action(action)
        for action in (safe_next_actions or [])
        if action
    ]
    if not alternates or alternates[0] != primary:
        alternates = [primary, *[action for action in alternates if action != primary]]
    payload: dict[str, object] = {
        "foreground_action_contract": FOREGROUND_ACTION_CONTRACT_VERSION,
        "foreground_action": primary,
        "safe_next_actions": alternates,
    }
    if include_compat_alias:
        payload["agent_next_action"] = primary
    return payload


def foreground_readiness_card(
    *,
    subject: str,
    scope: str,
    state: str,
    usable_now: bool,
    blocks_first_recall: bool,
    blocks_exact_latest: bool = False,
    recommended: Sequence[str] | None = None,
    next_actions: Sequence[Mapping[str, object]] | None = None,
    claim_boundary: str = "readiness_is_operational_status_not_source_truth",
) -> dict[str, object]:
    """Build the shared compact readiness shape for foreground surfaces.

    This card intentionally stays smaller than an internal diagnostics model.
    It answers the product question a foreground agent has first: can ordinary
    continuity proceed now, and what must be refreshed before higher-risk or
    exact-latest claims? Avoid putting path-bearing operator commands here;
    attach executable/template actions through the foreground action contract.
    """

    payload: dict[str, object] = {
        "readiness_contract": READINESS_CARD_CONTRACT_VERSION,
        "subject": subject,
        "scope": scope,
        "state": state,
        "usable_now": bool(usable_now),
        "blocks_first_recall": bool(blocks_first_recall),
        "blocks_exact_latest": bool(blocks_exact_latest),
        "recommended": [str(item) for item in (recommended or []) if str(item)],
        "next_actions": [dict(action) for action in (next_actions or []) if action],
        "claim_boundary": claim_boundary,
    }
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, "", [])
    }


def foreground_action_contract_violations(payload: Mapping[str, object]) -> list[dict[str, str]]:
    """Lint compact-card action aliases against the foreground-action contract."""

    violations: list[dict[str, str]] = []
    foreground = payload.get("foreground_action")
    agent_next = payload.get("agent_next_action")
    safe_actions = payload.get("safe_next_actions")
    contract = payload.get("foreground_action_contract")
    if foreground is None:
        if agent_next is not None or contract == FOREGROUND_ACTION_CONTRACT_VERSION:
            violations.append(
                {
                    "field": "foreground_action",
                    "reason": "missing_canonical_foreground_action",
                }
            )
        return violations
    if not isinstance(foreground, Mapping):
        violations.append(
            {
                "field": "foreground_action",
                "reason": "canonical_foreground_action_must_be_object",
            }
        )
        return violations
    foreground_dict = dict(foreground)
    violations.extend(_foreground_action_shape_violations(foreground, field="foreground_action"))
    violations.extend(_command_template_marker_violations(foreground, field="foreground_action"))
    if isinstance(agent_next, Mapping) and dict(agent_next) != foreground_dict:
        violations.append(
            {
                "field": "agent_next_action",
                "reason": "alias_must_match_foreground_action",
            }
        )
    if isinstance(safe_actions, Sequence) and not isinstance(safe_actions, str):
        first = next(iter(safe_actions), None)
        if not isinstance(first, Mapping):
            violations.append(
                {
                    "field": "safe_next_actions.0",
                    "reason": "primary_safe_action_must_be_object",
                }
            )
        elif dict(first) != foreground_dict:
            violations.append(
                {
                    "field": "safe_next_actions.0",
                    "reason": "primary_safe_action_must_match_foreground_action",
                }
            )
        else:
            violations.extend(_foreground_action_shape_violations(first, field="safe_next_actions.0"))
        for index, action in enumerate(safe_actions):
            if index == 0 or not isinstance(action, Mapping):
                continue
            violations.extend(
                _command_template_marker_violations(action, field=f"safe_next_actions.{index}")
            )
    for key in ("next_safe_action", "follow_up_action", "secondary_action"):
        action = payload.get(key)
        if isinstance(action, Mapping):
            violations.extend(_command_template_marker_violations(action, field=key))
    return violations


def _command_template_marker_violations(
    action: Mapping[str, object],
    *,
    field: str,
) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    if command_value_is_non_runnable_marker(action.get("command")):
        violations.append(
            {
                "field": f"{field}.command",
                "reason": "executable_field_is_non_runnable_marker",
            }
        )
    if isinstance(action.get("command_template"), str) and action.get("template_only") is not True:
        violations.append(
            {
                "field": f"{field}.template_only",
                "reason": "command_template_requires_template_only_true",
            }
        )
    nested = action.get("secondary_action")
    if isinstance(nested, Mapping):
        violations.extend(
            _command_template_marker_violations(nested, field=f"{field}.secondary_action")
        )
    return violations


def _foreground_action_shape_violations(action: Mapping[str, object], *, field: str) -> list[dict[str, str]]:
    """Return minimum usability violations for one foreground action card.

    Alias equality protects machines from precedence ambiguity, but it does not
    stop a skeletal card from reaching the foreground. The v1 card must also
    tell the next agent what the action is, why it is safe/useful, and what risk
    and claim boundary it carries. Healthy no-work cards use an explicit
    continue/no-op marker instead of pretending to have a shell command.
    """

    violations: list[dict[str, str]] = []
    for key in ("id", "label", "mutation_risk", "claim_boundary", "why"):
        value = action.get(key)
        if not isinstance(value, str) or not value.strip():
            violations.append(
                {
                    "field": f"{field}.{key}",
                    "reason": "required_foreground_action_field_missing",
                }
            )
    has_target = any(
        isinstance(action.get(key), str) and str(action.get(key)).strip()
        for key in ("command", "command_template", "tool_name")
    )
    if isinstance(action.get("command_template"), str) and action.get("template_only") is not True:
        violations.append(
            {
                "field": f"{field}.template_only",
                "reason": "command_template_requires_template_only_true",
            }
        )
    has_continue_marker = any(
        bool(action.get(key))
        for key in ("continue_without_command", "no_op", "no_command_needed")
    )
    if not has_target and not has_continue_marker:
        violations.append(
            {
                "field": field,
                "reason": "foreground_action_needs_target_or_explicit_continue_marker",
            }
        )
    return violations


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
    action_fields = (
        canonical_foreground_action_fields(primary, safe_next_actions=safe_next_actions)
        if primary
        else {
            "foreground_action_contract": FOREGROUND_ACTION_CONTRACT_VERSION,
            "foreground_action": {},
            "agent_next_action": {},
            "safe_next_actions": [],
        }
    )
    return {
        "kind": kind,
        "ok": False,
        "status": status,
        "surface_class": surface_class,
        "error": {"code": error_code, "message": message},
        **action_fields,
        "source_boundary": dict(
            source_boundary
            or {
                "source_backed_claim_allowed": False,
                "source_reopen_required_before_claims": True,
            }
        ),
    }


def write_boundary(
    *,
    written: bool,
    explicit_write_required: bool = False,
    target: str | None = None,
    rollback_available: bool | None = None,
) -> dict[str, object]:
    """Machine-readable receipt for mutating or would-mutate surfaces.

    Do not infer write state from `ok`, `applied`, or human text. Some recovery
    cards are successful precisely because no write happened, and some conflict
    paths write safe side artifacts while leaving the primary local state
    unchanged. Keep this tiny helper vocabulary stable so new mutating surfaces
    do not invent one-off aliases again.
    """

    payload: dict[str, object] = {
        "written": bool(written),
        "no_write_happened": not bool(written),
        "explicit_write_required": bool(explicit_write_required),
    }
    if target:
        payload["target"] = target
    if rollback_available is not None:
        payload["rollback_available"] = bool(rollback_available)
    return payload


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
    action_fields = (
        canonical_foreground_action_fields(primary, safe_next_actions=choices)
        if primary
        else {
            "foreground_action_contract": FOREGROUND_ACTION_CONTRACT_VERSION,
            "foreground_action": {},
            "agent_next_action": {},
            "safe_next_actions": [],
        }
    )
    return {
        "kind": kind,
        "ok": True,
        "status": status,
        "surface_class": surface_class,
        "decision": decision,
        "choices": list(choices),
        **action_fields,
        "write_boundary": {
            "written": False,
            "no_write_happened": bool(no_write_happened),
            "explicit_write_required": True,
        },
    }
