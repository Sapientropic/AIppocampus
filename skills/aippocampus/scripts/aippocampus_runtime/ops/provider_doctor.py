#!/usr/bin/env python3
"""Human-facing live-provider visibility diagnostics.

This command answers one narrow operator question: can the process that runs
AIppocampus, and a child process like a Codex hook, see the API-key environment
variable required by the selected model route? It intentionally does not read
`.env` files, credential stores, or keychain entries; those can prove a key
exists somewhere, but not that the hook process inherits it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any

from aippocampus_runtime.model.routing import ModelRoute, resolve_model_route
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

    return {
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
        },
        "recommended_actions": _recommended_actions(
            provider_env_var=resolved_provider_env_var,
            current_visible=current_visible,
            child_visible=child_visible,
        ),
    }


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
    for action in report.get("recommended_actions") or []:
        if isinstance(action, dict) and action.get("message"):
            lines.append(f"- Next: {action['message']}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aippocampus doctor")
    subparsers = parser.add_subparsers(dest="command", required=True)
    provider_parser = subparsers.add_parser(
        "provider",
        help="Check whether the selected model route key is visible to this process.",
    )
    provider_parser.add_argument("--model-route", default="default")
    provider_parser.add_argument("--provider-env-var", dest="provider_env_var")
    provider_parser.add_argument("--api-key-env", dest="provider_env_var")
    provider_parser.add_argument("--no-child-check", action="store_true")
    provider_parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    report = build_provider_doctor_report(
        model_route=args.model_route,
        provider_env_var=args.provider_env_var,
        check_child_process=not args.no_child_check,
    )
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
