"""CLI command helpers for activation payload compaction maintenance."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values


def _path_arg(value: str, *, cwd: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else cwd / path


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
        "message": str(
            redact_sensitive_values(redact_private_paths((stderr or stdout or "").strip()))
        )[:1000],
    }
