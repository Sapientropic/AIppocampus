#!/usr/bin/env python3
"""No-write registry for AIppocampus runtime environment knobs."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Mapping

from aippocampus_runtime.contracts import public_envelope

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
    _knob("AIPPOCAMPUS_COGNITIVE_WORKER_MODE", "model/routing", "provider_specific", "worker routing", "auto"),
    _knob("AIPPOCAMPUS_SEMANTIC_GATE", "recall", "experimental", "semantic recall", "auto"),
    _knob("AIPPOCAMPUS_SEMANTIC_TIMEOUT", "recall", "experimental", "semantic recall", "route default"),
    _knob("AIPPOCAMPUS_SEMANTIC_CATALOG_LIMIT", "recall", "experimental", "semantic recall", "route default"),
    _knob("AIPPOCAMPUS_SEMANTIC_TRIGGER_LIMIT", "recall", "experimental", "semantic recall", "route default"),
    _knob("AIPPOCAMPUS_SEMANTIC_TEMPERATURE", "recall", "experimental", "semantic recall", "route default"),
    _knob("AIPPOCAMPUS_SEMANTIC_CACHE_TTL", "recall", "experimental", "semantic recall", "built-in TTL"),
    _knob("AIPPOCAMPUS_PROMPT_HOOK_BUDGET_MS", "hooks", "stable_public", "prompt hook", "host-safe default"),
    _knob("AIPPOCAMPUS_PROMPT_SEMANTIC_TIMEOUT", "hooks", "experimental", "prompt hook", "host-safe default"),
    _knob("AIPPOCAMPUS_PROMPT_PROBE_LIMIT", "recall", "experimental", "prompt recall", "built-in default"),
    _knob("AIPPOCAMPUS_PROMPT_SKIP_TELEMETRY", "hooks", "stable_public", "prompt hook telemetry", "enabled"),
    _knob("AIPPOCAMPUS_LIFECYCLE_HOOK_BUDGET_MS", "hooks", "stable_public", "lifecycle hook", "host-safe default"),
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
    _knob("AIPPOCAMPUS_SUBCONSCIOUS_HOOK", "subconscious", "experimental", "background scheduling", "enabled"),
    _knob("AIPPOCAMPUS_SUBCONSCIOUS_JOB_CONCURRENCY", "subconscious", "experimental", "background scheduling", "4"),
    _knob("AIPPOCAMPUS_SUBCONSCIOUS_CONCURRENCY", "subconscious", "experimental", "background jobs", "4"),
    _knob("AIPPOCAMPUS_SUBCONSCIOUS_SAMPLES_PER_JOB", "subconscious", "experimental", "background jobs", "2"),
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


def config_registry_names() -> set[str]:
    return set(CONFIG_BY_NAME)


def _public_config_entry(knob: ConfigKnob, env: Mapping[str, str]) -> dict[str, object]:
    configured = bool(str(env.get(knob.name, "")).strip())
    return {
        "name": knob.name,
        "owner": knob.owner,
        "stability": knob.stability,
        "surface": knob.surface,
        "default": knob.default,
        "sensitive": knob.sensitive,
        "configured": configured,
        "source": "env" if configured else ("default" if knob.default != "unset" else "unset"),
        "value_redacted": configured,
        "notes": knob.notes,
    }


def config_report(env: Mapping[str, str] | None = None) -> dict[str, object]:
    current_env = env if env is not None else os.environ
    registered = [_public_config_entry(knob, current_env) for knob in sorted(CONFIG_KNOBS, key=lambda item: item.name)]
    unknown_names = sorted(
        name for name in current_env if name.startswith("AIPPOCAMPUS_") and name not in CONFIG_BY_NAME
    )
    warnings = [
        {"code": "unregistered_aippocampus_env", "name": name}
        for name in unknown_names
    ]
    status = "partial" if warnings else "ok"
    return public_envelope(
        ok=True,
        status=status,
        data={
            "kind": "aippocampus_config_registry_report",
            "no_write": True,
            "value_policy": "values are never printed; configured values are presence-only",
            "knobs": registered,
            "stability_buckets": list(CONFIG_STABILITY_BUCKETS),
            "unknown_count": len(unknown_names),
        },
        warnings=warnings,
        cannot_claim=[
            "config_report_does_not_validate_secret_values",
            "config_report_does_not_probe_provider_connectivity",
        ],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report registered AIppocampus configuration knobs.")
    parser.add_argument("command", nargs="?", default="report", choices=("report",))
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    args = parser.parse_args(argv)

    report = config_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        data = report["data"]
        print(f"config report: status={report['status']} knobs={len(data['knobs'])} unknown={data['unknown_count']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
