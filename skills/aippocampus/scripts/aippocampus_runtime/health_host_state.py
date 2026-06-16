"""Public-safe Codex host-state confound diagnostics for health output."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from aippocampus_runtime.ops.storage_governance_contract import human_bytes

MAX_SCAN_FILES = 5000


def _size_bucket(size: int) -> str:
    if size <= 0:
        return "empty"
    if size < 10 * 1024 * 1024:
        return "small"
    if size < 256 * 1024 * 1024:
        return "medium"
    if size < 1024 * 1024 * 1024:
        return "large"
    return "very_large"


def _safe_stat_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def _iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    try:
        return (path for path in root.rglob("*") if path.is_file())
    except OSError:
        return []


def _tree_summary(root: Path, *, suffixes: tuple[str, ...] | None = None) -> dict[str, Any]:
    total = 0
    count = 0
    truncated = False
    suffix_set = tuple(item.casefold() for item in suffixes or ())
    for path in _iter_files(root):
        name = path.name.casefold()
        if suffix_set and not any(name.endswith(suffix) for suffix in suffix_set):
            continue
        count += 1
        if count > MAX_SCAN_FILES:
            truncated = True
            break
        total += _safe_stat_size(path)
    return {
        "available": root.exists(),
        "file_count": min(count, MAX_SCAN_FILES),
        "total_bytes": total,
        "total_human": human_bytes(total),
        "size_bucket": _size_bucket(total),
        "scan_truncated": truncated,
        "paths_included": False,
    }


def _known_file_summary(home: Path, names: tuple[str, ...]) -> dict[str, Any]:
    total = 0
    count = 0
    for name in names:
        path = home / name
        size = _safe_stat_size(path)
        if size:
            count += 1
            total += size
    return {
        "available": count > 0,
        "file_count": count,
        "total_bytes": total,
        "total_human": human_bytes(total),
        "size_bucket": _size_bucket(total),
        "paths_included": False,
    }


def codex_host_state_confounds(home: Path) -> dict[str, Any]:
    """Return aggregate host-state pressure hints without local paths or contents.

    These diagnostics explain possible Codex Desktop/local-host drag separately
    from AIppocampus registry or generated-cache pressure. They must never become
    a default recommendation to disable AIppocampus.
    """

    resolved = Path(home).expanduser()
    logs_db_wal = _tree_summary(
        resolved / "logs",
        suffixes=(".db", ".sqlite", ".sqlite3", ".db-wal", ".sqlite-wal", ".log"),
    )
    session_store = _tree_summary(resolved / "sessions")
    archived_sessions = _tree_summary(resolved / "archived_sessions")
    thread_list = _known_file_summary(
        resolved,
        ("threads.json", "thread-list.json", "thread_list.json", "history.json"),
    )
    available = any(
        section.get("available")
        for section in (logs_db_wal, session_store, archived_sessions, thread_list)
    )
    total_bytes = sum(
        int(section.get("total_bytes") or 0)
        for section in (logs_db_wal, session_store, archived_sessions, thread_list)
    )
    return {
        "available": available,
        "status": "observed" if available else "not_available",
        "artifact_scope": "codex_host_state_not_aippocampus_registry",
        "total_observed_bytes": total_bytes,
        "total_observed_human": human_bytes(total_bytes),
        "size_bucket": _size_bucket(total_bytes),
        "logs_db_wal": logs_db_wal,
        "session_store": session_store,
        "archived_session_store": archived_sessions,
        "thread_list": thread_list,
        "startup_latency": {
            "available": False,
            "bucket": "not_measured",
            "reason": "health does not time Codex Desktop startup",
        },
        "privacy_boundary": {
            "paths_included": False,
            "file_names_included": False,
            "raw_thread_ids_included": False,
            "prompt_text_read": False,
        },
        "claim_boundary": (
            "Host-state size can confound local performance diagnostics; it is separate "
            "from AIppocampus registry/cache metrics and is not evidence that hooks "
            "should be disabled."
        ),
    }
