from __future__ import annotations

import os
import time
from pathlib import Path

MAX_HOST_TIMEOUT_SLEEP_SECONDS = 1.25


def host_timeout_sleep(seconds: float, *, reason: str) -> None:
    """Bound the few tests that intentionally exercise real host-time timeout paths."""
    if not reason.strip():
        raise AssertionError("host timeout sleeps need a reason at the call site")
    if seconds <= 0 or seconds > MAX_HOST_TIMEOUT_SLEEP_SECONDS:
        raise AssertionError(
            f"host timeout sleep must be in (0, {MAX_HOST_TIMEOUT_SLEEP_SECONDS}], got {seconds}"
        )
    time.sleep(seconds)


def advance_file_mtime(path: Path, *, seconds: float = 2.0) -> None:
    """Force a cache-visible mtime tick without waiting on filesystem resolution."""
    stat = path.stat()
    bump_ns = max(1, int(seconds * 1_000_000_000))
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + bump_ns))
