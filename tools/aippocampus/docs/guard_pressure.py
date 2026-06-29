"""Guard-budget pressure helpers for architecture debt reporting."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

LOW_MARGIN_OWNER_ISSUES = {
    "skills/aippocampus/scripts/aippocampus_runtime/learning_loop/core.py": "#2631",
    "skills/aippocampus/scripts/aippocampus_runtime/mcp/agent_recall_projection.py": "#2679",
    "skills/aippocampus/scripts/aippocampus_runtime/ops/telepathy_handoff_store.py": "#2678",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_continuity_cli.py": "#2676",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_recall_pipeline.py": "#2631",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/associative_path_fallback.py": "#2678",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_recall_decision.py": "#2631",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_foreground_budget.py": "#2794",
    "skills/aippocampus/scripts/aippocampus_runtime/source/registry_search_pipeline.py": "#2635",
    "skills/aippocampus/scripts/aippocampus_runtime/subconscious/candidate_router.py": "#2678",
    "skills/aippocampus/scripts/aippocampus_runtime/subconscious/jobs.py": "#2631",
    "skills/aippocampus/scripts/aippocampus_runtime/update/plugin_installer.py": "#2197",
    "skills/aippocampus/scripts/aippocampus_runtime/dream/input_pack.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/install_action_hint.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/hooks/foreground_status.py": "#2611",
    "skills/aippocampus/scripts/aippocampus_runtime/recall/continuity_domains.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/coding/episode_arc_private_adjudication.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/contracts.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/sync/object_storage/cli.py": "#2548",
    "skills/aippocampus/scripts/aippocampus_runtime/ops/doctors/provider_doctor.py": "#2548",
    "tests/aippocampus/test_warm_ambient_recall.py": "#2548",
    "tools/aippocampus/docs/debt_report.py": "#2678",
    "tools/aippocampus/recall_integration_readiness.py": "#2611",
    "tools/aippocampus/test_plan.py": "#2687",
    "tools/aippocampus/test_tier_manifest.py": "#2691",
}

PARKED_LOW_MARGIN_PRESSURE = {
    "skills/aippocampus/scripts/aippocampus_runtime/learning_loop/core.py": {
        "park_owner_issue": "#2951",
        "parked_reason": "Parked as freeze-except-delete/split; split a named learning-loop boundary before growth.",
    },
    "skills/aippocampus/scripts/aippocampus_runtime/ops/telepathy_handoff_store.py": {
        "park_owner_issue": "#2951",
        "parked_reason": "Parked as freeze-except-delete/split; split a handoff projection or validation boundary before growth.",
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/agent_recall_pipeline.py": {
        "park_owner_issue": "#2951",
        "parked_reason": "Parked as freeze-except-delete/split; split a recall pipeline stage before growth.",
    },
    "skills/aippocampus/scripts/aippocampus_runtime/recall/prompt_foreground_budget.py": {
        "park_owner_issue": "#2951",
        "parked_reason": "Parked as freeze-except-delete/split; split result-tier or card rendering before growth.",
    },
    "skills/aippocampus/scripts/aippocampus_runtime/subconscious/jobs.py": {
        "park_owner_issue": "#2951",
        "parked_reason": "Parked as freeze-except-delete/split; split runner orchestration before growth.",
    },
    "skills/aippocampus/scripts/aippocampus_runtime/update/plugin_installer.py": {
        "park_owner_issue": "#2951",
        "parked_reason": "Parked as freeze-except-delete/split; split host/probe or replacement helpers before growth.",
    },
    "tools/aippocampus/recall_integration_readiness.py": {
        "park_owner_issue": "#2951",
        "parked_reason": "Parked as freeze-except-delete/split; split cue catalog or result projection before growth.",
    },
}


def low_margin_owner_issue(rel_path: str) -> str:
    return LOW_MARGIN_OWNER_ISSUES.get(rel_path, "")


def _owner_state_value(
    owner_issue: str,
    owner_issue_states: Mapping[str, object] | None,
) -> tuple[str, str]:
    if not owner_issue:
        return "", ""
    states = owner_issue_states or {}
    raw = states.get(owner_issue) or states.get(owner_issue.lstrip("#"))
    if isinstance(raw, Mapping):
        state = str(raw.get("state") or raw.get("owner_issue_state") or "unknown").casefold()
        kind = str(raw.get("kind") or raw.get("owner_issue_kind") or "issue").casefold()
        return state, kind
    if raw is None:
        return "unknown", "issue"
    return str(raw).casefold(), "issue"


def owner_issue_metadata(
    owner_issue: str,
    *,
    owner_issue_states: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Classify owner issue coverage without treating history as active work.

    Guard-pressure rows use owner issues as provenance, but only a confirmed
    open issue is active coverage. Closed, merged, and unknown states are kept
    visible so future agents can follow the history, while the acceptance gate
    still asks for a fresh split/trim owner before growing the pressured file.
    """

    state, kind = _owner_state_value(owner_issue, owner_issue_states)
    active = bool(owner_issue) and state == "open"
    historical = state in {"closed", "merged"}
    return {
        "owner_issue": owner_issue,
        "owner_issue_state": state,
        "owner_issue_kind": kind,
        "owner_issue_active": active,
        "owner_issue_history_only": bool(owner_issue) and (historical or not active),
        "tracked_owner_issue": active,
    }


