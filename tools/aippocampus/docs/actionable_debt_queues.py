"""Actionable debt queues for the compact architecture debt report."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

DEFAULT_ACCEPTED_MARKER_PREFIX = "aippocampus-debt-ok:"


def accepted_exception_marker_inventory(
    files: Iterable[Path],
    *,
    repo_root: Path,
    marker_prefix: str = DEFAULT_ACCEPTED_MARKER_PREFIX,
    detail: bool = False,
) -> dict[str, Any]:
    markers: list[dict[str, Any]] = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        rel_path = path.relative_to(repo_root).as_posix()
        for line_number, line in enumerate(lines, start=1):
            stripped = line.lstrip()
            if not stripped.startswith("#") or marker_prefix not in stripped:
                continue
            tail = stripped.split(marker_prefix, 1)[1].strip()
            family = tail.split()[0].strip(" .,:;#") if tail else "unknown"
            markers.append(
                {
                    "path": rel_path,
                    "line": line_number,
                    "marker_family": family or "unknown",
                }
            )

    by_file = Counter(str(item["path"]) for item in markers)
    by_family = Counter(str(item["marker_family"]) for item in markers)
    grouped: dict[str, dict[str, Any]] = {}
    family_counts_by_file: dict[str, Counter[str]] = defaultdict(Counter)
    for marker in markers:
        family_counts_by_file[str(marker["path"])][str(marker["marker_family"])] += 1
    for path, family_counts in sorted(family_counts_by_file.items()):
        grouped[path] = {"path": path, "families": dict(sorted(family_counts.items()))}

    return {
        "summary": {
            "marker_total": len(markers),
            "file_count": len(by_file),
            "family_count": len(by_family),
        },
        "top_files": [{"path": path, "count": count} for path, count in by_file.most_common(10)],
        "families": [
            {"marker_family": family, "count": count}
            for family, count in by_family.most_common(20)
        ],
        "markers_by_file": list(grouped.values()),
        **({"markers": markers} if detail else {}),
    }


def _sample_paths(rows: Sequence[Mapping[str, Any]], *, limit: int = 5) -> list[str]:
    return [str(row.get("path")) for row in rows[:limit] if row.get("path")]


def _queue(
    queue_id: str,
    *,
    count: int,
    next_action: str,
    rows: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "queue_id": queue_id,
        "count": count,
        "next_action": next_action,
    }
    sample = _sample_paths(rows)
    if sample:
        payload["sample_paths"] = sample
    return payload


def build_actionable_debt_queues(
    *,
    rows: Sequence[Mapping[str, Any]],
    count_drifts: Sequence[Mapping[str, Any]],
    stale_allowances: Sequence[Mapping[str, Any]],
    single_digit_guard_pressure: Sequence[Mapping[str, Any]],
    accepted_exception_debt: Mapping[str, Any],
) -> dict[str, Any]:
    positive = [row for row in count_drifts if row.get("drift_class") == "positive_drift"]
    negative = [row for row in count_drifts if row.get("drift_class") == "negative_drift"]
    exact_or_near = [
        row
        for row in rows
        if str(row.get("path") or "").startswith("skills/aippocampus/scripts/")
        and int(row.get("margin") or 0) <= 2
    ]
    exception_total = int(
        (accepted_exception_debt.get("summary") or {}).get("marker_total") or 0
    )
    exception_rows = list(accepted_exception_debt.get("top_files") or [])

    queues: list[dict[str, Any]] = []
    if positive:
        queues.append(
            _queue(
                "positive_count_drift",
                count=len(positive),
                rows=positive,
                next_action="split_or_refresh_register_counts_for_files_that_grew",
            )
        )
    if exception_total:
        queues.append(
            _queue(
                "accepted_exception_debt",
                count=exception_total,
                rows=exception_rows,
                next_action="remove_or_narrow_accepted_exception_markers_by_owner_file",
            )
        )
    if exact_or_near:
        queues.append(
            _queue(
                "near_zero_guard_headroom",
                count=len(exact_or_near),
                rows=exact_or_near,
                next_action="split_or_delete_before_adding_behavior_to_near_budget_runtime_files",
            )
        )
    if negative:
        queues.append(
            _queue(
                "negative_count_drift",
                count=len(negative),
                rows=negative,
                next_action="refresh_stale_registered_counts_after_shrink",
            )
        )
    if stale_allowances:
        queues.append(
            _queue(
                "stale_allowance_after_split",
                count=len(stale_allowances),
                rows=stale_allowances,
                next_action="lower_guard_budget_or_archive_stale_budget_rows",
            )
        )
    if single_digit_guard_pressure:
        queues.append(
            _queue(
                "single_digit_guard_pressure",
                count=len(single_digit_guard_pressure),
                rows=single_digit_guard_pressure,
                next_action="open_or_use_owner_split_issue_before_touching_guard_pressure_rows",
            )
        )

    return {
        "queue_count": len(queues),
        "top_queue": queues[0] if queues else None,
        "queues": queues[:8],
        "boundary": "Actionable debt queues come from debt_report inventories, not broad prose grep.",
    }
