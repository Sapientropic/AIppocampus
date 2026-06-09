"""Public-safe AMemGym official-runner execution state projections."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()


def sha1_short(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def safe_path_label(path: Path | str) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(_paths.REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return f"external_file:{sha1_short(str(resolved))}"


def read_json(path: Path | str) -> dict[str, Any] | list[Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path | str, payload: dict[str, Any] | list[Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def env_data_items(env_data_path: Path | str) -> list[Any]:
    payload = read_json(env_data_path)
    if not isinstance(payload, list):
        raise ValueError("AMemGym env data must be a JSON array")
    return payload


def env_item_ids(env_data_path: Path | str) -> list[str]:
    payload = env_data_items(env_data_path)
    ids: list[str] = []
    for index, item in enumerate(payload, start=1):
        if isinstance(item, dict):
            ids.append(str(item.get("id") or f"row-{index}"))
        else:
            ids.append(f"row-{index}")
    return ids


def prepare_bounded_env_data(
    env_data_path: Path | str,
    *,
    max_cases: int | None,
    output_dir: Path | str,
) -> tuple[Path, dict[str, Any]]:
    try:
        items = env_data_items(env_data_path)
    except Exception as exc:
        return (
            Path(env_data_path),
            {
                "status": "env_data_unavailable",
                "source_env_data_label": safe_path_label(env_data_path),
                "active_env_data_label": safe_path_label(env_data_path),
                "full_item_count": None,
                "run_item_count": None,
                "max_cases": max_cases,
                "bounded_subset": False,
                "item_ids_sha1": None,
                "boundary": ["env_data_required_before_bounded_live_run"],
                "unavailable_reason": type(exc).__name__,
            },
        )
    full_count = len(items)
    if max_cases is not None and max_cases < 1:
        raise ValueError("--max-cases must be a positive integer")
    run_items = items[:max_cases] if max_cases is not None else items
    bounded_subset = max_cases is not None and len(run_items) < full_count
    active_env_data_path = Path(env_data_path)
    if bounded_subset:
        digest = sha1_short(f"{Path(env_data_path).resolve()}:{full_count}:{len(run_items)}")
        active_env_data_path = Path(output_dir) / f"{Path(env_data_path).stem}-first-{len(run_items)}-{digest}.json"
        # This ignored subset gives operators a bounded live-provider slice
        # without changing upstream AMemGym or treating the subset as full
        # public v1.base evidence.
        write_json(active_env_data_path, run_items)
    item_ids = []
    for index, item in enumerate(run_items, start=1):
        item_ids.append(str(item.get("id") or f"row-{index}") if isinstance(item, dict) else f"row-{index}")
    boundary = ["full_public_v1_base_candidate"]
    if bounded_subset:
        boundary = ["progressive_subset_debug_only", "not_full_public_v1_base_score"]
    elif max_cases is not None:
        boundary = ["requested_limit_covers_all_available_items"]
    return (
        active_env_data_path,
        {
            "source_env_data_label": safe_path_label(env_data_path),
            "active_env_data_label": safe_path_label(active_env_data_path),
            "full_item_count": full_count,
            "run_item_count": len(run_items),
            "max_cases": max_cases,
            "bounded_subset": bounded_subset,
            "item_ids_sha1": sha1_short("\n".join(item_ids)),
            "boundary": boundary,
        },
    )


def random_progress(path: Path) -> dict[str, Any]:
    return {
        "status": "complete" if path.exists() else "missing",
        "completed_file_count": 1 if path.exists() else 0,
        "expected_file_count": 1,
    }


def public_command_argv(
    surface: str,
    *,
    entrypoints: dict[str, str],
    env_data_path: Path | str,
    env_config_path: Path | str,
    agent_config_path: Path | str,
    overall_output_dir: Path | str,
    upperbound_output_dir: Path | str,
    random_output_file: Path | str,
    runner: str,
) -> list[str]:
    command_prefix = ["python", "-m"] if runner == "python" else ["uv", "run", "python", "-m"]
    if surface == "overall":
        return [
            *command_prefix,
            entrypoints[surface],
            "--agent_config",
            safe_path_label(agent_config_path),
            "--env_data",
            safe_path_label(env_data_path),
            "--env_config",
            safe_path_label(env_config_path),
            "--output_dir",
            safe_path_label(overall_output_dir),
        ]
    if surface == "upperbound":
        return [
            *command_prefix,
            entrypoints[surface],
            "--agent_config",
            safe_path_label(agent_config_path),
            "--env_data",
            safe_path_label(env_data_path),
            "--output_dir",
            safe_path_label(upperbound_output_dir),
        ]
    if surface == "random":
        return [
            *command_prefix,
            entrypoints[surface],
            "--env_data",
            safe_path_label(env_data_path),
            "--output_file",
            safe_path_label(random_output_file),
        ]
    raise ValueError(f"unknown AMemGym surface: {surface}")


def safe_command_plan(
    *,
    upstream_root: Path | str,
    env_data_path: Path | str,
    env_config_path: Path | str,
    agent_config_path: Path | str,
    overall_output_dir: Path | str,
    upperbound_output_dir: Path | str,
    random_output_file: Path | str,
    runner: str,
    arm: str,
    provider: str,
    entrypoints: dict[str, str],
    official_native_arm: str,
    local_scripted_provider: str,
    default_provider_overlay_root: Path | str,
    default_adapter_overlay_root: Path | str,
    provider_plan_environment: Any,
) -> dict[str, Any]:
    pythonpath_add = [safe_path_label(Path(upstream_root) / "src")]
    if provider == local_scripted_provider:
        pythonpath_add = [
            safe_path_label(Path(default_provider_overlay_root) / "local-scripted-provider"),
            *pythonpath_add,
        ]
    if arm != official_native_arm:
        pythonpath_add = [
            safe_path_label(Path(default_adapter_overlay_root) / "aippocampus" / "src"),
            "benchmarks/aippocampus",
            "skills/aippocampus/scripts",
            *pythonpath_add,
        ]
    return {
        "upstream_install": [
            "git clone https://github.com/AGI-Eval-Official/amemgym.git .tmp/amemgym-upstream",
            "cd .tmp/amemgym-upstream",
            "uv sync",
        ],
        "entrypoints": list(entrypoints.values()),
        "working_directory": safe_path_label(upstream_root),
        "environment": {
            "pythonpath_add": pythonpath_add,
            **provider_plan_environment(provider),
        },
        "arm": {
            "selected": arm,
            "official_factory_overlay_required": arm != official_native_arm,
        },
        "commands": {
            surface: public_command_argv(
                surface,
                entrypoints=entrypoints,
                env_data_path=env_data_path,
                env_config_path=env_config_path,
                agent_config_path=agent_config_path,
                overall_output_dir=overall_output_dir,
                upperbound_output_dir=upperbound_output_dir,
                random_output_file=random_output_file,
                runner=runner,
            )
            for surface in ("overall", "upperbound", "random")
        },
    }


def completed_surface_from_output(_surface: str, output_payload: dict[str, Any]) -> bool:
    return output_payload.get("status") == "found"


def skipped_complete_run_result(surface: str) -> dict[str, Any]:
    return {
        "surface": surface,
        "status": "skipped_complete",
        "ok": True,
        "returncode": None,
        "elapsed_ms": 0.0,
        "reason": "resume_existing_complete_output",
    }


def phase_status(output_status: str) -> str:
    if output_status == "found":
        return "complete"
    if output_status == "partial":
        return "partial"
    return "missing"


def phase_incomplete_reason(surface: str, status: str) -> str | None:
    if status == "complete":
        return None
    return f"official_{surface}_output_{status}"


def run_elapsed_by_surface(run_results: list[dict[str, Any]]) -> dict[str, float]:
    elapsed: dict[str, float] = {}
    for result in run_results:
        surface = result.get("surface")
        value = result.get("elapsed_ms")
        if isinstance(surface, str) and isinstance(value, int | float):
            elapsed[surface] = float(value)
    return elapsed


def phase_states_from_score_payload(
    score_payload: dict[str, Any],
    *,
    run_results: list[dict[str, Any]],
) -> dict[str, Any]:
    outputs = score_payload.get("outputs") if isinstance(score_payload.get("outputs"), dict) else {}
    elapsed = run_elapsed_by_surface(run_results)
    states: dict[str, Any] = {}
    for surface in ("overall", "upperbound", "random"):
        output_payload = outputs.get(surface) if isinstance(outputs.get(surface), dict) else {}
        status = phase_status(str(output_payload.get("status") or "missing"))
        progress = output_payload.get("progress") if isinstance(output_payload.get("progress"), dict) else {}
        state = {
            "status": status,
            "elapsed_ms": elapsed.get(surface),
            "incomplete_reason": phase_incomplete_reason(surface, status),
        }
        state.update(progress)
        states[surface] = state
    return states


def fixed_arm_execution_status(
    *,
    all_scores_present: bool,
    bounded_subset: bool,
    has_partial_outputs: bool,
    run_results: list[dict[str, Any]],
) -> str:
    if all_scores_present and bounded_subset:
        return "complete_bounded_subset_outputs_not_full_v1_base"
    if all_scores_present:
        return "complete_full_fixed_arm_outputs"
    if has_partial_outputs:
        return "partial_resumable_outputs"
    if run_results:
        return "incomplete_after_surface_run"
    return "planned_missing_outputs"


def build_fixed_arm_execution(
    *,
    status: str,
    arm: str,
    provider: str,
    dataset: dict[str, Any],
    score_payload: dict[str, Any],
    run_results: list[dict[str, Any]],
    resume: bool,
    elapsed_ms: float,
) -> dict[str, Any]:
    phase_states = phase_states_from_score_payload(score_payload, run_results=run_results)
    skipped = [result["surface"] for result in run_results if result.get("status") == "skipped_complete"]
    surface_elapsed = {
        result["surface"]: result["elapsed_ms"]
        for result in run_results
        if isinstance(result.get("surface"), str) and isinstance(result.get("elapsed_ms"), int | float)
    }
    return {
        "status": status,
        "arm": arm,
        "provider": provider,
        "dataset": dataset,
        "phase_states": phase_states,
        "resume": {
            "requested": resume,
            "skipped_surfaces": skipped,
            "boundary": (
                "Resume skips surfaces whose official summary artifacts are already complete; "
                "partial official surfaces are reported for manual continuation rather than "
                "treated as upstream incremental checkpoints."
            ),
        },
        "cost_latency": {
            "provider_cost_status": "unavailable",
            "unavailable_reason": "provider_usage_metadata_not_extracted_from_official_outputs",
            "latency_status": "process_elapsed_only",
            "process_elapsed_ms": elapsed_ms,
            "surface_elapsed_ms": surface_elapsed,
        },
        "checkpoint": {"status": "not_requested"},
    }


def checkpoint_payload(
    *,
    schema_version: int,
    generated_at: str,
    fixed_arm_execution: dict[str, Any],
    claim_boundary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "kind": "aippocampus_amemgym_official_runner_checkpoint",
        "generated_at": generated_at,
        "status": fixed_arm_execution["status"],
        "arm": fixed_arm_execution["arm"],
        "provider": fixed_arm_execution["provider"],
        "dataset": fixed_arm_execution["dataset"],
        "phase_states": fixed_arm_execution["phase_states"],
        "resume": fixed_arm_execution["resume"],
        "cost_latency": fixed_arm_execution["cost_latency"],
        "claim_boundary": {
            "official_amemgym_score": claim_boundary["official_amemgym_score"],
            "provider_score_kind": claim_boundary["provider_score_kind"],
        },
        "privacy_boundary": {
            "raw_text_emitted": False,
            "absolute_paths_emitted": False,
            "provider_credentials_emitted": False,
            "raw_official_outputs_committed": False,
        },
    }


def write_checkpoint_file(
    checkpoint_path: Path | str,
    *,
    schema_version: int,
    generated_at: str,
    fixed_arm_execution: dict[str, Any],
    claim_boundary: dict[str, Any],
) -> dict[str, Any]:
    payload = checkpoint_payload(
        schema_version=schema_version,
        generated_at=generated_at,
        fixed_arm_execution=fixed_arm_execution,
        claim_boundary=claim_boundary,
    )
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path = Path(checkpoint_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {
        "status": "written",
        "label": safe_path_label(path),
        "content_sha1": sha1_short(text),
    }


def aippocampus_official_adapter_protocol(
    *,
    official_native_arm: str,
    clean_source_arm: str,
    semantic_sidecar_arm: str,
) -> dict[str, Any]:
    return {
        "host": "official_amemgym_overall_runner",
        "why_base_agent_is_not_enough": (
            "A BaseAgent wrapper that only writes messages and searches files is "
            "a clean-source retrieval baseline, not the full AIppocampus memory system."
        ),
        "lifecycle_surrogates": [
            {
                "aippocampus_phase": "host_visible_message_capture",
                "official_runner_surface": "BaseAgent.act/add_msgs",
                "purpose": "record AMemGym user/assistant visible turns without reading gold state",
            },
            {
                "aippocampus_phase": "lifecycle_refresh",
                "official_runner_surface": "BaseAgent.save_state at each period checkpoint",
                "purpose": "build generic-jsonl, clean source, and source index before scoring",
            },
            {
                "aippocampus_phase": "background_worker_precache",
                "official_runner_surface": "adapter pre-score preparation inside the ignored agent state directory",
                "purpose": (
                    "materialize route cache, working-memory, semantic triggers, or semantic "
                    "sidecars before answer_question; cold worker cost is reported separately"
                ),
            },
            {
                "aippocampus_phase": "foreground_recall",
                "official_runner_surface": "BaseAgent.answer_question",
                "purpose": "consume prepared artifacts, reopen clean-source snippets, and ask the same llm_config model",
            },
        ],
        "arms": {
            official_native_arm: {
                "official_comparable": True,
                "memory_surface": "full AMemGym msg_history in model context",
            },
            clean_source_arm: {
                "official_comparable": True,
                "memory_surface": "generic-jsonl -> clean-source exact/source-index retrieval",
                "claim_level": "file_retrieval_baseline",
                "not_full_aippocampus": True,
            },
            semantic_sidecar_arm: {
                "official_comparable": True,
                "memory_surface": "prepared clean source plus working-memory/semantic sidecar navigation with source reopen",
                "claim_level": "full_arm_only_when_precache_artifacts_are_present",
                "missing_worker_degrades_to": clean_source_arm,
            },
        },
        "must_preserve_for_score_comparability": [
            "same AMemGym overall prompt, parser, answer choices, random fallback, and metric code",
            "same llm_config model, temperature, max_tokens, provider base URL, and credential injection shape",
            "answer_question must not mutate memory state",
            "adapter must not read period state, answer_choice state, required_info gold labels, or real user memory",
            "each AMemGym item and period uses only its own ignored local agent state",
        ],
        "precache_claim_gate": {
            "clean_source_only_required": ["transcript.jsonl", "clean-source/messages.jsonl", "source-index/source_index.sqlite"],
            "semantic_sidecar_required": [
                "clean-source/messages.jsonl",
                "source-index/source_index.sqlite",
                "working_memory.jsonl or semantic-scope-labels.jsonl or semantic_triggers.jsonl",
            ],
            "cold_start_cost": "reported separately from warmed answer quality",
        },
    }
