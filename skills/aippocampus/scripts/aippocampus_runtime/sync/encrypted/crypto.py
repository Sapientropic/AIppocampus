#!/usr/bin/env python3
"""Small age CLI boundary for AIppocampus encrypted sync."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable


class EncryptedSyncError(RuntimeError):
    """Raised when encrypted sync preflight or decryption fails."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def issue(code: str, message: str, **extra: Any) -> dict[str, Any]:
    data = {"code": code, "message": message}
    data.update(extra)
    return data


def validate_recipients(recipients: Iterable[str] | None) -> tuple[list[str], dict[str, Any] | None]:
    collected: list[str] = []
    for value in recipients or []:
        text = str(value).strip()
        if not text:
            continue
        if text.startswith("AGE-SECRET-KEY"):
            return [], issue(
                "recipient_secret_rejected",
                "AGE-SECRET-KEY values are private identities; pass public recipients to --recipient",
            )
        collected.append(text)
    if not collected:
        return [], issue("recipient_missing", "encrypted sync push requires at least one recipient")
    return collected, None


def recipients_from_files(
    paths: Iterable[str | Path] | None,
) -> tuple[list[str], dict[str, Any] | None]:
    recipients: list[str] = []
    for raw_path in paths or []:
        path = Path(raw_path)
        if not path.is_file():
            return [], issue("recipient_file_missing", f"recipient file not found: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if text and not text.startswith("#"):
                recipients.append(text)
    return validate_recipients(recipients)


def resolve_age_binary(age_bin: str | Path | None = None) -> tuple[str | None, dict[str, Any] | None]:
    candidate = str(age_bin or os.environ.get("AIPPOCAMPUS_AGE_BIN") or "")
    if candidate:
        path = shutil.which(candidate) if not Path(candidate).exists() else candidate
    else:
        path = shutil.which("age")
    if not path:
        return None, issue(
            "age_missing",
            "age binary was not found; install age or set AIPPOCAMPUS_AGE_BIN",
        )
    try:
        proc = subprocess.run(
            [str(path), "--version"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        return None, issue("age_missing", f"failed to run age: {exc}")
    if proc.returncode != 0:
        return None, issue("age_missing", proc.stderr or proc.stdout or "age preflight failed")
    return str(path), None


def run_age(args: list[str], *, wrong_key_code: bool = False) -> None:
    proc = subprocess.run(args, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode == 0:
        return
    stderr = (proc.stderr or proc.stdout or "age command failed").strip()
    code = "wrong_key" if wrong_key_code else "age_failed"
    raise EncryptedSyncError(code, stderr)


def encrypt_with_age(source: Path, destination: Path, *, recipients: list[str], age_bin: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    args = [age_bin]
    for recipient in recipients:
        args.extend(["-r", recipient])
    args.extend(["-o", str(destination), str(source)])
    run_age(args)


def decrypt_with_age(
    source: Path,
    destination: Path,
    *,
    identity_files: Iterable[str | Path] | None,
    age_bin: str,
) -> None:
    identities = [Path(path) for path in identity_files or []]
    if not identities:
        raise EncryptedSyncError("identity_missing", "encrypted sync decrypt requires an identity")
    for identity in identities:
        if not identity.is_file():
            raise EncryptedSyncError("identity_missing", f"identity file not found: {identity}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    args = [age_bin, "-d"]
    for identity in identities:
        args.extend(["-i", str(identity)])
    args.extend(["-o", str(destination), str(source)])
    run_age(args, wrong_key_code=True)
