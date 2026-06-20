#!/usr/bin/env python3
"""Best-effort local writer lock helpers for Dream background writes."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import now_utc


class FileLock:
    """Local JSON-file lock that only releases the generation it acquired.

    This is intentionally not a distributed lock. It protects explicit local
    Dream write commands from interleaving on filesystems without a shared flock
    primitive, while foreground readers continue to avoid waiting on Dream
    writer locks.
    """

    def __init__(self, path: Path, *, stale_seconds: int) -> None:
        self.path = path
        self.stale_seconds = stale_seconds
        self.owner_token = f"dreamlock_{uuid.uuid4().hex}"
        self.fd: int | None = None
        self.recovered_stale_lock = False
        self.acquire_diagnostic: dict[str, Any] = {}
        self.release_diagnostic: dict[str, Any] = {}

    def _read_payload(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _open_new_generation(self) -> int:
        return os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = self._open_new_generation()
        except FileExistsError as exc:
            try:
                age = max(0.0, time.time() - self.path.stat().st_mtime)
            except OSError:
                age = 0.0
            if age <= self.stale_seconds:
                raise RuntimeError("dream sleep-cycle writes already locked") from exc
            stale_payload = self._read_payload()
            self.acquire_diagnostic = {
                "recovered_stale_lock": True,
                "stale_age_seconds": round(age, 3),
                "stale_threshold_seconds": self.stale_seconds,
                "stale_owner_token": stale_payload.get("owner_token"),
                "stale_pid": stale_payload.get("pid"),
            }
            self.recovered_stale_lock = True
            try:
                self.path.unlink()
            except OSError:
                pass
            try:
                self.fd = self._open_new_generation()
            except FileExistsError as retry_exc:
                raise RuntimeError("dream sleep-cycle lock changed during stale recovery") from retry_exc
        payload = {
            "pid": os.getpid(),
            "created_at": now_utc(),
            "owner_token": self.owner_token,
            "lock_kind": "dream_sleep_cycle_write",
            "best_effort_local_lock": True,
            "foreground_readers_wait": False,
            "recovered_stale_lock": self.recovered_stale_lock,
        }
        os.write(self.fd, json.dumps(payload, sort_keys=True).encode("utf-8"))
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        payload = self._read_payload()
        if payload.get("owner_token") != self.owner_token:
            self.release_diagnostic = {
                "released": False,
                "reason": "owner_token_changed",
                "observed_owner_token": payload.get("owner_token"),
            }
            return
        try:
            self.path.unlink()
            self.release_diagnostic = {"released": True}
        except OSError as exc:
            self.release_diagnostic = {"released": False, "reason": type(exc).__name__}

    def diagnostic(self) -> dict[str, Any]:
        return {
            "lock_kind": "dream_sleep_cycle_write",
            "best_effort_local_lock": True,
            "foreground_readers_wait": False,
            "owner_token_matched_on_release": self.release_diagnostic.get("released") is True,
            "recovered_stale_lock": self.recovered_stale_lock,
            "stale_recovery": dict(self.acquire_diagnostic),
            "release": dict(self.release_diagnostic),
        }
