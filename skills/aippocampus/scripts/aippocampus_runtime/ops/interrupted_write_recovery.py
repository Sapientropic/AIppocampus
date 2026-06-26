"""Interrupted-write recovery helpers for maintenance surfaces."""

from __future__ import annotations

from pathlib import Path

from aippocampus_runtime import health as health_runtime
from aippocampus_runtime.io_tmp_recovery import (
    cleanup_stale_tmp_artifacts,
    stale_tmp_recovery_card,
)
from aippocampus_runtime.privacy import LOCAL_PATH_REDACTION

CLEANUP_INTERRUPTED_WRITES_COMMAND = [
    "aippocampus",
    "maintenance",
    "apply",
    "--cleanup-interrupted-writes",
    "--summary-json",
]


def _registry_root_from_health(health: dict | None) -> Path | None:
    storage = (health or {}).get("storage") if isinstance(health, dict) else {}
    active = storage.get("active_registry") if isinstance(storage, dict) else None
    if isinstance(active, str) and active and active != LOCAL_PATH_REDACTION:
        path = Path(active)
        return path.parent if path.name == "threads.json" else path
    return None


def _registry_root_from_runtime_health(cwd: Path) -> Path | None:
    """Resolve the local registry root from in-process health, before projection.

    The public health CLI deliberately redacts local paths. Maintenance apply
    still needs the real root for local file operations, so never derive write
    targets from projected JSON.
    """

    try:
        health = health_runtime.build_health_report(health_runtime.HealthOptions(cwd=cwd))
    except FileNotFoundError as exc:
        health = health_runtime.missing_rollout_health_report(cwd, exc)
    except Exception:
        return None
    return _registry_root_from_health(health)


def attach_interrupted_write_recovery(
    health: dict | None,
    *,
    registry_root: Path | None = None,
) -> dict | None:
    if health is None:
        return None
    root = registry_root or _registry_root_from_health(health)
    if root is None:
        return health
    recovery = stale_tmp_recovery_card(root)
    enriched = dict(health)
    enriched["interrupted_write_recovery"] = recovery
    if not recovery.get("ok"):
        recommended = list(enriched.get("recommended_actions") or [])
        if not any(
            item.get("id") == "cleanup_interrupted_writes"
            for item in recommended
            if isinstance(item, dict)
        ):
            recommended.append(
                {
                    "id": "cleanup_interrupted_writes",
                    "severity": "warning",
                    "reason": (
                        f"{recovery.get('stale_tmp_file_count', 0)} stale tmp file(s) "
                        f"and {recovery.get('orphaned_plugin_install_dir_count', 0)} "
                        "orphaned plugin install dir(s) were detected."
                    ),
                }
            )
        enriched["recommended_actions"] = recommended
    return enriched


def cleanup_interrupted_write_artifacts(
    *,
    registry_root: Path | None,
    projected_health: dict | None,
) -> dict:
    cleanup_root = registry_root or _registry_root_from_health(projected_health)
    if cleanup_root is None:
        return {
            "kind": "aippocampus_stale_tmp_cleanup",
            "ok": False,
            "dry_run": False,
            "deleted_count": 0,
            "deleted_bytes": 0,
            "deleted_human_bytes": "0 B",
            "failed_count": 1,
            "summary_before_cleanup": {},
            "deleted": [],
            "failed": [
                {
                    "path": LOCAL_PATH_REDACTION,
                    "reason": "registry_root_unavailable_from_internal_health",
                }
            ],
        }
    return cleanup_stale_tmp_artifacts(cleanup_root)
