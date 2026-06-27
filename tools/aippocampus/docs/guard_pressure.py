"""Guard-budget pressure helpers for architecture debt reporting."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

LOW_MARGIN_OWNER_ISSUES = {
    "skills/aippocampus/scripts/aippocampus_runtime/learning_loop/core.py": "#2631",
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_projection.py": "#2679",
    "skills/aippocampus/scripts/aippocampus_runtime/ops/telepathy_handoff_store.py": "#2678",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_continuity_cli.py": "#2676",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/associative_path_fallback.py": "#2678",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_recall_decision.py": "#2631",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_foreground_budget.py": "#2794",
    "skills/aippocampus/scripts/aippocampus_runtime/source/registry_search_pipeline.py": "#2635",
    "skills/aippocampus/scripts/aippocampus_runtime/subconscious/candidate_router.py": "#2678",
    "skills/aippocampus/scripts/aippocampus_runtime/subconscious/jobs.py": "#2631",
    "skills/aippocampus/scripts/aippocampus_runtime/update/plugin_installer.py": "#2197",
    "skills/aippocampus/scripts/aippocampus_runtime/dream/input_pack.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/install_action_hint.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/continuity_domains.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/coding/episode_arc_private_adjudication.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/contracts.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/sync/object_storage/cli.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/ops/provider_doctor.py": "#2548",
    "tests/aippocampus/test_warm_ambient_recall.py": "#2548",
    "tools/aippocampus/docs/debt_report.py": "#2678",
    "tools/aippocampus/recall_integration_readiness.py": "#2611",
    "tools/aippocampus/test_plan.py": "#2687",
    "tools/aippocampus/test_tier_manifest.py": "#2691",
}


def low_margin_owner_issue(rel_path: str) -> str:
    return LOW_MARGIN_OWNER_ISSUES.get(rel_path, "")


def pressure_row(
    row: Mapping[str, object],
    *,
    split_boundaries: Mapping[str, str],
    layer_for_path: Callable[[str], str],
) -> dict[str, object]:
    rel_path = str(row["path"])
    owner_issue = low_margin_owner_issue(rel_path)
    return {
        "path": rel_path,
        "layer": layer_for_path(rel_path),
        "current_count": int(row["current_count"]),
        "guard_budget": int(row["guard_budget"]),
        "margin": int(row["margin"]),
        "owner_issue": owner_issue,
        "tracked_owner_issue": bool(owner_issue),
        "next_split_boundary": split_boundaries.get(
            rel_path,
            "Open or assign a focused split owner before growing this file.",
        ),
        "recommendation": "split_trim_or_assign_owner_before_growing_low_margin_guard",
    }


def changed_surface_guard_pressure(
    changed_files: list[str] | None = None,
    *,
    rows: list[dict[str, object]] | None = None,
    repo_root: Path,
    budget_entries: Mapping[str, int],
    script_line_count: Callable[[Path], int],
    split_boundaries: Mapping[str, str],
    layer_for_path: Callable[[str], str],
    margin_limit: int,
) -> list[dict[str, object]]:
    """Return low-headroom budget rows touched by this PR surface.

    This is intentionally a changed-surface gate, not just a closeout report:
    agents tend to discover line-budget pressure after the implementation is
    already shaped. Touching a still-pressured owner without an issue/action
    pointer should become acceptance-bearing before broad tests run.
    """

    normalized = sorted({path.replace("\\", "/") for path in changed_files or [] if path})
    if not normalized:
        return []
    if rows is None:
        candidate_rows: list[dict[str, object]] = []
        for rel_path in normalized:
            budget = budget_entries.get(rel_path)
            path = repo_root / rel_path
            if budget is None or not rel_path.endswith(".py") or not path.is_file():
                continue
            current = script_line_count(path)
            candidate_rows.append(
                {
                    "path": rel_path,
                    "guard_budget": int(budget),
                    "current_count": current,
                    "over_budget": current > int(budget),
                    "margin": int(budget) - current,
                }
            )
    else:
        candidate_rows = list(rows)
    pressure_by_path = {
        str(row["path"]): pressure_row(
            row,
            split_boundaries=split_boundaries,
            layer_for_path=layer_for_path,
        )
        for row in candidate_rows
        if int(row["margin"]) <= margin_limit
    }
    return [
        dict(pressure_by_path[path])
        for path in normalized
        if path in pressure_by_path
    ]


__all__ = [
    "LOW_MARGIN_OWNER_ISSUES",
    "changed_surface_guard_pressure",
    "low_margin_owner_issue",
    "pressure_row",
]
