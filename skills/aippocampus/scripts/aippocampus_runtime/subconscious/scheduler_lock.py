"""Local lock helper for the hook-safe subconscious scheduler."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from aippocampus_runtime.core import now_utc

DEFAULT_STALE_LOCK_SECONDS = 2 * 60 * 60


class FileLock:
    def __init__(self, path: Path, *, stale_seconds: int = DEFAULT_STALE_LOCK_SECONDS) -> None:
        self.path = path
        self.stale_seconds = stale_seconds
        self.fd: int | None = None
        self.recovered_stale_lock = False
        self.stale_age_seconds: int | None = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        last_exists: FileExistsError | None = None
        for _attempt in range(2):
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as exc:
                last_exists = exc
                try:
                    age = max(0.0, time.time() - self.path.stat().st_mtime)
                except OSError:
                    age = 0.0
                if age <= self.stale_seconds:
                    raise RuntimeError(
                        "subconscious scheduler already running: "
                        f"active local lock {self.path.name} "
                        f"age={age:.1f}s threshold={self.stale_seconds}s"
                    ) from exc
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as unlink_exc:
                    raise RuntimeError(
                        "subconscious scheduler already running: "
                        f"stale local lock {self.path.name} could not be removed"
                    ) from unlink_exc
                self.recovered_stale_lock = True
                self.stale_age_seconds = int(age)
                continue
            payload: dict[str, object] = {"pid": os.getpid(), "created_at": now_utc()}
            if self.recovered_stale_lock:
                payload.update(
                    {
                        "recovered_stale_lock": True,
                        "stale_age_seconds": self.stale_age_seconds,
                        "stale_threshold_seconds": self.stale_seconds,
                    }
                )
            os.write(self.fd, json.dumps(payload).encode("utf-8"))
            return self
        raise RuntimeError(
            "subconscious scheduler already running: stale local lock recovery raced"
        ) from last_exists

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        try:
            self.path.unlink()
        except OSError:
            pass
