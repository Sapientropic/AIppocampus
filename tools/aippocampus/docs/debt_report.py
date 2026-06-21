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
REGISTER_COUNT_ROW = re.compile(
    r"^(?P<prefix>\|\s*`(?P<path>[^`]+\.py)`\s*\|\s*)"
    r"(?P<count>\d+)"
    r"(?P<suffix>\s*\|\s*\d+\s*\|.*)$"
)
REFRESH_REGISTER_COUNTS_COMMAND = (
    "python tools\\aippocampus\\docs\\debt_report.py --refresh-register-counts --write"
)
SMALL_DRIFT_LIMIT = 5
STALE_ALLOWANCE_MIN_BUDGET = 1000
STALE_ALLOWANCE_MAX_CURRENT = 300
STALE_ALLOWANCE_MAX_RATIO = 0.25
SINGLE_DIGIT_GUARD_MARGIN_LIMIT = 9
LOW_MARGIN_OWNER_ISSUES = {
    "skills/aippocampus/scripts/aippocampus_runtime/dream/input_pack.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/install_action_hint.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/continuity_domains.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/coding/episode_arc_private_adjudication.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/contracts.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/sync/object_storage/cli.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/ops/provider_doctor.py": "#2548",
    "tests/aippocampus/test_warm_ambient_recall.py": "#2548",
}


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
    single_digit_guard_pressure: list[dict[str, object]] = []
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
        low_margin_owner = LOW_MARGIN_OWNER_ISSUES.get(rel_path, "")
        if margin <= SINGLE_DIGIT_GUARD_MARGIN_LIMIT:
            single_digit_guard_pressure.append(
                {
                    "path": rel_path,
                    "layer": layer,
                    "current_count": current,
                    "guard_budget": budget,
                    "margin": margin,
                    "owner_issue": low_margin_owner,
                    "tracked_owner_issue": bool(low_margin_owner),
                    "next_split_boundary": split_boundaries.get(
                        rel_path,
                        "Open or assign a focused split owner before growing this file.",
                    ),
                    "recommendation": (
                        "split_trim_or_assign_owner_before_growing_low_margin_guard"
                    ),
                }
            )
        if margin <= max(25, int(budget * 0.08)):
            bucket["near_budget_count"] = int(bucket["near_budget_count"]) + 1
            target = {
                "path": rel_path,
                "layer": layer,
                "current_count": current,
                "guard_budget": budget,
                "margin": margin,
                "recommendation": "split_owner_or_archive_stale_supporting_material",
            }
            if margin <= SINGLE_DIGIT_GUARD_MARGIN_LIMIT:
                target["owner_issue"] = low_margin_owner
                target["tracked_owner_issue"] = bool(low_margin_owner)
            archive_or_split_targets.append(target)
    total_lines = sum(int(layer["tracked_lines"]) for layer in layers.values())
    archive_or_split_targets.sort(key=lambda item: (int(item["margin"]), str(item["path"])))
    near_zero_runtime_split_queue.sort(key=lambda item: (int(item["margin"]), str(item["path"])))
    single_digit_guard_pressure.sort(key=lambda item: (int(item["margin"]), str(item["path"])))
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
            "single_digit_guard_pressure_count": len(single_digit_guard_pressure),
            "unowned_single_digit_guard_pressure_count": sum(
                1
                for row in single_digit_guard_pressure
                if not row.get("tracked_owner_issue")
            ),
        },
        "near_zero_runtime_split_queue": near_zero_runtime_split_queue,
        "single_digit_guard_pressure": single_digit_guard_pressure,
    }


def count_drift_entries(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    current_by_path = {str(row["path"]): int(row["current_count"]) for row in rows}
    budget_by_path = {str(row["path"]): int(row["guard_budget"]) for row in rows}
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
                "drift_class": drift_class(
                    registered_count=registered_count,
                    current_count=current_count,
                    guard_budget=budget_by_path[rel_path],
                ),
                "recommended_action": drift_recommended_action(
                    registered_count=registered_count,
                    current_count=current_count,
                ),
            }
        )
    return sorted(drifts, key=lambda row: (str(row["path"])))


