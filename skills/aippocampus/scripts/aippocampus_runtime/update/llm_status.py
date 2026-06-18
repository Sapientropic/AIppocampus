"""Printable LLM-provider readiness projection for update status."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

from aippocampus_runtime.cognitive_worker_mode import resolve_cognitive_worker_mode
from aippocampus_runtime.model.routing import resolve_model_route


def _provider_env_name(route: Any, override: str | None) -> str:
    return str(override or getattr(route, "api_key_env", "") or "").strip()


def _current_process_has_env(name: str) -> bool:
    # Presence-only: update status never reads or serializes provider key values.
    return bool(name and name in os.environ)


def _child_process_has_env(name: str) -> bool | None:
    if not name:
        return None
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, sys; sys.exit(0 if sys.argv[1] in os.environ else 1)",
            name,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def _recommended_actions(status: str) -> list[dict[str, str]]:
    actions = [
        {
            "id": "inspect_provider_doctor_detail",
            "command": "aippocampus doctor provider --detail full --json",
            "mutation_risk": "read_only",
            "claim_boundary": "operator_detail_not_memory_evidence",
        }
    ]
    if status == "missing_provider_env_var":
        actions.insert(
            0,
            {
                "id": "plan_provider_key_bridge",
                "command": "aippocampus onboard provider-key --plan --json",
                "mutation_risk": "read_only_plan",
                "claim_boundary": "provider_key_setup_not_memory_evidence",
            },
        )
    return actions


def status_llm(
    *,
    model_route: str | None = "default",
    provider_env_var: str | None = None,
    check_child_process: bool = True,
) -> dict[str, Any]:
    try:
        route = resolve_model_route(model_route)
    except ValueError:
        return {
            "surface": "llm",
            "status": "route_config_error",
            "ready": False,
            "provider_env_var_omitted": bool(provider_env_var),
            "visible_in_current_process": None,
            "visible_in_child_process": None,
            "cognitive_worker": resolve_cognitive_worker_mode(
                provider_key_visible=False
            ),
            "recommended_actions": _recommended_actions("route_config_error"),
            "privacy": _privacy(provider_env_var_known=bool(provider_env_var)),
            "safety_notes": _safety_notes(),
        }

    env_name = _provider_env_name(route, provider_env_var)
    current_visible = _current_process_has_env(env_name)
    child_visible = _child_process_has_env(env_name) if check_child_process else None
    ok = current_visible and child_visible is not False
    status = "ready" if ok else (
        "missing_provider_env_var" if not current_visible else "child_process_missing_provider_env_var"
    )
    route_payload = route.as_dict()
    return {
        "surface": "llm",
        "status": status,
        "ready": ok,
        "provider": route_payload.get("provider"),
        "model": route_payload.get("model"),
        "provider_env_var_omitted": bool(env_name),
        "visible_in_current_process": current_visible,
        "visible_in_child_process": child_visible,
        "cognitive_worker": resolve_cognitive_worker_mode(
            api_key_env=env_name,
            provider_key_visible=current_visible,
        ),
        "recommended_actions": _recommended_actions(status),
        "privacy": _privacy(provider_env_var_known=bool(env_name)),
        "safety_notes": _safety_notes(),
    }


def _privacy(*, provider_env_var_known: bool) -> dict[str, Any]:
    return {
        "env_var_value_printed": False,
        "env_var_value_checked": False,
        "provider_env_var_name_omitted": provider_env_var_known,
        "local_paths_included": False,
        "base_url_value_printed": False,
        "operator_detail_available": True,
    }


def _safety_notes() -> list[str]:
    return [
        "LLM key setup is presence-only and redacted; update never prints or guesses key values",
        "set the provider key in the environment that launches Codex or the hook process",
    ]
