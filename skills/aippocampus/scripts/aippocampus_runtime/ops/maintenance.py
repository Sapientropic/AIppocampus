#!/usr/bin/env python3
"""Threshold-style maintenance hook for aippocampus."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from aippocampus_runtime.privacy import LOCAL_PATH_REDACTION

SCRIPT_DIR = Path(__file__).resolve().parents[2]


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


def failure_result(
    action_id: str, cmd: list[str], returncode: int, stdout: str = "", stderr: str = ""
) -> dict:
    message = (stderr or stdout or "").strip()
    return {
        "id": action_id,
        "command": cmd,
        "returncode": returncode,
        "message": message[:1000],
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
    message = (stderr or stdout or "").strip()
    return {
        "id": "activation_payload_compaction",
        "command": public_activation_payload_compaction_command(cmd),
        "returncode": returncode,
        "message": message[:1000],
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


def summary_payload(result: dict) -> dict:
    return {
        "kind": "aippocampus_maintenance_summary",
        "ok": result.get("maintenance_status") in {"ok", "degraded"},
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
        "remaining_recommended_actions": [
            {
                "id": item.get("id"),
                "severity": item.get("severity"),
                "reason": item.get("reason"),
            }
            for item in (result.get("remaining_recommended_actions") or [])[:8]
        ],
        "full_audit_available": True,
        "full_audit_flag": "--json",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aippocampus maintenance")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument(
        "--append-checkpoint",
        action="store_true",
        help="Append checkpoint candidates instead of only suggesting them.",
    )
    parser.add_argument(
        "--no-refresh-cognitive-map",
        action="store_true",
        help="Do not refresh the cognitive-map sidecar from existing subconscious findings.",
    )
    parser.add_argument(
        "--no-refresh-graphify",
        action="store_true",
        help="Do not refresh the prepared Graphify corpus.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Preserve legacy strict behavior: stop on the first failed action.",
    )
    parser.add_argument(
        "--activation-dead-letter-manifest",
        help="Explicit dead-letter apply manifest for activation payload compaction.",
    )
    parser.add_argument("--activation-ambient-cache")
    parser.add_argument("--activation-working-memory")
    parser.add_argument("--activation-semantic-triggers")
    parser.add_argument("--activation-active-recall-locks")
    parser.add_argument("--activation-compacted-at")
    parser.add_argument(
        "--apply-activation-payload-compaction",
        action="store_true",
        help="Allow activation owner files to be rewritten; dry-run is the default.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--summary-json",
        action="store_true",
        help="Emit a bounded foreground summary instead of the full maintenance audit payload.",
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
    if args.fail_fast:
        health = run_json(health_cmd)
        action_results.append({"id": "health_initial", "result": health})
    else:
        code, health_payload, stdout, stderr = run_json_checked(health_cmd)
        if code != 0 or health_payload is None:
            action_failures.append(failure_result("health_initial", health_cmd, code, stdout, stderr))
            health = {}
        else:
            health = health_payload
            action_results.append({"id": "health_initial", "result": health})

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
        cmd = [sys.executable, "-m", "aippocampus_runtime.recall.index_builder", "--cwd", str(cwd)]
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
                        "-m", "aippocampus_runtime.recall.index_builder",
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
        cmd = [
            sys.executable,
            "-m", "aippocampus_runtime.ops.graphify_corpus",
            "--cwd",
            str(cwd),
            "--json",
        ]
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
