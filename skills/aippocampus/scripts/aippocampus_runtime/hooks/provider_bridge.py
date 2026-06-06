#!/usr/bin/env python3
"""Opt-in provider-key bridge wrapper for Codex hooks.

This module is only used after `aippocampus onboard provider-key --apply`
installs an explicit bridge manifest. The ordinary prompt and lifecycle hooks
remain env-only; this wrapper fetches the configured private key source, sets the
selected env var for this hook process, then delegates to the original hook.
Failures are fail-open so source-backed hook behavior can still run without
provider lift.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
from typing import Any

from aippocampus_runtime.ops.provider_credentials import dotenv_values

LIFECYCLE_EVENTS = {"SessionStart", "Stop", "PreCompact", "PostCompact"}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _command_secret(argv: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def _macos_keychain_secret(source: dict[str, Any]) -> str | None:
    service = str(source.get("service") or "").strip()
    if not service:
        return None
    argv = ["security", "find-generic-password", "-w", "-s", service]
    account = str(source.get("account") or "").strip()
    if account:
        argv.extend(["-a", account])
    return _command_secret(argv)


def _linux_secret_service_secret(source: dict[str, Any]) -> str | None:
    raw_attrs = source.get("attributes")
    attrs = raw_attrs if isinstance(raw_attrs, dict) else {}
    if not attrs:
        return None
    argv = ["secret-tool", "lookup"]
    for key, value in sorted(attrs.items()):
        argv.extend([str(key), str(value)])
    return _command_secret(argv)


def _decode_windows_credential_blob(blob: bytes) -> str:
    for encoding in ("utf-16-le", "utf-8"):
        try:
            text = blob.decode(encoding).rstrip("\x00")
        except UnicodeDecodeError:
            continue
        if text:
            return text
    return ""


def _windows_credential_manager_secret(source: dict[str, Any]) -> str | None:
    if os.name != "nt":
        return None
    target_name = str(source.get("target_name") or "").strip()
    if not target_name:
        return None

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", ctypes.c_ulong),
            ("Type", ctypes.c_ulong),
            ("TargetName", ctypes.c_wchar_p),
            ("Comment", ctypes.c_wchar_p),
            ("LastWritten", FILETIME),
            ("CredentialBlobSize", ctypes.c_ulong),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", ctypes.c_ulong),
            ("AttributeCount", ctypes.c_ulong),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", ctypes.c_wchar_p),
            ("UserName", ctypes.c_wchar_p),
        ]

    credential_ptr = ctypes.POINTER(CREDENTIALW)()
    advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
    read = advapi32.CredReadW
    read.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.POINTER(CREDENTIALW)),
    ]
    read.restype = ctypes.c_bool
    free = advapi32.CredFree
    free.argtypes = [ctypes.c_void_p]
    free.restype = None
    if not read(target_name, 1, 0, ctypes.byref(credential_ptr)):
        return None
    try:
        credential = credential_ptr.contents
        size = int(credential.CredentialBlobSize or 0)
        if not credential.CredentialBlob or size <= 0:
            return None
        return _decode_windows_credential_blob(ctypes.string_at(credential.CredentialBlob, size))
    finally:
        free(credential_ptr)


def environment_update_from_manifest(manifest_path: str | Path) -> dict[str, str]:
    manifest = _load_json(Path(manifest_path))
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    env_var = str(manifest.get("provider_env_var") or source.get("env_var") or "").strip()
    if not env_var:
        return {}
    source_kind = str(source.get("kind") or "").strip().replace("_", "-").casefold()
    value: str | None
    if source_kind == "explicit-dotenv":
        dotenv_path = str(source.get("dotenv_path") or "").strip()
        value = dotenv_values(Path(dotenv_path)).get(env_var) if dotenv_path else None
    elif source_kind == "macos-keychain":
        value = _macos_keychain_secret(source)
    elif source_kind == "windows-credential-manager":
        value = _windows_credential_manager_secret(source)
    elif source_kind == "linux-secret-service":
        value = _linux_secret_service_secret(source)
    else:
        value = None
    return {env_var: value} if value is not None else {}


def _event_from_hook_stdin(raw: str) -> str:
    if not raw.strip():
        return ""
    try:
        data = json.loads(raw)
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("hook_event_name") or data.get("event") or "")


def _delegate(event: str, args: list[str]) -> int:
    if event in LIFECYCLE_EVENTS:
        from aippocampus_runtime.hooks import lifecycle  # noqa: PLC0415

        return int(lifecycle.main(args) or 0)
    from aippocampus_runtime.hooks import prompt  # noqa: PLC0415

    return int(prompt.main(args) or 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--manifest", required=True)
    known, remaining = parser.parse_known_args(argv)
    raw_stdin = sys.stdin.read()
    for key, value in environment_update_from_manifest(known.manifest).items():
        os.environ[key] = value
    event = _event_from_hook_stdin(raw_stdin)
    old_stdin = sys.stdin
    sys.stdin = StringIO(raw_stdin)
    try:
        return _delegate(event, remaining)
    finally:
        sys.stdin = old_stdin


if __name__ == "__main__":
    raise SystemExit(main())
