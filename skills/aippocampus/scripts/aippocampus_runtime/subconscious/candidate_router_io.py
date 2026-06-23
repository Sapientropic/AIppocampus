"""IO and default-path helpers for subconscious candidate routing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.registry.api import registry_paths
from aippocampus_runtime.source.io_kernel import (
    load_json_dict,
    load_jsonl_dict_rows,
)

DEFAULT_CANDIDATES_NAME = "promotion_candidates.jsonl"
DEFAULT_JOBS_NAME = "subconscious_jobs.jsonl"
DEFAULT_WORKING_MEMORY_NAME = "working_memory.jsonl"
DEFAULT_SUMMARY_NAME = "working_memory_summary.json"


def default_candidates_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_CANDIDATES_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_CANDIDATES_NAME


def default_jobs_path(registry_path: Path | None = None, registry_dir: Path | None = None) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_JOBS_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_JOBS_NAME


def default_working_memory_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_WORKING_MEMORY_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_WORKING_MEMORY_NAME


def default_summary_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_SUMMARY_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_SUMMARY_NAME


def load_candidates(path: Path) -> list[dict[str, Any]]:
    return [
        row
        for row in load_jsonl_dict_rows(path).rows
        if row.get("kind") == "aippocampus_promotion_candidate"
    ]


def load_findings_by_id(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in load_jsonl_dict_rows(path).rows:
        if row.get("kind") != "aippocampus_subconscious_job_finding":
            continue
        key = str(row.get("fingerprint") or "")
        if key:
            out[key] = row
    return out


def load_thread_projects(path: Path) -> dict[str, str]:
    registry_path = path.parent / "threads.json"
    data = load_json_dict(registry_path).data
    out: dict[str, str] = {}
    for entry in data.get("threads") or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("thread_key") or "")
        label = str(entry.get("project_label") or entry.get("workspace_name") or "")
        if key and label:
            out[key] = label
    return out
