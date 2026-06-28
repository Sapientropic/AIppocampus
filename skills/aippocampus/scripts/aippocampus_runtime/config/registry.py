#!/usr/bin/env python3
"""No-write registry for AIppocampus runtime environment knobs."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any, Mapping

from aippocampus_runtime.contracts import canonical_foreground_action_fields, public_envelope

CONFIG_STABILITY_BUCKETS = (
    "stable_public",
    "provider_specific",
    "experimental",
    "test_only",
    "legacy_fallback",
    "internal_maintainer",
)


@dataclass(frozen=True)
class ConfigKnob:
    name: str
    owner: str
    stability: str
    surface: str
    default: str
    sensitive: bool = False
    notes: str = ""


def _knob(
    name: str,
    owner: str,
    stability: str,
    surface: str,
    default: str = "built-in default",
    *,
    sensitive: bool = False,
    notes: str = "",
) -> ConfigKnob:
    if stability not in CONFIG_STABILITY_BUCKETS:
        raise ValueError(f"unknown config stability: {stability}")
    return ConfigKnob(name, owner, stability, surface, default, sensitive, notes)


CONFIG_KNOBS = (
    _knob("AIPPOCAMPUS_HOME", "core/registry", "stable_public", "local storage", "provider-neutral home discovery"),
    _knob("AIPPOCAMPUS_REGISTRY_DIR", "core/registry", "stable_public", "local storage", "derived from AIPPOCAMPUS_HOME"),
    _knob("AIPPOCAMPUS_GENERIC_IMPORT_DIR", "onboarding", "stable_public", "source import", "unset"),
    _knob("AIPPOCAMPUS_VAULT", "vault", "stable_public", "vault import", "unset"),
    _knob("AIPPOCAMPUS_STYLE_SOURCE", "vault", "stable_public", "vault import", "unset"),
    _knob("AIPPOCAMPUS_SCRIPT_SOURCE", "vault", "stable_public", "vault import", "unset"),
    _knob("AIPPOCAMPUS_SITE_MARK", "vault", "stable_public", "vault import", "unset"),
    _knob("AIPPOCAMPUS_SITE_TITLE", "vault", "stable_public", "vault import", "unset"),
    _knob("AIPPOCAMPUS_AGE_BIN", "sync/encrypted", "stable_public", "encrypted sync", "age"),
    _knob("AIPPOCAMPUS_AGE_KEYGEN_BIN", "sync/encrypted", "stable_public", "encrypted sync", "age-keygen"),
    _knob("AIPPOCAMPUS_OBJECT_STORE_URL", "sync/object_storage", "provider_specific", "object sync", "unset"),
    _knob("AIPPOCAMPUS_OBJECT_PROVIDER", "sync/object_storage", "provider_specific", "object sync", "auto"),
    _knob("AIPPOCAMPUS_OBJECT_BUCKET", "sync/object_storage", "provider_specific", "object sync", "unset"),
    _knob("AIPPOCAMPUS_OBJECT_REGION", "sync/object_storage", "provider_specific", "object sync", "unset"),
    _knob("AIPPOCAMPUS_OBJECT_ACCOUNT_ID", "sync/object_storage", "provider_specific", "object sync", "unset"),
    _knob("AIPPOCAMPUS_OBJECT_PREFIX", "sync/object_storage", "provider_specific", "object sync", "unset"),
    _knob("AIPPOCAMPUS_OBJECT_STORE_TOKEN", "sync/object_storage", "provider_specific", "object sync", "unset", sensitive=True),
    _knob("AIPPOCAMPUS_OBJECT_ACCESS_KEY_ID", "sync/object_storage", "provider_specific", "object sync", "unset", sensitive=True),
    _knob("AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY", "sync/object_storage", "provider_specific", "object sync", "unset", sensitive=True),
    _knob("AIPPOCAMPUS_OBJECT_SESSION_TOKEN", "sync/object_storage", "provider_specific", "object sync", "unset", sensitive=True),
    _knob("AIPPOCAMPUS_DEEPSEEK_BASE_URL", "model/routing", "provider_specific", "model routing", "provider route default"),
    _knob("AIPPOCAMPUS_DEEPSEEK_FLASH_MODEL", "model/routing", "provider_specific", "model routing", "provider route default"),
    _knob("AIPPOCAMPUS_DEEPSEEK_PRO_MODEL", "model/routing", "provider_specific", "model routing", "provider route default"),
    _knob(
        "AIPPOCAMPUS_DEEPSEEK_API_KEY",
        "model/routing",
        "provider_specific",
        "model routing",
        "unset",
        sensitive=True,
        notes="Canonical DeepSeek credential env; provider-native env names are no longer defaults.",
    ),
    _knob("AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV", "model/routing", "provider_specific", "model routing", "provider route default"),
    _knob("AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL", "model/routing", "provider_specific", "model routing", "unset"),
    _knob("AIPPOCAMPUS_OPENAI_COMPAT_CACHE_METRICS_KIND", "model/routing", "provider_specific", "model routing", "provider route default"),
    _knob("AIPPOCAMPUS_OPENAI_COMPAT_CONCURRENCY", "model/routing", "provider_specific", "model routing", "provider route default"),
    _knob("AIPPOCAMPUS_OPENAI_COMPAT_DEFAULT_REASONING_EFFORT", "model/routing", "provider_specific", "model routing", "provider route default"),
    _knob("AIPPOCAMPUS_OPENAI_COMPAT_DEFAULT_THINKING", "model/routing", "provider_specific", "model routing", "provider route default"),
    _knob("AIPPOCAMPUS_OPENAI_COMPAT_MODEL", "model/routing", "provider_specific", "model routing", "unset"),
    _knob("AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER", "model/routing", "provider_specific", "model routing", "openai-compatible"),
    _knob("AIPPOCAMPUS_OPENAI_COMPAT_REASONING_CONTENT_HANDLING", "model/routing", "provider_specific", "model routing", "provider route default"),
    _knob("AIPPOCAMPUS_OPENAI_COMPAT_ROUTE", "model/routing", "provider_specific", "model routing", "unset"),
    _knob("AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_JSON", "model/routing", "provider_specific", "model routing", "provider route default"),
    _knob("AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_REASONING_EFFORT", "model/routing", "provider_specific", "model routing", "provider route default"),
    _knob("AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_THINKING", "model/routing", "provider_specific", "model routing", "provider route default"),
    _knob("AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_USER_ID", "model/routing", "provider_specific", "model routing", "provider route default"),
    _knob("AIPPOCAMPUS_AGENT_FALLBACK_AVAILABLE", "model/routing", "provider_specific", "agent fallback", "unset"),
    _knob(
        "AIPPOCAMPUS_FOREGROUND_TOOLS_VISIBLE",
        "update/cli",
        "experimental",
        "host readiness diagnostics",
        "auto",
    ),
    _knob(
        "AIPPOCAMPUS_FOREGROUND_KEY_TOOLS_CALLABLE",
        "update/cli",
        "experimental",
        "host readiness diagnostics",
        "auto",
    ),
    _knob(
        "AIPPOCAMPUS_FOREGROUND_KEY_TOOL_FAILURE",
        "update/cli",
        "experimental",
        "host readiness diagnostics",
        "unset",
    ),
    _knob("AIPPOCAMPUS_COGNITIVE_WORKER_MODE", "model/routing", "provider_specific", "worker routing", "auto"),
    _knob("AIPPOCAMPUS_SEMANTIC_GATE", "recall", "experimental", "semantic recall", "auto"),
    _knob("AIPPOCAMPUS_SEMANTIC_TIMEOUT", "recall", "experimental", "semantic recall", "route default"),
    _knob("AIPPOCAMPUS_SEMANTIC_CATALOG_LIMIT", "recall", "experimental", "semantic recall", "route default"),
    _knob("AIPPOCAMPUS_SEMANTIC_TRIGGER_LIMIT", "recall", "experimental", "semantic recall", "route default"),
    _knob("AIPPOCAMPUS_SEMANTIC_TEMPERATURE", "recall", "experimental", "semantic recall", "route default"),
    _knob("AIPPOCAMPUS_SEMANTIC_CACHE_TTL", "recall", "experimental", "semantic recall", "built-in TTL"),
    _knob("AIPPOCAMPUS_PROMPT_HOOK_BUDGET_MS", "hooks", "stable_public", "prompt hook", "3500"),
    _knob("AIPPOCAMPUS_PROMPT_SEMANTIC_TIMEOUT", "hooks", "experimental", "prompt hook", "host-safe default"),
    _knob("AIPPOCAMPUS_PROMPT_PROBE_LIMIT", "recall", "experimental", "prompt recall", "built-in default"),
    _knob("AIPPOCAMPUS_PROMPT_SKIP_TELEMETRY", "hooks", "stable_public", "prompt hook telemetry", "enabled"),
    _knob("AIPPOCAMPUS_ACTION_HINT_AUTO_CHAIN", "hooks", "experimental", "action hint", "auto"),
    _knob("AIPPOCAMPUS_CURRENT_THREAD_KEY", "source/agent_self_note_cli", "experimental", "current-thread self-note", "unset"),
    _knob("AIPPOCAMPUS_AGENT_LAST_RECALL_PATH", "recall/agent_continuity", "experimental", "agent recall", "registry cache"),
    _knob(
        "AIPPOCAMPUS_APW_PROMOTION_MODE",
        "recall/associative_path_fallback",
        "experimental",
        "agent recall",
        "semi_default_recovery",
        notes="Use opt_in to roll APW recall recovery back to explicit fallback; off suppresses recall fallback.",
    ),
    _knob("AIPPOCAMPUS_FEEDBACK_JSONL", "controls", "experimental", "durable feedback rows", "unset"),
    _knob("AIPPOCAMPUS_LIFECYCLE_HOOK_BUDGET_MS", "hooks", "stable_public", "lifecycle hook", "15000"),
    _knob("AIPPOCAMPUS_WARM_RECALL_BACKGROUND", "warm_ambient", "experimental", "warm recall", "auto"),
    _knob("AIPPOCAMPUS_WARM_RECALL_TIMEOUT", "warm_ambient", "experimental", "warm recall", "route default"),
    _knob("AIPPOCAMPUS_WARM_RECALL_MAX_WORKERS", "warm_ambient", "experimental", "warm recall", "route default"),
    _knob("AIPPOCAMPUS_WARM_RECALL_QUORUM", "warm_ambient", "experimental", "warm recall", "route default"),
    _knob("AIPPOCAMPUS_WARM_RECALL_CATALOG_LIMIT", "warm_ambient", "experimental", "warm recall", "route default"),
    _knob("AIPPOCAMPUS_WARM_RECALL_TEMPERATURE", "warm_ambient", "experimental", "warm recall", "route default"),
    _knob("AIPPOCAMPUS_WARM_RECALL_THINKING", "warm_ambient", "experimental", "warm recall", "route default"),
    _knob("AIPPOCAMPUS_WARM_RECALL_REASONING_EFFORT", "warm_ambient", "experimental", "warm recall", "route default"),
    _knob("AIPPOCAMPUS_WARM_PREFIX_CACHE_WARMUP_DELAY", "warm_ambient", "internal_maintainer", "warm prefix cache", "built-in default"),
    _knob("AIPPOCAMPUS_WARM_PREFIX_CACHE_WARMUP_SCOUTS", "warm_ambient", "internal_maintainer", "warm prefix cache", "built-in default"),
    _knob("AIPPOCAMPUS_DETACHED_WARM_TIMEOUT", "warm_ambient", "experimental", "detached warm recall", "built-in default"),
    _knob("AIPPOCAMPUS_DETACHED_WARM_PREFIX_CACHE_WARMUP_DELAY", "warm_ambient", "internal_maintainer", "detached warm recall", "built-in default"),
    _knob("AIPPOCAMPUS_DETACHED_WARM_PREFIX_CACHE_WARMUP_SCOUTS", "warm_ambient", "internal_maintainer", "detached warm recall", "built-in default"),
    _knob("AIPPOCAMPUS_DREAM_DELIVERY_MODE", "dream", "experimental", "dream delivery", "auto"),
    _knob("AIPPOCAMPUS_DREAM_ROLLOUT_RATE", "dream", "experimental", "dream delivery", "1.0"),
    _knob("AIPPOCAMPUS_DREAM_SHADOW_AB", "dream", "experimental", "dream delivery", "disabled"),
    _knob("AIPPOCAMPUS_DREAM_SHADOW_AB_SALT", "dream", "experimental", "dream delivery", "unset", sensitive=True),
    _knob(
        "AIPPOCAMPUS_BACKGROUND_MODEL_CONSENT",
        "subconscious/dream",
        "experimental",
        "background model consent",
        "disabled",
        notes="Separate opt-in for sending background subconscious/Dream seeds to an external model; provider key visibility alone is not consent.",
    ),
    _knob("AIPPOCAMPUS_SUBCONSCIOUS_HOOK", "subconscious", "experimental", "background scheduling", "disabled"),
    _knob("AIPPOCAMPUS_SUBCONSCIOUS_JOB_CONCURRENCY", "subconscious", "experimental", "background scheduling", "4"),
    _knob("AIPPOCAMPUS_SUBCONSCIOUS_CONCURRENCY", "subconscious", "experimental", "background jobs", "4"),
    _knob("AIPPOCAMPUS_SUBCONSCIOUS_SAMPLES_PER_JOB", "subconscious", "experimental", "background jobs", "2"),
    _knob("AIPPOCAMPUS_CONTINUITY_DOMAIN_PRODUCTION", "subconscious", "experimental", "background jobs", "off"),
    _knob("AIPPOCAMPUS_SUBCONSCIOUS_STAGING_WARN_ROWS", "subconscious", "internal_maintainer", "staging maintenance", "built-in threshold"),
    _knob("AIPPOCAMPUS_SUBCONSCIOUS_STAGING_WARN_BYTES", "subconscious", "internal_maintainer", "staging maintenance", "built-in threshold"),
    _knob("AIPPOCAMPUS_LOG_MAX_BYTES", "ops/log_retention", "stable_public", "log retention", "built-in limit"),
    _knob("AIPPOCAMPUS_LOG_BACKUPS", "ops/log_retention", "stable_public", "log retention", "built-in count"),
    _knob("AIPPOCAMPUS_SPEND_WARN_EFFECTIVE_TOKENS", "ops/spend_doctor", "internal_maintainer", "spend diagnostics", "built-in threshold"),
    _knob("AIPPOCAMPUS_SPEND_WARN_MIN_FOREGROUND_VALUE_RATE", "ops/spend_doctor", "internal_maintainer", "spend diagnostics", "built-in threshold"),
    _knob("AIPPOCAMPUS_PROJECTS_TOKEN", "github/project_triage", "internal_maintainer", "GitHub Project automation", "unset", sensitive=True),
    _knob("AIPPOCAMPUS_PROJECT_OWNER", "github/project_triage", "internal_maintainer", "GitHub Project automation", "repository owner"),
    _knob("AIPPOCAMPUS_PROJECT_NUMBER", "github/project_triage", "internal_maintainer", "GitHub Project automation", "repository project"),
)

CONFIG_BY_NAME = {knob.name: knob for knob in CONFIG_KNOBS}
LOCAL_PATH_REDACTION = "<local-path-redacted>"


def config_registry_names() -> set[str]:
    return set(CONFIG_BY_NAME)


def _value_kind_for_knob(name: str) -> str:
    if name.endswith("_MS") or any(
        token in name
        for token in (
            "_LIMIT",
            "_CONCURRENCY",
            "_MAX_WORKERS",
            "_SAMPLES_PER_JOB",
            "_SCOUTS",
            "_BACKUPS",
            "_BYTES",
            "_TOKENS",
            "_WARN_ROWS",
        )
    ):
        return "positive_integer"
    if name.endswith("_TIMEOUT") or name.endswith("_RATE") or name.endswith("_TEMPERATURE"):
        return "positive_float"
    if name.endswith("_HOME") or name.endswith("_PATH") or name.endswith("_JSONL"):
        return "local_path_or_locator"
    if any(token in name for token in ("_DIR", "_BIN", "_SOURCE", "_VAULT")):
        return "local_path_or_locator"
    return "string"


def _validation_warning(name: str, value: str, value_kind: str) -> dict[str, object] | None:
    if not value.strip():
        return None
    if value_kind == "positive_integer":
        try:
            if int(value) <= 0:
                raise ValueError
        except ValueError:
            return {
                "code": "malformed_numeric_env",
                "name": name,
                "value_kind": value_kind,
            }
    if value_kind == "positive_float":
        try:
            if float(value) <= 0:
                raise ValueError
        except ValueError:
            return {
                "code": "malformed_numeric_env",
                "name": name,
                "value_kind": value_kind,
            }
    return None


def _resolved_value(
    knob: ConfigKnob,
    env: Mapping[str, str],
    *,
    include_resolved: bool,
) -> str | None:
    if not include_resolved:
        return None
    configured = bool(str(env.get(knob.name, "")).strip())
    value_kind = _value_kind_for_knob(knob.name)
    if knob.sensitive:
        return "<redacted>" if configured else ""
    if value_kind == "local_path_or_locator" and configured:
        return LOCAL_PATH_REDACTION
    if configured:
        return str(env.get(knob.name) or "")
    return "" if knob.default == "unset" else knob.default


def _public_config_entry(
    knob: ConfigKnob,
    env: Mapping[str, str],
    *,
    include_resolved: bool = False,
) -> dict[str, object]:
    configured = bool(str(env.get(knob.name, "")).strip())
    value_kind = _value_kind_for_knob(knob.name)
    entry: dict[str, object] = {
        "name": knob.name,
        "owner": knob.owner,
        "stability": knob.stability,
        "surface": knob.surface,
        "default": knob.default,
        "sensitive": knob.sensitive,
        "value_kind": value_kind,
        "configured": configured,
        "source": "env" if configured else ("default" if knob.default != "unset" else "unset"),
        "value_redacted": configured
        and (not include_resolved or knob.sensitive or value_kind == "local_path_or_locator"),
        "notes": knob.notes,
    }
    resolved = _resolved_value(knob, env, include_resolved=include_resolved)
    if resolved is not None:
        entry["resolved_value"] = resolved
    return entry


def config_report(
    env: Mapping[str, str] | None = None,
    *,
    include_resolved: bool = False,
) -> dict[str, object]:
    current_env = env if env is not None else os.environ
    sorted_knobs = sorted(CONFIG_KNOBS, key=lambda item: item.name)
    registered = [
        _public_config_entry(knob, current_env, include_resolved=include_resolved)
        for knob in sorted_knobs
    ]
    unknown_names = sorted(
        name for name in current_env if name.startswith("AIPPOCAMPUS_") and name not in CONFIG_BY_NAME
    )
    warnings: list[dict[str, object]] = [
        {"code": "unregistered_aippocampus_env", "name": name}
        for name in unknown_names
    ]
    for knob in sorted_knobs:
        warning = _validation_warning(
            knob.name,
            str(current_env.get(knob.name, "")),
            _value_kind_for_knob(knob.name),
        )
        if warning is not None:
            warnings.append(warning)
    status = "partial" if warnings else "ok"
    return public_envelope(
        ok=True,
        status=status,
        data={
            "kind": "aippocampus_config_registry_report",
            "no_write": True,
            "value_policy": (
                "safe non-sensitive resolved values included; secrets and local paths redacted"
                if include_resolved
                else "values are never printed; configured values are presence-only"
            ),
            "knobs": registered,
            "stability_buckets": list(CONFIG_STABILITY_BUCKETS),
            "unknown_count": len(unknown_names),
            "resolved_values_included": include_resolved,
        },
        warnings=warnings,
        cannot_claim=[
            "config_report_does_not_validate_secret_values",
            "config_report_does_not_probe_provider_connectivity",
        ],
    )


def config_knob_detail_report(
    name: str,
    env: Mapping[str, str] | None = None,
    *,
    include_resolved: bool = False,
) -> dict[str, object]:
    normalized = str(name or "").strip().upper()
    knob = CONFIG_BY_NAME.get(normalized)
    if knob is None:
        return {
            "schema_version": 1,
            "kind": "aippocampus_config_knob_detail",
            "ok": False,
            "status": "unknown_config_knob",
            "name": normalized,
            "known_count": len(CONFIG_BY_NAME),
            "privacy": {"values_printed": False},
        }
    current_env = env if env is not None else os.environ
    entry = _public_config_entry(knob, current_env, include_resolved=include_resolved)
    value_kind = _value_kind_for_knob(knob.name)
    warning = _validation_warning(
        knob.name,
        str(current_env.get(knob.name, "")),
        value_kind,
    )
    return {
        "schema_version": 1,
        "kind": "aippocampus_config_knob_detail",
        "ok": True,
        "status": "ok" if warning is None else "partial",
        "knob": entry,
        "warnings": [warning] if warning else [],
        "privacy": {
            "values_printed": include_resolved and not knob.sensitive and value_kind != "local_path_or_locator",
            "secret_values_printed": False,
            "local_paths_printed": False,
        },
        "claim_boundary": "config diagnostics are local setup state, not source evidence",
    }


def config_summary_report(report: Mapping[str, object]) -> dict[str, object]:
    raw_data = report.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    raw_knobs = data.get("knobs")
    knobs: list[Any] = raw_knobs if isinstance(raw_knobs, list) else []
    configured = [item for item in knobs if isinstance(item, dict) and item.get("configured")]
    configured_sensitive = [item for item in configured if item.get("sensitive")]
    unknown_count = int(data.get("unknown_count") or 0)
    raw_warnings = report.get("warnings")
    warnings: list[Any] = raw_warnings if isinstance(raw_warnings, list) else []
    full_audit_command = "aippocampus doctor config --detail full --json"
    operator_json_command = "aippocampus doctor config --operator-json"
    safe_next_actions: list[dict[str, object]] = [
        {
            "id": "open_full_config_inventory",
            "label": "Open full config inventory",
            "command": full_audit_command,
            "mutation_risk": "read_only",
            "claim_boundary": "operator_diagnostic_not_source_evidence",
            "why": "Use the operator report only when you need the full registered knob inventory.",
        }
    ]
    if unknown_count:
        foreground_action = {
            "id": "review_unknown_config_env",
            "label": "Review unknown AIPPOCAMPUS_* env names",
            "command": full_audit_command,
            "why": "Unknown AIPPOCAMPUS_* names do not affect runtime unless registered; inspect before treating them as live configuration.",
            "unknown_env_var_count": unknown_count,
            "mutation_risk": "read_only",
            "claim_boundary": "operator_diagnostic_not_source_evidence",
        }
        recommended_actions = [
            {
                "id": "review_unknown_config_env",
                "message": "Review unknown AIPPOCAMPUS_* environment names before assuming they affect runtime behavior.",
            }
        ]
    else:
        foreground_action = {
            "id": "no_action_needed",
            "label": "No config action needed",
            "message": "No foreground config action is needed from this compact doctor card.",
            "why": "All observed AIPPOCAMPUS_* environment names are registered; open the full inventory only for operator audit.",
            "mutation_risk": "read_only",
            "claim_boundary": "operator_diagnostic_not_source_evidence",
            "continue_without_command": True,
        }
        recommended_actions = []
    action_fields = canonical_foreground_action_fields(
        foreground_action,
        safe_next_actions=[foreground_action, *safe_next_actions],
    )
    return {
        "schema_version": 1,
        "kind": "aippocampus_config_doctor_summary",
        "ok": bool(report.get("ok")),
        "status": str(report.get("status") or "unknown"),
        "detail": "compact",
        "surface": "foreground_decision_card",
        "registered_knob_count": len(knobs),
        "unknown_env_var_count": unknown_count,
        "configured_count": len(configured),
        "configured_sensitive_count": len(configured_sensitive),
        "warning_count": len(warnings),
        "warnings": warnings[:5],
        **action_fields,
        "recommended_actions": recommended_actions,
        "audit_json_available": True,
        "full_audit_command": full_audit_command,
        "operator_json_available": {
            "detail_full_command": full_audit_command,
            "operator_json_command": operator_json_command,
        },
        "privacy": {
            "values_printed": False,
            "configured_values_presence_only": True,
            "local_paths_included": False,
            "unknown_env_values_printed": False,
            "provider_connectivity_probe_performed": False,
        },
        "claim_boundary": {
            "can_use_for": "foreground config/navigation decision",
            "must_open_operator_report_for": "full registered knob inventory and cannot_claim boundaries",
            "does_not_validate_secret_values": True,
            "does_not_probe_provider_connectivity": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report registered AIppocampus configuration knobs.")
    parser.add_argument("command", nargs="?", default="report", choices=("report", "describe"))
    parser.add_argument("knob", nargs="?")
    parser.add_argument("--resolved", action="store_true", help="Include non-sensitive resolved values.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument(
        "--detail",
        choices=["compact", "full"],
        default="compact",
        help="JSON detail level. Default --json emits a compact foreground decision card.",
    )
    parser.add_argument(
        "--operator-json",
        action="store_true",
        help="Emit the full operator knob inventory JSON; implies JSON output.",
    )
    parser.add_argument(
        "--compact-json",
        "--summary",
        action="store_true",
        dest="summary_json",
        help="Emit compact foreground-agent JSON instead of the full knob catalog.",
    )
    args = parser.parse_args(argv)

    if args.command == "describe":
        if not args.knob:
            parser.error("config describe requires a knob name")
        detail = config_knob_detail_report(args.knob, include_resolved=args.resolved)
        if args.json:
            print(json.dumps(detail, ensure_ascii=False, indent=2))
        else:
            raw_knob = detail.get("knob")
            knob: dict[str, Any] = raw_knob if isinstance(raw_knob, dict) else {}
            if not detail.get("ok"):
                print(f"config knob: {detail.get('name')} not registered")
            else:
                print(f"config knob: {knob.get('name')}")
                print(f"- surface: {knob.get('surface')}")
                print(f"- default: {knob.get('default')}")
                print(f"- source: {knob.get('source')}")
                if args.resolved:
                    print(f"- resolved: {knob.get('resolved_value', '')}")
                if knob.get("notes"):
                    print(f"- notes: {knob.get('notes')}")
        return 0 if detail.get("ok") else 2

    report = config_report(include_resolved=args.resolved)
    full_detail_json = bool(args.operator_json or args.detail == "full")
    if args.summary_json:
        print(json.dumps(config_summary_report(report), ensure_ascii=False))
    elif args.json and not full_detail_json:
        print(json.dumps(config_summary_report(report), ensure_ascii=False, indent=2))
    elif args.json or args.operator_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        raw_data = report.get("data")
        data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
        knobs = data.get("knobs") if isinstance(data, dict) else []
        unknown_count = data.get("unknown_count") if isinstance(data, dict) else 0
        knob_count = len(knobs) if isinstance(knobs, list) else 0
        print(
            f"config report: status={report['status']} "
            f"knobs={knob_count} unknown={unknown_count}"
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
