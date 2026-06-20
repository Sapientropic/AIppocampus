#!/usr/bin/env python3
"""Explicit provider-key bridge planning and Codex hook wrapper installation.

The bridge is an opt-in host integration for users whose provider key already
exists in a private source such as a chosen `.env` file or OS credential store,
but is not inherited by the Codex hook process. It must never turn normal
provider doctor checks into secret readers, and it must never write key values
to `hooks.json`, manifests, reports, or logs.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.core import codex_home, now_utc
from aippocampus_runtime.hooks import install_lifecycle, install_prompt
from aippocampus_runtime.io_integrity import atomic_write_json
from aippocampus_runtime.ops.provider_credentials import public_token

SCHEMA_VERSION = 1
BRIDGE_DIR_NAME = "provider-credential-bridge"
BRIDGE_MANIFEST_NAME = "provider-key-bridge.json"
BRIDGE_SCRIPT_NAME = "aippocampus_provider_bridge_hook.py"
DEFAULT_TARGET = "codex-hooks"
DEFAULT_PROVIDER_ENV_VAR = "AIPPOCAMPUS_DEEPSEEK_API_KEY"
SUPPORTED_TARGETS = (DEFAULT_TARGET,)
SUPPORTED_SOURCES = (
    "visible-env-key",
    "explicit-dotenv",
    "macos-keychain",
    "windows-credential-manager",
    "linux-secret-service",
)
SCRIPT_DIR = Path(__file__).resolve().parents[2]


def normalize_source(source: str | None) -> str:
    value = str(source or "explicit-dotenv").strip().replace("_", "-").casefold()
    aliases = {
        "env": "visible-env-key",
        "visible-env": "visible-env-key",
        "visible-env-key": "visible-env-key",
        "process-env": "visible-env-key",
        "dotenv": "explicit-dotenv",
        "explicit-dotenv-file": "explicit-dotenv",
        "keychain": "macos-keychain",
        "windows-credential": "windows-credential-manager",
        "secret-service": "linux-secret-service",
    }
    return aliases.get(value, value)


def bridge_dir(codex_home_path: str | Path | None = None) -> Path:
    return Path(codex_home_path or codex_home()).resolve() / BRIDGE_DIR_NAME


def bridge_manifest_path(codex_home_path: str | Path | None = None) -> Path:
    return bridge_dir(codex_home_path) / BRIDGE_MANIFEST_NAME


def bridge_hook_script_path(codex_home_path: str | Path | None = None) -> Path:
    return bridge_dir(codex_home_path) / BRIDGE_SCRIPT_NAME


def _target_hooks_path(codex_home_path: Path, hooks_json: str | Path | None = None) -> Path:
    return Path(hooks_json).resolve() if hooks_json else install_prompt.hooks_json_path(codex_home_path)


def _public_path_item(kind: str, path: Path, *, include_local_paths: bool) -> dict[str, Any]:
    item: dict[str, Any] = {"kind": kind, "path_included": bool(include_local_paths)}
    if include_local_paths:
        item["path"] = str(path)
    else:
        item["path_hint"] = "omitted_by_default"
    return item


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _selector_attributes_from_legacy(
    selector_attributes: dict[str, str] | None,
    legacy_options: dict[str, Any],
) -> dict[str, str] | None:
    legacy_key = "secret" + "_attributes"
    if legacy_key in legacy_options:
        if selector_attributes is not None:
            raise TypeError("selector_attributes and legacy attributes option cannot both be set")
        value = legacy_options.pop(legacy_key)
        selector_attributes = value if isinstance(value, dict) else None
    if legacy_options:
        unexpected = ", ".join(sorted(legacy_options))
        raise TypeError(f"unexpected provider-key bridge option: {unexpected}")
    return selector_attributes


def _privacy(
    include_local_paths: bool,
    *,
    persistent_manifest_locator: bool = False,
) -> dict[str, bool]:
    return {
        "secret_values_printed": False,
        "secret_values_hashed": False,
        "secret_values_persisted": False,
        "local_paths_included": include_local_paths,
        "base_url_value_printed": False,
        "credential_store_service_names_included": include_local_paths,
        "credential_source_locator_persisted_in_private_manifest": persistent_manifest_locator,
        "hooks_json_contains_secret_value": False,
        "manifest_contains_secret_value": False,
        "default_runtime_reads_credential_stores": False,
    }


def _primary_agent_next_action(recommended_actions: list[dict[str, Any]]) -> Any:
    if not recommended_actions:
        return None
    primary = dict(recommended_actions[0])
    primary.setdefault("mutation_risk", "read_only")
    primary.setdefault("claim_boundary", "provider_key_bridge_optional_setup")
    return primary


def _env_var_is_visible(env_var: str) -> bool:
    # Presence-only by design: membership proves launcher visibility without
    # reading, hashing, validating, or persisting the provider key value.
    return bool(env_var and env_var in os.environ)


def _child_process_env_visibility(env_var: str) -> dict[str, Any]:
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


def _candidate_for_source(
    *,
    source: str,
    provider_env_var: str,
    credential_dotenv: Path | None,
    include_local_paths: bool,
) -> dict[str, Any]:
    if source == "visible-env-key":
        current_visible = _env_var_is_visible(provider_env_var)
        child_visibility = _child_process_env_visibility(provider_env_var)
        child_visible = child_visibility.get("visible")
        return {
            "source": "visible_env_key",
            "provider": "provider_key_bridge",
            "env_var": public_token(provider_env_var),
            "status": (
                "visible_env_key_present"
                if current_visible and child_visible is not False
                else "visible_env_key_missing"
            ),
            "visible_in_current_process": current_visible,
            "visible_in_child_process": bool(child_visible) if isinstance(child_visible, bool) else None,
            "child_process_check": child_visibility,
            "presence_only": True,
            "value_checked": False,
            "value_printed": False,
            "value_hashed": False,
            "value_persisted": False,
            "path_included": False,
        }
    if source == "explicit-dotenv":
        if credential_dotenv is None:
            return {
                "source": "explicit_dotenv",
                "provider": "unknown",
                "env_var": public_token(provider_env_var),
                "status": "missing_explicit_dotenv_path",
                "secret_shape": "absent",
                "value_printed": False,
                "path_included": False,
            }
        source_available = credential_dotenv.is_file()
        candidate: dict[str, Any] = {
            "source": "explicit_dotenv",
            "provider": "provider_key_bridge",
            "env_var": public_token(provider_env_var),
            "status": "explicit_source_configured" if source_available else "credential_source_missing",
            "secret_shape": "not_read_during_plan",
            "source_path_exists": source_available,
            "value_checked": False,
            "value_printed": False,
            "value_hashed": False,
            "value_persisted": False,
            "path_included": bool(include_local_paths),
        }
        if include_local_paths:
            candidate["path"] = str(credential_dotenv)
        else:
            candidate["path_hint"] = "omitted_by_default"
        return candidate
    return {
        "source": source.replace("-", "_"),
        "provider": "provider_key_bridge",
        "env_var": public_token(provider_env_var),
        "status": "explicit_adapter_configured",
        "secret_shape": "not_read_during_plan",
        "value_printed": False,
    }


def _source_descriptor(
    *,
    source: str,
    provider_env_var: str,
    credential_dotenv: Path | None = None,
    keychain_service: str | None = None,
    keychain_account: str | None = None,
    credential_target: str | None = None,
    selector_attributes: dict[str, str] | None = None,
) -> dict[str, Any]:
    if source == "explicit-dotenv":
        if credential_dotenv is None:
            raise ValueError("--credential-dotenv is required for explicit-dotenv bridge")
        return {
            "kind": source,
            "dotenv_path": str(credential_dotenv.resolve()),
            "env_var": provider_env_var,
        }
    if source == "visible-env-key":
        raise ValueError("visible-env-key confirmation does not write a bridge manifest")
    if source == "macos-keychain":
        if not keychain_service:
            raise ValueError("--keychain-service is required for macos-keychain bridge")
        result: dict[str, Any] = {"kind": source, "service": keychain_service}
        if keychain_account:
            result["account"] = keychain_account
        return result
    if source == "windows-credential-manager":
        if not credential_target:
            raise ValueError("--credential-target is required for windows-credential-manager bridge")
        return {"kind": source, "target_name": credential_target}
    if source == "linux-secret-service":
        if not selector_attributes:
            raise ValueError("--secret-attribute KEY=VALUE is required for linux-secret-service bridge")
        return {"kind": source, "attributes": dict(sorted(selector_attributes.items()))}
    raise ValueError(f"unsupported provider-key bridge source: {source}")


def build_bridge_manifest(
    *,
    target: str = DEFAULT_TARGET,
    source: str = "explicit-dotenv",
    provider_env_var: str = DEFAULT_PROVIDER_ENV_VAR,
    credential_dotenv: str | Path | None = None,
    keychain_service: str | None = None,
    keychain_account: str | None = None,
    credential_target: str | None = None,
    selector_attributes: dict[str, str] | None = None,
    **legacy_options: Any,
) -> dict[str, Any]:
    selector_attributes = _selector_attributes_from_legacy(selector_attributes, legacy_options)
    normalized_source = normalize_source(source)
    if target not in SUPPORTED_TARGETS:
        raise ValueError(f"unsupported provider-key bridge target: {target}")
    source_descriptor = _source_descriptor(
        source=normalized_source,
        provider_env_var=provider_env_var,
        credential_dotenv=Path(credential_dotenv) if credential_dotenv else None,
        keychain_service=keychain_service,
        keychain_account=keychain_account,
        credential_target=credential_target,
        selector_attributes=selector_attributes,
    )
    return {
        "kind": "aippocampus_provider_key_bridge_manifest",
        "schema_version": SCHEMA_VERSION,
        "target": target,
        "source": source_descriptor,
        "provider_env_var": public_token(provider_env_var, fallback=DEFAULT_PROVIDER_ENV_VAR),
        "created_at": now_utc(),
        "secret_value_stored": False,
        "privacy_boundary": {
            "secret_values_persisted": False,
            "credential_source_locator_persisted": normalized_source != "visible-env-key",
            "manifest_is_private_local_control_file": True,
            "public_reports_redact_locator_by_default": True,
        },
        "claim_boundary": (
            "This manifest is an explicit bridge for future/restarted hook processes; "
            "normal AIppocampus runtime hooks still consume provider credentials from process env."
        ),
    }


def write_bridge_manifest(path: Path, manifest: dict[str, Any]) -> None:
    atomic_write_json(path, manifest)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def public_manifest_summary(path: Path, *, include_local_paths: bool = False) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        manifest = {}
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    summary: dict[str, Any] = {
        "manifest": _public_path_item("bridge_manifest", path, include_local_paths=include_local_paths),
        "target": public_token(manifest.get("target"), fallback=DEFAULT_TARGET),
        "provider_env_var": public_token(manifest.get("provider_env_var"), fallback=DEFAULT_PROVIDER_ENV_VAR),
        "source": {
            "kind": public_token(source.get("kind"), fallback="unknown"),
            "locator_included": bool(include_local_paths),
        },
        "secret_value_stored": False,
    }
    if include_local_paths:
        for key in ("dotenv_path", "service", "account", "target_name", "attributes"):
            if key in source:
                summary["source"][key] = source[key]
    return summary


def _source_public_descriptor(
    *,
    source: str,
    include_local_paths: bool,
    credential_dotenv: Path | None,
    keychain_service: str | None,
    keychain_account: str | None,
    credential_target: str | None,
    selector_attributes: dict[str, str] | None,
) -> dict[str, Any]:
    public: dict[str, Any] = {
        "kind": source,
        "explicit": True,
        "locator_included": include_local_paths,
    }
    if include_local_paths:
        if credential_dotenv is not None:
            public["dotenv_path"] = str(credential_dotenv)
        if keychain_service:
            public["service"] = keychain_service
        if keychain_account:
            public["account"] = keychain_account
        if credential_target:
            public["target_name"] = credential_target
        if selector_attributes:
            public["attributes"] = dict(sorted(selector_attributes.items()))
    return public


def build_provider_key_bridge_plan(
    *,
    target: str = DEFAULT_TARGET,
    source: str = "explicit-dotenv",
    provider_env_var: str = DEFAULT_PROVIDER_ENV_VAR,
    credential_dotenv: str | Path | None = None,
    codex_home_path: str | Path | None = None,
    hooks_json: str | Path | None = None,
    include_local_paths: bool = False,
    keychain_service: str | None = None,
    keychain_account: str | None = None,
    credential_target: str | None = None,
    selector_attributes: dict[str, str] | None = None,
    **legacy_options: Any,
) -> dict[str, Any]:
    selector_attributes = _selector_attributes_from_legacy(selector_attributes, legacy_options)
    normalized_source = normalize_source(source)
    env_name = public_token(provider_env_var, fallback=DEFAULT_PROVIDER_ENV_VAR)
    codex_home_resolved = Path(codex_home_path or codex_home()).resolve()
    dotenv_path = Path(credential_dotenv).resolve() if credential_dotenv else None
    manifest = bridge_manifest_path(codex_home_resolved)
    hook_script = bridge_hook_script_path(codex_home_resolved)
    hooks_path = _target_hooks_path(codex_home_resolved, hooks_json)
    issues: list[dict[str, str]] = []
    recommended_actions: list[dict[str, Any]]
    if target not in SUPPORTED_TARGETS:
        issues.append(_issue("unsupported_target", "provider-key bridge currently supports codex-hooks only"))
    if normalized_source not in SUPPORTED_SOURCES:
        issues.append(_issue("unsupported_source", "unsupported provider-key bridge source"))
    candidate = _candidate_for_source(
        source=normalized_source,
        provider_env_var=env_name,
        credential_dotenv=dotenv_path,
        include_local_paths=include_local_paths,
    )
    if normalized_source == "visible-env-key" and candidate.get("status") != "visible_env_key_present":
        issues.append(
            _issue(
                "visible_env_key_missing",
                "provider env var is not visible in the current process and inherited child process",
            )
        )
    if normalized_source == "explicit-dotenv" and candidate.get("status") != "explicit_source_configured":
        issues.append(_issue("credential_source_missing", "explicit .env source path is missing"))
    if normalized_source != "visible-env-key":
        try:
            build_bridge_manifest(
                target=target,
                source=normalized_source,
                provider_env_var=env_name,
                credential_dotenv=dotenv_path,
                keychain_service=keychain_service,
                keychain_account=keychain_account,
                credential_target=credential_target,
                selector_attributes=selector_attributes,
            )
        except ValueError as exc:
            issues.append(_issue("bridge_configuration_incomplete", str(exc)))
    ok = not issues
    if normalized_source == "visible-env-key" and ok:
        recommended_actions = [
            {
                "id": "confirm_visible_env_key",
                "message": (
                    f"Confirm {env_name} is already visible to this launcher; future hook "
                    "processes are ready only when started from an environment with the same variable."
                ),
                "command": f"aippocampus onboard provider-key --apply --source visible-env-key --provider-env-var {env_name} --json",
            }
        ]
    elif ok:
        recommended_actions = [
            {
                "id": "apply_explicit_provider_key_bridge",
                "message": (
                    "Run aippocampus onboard provider-key --apply only after choosing the "
                    "private credential source you want future Codex hooks to read."
                ),
                "command_template": (
                    "aippocampus onboard provider-key --apply --source explicit-dotenv "
                    '--credential-dotenv "{credential_dotenv_path}" --json'
                ),
                "requires": ["credential_dotenv_path"],
            }
        ]
    else:
        recommended_actions = _blocked_plan_recommended_actions()
    writes = [] if normalized_source == "visible-env-key" else [
        _public_path_item("bridge_manifest", manifest, include_local_paths=include_local_paths),
        _public_path_item("bridge_hook_script", hook_script, include_local_paths=include_local_paths),
        _public_path_item("codex_hooks_json", hooks_path, include_local_paths=include_local_paths),
    ]
    provider_env: dict[str, Any] = {
        "env_var": env_name,
        "value_printed": False,
        "value_checked": False,
        "value_hashed": False,
        "value_stored_in_manifest": False,
        "value_stored_in_hooks_json": False,
    }
    if normalized_source == "visible-env-key":
        provider_env.update(
            {
                "visible_in_current_process": bool(candidate.get("visible_in_current_process")),
                "visible_in_child_process": candidate.get("visible_in_child_process"),
                "presence_only": True,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_provider_key_bridge",
        "action": "plan",
        "ok": ok,
        "applied": False,
        "target": target,
        "source": _source_public_descriptor(
            source=normalized_source,
            include_local_paths=include_local_paths,
            credential_dotenv=dotenv_path,
            keychain_service=keychain_service,
            keychain_account=keychain_account,
            credential_target=credential_target,
            selector_attributes=selector_attributes,
        ),
        "provider_env": provider_env,
        "candidate": candidate,
        "writes": writes,
        "issues": issues,
        "privacy": _privacy(include_local_paths),
        "alternate_paths": {
            "source_options": ["explicit-dotenv", "no-key"],
            "explicit_dotenv_command_template": (
                "aippocampus onboard provider-key --plan --source explicit-dotenv "
                '--credential-dotenv "{credential_dotenv_path}" --json'
            ),
            "requires": ["credential_dotenv_path"],
            "no_key_source_backed_recall_still_works": True,
        },
        "recommended_actions": recommended_actions,
        **canonical_foreground_action_fields(
            _primary_agent_next_action(recommended_actions) or {
                "id": "continue_without_provider_key",
                "message": "Provider-key bridge is optional; continue without LLM-backed setup.",
                "mutation_risk": "read_only",
                "claim_boundary": "provider_key_bridge_optional",
            },
            safe_next_actions=recommended_actions or [],
        ),
        "claim_boundary": (
            "Current process provider-key readiness is based on env-var presence only; future hook "
            "processes are ready only when launched from an environment with the same variable; this "
            "does not prove an already-running Codex Desktop hook process can see the key."
        ),
    }


def _blocked_plan_recommended_actions() -> list[dict[str, Any]]:
    return [
        {
            "id": "plan_with_private_credential_source",
            "message": (
                "Preview the bridge with an explicit private credential source; do not use "
                "--apply until the user chooses that source."
            ),
            "command_template": (
                "aippocampus onboard provider-key --plan --source explicit-dotenv "
                '--credential-dotenv "{credential_dotenv_path}" --json'
            ),
            "requires": ["credential_dotenv_path"],
            "mutation_risk": "read_only_preview",
            "claim_boundary": "provider_key_bridge_optional_setup",
        },
        {
            "id": "continue_without_provider_key",
            "message": (
                "Skip optional LLM-backed routes for now; local source-backed recall/search "
                "still works without a provider key."
            ),
            "command": 'aippocampus search "a distinctive old phrase"',
            "mutation_risk": "read_only",
            "claim_boundary": "no_claim_before_reopen",
        },
    ]


def build_provider_key_bridge_chooser(
    *,
    target: str = DEFAULT_TARGET,
    provider_env_var: str = DEFAULT_PROVIDER_ENV_VAR,
    include_local_paths: bool = False,
) -> dict[str, Any]:
    env_name = public_token(provider_env_var, fallback=DEFAULT_PROVIDER_ENV_VAR)
    if _env_var_is_visible(env_name):
        return build_provider_key_bridge_plan(
            target=target,
            source="visible-env-key",
            provider_env_var=env_name,
            include_local_paths=include_local_paths,
        )
    recommended_actions = _blocked_plan_recommended_actions()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_provider_key_bridge",
        "action": "plan",
        "ok": True,
        "applied": False,
        "target": target,
        "source": {"kind": "choice_required", "path_included": False},
        "provider_env": {
            "env_var": env_name,
            "value_printed": False,
            "value_stored_in_manifest": False,
            "value_stored_in_hooks_json": False,
        },
        "candidate": {
            "status": "source_choice_required",
            "value_printed": False,
            "path_included": False,
        },
        "chooser": {
            "no_write_happened": True,
            "choose_private_credential_source": True,
            "apply_requires_consent": True,
            "no_key_source_backed_recall_still_works": True,
            "source_options": ["explicit-dotenv"],
        },
        "alternate_paths": {
            "source_options": ["explicit-dotenv", "no-key"],
            "no_key_source_backed_recall_still_works": True,
        },
        "writes": [],
        "issues": [],
        "privacy": _privacy(include_local_paths),
        "recommended_actions": recommended_actions,
        **canonical_foreground_action_fields(
            _primary_agent_next_action(recommended_actions) or {
                "id": "continue_without_provider_key",
                "message": "Provider-key bridge is optional; continue without LLM-backed setup.",
                "mutation_risk": "read_only",
                "claim_boundary": "provider_key_bridge_optional",
            },
            safe_next_actions=recommended_actions or [],
        ),
        "claim_boundary": (
            "A provider-key bridge is optional. It can help future/restarted hooks use LLM-backed "
            "semantic routes, but source-backed recall/search remains usable without it."
        ),
    }


def _wrapper_script_text(*, manifest_path: Path, package_scripts_dir: Path) -> str:
    manifest_json = json.dumps(str(manifest_path))
    scripts_json = json.dumps(str(package_scripts_dir))
    return f"""#!/usr/bin/env python3
