#!/usr/bin/env python3
"""Owner-checked local file leases for AIppocampus writers.

These leases are deliberately local and best-effort. They are not a
distributed lock. The important contract is narrower: stale recovery and
release must not delete a fresh owner generation after another process has
acquired the same path.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import now_utc


class OwnerCheckedLeaseBusyError(RuntimeError):
    """Raised when a local lease stays active past the caller's wait budget."""

    def __init__(self, path: Path, *, wait_timeout_seconds: float) -> None:
        self.path = path
        self.wait_timeout_seconds = wait_timeout_seconds
        super().__init__(f"local writer lease busy: {path}")


class OwnerCheckedLeaseChangedError(RuntimeError):
    """Raised when stale recovery observes a different owner generation."""


class OwnerCheckedFileLease:
    """Create an exclusive local lease and release only the acquired generation."""

    def __init__(
        self,
        path: Path,
        *,
        lock_kind: str,
        stale_after_seconds: float,
        wait_timeout_seconds: float = 0.0,
        poll_interval_seconds: float = 0.05,
        payload_extra: dict[str, Any] | None = None,
        busy_message: str | None = None,
    ) -> None:
        self.path = path
        self.lock_kind = lock_kind
        self.stale_after_seconds = float(stale_after_seconds)
        self.wait_timeout_seconds = float(wait_timeout_seconds)
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.payload_extra = dict(payload_extra or {})
        self.busy_message = busy_message
        self.owner_token = f"{lock_kind}_{uuid.uuid4().hex}"
        self.fd: int | None = None
        self.recovered_stale_lock = False
        self.stale_age_seconds: float | None = None
        self.acquire_diagnostic: dict[str, Any] = {}
        self.release_diagnostic: dict[str, Any] = {}

    def _open_new_generation(self) -> int:
        return os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)

    def _read_payload(self, path: Path | None = None) -> dict[str, Any]:
        try:
            payload = json.loads((path or self.path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _snapshot(self) -> dict[str, Any]:
        stat = self.path.stat()
        payload = self._read_payload()
        identity = {
            "owner_token": payload.get("owner_token"),
            "pid": payload.get("pid"),
            "created_at": payload.get("created_at"),
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
        }
        return {
            "payload": payload,
            "identity": identity,
            "age_seconds": max(0.0, time.time() - stat.st_mtime),
        }

    def _quarantine_stale_snapshot(self, snapshot: dict[str, Any]) -> None:
        quarantine = self.path.with_name(
            f".{self.path.name}.{self.owner_token}.stale"
        )
        try:
            self.path.replace(quarantine)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise OwnerCheckedLeaseChangedError(
                f"{self.lock_kind} stale local lease could not be quarantined"
            ) from exc

        moved_payload = self._read_payload(quarantine)
        try:
            moved_stat = quarantine.stat()
        except OSError as exc:
            raise OwnerCheckedLeaseChangedError(
                f"{self.lock_kind} stale local lease disappeared during quarantine"
            ) from exc
        moved_identity = {
            "owner_token": moved_payload.get("owner_token"),
            "pid": moved_payload.get("pid"),
            "created_at": moved_payload.get("created_at"),
            "mtime_ns": moved_stat.st_mtime_ns,
            "size": moved_stat.st_size,
        }
        if moved_identity != snapshot["identity"]:
            if not self.path.exists():
                try:
                    quarantine.replace(self.path)
                except OSError:
                    pass
            raise OwnerCheckedLeaseChangedError(
                f"{self.lock_kind} local lease changed during stale recovery"
            )
        try:
            quarantine.unlink()
        except FileNotFoundError:
            pass

    def _payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": 1,
            "kind": "aippocampus_owner_checked_file_lease",
            "lock_kind": self.lock_kind,
            "pid": os.getpid(),
            "created_at": now_utc(),
            "owner_token": self.owner_token,
            "stale_after_seconds": int(self.stale_after_seconds),
            "best_effort_local_lock": True,
            "recovered_stale_lock": self.recovered_stale_lock,
        }
        if self.recovered_stale_lock:
            payload["stale_age_seconds"] = int(self.stale_age_seconds or 0)
            payload["stale_threshold_seconds"] = int(self.stale_after_seconds)
        payload.update(self.payload_extra)
        return payload

    def __enter__(self) -> "OwnerCheckedFileLease":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + max(0.0, self.wait_timeout_seconds)
        while True:
            try:
                self.fd = self._open_new_generation()
            except (FileExistsError, PermissionError) as exc:
                try:
                    snapshot = self._snapshot()
                except (FileNotFoundError, PermissionError, OSError):
                    # Windows can briefly deny O_EXCL/create while another
                    # waiter or releaser is touching the lock path, even before
                    # the payload is readable. Treat that as the same active
                    # lease contention as FileExistsError; raising here makes
                    # concurrent semantic-cache writers fail instead of queue.
                    if time.monotonic() < deadline:
                        time.sleep(max(0.01, self.poll_interval_seconds))
                        continue
                    raise OwnerCheckedLeaseBusyError(
                        self.path,
                        wait_timeout_seconds=self.wait_timeout_seconds,
                    ) from exc
                age = float(snapshot["age_seconds"])
                if age > self.stale_after_seconds:
                    self.recovered_stale_lock = True
                    self.stale_age_seconds = age
                    self.acquire_diagnostic = {
                        "recovered_stale_lock": True,
                        "stale_age_seconds": round(age, 3),
                        "stale_threshold_seconds": self.stale_after_seconds,
                        "stale_owner_token": snapshot["payload"].get("owner_token"),
                        "stale_pid": snapshot["payload"].get("pid"),
                    }
                    self._quarantine_stale_snapshot(snapshot)
                    continue
                if time.monotonic() < deadline:
                    time.sleep(max(0.01, self.poll_interval_seconds))
                    continue
                raise OwnerCheckedLeaseBusyError(
                    self.path,
                    wait_timeout_seconds=self.wait_timeout_seconds,
                ) from exc
            os.write(self.fd, json.dumps(self._payload(), sort_keys=True).encode("utf-8"))
            return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        deadline = time.monotonic() + max(0.25, min(2.0, self.poll_interval_seconds * 20))
        while True:
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
                return
            except FileNotFoundError:
                self.release_diagnostic = {"released": True, "already_absent": True}
                return
            except OSError as exc:
                if time.monotonic() >= deadline:
                    self.release_diagnostic = {
                        "released": False,
                        "reason": type(exc).__name__,
                    }
                    return
                # On Windows a concurrent waiter can briefly hold a read handle
                # on the lock payload while checking owner/stale status. The
                # owner token still proves this is our generation; retrying the
                # unlink avoids leaving a fresh orphan lock that makes every
                # later writer time out until stale recovery.
                time.sleep(max(0.01, min(0.05, self.poll_interval_seconds)))