def refresh_register_count_rows(
    text: str,
    current_counts: dict[str, int],
) -> tuple[str, list[dict[str, object]]]:
    """Refresh only the human-written current-count column in the action register.

    Guard budgets and owner-boundary prose are still human decisions. This helper
    deliberately touches only the first numeric count in register table rows so
    agents do not hand-edit stale counts or accidentally rewrite budgets while
    trying to clear a drift warning.
    """

    changes: list[dict[str, object]] = []
    lines: list[str] = []
    for line in text.splitlines(keepends=True):
        newline = ""
        body = line
        if line.endswith("\r\n"):
            body = line[:-2]
            newline = "\r\n"
        elif line.endswith("\n"):
            body = line[:-1]
            newline = "\n"
        match = REGISTER_COUNT_ROW.match(body)
        if not match:
            lines.append(line)
            continue
        rel_path = match.group("path")
        current_count = current_counts.get(rel_path)
        if current_count is None:
            lines.append(line)
            continue
        old_count = int(match.group("count"))
        if old_count == current_count:
            lines.append(line)
            continue
        changes.append(
            {
                "path": rel_path,
                "old_current_count": old_count,
                "current_count": current_count,
                "drift": current_count - old_count,
            }
        )
        lines.append(f"{match.group('prefix')}{current_count}{match.group('suffix')}{newline}")
    return "".join(lines), changes


def refresh_register_counts(*, write: bool = False) -> dict[str, object]:
    report = build_report()
    current_counts = {
        str(row["path"]): int(row["current_count"])
        for row in report["rows"]
        if isinstance(row, dict)
    }
    original = ARCHITECTURE_DEBT_REGISTER.read_text(encoding="utf-8")
    refreshed, changes = refresh_register_count_rows(original, current_counts)
    if write and refreshed != original:
        ARCHITECTURE_DEBT_REGISTER.write_text(refreshed, encoding="utf-8")
    return {
        "ok": True,
        "write": write,
        "changed": bool(changes),
        "changed_count": len(changes),
        "changes": changes,
        "target": ARCHITECTURE_DEBT_REGISTER.relative_to(REPO_ROOT).as_posix(),
        "refresh_command": REFRESH_REGISTER_COUNTS_COMMAND,
    }


def drift_class(
    *,
    registered_count: int,
    current_count: int,
    guard_budget: int,
) -> str:
    drift = current_count - registered_count
    if abs(drift) <= SMALL_DRIFT_LIMIT:
        return "harmless_small_drift"
    if drift > 0:
        return "positive_drift"
    if is_stale_allowance(current_count=current_count, guard_budget=guard_budget):
        return "large_stale_allowance_after_shrink"
    return "negative_drift"


def drift_recommended_action(*, registered_count: int, current_count: int) -> str:
    drift = current_count - registered_count
    if abs(drift) <= SMALL_DRIFT_LIMIT:
        return "refresh_registered_count_when_touching_row"
    if drift > 0:
        return "refresh_current_count_or_split_before_raising_budget"
    return "refresh_current_count_and_check_for_stale_guard_allowance"


def is_stale_allowance(*, current_count: int, guard_budget: int) -> bool:
    if guard_budget < STALE_ALLOWANCE_MIN_BUDGET:
        return False
    return (
        current_count <= STALE_ALLOWANCE_MAX_CURRENT
        and current_count <= int(guard_budget * STALE_ALLOWANCE_MAX_RATIO)
    )


