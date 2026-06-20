#!/usr/bin/env python3
"""Emit the current architecture debt inventory from markdown budgets."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE_DEBT_REGISTER = (
    REPO_ROOT / "docs" / "architecture" / "architecture-debt-register.md"
)
ARCHITECTURE_DEBT_SNAPSHOT = (
    REPO_ROOT
    / "docs"
    / "evidence"
    / "reports"
    / "architecture-debt-snapshot-2026-06-04.md"
)
BUDGET_ROW = re.compile(
    r"^\|\s*`(?P<path>[^`]+\.py)`\s*"
    r"\|\s*(?P<first>\d+)\s*\|(?:\s*(?P<second>\d+)\s*\|)?",
    re.MULTILINE,
)


def script_line_count(path: Path) -> int:
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        count += 1
    return count


def inventory_sources() -> list[Path]:
    return [ARCHITECTURE_DEBT_REGISTER, ARCHITECTURE_DEBT_SNAPSHOT]


def budget_entries() -> dict[str, int]:
    entries: dict[str, int] = {}
    for source in inventory_sources():
        text = source.read_text(encoding="utf-8")
        for match in BUDGET_ROW.finditer(text):
            entries[match.group("path")] = int(match.group("second") or match.group("first"))
    return dict(sorted(entries.items()))


def registered_current_counts() -> dict[str, int]:
    """Return human-written current counts from the action register only.

    Budgets are contractual. The current-count column is just a convenience
    for readers, so this report warns on drift instead of letting stale copied
    numbers become another source of truth.
    """

    counts: dict[str, int] = {}
    text = ARCHITECTURE_DEBT_REGISTER.read_text(encoding="utf-8")
    for match in BUDGET_ROW.finditer(text):
        if match.group("second"):
            counts[match.group("path")] = int(match.group("first"))
    return counts


def split_boundary_entries() -> dict[str, str]:
    boundaries: dict[str, str] = {}
    for source in inventory_sources():
        text = source.read_text(encoding="utf-8")
        for line in text.splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 5 or not cells[0].startswith("`") or not cells[0].endswith("`"):
                continue
            path = cells[0].strip("`")
            if path.endswith(".py"):
                boundaries.setdefault(path, cells[4])
    return boundaries


def layer_for_path(rel_path: str) -> str:
    if rel_path.startswith("skills/aippocampus/scripts/"):
        return "runtime"
    if rel_path.startswith("tests/"):
        return "tests"
    if rel_path.startswith("benchmarks/"):
        return "benchmarks"
    if rel_path.startswith("docs/"):
        return "docs"
    if rel_path.startswith("tools/"):
        return "tools"
    return "other"


def build_system_weight(
    rows: list[dict[str, object]],
    *,
    split_boundaries: dict[str, str],
) -> dict[str, object]:
    layers: dict[str, dict[str, object]] = {
        name: {
            "tracked_file_count": 0,
            "tracked_lines": 0,
            "guard_budget_total": 0,
            "over_budget_count": 0,
            "near_budget_count": 0,
        }
        for name in ("runtime", "tests", "benchmarks", "docs", "tools")
    }
    archive_or_split_targets: list[dict[str, object]] = []
    near_zero_runtime_split_queue: list[dict[str, object]] = []
    for row in rows:
        rel_path = str(row["path"])
        layer = layer_for_path(rel_path)
        if layer not in layers:
            continue
        current = int(row["current_count"])
        budget = int(row["guard_budget"])
        margin = int(row["margin"])
        bucket = layers[layer]
        bucket["tracked_file_count"] = int(bucket["tracked_file_count"]) + 1
        bucket["tracked_lines"] = int(bucket["tracked_lines"]) + current
        bucket["guard_budget_total"] = int(bucket["guard_budget_total"]) + budget
        if bool(row["over_budget"]):
            bucket["over_budget_count"] = int(bucket["over_budget_count"]) + 1
        if layer == "runtime" and margin <= 2:
            near_zero_runtime_split_queue.append(
                {
                    "path": rel_path,
                    "current_count": current,
                    "guard_budget": budget,
                    "margin": margin,
                    "status": (
                        "over_budget"
                        if margin < 0
                        else "exact_zero_guard"
                        if margin == 0
                        else "near_zero_margin"
                    ),
                    "next_split_boundary": split_boundaries.get(
                        rel_path,
                        "Add a focused split boundary to architecture-debt-register.md before growing this owner.",
                    ),
                }
            )
        if margin <= max(25, int(budget * 0.08)):
            bucket["near_budget_count"] = int(bucket["near_budget_count"]) + 1
            archive_or_split_targets.append(
                {
                    "path": rel_path,
                    "layer": layer,
                    "current_count": current,
                    "guard_budget": budget,
                    "margin": margin,
                    "recommendation": "split_owner_or_archive_stale_supporting_material",
                }
            )
    total_lines = sum(int(layer["tracked_lines"]) for layer in layers.values())
    archive_or_split_targets.sort(key=lambda item: (int(item["margin"]), str(item["path"])))
    near_zero_runtime_split_queue.sort(key=lambda item: (int(item["margin"]), str(item["path"])))
    exact_zero_runtime_count = sum(
        1
        for row in near_zero_runtime_split_queue
        if int(row["margin"]) == 0
    )
    near_zero_runtime_count = sum(
        1
        for row in near_zero_runtime_split_queue
        if 0 < int(row["margin"]) <= 2
    )
    over_budget_runtime_count = sum(
        1
        for row in near_zero_runtime_split_queue
        if int(row["margin"]) < 0
    )
    return {
        "schema_version": "aippocampus-system-weight-v1",
        "total_tracked_lines": total_lines,
        "layers": layers,
        "fresh_agent_load": {
            "tracked_file_count": sum(int(layer["tracked_file_count"]) for layer in layers.values()),
            "tracked_lines": total_lines,
            "interpretation": "tracked large-file surface only; not whole repository LOC",
        },
        "product_proof_audit_research_split": {
            "runtime": "product_runtime",
            "tests": "proof_regression",
            "benchmarks": "proof_benchmark",
            "docs": "architecture_or_research_context",
            "tools": "operator_audit_or_maintenance",
        },
        "archive_or_split_targets": archive_or_split_targets[:20],
        "guard_headroom_summary": {
            "runtime_exact_zero_count": exact_zero_runtime_count,
            "runtime_near_zero_count": near_zero_runtime_count,
            "runtime_over_budget_count": over_budget_runtime_count,
            "runtime_split_queue_count": len(near_zero_runtime_split_queue),
        },
        "near_zero_runtime_split_queue": near_zero_runtime_split_queue,
    }


def count_drift_entries(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    current_by_path = {str(row["path"]): int(row["current_count"]) for row in rows}
    drifts: list[dict[str, object]] = []
    for rel_path, registered_count in registered_current_counts().items():
        current_count = current_by_path.get(rel_path)
        if current_count is None or current_count == registered_count:
            continue
        drifts.append(
            {
                "path": rel_path,
                "registered_current_count": registered_count,
                "current_count": current_count,
                "drift": current_count - registered_count,
            }
        )
    return sorted(drifts, key=lambda row: (str(row["path"])))


def report_warnings(
    *,
    headroom_summary: dict[str, object],
    count_drifts: list[dict[str, object]],
) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []
    exact_zero = int(headroom_summary.get("runtime_exact_zero_count") or 0)
    near_zero = int(headroom_summary.get("runtime_near_zero_count") or 0)
    if exact_zero:
        warnings.append(
            {
                "code": "runtime_exact_zero_headroom",
                "message": (
                    f"{exact_zero} runtime guard(s) have exact-zero headroom; split an owner before growing them."
                ),
                "count": exact_zero,
            }
        )
    if near_zero:
        warnings.append(
            {
                "code": "runtime_near_zero_headroom",
                "message": (
                    f"{near_zero} runtime guard(s) have only 1-2 lines of headroom; treat them as split-first."
                ),
                "count": near_zero,
            }
        )
    if count_drifts:
        warnings.append(
            {
                "code": "architecture_debt_register_count_drift",
                "message": (
                    f"{len(count_drifts)} architecture debt register current-count row(s) drift from script_line_count()."
                ),
                "count": len(count_drifts),
            }
        )
    return warnings


def build_report() -> dict[str, object]:
    entries = budget_entries()
    split_boundaries = split_boundary_entries()
    rows: list[dict[str, object]] = []
    missing_files: list[str] = []
    for rel_path, budget in entries.items():
        path = REPO_ROOT / rel_path
        if not path.exists():
            missing_files.append(rel_path)
            continue
        loc = script_line_count(path)
        rows.append(
            {
                "path": rel_path,
                "guard_budget": budget,
                "current_count": loc,
                "over_budget": loc > budget,
                "margin": budget - loc,
            }
        )
    over_budget = [row for row in rows if row["over_budget"]]
    system_weight = build_system_weight(rows, split_boundaries=split_boundaries)
    headroom_summary = dict(system_weight["guard_headroom_summary"])
    count_drifts = count_drift_entries(rows)
    return {
        "ok": not missing_files and not over_budget,
        "sources": [source.relative_to(REPO_ROOT).as_posix() for source in inventory_sources()],
        "entry_count": len(entries),
        "missing_files": missing_files,
        "over_budget": over_budget,
        "headroom_summary": headroom_summary,
        "count_drift": count_drifts,
        "warnings": report_warnings(
            headroom_summary=headroom_summary,
            count_drifts=count_drifts,
        ),
        "system_weight": system_weight,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    report = build_report()
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for row in report["rows"]:
            print(
                f"{row['path']}: {row['current_count']}/{row['guard_budget']} "
                f"(margin {row['margin']})"
            )
        summary = report["headroom_summary"]
        print(
            "runtime guard headroom: "
            f"exact_zero={summary['runtime_exact_zero_count']} "
            f"near_zero={summary['runtime_near_zero_count']} "
            f"over_budget={summary['runtime_over_budget_count']}"
        )
        for warning in report["warnings"]:
            print(f"! {warning['code']}: {warning['message']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
