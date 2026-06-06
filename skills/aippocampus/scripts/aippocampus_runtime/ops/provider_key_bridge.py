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
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import codex_home, now_utc
from aippocampus_runtime.hooks import install_lifecycle, install_prompt
from aippocampus_runtime.ops.provider_credentials import (
    credential_candidate,
    dotenv_values,
    public_candidate,
    public_token,
)

SCHEMA_VERSION = 1
BRIDGE_DIR_NAME = "provider-credential-bridge"
BRIDGE_MANIFEST_NAME = "provider-key-bridge.json"
BRIDGE_SCRIPT_NAME = "aippocampus_provider_bridge_hook.py"
DEFAULT_TARGET = "codex-hooks"
DEFAULT_PROVIDER_ENV_VAR = "DEEPSEEK_API_KEY"
SUPPORTED_TARGETS = (DEFAULT_TARGET,)
SUPPORTED_SOURCES = (
    "explicit-dotenv",
    "macos-keychain",
    "windows-credential-manager",
    "linux-secret-service",
)
SCRIPT_DIR = Path(__file__).resolve().parents[2]


def normalize_source(source: str | None) -> str:
    value = str(source or "explicit-dotenv").strip().replace("_", "-").casefold()
    aliases = {
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


def _privacy(include_local_paths: bool) -> dict[str, bool]:
    return {
        "secret_values_printed": False,
        "local_paths_included": include_local_paths,
        "base_url_value_printed": False,
        "credential_store_service_names_included": include_local_paths,
        "hooks_json_contains_secret_value": False,
        "manifest_contains_secret_value": False,
        "default_runtime_reads_credential_stores": False,
    }


def _candidate_for_source(
    *,
    source: str,
    provider_env_var: str,
    credential_dotenv: Path | None,
    include_local_paths: bool,
) -> dict[str, Any]:
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
        value = dotenv_values(credential_dotenv).get(provider_env_var)
        return public_candidate(
            credential_candidate(
                source="explicit_dotenv",
                provider="provider_key_bridge",
                env_var=provider_env_var,
                value=value,
                path=credential_dotenv,
                include_local_paths=include_local_paths,
            )
        )
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
    secret_attributes: dict[str, str] | None = None,
) -> dict[str, Any]:
    if source == "explicit-dotenv":
        if credential_dotenv is None:
            raise ValueError("--credential-dotenv is required for explicit-dotenv bridge")
        return {
            "kind": source,
            "dotenv_path": str(credential_dotenv.resolve()),
            "env_var": provider_env_var,
        }
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
        if not secret_attributes:
            raise ValueError("--secret-attribute KEY=VALUE is required for linux-secret-service bridge")
        return {"kind": source, "attributes": dict(sorted(secret_attributes.items()))}
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
    secret_attributes: dict[str, str] | None = None,
) -> dict[str, Any]:
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
        secret_attributes=secret_attributes,
    )
    return {
        "kind": "aippocampus_provider_key_bridge_manifest",
        "schema_version": SCHEMA_VERSION,
        "target": target,
        "source": source_descriptor,
        "provider_env_var": public_token(provider_env_var, fallback=DEFAULT_PROVIDER_ENV_VAR),
        "created_at": now_utc(),
        "secret_value_stored": False,
        "claim_boundary": (
            "This manifest is an explicit bridge for future/restarted hook processes; "
            "normal AIppocampus runtime hooks still consume provider credentials from process env."
        ),
    }


