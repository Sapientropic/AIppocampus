#!/usr/bin/env python3
"""Threshold-style maintenance hook for aippocampus."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)

SCRIPT_DIR = Path(__file__).resolve().parents[2]
READ_ONLY_OPERATIONS = {"status", "summary", "plan"}
APPLY_OPERATIONS = {"apply", "run"}
APPLY_SUMMARY_COMMAND = "aippocampus maintenance apply --summary-json"
STATUS_COMMAND = "aippocampus maintenance status --json"


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


def activation_payload_compaction_cmd(args: argparse.Namespace, *, cwd: Path) -> list[str] | None:
    if not args.activation_dead_letter_manifest:
        return None
    cmd = [
        sys.executable,
        "-m",
        "aippocampus_runtime.ops.activation_payload_compaction",
        "--dead-letter-manifest",
        str(_path_arg(args.activation_dead_letter_manifest, cwd=cwd)),
        "--json",
    ]
    for option, value in (
        ("--ambient-cache", args.activation_ambient_cache),
        ("--working-memory", args.activation_working_memory),
        ("--semantic-triggers", args.activation_semantic_triggers),
        ("--active-recall-locks", args.activation_active_recall_locks),
    ):
        if value:
            cmd.extend([option, str(_path_arg(value, cwd=cwd))])
    if args.activation_compacted_at:
        cmd.extend(["--compacted-at", str(args.activation_compacted_at)])
    if args.apply_activation_payload_compaction:
        cmd.append("--apply")
    return cmd


def _path_arg(value: str, *, cwd: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else cwd / path


def public_activation_payload_compaction_command(cmd: list[str]) -> list[str]:
    public_cmd = [
        "python",
        "-m",
        "aippocampus_runtime.ops.activation_payload_compaction",
        "--dead-letter-manifest",
        "<omitted>",
        "--json",
    ]
    for option in (
        "--ambient-cache",
        "--working-memory",
        "--semantic-triggers",
        "--active-recall-locks",
        "--compacted-at",
    ):
        if option in cmd:
            public_cmd.extend([option, "<omitted>"])
    if "--apply" in cmd:
        public_cmd.append("--apply")
    return public_cmd


def activation_payload_compaction_failure_result(
    cmd: list[str], returncode: int, stdout: str = "", stderr: str = ""
) -> dict:
    return {
        "id": "activation_payload_compaction",
        "command": public_activation_payload_compaction_command(cmd),
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
    if health_final and any(
        item.get("severity") in {"critical", "warning"}
        for item in health_final.get("recommended_actions", [])
    ):
        return "degraded"
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


def unique_action_ids(action_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for action_id in action_ids:
        clean = str(action_id or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def health_maintenance_status(health: dict | None) -> str:
    if not health:
        return "unavailable"
    status = str(health.get("status") or "").strip()
    if status:
        return status
    return "ok" if health.get("ok") else "attention_needed"


def health_maintenance_ok(health: dict | None) -> bool:
    if not health or not bool(health.get("ok")):
        return False
    return not any(
        item.get("severity") in {"critical", "warning"}
        for item in health.get("recommended_actions", []) or []
        if isinstance(item, dict)
    )


def public_action_command(action_id: str) -> str | None:
    if action_id == "checkpoint":
        return "aippocampus maintenance apply --append-checkpoint --summary-json"
    if action_id in {
        "build_clean_source",
        "build_index",
        "build_segments",
        "build_cognitive_map",
        "prepare_graphify_corpus",
    }:
        return APPLY_SUMMARY_COMMAND
    return None


def public_recommended_action(item: dict) -> dict:
    action_id = str(item.get("id") or "")
    result = {
        "id": action_id,
        "severity": item.get("severity"),
        "reason": item.get("reason"),
    }
    command = public_action_command(action_id)
    if command:
        result["command"] = command
    else:
        result["operator_boundary"] = "inspect the full audit before acting on this item"
    return {key: value for key, value in result.items() if value not in (None, "", [])}


def best_next_action(recommended: list[dict]) -> dict:
    if not recommended:
        return {
            "id": "continue",
            "decision": "continue",
            "reason": "No blocking maintenance action is currently recommended.",
        }
    severity_rank = {"critical": 0, "warning": 1, "info": 2, "suggestion": 3}
    ordered = sorted(
        recommended,
        key=lambda item: severity_rank.get(str(item.get("severity") or ""), 9),
    )
    action = public_recommended_action(ordered[0])
    action.setdefault("decision", "preview or apply the next maintenance action")
    return action


def user_impact(health: dict | None, recommended: list[dict]) -> dict:
    if health_maintenance_ok(health):
        return {
            "recall_usable": "yes",
            "can_continue_normally": True,
            "summary": "Source-backed recall/search can continue normally.",
        }
    blocking = [
        item
        for item in recommended
        if isinstance(item, dict) and item.get("severity") in {"critical", "warning"}
    ]
    if blocking:
        return {
            "recall_usable": "degraded",
            "can_continue_normally": False,
            "summary": (
                "Source-backed recall/search may be incomplete until the blocking "
                "maintenance action is applied."
            ),
        }
    return {
        "recall_usable": "yes_with_optional_maintenance",
        "can_continue_normally": True,
        "summary": "Core recall/search can continue; remaining items are optional upkeep.",
    }


def summary_payload(result: dict) -> dict:
    remaining = [
        public_recommended_action(item)
        for item in (result.get("remaining_recommended_actions") or [])[:8]
        if isinstance(item, dict)
    ]
    return {
        "kind": "aippocampus_maintenance_summary",
        "ok": result.get("maintenance_status") in {"ok", "degraded"},
        "mode": "applied",
        "read_only": False,
        "maintenance_status": result.get("maintenance_status"),
        "cwd": LOCAL_PATH_REDACTION,
        "cwd_label": result.get("cwd_label"),
        "action_count": len(result.get("action_results") or []),
        "failure_count": len(result.get("action_failures") or []),
        "skipped_count": len(result.get("skipped_due_to_failure") or []),
        "remaining_recommended_action_count": len(result.get("remaining_recommended_actions") or []),
        "action_ids": [item.get("id") for item in (result.get("action_results") or [])[:12]],
        "failure_samples": [
            {
                "id": item.get("id"),
                "returncode": item.get("returncode"),
                "message": item.get("message"),
            }
            for item in (result.get("action_failures") or [])[:5]
        ],
        "remaining_recommended_actions": remaining,
        "best_next_action": best_next_action(result.get("remaining_recommended_actions") or []),
        "user_impact": user_impact(
            result.get("health_final"),
            result.get("remaining_recommended_actions") or [],
        ),
        "full_audit_available": True,
        "full_audit_flag": "--json",
        "plan_first_command": STATUS_COMMAND,
        "agent_next_action": (
            "Use maintenance status/summary for a no-write card; use maintenance apply when "
            "the user intentionally wants local generated artifacts refreshed."
        ),
    }


def plan_payload(
    *,
    cwd: Path,
    health: dict | None,
    health_returncode: int,
    health_error: str = "",
    refresh_cognitive_map: bool,
    refresh_graphify: bool,
    mode: str = "plan",
) -> dict:
    recommended = list((health or {}).get("recommended_actions") or [])
    would_run_ids = [str(item.get("id") or "") for item in recommended if item.get("id")]
    if refresh_cognitive_map:
        would_run_ids.append("build_cognitive_map")
    if refresh_graphify and any(item.get("id") == "prepare_graphify_corpus" for item in recommended):
        would_run_ids.append("prepare_graphify_corpus")
    command_ok = health_returncode == 0 and health is not None
    maintenance_ok = command_ok and health_maintenance_ok(health)
    payload = {
        "kind": (
            "aippocampus_maintenance_summary"
            if mode == "summary"
            else "aippocampus_maintenance_plan"
        ),
        "ok": maintenance_ok,
        "command_ok": command_ok,
        "plan_generated": command_ok,
        "maintenance_ok": maintenance_ok,
        "maintenance_status": health_maintenance_status(health),
        "mode": mode,
        "read_only": True,
        "cwd": LOCAL_PATH_REDACTION,
        "cwd_label": cwd.name or str(cwd),
        "recommended_action_count": len(recommended),
        "would_run_action_ids": unique_action_ids(would_run_ids)[:16],
        "remaining_recommended_actions": [
            public_recommended_action(item)
            for item in recommended[:8]
            if isinstance(item, dict)
        ],
        "best_next_action": best_next_action(recommended),
        "user_impact": user_impact(health, recommended),
        "apply_command": APPLY_SUMMARY_COMMAND,
        "full_audit_available": True,
        "full_audit_flag": "--json",
        "full_audit_apply_command": "aippocampus maintenance apply --json",
        "privacy_boundary": {
            "local_paths_included": False,
            "writes_performed": False,
            "source_text_included": False,
        },
        "agent_next_action": (
            "If this plan matches the intended release gate, apply once with "
            "`aippocampus maintenance apply --summary-json`; do not repeat broad tests just to inspect status."
        ),
    }
    if not command_ok and health_error:
        payload["health_probe"] = {
            "returncode": health_returncode,
            "status": "failed",
            "message": health_error[:240],
        }
    return payload


def main(argv: list[str] | None = None) -> int:
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
    activation_group.add_argument(
        "--activation-dead-letter-manifest",
        help="Explicit dead-letter apply manifest for activation payload compaction.",
    )
    activation_group.add_argument("--activation-ambient-cache")
    activation_group.add_argument("--activation-working-memory")
    activation_group.add_argument("--activation-semantic-triggers")
    activation_group.add_argument("--activation-active-recall-locks")
    activation_group.add_argument("--activation-compacted-at")
    activation_group.add_argument(
        "--apply-activation-payload-compaction",
        action="store_true",
        help="Allow activation owner files to be rewritten; dry-run is the default.",
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

    health_cmd = [
        sys.executable,
        "-m", "aippocampus_runtime.health",
        "--cwd",
        str(cwd),
        "--json",
    ]
    initial_health_returncode = 0
    initial_health_error = ""
    if args.fail_fast:
        health = run_json(health_cmd)
        action_results.append({"id": "health_initial", "result": health})
    else:
        code, health_payload, stdout, stderr = run_json_checked(health_cmd)
        initial_health_returncode = code
        initial_health_error = (stderr or stdout or "").strip()
        if code != 0 or health_payload is None:
            action_failures.append(failure_result("health_initial", health_cmd, code, stdout, stderr))
            health = {}
        else:
            health = health_payload
            action_results.append({"id": "health_initial", "result": health})

    operation = args.operation or ("summary" if args.summary_json else "status")
    read_only = args.plan or operation in READ_ONLY_OPERATIONS
    if read_only:
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
                    health = health_payload
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
                    health = health_payload
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
                    health = health_payload
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
                            health = health_payload
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
                    health = health_payload
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
                    health = health_payload
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
                    health = health_payload
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
            health_final = health_payload
        else:
            action_failures.append(failure_result("health_final", health_cmd, code, stdout, stderr))
    if (
        not args.fail_fast
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
                health_final = health_payload
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
                health_final = health_payload
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
