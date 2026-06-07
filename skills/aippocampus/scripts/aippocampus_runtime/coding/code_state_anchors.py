"""Public-safe code-state anchors for coding decision events.

Anchors are checkout coordinates for reopening current evidence. They are not
proof of user intent, not a code index, and not raw diff or test-log storage.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_text
from aippocampus_runtime.registry.api import unique_preserve

SCHEMA_VERSION = 1
CODE_STATE_ANCHOR_KIND = "aippocampus_coding_code_state_anchor"
MAX_ANCHORS = 3
MAX_FILES_PER_ANCHOR = 8
MAX_CHECK_REFS = 8
CHECK_STATUSES = {
    "success",
    "failure",
    "neutral",
    "skipped",
    "cancelled",
    "timed_out",
    "pending",
    "unknown",
}


def _public_hash(value: Any, *, length: int = 16) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8", errors="replace")).hexdigest()[:length]


def _safe_text(value: Any, limit: int = 140) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, limit)


def _safe_repo_path(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text or "://" in text or text.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", text):
        return ""
    parts = [part for part in text.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        return ""
    return "/".join(parts[:16])


def _candidate_repo_paths(candidate: Mapping[str, Any]) -> list[str]:
    raw_files = candidate.get("affected_scope", {}).get("files") if isinstance(candidate.get("affected_scope"), Mapping) else []
    if not isinstance(raw_files, Sequence) or isinstance(raw_files, (str, bytes)):
        return []
    paths: list[str] = []
    for item in raw_files:
        raw_path = item.get("path") if isinstance(item, Mapping) else item
        path = _safe_repo_path(raw_path)
        if path:
            paths.append(path)
    return unique_preserve(paths, limit=MAX_FILES_PER_ANCHOR)


def _file_fingerprint(repo_root: Path | str | None, repo_path: str) -> str:
    if not repo_root:
        return ""
    path = Path(repo_root).joinpath(*repo_path.split("/"))
    try:
        if not path.is_file():
            return ""
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return f"sha256:{digest.hexdigest()[:16]}"


def _safe_check_status(value: Any) -> str:
    status = str(value or "unknown").strip().casefold().replace("-", "_")
    return status if status in CHECK_STATUSES else "unknown"


def _has_public_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _safe_check_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    refs: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        name = _safe_text(item.get("name") or item.get("check_name"), 120)
        status = _safe_check_status(item.get("status") or item.get("conclusion"))
        if not name:
            continue
        ref: dict[str, Any] = {"name": name, "status": status}
        check_id = item.get("id") or item.get("check_id") or item.get("run_id")
        if check_id:
            ref["check_id_hash"] = _public_hash(check_id)
        refs.append(ref)
        if len(refs) >= MAX_CHECK_REFS:
            break
    return refs


def build_checkout_code_state_anchor(
    candidate: Mapping[str, Any],
    *,
    repo_root: Path | str | None = None,
    repo_commit: str = "",
    commit_sha: str = "",
    branch_or_head_ref: str = "",
    pr_ref: str = "",
    issue_ref: str = "",
    test_or_check_refs: Sequence[Mapping[str, Any]] | None = None,
    repo_state_fingerprint: str = "",
    dirty_workspace_fingerprint: str = "",
) -> dict[str, Any]:
    """Build a checkout anchor from already-sanitized decision-event scope."""

    files: list[dict[str, Any]] = []
    for repo_path in _candidate_repo_paths(candidate):
        file_row: dict[str, Any] = {"path": repo_path, "change_kind": "observed"}
        fingerprint = _file_fingerprint(repo_root, repo_path)
        if fingerprint:
            file_row["new_file_fingerprint"] = fingerprint
        files.append(file_row)
    normalized_commit = _safe_text(repo_commit or commit_sha, 80)
    branch = _safe_text(branch_or_head_ref, 140)
    anchor = {
        "schema_version": SCHEMA_VERSION,
        "kind": CODE_STATE_ANCHOR_KIND,
        "anchor_id": "code_anchor_"
        + _public_hash(
            [
                candidate.get("decision_id"),
                normalized_commit,
                branch,
                files,
                pr_ref,
                issue_ref,
            ],
            length=18,
        ),
        "decision_event_id": _safe_text(candidate.get("decision_id"), 120),
        "repo_commit": normalized_commit,
        "commit_sha": normalized_commit,
        "branch_or_head_ref": branch,
        "branch_ref_hash": _public_hash(branch) if branch else "",
        "pr_ref": _safe_text(pr_ref, 80),
        "issue_ref": _safe_text(issue_ref, 80),
        "repo_state_fingerprint": _safe_text(repo_state_fingerprint, 120),
        "dirty_workspace_fingerprint": _safe_text(dirty_workspace_fingerprint, 120),
        "file_diff_scope": files,
        "test_or_check_refs": _safe_check_refs(test_or_check_refs or []),
        "source_boundary": "code_state_coordinate_not_user_intent",
        "privacy_boundary": {
            "raw_diffs_serialized": False,
            "raw_test_logs_serialized": False,
            "local_paths_serialized": False,
            "secrets_serialized": False,
        },
    }
    return {key: value for key, value in anchor.items() if _has_public_value(value)}


def _safe_file_scope(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    files: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        path = _safe_repo_path(item.get("path"))
        if not path:
            continue
        clean = {
            "path": path,
            "change_kind": _safe_text(item.get("change_kind") or "observed", 80) or "observed",
            "old_file_fingerprint": _safe_text(item.get("old_file_fingerprint"), 120),
            "new_file_fingerprint": _safe_text(
                item.get("new_file_fingerprint") or item.get("file_fingerprint"),
                120,
            ),
        }
        files.append({key: val for key, val in clean.items() if val})
        if len(files) >= MAX_FILES_PER_ANCHOR:
            break
    return files


def compact_code_state_anchors(
    anchors: Any,
    *,
    limit: int = MAX_ANCHORS,
) -> list[dict[str, Any]]:
    if not isinstance(anchors, Sequence) or isinstance(anchors, (str, bytes)):
        return []
    compact: list[dict[str, Any]] = []
    for item in anchors:
        if not isinstance(item, Mapping):
            continue
        clean = {
            "kind": CODE_STATE_ANCHOR_KIND,
            "anchor_id": _safe_text(item.get("anchor_id"), 120),
            "decision_event_id": _safe_text(item.get("decision_event_id"), 120),
            "repo_commit": _safe_text(item.get("repo_commit") or item.get("commit_sha"), 80),
            "commit_sha": _safe_text(item.get("commit_sha") or item.get("repo_commit"), 80),
            "branch_or_head_ref": _safe_text(item.get("branch_or_head_ref"), 140),
            "branch_ref_hash": _safe_text(item.get("branch_ref_hash"), 80)
            or (_public_hash(item.get("branch_or_head_ref")) if item.get("branch_or_head_ref") else ""),
            "pr_ref": _safe_text(item.get("pr_ref"), 80),
            "issue_ref": _safe_text(item.get("issue_ref"), 80),
            "repo_state_fingerprint": _safe_text(item.get("repo_state_fingerprint"), 120),
            "dirty_workspace_fingerprint": _safe_text(item.get("dirty_workspace_fingerprint"), 120),
            "file_diff_scope": _safe_file_scope(item.get("file_diff_scope")),
            "test_or_check_refs": _safe_check_refs(item.get("test_or_check_refs") or []),
            "source_boundary": "code_state_coordinate_not_user_intent",
            "privacy_boundary": {
                "raw_diffs_serialized": False,
                "raw_test_logs_serialized": False,
                "local_paths_serialized": False,
                "secrets_serialized": False,
            },
        }
        clean = {key: value for key, value in clean.items() if _has_public_value(value)}
        if clean.get("file_diff_scope") or clean.get("repo_commit") or clean.get("pr_ref"):
            compact.append(clean)
        if len(compact) >= limit:
            break
    return compact


def _current_file_fingerprints(current_code_state: Mapping[str, Any]) -> Mapping[str, str]:
    raw = current_code_state.get("file_fingerprints") or current_code_state.get("current_file_fingerprints") or {}
    return raw if isinstance(raw, Mapping) else {}


def _normalize_fingerprint(value: Any) -> str:
    text = str(value or "").strip().casefold()
    if text and not text.startswith("sha256:"):
        return f"sha256:{text}"
    return text


def assess_code_state_currentness(
    anchors: Any,
    *,
    current_code_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    compact = compact_code_state_anchors(anchors)
    if not compact:
        return {
            "status": "no_anchors",
            "requires_refresh": False,
            "signals": [],
            "anchor_count": 0,
            "policy": {
                "anchors_are_coordinates_not_truth": True,
                "missing_anchors_fail_open": True,
            },
        }
    if not current_code_state:
        return {
            "status": "anchors_present_unchecked",
            "requires_refresh": False,
            "signals": [],
            "anchor_count": len(compact),
            "policy": {
                "anchors_are_coordinates_not_truth": True,
                "missing_current_state_fails_open": True,
            },
        }
    current_commit = str(
        current_code_state.get("repo_commit") or current_code_state.get("commit_sha") or ""
    ).strip()
    raw_pr_refs = current_code_state.get("pr_refs")
    current_pr_refs = (
        {str(item).strip() for item in raw_pr_refs if str(item).strip()}
        if isinstance(raw_pr_refs, Sequence) and not isinstance(raw_pr_refs, (str, bytes))
        else set()
    )
    current_dirty = str(current_code_state.get("dirty_workspace_fingerprint") or "").strip()
    fingerprints = _current_file_fingerprints(current_code_state)
    signals: list[str] = []
    checked_files = 0
    for anchor in compact:
        expected_commit = str(anchor.get("repo_commit") or anchor.get("commit_sha") or "").strip()
        if expected_commit and current_commit and expected_commit != current_commit:
            signals.append("commit_mismatch")
        expected_pr = str(anchor.get("pr_ref") or "").strip()
        if expected_pr and "pr_refs" in current_code_state and expected_pr not in current_pr_refs:
            signals.append("pr_missing")
        expected_dirty = str(anchor.get("dirty_workspace_fingerprint") or "").strip()
        if expected_dirty and current_dirty and expected_dirty != current_dirty:
            signals.append("dirty_state_changed")
        for file_row in anchor.get("file_diff_scope") or []:
            if not isinstance(file_row, Mapping):
                continue
            path = str(file_row.get("path") or "")
            expected = _normalize_fingerprint(
                file_row.get("new_file_fingerprint") or file_row.get("file_fingerprint")
            )
            actual = _normalize_fingerprint(fingerprints.get(path))
            if expected and actual:
                checked_files += 1
                if expected != actual:
                    signals.append("file_hash_mismatch")
    unique_signals = unique_preserve(signals, limit=8)
    return {
        "status": "refresh_required" if unique_signals else "current_or_unverified",
        "requires_refresh": bool(unique_signals),
        "signals": unique_signals,
        "anchor_count": len(compact),
        "checked_file_count": checked_files,
        "current_state_boundary": "current_checkout_signal_not_user_intent",
        "policy": {
            "anchors_are_coordinates_not_truth": True,
            "mismatch_degrades_to_refresh_sources": True,
        },
    }


__all__ = [
    "CODE_STATE_ANCHOR_KIND",
    "SCHEMA_VERSION",
    "assess_code_state_currentness",
    "build_checkout_code_state_anchor",
    "compact_code_state_anchors",
]
