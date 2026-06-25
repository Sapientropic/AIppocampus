#!/usr/bin/env python3
"""Threshold-style maintenance hook for aippocampus."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from aippocampus_runtime import health as health_runtime
from aippocampus_runtime.ops.activation_compaction_cli import (
    activation_payload_compaction_cmd,
    activation_payload_compaction_failure_result,
    public_activation_payload_compaction_command,
)
from aippocampus_runtime.ops.interrupted_write_recovery import (
    CLEANUP_INTERRUPTED_WRITES_COMMAND,
    _registry_root_from_runtime_health,
    attach_interrupted_write_recovery,
    cleanup_interrupted_write_artifacts,
)
from aippocampus_runtime.ops.maintenance_projection import (
    health_maintenance_status,
    plan_payload,
    summary_payload,
)
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)

SCRIPT_DIR = Path(__file__).resolve().parents[2]
READ_ONLY_OPERATIONS = {"status", "summary", "plan"}
APPLY_OPERATIONS = {"apply", "run"}


def run_json(cmd: list[str]) -> dict:
    proc = subprocess.run(
        cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)
    return json.loads(proc.stdout)


def run_json_checked(cmd: list[str]) -> tuple[int, dict | None, str, str]:
    proc = subprocess.run(
        cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False
    )
    if proc.returncode != 0:
        return proc.returncode, None, proc.stdout, proc.stderr
    try:
        return proc.returncode, json.loads(proc.stdout), proc.stdout, proc.stderr
    except json.JSONDecodeError as exc:
        return 1, None, proc.stdout, f"invalid JSON output: {exc}"


def read_only_health_probe(cwd: Path) -> tuple[int, dict | None, str]:
    """Return the foreground maintenance health source without full diagnostics.

    Status/summary cards are used while an agent is deciding whether ordinary
    recall can continue. They must not wait behind the operator-only probes
    (storage pressure scans, background cognition health, path-heavy audits)
    that `maintenance apply/run` still need before and after writes.
    """

    try:
        return (
            0,
            health_runtime.build_health_report(health_runtime.HealthOptions(cwd=cwd)),
            "",
        )
    except FileNotFoundError as exc:
        return 0, health_runtime.missing_rollout_health_report(cwd, exc), ""
    except Exception as exc:  # pragma: no cover - defensive fail-open for CLI foreground card
        return 1, None, public_failure_message(stderr=str(exc))


def run_text(cmd: list[str]) -> str:
    proc = subprocess.run(
        cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout or proc.stderr)
    return proc.stdout


def run_text_checked(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False
    )
    return proc.returncode, proc.stdout, proc.stderr


def has_action(health: dict, action_id: str) -> bool:
    return any(item.get("id") == action_id for item in health.get("recommended_actions", []))


def command_result(action_id: str, cmd: list[str], returncode: int) -> dict:
    return {"id": action_id, "command": cmd, "returncode": returncode}


def public_failure_message(stdout: str = "", stderr: str = "") -> str:
    return str(redact_sensitive_values(redact_private_paths((stderr or stdout or "").strip())))[:1000]


def failure_result(
    action_id: str, cmd: list[str], returncode: int, stdout: str = "", stderr: str = ""
) -> dict:
    return {
        "id": action_id,
        "command": cmd,
        "returncode": returncode,
        "message": public_failure_message(stdout, stderr),
    }


def maintenance_status(
    *, failures: list[dict], skipped: list[dict], health_final: dict | None
) -> str:
    if failures and health_final is None:
        return "failed"
    if failures:
        return "blocked" if skipped else "degraded"
    if health_final:
        status = health_maintenance_status(health_final)
        if status != "ok":
            return status
    return "ok"


def failed_action_ids(failures: list[dict]) -> set[str]:
    return {str(item.get("id") or "") for item in failures}


def index_builder_cmd(cwd: Path) -> list[str]:
    return [sys.executable, "-m", "aippocampus_runtime.recall.index_builder", "--cwd", str(cwd)]


def graphify_corpus_cmd(cwd: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "aippocampus_runtime.ops.graphify_corpus",
        "--cwd",
        str(cwd),
        "--json",
    ]


def main(argv: list[str] | None = None) -> int:
    """aippocampus-stage-map: parse intent -> probe health -> run explicit actions -> recheck health -> render result."""

    parser = argparse.ArgumentParser(
        prog="aippocampus maintenance",
        description=(
            "Plan or apply bounded local maintenance.\n\n"
            "Safe first steps:\n"
            "  aippocampus maintenance status --json\n"
            "  aippocampus maintenance summary --json\n\n"
            "Write mode is explicit:\n"
            "  aippocampus maintenance apply --summary-json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "operation",
        nargs="?",
        choices=sorted(READ_ONLY_OPERATIONS | APPLY_OPERATIONS),
        help="status/summary/plan are read-only; apply/run refresh generated artifacts.",
    )
    foreground_group = parser.add_argument_group("Foreground read-only/status options")
    apply_group = parser.add_argument_group("Explicit apply/run options")
    activation_group = parser.add_argument_group("Advanced operator activation compaction")
    foreground_group.add_argument("--cwd", default=os.getcwd())
    apply_group.add_argument(
        "--append-checkpoint",
        action="store_true",
        help="Append checkpoint candidates instead of only suggesting them.",
    )
    apply_group.add_argument(
        "--no-refresh-cognitive-map",
        action="store_true",
        help="Do not refresh the cognitive-map sidecar from existing subconscious findings.",
    )
    apply_group.add_argument(
        "--no-refresh-graphify",
        action="store_true",
        help="Do not refresh the prepared Graphify corpus.",
    )
    apply_group.add_argument(
        "--fail-fast",
        action="store_true",
        help="Preserve legacy strict behavior: stop on the first failed action.",
    )
    apply_group.add_argument(
        "--cleanup-interrupted-writes",
        action="store_true",
        help="Delete stale AIppocampus-owned tmp artifacts after reviewing maintenance status.",
    )
    activation_group.add_argument(
        "--activation-dead-letter-manifest",
        help=argparse.SUPPRESS,
    )
    activation_group.add_argument("--activation-ambient-cache", help=argparse.SUPPRESS)
    activation_group.add_argument("--activation-working-memory", help=argparse.SUPPRESS)
    activation_group.add_argument("--activation-semantic-triggers", help=argparse.SUPPRESS)
    activation_group.add_argument("--activation-active-recall-locks", help=argparse.SUPPRESS)
    activation_group.add_argument("--activation-compacted-at", help=argparse.SUPPRESS)
    activation_group.add_argument(
        "--apply-activation-payload-compaction",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    foreground_group.add_argument("--json", action="store_true", dest="json_output")
    foreground_group.add_argument(
        "--summary-json",
        action="store_true",
        help=(
            "Emit a foreground summary. Without apply/run this is read-only; with "
            "apply/run it summarizes the executed maintenance actions."
        ),
    )
    foreground_group.add_argument(
        "--plan",
        "--dry-run",
        action="store_true",
        dest="plan",
        help="No-write preview of health-driven maintenance actions.",
    )
    args = parser.parse_args(argv)

    cwd = Path(args.cwd).resolve()
    action_results: list[dict] = []
    action_failures: list[dict] = []
    skipped_due_to_failure: list[dict] = []

    operation = args.operation or ("summary" if args.summary_json else "status")
    read_only = args.plan or operation in READ_ONLY_OPERATIONS
    if read_only:
        initial_health_returncode, health, initial_health_error = read_only_health_probe(cwd)
        if initial_health_returncode != 0 or health is None:
            action_failures.append(
                {
                    "id": "health_initial",
                    "command": ["aippocampus", "health", "--json"],
                    "returncode": initial_health_returncode,
                    "message": initial_health_error,
                }
            )
        else:
            health = attach_interrupted_write_recovery(health)
            action_results.append({"id": "health_initial", "result": health})
        mode = "plan" if args.plan or operation == "plan" else operation
        payload = plan_payload(
            cwd=cwd,
            health=health,
            health_returncode=initial_health_returncode,
            health_error=initial_health_error,
            refresh_cognitive_map=not args.no_refresh_cognitive_map,
            refresh_graphify=not args.no_refresh_graphify,
            mode=mode,
        )
        if args.json_output or args.summary_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"maintenance {payload['mode']} for {payload['cwd_label']}: no writes")
            print(f"would run: {', '.join(payload['would_run_action_ids']) or 'nothing'}")
            print(f"next: {payload['apply_command']}")
        return 0 if payload["command_ok"] else 1

    health_cmd = [
        sys.executable,
        "-m", "aippocampus_runtime.health",
        "--cwd",
        str(cwd),
        "--detail",
        "full",
        "--json",
    ]
    initial_health_returncode = 0
    initial_health_error = ""
    registry_root = _registry_root_from_runtime_health(cwd) if args.cleanup_interrupted_writes else None
    if args.fail_fast:
        health = run_json(health_cmd)
        health = attach_interrupted_write_recovery(health, registry_root=registry_root) or health
        action_results.append({"id": "health_initial", "result": health})
    else:
        code, health_payload, stdout, stderr = run_json_checked(health_cmd)
        initial_health_returncode = code
        initial_health_error = (stderr or stdout or "").strip()
        if code != 0 or health_payload is None:
            action_failures.append(failure_result("health_initial", health_cmd, code, stdout, stderr))
            health = {}
        else:
            health = (
                attach_interrupted_write_recovery(health_payload, registry_root=registry_root)
                or health_payload
            )
            action_results.append({"id": "health_initial", "result": health})

    if args.cleanup_interrupted_writes:
        cleanup = cleanup_interrupted_write_artifacts(
            registry_root=registry_root,
            projected_health=health if isinstance(health, dict) else None,
        )
        action_results.append(
            {
                **command_result(
                    "cleanup_interrupted_writes",
                    CLEANUP_INTERRUPTED_WRITES_COMMAND,
                    0 if cleanup.get("ok") else 1,
                ),
                "result": cleanup,
            }
        )
        if not cleanup.get("ok"):
            action_failures.append(
                {
                    "id": "cleanup_interrupted_writes",
                    "command": [
                        "aippocampus",
                        "maintenance",
                        "apply",
                        "--cleanup-interrupted-writes",
                        "--summary-json",
                    ],
                    "returncode": 1,
                    "message": "One or more stale AIppocampus tmp artifacts could not be removed.",
                }
            )
        # This flag is a targeted recovery action emitted by maintenance
        # status. Do not let it implicitly run the broader health-driven
        # generated-artifact refresh queue; users can run plain
        # `maintenance apply` when they want that heavier pass.
        health = {**health, "recommended_actions": []} if isinstance(health, dict) else {}
        args.no_refresh_cognitive_map = True
        args.no_refresh_graphify = True

    if has_action(health, "build_clean_source"):
        cmd = [
            sys.executable,
            "-m",
            "aippocampus_runtime.source.clean_source",
            "--cwd",
            str(cwd),
            "--json",
        ]
        if args.fail_fast:
            clean_source = run_json(cmd)
            action_results.append({"id": "build_clean_source", "result": clean_source})
            health = run_json(health_cmd)
        else:
            code, clean_source_payload, stdout, stderr = run_json_checked(cmd)
            if code == 0 and clean_source_payload is not None:
                action_results.append(
                    {
                        **command_result("build_clean_source", cmd, code),
                        "result": clean_source_payload,
                    }
                )
                code, health_payload, health_stdout, health_stderr = run_json_checked(health_cmd)
                if code == 0 and health_payload is not None:
                    health = (
                        attach_interrupted_write_recovery(
                            health_payload,
                            registry_root=registry_root,
                        )
                        or health_payload
                    )
                else:
                    action_failures.append(
                        failure_result(
                            "health_after_build_clean_source",
                            health_cmd,
                            code,
                            health_stdout,
                            health_stderr,
                        )
                    )
            else:
                action_failures.append(
                    failure_result("build_clean_source", cmd, code, stdout, stderr)
                )

    if has_action(health, "build_index") and "build_clean_source" not in failed_action_ids(action_failures):
        cmd = index_builder_cmd(cwd)
        if args.fail_fast:
            out = run_text(cmd)
            action_results.append({"id": "build_index", "output": out.strip()})
            health = run_json(health_cmd)
        else:
            code, stdout, stderr = run_text_checked(cmd)
            if code == 0:
                action_results.append(
                    {**command_result("build_index", cmd, code), "output": stdout.strip()}
                )
                code, health_payload, health_stdout, health_stderr = run_json_checked(health_cmd)
                if code == 0 and health_payload is not None:
                    health = (
                        attach_interrupted_write_recovery(
                            health_payload,
                            registry_root=registry_root,
                        )
                        or health_payload
                    )
                else:
                    action_failures.append(
                        failure_result("health_after_build_index", health_cmd, code, health_stdout, health_stderr)
                    )
            else:
                action_failures.append(failure_result("build_index", cmd, code, stdout, stderr))
    elif has_action(health, "build_index") and "build_clean_source" in failed_action_ids(action_failures):
        skipped_due_to_failure.append(
            {
                "id": "build_index",
                "reason": "depends_on_failed_build_clean_source",
            }
        )

    if has_action(health, "checkpoint"):
        cmd = [sys.executable, "-m", "aippocampus_runtime.artifacts.checkpoint", "--cwd", str(cwd), "--json"]
        if args.append_checkpoint:
            cmd.append("--append")
        if args.fail_fast:
            checkpoint = run_json(cmd)
            action_results.append(
                {"id": "checkpoint", "appended": args.append_checkpoint, "result": checkpoint}
            )
            health = run_json(health_cmd)
            if args.append_checkpoint:
                run_text([sys.executable, "-m", "aippocampus_runtime.recall.index_builder", "--cwd", str(cwd)])
                health = run_json(health_cmd)
        else:
            code, checkpoint_payload, stdout, stderr = run_json_checked(cmd)
            if code == 0 and checkpoint_payload is not None:
                action_results.append(
                    {
                        **command_result("checkpoint", cmd, code),
                        "appended": args.append_checkpoint,
                        "result": checkpoint_payload,
                    }
                )
                code, health_payload, health_stdout, health_stderr = run_json_checked(health_cmd)
                if code == 0 and health_payload is not None:
                    health = (
                        attach_interrupted_write_recovery(
                            health_payload,
                            registry_root=registry_root,
                        )
                        or health_payload
                    )
                else:
                    action_failures.append(
                        failure_result("health_after_checkpoint", health_cmd, code, health_stdout, health_stderr)
                    )
                if args.append_checkpoint:
                    rebuild_cmd = [
                        sys.executable,
                        "-m",
                        "aippocampus_runtime.recall.index_builder",
                        "--cwd",
                        str(cwd),
                    ]
                    code, rebuild_stdout, rebuild_stderr = run_text_checked(rebuild_cmd)
                    if code == 0:
                        action_results.append(
                            {
                                **command_result("build_index_after_checkpoint", rebuild_cmd, code),
                                "output": rebuild_stdout.strip(),
                            }
                        )
                        code, health_payload, health_stdout, health_stderr = run_json_checked(health_cmd)
                        if code == 0 and health_payload is not None:
                            health = (
                                attach_interrupted_write_recovery(
                                    health_payload,
                                    registry_root=registry_root,
                                )
                                or health_payload
                            )
                        else:
                            action_failures.append(
                                failure_result(
                                    "health_after_checkpoint_index",
                                    health_cmd,
                                    code,
                                    health_stdout,
                                    health_stderr,
                                )
                            )
                    else:
                        action_failures.append(
                            failure_result("build_index_after_checkpoint", rebuild_cmd, code, rebuild_stdout, rebuild_stderr)
                        )
            else:
                action_failures.append(failure_result("checkpoint", cmd, code, stdout, stderr))

    if has_action(health, "build_segments"):
        # Segments are an acceleration layer over the same normalized transcript
        # as the main index. Build them after the main index/checkpoint pass so
        # shard metadata points at the latest anchors and message count.
        cmd = [sys.executable, "-m", "aippocampus_runtime.recall.segment_builder", "--cwd", str(cwd)]
        if args.fail_fast:
            out = run_text(cmd)
            action_results.append({"id": "build_segments", "output": out.strip()})
            health = run_json(health_cmd)
        else:
            code, stdout, stderr = run_text_checked(cmd)
            if code == 0:
                action_results.append(
                    {**command_result("build_segments", cmd, code), "output": stdout.strip()}
                )
                code, health_payload, health_stdout, health_stderr = run_json_checked(health_cmd)
                if code == 0 and health_payload is not None:
                    health = (
                        attach_interrupted_write_recovery(
                            health_payload,
                            registry_root=registry_root,
                        )
                        or health_payload
                    )
                else:
                    action_failures.append(
                        failure_result("health_after_build_segments", health_cmd, code, health_stdout, health_stderr)
                    )
            else:
                action_failures.append(failure_result("build_segments", cmd, code, stdout, stderr))

    if not args.no_refresh_cognitive_map:
        # Cognitive-map routes are produced by the detached subconscious layer;
        # maintenance only validates and materializes whatever staging already
        # exists, keeping this foreground pass model-free and hook-safe.
        cmd = [
            sys.executable,
            "-m", "aippocampus_runtime.navigation.cognitive_map",
            "--json",
        ]
        if args.fail_fast:
            cognitive_map = run_json(cmd)
            action_results.append({"id": "build_cognitive_map", "result": cognitive_map})
            health = run_json(health_cmd)
        else:
            code, cognitive_map_payload, stdout, stderr = run_json_checked(cmd)
            if code == 0 and cognitive_map_payload is not None:
                action_results.append(
                    {
                        **command_result("build_cognitive_map", cmd, code),
                        "result": cognitive_map_payload,
                    }
                )
                code, health_payload, health_stdout, health_stderr = run_json_checked(health_cmd)
                if code == 0 and health_payload is not None:
                    health = (
                        attach_interrupted_write_recovery(
                            health_payload,
                            registry_root=registry_root,
                        )
                        or health_payload
                    )
                else:
                    action_failures.append(
                        failure_result(
                            "health_after_build_cognitive_map",
                            health_cmd,
                            code,
                            health_stdout,
                            health_stderr,
                        )
                    )
            else:
                action_failures.append(failure_result("build_cognitive_map", cmd, code, stdout, stderr))

    if (
        has_action(health, "prepare_graphify_corpus")
        and not args.no_refresh_graphify
        and "build_index" not in failed_action_ids(action_failures)
    ):
        cmd = graphify_corpus_cmd(cwd)
        if args.fail_fast:
            graphify = run_json(cmd)
            action_results.append({"id": "prepare_graphify_corpus", "result": graphify})
            health = run_json(health_cmd)
        else:
            code, graphify_payload, stdout, stderr = run_json_checked(cmd)
            if code == 0 and graphify_payload is not None:
                action_results.append(
                    {
                        **command_result("prepare_graphify_corpus", cmd, code),
                        "result": graphify_payload,
                    }
                )
                code, health_payload, health_stdout, health_stderr = run_json_checked(health_cmd)
                if code == 0 and health_payload is not None:
                    health = (
                        attach_interrupted_write_recovery(
                            health_payload,
                            registry_root=registry_root,
                        )
                        or health_payload
                    )
                else:
                    action_failures.append(
                        failure_result(
                            "health_after_prepare_graphify_corpus",
                            health_cmd,
                            code,
                            health_stdout,
                            health_stderr,
                        )
                    )
            else:
                action_failures.append(
                    failure_result("prepare_graphify_corpus", cmd, code, stdout, stderr)
                )
    elif (
        has_action(health, "prepare_graphify_corpus")
        and not args.no_refresh_graphify
        and "build_index" in failed_action_ids(action_failures)
    ):
        skipped_due_to_failure.append(
            {
                "id": "prepare_graphify_corpus",
                "reason": "depends_on_failed_build_index",
            }
        )

    activation_compaction_cmd = activation_payload_compaction_cmd(args, cwd=cwd)
    if activation_compaction_cmd:
        if args.fail_fast:
            compaction = run_json(activation_compaction_cmd)
            action_results.append(
                {
                    "id": "activation_payload_compaction",
                    "command": public_activation_payload_compaction_command(
                        activation_compaction_cmd
                    ),
                    "returncode": 0,
                    "result": compaction,
                }
            )
        else:
            code, compaction_payload, stdout, stderr = run_json_checked(
                activation_compaction_cmd
            )
            if code == 0 and compaction_payload is not None:
                action_results.append(
                    {
                        "id": "activation_payload_compaction",
                        "command": public_activation_payload_compaction_command(
                            activation_compaction_cmd
                        ),
                        "returncode": code,
                        "result": compaction_payload,
                    }
                )
            else:
                action_failures.append(
                    activation_payload_compaction_failure_result(
                        activation_compaction_cmd,
                        code,
                        stdout,
                        stderr,
                    )
                )

    health_final = None
    if args.fail_fast:
        health_final = health
    else:
        code, health_payload, stdout, stderr = run_json_checked(health_cmd)
        if code == 0 and health_payload is not None:
            health_final = (
                attach_interrupted_write_recovery(health_payload, registry_root=registry_root)
                or health_payload
            )
        else:
            action_failures.append(failure_result("health_final", health_cmd, code, stdout, stderr))
    if (
        not args.fail_fast
        and not args.cleanup_interrupted_writes
        and health_final
        and has_action(health_final, "build_index")
        and "build_index" not in failed_action_ids(action_failures)
    ):
        # A live Codex thread can append enough rows during maintenance itself
        # to trip the bulk freshness threshold after the first index build.
        # One final catch-up keeps the front door from telling users to repeat
        # the same maintenance command immediately after it succeeded.
        catchup_cmd = index_builder_cmd(cwd)
        code, catchup_stdout, catchup_stderr = run_text_checked(catchup_cmd)
        if code == 0:
            action_results.append(
                {
                    **command_result("build_index_final_catchup", catchup_cmd, code),
                    "output": catchup_stdout.strip(),
                }
            )
            code, health_payload, health_stdout, health_stderr = run_json_checked(health_cmd)
            if code == 0 and health_payload is not None:
                health_final = (
                    attach_interrupted_write_recovery(
                        health_payload,
                        registry_root=registry_root,
                    )
                    or health_payload
                )
            else:
                action_failures.append(
                    failure_result(
                        "health_after_index_final_catchup",
                        health_cmd,
                        code,
                        health_stdout,
                        health_stderr,
                    )
                )
        else:
            action_failures.append(
                failure_result(
                    "build_index_final_catchup",
                    catchup_cmd,
                    code,
                    catchup_stdout,
                    catchup_stderr,
                )
            )
    if (
        not args.fail_fast
        and health_final
        and has_action(health_final, "prepare_graphify_corpus")
        and not args.no_refresh_graphify
        and "build_index" not in failed_action_ids(action_failures)
        and "build_index_final_catchup" not in failed_action_ids(action_failures)
    ):
        catchup_cmd = graphify_corpus_cmd(cwd)
        code, graphify_payload, stdout, stderr = run_json_checked(catchup_cmd)
        if code == 0 and graphify_payload is not None:
            action_results.append(
                {
                    **command_result("prepare_graphify_corpus_final_catchup", catchup_cmd, code),
                    "result": graphify_payload,
                }
            )
            code, health_payload, health_stdout, health_stderr = run_json_checked(health_cmd)
            if code == 0 and health_payload is not None:
                health_final = (
                    attach_interrupted_write_recovery(
                        health_payload,
                        registry_root=registry_root,
                    )
                    or health_payload
                )
            else:
                action_failures.append(
                    failure_result(
                        "health_after_graphify_final_catchup",
                        health_cmd,
                        code,
                        health_stdout,
                        health_stderr,
                    )
                )
        else:
            action_failures.append(
                failure_result(
                    "prepare_graphify_corpus_final_catchup",
                    catchup_cmd,
                    code,
                    stdout,
                    stderr,
                )
            )
    remaining = health_final.get("recommended_actions", []) if health_final else []
    result = {
        "cwd": LOCAL_PATH_REDACTION,
        "cwd_label": cwd.name or str(cwd),
        "actions": action_results,
        "action_results": action_results,
        "action_failures": action_failures,
        "skipped_due_to_failure": skipped_due_to_failure,
        "remaining_recommended_actions": remaining,
        "health_final": health_final,
        "maintenance_status": maintenance_status(
            failures=action_failures,
            skipped=skipped_due_to_failure,
            health_final=health_final,
        ),
    }
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.summary_json:
        print(json.dumps(summary_payload(result), ensure_ascii=False, indent=2))
    else:
        print(f"memory maintenance {result['maintenance_status']} for {cwd}")
        for item in action_results[1:]:
            print(f"- {item['id']}")
        if action_failures:
            print("failures:")
            for item in action_failures:
                print(f"- {item['id']}: {item['message']}")
        final_actions = remaining
        if final_actions:
            print("remaining recommendations:")
            for item in final_actions:
                print(f"- {item['id']} [{item['severity']}]: {item['reason']}")
        else:
            print("no remaining recommendations")
    return 0 if result["maintenance_status"] in {"ok", "degraded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
