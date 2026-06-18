"""Small integrity helpers for local AIppocampus state writes.

These helpers are deliberately boring and local-only. They prevent half-written
JSON/JSONL artifacts from becoming silent recall state, and they keep persisted
diagnostics on the public-safe side of the privacy boundary. Do not broaden the
stale-tmp sweep to arbitrary filenames: cleanup must stay limited to temporary
files created by AIppocampus writers or plugin installers.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import (
    now_utc,
    sanitize_external_model_payload,
)

TMP_SUFFIX = ".tmp"
PLUGIN_INSTALL_TMP_SUFFIX = ".tmp-aippocampus-install"


def public_safe_payload(value: Any, *, project_root: str | Path | None = None) -> Any:
    """Return a persisted-state projection with paths/secrets redacted."""

    return sanitize_external_model_payload(value, project_root=project_root)


def _atomic_replace_bytes(path: Path, payload_bytes: bytes) -> None:
    """Write bytes by same-directory tmp+replace.

    Same-directory replacement keeps the operation atomic on normal local
    filesystems and avoids cross-device rename surprises. The tmp name is
    AIppocampus-specific so startup sweeps can identify interrupted writes
    without touching unrelated user files.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.aippocampus-{os.getpid()}-{time.time_ns()}{TMP_SUFFIX}")
    try:
        with tmp.open("xb") as handle:
            # This low-level writer serves both public-safe generated state and
            # private local control manifests. Callers own that boundary through
            # `sanitize=True`; provider bridge locators must remain executable
            # on the local machine and are not public artifacts.
            handle.write(payload_bytes)
        tmp.replace(path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def atomic_write_json(
    path: Path,
    payload: Mapping[str, Any],
    *,
    sanitize: bool = False,
    project_root: str | Path | None = None,
    indent: int | None = 2,
) -> None:
    data: Any = public_safe_payload(dict(payload), project_root=project_root) if sanitize else dict(payload)
    body = json.dumps(data, ensure_ascii=False, indent=indent)
    _atomic_replace_bytes(path, body.encode("utf-8"))


def atomic_write_jsonl(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    sanitize: bool = False,
    project_root: str | Path | None = None,
    sort_keys: bool = False,
) -> None:
    materialized = [dict(row) for row in rows]
    if sanitize:
        materialized = [
            public_safe_payload(row, project_root=project_root) for row in materialized
        ]
    body = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=sort_keys) + "\n"
        for row in materialized
    )
    _atomic_replace_bytes(path, body.encode("utf-8"))


def stale_tmp_recovery_card(root: Path, *, max_age_seconds: float = 300.0) -> dict[str, Any]:
    """Inspect AIppocampus temporary artifacts under one root.

    The card is safe for foreground startup/readiness paths: it reports counts
    and one recovery command, not private paths. Callers that own a specific
    operator view may expose exact paths behind an explicit detail mode.
    """

    now = time.time()
    stale_tmp = 0
    plugin_orphans = 0
    if root.exists():
        for item in root.rglob("*"):
            name = item.name
            if not (
                name.endswith(TMP_SUFFIX)
                or name.endswith(PLUGIN_INSTALL_TMP_SUFFIX)
                or ".aippocampus-" in name
            ):
                continue
            try:
                age = now - item.stat().st_mtime
            except OSError:
                continue
            if age < max_age_seconds:
                continue
            if item.is_dir() and name.endswith(PLUGIN_INSTALL_TMP_SUFFIX):
                plugin_orphans += 1
            elif item.is_file() and name.endswith(TMP_SUFFIX):
                stale_tmp += 1
    found = stale_tmp + plugin_orphans
    return {
        "kind": "aippocampus_interrupted_write_recovery",
        "ok": found == 0,
        "status": "ok" if found == 0 else "interrupted_write_artifacts_found",
        "checked_at": now_utc(),
        "stale_tmp_file_count": stale_tmp,
        "orphaned_plugin_install_dir_count": plugin_orphans,
        "foreground_action": (
            {
                "id": "review_interrupted_writes",
                "command": "aippocampus maintenance status --json",
                "mutation_risk": "read_only",
                "claim_boundary": "local_recovery_diagnostic_not_source_truth",
                "why": "Interrupted write artifacts were detected; review maintenance before relying on generated recall state.",
            }
            if found
            else {
                "id": "no_interrupted_write_artifacts",
                "kind": "no_op",
                "mutation_risk": "none",
                "claim_boundary": "local_recovery_diagnostic_not_source_truth",
                "why": "No stale AIppocampus tmp or orphaned plugin install artifacts were detected.",
            }
        ),
    }
