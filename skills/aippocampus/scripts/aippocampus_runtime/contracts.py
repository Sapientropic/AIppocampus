"""Shared public-boundary vocabulary for AIppocampus runtime surfaces.

This module is deliberately small. It gives CLI, MCP, hook, ops, and generated
report owners a common language without forcing precise internal sidecars into a
generic schema. Source authority still belongs to clean source, source refs, and
domain-specific gates; these constants only classify observable runtime state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from aippocampus_runtime.contract_command_safety import (
    EXECUTABLE_COMMAND_FIELDS,  # noqa: F401 - re-exported public contract constant
    command_value_is_non_runnable_marker,
    command_value_needs_input,  # noqa: F401 - re-exported public helper
    executable_command_violations,  # noqa: F401 - re-exported public helper
    shell_quote,  # noqa: F401 - re-exported public helper
)

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

FOREGROUND_ACTION_CONTRACT_VERSION = "foreground-action-v2"
READINESS_CARD_CONTRACT_VERSION = "readiness-card-v1"

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
    max_safe_next_actions: int | None = None,
    safe_next_read_only_only: bool = False,
) -> dict[str, object]:
    """Return the shared foreground action field set for compact cards.

    `foreground_action` is the authoritative primary action. In
    ``foreground-action-v2`` the default compact shape no longer repeats the
    same object through ``agent_next_action`` or ``safe_next_actions[0]``:
    repeated primary aliases made foreground cards heavier and drift-prone.
    ``safe_next_actions`` now carries true alternatives or follow-up actions.

    See ``docs/architecture/ops/json-compatibility-inventory.md`` before
    reviving any retired alias.
    """

    primary = normalize_foreground_action(foreground_action)
    primary_keys = _foreground_action_semantic_keys(primary)
    seen_alternate_keys: set[tuple[str, str]] = set()
    alternates = []
    for action in (safe_next_actions or []):
        if not action:
            continue
        normalized = normalize_foreground_action(action)
        if safe_next_read_only_only and not foreground_action_is_read_only(normalized):
            continue
        semantic_keys = _foreground_action_semantic_keys(normalized)
        if normalized == primary or semantic_keys.intersection(primary_keys):
            continue
        if semantic_keys.intersection(seen_alternate_keys):
            continue
        if normalized not in alternates:
            alternates.append(normalized)
            seen_alternate_keys.update(semantic_keys)
        if max_safe_next_actions is not None and len(alternates) >= max_safe_next_actions:
            break
    payload: dict[str, object] = {
        "foreground_action_contract": FOREGROUND_ACTION_CONTRACT_VERSION,
        "foreground_action": primary,
        "safe_next_actions": alternates,
    }
    return payload


def foreground_action_is_read_only(action: Mapping[str, object]) -> bool:
    """Return whether an action is safe for default compact foreground menus.

    Compact foreground surfaces are the path a later agent will most likely
    execute without further deliberation. Keep write-capable operations out of
    `safe_next_actions` unless a call site deliberately exposes a consented
    write section. This helper is intentionally vocabulary-based so new
    mutation risks do not become implicitly safe just because they are novel.
    """

    mutation_risk = str(action.get("mutation_risk") or "").strip()
    return mutation_risk in {
        "read_only",
        "read_only_preview",
        "read_only_preview_of_delete",
    }


def _normalized_action_command(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def _foreground_action_semantic_keys(action: Mapping[str, object]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    action_id = str(action.get("id") or "").strip().casefold()
    if action_id:
        keys.add(("id", action_id))
    command = _normalized_action_command(action.get("command"))
    if command:
        keys.add(("command", command))
        keys.add(("action_text", command))
    command_template = _normalized_action_command(action.get("command_template"))
    if command_template:
        keys.add(("command_template", command_template))
        keys.add(("action_text", command_template))
    return keys


def strip_foreground_action_legacy_aliases(value: object) -> object:
    """Return public JSON with duplicated v1 foreground action aliases removed.

    ``foreground_action`` is the only primary action in v2. This sanitizer is a
    boundary backstop for older cards that still build ``agent_next_action`` or
    repeat the primary in ``safe_next_actions``. It intentionally does not touch
    nested row-level action fields unless a mapping also carries a canonical
    ``foreground_action``; those fields are domain data, not v1 compatibility
    mirrors.
    """

    if isinstance(value, list):
        return [strip_foreground_action_legacy_aliases(item) for item in value]
    if not isinstance(value, Mapping):
        return value
    payload = {
        key: strip_foreground_action_legacy_aliases(item)
        for key, item in value.items()
    }
    foreground = payload.get("foreground_action")
    if not isinstance(foreground, Mapping):
        return payload
    foreground_dict = dict(foreground)
    payload["foreground_action_contract"] = FOREGROUND_ACTION_CONTRACT_VERSION
    payload.pop("agent_next_action", None)
    next_safe_action = payload.get("next_safe_action")
    if isinstance(next_safe_action, Mapping) and dict(next_safe_action) == foreground_dict:
        payload.pop("next_safe_action", None)
    safe_actions = payload.get("safe_next_actions")
    if isinstance(safe_actions, Sequence) and not isinstance(safe_actions, str):
        alternates = []
        for action in safe_actions:
            if not isinstance(action, Mapping):
                continue
            action_dict = dict(action)
            if action_dict == foreground_dict or action_dict in alternates:
                continue
            alternates.append(action_dict)
        payload["safe_next_actions"] = alternates
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
    """Lint compact-card action fields against the foreground-action contract."""

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
    primary_keys = _foreground_action_semantic_keys(foreground)
    seen_safe_keys: dict[tuple[str, str], int] = {}
    violations.extend(_foreground_action_shape_violations(foreground, field="foreground_action"))
    violations.extend(_command_template_marker_violations(foreground, field="foreground_action"))
    if isinstance(agent_next, Mapping):
        violations.append(
            {
                "field": "agent_next_action",
                "reason": "legacy_alias_removed_from_foreground_action_v2",
            }
        )
    if isinstance(safe_actions, Sequence) and not isinstance(safe_actions, str):
        for index, action in enumerate(safe_actions):
            if not isinstance(action, Mapping):
                continue
            if dict(action) == foreground_dict:
                violations.append(
                    {
                        "field": f"safe_next_actions.{index}",
                        "reason": "primary_action_must_not_be_repeated_in_safe_next_actions",
                    }
                )
            action_keys = _foreground_action_semantic_keys(action)
            if action_keys.intersection(primary_keys):
                violations.append(
                    {
                        "field": f"safe_next_actions.{index}",
                        "reason": "primary_action_semantically_repeated_in_safe_next_actions",
                    }
                )
            for action_key in action_keys:
                first_index = seen_safe_keys.get(action_key)
                if first_index is not None:
                    violations.append(
                        {
                            "field": f"safe_next_actions.{index}",
                            "reason": "duplicate_safe_next_action_semantic_key",
                        }
                    )
                    break
                seen_safe_keys[action_key] = index
            violations.extend(_command_template_marker_violations(action, field=f"safe_next_actions.{index}"))
        if any(not isinstance(action, Mapping) for action in safe_actions):
            violations.append(
                {
                    "field": "safe_next_actions",
                    "reason": "safe_next_actions_items_must_be_objects",
                }
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
    requires = action.get("requires")
    if isinstance(requires, str):
        violations.append(
            {
                "field": f"{field}.requires",
                "reason": "requires_must_be_list",
            }
        )
    elif isinstance(requires, Sequence) and not isinstance(requires, (str, bytes)):
        for index, item in enumerate(requires):
            if not isinstance(item, str) or not item.strip():
                violations.append(
                    {
                        "field": f"{field}.requires.{index}",
                        "reason": "requires_items_must_be_nonempty_strings",
                    }
                )
    template = action.get("command_template")
    if isinstance(template, str) and ("<" in template or ">" in template):
        violations.append(
            {
                "field": f"{field}.command_template",
                "reason": "command_template_must_use_brace_placeholders",
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
        canonical_foreground_action_fields(
            primary,
            safe_next_actions=choices,
            max_safe_next_actions=2,
            safe_next_read_only_only=True,
        )
        if primary
        else {
            "foreground_action_contract": FOREGROUND_ACTION_CONTRACT_VERSION,
            "foreground_action": {},
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
