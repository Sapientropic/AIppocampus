#!/usr/bin/env python3
"""Dry-run storage governance over existing AIppocampus storage reports.

The governance command is intentionally report-first. It may generate the
registry-scale capacity report because that report only stats files and reads
manifests, but it does not generate a retention report implicitly: retention
audits can contain raw-rollout excerpts, so operators must create or pass that
report explicitly when they want path-level cleanup candidates.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, cast

from aippocampus_runtime.cli.human_io import exit_code_for_payload
from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.core import (
    codex_home,
    default_thread_retention_dir,
    locate_rollout,
    now_utc,
    resolve_artifact_path,
)
from aippocampus_runtime.ops import storage_capacity_report
from aippocampus_runtime.ops import storage_governance_actions as gc_actions
from aippocampus_runtime.ops.storage_eviction import apply_rebuildable_evictions
from aippocampus_runtime.ops.storage_governance_contract import (
    CLASS_ALL,
    CLASS_REBUILDABLE,
    REBUILDABLE_ACTIONS,
    REVIEW_ARTIFACT_ACTIONS,
    SCHEMA_VERSION,
    SUPPORTED_CLASSES,
    TIER_REBUILDABLE_CACHE,
    TIER_REVIEW_ARTIFACT,
    candidate_class_for_tier,
    capacity_preconditions,
    generation_gc_candidates_from_capacity_thread,
    human_bytes,
    matches_class,
    plan_metrics,
    rebuild_command_for_retention_item,
    segment_generation_gc_candidates_from_capacity_thread,
    status,
)
from aippocampus_runtime.ops.storage_governance_projection import (
    bounded_cli_projection,
    redact_report_sources,
    render_apply_text,
    render_text,
)
from aippocampus_runtime.source.io_kernel import load_json_dict


def load_governance_json_report(path: Path) -> dict[str, Any]:
    result = load_json_dict(path, missing_is_loss=True)
    loss = result.loss
    if int(loss.get("non_object_json_count") or 0):
        raise ValueError(f"JSON report {path} must contain an object")
    if int(loss.get("total_loss_count") or 0):
        raise ValueError(f"could not read JSON report {path}")
    return result.data


def _path_projection(
    path_text: str | None,
    *,
    roots: Iterable[tuple[str, Path]],
    include_paths: bool,
) -> dict[str, Any]:
    if not path_text:
        return {"path_known": False}
    path = Path(path_text)
    result: dict[str, Any] = {
        "path_known": True,
        "path_label": path.name or str(path),
    }
    for label, root in roots:
        try:
            relative = path.resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            continue
        result["relative_path"] = relative
        result["relative_to"] = label
        break
    if include_paths:
        result["path"] = str(path)
    return result


def _retention_preconditions(
    retention_report: dict[str, Any],
    *,
    tier: str,
    include_active: bool,
) -> dict[str, dict[str, str]]:
    rollout = retention_report.get("rollout") or {}
    anchors = retention_report.get("anchors") or {}
    rollout_size = int(rollout.get("size_bytes") or 0)
    anchors_exists = bool(anchors.get("exists"))
    anchors_count = int(anchors.get("count") or 0)

    active_status = "needs_apply_check" if include_active else "blocked_by_default"
    active_evidence = (
        "--include-active was passed; apply mode must still prove no live writer owns the path."
        if include_active
        else "Current-thread eviction is excluded by default until --include-active is explicit."
    )

    preconditions = {
        "raw_or_archive_source": status(
            "passed" if rollout_size > 0 else "blocked",
            evidence=(
                f"retention_report rollout.size_bytes={rollout_size}"
                if rollout_size > 0
                else "retention_report has no positive rollout size"
            ),
            requirement="Raw rollout or verified cold archive must exist before eviction.",
        ),
        "anchors_or_registry_refs": status(
            "passed" if anchors_exists and anchors_count > 0 else "needs_apply_check",
            evidence=(
                f"retention_report anchors.count={anchors_count}"
                if anchors_exists
                else "retention_report does not prove anchor presence"
            ),
            requirement="Anchors or registry source refs must survive cache eviction.",
        ),
        "active_thread_exclusion": status(
            active_status,
            evidence=active_evidence,
            requirement="Do not evict the current active thread unless explicitly requested.",
        ),
        "writer_or_export_lease": status(
            "needs_apply_check",
            evidence="Dry-run does not inspect live writer/build/export leases.",
            requirement="No active writer/build/export lease may own the target path.",
        ),
    }
    if tier == TIER_REBUILDABLE_CACHE:
        preconditions["last_known_good_pointer"] = status(
            "needs_apply_check",
            evidence="Dry-run does not mutate generation pointer or last-known-good state.",
            requirement="Apply mode must preserve last-known-good/index pointer semantics.",
        )
    if tier == TIER_REVIEW_ARTIFACT:
        preconditions["human_review_or_inactive_export"] = status(
            "needs_apply_check",
            evidence="Dry-run cannot prove no active review/export is using the artifact.",
            requirement="Review artifacts are eligible only after human review or inactive export.",
        )
    return preconditions


def _candidate_from_retention_item(
    item: dict[str, Any],
    *,
    retention_report: dict[str, Any],
    roots: list[tuple[str, Path]],
    include_active: bool,
    include_paths: bool,
) -> dict[str, Any] | None:
    action = str(item.get("action") or "")
    if action in REBUILDABLE_ACTIONS:
        tier = TIER_REBUILDABLE_CACHE
    elif action in REVIEW_ARTIFACT_ACTIONS:
        tier = TIER_REVIEW_ARTIFACT
    else:
        return None

    size = int(item.get("bytes") or 0)
    candidate_class = candidate_class_for_tier(tier)
    return {
        "id": f"retention:{item.get('id')}",
        "class": candidate_class,
        "tier": tier,
        "label": item.get("label"),
        "kind": item.get("kind"),
        "bytes": size,
        "human_bytes": human_bytes(size),
        "path": _path_projection(
            item.get("path"),
            roots=roots,
            include_paths=include_paths,
        ),
        "source_report": {
            "kind": "retention_report",
            "schema_version": retention_report.get("schema_version"),
            "item_id": item.get("id"),
            "action": action,
            "safety": item.get("safety"),
            "owner_index": _path_projection(
                retention_report.get("index_dir"),
                roots=roots,
                include_paths=include_paths,
            ),
        },
        "evidence": list(item.get("evidence") or []),
        "preconditions": _retention_preconditions(
            retention_report,
            tier=tier,
            include_active=include_active,
        ),
        "rebuild_command": rebuild_command_for_retention_item(item),
        "expected_rebuild_cost": {
            "class": "medium" if tier == TIER_REBUILDABLE_CACHE else "manual_review",
            "seconds": None,
        },
    }


def _capacity_candidates(
    capacity_report: dict[str, Any],
    *,
    include_active: bool,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for thread in capacity_report.get("candidate_threads") or capacity_report.get("top_threads") or []:
        generated = int(thread.get("generated_index_bytes") or 0)
        semantic = int(thread.get("semantic_sidecar_bytes") or 0)
        size = generated + semantic
        if size <= 0:
            continue
        thread_dir = str(thread.get("thread_dir") or thread.get("thread_key") or "thread")
        candidates.append(
            {
                "id": f"capacity:{thread_dir}:generated-cache",
                "class": CLASS_REBUILDABLE,
                "tier": TIER_REBUILDABLE_CACHE,
                "label": f"Generated cache footprint for {thread_dir}",
                "kind": "aggregate_rebuildable_cache",
                "bytes": size,
                "human_bytes": human_bytes(size),
                "path": {
                    "path_known": bool(thread.get("relative_path")),
                    "relative_path": thread.get("relative_path"),
                    "relative_to": "registry",
                },
                "source_report": {
                    "kind": "storage_capacity_report",
                    "schema_version": capacity_report.get("schema_version"),
                    "section": "top_threads",
                    "thread_key": thread.get("thread_key"),
                    "thread_dir": thread.get("thread_dir"),
                },
                "evidence": [
                    f"generated_index_bytes={generated}",
                    f"semantic_sidecar_bytes={semantic}",
                    f"index_amplification_ratio={thread.get('index_amplification_ratio')}",
                    f"query_fanout_indexes={thread.get('query_fanout_indexes')}",
                ],
                "preconditions": capacity_preconditions(
                    thread,
                    include_active=include_active,
                ),
                "actionability": "plan_only_aggregate",
                "plan_only_reason": gc_actions.CAPACITY_AGGREGATE_PLAN_ONLY_REASON,
                "rebuild_note": gc_actions.CAPACITY_AGGREGATE_REBUILD_NOTE,
                "expected_rebuild_cost": {"class": "medium", "seconds": None},
            }
        )
        candidates.extend(
            generation_gc_candidates_from_capacity_thread(
                thread,
                include_active=include_active,
            )
        )
        candidates.extend(
            segment_generation_gc_candidates_from_capacity_thread(
                thread,
                include_active=include_active,
            )
        )
    return candidates


def _default_retention_report_path(cwd: Path) -> tuple[Path | None, list[Path]]:
    attempted = [cwd / ".aippocampus" / "retention" / "retention_report.json"]
    try:
        rollout = locate_rollout(cwd, codex_home())
    except Exception:
        rollout = None
    if rollout is not None:
        attempted.insert(0, default_thread_retention_dir(cwd, rollout) / "retention_report.json")
    for path in attempted:
        if path.exists():
            return path, attempted
    return None, attempted


def _load_capacity_report(
    *,
    registry_dir: str | Path | None,
    capacity_report_path: Path | None,
    top: int,
    include_paths: bool,
    planner_query: str | None,
    fanout_budget: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if capacity_report_path is not None:
        return load_governance_json_report(capacity_report_path), {
            "kind": "storage_capacity_report",
            "mode": "loaded_existing_json",
            "path": str(capacity_report_path),
        }
    report = storage_capacity_report.build_report(
        registry_dir,
        top=top,
        include_paths=include_paths,
        include_candidate_threads=True,
        planner_query=planner_query,
        fanout_budget=fanout_budget,
    )
    return report, {
        "kind": "storage_capacity_report",
        "mode": "generated_without_message_bodies",
    }


def _load_retention_report(
    *,
    cwd: Path,
    retention_report_path: Path | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    attempted: list[Path] = []
    path = retention_report_path
    if path is None:
        path, attempted = _default_retention_report_path(cwd)
    if path is None:
        return None, {
            "kind": "retention_report",
            "mode": "missing",
            "attempted": [str(item) for item in attempted],
            "note": "Run retention_report.py --write or pass --retention-report for path-level candidates.",
        }
    return load_governance_json_report(path), {
        "kind": "retention_report",
        "mode": "loaded_existing_json",
        "path": str(path),
    }


def build_plan(
    cwd: str | Path | None = None,
    *,
    registry_dir: str | Path | None = None,
    capacity_report_path: str | Path | None = None,
    retention_report_path: str | Path | None = None,
    class_filter: str = CLASS_ALL,
    include_active: bool = False,
    include_paths: bool = False,
    top: int = 12,
    planner_query: str | None = None,
    fanout_budget: int = 64,
) -> dict[str, Any]:
    if class_filter not in SUPPORTED_CLASSES:
        raise ValueError(f"unsupported class: {class_filter}")

    cwd_path = Path(cwd or os.getcwd()).resolve()
    capacity_path = (
        resolve_artifact_path(capacity_report_path, cwd_path, Path())
        if capacity_report_path is not None
        else None
    )
    retention_path = (
        resolve_artifact_path(retention_report_path, cwd_path, Path())
        if retention_report_path is not None
        else None
    )
    registry_path = Path(registry_dir).resolve() if registry_dir is not None else None
    capacity_report, capacity_source = _load_capacity_report(
        registry_dir=registry_path,
        capacity_report_path=capacity_path,
        top=top,
        include_paths=include_paths,
        planner_query=planner_query,
        fanout_budget=fanout_budget,
    )
    retention_report, retention_source = _load_retention_report(
        cwd=cwd_path,
        retention_report_path=retention_path,
    )

    roots: list[tuple[str, Path]] = []
    if retention_report and retention_report.get("index_dir"):
        roots.append(("thread_index", Path(str(retention_report["index_dir"]))))
    if registry_path is not None:
        roots.append(("registry", registry_path))
    elif capacity_report.get("registry", {}).get("path"):
        roots.append(("registry", Path(str(capacity_report["registry"]["path"]))))
    roots.append(("cwd", cwd_path))

    all_candidates: list[dict[str, Any]]
    if retention_report is not None:
        all_candidates = [
            candidate
            for item in retention_report.get("items") or []
            if (
                candidate := _candidate_from_retention_item(
                    item,
                    retention_report=retention_report,
                    roots=roots,
                    include_active=include_active,
                    include_paths=include_paths,
                )
            )
            is not None
        ]
    else:
        all_candidates = _capacity_candidates(
            capacity_report,
            include_active=include_active,
        )
    candidates = [
        candidate for candidate in all_candidates if matches_class(candidate, class_filter)
    ]

    foreground_actions = gc_actions.storage_gc_foreground_actions(
        retention_report_available=retention_report is not None,
    )
    safe_next_actions = cast(list[dict[str, Any]], foreground_actions["safe_next_actions"])
    next_steps = cast(list[str], foreground_actions["next_steps"])
    action_fields = canonical_foreground_action_fields(
        safe_next_actions[0],
        safe_next_actions=safe_next_actions,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "status": "dry_run_ready",
        "surface_class": "foreground_storage_gc_plan",
        **action_fields,
        "created_at": now_utc(),
        "mode": "dry_run",
        "requested_class": class_filter,
        "apply_supported": False,
        "privacy": {
            "reads_clean_source_message_bodies": False,
            "reads_raw_rollout_bodies": False,
            "reads_json_manifests": True,
            "loads_existing_retention_report": retention_report is not None,
            "absolute_paths_included": include_paths,
            "local_private_identifiers_included": include_paths,
        },
        "policy_model": {
            "canonical_source_tier": {
                "default_action": "never_auto_delete_or_lossy_prune",
                "examples": ["raw rollout", "clean source", "anchors", "registry refs"],
            },
            "rebuildable_cache_tier": {
                "default_action": "eligible_for_eviction_under_disk_pressure_with_preconditions",
                "examples": ["SQLite/FTS indexes", "segment indexes", "Graphify corpus"],
            },
            "navigation_review_artifact_tier": {
                "default_action": "eligible_only_after_inactive_export_or_human_review",
                "examples": ["bundle staging", "screenshots", "review traces"],
            },
        },
        "report_sources": redact_report_sources(
            {"capacity": capacity_source, "retention": retention_source},
            include_paths=include_paths,
        ),
        "metrics": plan_metrics(
            capacity_report=capacity_report,
            retention_report=retention_report,
            candidates=candidates,
        ),
        "candidates": candidates,
        "warnings": [
            item
            for item in [
                (
                    "Path-level retention candidates are unavailable because no existing "
                    "retention_report.json was found or passed."
                    if retention_report is None
                    else None
                ),
                (
                    "Apply v1 evicts retention-report-backed main SQLite caches and old "
                    "generation directories whose apply-time reader-pin/TTL and pointer "
                    "checks pass; capacity aggregates and other candidate classes remain plan-only."
                ),
            ]
            if item
        ],
        "next_steps": next_steps,
    }


def apply_plan(
    cwd: str | Path | None = None,
    *,
    registry_dir: str | Path | None = None,
    capacity_report_path: str | Path | None = None,
    retention_report_path: str | Path | None = None,
    class_filter: str = CLASS_REBUILDABLE,
    include_active: bool = False,
    include_paths: bool = False,
    top: int = 12,
    planner_query: str | None = None,
    fanout_budget: int = 64,
) -> dict[str, Any]:
    plan = build_plan(
        cwd,
        registry_dir=registry_dir,
        capacity_report_path=capacity_report_path,
        retention_report_path=retention_report_path,
        class_filter=class_filter,
        include_active=include_active,
        include_paths=True,
        top=top,
        planner_query=planner_query,
        fanout_budget=fanout_budget,
    )
    outcome = apply_rebuildable_evictions(
        plan,
        include_active=include_active,
        include_paths=include_paths,
    )
    metrics = dict(plan["metrics"])
    metrics.update(
        {
            "eviction_applied_count": len(outcome["applied"]),
            "eviction_blocked_count": len(outcome["blocked"]),
            "eviction_skipped_count": len(outcome.get("skipped") or []),
            "reclaimed_bytes": outcome["reclaimed_bytes"],
            "reclaimed_human": outcome["reclaimed_human"],
            "post_eviction_recall_surface_ok": bool(outcome["applied"]) and not outcome["blocked"],
            "post_eviction_recall_surface_status": (
                "intentional_rebuildable_degraded"
                if outcome["applied"]
                else "not_changed"
            ),
        }
    )
    warnings = list(plan.get("warnings", []))
    if class_filter == CLASS_ALL:
        warnings.append("Apply mode only evicts supported rebuildable cache candidates; other classes are blocked.")
    if outcome["blocked"]:
        warnings.append("One or more candidates were not evicted because apply preconditions failed.")
    if outcome.get("skipped"):
        warnings.append("One or more plan-only candidates were explicitly skipped by apply mode.")
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": now_utc(),
        "mode": "apply",
        "requested_class": class_filter,
        "apply_supported": True,
        "ok": bool(outcome["applied"]) and not outcome["blocked"],
        "privacy": {
            "reads_clean_source_message_bodies": False,
            "reads_raw_rollout_bodies": False,
            "reads_json_manifests": True,
            "loads_existing_retention_report": plan["privacy"]["loads_existing_retention_report"],
            "absolute_paths_included": include_paths,
        },
        "report_sources": redact_report_sources(
            plan["report_sources"],
            include_paths=include_paths,
        ),
        "metrics": metrics,
        "applied": outcome["applied"],
        "blocked": outcome["blocked"],
        "skipped": outcome.get("skipped") or [],
        "warnings": warnings,
        "next_steps": [
            "Run health/maintenance after apply; intentional rebuildable eviction should report degraded-but-rebuildable state.",
            "Rebuild evicted caches from the manifest rebuild_command before relying on generated-cache search performance.",
        ],
    }


def _error_payload(code: str, message: str, *, error_class: str = "usage_error") -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "error": {
            "code": code,
            "class": error_class,
            "message": message,
        },
        "data": None,
    }


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="aippocampus storage")
    subparsers = parser.add_subparsers(dest="command", required=True)
    gc_parser = subparsers.add_parser(
        "gc",
        usage="aippocampus storage gc --dry-run --summary-json --cwd .",
        help="Plan storage cleanup from capacity and retention evidence.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Plan or apply AIppocampus storage cleanup.

Safe first step:
  aippocampus storage gc --dry-run --summary-json --cwd .

`--dry-run` performs no writes. It reports candidate classes and why cleanup is
or is not allowed.

`--apply` may delete only candidates that pass deterministic source, manifest,
lease, active-thread, and rebuildability checks. Prefer the narrow supported
path:
  aippocampus storage gc --apply --class rebuildable --include-active --summary-json --cwd .

High-risk/private flags:
  --include-active asks apply-time checks to consider paths near active work;
     it is still blocked unless live-writer and source checks pass.
  --include-paths prints local filesystem paths and is for private operator
     diagnostics only.""",
    )
    mode_group = gc_parser.add_mutually_exclusive_group(required=False)
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="No-write planning mode. Use this before any cleanup apply.",
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help="Attempt cleanup after deterministic checks; prefer --class rebuildable.",
    )
    gc_parser.add_argument("--cwd", default=os.getcwd())
    gc_parser.add_argument("--registry-dir", default=None)
    gc_parser.add_argument("--capacity-report", default=None)
    gc_parser.add_argument("--retention-report", default=None)
    gc_parser.add_argument(
        "--class",
        dest="class_filter",
        default=CLASS_ALL,
        choices=sorted(SUPPORTED_CLASSES),
        help="Candidate class to plan/apply. Apply is safest and best-supported for rebuildable.",
    )
    gc_parser.add_argument(
        "--include-active",
        action="store_true",
        help="Private/high-risk: include active-thread-adjacent paths for apply-time checks.",
    )
    gc_parser.add_argument(
        "--include-paths",
        action="store_true",
        help="Private diagnostic: print local paths that are redacted by default.",
    )
    gc_parser.add_argument("--top", type=int, default=12)
    gc_parser.add_argument("--planner-query", default=None)
    gc_parser.add_argument("--fanout-budget", type=int, default=64)
    gc_parser.add_argument("--json", action="store_true", dest="json_output")
    gc_parser.add_argument(
        "--summary-json",
        action="store_true",
        help="Emit a bounded foreground summary instead of the full audit payload.",
    )
    gc_parser.add_argument(
        "--full",
        action="store_true",
        help="With --json, include the full candidate list instead of the --top bounded sample.",
    )
    args = parser.parse_args(raw_args)

    if args.command != "gc":
        parser.print_help()
        return 2
    if not args.dry_run and not args.apply:
        if args.summary_json:
            args.dry_run = True
        elif (
            not args.json_output
            and not args.summary_json
            and getattr(sys.stdout, "isatty", lambda: False)()
        ):
            # The human no-flag path should be useful on an interactive
            # terminal, but the piped/no-flag path stays a clear command hint
            # so scripts do not silently receive a different machine contract.
            args.dry_run = True
        else:
            gc_parser.print_help(sys.stderr)
            return exit_code_for_payload(
                _error_payload(
                    "storage_gc_invalid_report",
                    "Storage GC needs --dry-run, --summary-json, or --apply before it can produce a report.",
                    error_class="validation_error",
                )
            )
    if args.apply:
        try:
            result = apply_plan(
                args.cwd,
                registry_dir=args.registry_dir,
                capacity_report_path=args.capacity_report,
                retention_report_path=args.retention_report,
                class_filter=args.class_filter,
                include_active=args.include_active,
                include_paths=args.include_paths,
                top=args.top,
                planner_query=args.planner_query,
                fanout_budget=args.fanout_budget,
            )
        except ValueError as exc:
            if args.json_output:
                print(
                    json.dumps(
                        _error_payload(
                            "storage_gc_invalid_report",
                            str(exc),
                            error_class="validation_error",
                        ),
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(str(exc), file=sys.stderr)
            return 2
        if args.json_output or args.summary_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(render_apply_text(result))
        return exit_code_for_payload(result)

    explicit_top = "--top" in raw_args or any(item.startswith("--top=") for item in raw_args)
    plan_top = max(1, int(args.top))
    plan_fanout_budget = max(1, int(args.fanout_budget))
    foreground_json = args.summary_json or (args.json_output and not args.full)
    if foreground_json:
        plan_top = plan_top if explicit_top else 1
        plan_fanout_budget = min(plan_fanout_budget, 16)
        if args.capacity_report is None and args.retention_report is None:
            retention_path, _attempted = _default_retention_report_path(Path(args.cwd).resolve())
            if retention_path is not None:
                args.retention_report = str(retention_path)
    try:
        plan = build_plan(
            args.cwd,
            registry_dir=args.registry_dir,
            capacity_report_path=args.capacity_report,
            retention_report_path=args.retention_report,
            class_filter=args.class_filter,
            include_active=args.include_active,
            include_paths=args.include_paths,
            top=plan_top,
            planner_query=args.planner_query,
            fanout_budget=plan_fanout_budget,
        )
    except ValueError as exc:
        if args.json_output:
            print(
                json.dumps(
                    _error_payload(
                        "storage_gc_invalid_report",
                        str(exc),
                        error_class="validation_error",
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(str(exc), file=sys.stderr)
        return exit_code_for_payload(
            _error_payload(
                "storage_gc_invalid_report",
                str(exc),
                error_class="validation_error",
            )
        )
    if args.summary_json:
        print(
            json.dumps(
                bounded_cli_projection(
                    plan,
                    limit=plan_top,
                    summary_only=True,
                    schema_version=SCHEMA_VERSION,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.json_output:
        payload = plan if args.full else bounded_cli_projection(
            plan,
            limit=plan_top,
            summary_only=False,
            schema_version=SCHEMA_VERSION,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
