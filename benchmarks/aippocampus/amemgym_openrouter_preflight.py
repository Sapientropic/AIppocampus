"""Public-safe OpenRouter route preflight helpers for AMemGym runs."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_CHAT_COMPLETIONS_URL = f"{OPENROUTER_BASE_URL}/chat/completions"
OPENROUTER_ROUTE_PROBE_PROMPT = "Reply with exactly OK."


def _sha1_short(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def _read_json(path: Path | str) -> dict[str, Any] | list[Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _safe_public_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    text = str(value)
    if not text:
        return ""
    if len(text) > 120:
        return f"value_sha1:{_sha1_short(text)}"
    return text


def openrouter_models_required_for_surfaces(
    *,
    run_surfaces: tuple[str, ...],
    env_config_path: Path | str,
    agent_config_path: Path | str,
) -> list[dict[str, Any]]:
    """Return the provider routes that must be available before a live run.

    This follows the official AMemGym entrypoints. `overall` calls the
    evaluated agent and the low-temperature environment simulator for follow-up
    turns; `upperbound` calls the evaluated agent config; `random` is
    deterministic and does not need a provider route. Keeping this narrow
    prevents an unused config field from blocking an otherwise runnable resume.
    """

    required: dict[str, set[str]] = {}
    surfaces = set(run_surfaces)
    if {"overall", "upperbound"} & surfaces:
        agent = _read_json(agent_config_path)
        if isinstance(agent, dict) and isinstance(agent.get("llm_config"), dict):
            model = str(agent["llm_config"].get("llm_model") or "").strip()
            if model:
                required.setdefault(model, set()).add("agent")
    if "overall" in surfaces:
        env = _read_json(env_config_path)
        if isinstance(env, dict) and isinstance(env.get("llm_config_low_temp"), dict):
            model = str(env["llm_config_low_temp"].get("llm_model") or "").strip()
            if model:
                required.setdefault(model, set()).add("environment_low_temp")
    return [
        {"model": model, "roles": sorted(roles)}
        for model, roles in sorted(required.items())
    ]


def safe_openrouter_error_summary(body: str) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {
            "shape": "non_json",
            "body_sha1": _sha1_short(body),
            "body_length": len(body),
        }
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return {"shape": "missing_error", "body_sha1": _sha1_short(body)}
    metadata = error.get("metadata") if isinstance(error.get("metadata"), dict) else {}
    safe_metadata: dict[str, Any] = {}
    for key in ("provider_name", "model_slug", "reasons", "patterns"):
        if key in metadata:
            safe_metadata[key] = metadata[key]
    if "flagged_input" in metadata:
        flagged = str(metadata.get("flagged_input") or "")
        safe_metadata["flagged_input_sha1"] = _sha1_short(flagged)
        safe_metadata["flagged_input_length"] = len(flagged)
    previous_errors = metadata.get("previous_errors")
    if isinstance(previous_errors, list):
        safe_metadata["previous_errors"] = [
            {
                "code": item.get("code"),
                "message": str(item.get("message") or "")[:240],
            }
            for item in previous_errors[:3]
            if isinstance(item, dict)
        ]
    openrouter_metadata = payload.get("openrouter_metadata") if isinstance(payload, dict) else None
    safe_router_metadata: dict[str, Any] = {}
    if isinstance(openrouter_metadata, dict):
        for key in ("requested", "strategy", "region", "summary", "attempt", "is_byok"):
            if key in openrouter_metadata:
                safe_router_metadata[key] = openrouter_metadata[key]
        endpoints = openrouter_metadata.get("endpoints")
        if isinstance(endpoints, dict):
            safe_router_metadata["endpoints"] = {
                "total": endpoints.get("total"),
                "available_count": len(endpoints.get("available") or []),
            }
        pipeline = openrouter_metadata.get("pipeline")
        if isinstance(pipeline, list):
            safe_router_metadata["pipeline"] = [
                {
                    key: stage.get(key)
                    for key in ("type", "name", "summary")
                    if isinstance(stage, dict) and key in stage
                }
                for stage in pipeline[:8]
            ]
    return {
        "code": error.get("code"),
        "message": str(error.get("message") or "")[:240],
        "metadata": safe_metadata,
        "openrouter_metadata": safe_router_metadata,
    }


def probe_openrouter_chat_route(
    *,
    api_key: str,
    model: str,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Send a tiny harmless request so policy/permission failures are explicit."""

    started = time.perf_counter()
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": OPENROUTER_ROUTE_PROBE_PROMPT}],
        "temperature": 0,
        "max_tokens": 4,
    }
    request = urllib.request.Request(
        OPENROUTER_CHAT_COMPLETIONS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-OpenRouter-Metadata": "enabled",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
        parsed = json.loads(body)
        usage = parsed.get("usage") if isinstance(parsed.get("usage"), dict) else {}
        return {
            "status": "passed",
            "http_status": 200,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "model": model,
            "returned_model": _safe_public_value(parsed.get("model")),
            "provider": _safe_public_value(parsed.get("provider")),
            "usage": {
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
            },
        }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "status": "failed",
            "http_status": exc.code,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "model": model,
            "error": safe_openrouter_error_summary(body),
        }
    except Exception as exc:
        return {
            "status": "failed",
            "http_status": None,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "model": model,
            "error": {
                "code": type(exc).__name__,
                "message": str(exc)[:240],
            },
        }


def openrouter_route_preflight_summary(
    *,
    provider: str,
    enabled: bool,
    pending_run_surfaces: tuple[str, ...],
    provider_status: dict[str, Any],
    env_config_path: Path | str,
    agent_config_path: Path | str,
    timeout_seconds: int | None,
    credential_lookup: Callable[[str], str | None],
    probe_func: Callable[..., dict[str, Any]] = probe_openrouter_chat_route,
) -> dict[str, Any]:
    if provider != "openrouter":
        return {"required": False, "status": "skipped_not_openrouter", "checks": []}
    if not enabled:
        return {"required": False, "status": "skipped_disabled", "checks": []}
    models = openrouter_models_required_for_surfaces(
        run_surfaces=pending_run_surfaces,
        env_config_path=env_config_path,
        agent_config_path=agent_config_path,
    )
    if not models:
        return {"required": False, "status": "skipped_no_live_llm_surface", "checks": []}
    credential_alias = provider_status.get("credential_alias")
    api_key = credential_lookup(str(credential_alias)) if credential_alias else None
    if not api_key:
        return {
            "required": True,
            "status": "failed_missing_credential",
            "checks": [
                {
                    "model": entry["model"],
                    "roles": entry["roles"],
                    "status": "not_checked",
                    "error": "openrouter_credential_missing",
                }
                for entry in models
            ],
        }
    checks = []
    for entry in models:
        result = probe_func(
            api_key=api_key,
            model=entry["model"],
            timeout_seconds=timeout_seconds or 30,
        )
        result["roles"] = entry["roles"]
        checks.append(result)
    return {
        "required": True,
        "status": "passed" if all(check.get("status") == "passed" for check in checks) else "failed",
        "probe_prompt": "harmless_fixed_ok",
        "checks": checks,
    }
