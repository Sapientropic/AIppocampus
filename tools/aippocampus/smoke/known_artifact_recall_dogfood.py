#!/usr/bin/env python3
"""Cheap dogfood probes for known project-artifact recall failures."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

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
    "artifact_exists",
    "live_recall_found",
    "live_search_found",
    "usable_foreground_action",
)
CommandRunner = Callable[[list[str], Path], dict[str, Any]]

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


def _default_command_runner(argv: list[str], cwd: Path) -> dict[str, Any]:
    proc = subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    payload: Any = {}
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    return {
        "returncode": proc.returncode,
        "payload": payload,
        "stdout_present": bool(proc.stdout.strip()),
        "stderr_present": bool(proc.stderr.strip()),
    }


def _target_needles(case: dict[str, Any]) -> list[str]:
    needles = [str(path) for path in case.get("expected_paths") or [] if str(path).strip()]
    discussion = str(case.get("discussion") or "").strip()
    if discussion:
        needles.extend([f"/discussions/{discussion}", f"discussion {discussion}", f"#{discussion}"])
    if case.get("case_id") == "discussion_2127_exact_public_phrase":
        needles.extend(["/discussions/2127", "discussion 2127", "#2127"])
    return needles


def _payload_contains_any(value: Any, needles: list[str]) -> bool:
    if not needles:
        return False
    lowered = [needle.casefold() for needle in needles if needle]

    def walk(item: Any) -> bool:
        if isinstance(item, dict):
            return any(walk(child) for child in item.values())
        if isinstance(item, list):
            return any(walk(child) for child in item)
        text = str(item or "").casefold()
        return any(needle in text for needle in lowered)

    return walk(value)


def _foreground_action_is_usable(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return _has_action(payload.get("foreground_action")) or _has_action(
        payload.get("safe_next_actions")
    )


def _live_case_observation(
    case: dict[str, Any],
    *,
    repo_root: Path,
    command_runner: CommandRunner,
) -> dict[str, Any]:
    cue = str(case.get("cue") or "")
    needles = _target_needles(case)
    cli = [sys.executable, "-m", "aippocampus_runtime.cli.facade"]
    recall = command_runner([*cli, "agent", "recall", cue, "--json"], repo_root)
    search = command_runner([*cli, "search", "--all", cue, "--json"], repo_root)
    recall_payload = recall.get("payload")
    search_payload = search.get("payload")
    live_recall_found = _payload_contains_any(recall_payload, needles)
    live_search_found = _payload_contains_any(search_payload, needles)
    usable_foreground_action = bool(
        (live_recall_found and _foreground_action_is_usable(recall_payload))
        or (live_search_found and _foreground_action_is_usable(search_payload))
    )
    return {
        "status": "live_checked",
        "metrics": {
            "live_recall_found": live_recall_found,
            "live_search_found": live_search_found,
            "usable_foreground_action": usable_foreground_action,
            "usable_next_action": usable_foreground_action,
        },
        "live": {
            "recall_returncode": recall.get("returncode"),
            "search_returncode": search.get("returncode"),
            "recall_status": recall_payload.get("status") if isinstance(recall_payload, dict) else None,
            "search_status": search_payload.get("status") if isinstance(search_payload, dict) else None,
            "expected_target_seen_in_recall": live_recall_found,
            "expected_target_seen_in_search": live_search_found,
        },
    }


def _metrics_from_observation(observation: dict[str, Any]) -> dict[str, bool]:
    metrics: dict[str, bool] = {}
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
    if observation.get("artifact_exists"):
        metrics["artifact_exists"] = True
    if _has_action(observation.get("next_action") or observation.get("safe_next_actions")):
        metrics["usable_next_action"] = True
    return metrics


def _merge_metrics(base: dict[str, bool], observed: dict[str, bool]) -> dict[str, bool]:
    return {
        metric: bool(base.get(metric) or observed.get(metric))
        for metric in OBSERVED_METRICS
    }


def _static_case_result(case: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    metrics = _empty_metrics()
    evidence: dict[str, Any] = {}
    if case["artifact_kind"] == "repo_doc":
        found = [
            path
            for path in case.get("expected_paths") or []
            if (repo_root / str(path)).exists()
        ]
        metrics["artifact_exists"] = bool(found)
        metrics["known_artifact_found"] = bool(found)
        evidence["found_paths"] = found
        next_action = (
            "Run live agent recall/search for the named inventory; static file existence is setup only."
        )
    elif case["artifact_kind"] == "discussion_atlas_pointer":
        atlas_text = (repo_root / ATLAS_REL_PATH).read_text(encoding="utf-8")
        pointer = discussion_atlas_navigation_pointer(atlas_text, str(case["cue"]))
        metrics["artifact_exists"] = bool(pointer.get("ok"))
        metrics["known_artifact_found"] = bool(pointer.get("ok"))
        metrics["usable_next_action"] = bool(pointer.get("ok"))
        metrics["usable_foreground_action"] = bool(pointer.get("ok"))
        evidence["pointer"] = pointer.get("pointer") if pointer.get("ok") else None
        next_action = (
            str((pointer.get("pointer") or {}).get("next_action") or "")
            if pointer.get("ok")
            else str(pointer.get("next_action") or "")
        )
    else:
        atlas_text = (repo_root / ATLAS_REL_PATH).read_text(encoding="utf-8")
        pointer = discussion_atlas_navigation_pointer(atlas_text, str(case["cue"]))
        metrics["artifact_exists"] = bool(pointer.get("ok"))
        metrics["known_artifact_found"] = bool(pointer.get("ok"))
        metrics["usable_next_action"] = bool(pointer.get("ok"))
        metrics["usable_foreground_action"] = bool(pointer.get("ok"))
        evidence["pointer"] = pointer.get("pointer") if pointer.get("ok") else None
        next_action = (
            str((pointer.get("pointer") or {}).get("next_action") or "")
            if pointer.get("ok")
            else "Run `aippocampus search --all` and require no-match/low-coverage instead of unrelated routes."
        )
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
    command_runner: CommandRunner | None = _default_command_runner,
    cases: tuple[dict[str, Any], ...] = DEFAULT_CASES,
) -> dict[str, Any]:
    by_case = _observation_by_case(observations or [])
    results: list[dict[str, Any]] = []
    for case in cases:
        result = _static_case_result(case, repo_root)
        if command_runner is not None:
            live_observation = _live_case_observation(
                case,
                repo_root=repo_root,
                command_runner=command_runner,
            )
            observed_metrics = _metrics_from_observation(live_observation)
            result["metrics"] = _merge_metrics(result["metrics"], observed_metrics)
            result["live"] = live_observation.get("live")
        observation = by_case.get(str(case["case_id"]))
        if observation:
            observed_metrics = _metrics_from_observation(observation)
            result["metrics"] = _merge_metrics(result["metrics"], observed_metrics)
            result["observation_status"] = observation.get("status")
        for field in (
            "artifact_exists",
            "live_recall_found",
            "live_search_found",
            "usable_foreground_action",
        ):
            result[field] = bool(result["metrics"].get(field))
        if case["artifact_kind"] == "repo_doc":
            live_found = bool(
                result["metrics"]["live_recall_found"] or result["metrics"]["live_search_found"]
            )
            setup_ok = bool(result["metrics"]["artifact_exists"])
            usable = bool(result["metrics"]["usable_foreground_action"])
        elif case["artifact_kind"] == "phrase_search_negative_control":
            live_found = bool(
                result["metrics"]["live_recall_found"]
                or result["metrics"]["live_search_found"]
                or result["metrics"]["known_artifact_found"]
            )
            setup_ok = bool(result["metrics"]["known_artifact_found"])
            usable = bool(
                result["metrics"]["usable_next_action"]
                or result["metrics"]["usable_foreground_action"]
            )
        else:
            live_found = bool(
                result["metrics"]["live_recall_found"]
                or result["metrics"]["live_search_found"]
                or result["metrics"]["usable_foreground_action"]
            )
            setup_ok = bool(result["metrics"]["artifact_exists"])
            usable = bool(result["metrics"]["usable_next_action"])
        result["ok"] = bool(
            setup_ok
            and (live_found or result["metrics"]["usable_foreground_action"])
            and usable
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
