"""Recipient collection helpers for encrypted sync migration."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from aippocampus_runtime.sync.encrypted import keys as encrypted_sync_keys
from aippocampus_runtime.sync.encrypted.crypto import recipients_from_files, validate_recipients


def collect_recipients_for_registry(
    registry_dir: str | Path,
    *,
    recipients: Iterable[str] | None = None,
    recipient_files: Iterable[str | Path] | None = None,
) -> tuple[list[str], dict | None]:
    explicit, explicit_issue = validate_recipients(recipients or [])
    if explicit_issue and recipients:
        return [], explicit_issue
    file_recipients, file_issue = recipients_from_files(recipient_files)
    if file_issue and recipient_files:
        return [], file_issue
    trusted = (
        encrypted_sync_keys.trusted_recipients_for_registry(registry_dir)
        if not explicit and not file_recipients
        else []
    )
    return validate_recipients(explicit + file_recipients + trusted)
