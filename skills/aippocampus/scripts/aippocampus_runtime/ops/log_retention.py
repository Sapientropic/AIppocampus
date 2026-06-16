#!/usr/bin/env python3
"""Bound local hook/background logs without exposing their contents."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from aippocampus_runtime.core import aippocampus_registry_dir

DEFAULT_MAX_LOG_BYTES = 8 * 1024 * 1024
DEFAULT_BACKUPS = 3
LOG_MAX_BYTES_ENV = "AIPPOCAMPUS_LOG_MAX_BYTES"
LOG_BACKUPS_ENV = "AIPPOCAMPUS_LOG_BACKUPS"
LOG_CHUNK_BYTES = 64 * 1024

KNOWN_LOG_RELATIVE_PATHS = (
    Path("logs") / "build_associations_hook.log",
    Path("logs") / "subconscious_scheduler_hook.log",
    Path("subconscious_scheduler.log"),
    Path("maintenance_hook.jsonl"),
    Path("aippocampus_prompt_hook.jsonl"),
)
LOG_DIR_SUFFIXES = {".log", ".jsonl"}


def _positive_int(value: Any, default: int, *, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= minimum else default


def retention_settings(
    *,
    max_bytes: int | None = None,
    backups: int | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, int]:
    values = os.environ if env is None else env
    resolved_max = (
        _positive_int(values.get(LOG_MAX_BYTES_ENV), DEFAULT_MAX_LOG_BYTES)
        if max_bytes is None
        else _positive_int(max_bytes, DEFAULT_MAX_LOG_BYTES)
    )
    resolved_backups = (
        _positive_int(values.get(LOG_BACKUPS_ENV), DEFAULT_BACKUPS, minimum=0)
        if backups is None
        else _positive_int(backups, DEFAULT_BACKUPS, minimum=0)
    )
    return resolved_max, resolved_backups


def _backup_path(path: Path, index: int) -> Path:
    return path.with_name(f"{path.name}.{index}.gz")


def _public_log_item(path: Path, root: Path, *, max_bytes: int, error: str | None = None) -> dict[str, Any]:
    try:
        size = path.stat().st_size if path.exists() else 0
    except OSError:
        size = 0
        error = error or "stat_failed"
    try:
        artifact_rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        artifact_rel = path.name
    item: dict[str, Any] = {
        "artifact_name": path.name,
        "artifact_rel": artifact_rel,
        "size_bytes": size,
        "max_bytes": max_bytes,
        "oversized": size >= max_bytes,
    }
    if error:
        item["error"] = error
    return item


def iter_known_logs(root: str | Path) -> Iterable[Path]:
    registry_root = Path(root)
    seen: set[Path] = set()
    for relative in KNOWN_LOG_RELATIVE_PATHS:
        path = registry_root / relative
        if path not in seen:
            seen.add(path)
            yield path
    logs_dir = registry_root / "logs"
    if not logs_dir.exists():
        return
    try:
        candidates = sorted(logs_dir.iterdir(), key=lambda item: item.name)
    except OSError:
        return
    for path in candidates:
        if not path.is_file() or path.suffix not in LOG_DIR_SUFFIXES:
            continue
        if path in seen:
            continue
        seen.add(path)
        yield path


def log_health_report(
    root: str | Path | None = None,
    *,
    max_bytes: int | None = None,
    backups: int | None = None,
) -> dict[str, Any]:
    registry_root = Path(root) if root is not None else aippocampus_registry_dir()
    resolved_max, resolved_backups = retention_settings(max_bytes=max_bytes, backups=backups)
    items = [
        _public_log_item(path, registry_root, max_bytes=resolved_max)
        for path in iter_known_logs(registry_root)
        if path.exists()
    ]
    items.sort(key=lambda item: (not item["oversized"], -int(item["size_bytes"]), item["artifact_rel"]))
    oversized_count = sum(1 for item in items if item["oversized"])
    return {
        "available": True,
        "max_bytes": resolved_max,
        "backups": resolved_backups,
        "oversized": oversized_count > 0,
        "oversized_count": oversized_count,
        "total_bytes": sum(int(item["size_bytes"]) for item in items),
        "items": items,
        "remediation_command": "aippocampus logs rotate --dry-run",
        "privacy_boundary": {
            "log_contents_emitted": False,
            "local_paths_emitted": False,
            "raw_prompt_or_source_snippets_emitted": False,
        },
    }


def add_health_action(
    actions: list[dict[str, Any]],
    root: str | Path,
    *,
    max_bytes: int | None = None,
) -> dict[str, Any]:
    logs = log_health_report(root, max_bytes=max_bytes)
    if logs["oversized"]:
        actions.append(
            {
                "id": "rotate_logs",
                "severity": "warning",
                "reason": f"{logs['oversized_count']} AIppocampus log artifact(s) exceed the retention threshold",
                "command": "aippocampus logs rotate --dry-run",
            }
        )
    return logs


def rotate_log_if_needed(
    path: str | Path,
    *,
    max_bytes: int | None = None,
    backups: int | None = None,
) -> dict[str, Any]:
    log = Path(path)
    resolved_max, resolved_backups = retention_settings(max_bytes=max_bytes, backups=backups)
    root = log.parent.parent if log.parent.name == "logs" else log.parent
    report = _public_log_item(log, root, max_bytes=resolved_max)
    report.update({"rotated": False, "backups": resolved_backups})
    if not log.exists():
        report["skipped"] = "missing"
        return report
    if report["size_bytes"] < resolved_max:
        report["skipped"] = "below_threshold"
        return report

    tmp = _backup_path(log, 1).with_suffix(".gz.tmp")
    try:
        if resolved_backups <= 0:
            log.unlink()
            report.update({"rotated": True, "dropped": True, "size_bytes": 0})
            return report

        oldest = _backup_path(log, resolved_backups)
        if oldest.exists():
            oldest.unlink()
        for index in range(resolved_backups - 1, 0, -1):
            src = _backup_path(log, index)
            dst = _backup_path(log, index + 1)
            if src.exists():
                if dst.exists():
                    dst.unlink()
                src.replace(dst)

        tmp.parent.mkdir(parents=True, exist_ok=True)
        with log.open("rb") as src_fh, gzip.open(tmp, "wb") as dst_fh:
            shutil.copyfileobj(src_fh, dst_fh)
        tmp.replace(_backup_path(log, 1))
        log.unlink()
        report.update(
            {
                "rotated": True,
                "backup_name": _backup_path(log, 1).name,
                "size_bytes": 0,
            }
        )
        return report
    except OSError as exc:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        report.update({"error": type(exc).__name__, "message": str(exc)[:200]})
        return report


def append_bytes_with_rotation(
    path: str | Path,
    data: bytes,
    *,
    max_bytes: int | None = None,
    backups: int | None = None,
) -> dict[str, Any]:
    log = Path(path)
    resolved_max, resolved_backups = retention_settings(max_bytes=max_bytes, backups=backups)
    log.parent.mkdir(parents=True, exist_ok=True)
    rotations: list[dict[str, Any]] = []
    view = memoryview(data)
    written = 0
    while view:
        if log.exists():
            try:
                current_size = log.stat().st_size
            except OSError:
                current_size = 0
            if current_size >= resolved_max:
                rotation = rotate_log_if_needed(
                    log, max_bytes=resolved_max, backups=resolved_backups
                )
                rotations.append(rotation)
                try:
                    current_size = log.stat().st_size if log.exists() else 0
                except OSError:
                    current_size = resolved_max
                if rotation.get("error") or current_size >= resolved_max:
                    return {
                        "written_bytes": written,
                        "dropped_bytes": len(view),
                        "rotations": [
                            item
                            for item in rotations
                            if item.get("rotated") or item.get("error")
                        ],
                        "artifact_name": log.name,
                        "error": rotation.get("error") or "rotation_failed",
                    }
        else:
            current_size = 0
        allowance = max(1, resolved_max - current_size)
        chunk = view[:allowance]
        with log.open("ab") as fh:
            fh.write(chunk)
        written += len(chunk)
        view = view[allowance:]
        if view:
            rotations.append(
                rotate_log_if_needed(log, max_bytes=resolved_max, backups=resolved_backups)
            )
    return {
        "written_bytes": written,
        "rotations": [item for item in rotations if item.get("rotated") or item.get("error")],
        "artifact_name": log.name,
    }


def append_text_with_rotation(
    path: str | Path,
    text: str,
    *,
    encoding: str = "utf-8",
    max_bytes: int | None = None,
    backups: int | None = None,
) -> dict[str, Any]:
    return append_bytes_with_rotation(
        path,
        text.encode(encoding, errors="replace"),
        max_bytes=max_bytes,
        backups=backups,
    )


def logged_subprocess_cmd(cmd: list[str], *, log: str | Path, cwd: str | Path | None = None) -> list[str]:
    args = [
        sys.executable,
        "-m",
        "aippocampus_runtime.ops.log_retention",
        "run",
        "--log",
        str(log),
    ]
    if cwd is not None:
        args.extend(["--cwd", str(cwd)])
    return [*args, "--", *cmd]


def run_command_with_rotating_log(
    cmd: list[str],
    *,
    log: str | Path,
    cwd: str | Path | None = None,
    max_bytes: int | None = None,
    backups: int | None = None,
) -> int:
    log_path = Path(log)
    rotate_log_if_needed(log_path, max_bytes=max_bytes, backups=backups)
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd is not None else None,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert proc.stdout is not None
    try:
        while True:
            chunk = proc.stdout.read(LOG_CHUNK_BYTES)
            if not chunk:
                break
            append_bytes_with_rotation(log_path, chunk, max_bytes=max_bytes, backups=backups)
    finally:
        proc.stdout.close()
    return int(proc.wait())


def rotate_known_logs(
    root: str | Path | None = None,
    *,
    max_bytes: int | None = None,
    backups: int | None = None,
) -> dict[str, Any]:
    registry_root = Path(root) if root is not None else aippocampus_registry_dir()
    resolved_max, resolved_backups = retention_settings(max_bytes=max_bytes, backups=backups)
    results = [
        rotate_log_if_needed(path, max_bytes=resolved_max, backups=resolved_backups)
        for path in iter_known_logs(registry_root)
        if path.exists()
    ]
    return {
        "ok": not any(item.get("error") for item in results),
        "rotated_count": sum(1 for item in results if item.get("rotated")),
        "items": results,
        "health": log_health_report(registry_root, max_bytes=resolved_max, backups=resolved_backups),
    }


def rotation_plan(
    root: str | Path | None = None,
    *,
    max_bytes: int | None = None,
    backups: int | None = None,
) -> dict[str, Any]:
    health = log_health_report(root, max_bytes=max_bytes, backups=backups)
    return {
        "kind": "aippocampus_logs_rotation_plan",
        "ok": True,
        "read_only": True,
        "apply_required": True,
        "oversized_count": health["oversized_count"],
        "would_rotate_count": health["oversized_count"],
        "max_bytes": health["max_bytes"],
        "backups": health["backups"],
        "items": [item for item in health["items"] if item["oversized"]],
        "apply_command": "aippocampus logs rotate --apply",
        "privacy_boundary": health["privacy_boundary"]
        | {"writes_performed": False, "local_paths_emitted": False},
        "agent_next_action": (
            "If these log artifacts are the intended cleanup target, apply once with "
            "`aippocampus logs rotate --apply`; status remains read-only."
        ),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aippocampus logs",
        usage="aippocampus logs [status|rotate|run] [options]",
        description=(
            "Local log retention card.\n\n"
            "Action card:\n"
            "  logs              Show read-only status; never writes.\n"
            "  logs status       Same read-only status with optional --json.\n"
            "  logs rotate --plan Preview bounded rotation without touching logs.\n"
            "  logs rotate --apply Apply the bounded rotation plan.\n\n"
            "Logs are local audit artifacts. Status and plan never print log contents."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.set_defaults(
        registry_dir=None,
        max_bytes=None,
        backups=None,
        json_output=False,
    )
    subparsers = parser.add_subparsers(dest="command")
    for name in ("status", "rotate"):
        sub = subparsers.add_parser(
            name,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description=(
                "Read-only log status. No log contents or local paths are emitted."
                if name == "status"
                else (
                    "Plan or apply bounded local log rotation.\n\n"
                    "Safe first step:\n"
                    "  aippocampus logs rotate --plan --json\n\n"
                    "`--plan`/`--dry-run` performs no writes. `--apply` compresses "
                    "oversized known log artifacts and retains the configured backup count."
                )
            ),
        )
        sub.add_argument("--registry-dir", default=None)
        sub.add_argument("--max-bytes", type=int, default=None)
        sub.add_argument("--backups", type=int, default=None)
        if name == "rotate":
            sub.add_argument(
                "--plan",
                "--dry-run",
                action="store_true",
                dest="plan",
                help="No-write preview. Shows which known log artifacts would rotate.",
            )
            sub.add_argument(
                "--apply",
                action="store_true",
                help=(
                    "Write mode. Compress oversized known log artifacts, remove the "
                    "current oversized file, and retain configured backups."
                ),
            )
        sub.add_argument("--json", action="store_true", dest="json_output")
    run = subparsers.add_parser("run")
    run.add_argument("--log", required=True)
    run.add_argument("--cwd", default=None)
    run.add_argument("--max-bytes", type=int, default=None)
    run.add_argument("--backups", type=int, default=None)
    run.add_argument("child", nargs=argparse.REMAINDER)
    return parser


def _registry_root(value: str | None) -> Path:
    return Path(value).resolve() if value else aippocampus_registry_dir()


def _print_text_status(report: dict[str, Any]) -> None:
    if report["oversized"]:
        print(f"logs: {report['oversized_count']} oversized artifact(s)")
    else:
        print("logs: within retention budget")
    for item in report["items"]:
        marker = "oversized" if item["oversized"] else "ok"
        print(f"- {item['artifact_rel']}: {item['size_bytes']} bytes [{marker}]")


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    command = args.command or "status"
    if command == "run":
        child = list(args.child)
        if child and child[0] == "--":
            child = child[1:]
        if not child:
            print("missing child command after --", file=sys.stderr)
            return 2
        return run_command_with_rotating_log(
            child,
            log=args.log,
            cwd=args.cwd,
            max_bytes=args.max_bytes,
            backups=args.backups,
        )

    root = _registry_root(args.registry_dir)
    if command == "rotate":
        if args.plan or not args.apply:
            result = rotation_plan(root, max_bytes=args.max_bytes, backups=args.backups)
            if args.json_output:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"logs rotation plan: {result['would_rotate_count']} would rotate")
                print(f"next: {result['apply_command']}")
            return 0
        result = rotate_known_logs(root, max_bytes=args.max_bytes, backups=args.backups)
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            _print_text_status(result["health"])
        return 0 if result["ok"] else 1

    result = log_health_report(root, max_bytes=args.max_bytes, backups=args.backups)
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_text_status(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
