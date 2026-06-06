"""Explicit provider credential-source discovery for onboarding diagnostics.

Normal runtime provider checks are presence-only. This module is used only when
the operator explicitly asks to inspect candidate credential sources; it may read
candidate values for shape/probe status, but public reports must never include
secret values, endpoint values, or local paths by default.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from aippocampus_runtime.model.routing import ModelRoute

CredentialValidator = Callable[[dict[str, Any], ModelRoute], dict[str, Any]]


def public_token(value: Any, *, fallback: str = "unknown", limit: int = 96) -> str:
    text = str(value or "").strip()
    clean = "".join(char for char in text[:limit] if char.isalnum() or char in {"_", "-", "."})
    return clean or fallback


def secret_shape(value: str) -> str:
    return f"len:{len(value)}"


def public_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in candidate.items() if not str(key).startswith("_")}


def dotenv_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def credential_validation_unknown() -> dict[str, str]:
    return {"status": "unknown_not_probed", "method": "not_requested"}


def models_probe_url(route: ModelRoute) -> str:
    base_url = (route.base_url or "").rstrip("/")
    return f"{base_url}/models" if base_url else "/models"


def safe_probe_transport(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return True
    if parsed.scheme != "http":
        return False
    host = (parsed.hostname or "").casefold()
    return host in {"localhost", "127.0.0.1", "::1"}


def validate_credential_candidate(candidate: dict[str, Any], route: ModelRoute) -> dict[str, Any]:
    """Probe a candidate credential without returning secret or endpoint values."""

    secret = str(candidate.get("_secret_value") or "")
    if not secret:
        return {"status": "unknown_not_probed", "method": "models_endpoint"}
    probe_url = models_probe_url(route)
    if not safe_probe_transport(probe_url):
        return {"status": "unsafe_transport_not_probed", "method": "models_endpoint"}
    request = urllib.request.Request(
        probe_url,
        headers={
            "Authorization": f"Bearer {secret}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            status = int(getattr(response, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return {"status": "invalid_401", "method": "models_endpoint"}
        if exc.code == 403:
            return {"status": "invalid_403", "method": "models_endpoint"}
        return {"status": "network_error", "method": "models_endpoint"}
    except (OSError, TimeoutError):
        return {"status": "network_error", "method": "models_endpoint"}
    if 200 <= status < 300:
        return {"status": "valid", "method": "models_endpoint"}
    return {"status": "network_error", "method": "models_endpoint"}


def apply_validation(
    candidate: dict[str, Any],
    *,
    route: ModelRoute,
    validate_credentials: bool,
    credential_validator: CredentialValidator | None,
) -> dict[str, Any]:
    if not validate_credentials:
        unknown = credential_validation_unknown()
        candidate["validation_status"] = unknown["status"]
        candidate["validation_method"] = unknown["method"]
        return candidate
    validator = credential_validator or validate_credential_candidate
    result = validator(candidate, route)
    candidate["validation_status"] = public_token(result.get("status"), fallback="unknown_not_probed")
    candidate["validation_method"] = public_token(result.get("method"), fallback="unknown")
    return candidate


def credential_candidate(
    *,
    source: str,
    provider: str,
    env_var: str,
    value: str | None,
    path: Path | None = None,
    include_local_paths: bool = False,
) -> dict[str, Any]:
    present = value is not None
    candidate: dict[str, Any] = {
        "source": source,
        "provider": public_token(provider),
        "env_var": public_token(env_var),
        "status": "candidate_present" if present else "candidate_absent",
        "secret_shape": secret_shape(value or "") if present else "absent",
        "value_printed": False,
    }
    if present:
        candidate["_secret_value"] = value
    if path is not None:
        candidate["path_included"] = bool(include_local_paths)
        if include_local_paths:
            candidate["path"] = str(path)
        else:
            candidate["path_hint"] = "omitted_by_default"
    return candidate


def bridge_plan(candidates: list[dict[str, Any]], *, env_var: str) -> list[dict[str, str]]:
    present_candidates = [
        item for item in candidates if str(item.get("status") or "") == "candidate_present"
    ]
    statuses = {str(item.get("validation_status") or "") for item in present_candidates}
    if "valid" in statuses:
        return [
            {
                "id": "bridge_valid_candidate_explicitly",
                "message": (
                    "A validated candidate exists. Bridge it into the launcher or hook environment "
                    "with an explicit operator action; AIppocampus will not store the secret in config."
                ),
            }
        ]
    if present_candidates and statuses <= {"unknown_not_probed"}:
        return [
            {
                "id": "validate_candidate_before_bridge",
                "message": (
                    "Credential candidates were found but not validated. Rerun with "
                    "--validate-credentials before bridging a candidate into hooks."
                ),
            }
        ]
    return [
        {
            "id": "set_provider_env_in_hook_environment",
            "message": (
                f"No validated credential candidate is ready to bridge. Configure {public_token(env_var)} "
                "in the environment that launches Codex or the hook process."
            ),
        }
    ]


def build_credential_discovery_report(
    *,
    route: ModelRoute,
    provider_env_var: str,
    dotenv_paths: list[Path] | None = None,
    include_local_paths: bool = False,
    validate_credentials: bool = False,
    credential_validator: CredentialValidator | None = None,
) -> dict[str, Any]:
    # This path is intentionally explicit. It may inspect candidate values for
    # shape/validation only after the operator asks for credential discovery;
    # normal provider doctor remains presence-only and never reads values.
    dotenv_paths = dotenv_paths or []
    candidates: list[dict[str, Any]] = []
    provider = route.provider or "unknown"
    env_value = os.environ.get(provider_env_var) if provider_env_var else None
    candidates.append(
        credential_candidate(
            source="current_process_env",
            provider=provider,
            env_var=provider_env_var,
            value=env_value,
        )
    )
    for path in dotenv_paths:
        values = dotenv_values(path)
        value = values.get(provider_env_var)
        if value is None:
            continue
        candidates.append(
            credential_candidate(
                source="explicit_dotenv",
                provider=provider,
                env_var=provider_env_var,
                value=value,
                path=path,
                include_local_paths=include_local_paths,
            )
        )
    validated = [
        apply_validation(
            candidate,
            route=route,
            validate_credentials=validate_credentials,
            credential_validator=credential_validator,
        )
        for candidate in candidates
    ]
    public_candidates = [public_candidate(candidate) for candidate in validated]
    return {
        "checked": True,
        "schema_version": 1,
        "explicit_command_required": True,
        "default_runtime_reads_credential_stores": False,
        "recursive_filesystem_scan": False,
        "validation_requested": validate_credentials,
        "candidates": public_candidates,
        "reserved_sources": [
            {
                "source": "macos_keychain",
                "status": "reserved_requires_explicit_service",
                "default_scanned": False,
            },
            {
                "source": "windows_credential_manager",
                "status": "reserved_requires_explicit_target",
                "default_scanned": False,
            },
            {
                "source": "linux_secret_service",
                "status": "reserved_requires_explicit_lookup",
                "default_scanned": False,
            },
        ],
        "bridge_plan": bridge_plan(public_candidates, env_var=provider_env_var),
        "privacy": {
            "secret_values_printed": False,
            "local_paths_included": include_local_paths,
            "base_url_value_printed": False,
            "credential_store_service_names_included": False,
        },
        "claim_boundary": (
            "credential discovery is explicit onboarding help; runtime hooks and provider doctor "
            "still read provider credentials from environment variables only"
        ),
    }