def stale_allowance_entries(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    stale_rows: list[dict[str, object]] = []
    for row in rows:
        current = int(row["current_count"])
        budget = int(row["guard_budget"])
        if not is_stale_allowance(current_count=current, guard_budget=budget):
            continue
        stale_rows.append(
            {
                "path": str(row["path"]),
                "current_count": current,
                "guard_budget": budget,
                "margin": int(row["margin"]),
                "budget_to_current_ratio": round(budget / max(current, 1), 2),
                "drift_class": "large_stale_allowance_after_shrink",
                "recommended_action": (
                    "lower_guard_budget_or_archive_row_with_dated_owner_rationale"
                ),
            }
        )
    return sorted(stale_rows, key=lambda row: (str(row["path"])))


def count_drift_summary(count_drifts: list[dict[str, object]]) -> dict[str, int]:
    summary = {
        "harmless_small_drift": 0,
        "positive_drift": 0,
        "negative_drift": 0,
        "large_stale_allowance_after_shrink": 0,
    }
    for row in count_drifts:
        drift_type = str(row.get("drift_class") or "")
        if drift_type in summary:
            summary[drift_type] += 1
    return summary


def report_warnings(
    *,
    headroom_summary: dict[str, object],
    count_drifts: list[dict[str, object]],
    stale_allowances: list[dict[str, object]],
    single_digit_guard_pressure: list[dict[str, object]] | None = None,
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
        drift_summary = count_drift_summary(count_drifts)
        warnings.append(
            {
                "code": "architecture_debt_register_count_drift",
                "message": (
                    f"{len(count_drifts)} architecture debt register current-count row(s) drift from script_line_count()."
                ),
                "count": len(count_drifts),
                "drift_summary": drift_summary,
                "refresh_command": REFRESH_REGISTER_COUNTS_COMMAND,
            }
        )
    if stale_allowances:
        warnings.append(
            {
                "code": "architecture_debt_stale_allowance",
                "message": (
                    f"{len(stale_allowances)} guard budget row(s) look stale after a split; "
                    "lower the budget or archive the row with a dated owner rationale."
                ),
                "count": len(stale_allowances),
            }
        )
    guard_pressure = list(single_digit_guard_pressure or [])
    if guard_pressure:
        unowned = [row for row in guard_pressure if not row.get("tracked_owner_issue")]
        warnings.append(
            {
                "code": "architecture_debt_single_digit_guard_pressure",
                "message": (
                    f"{len(guard_pressure)} guard budget row(s) have single-digit headroom. "
                    "Touching them should start with a split/trim plan, not late closeout cleanup."
                ),
                "count": len(guard_pressure),
                "unowned_count": len(unowned),
                "owned_count": len(guard_pressure) - len(unowned),
                "sample_paths": [str(row.get("path")) for row in guard_pressure[:5]],
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
    stale_allowances = stale_allowance_entries(rows)
    return {
        "ok": not missing_files and not over_budget and not stale_allowances,
        "sources": [source.relative_to(REPO_ROOT).as_posix() for source in inventory_sources()],
        "entry_count": len(entries),
        "missing_files": missing_files,
        "over_budget": over_budget,
        "headroom_summary": headroom_summary,
        "count_drift": count_drifts,
        "count_drift_summary": count_drift_summary(count_drifts),
        "stale_allowances": stale_allowances,
        "warnings": report_warnings(
            headroom_summary=headroom_summary,
            count_drifts=count_drifts,
            stale_allowances=stale_allowances,
            single_digit_guard_pressure=list(
                system_weight["single_digit_guard_pressure"]
            ),
        ),
        "system_weight": system_weight,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--refresh-register-counts",
        action="store_true",
        help=(
            "Refresh only the current script_line_count() column in "
            "docs/architecture/architecture-debt-register.md."
        ),
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="With --refresh-register-counts, write the refreshed counts to disk.",
    )
    args = parser.parse_args()

    if args.refresh_register_counts:
        result = refresh_register_counts(write=bool(args.write))
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            mode = "updated" if args.write else "would update"
            print(f"{mode}: {result['changed_count']} architecture debt register count row(s)")
            if result["changed_count"] and not args.write:
                print(f"write with: {REFRESH_REGISTER_COUNTS_COMMAND}")
        return 0

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
