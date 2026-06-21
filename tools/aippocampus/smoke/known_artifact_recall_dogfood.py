#!/usr/bin/env python3
"""Cheap dogfood probes for known project-artifact recall failures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

DOC_TOOLS = Path(__file__).resolve().parents[1] / "docs"
sys.path.insert(0, str(DOC_TOOLS))

from discussion_atlas_guard import (  # noqa: E402
    ATLAS_REL_PATH,
    discussion_atlas_navigation_pointer,
)

OBSERVED_METRICS = (
    "manual_search_fallback",
    "irrelevant_memory_drag",
    "wrong_route_drag",
    "known_artifact_found",
    "usable_next_action",
)

DEFAULT_CASES: tuple[dict[str, Any], ...] = (
    {
        "case_id": "compatibility_inventory_natural_cue",
        "cue": "compatibility historical fields inventory/report",
        "artifact_kind": "repo_doc",
        "expected_paths": [
            "docs/architecture/ops/compatibility-shim-inventory.md",
            "docs/architecture/ops/legacy-alias-inventory.md",
        ],
        "owner": "recall_fallback",
    },
    {
        "case_id": "discussion_2127_natural_cue",
        "cue": "discussion 2127 source-backed conversation too safe but useless discussion article",
        "artifact_kind": "discussion_atlas_pointer",
        "discussion": 2127,
        "owner": "discussion_atlas_guard",
    },
    {
        "case_id": "discussion_2127_exact_public_phrase",
        "cue": "A safe packet that leaves the agent lost is not a success",
        "artifact_kind": "phrase_search_negative_control",
        "owner": "registry_search_phrase_coverage",
    },
)


def _empty_metrics() -> dict[str, bool]:
    return {metric: False for metric in OBSERVED_METRICS}


def _observation_by_case(observations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("case_id") or ""): item
        for item in observations
        if isinstance(item, dict) and item.get("case_id")
    }


def _has_action(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(value.get("command") or value.get("command_template") or value.get("next_action"))
    if isinstance(value, list):
        return any(_has_action(item) for item in value)
    return False


def _metrics_from_observation(observation: dict[str, Any]) -> dict[str, bool]:
    metrics = _empty_metrics()
    raw_metrics = observation.get("metrics")
    if isinstance(raw_metrics, dict):
        for metric in OBSERVED_METRICS:
            if metric in raw_metrics:
                metrics[metric] = bool(raw_metrics[metric])
    status = str(observation.get("status") or "").casefold()
    if status in {"refine_only", "no_route", "no_match", "manual_search_needed"}:
        metrics["manual_search_fallback"] = True
    if status in {"wrong_route", "unrelated_route"}:
        metrics["wrong_route_drag"] = True
    if status in {"irrelevant_matches", "unrelated_high_confidence"}:
        metrics["irrelevant_memory_drag"] = True
    if observation.get("known_artifact_found"):
        metrics["known_artifact_found"] = True
    if _has_action(observation.get("next_action") or observation.get("safe_next_actions")):
        metrics["usable_next_action"] = True
    return metrics


def _static_case_result(case: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    metrics = _empty_metrics()
    evidence: dict[str, Any] = {}
    if case["artifact_kind"] == "repo_doc":
        found = [
            path
            for path in case.get("expected_paths") or []
            if (repo_root / str(path)).exists()
        ]
        metrics["known_artifact_found"] = bool(found)
        metrics["usable_next_action"] = bool(found)
        evidence["found_paths"] = found
        next_action = f"Open {found[0]} before answering." if found else "Run repo/doc search for the named inventory."
    elif case["artifact_kind"] == "discussion_atlas_pointer":
        atlas_text = (repo_root / ATLAS_REL_PATH).read_text(encoding="utf-8")
        pointer = discussion_atlas_navigation_pointer(atlas_text, str(case["cue"]))
        metrics["known_artifact_found"] = bool(pointer.get("ok"))
        metrics["usable_next_action"] = bool(pointer.get("ok"))
        evidence["pointer"] = pointer.get("pointer") if pointer.get("ok") else None
        next_action = (
            str((pointer.get("pointer") or {}).get("next_action") or "")
            if pointer.get("ok")
            else str(pointer.get("next_action") or "")
        )
    else:
        next_action = "Run `aippocampus search --all` and require no-match/low-coverage instead of unrelated routes."
        metrics["usable_next_action"] = True
    return {
        "case_id": case["case_id"],
        "cue": case["cue"],
        "artifact_kind": case["artifact_kind"],
        "owner": case["owner"],
        "metrics": metrics,
        "next_action": next_action,
        "evidence": evidence,
    }


def evaluate_known_artifact_recall(
    *,
    repo_root: Path,
    observations: list[dict[str, Any]] | None = None,
    cases: tuple[dict[str, Any], ...] = DEFAULT_CASES,
) -> dict[str, Any]:
    by_case = _observation_by_case(observations or [])
    results: list[dict[str, Any]] = []
    for case in cases:
        result = _static_case_result(case, repo_root)
        observation = by_case.get(str(case["case_id"]))
        if observation:
            observed_metrics = _metrics_from_observation(observation)
            result["metrics"] = {**result["metrics"], **observed_metrics}
            result["observation_status"] = observation.get("status")
        result["ok"] = bool(
            result["metrics"]["known_artifact_found"]
            and result["metrics"]["usable_next_action"]
            and not result["metrics"]["irrelevant_memory_drag"]
            and not result["metrics"]["wrong_route_drag"]
        )
        if not result["ok"] and not result["metrics"]["manual_search_fallback"]:
            result["metrics"]["manual_search_fallback"] = True
        results.append(result)

    metric_counts = {
        metric: sum(1 for result in results if result["metrics"].get(metric))
        for metric in OBSERVED_METRICS
    }
    failing_owners = sorted({result["owner"] for result in results if not result["ok"]})
    return {
        "kind": "aippocampus_known_artifact_recall_dogfood",
        "schema_version": 1,
        "ok": not failing_owners,
        "case_count": len(results),
        "passed_count": sum(1 for result in results if result["ok"]),
        "failed_count": sum(1 for result in results if not result["ok"]),
        "metric_counts": metric_counts,
        "failing_owners": failing_owners,
        "cases": results,
        "privacy_boundary": {
            "discussion_bodies_serialized": False,
            "private_paths_serialized": False,
            "public_metadata_only": True,
        },
        "claim_boundary": "dogfood probe records known-artifact recall blockers; it is not a broad recall benchmark claim",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--observations-json", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    observations: list[dict[str, Any]] | None = None
    if args.observations_json:
        loaded = json.loads(args.observations_json.read_text(encoding="utf-8"))
        observations = loaded if isinstance(loaded, list) else loaded.get("observations", [])
    report = evaluate_known_artifact_recall(
        repo_root=args.repo_root,
        observations=observations,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"known-artifact recall dogfood: passed {report['passed_count']}/{report['case_count']}")
        if report["failing_owners"]:
            print("owners: " + ", ".join(report["failing_owners"]))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
