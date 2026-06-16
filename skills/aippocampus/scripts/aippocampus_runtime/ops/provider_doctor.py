#!/usr/bin/env python3
"""Human-facing live-provider visibility diagnostics.

This command answers one narrow operator question by default: can the process that runs
AIppocampus, and a child process like a Codex hook, see the API-key environment
variable required by the selected model route? It intentionally does not read
`.env` files, credential stores, or keychain entries; those can prove a key
exists somewhere, but not that the hook process inherits it.

The explicit `--discover-credential-sources` mode is onboarding-only. It can
inspect current-process env and user-specified `.env` files to report redacted
candidate shape and optional validation status, but it still does not change the
runtime rule: hooks and model workers read credentials from environment variables.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime.cognitive_worker_mode import resolve_cognitive_worker_mode
from aippocampus_runtime.legacy_aliases import env_legacy_alias_diagnostics
from aippocampus_runtime.model.routing import ModelRoute, resolve_model_route
from aippocampus_runtime.ops.provider_credentials import (
    CredentialValidator,
    build_credential_discovery_report,
)
from aippocampus_runtime.public_output import emit_public_text
from aippocampus_runtime.recall.semantic_recall_gate import semantic_gate_enabled
from aippocampus_runtime.warm_ambient.scheduler import warm_background_enabled

SCHEMA_VERSION = 1
DEFAULT_PROVIDER_ENV_VAR = "DEEPSEEK" + "_API_KEY"
ROUTE_PROVIDER_ENV_ATTR = "api" + "_key_env"


def _public_token(value: Any, *, fallback: str = "unknown", limit: int = 96) -> str:
    text = str(value or "").strip()
    clean = "".join(char for char in text[:limit] if char.isalnum() or char in {"_", "-", "."})
    return clean or fallback


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _child_process_env_visibility(env_var: str) -> dict[str, Any]:
    # Presence-only by design: reading even a non-empty/empty boolean from the
    # key value would turn this doctor into credential inspection.
    script = "import os, sys; sys.exit(0 if sys.argv[1] in os.environ else 2)"
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script, env_var],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError as exc:
        return {
            "checked": True,
            "visible": False,
            "error": {"code": "child_env_check_failed", "message": str(exc)},
        }
    return {"checked": True, "visible": proc.returncode == 0, "exit_code": proc.returncode}


def _env_var_is_visible(env_var: str) -> bool:
    # Keep this as membership, not get(): the doctor must not touch key values.
    return bool(env_var and env_var in os.environ)


def _public_route(route: ModelRoute, *, requested_route: str) -> dict[str, Any]:
    capabilities = route.capabilities.as_dict() if route.capabilities else {}
    return {
        "requested_route": _public_token(requested_route or "default"),
        "resolved_route": _public_token(route.route),
        "provider": _public_token(route.provider),
        "tier": _public_token(route.tier),
        "model": _public_token(route.model),
        "provider_env_var": _public_token(_route_provider_env_var(route), fallback=DEFAULT_PROVIDER_ENV_VAR),
        "base_url_configured": bool(route.base_url),
        "base_url_value_printed": False,
        "capabilities": capabilities,
    }


def _route_provider_env_var(route: ModelRoute) -> str:
    return str(getattr(route, ROUTE_PROVIDER_ENV_ATTR, "") or "").strip()


def _semantic_gate_visible_for_route(*, current_visible: bool, provider_env_var: str) -> bool:
    kwargs: dict[str, Any] = {
        "api" + "_key": "present" if current_visible else None,
        "api" + "_key_env": provider_env_var or DEFAULT_PROVIDER_ENV_VAR,
    }
    return semantic_gate_enabled(**kwargs)


def _recommended_actions(
    *,
    provider_env_var: str,
    current_visible: bool,
    child_visible: bool | None,
) -> list[dict[str, str]]:
    if current_visible and child_visible is not False:
        return []
    env_name = _public_token(provider_env_var, fallback=DEFAULT_PROVIDER_ENV_VAR)
    if not current_visible:
        return [
            {
                "id": "set_provider_env_in_hook_environment",
                "message": (
                    f"Set {env_name} in the environment that launches Codex or the hook process; "
                    "a key stored in a separate .env file or credential store is not automatically visible."
                ),
            }
        ]
    return [
        {
            "id": "check_child_process_environment_inheritance",
            "message": (
                f"{env_name} is visible in the current process but not in a child process; "
                "check the launcher or hook environment inheritance."
            ),
        }
    ]


def build_provider_doctor_report(
    *,
    model_route: str | None = "default",
    provider_env_var: str | None = None,
    check_child_process: bool = True,
    discover_credential_sources: bool = False,
    credential_dotenv_paths: list[Path] | None = None,
    include_local_paths: bool = False,
    validate_credentials: bool = False,
    credential_validator: CredentialValidator | None = None,
) -> dict[str, Any]:
    requested_route = str(model_route or "default").strip() or "default"
    try:
        route = resolve_model_route(requested_route)
    except ValueError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "aippocampus_provider_doctor",
            "ok": False,
            "status": "route_config_error",
            "route": {
                "requested_route": _public_token(requested_route),
                "error": {"code": "route_config_error", "message": str(exc)},
            },
            "provider_env": {"checked": False, "value_printed": False},
            "hook_relevance": {
                "prompt_hook_reads_process_env": True,
                "does_not_read_dotenv_or_credential_store": True,
                "actual_installed_hook_process_checked": False,
                "diagnostic_scope": "current process route configuration only",
            },
            "privacy": {
                "env_var_value_printed": False,
                "local_paths_included": False,
                "base_url_value_printed": False,
                "checked_env_var_names": [],
            },
            "recommended_actions": [
                {
                    "id": "complete_model_route_configuration",
                    "message": "Complete the configured model route before checking provider key visibility.",
                }
            ],
        }

    resolved_provider_env_var = str(provider_env_var or _route_provider_env_var(route) or "").strip()
    public_env_name = _public_token(resolved_provider_env_var, fallback=DEFAULT_PROVIDER_ENV_VAR)
    current_visible = _env_var_is_visible(resolved_provider_env_var)
    legacy_aliases = env_legacy_alias_diagnostics()
    cognitive_worker = resolve_cognitive_worker_mode(
        api_key_env=resolved_provider_env_var,
        provider_key_visible=current_visible,
    )
    child_visibility = (
        _child_process_env_visibility(resolved_provider_env_var)
        if check_child_process and resolved_provider_env_var
        else {"checked": False, "visible": None}
    )
    child_visible_value = child_visibility.get("visible")
    child_visible = bool(child_visible_value) if isinstance(child_visible_value, bool) else None
    ok = current_visible and child_visible is not False
    if ok:
        status = "ready"
    elif not current_visible:
        status = "missing_provider_env_var"
    else:
        status = "child_process_missing_provider_env_var"

    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_provider_doctor",
        "ok": ok,
        "status": status,
        "route": _public_route(route, requested_route=requested_route),
        "provider_env": {
            "checked": True,
            "env_var": public_env_name,
            "visible_in_current_process": current_visible,
            "visible_in_child_process": child_visible,
            "child_process_check": child_visibility,
            "presence_only": True,
            "value_checked": False,
            "value_printed": False,
        },
        "legacy_aliases": legacy_aliases,
        "cognitive_worker": cognitive_worker,
        "hook_relevance": {
            "prompt_hook_reads_process_env": True,
            "does_not_read_dotenv_or_credential_store": True,
            "actual_installed_hook_process_checked": False,
            "semantic_gate_enabled_for_route": _semantic_gate_visible_for_route(
                current_visible=current_visible,
                provider_env_var=resolved_provider_env_var,
            ),
            "warm_background_enabled": warm_background_enabled(),
            "diagnostic_scope": (
                "current process and child process environment; run from the same launcher "
                "environment that will start the Codex hook. This does not inspect a previously "
                "started Codex Desktop hook process."
            ),
        },
        "privacy": {
            "env_var_value_printed": False,
            "env_var_value_checked": False,
            "local_paths_included": False,
            "base_url_value_printed": False,
            "checked_env_var_names": [public_env_name],
            "legacy_alias_values_printed": False,
            "credential_discovery_values_printed": False,
        },
        "recommended_actions": _recommended_actions(
            provider_env_var=resolved_provider_env_var,
            current_visible=current_visible,
            child_visible=child_visible,
        ),
    }
    if discover_credential_sources:
        report["credential_discovery"] = build_credential_discovery_report(
            route=route,
            provider_env_var=resolved_provider_env_var,
            dotenv_paths=credential_dotenv_paths,
            include_local_paths=include_local_paths,
            validate_credentials=validate_credentials,
            credential_validator=credential_validator,
        )
    return report


def render_text(report: dict[str, Any]) -> str:
    route = _as_dict(report.get("route"))
    provider_env = _as_dict(report.get("provider_env"))
    lines = [
        "AIppocampus provider doctor",
        f"- Status: {report.get('status')}",
        f"- Route: {route.get('provider', 'unknown')} / {route.get('model', 'unknown')}",
    ]
    if provider_env.get("checked"):
        lines.extend(
            [
                f"- Provider env: {provider_env.get('env_var')}",
                f"- Visible in current process: {str(provider_env.get('visible_in_current_process')).lower()}",
                f"- Visible in child process: {str(provider_env.get('visible_in_child_process')).lower()}",
                "- Privacy: key value not printed; base URL value not printed; local paths omitted",
            ]
        )
    else:
        lines.append("- Key env: not checked because route configuration failed")
    cognitive_worker = _as_dict(report.get("cognitive_worker"))
    if cognitive_worker:
        lines.append(f"- Cognitive worker mode: {cognitive_worker.get('status', 'unknown')}")
    for action in report.get("recommended_actions") or []:
        if isinstance(action, dict) and action.get("message"):
            lines.append(f"- Next: {action['message']}")
    lines.append("")
    return "\n".join(lines)


def render_config_text(report: dict[str, Any]) -> str:
    data = _as_dict(report.get("data"))
    knobs = list(data.get("knobs") or [])
    configured = [
        item for item in knobs if isinstance(item, dict) and item.get("configured")
    ]
    configured_sensitive = [item for item in configured if item.get("sensitive")]
    cannot_claim = list(report.get("cannot_claim") or [])
    lines = [
        "AIppocampus config doctor",
        f"- Status: {report.get('status')}",
        f"- Registered knobs: {len(knobs)}",
        f"- Configured env vars: {len(configured)}",
        f"- Sensitive env vars present: {len(configured_sensitive)}",
        f"- Unknown AIPPOCAMPUS_* env vars: {data.get('unknown_count', 0)}",
        f"- Warnings: {len(report.get('warnings') or [])}",
        "- Cannot claim: config presence does not validate secret values or provider connectivity",
        "- Privacy: values are not printed; configured values are presence-only",
        "- Next: use `aippocampus doctor provider` when you need provider/key connectivity readiness.",
        "",
    ]
    if cannot_claim:
        lines.append("- Detail: " + ", ".join(str(item) for item in cannot_claim[:3]))
        lines.append("")
    return "\n".join(lines)


def public_json_text(report: dict[str, Any]) -> str:
    """Serialize the provider doctor public report.

    Provider doctor output intentionally reports key presence and public env var
    names only. Explicit credential discovery may read candidate values for
    shape/probe status, but it never prints those values; tests assert that
    boundary.
    """

    return json.dumps(report, ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aippocampus doctor",
        description=(
            "Task-first diagnostics:\n"
            "  provider  Check whether optional LLM/provider keys are visible to this launcher.\n"
            "  spend     Review local model-spend/yield aggregates without prompts or keys.\n"
            "  config    Audit registered AIPPOCAMPUS_* knobs without printing values."
        ),
        epilog=(
            "Doctor commands are local diagnostics, not recall results. Basic "
            "source-backed search and recall still work without provider keys."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    provider_parser = subparsers.add_parser(
        "provider",
        usage="aippocampus doctor provider [--json] [advanced diagnostics]",
        help="Check whether the selected model route key is visible to this process.",
        description=(
            "Provider doctor answers: can optional LLM-backed semantic/background "
            "routes see the configured key from this launcher or a child process?\n\n"
            "Normal examples:\n"
            "  aippocampus doctor provider\n"
            "  aippocampus doctor provider --json\n"
            "  aippocampus doctor provider --discover-credential-sources --credential-dotenv <path> --json"
        ),
        epilog=(
            "Privacy boundary: key values and base URLs are never printed. "
            "No-key source-backed recall/search remains usable."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    provider_parser.add_argument("--model-route", default="default")
    provider_parser.add_argument("--provider-env-var", dest="provider_env_var")
    provider_parser.add_argument("--api-key-env", dest="provider_env_var")
    provider_parser.add_argument("--no-child-check", action="store_true")
    provider_parser.add_argument("--discover-credential-sources", action="store_true")
    provider_parser.add_argument("--credential-dotenv", action="append", default=[])
    provider_parser.add_argument("--include-local-paths", action="store_true")
    provider_parser.add_argument("--validate-credentials", action="store_true")
    provider_parser.add_argument("--json", action="store_true", dest="json_output")
    spend_parser = subparsers.add_parser(
        "spend",
        usage="aippocampus doctor spend [--json] [threshold options]",
        help="Report private-safe local model spend and foreground yield.",
        description=(
            "Spend doctor answers: are optional model-backed routes spending tokens "
            "and producing foreground value?\n\n"
            "Normal examples:\n"
            "  aippocampus doctor spend\n"
            "  aippocampus doctor spend --json"
        ),
        epilog="Privacy boundary: aggregate counts only; no prompts, keys, or source text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    spend_parser.add_argument("--registry-dir")
    spend_parser.add_argument("--days", type=int, default=7)
    spend_parser.add_argument("--warning-effective-tokens", type=int, default=None)
    spend_parser.add_argument("--warning-min-foreground-value-rate", type=float, default=None)
    spend_parser.add_argument("--json", action="store_true", dest="json_output")
    config_parser = subparsers.add_parser(
        "config",
        usage="aippocampus doctor config [--compact-json|--json]",
        help="Report registered AIPPOCAMPUS_* configuration without printing values.",
        description=(
            "Config doctor answers: which AIppocampus configuration knobs are "
            "known/configured without revealing their values?\n\n"
            "Normal examples:\n"
            "  aippocampus doctor config --compact-json\n"
            "  aippocampus doctor config --json"
        ),
        epilog="Privacy boundary: values are never printed; configured means presence only.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    config_parser.add_argument("--json", action="store_true", dest="json_output")
    config_parser.add_argument(
        "--compact-json",
        "--summary",
        action="store_true",
        dest="summary_json",
        help="Emit compact foreground-agent JSON instead of the full knob catalog.",
    )
    args = parser.parse_args(argv)

    if args.command == "spend":
        from aippocampus_runtime.ops import spend_doctor  # noqa: PLC0415

        kwargs: dict[str, Any] = {}
        if args.warning_effective_tokens is not None:
            kwargs["warn_effective_tokens"] = args.warning_effective_tokens
        if args.warning_min_foreground_value_rate is not None:
            kwargs["warn_min_foreground_value_rate"] = args.warning_min_foreground_value_rate
        report = spend_doctor.build_spend_doctor_report(
            registry_dir=args.registry_dir,
            days=args.days,
            **kwargs,
        )
        if args.json_output:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(spend_doctor.render_text(report))
        return 0

    if args.command == "config":
        from aippocampus_runtime.config import registry as config_registry  # noqa: PLC0415

        report = config_registry.config_report()
        if args.summary_json:
            print(
                json.dumps(
                    config_registry.config_summary_report(report),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.json_output:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(render_config_text(report))
        return 0

    report = build_provider_doctor_report(
        model_route=args.model_route,
        provider_env_var=args.provider_env_var,
        check_child_process=not args.no_child_check,
        discover_credential_sources=args.discover_credential_sources,
        credential_dotenv_paths=[Path(path) for path in args.credential_dotenv],
        include_local_paths=args.include_local_paths,
        validate_credentials=args.validate_credentials,
    )
    if args.json_output:
        emit_public_text(public_json_text(report))
    else:
        emit_public_text(render_text(report), end="")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