def write_bridge_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    tmp.replace(path)
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
    secret_attributes: dict[str, str] | None,
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
        if secret_attributes:
            public["attributes"] = dict(sorted(secret_attributes.items()))
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
    secret_attributes: dict[str, str] | None = None,
) -> dict[str, Any]:
    normalized_source = normalize_source(source)
    env_name = public_token(provider_env_var, fallback=DEFAULT_PROVIDER_ENV_VAR)
    codex_home_resolved = Path(codex_home_path or codex_home()).resolve()
    dotenv_path = Path(credential_dotenv).resolve() if credential_dotenv else None
    manifest = bridge_manifest_path(codex_home_resolved)
    hook_script = bridge_hook_script_path(codex_home_resolved)
    hooks_path = _target_hooks_path(codex_home_resolved, hooks_json)
    issues: list[dict[str, str]] = []
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
    if normalized_source == "explicit-dotenv" and candidate.get("status") != "candidate_present":
        issues.append(_issue("credential_candidate_missing", "explicit .env candidate is missing the provider env var"))
    try:
        build_bridge_manifest(
            target=target,
            source=normalized_source,
            provider_env_var=env_name,
            credential_dotenv=dotenv_path,
            keychain_service=keychain_service,
            keychain_account=keychain_account,
            credential_target=credential_target,
            secret_attributes=secret_attributes,
        )
    except ValueError as exc:
        issues.append(_issue("bridge_configuration_incomplete", str(exc)))
    ok = not issues
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
            secret_attributes=secret_attributes,
        ),
        "provider_env": {
            "env_var": env_name,
            "value_printed": False,
            "value_stored_in_manifest": False,
            "value_stored_in_hooks_json": False,
        },
        "candidate": candidate,
        "writes": [
            _public_path_item("bridge_manifest", manifest, include_local_paths=include_local_paths),
            _public_path_item("bridge_hook_script", hook_script, include_local_paths=include_local_paths),
            _public_path_item("codex_hooks_json", hooks_path, include_local_paths=include_local_paths),
        ],
        "issues": issues,
        "privacy": _privacy(include_local_paths),
        "recommended_actions": [
            {
                "id": "apply_explicit_provider_key_bridge",
                "message": (
                    "Run aippocampus onboard provider-key --apply only after choosing the "
                    "private credential source you want future Codex hooks to read."
                ),
            }
        ]
        if ok
        else [],
        "claim_boundary": (
            "An applied bridge can make future/restarted Codex hook processes set the provider env var; "
            "it does not prove an already-running Codex Desktop hook process can see the key."
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
    secret_attributes: dict[str, str] | None = None,
) -> dict[str, Any]:
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
        secret_attributes=secret_attributes,
    )
    if not plan.get("ok"):
        plan["action"] = "apply"
        plan["applied"] = False
        return plan

    normalized_source = normalize_source(source)
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
        secret_attributes=secret_attributes,
    )
    write_bridge_manifest(manifest_path, manifest)
    _write_wrapper_script(hook_script, manifest_path=manifest_path)
    prompt = install_prompt.install(hooks_path, script=hook_script)
    lifecycle = install_lifecycle.install(hooks_path, script=hook_script)
    return {
        **plan,
        "action": "apply",
        "applied": True,
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


def _parse_secret_attributes(values: list[str] | None) -> dict[str, str]:
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
    if report.get("applied"):
        lines.append("- Bridge applied for future/restarted Codex hooks")
    if report.get("undone"):
        lines.append("- Bridge removed and direct hooks restored")
    for issue_item in report.get("issues") or []:
        if isinstance(issue_item, dict):
            lines.append(f"- Issue: {issue_item.get('code')}")
    lines.append("- Secret values are not printed or stored in hooks.json")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aippocampus onboard provider-key")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--plan", action="store_true")
    action.add_argument("--apply", action="store_true")
    action.add_argument("--undo", action="store_true")
    parser.add_argument("--target", default=DEFAULT_TARGET, choices=SUPPORTED_TARGETS)
    parser.add_argument("--source", default="explicit-dotenv", choices=SUPPORTED_SOURCES)
    parser.add_argument("--provider-env-var", "--api-key-env", default=DEFAULT_PROVIDER_ENV_VAR)
    parser.add_argument("--credential-dotenv")
    parser.add_argument("--keychain-service")
    parser.add_argument("--keychain-account")
    parser.add_argument("--credential-target")
    parser.add_argument("--secret-attribute", action="append", default=[])
    parser.add_argument("--codex-home")
    parser.add_argument("--hooks-json")
    parser.add_argument("--include-local-paths", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    try:
        attrs = _parse_secret_attributes(args.secret_attribute)
        common = {
            "target": args.target,
            "codex_home_path": args.codex_home,
            "hooks_json": args.hooks_json,
            "include_local_paths": bool(args.include_local_paths),
        }
        if args.undo:
            report = undo_provider_key_bridge(**common)
        else:
            params = {
                **common,
                "source": args.source,
                "provider_env_var": args.provider_env_var,
                "credential_dotenv": args.credential_dotenv,
                "keychain_service": args.keychain_service,
                "keychain_account": args.keychain_account,
                "credential_target": args.credential_target,
                "secret_attributes": attrs,
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