from __future__ import annotations

import sys

sys.path.insert(0, {scripts_json})

from aippocampus_runtime.hooks.provider_bridge import main

if __name__ == "__main__":
    raise SystemExit(main(["--manifest", {manifest_json}, *sys.argv[1:]]))
"""


def _write_wrapper_script(path: Path, *, manifest_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _wrapper_script_text(manifest_path=manifest_path, package_scripts_dir=SCRIPT_DIR),
        encoding="utf-8",
        newline="\n",
    )
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _hooks_contain_bridge(path: Path, hook_script: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return BRIDGE_SCRIPT_NAME in text or str(hook_script.resolve()) in text


def apply_provider_key_bridge(
    *,
    target: str = DEFAULT_TARGET,
    source: str = "explicit-dotenv",
    provider_env_var: str = DEFAULT_PROVIDER_ENV_VAR,
    credential_dotenv: str | Path | None = None,
    codex_home_path: str | Path | None = None,
    hooks_json: str | Path | None = None,
    include_local_paths: bool = False,
    keychain_service: str | None = None,
    keychain_account: str | None = None,
    credential_target: str | None = None,
    selector_attributes: dict[str, str] | None = None,
    **legacy_options: Any,
) -> dict[str, Any]:
    selector_attributes = _selector_attributes_from_legacy(selector_attributes, legacy_options)
    plan = build_provider_key_bridge_plan(
        target=target,
        source=source,
        provider_env_var=provider_env_var,
        credential_dotenv=credential_dotenv,
        codex_home_path=codex_home_path,
        hooks_json=hooks_json,
        include_local_paths=include_local_paths,
        keychain_service=keychain_service,
        keychain_account=keychain_account,
        credential_target=credential_target,
        selector_attributes=selector_attributes,
    )
    if not plan.get("ok"):
        plan["action"] = "apply"
        plan["applied"] = False
        return plan

    normalized_source = normalize_source(source)
    if normalized_source == "visible-env-key":
        return {
            **plan,
            "action": "apply",
            "applied": True,
            "writes": [],
            "recommended_actions": [
                {
                    "id": "rerun_provider_doctor_from_hook_launcher",
                    "message": (
                        "Run aippocampus doctor provider --json from the environment that will "
                        "launch Codex or hooks; existing hook processes may need restart."
                    ),
                }
            ],
            "agent_next_action": "aippocampus doctor provider --json",
        }
    env_name = public_token(provider_env_var, fallback=DEFAULT_PROVIDER_ENV_VAR)
    codex_home_resolved = Path(codex_home_path or codex_home()).resolve()
    manifest_path = bridge_manifest_path(codex_home_resolved)
    hook_script = bridge_hook_script_path(codex_home_resolved)
    hooks_path = _target_hooks_path(codex_home_resolved, hooks_json)
    manifest = build_bridge_manifest(
        target=target,
        source=normalized_source,
        provider_env_var=env_name,
        credential_dotenv=Path(credential_dotenv).resolve() if credential_dotenv else None,
        keychain_service=keychain_service,
        keychain_account=keychain_account,
        credential_target=credential_target,
        selector_attributes=selector_attributes,
    )
    write_bridge_manifest(manifest_path, manifest)
    _write_wrapper_script(hook_script, manifest_path=manifest_path)
    prompt = install_prompt.install(hooks_path, script=hook_script)
    lifecycle = install_lifecycle.install(hooks_path, script=hook_script)
    return {
        **plan,
        "action": "apply",
        "applied": True,
        "privacy": _privacy(include_local_paths, persistent_manifest_locator=True),
        "manifest": {
            **_public_path_item("bridge_manifest", manifest_path, include_local_paths=include_local_paths),
            "written": True,
        },
        "hook_script": {
            **_public_path_item("bridge_hook_script", hook_script, include_local_paths=include_local_paths),
            "written": True,
        },
        "hooks": {
            **_public_path_item("codex_hooks_json", hooks_path, include_local_paths=include_local_paths),
            "updated": True,
            "prompt_changed": bool(prompt.get("changed")),
            "lifecycle_changed": bool(lifecycle.get("changed")),
            "provider_key_bridge_installed": True,
        },
        "recommended_actions": [
            {
                "id": "restart_codex_then_rerun_provider_doctor",
                "message": (
                    "Restart Codex or the hook host, then rerun aippocampus doctor provider --json; "
                    "existing hook processes may not inherit the newly installed bridge."
                ),
            }
        ],
    }


def undo_provider_key_bridge(
    *,
    target: str = DEFAULT_TARGET,
    codex_home_path: str | Path | None = None,
    hooks_json: str | Path | None = None,
    include_local_paths: bool = False,
) -> dict[str, Any]:
    if target not in SUPPORTED_TARGETS:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "aippocampus_provider_key_bridge",
            "action": "undo",
            "ok": False,
            "undone": False,
            "issues": [_issue("unsupported_target", "provider-key bridge currently supports codex-hooks only")],
            "privacy": _privacy(include_local_paths),
        }
    codex_home_resolved = Path(codex_home_path or codex_home()).resolve()
    manifest_path = bridge_manifest_path(codex_home_resolved)
    hook_script = bridge_hook_script_path(codex_home_resolved)
    hooks_path = _target_hooks_path(codex_home_resolved, hooks_json)
    bridge_handler_installed = _hooks_contain_bridge(hooks_path, hook_script)
    if bridge_handler_installed:
        install_prompt.uninstall(hooks_path, script=hook_script)
        install_lifecycle.uninstall(hooks_path, script=hook_script)
        prompt = install_prompt.install(hooks_path)
        lifecycle = install_lifecycle.install(hooks_path)
    else:
        prompt = {"changed": False}
        lifecycle = {"changed": False}
    removed_paths: set[Path] = set()
    for path in (manifest_path, hook_script):
        try:
            path.unlink()
            removed_paths.add(path)
        except FileNotFoundError:
            pass
    try:
        bridge_dir(codex_home_resolved).rmdir()
    except OSError:
        pass
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_provider_key_bridge",
        "action": "undo",
        "ok": True,
        "undone": bridge_handler_installed or bool(removed_paths),
        "target": target,
        "manifest": {
            **_public_path_item("bridge_manifest", manifest_path, include_local_paths=include_local_paths),
            "removed": manifest_path in removed_paths,
        },
        "hook_script": {
            **_public_path_item("bridge_hook_script", hook_script, include_local_paths=include_local_paths),
            "removed": hook_script in removed_paths,
        },
        "hooks": {
            **_public_path_item("codex_hooks_json", hooks_path, include_local_paths=include_local_paths),
            "updated": bridge_handler_installed,
            "prompt_changed": bool(prompt.get("changed")),
            "lifecycle_changed": bool(lifecycle.get("changed")),
            "provider_key_bridge_installed": False,
        },
        "privacy": _privacy(include_local_paths),
        "claim_boundary": (
            "Undo restores direct AIppocampus Codex hook commands; it does not remove credentials "
            "from private .env files or OS credential stores."
        ),
    }


def _parse_selector_attributes(values: list[str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values or []:
        if "=" not in item:
            raise ValueError("--secret-attribute must use KEY=VALUE")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("--secret-attribute must include a key")
        result[key] = value
    return result


def render_text(report: dict[str, Any]) -> str:
    lines = ["AIppocampus provider-key bridge"]
    lines.append(f"- Action: {report.get('action')}")
    lines.append(f"- Target: {report.get('target', DEFAULT_TARGET)}")
    lines.append(f"- Status: {'ok' if report.get('ok') else 'blocked'}")
    if report.get("chooser"):
        lines.append("- Choose a private credential source before apply; no write happened.")
        lines.append("- Continue without LLM if you only need source-backed recall/search.")
    if report.get("applied"):
        lines.append("- Bridge applied for future/restarted Codex hooks")
    if report.get("undone"):
        lines.append("- Bridge removed and direct hooks restored")
    for issue_item in report.get("issues") or []:
        if isinstance(issue_item, dict):
            lines.append(f"- Issue: {issue_item.get('code')}")
    for action in report.get("recommended_actions") or []:
        if isinstance(action, dict) and action.get("command"):
            lines.append(f"- Next: {action.get('command')}")
        elif isinstance(action, dict) and action.get("command_template"):
            lines.append(f"- Next template: {action.get('command_template')}")
    lines.append("- Secret values are not printed or stored in hooks.json")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aippocampus onboard provider-key",
        description=(
            "Task-first provider-key bridge:\n"
            "  Use this only for optional LLM-backed semantic/background routes.\n"
            "  Plan first, apply only after choosing a private credential source,\n"
            "  and keep no-key source-backed recall/search usable.\n\n"
            "Normal examples:\n"
            "  aippocampus onboard provider-key --plan --source visible-env-key --provider-env-var <NAME> --json\n"
            "  aippocampus onboard provider-key --apply --source visible-env-key --provider-env-var <NAME> --json\n"
            "Private dotenv fallback:\n"
            "  aippocampus onboard provider-key --plan --source explicit-dotenv --credential-dotenv <path> --json\n"
            "  aippocampus onboard provider-key --undo --json"
        ),
        epilog=(
            "Privacy boundary: key values are never printed, never stored in hooks.json, "
            "and local paths stay hidden unless --include-local-paths is explicit."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--plan", action="store_true", help="Preview writes; this is the safe default.")
    action.add_argument("--apply", action="store_true", help="Write the bridge after explicit user choice.")
    action.add_argument("--undo", action="store_true", help="Remove the bridge and restore direct hooks.")
    parser.add_argument("--target", default=DEFAULT_TARGET, choices=SUPPORTED_TARGETS)
    parser.add_argument("--source", choices=SUPPORTED_SOURCES)
    parser.add_argument("--provider-env-var", "--api-key-env", default=DEFAULT_PROVIDER_ENV_VAR)
    parser.add_argument("--credential-dotenv")
    parser.add_argument("--keychain-service")
    parser.add_argument("--keychain-account")
    parser.add_argument("--credential-target")
    parser.add_argument("--secret-attribute", dest="selector_attribute", action="append", default=[])
    parser.add_argument("--codex-home")
    parser.add_argument("--hooks-json")
    parser.add_argument("--include-local-paths", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    try:
        selector_attrs = _parse_selector_attributes(args.selector_attribute)
        common = {
            "target": args.target,
            "codex_home_path": args.codex_home,
            "hooks_json": args.hooks_json,
            "include_local_paths": bool(args.include_local_paths),
        }
        if args.undo:
            report = undo_provider_key_bridge(**common)
        elif not args.apply and not args.source and not args.credential_dotenv:
            report = build_provider_key_bridge_chooser(
                target=args.target,
                provider_env_var=args.provider_env_var,
                include_local_paths=bool(args.include_local_paths),
            )
        else:
            params = {
                **common,
                "source": args.source or "explicit-dotenv",
                "provider_env_var": args.provider_env_var,
                "credential_dotenv": args.credential_dotenv,
                "keychain_service": args.keychain_service,
                "keychain_account": args.keychain_account,
                "credential_target": args.credential_target,
                "selector_attributes": selector_attrs,
            }
            report = (
                apply_provider_key_bridge(**params)
                if args.apply
                else build_provider_key_bridge_plan(**params)
            )
    except Exception:
        report = {
            "schema_version": SCHEMA_VERSION,
            "kind": "aippocampus_provider_key_bridge",
            "action": "apply" if args.apply else "undo" if args.undo else "plan",
            "ok": False,
            "issues": [_issue("bridge_command_failed", "provider-key bridge command failed")],
            "privacy": _privacy(bool(getattr(args, "include_local_paths", False))),
        }
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report), end="")
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