def pressure_owner_metadata(
    rel_path: str,
    *,
    owner_issue_states: Mapping[str, object] | None = None,
) -> dict[str, object]:
    metadata = owner_issue_metadata(
        low_margin_owner_issue(rel_path),
        owner_issue_states=owner_issue_states,
    )
    if metadata.get("tracked_owner_issue"):
        owner_state = "active_owner"
    elif metadata.get("owner_issue_history_only"):
        owner_state = "history_only_owner"
    else:
        owner_state = "unowned"
    metadata.update(
        {
            "pressure_owner_state": owner_state,
            "parked_by_policy": False,
        }
    )
    parked = PARKED_LOW_MARGIN_PRESSURE.get(rel_path)
    if parked:
        metadata.update(
            {
                "pressure_owner_state": "parked_touch_time_split",
                "parked_by_policy": True,
                "park_owner_issue": parked["park_owner_issue"],
                "parked_reason": parked["parked_reason"],
                "touch_time_guard": (
                    "changed_surface_guard_pressure_blocks_until_split_trim_or_active_owner"
                ),
            }
        )
    return metadata


def pressure_row_is_unowned(row: Mapping[str, object]) -> bool:
    return not row.get("tracked_owner_issue") and not row.get("parked_by_policy")


def pressure_summary(rows: list[dict[str, object]]) -> dict[str, int]:
    return {
        "single_digit_guard_pressure_count": len(rows),
        "active_single_digit_guard_pressure_count": sum(
            1 for row in rows if row.get("tracked_owner_issue")
        ),
        "parked_single_digit_guard_pressure_count": sum(
            1 for row in rows if row.get("parked_by_policy")
        ),
        "unowned_single_digit_guard_pressure_count": sum(
            1 for row in rows if pressure_row_is_unowned(row)
        ),
    }


def changed_surface_warning(row: Mapping[str, object]) -> dict[str, object] | None:
    if row.get("tracked_owner_issue"):
        return None
    if row.get("parked_by_policy"):
        return {
            "code": "changed_surface_parked_guard_pressure",
            "path": row["path"],
            "layer": row["layer"],
            "current_count": row["current_count"],
            "guard_budget": row["guard_budget"],
            "margin": row["margin"],
            "next_split_boundary": row["next_split_boundary"],
            "park_owner_issue": row.get("park_owner_issue"),
            "parked_reason": row.get("parked_reason"),
            "acceptance_bearing": True,
            "message": (
                "Touched parked single-digit guard owner; split, shrink, "
                "or unpark with an active owner before closeout."
            ),
        }
    return {
        "code": "changed_surface_unowned_guard_pressure",
        "path": row["path"],
        "layer": row["layer"],
        "current_count": row["current_count"],
        "guard_budget": row["guard_budget"],
        "margin": row["margin"],
        "next_split_boundary": row["next_split_boundary"],
        "acceptance_bearing": True,
        "message": (
            "Touched exact-zero or single-digit guard owner without an issue/action "
            "pointer; split, shrink, or assign an owner before closeout."
        ),
    }


def pressure_row(
    row: Mapping[str, object],
    *,
    split_boundaries: Mapping[str, str],
    layer_for_path: Callable[[str], str],
    owner_issue_states: Mapping[str, object] | None = None,
) -> dict[str, object]:
    rel_path = str(row["path"])
    owner_metadata = pressure_owner_metadata(
        rel_path,
        owner_issue_states=owner_issue_states,
    )
    return {
        "path": rel_path,
        "layer": layer_for_path(rel_path),
        "current_count": int(row["current_count"]),
        "guard_budget": int(row["guard_budget"]),
        "margin": int(row["margin"]),
        **owner_metadata,
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
    owner_issue_states: Mapping[str, object] | None = None,
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
            owner_issue_states=owner_issue_states,
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
    "PARKED_LOW_MARGIN_PRESSURE",
    "changed_surface_guard_pressure",
    "low_margin_owner_issue",
    "owner_issue_metadata",
    "pressure_owner_metadata",
    "pressure_row_is_unowned",
    "pressure_summary",
    "changed_surface_warning",
    "pressure_row",
]
