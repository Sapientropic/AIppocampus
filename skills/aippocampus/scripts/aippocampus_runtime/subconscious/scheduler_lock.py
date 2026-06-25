"""Local lock helper for the hook-safe subconscious scheduler."""

from __future__ import annotations

from pathlib import Path

from aippocampus_runtime.local_file_lock import (
    OwnerCheckedFileLease,
    OwnerCheckedLeaseBusyError,
    OwnerCheckedLeaseChangedError,
)

DEFAULT_STALE_LOCK_SECONDS = 2 * 60 * 60


class FileLock:
    def __init__(self, path: Path, *, stale_seconds: int = DEFAULT_STALE_LOCK_SECONDS) -> None:
        self.path = path
        self.stale_seconds = stale_seconds
        self._lease: OwnerCheckedFileLease | None = None
        self.recovered_stale_lock = False
        self.stale_age_seconds: int | None = None

    def __enter__(self) -> "FileLock":
        lease = OwnerCheckedFileLease(
            self.path,
            lock_kind="subconscious_scheduler",
            stale_after_seconds=float(self.stale_seconds),
            payload_extra={"kind": "aippocampus_subconscious_scheduler_lock"},
        )
        try:
            lease.__enter__()
        except OwnerCheckedLeaseBusyError as exc:
            raise RuntimeError(
                "subconscious scheduler already running: "
                f"active local lock {self.path.name} "
                f"threshold={self.stale_seconds}s"
            ) from exc
        except OwnerCheckedLeaseChangedError as exc:
            raise RuntimeError(
                "subconscious scheduler already running: stale local lock recovery raced"
            ) from exc
        self._lease = lease
        self.recovered_stale_lock = lease.recovered_stale_lock
        self.stale_age_seconds = (
            int(lease.stale_age_seconds) if lease.stale_age_seconds is not None else None
        )
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._lease is not None:
            self._lease.__exit__(exc_type, exc, tb)
            self._lease = None
