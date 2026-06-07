#!/usr/bin/env python3
"""Smoke test provider-key bridge OS credential-store adapters.

This smoke creates a temporary test credential in the selected OS credential
store, verifies the provider bridge wrapper can load it into a hook-process
environment update, and removes the credential again. Public JSON must not
include the secret value, store locator, or local temporary paths.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.hooks import provider_bridge as hook_provider_bridge  # noqa: E402
from aippocampus_runtime.ops import provider_key_bridge  # noqa: E402

SCHEMA_VERSION = 1
KIND = "aippocampus_provider_key_bridge_os_store_smoke"
ENV_VAR = "DEEPSEEK_API_KEY"
SUPPORTED_SOURCES = ("macos-keychain", "windows-credential-manager", "linux-secret-service")


def _test_secret(run_id: str) -> str:
    return "sk-" + "FAKE_TEST_PROVIDER_BRIDGE_" + run_id


def _base_report(source: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source,
        "platform": sys.platform,
        "os_name": os.name,
        "ok": False,
        "skipped": False,
        "status": "not_run",
        "privacy": {
            "secret_values_printed": False,
            "locator_values_printed": False,
            "local_paths_included": False,
            "manifest_contains_secret_value": False,
            "public_report_contains_secret_or_locator": False,
        },
        "cleanup": {
            "attempted": False,
            "ok": False,
        },
        "claim_boundary": (
            "This smoke proves the selected OS credential-store adapter can feed an "
            "AIppocampus-owned provider-key hook wrapper on this host only; doctor "
            "provider remains an env-visibility diagnostic and does not read stores."
        ),
    }


def _skip(source: str, reason: str) -> dict[str, Any]:
    report = _base_report(source)
    report.update({"ok": True, "skipped": True, "status": "skipped", "reason": reason})
    return report


def _run_command(argv: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            input=input_text,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=12,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124)


def _write_manifest(root: Path, *, source: str, locator: dict[str, Any]) -> Path:
    manifest_path = root / "provider-key-bridge.json"
    manifest = provider_key_bridge.build_bridge_manifest(
        target="codex-hooks",
        source=source,
        provider_env_var=ENV_VAR,
        keychain_service=locator.get("service"),
        keychain_account=locator.get("account"),
        credential_target=locator.get("target_name"),
        selector_attributes=locator.get("attributes"),
    )
    provider_key_bridge.write_bridge_manifest(manifest_path, manifest)
    return manifest_path


def _public_result(
    *,
    source: str,
    manifest_path: Path,
    secret: str,
    locator_tokens: list[str],
    cleanup_attempted: bool,
    cleanup_ok: bool,
) -> dict[str, Any]:
    update = hook_provider_bridge.environment_update_from_manifest(manifest_path)
    manifest_text = manifest_path.read_text(encoding="utf-8")
    summary = provider_key_bridge.public_manifest_summary(manifest_path)
    report = _base_report(source)
    report.update(
        {
            "ok": update.get(ENV_VAR) == secret,
            "status": "adapter_read_ok" if update.get(ENV_VAR) == secret else "adapter_read_failed",
            "skipped": False,
            "result": {
                "env_var": ENV_VAR,
                "environment_update_contains_key": ENV_VAR in update,
                "environment_update_matches_secret": update.get(ENV_VAR) == secret,
                "manifest_summary": summary,
            },
            "cleanup": {
                "attempted": cleanup_attempted,
                "ok": cleanup_ok,
            },
        }
    )
    encoded_public = json.dumps(report, ensure_ascii=False, sort_keys=True)
    locator_leaked = any(token and token in encoded_public for token in locator_tokens)
    local_path_leaked = str(manifest_path.parent) in encoded_public
    leak = secret in encoded_public or locator_leaked or local_path_leaked
    report["privacy"]["manifest_contains_secret_value"] = secret in manifest_text
    report["privacy"]["secret_values_printed"] = secret in encoded_public
    report["privacy"]["locator_values_printed"] = locator_leaked
    report["privacy"]["local_paths_included"] = local_path_leaked
    report["privacy"]["public_report_contains_secret_or_locator"] = leak
    if report["privacy"]["manifest_contains_secret_value"] or leak:
        report["ok"] = False
        report["status"] = "privacy_leak_detected"
    return report


def _windows_write_credential(target_name: str, secret: str) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "not_windows"

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", ctypes.c_ulong),
            ("Type", ctypes.c_ulong),
            ("TargetName", ctypes.c_wchar_p),
            ("Comment", ctypes.c_wchar_p),
            ("LastWritten", ctypes.c_byte * 8),
            ("CredentialBlobSize", ctypes.c_ulong),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", ctypes.c_ulong),
            ("AttributeCount", ctypes.c_ulong),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", ctypes.c_wchar_p),
            ("UserName", ctypes.c_wchar_p),
        ]

    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return False, "missing_ctypes_windll"
    advapi32 = windll.advapi32
    blob = secret.encode("utf-16-le")
    blob_buffer = ctypes.create_string_buffer(blob)
    credential = CREDENTIALW()
    credential.Type = 1
    credential.TargetName = target_name
    credential.CredentialBlobSize = len(blob)
    credential.CredentialBlob = ctypes.cast(blob_buffer, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = 1
    credential.UserName = "AIppocampus"
    write = advapi32.CredWriteW
    write.argtypes = [ctypes.POINTER(CREDENTIALW), ctypes.c_ulong]
    write.restype = ctypes.c_bool
    if not write(ctypes.byref(credential), 0):
        return False, "credwrite_failed"
    return True, "written"


def _windows_delete_credential(target_name: str) -> bool:
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return False
    delete = windll.advapi32.CredDeleteW
    delete.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong]
    delete.restype = ctypes.c_bool
    return bool(delete(target_name, 1, 0))


def smoke_windows(run_id: str, secret: str) -> dict[str, Any]:
    source = "windows-credential-manager"
    if os.name != "nt":
        return _skip(source, "requires_windows")
    target_name = f"AIppocampus/provider-key-bridge-smoke/{run_id}"
    cleanup_attempted = False
    cleanup_ok = False
    with tempfile.TemporaryDirectory(prefix="aippocampus-provider-bridge-") as tmp:
        root = Path(tmp)
        written, reason = _windows_write_credential(target_name, secret)
        if not written:
            return {**_base_report(source), "status": reason, "issues": [{"code": reason}]}
        try:
            manifest = _write_manifest(
                root,
                source=source,
                locator={"target_name": target_name},
            )
            report = _public_result(
                source=source,
                manifest_path=manifest,
                secret=secret,
                locator_tokens=[target_name],
                cleanup_attempted=False,
                cleanup_ok=False,
            )
        finally:
            cleanup_attempted = True
            cleanup_ok = _windows_delete_credential(target_name)
    report["cleanup"] = {"attempted": cleanup_attempted, "ok": cleanup_ok}
    if not cleanup_ok:
        report["ok"] = False
        report["status"] = "cleanup_failed"
    return report


def smoke_macos(run_id: str, secret: str) -> dict[str, Any]:
    source = "macos-keychain"
    if sys.platform != "darwin":
        return _skip(source, "requires_macos")
    security = shutil.which("security")
    if not security:
        return _skip(source, "missing_security_cli")
    service = f"AIppocampus provider bridge smoke {run_id}"
    account = "aippocampus-smoke"
    cleanup_attempted = False
    cleanup_ok = False
    with tempfile.TemporaryDirectory(prefix="aippocampus-provider-bridge-") as tmp:
        root = Path(tmp)
        add = _run_command(
            [
                security,
                "add-generic-password",
                "-U",
                "-s",
                service,
                "-a",
                account,
                "-w",
                secret,
            ]
        )
        if add.returncode != 0:
            return _skip(source, "security_add_generic_password_unavailable")
        try:
            manifest = _write_manifest(
                root,
                source=source,
                locator={"service": service, "account": account},
            )
            report = _public_result(
                source=source,
                manifest_path=manifest,
                secret=secret,
                locator_tokens=[service, account],
                cleanup_attempted=False,
                cleanup_ok=False,
            )
        finally:
            cleanup_attempted = True
            cleanup = _run_command(
                [security, "delete-generic-password", "-s", service, "-a", account]
            )
            cleanup_ok = cleanup.returncode == 0
    report["cleanup"] = {"attempted": cleanup_attempted, "ok": cleanup_ok}
    if not cleanup_ok:
        report["ok"] = False
        report["status"] = "cleanup_failed"
    return report


def smoke_linux(run_id: str, secret: str) -> dict[str, Any]:
    source = "linux-secret-service"
    if not sys.platform.startswith("linux"):
        return _skip(source, "requires_linux")
    secret_tool = shutil.which("secret-tool")
    if not secret_tool:
        return _skip(source, "missing_secret_tool")
    attrs = {
        "service": "aippocampus-provider-bridge-smoke",
        "account": run_id,
    }
    attr_args = [item for pair in sorted(attrs.items()) for item in pair]
    cleanup_attempted = False
    cleanup_ok = False
    with tempfile.TemporaryDirectory(prefix="aippocampus-provider-bridge-") as tmp:
        root = Path(tmp)
        store = _run_command(
            [secret_tool, "store", "--label", "AIppocampus provider bridge smoke", *attr_args],
            input_text=secret,
        )
        if store.returncode != 0:
            return _skip(source, "secret_service_store_unavailable")
        try:
            manifest = _write_manifest(
                root,
                source=source,
                locator={"attributes": attrs},
            )
            report = _public_result(
                source=source,
                manifest_path=manifest,
                secret=secret,
                locator_tokens=list(attrs.values()),
                cleanup_attempted=False,
                cleanup_ok=False,
            )
        finally:
            cleanup_attempted = True
            cleanup = _run_command([secret_tool, "clear", *attr_args], input_text="y\n")
            cleanup_ok = cleanup.returncode == 0
    report["cleanup"] = {"attempted": cleanup_attempted, "ok": cleanup_ok}
    if not cleanup_ok:
        report["ok"] = False
        report["status"] = "cleanup_failed"
    return report


def default_source() -> str:
    if os.name == "nt":
        return "windows-credential-manager"
    if sys.platform == "darwin":
        return "macos-keychain"
    return "linux-secret-service"


def run_smoke(source: str) -> dict[str, Any]:
    selected = default_source() if source == "auto" else source
    run_id = uuid.uuid4().hex
    secret = _test_secret(run_id)
    if selected == "windows-credential-manager":
        return smoke_windows(run_id, secret)
    if selected == "macos-keychain":
        return smoke_macos(run_id, secret)
    if selected == "linux-secret-service":
        return smoke_linux(run_id, secret)
    return {**_base_report(selected), "status": "unsupported_source"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=("auto", *SUPPORTED_SOURCES), default="auto")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = run_smoke(args.source)
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "skipped" if report.get("skipped") else "ok" if report.get("ok") else "failed"
        print(f"provider-key bridge OS store smoke: {status} ({report.get('status')})")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
