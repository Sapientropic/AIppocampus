"""Default navigation sidecar loading for Task Orientation.

Task Orientation should benefit from reviewed/read-model work that already
exists on disk, but it must not become a broad local-history scanner. This
loader reads only small, named sidecars from the current project boundary (and
explicit operator paths) and returns route-shaped inputs for
``understanding_state``. Missing files are diagnostics with next actions, not
hard failures.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.coding import episode_arcs as episode_runtime
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall import background_findings
from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows

KIND = "aippocampus_orientation_sidecar_load"
SCHEMA_VERSION = 1
DEFAULT_SIDECAR_DIR_NAME = ".aippocampus"
DEFAULT_LIMIT = 3

JOURNEY_FILENAMES = ("journeys.jsonl", "journey_tracking.jsonl")
EPISODE_ARC_FILENAMES = ("episode-arcs.jsonl", "episode_arcs.jsonl")
EPISODE_EVENT_FILENAMES = ("episode-events.jsonl", "episode_events.jsonl")
REFLECTION_ADJUSTMENT_FILENAMES = (
    "reflection-adjustments.jsonl",
    "reflection_adjustments.jsonl",
)
LOCAL_WORKING_MEMORY_FILENAMES = ("working_memory.jsonl",)


def _public_payload(payload: Any) -> Any:
    return redact_sensitive_values(redact_private_paths(payload))


def _text(value: Any, limit: int = 180) -> str:
    return core.compact_text(str(value or "").strip(), limit)


def _tokens(text: Any) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"[\w\u4e00-\u9fff]+", str(text or ""))
        if len(token) >= 3
    }


def _task_matches(task: str, row: Mapping[str, Any], fields: Iterable[str]) -> bool:
    task_terms = _tokens(task)
    if not task_terms:
        return False
    material: list[str] = []
    for field in fields:
        value = row.get(field)
        if isinstance(value, Mapping):
            material.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
        elif isinstance(value, (list, tuple)):
            material.extend(str(item) for item in value)
        elif value not in (None, ""):
            material.append(str(value))
    return bool(task_terms & _tokens(" ".join(material)))


def _component(
    component: str,
    *,
    status: str,
    item_count: int = 0,
    next_action: str = "",
    source: str = "default_project_sidecar",
    jsonl_loss: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "component": component,
        "status": status,
        "item_count": item_count,
        "source": source,
        "authority": "navigation_only_not_fact",
    }
    if next_action:
        payload["next_action"] = next_action
    if jsonl_loss and int(jsonl_loss.get("total_loss_count") or 0):
        payload["jsonl_loss_count"] = int(jsonl_loss.get("total_loss_count") or 0)
        payload["jsonl_warning_codes"] = list(jsonl_loss.get("warning_codes") or [])
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return load_jsonl_dict_rows(path).rows


def _read_jsonl_result(path: Path):
    return load_jsonl_dict_rows(path)


def _first_existing(root: Path, filenames: Iterable[str]) -> Path | None:
    for name in filenames:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def _project_sidecar_root(
    *,
    cwd: str | Path | None,
    sidecar_dir: str | Path | None,
) -> Path:
    if sidecar_dir:
        return Path(sidecar_dir).expanduser().resolve()
    root = Path(cwd).expanduser().resolve() if cwd else Path.cwd().resolve()
    return root / DEFAULT_SIDECAR_DIR_NAME


def _has_source_refs(row: Mapping[str, Any]) -> bool:
    refs = row.get("source_refs") or row.get("current_frontier_source_refs")
    return bool(safe_source_refs(refs))


def _journey_rows(
    *,
    task: str,
    root: Path,
    explicit_path: str | Path | None,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = Path(explicit_path).expanduser().resolve() if explicit_path else _first_existing(root, JOURNEY_FILENAMES)
    if path is None:
        return [], _component(
            "journey_sidecar",
            status="missing",
            next_action="materialize source-backed live Journey candidates into .aippocampus/journeys.jsonl when this task depends on a long-running frontier",
        )
    result = _read_jsonl_result(path)
    rows = []
    for row in result.rows:
        status = str(row.get("status") or "").casefold()
        if row.get("kind") != "aippocampus_journey":
            continue
        if status in {"arrived", "abandoned", "resolved", "terminal"}:
            continue
        if not _has_source_refs(row):
            continue
        if not _task_matches(
            task,
            row,
            ("path_label", "core_inquiry", "current_frontier", "active_questions", "journey_id"),
        ):
            continue
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows, _component(
        "journey_sidecar",
        status="projected" if rows else "no_relevant_route",
        item_count=len(rows),
        next_action="" if rows else "continue without Journey hint or tighten the task cue",
        jsonl_loss=result.loss,
    )


def _episode_arc_rows(
    *,
    task: str,
    root: Path,
    explicit_path: str | Path | None,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = Path(explicit_path).expanduser().resolve() if explicit_path else _first_existing(root, EPISODE_ARC_FILENAMES)
    rows = []
    jsonl_loss: dict[str, Any] | None = None
    if path is not None:
        result = _read_jsonl_result(path)
        jsonl_loss = result.loss
        rows = [
            row
            for row in result.rows
            if row.get("kind") == episode_runtime.EPISODE_ARC_KIND
        ]
    else:
        event_path = _first_existing(root, EPISODE_EVENT_FILENAMES)
        if event_path is not None:
            result = _read_jsonl_result(event_path)
            jsonl_loss = result.loss
            rows = episode_runtime.build_episode_arcs(result.rows)
    if not rows:
        return [], _component(
            "episode_arc_sidecar",
            status="missing",
            next_action="write compact Episode/Arc rows when ordered source events should change the next route",
        )
    selected: list[dict[str, Any]] = []
    for row in rows:
        if not _has_source_refs(row):
            continue
        if not _task_matches(
            task,
            row,
            (
                "episode_id",
                "episode_kind",
                "event_order",
                "outcome",
                "current_validity",
                "affected_scope",
            ),
        ):
            continue
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected, _component(
        "episode_arc_sidecar",
        status="projected" if selected else "no_relevant_route",
        item_count=len(selected),
        next_action="" if selected else "reopen normally; no relevant sequence packet matched this task",
        jsonl_loss=jsonl_loss,
    )


def _reflection_adjustments(
    *,
    task: str,
    root: Path,
    explicit_path: str | Path | None,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = (
        Path(explicit_path).expanduser().resolve()
        if explicit_path
        else _first_existing(root, REFLECTION_ADJUSTMENT_FILENAMES)
    )
    if path is None:
        return [], _component(
            "reflection_adjustment_sidecar",
            status="missing",
            next_action="write reviewed Reflection adjustment rows only after source-backed feedback exists",
        )
    result = _read_jsonl_result(path)
    selected: list[dict[str, Any]] = []
    for row in result.rows:
        if row.get("kind") != "aippocampus_reflection_adjustment":
            continue
        if not _has_source_refs(row):
            continue
        if not _task_matches(task, row, ("target_id", "reason", "feedback_action", "surface")):
            continue
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected, _component(
        "reflection_adjustment_sidecar",
        status="projected" if selected else "no_relevant_route",
        item_count=len(selected),
        next_action="" if selected else "continue without Reflection adjustment; no reviewed feedback matched",
        jsonl_loss=result.loss,
    )


def _local_working_memory_path(root: Path) -> Path | None:
    return _first_existing(root, LOCAL_WORKING_MEMORY_FILENAMES)


def _reviewed_background_findings(
    *,
    task: str,
    project: str,
    root: Path,
    registry_dir: str | Path | None,
    explicit_path: str | Path | None,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    working_memory = Path(explicit_path).expanduser().resolve() if explicit_path else _local_working_memory_path(root)
    if working_memory is None and not registry_dir:
        return [], _component(
            "reviewed_background_findings",
            status="missing",
            next_action="run agent background for this task or provide a reviewed working-memory sidecar",
        )
    card = background_findings.background_findings_card(
        task,
        registry_dir=registry_dir,
        working_memory_path=working_memory,
        project=project,
        limit=limit,
        detail="compact",
    )
    summaries = [
        item
        for item in [card.get("best_finding"), *(card.get("finding_summaries") or [])]
        if isinstance(item, Mapping)
    ][:limit]
    status = "projected" if summaries else str(card.get("status") or "no_relevant_background_findings")
    return [dict(item) for item in summaries], _component(
        "reviewed_background_findings",
        status=status,
        item_count=len(summaries),
        next_action="" if summaries else "use ordinary recall or agent background if reviewed findings should exist",
        source="reviewed_working_memory_projection",
    )


def load_orientation_sidecars(
    task: str,
    *,
    project: str = "AIppocampus",
    cwd: str | Path | None = None,
    sidecar_dir: str | Path | None = None,
    registry_dir: str | Path | None = None,
    journeys_path: str | Path | None = None,
    episode_arcs_path: str | Path | None = None,
    reflection_adjustments_path: str | Path | None = None,
    working_memory_path: str | Path | None = None,
    limit_per_component: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Load capped, task-scoped navigation sidecars for ordinary orientation."""

    clean_task = _text(task, 240)
    root = _project_sidecar_root(cwd=cwd, sidecar_dir=sidecar_dir)
    limit = max(1, min(int(limit_per_component or DEFAULT_LIMIT), 6))

    journeys, journey_component = _journey_rows(
        task=clean_task,
        root=root,
        explicit_path=journeys_path,
        limit=limit,
    )
    arcs, arc_component = _episode_arc_rows(
        task=clean_task,
        root=root,
        explicit_path=episode_arcs_path,
        limit=limit,
    )
    adjustments, adjustment_component = _reflection_adjustments(
        task=clean_task,
        root=root,
        explicit_path=reflection_adjustments_path,
        limit=limit,
    )
    findings, background_component = _reviewed_background_findings(
        task=clean_task,
        project=project,
        root=root,
        registry_dir=registry_dir,
        explicit_path=working_memory_path,
        limit=limit,
    )
    components = [journey_component, arc_component, adjustment_component, background_component]
    projected_count = sum(int(item.get("item_count") or 0) for item in components)
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "status": "projected" if projected_count else "no_relevant_sidecars",
            "project": project,
            "sidecar_root_label": ".aippocampus",
            "components": components,
            "journeys": journeys,
            "episode_arcs": arcs,
            "reflection_adjustments": adjustments,
            "reviewed_background_findings": findings,
            "metrics": {
                "projected_item_count": projected_count,
                "component_count": len(components),
                "max_items_per_component": limit,
            },
            "source_boundary": {
                "navigation_only_not_fact": True,
                "sidecars_are_not_source_truth": True,
                "source_reopen_required_before_claims": True,
                "raw_source_text_serialized": False,
                "local_paths_serialized": False,
                "raw_dream_delivery_enabled": False,
            },
        }
    )


__all__ = [
    "DEFAULT_LIMIT",
    "KIND",
    "SCHEMA_VERSION",
    "load_orientation_sidecars",
]
