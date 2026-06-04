#!/usr/bin/env python3
"""Alternate-runtime sync smoke for Docker or WSL.

The regular cross-device smoke models multiple devices on one host. This smoke
adds a real alternate runtime boundary when Docker or WSL is available: the
bundle is created on the host, then the sync package runs inside the alternate
runtime and repairs locators to that runtime's local paths.

No external cloud backend is claimed here. Object storage remains a separate
adapter because pretending a local folder is cloud storage would weaken the
Stage 3 evidence boundary.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

import smoke_cross_device_sync

from aippocampus_runtime.sync import bundle as sync_bundle

# Build drive markers without literal drive-root strings so repo secret/path
# scans can still flag accidental local absolute paths elsewhere.
WINDOWS_PATH_MARKERS = tuple(f"{drive}:" + "\\" for drive in ("C", "D", "E")) + ("\\Users\\",)
DEFAULT_DOCKER_IMAGE = os.environ.get(
    "AIPPOCAMPUS_ALTERNATE_RUNTIME_DOCKER_IMAGE", "python:3.12-slim"
)


@dataclass(frozen=True)
class RuntimePaths:
    sync_dir: str
    target_registry: str
    runtime_root: str


def write_runtime_scripts(root: Path) -> Path:
    runtime_dir = root / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    for name in ("aippocampus_runtime", "conversation_sources"):
        shutil.copytree(_paths.SKILL_SCRIPTS / name, runtime_dir / name, dirs_exist_ok=True)
    return runtime_dir


def build_host_bundle(root: Path) -> dict[str, Any]:
    device = smoke_cross_device_sync.create_device_registry(
        root / "host-device",
        device_name="host-device",
        workspace_locator=smoke_cross_device_sync.fake_windows_workspace(),
        message_text="Host-side clean source that should survive alternate-runtime pull.",
    )
    sync_dir = root / "shared-sync-folder"
    push = sync_bundle.push_sync_bundle(device["registry"], sync_dir)
    return {"device": device, "sync_dir": sync_dir, "push": push}


def run_json(args: list[str], *, timeout: int = 90) -> dict[str, Any]:
    proc = subprocess.run(
        args,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    payload: dict[str, Any] = {}
    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = {}
    return {
        "ok": proc.returncode == 0 and bool(payload.get("ok", proc.returncode == 0)),
        "returncode": proc.returncode,
        "payload": payload,
        "stdout_tail": clean_process_tail(proc.stdout),
        "stderr_tail": clean_process_tail(proc.stderr),
        "args": args,
    }


def clean_process_tail(text: str, *, limit: int = 1200) -> str:
    tail = (text or "")[-limit:].replace("\x00", "")
    low = tail.casefold()
    if low.startswith("wsl:") and "localhost" in low:
        return "[wsl localhost warning suppressed]"
    return tail


def docker_available(image: str) -> tuple[bool, str]:
    docker = shutil.which("docker")
    if not docker:
        return False, "docker_not_found"
    version = subprocess.run([docker, "--version"], text=True, capture_output=True, check=False)
    if version.returncode != 0:
        return False, "docker_unavailable"
    inspect = subprocess.run(
        [docker, "image", "inspect", image], text=True, capture_output=True, check=False
    )
    if inspect.returncode != 0:
        return False, f"docker_image_missing:{image}"
    return True, version.stdout.strip()


def docker_paths(root: Path, runtime_dir: Path) -> RuntimePaths:
    return RuntimePaths(
        sync_dir="/work/shared-sync-folder",
        target_registry="/work/docker-target-registry",
        runtime_root="/work/runtime",
    )


def docker_run(image: str, root: Path, runtime_paths: RuntimePaths, command: str) -> dict[str, Any]:
    docker = shutil.which("docker") or "docker"
    args = [
        docker,
        "run",
        "--rm",
        "--pull",
        "never",
        "-v",
        f"{root.resolve()}:/work",
        "-w",
        runtime_paths.runtime_root,
        image,
        "python",
        "-m",
        "aippocampus_runtime.sync.bundle",
        command,
        "--sync-dir",
        runtime_paths.sync_dir,
        "--registry-dir",
        runtime_paths.target_registry,
        "--json",
    ]
    return run_json(args)


def wsl_available() -> tuple[bool, str]:
    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if not wsl:
        return False, "wsl_not_found"
    probe = subprocess.run(
        [wsl, "sh", "-lc", "command -v python3"], capture_output=True, check=False
    )
    if probe.returncode != 0:
        return False, "wsl_python3_missing"
    return True, decode_process_bytes(probe.stdout).strip() or "python3"


def fallback_wsl_mount_path(path: Path) -> str | None:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").casefold()
    if not drive:
        return None
    parts = [part for part in resolved.parts[1:] if part not in ("\\", "/")]
    return f"/mnt/{drive}/" + "/".join(part.replace("\\", "/") for part in parts)


def wsl_path(path: Path) -> str:
    wsl = shutil.which("wsl.exe") or shutil.which("wsl") or "wsl.exe"
    proc = subprocess.run(
        [wsl, "wslpath", "-a", str(path.resolve())], capture_output=True, check=False
    )
    stdout = decode_process_bytes(proc.stdout).strip()
    if proc.returncode == 0 and stdout:
        return stdout
    fallback = fallback_wsl_mount_path(path)
    if fallback:
        probe = subprocess.run(
            [wsl, "sh", "-lc", f"test -e {quote_sh(fallback)}"],
            capture_output=True,
            check=False,
        )
        if probe.returncode == 0:
            return fallback
    raise RuntimeError("wsl_path_translation_failed")


def decode_process_bytes(value: bytes | None) -> str:
    if not value:
        return ""
    for encoding in ("utf-8", "utf-16le", "mbcs"):
        try:
            text = value.decode(encoding)
        except Exception:
            continue
        if text:
            return text.replace("\x00", "")
    return value.decode("utf-8", errors="replace").replace("\x00", "")


def quote_sh(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def wsl_paths(root: Path, runtime_dir: Path) -> RuntimePaths:
    return RuntimePaths(
        sync_dir=f"{wsl_path(root)}/shared-sync-folder",
        target_registry=f"{wsl_path(root)}/wsl-target-registry",
        runtime_root=wsl_path(runtime_dir),
    )


def wsl_run(runtime_paths: RuntimePaths, command: str) -> dict[str, Any]:
    wsl = shutil.which("wsl.exe") or shutil.which("wsl") or "wsl.exe"
    shell = (
        "cd "
        + quote_sh(runtime_paths.runtime_root)
        + " && python3 -m aippocampus_runtime.sync.bundle"
        + f" {command} --sync-dir "
        + quote_sh(runtime_paths.sync_dir)
        + " --registry-dir "
        + quote_sh(runtime_paths.target_registry)
        + " --json"
    )
    return run_json([wsl, "sh", "-lc", shell])


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_target_registry(
    target_registry_json: Path, *, runtime_root_marker: str
) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    if not target_registry_json.is_file():
        return {
            "ok": False,
            "failures": [{"code": "missing_target_registry", "detail": str(target_registry_json)}],
        }
    registry = read_json(target_registry_json)
    text = json.dumps(registry, ensure_ascii=False)
    for marker in WINDOWS_PATH_MARKERS:
        if marker in text:
            failures.append({"code": "windows_locator_leaked", "detail": marker})
    paths = smoke_cross_device_sync.locator_values(registry)
    for key in (
        "registry_thread_store",
        "clean_source_messages_jsonl",
        "clean_source_turns_jsonl",
        "graph_json",
    ):
        value = str(paths.get(key) or "")
        if not value.startswith(runtime_root_marker):
            failures.append({"code": "locator_not_repaired_to_runtime", "detail": f"{key}={value}"})
        if "\\" in value:
            failures.append({"code": "runtime_locator_uses_backslash", "detail": f"{key}={value}"})
    if paths.get("workspace") is not None:
        failures.append(
            {"code": "workspace_should_stay_unresolved", "detail": str(paths.get("workspace"))}
        )
    if paths.get("rollout") is not None:
        failures.append(
            {"code": "raw_rollout_should_stay_excluded", "detail": str(paths.get("rollout"))}
        )
    return {"ok": not failures, "failures": failures, "paths": paths}


def run_runtime_smoke(
    runtime: str, root: Path, runtime_dir: Path, *, docker_image: str
) -> dict[str, Any]:
    if runtime == "docker":
        available, reason = docker_available(docker_image)
        if not available:
            return {"runtime": runtime, "ok": True, "skipped": True, "reason": reason}
        paths = docker_paths(root, runtime_dir)
        status = docker_run(docker_image, root, paths, "status")
        repair = docker_run(docker_image, root, paths, "repair") if status.get("ok") else None
        pull = (
            docker_run(docker_image, root, paths, "pull") if repair and repair.get("ok") else None
        )
        validation = (
            validate_target_registry(
                root / "docker-target-registry" / "threads.json",
                runtime_root_marker="/work/docker-target-registry",
            )
            if pull and pull.get("ok")
            else {
                "ok": False,
                "failures": [
                    {
                        "code": "pull_not_ok",
                        "detail": json.dumps((pull or {}).get("payload", {}), ensure_ascii=False),
                    }
                ],
            }
        )
        return {
            "runtime": runtime,
            "ok": bool(
                status.get("ok")
                and repair
                and repair.get("ok")
                and pull
                and pull.get("ok")
                and validation.get("ok")
            ),
            "skipped": False,
            "image": docker_image,
            "status": status,
            "repair": repair,
            "pull": pull,
            "validation": validation,
        }
    if runtime == "wsl":
        available, reason = wsl_available()
        if not available:
            return {"runtime": runtime, "ok": True, "skipped": True, "reason": reason}
        try:
            paths = wsl_paths(root, runtime_dir)
        except RuntimeError as exc:
            reason = str(exc) or "wsl_path_unavailable"
            return {"runtime": runtime, "ok": True, "skipped": True, "reason": reason}
        status = wsl_run(paths, "status")
        repair = wsl_run(paths, "repair") if status.get("ok") else None
        pull = wsl_run(paths, "pull") if repair and repair.get("ok") else None
        validation = (
            validate_target_registry(
                root / "wsl-target-registry" / "threads.json",
                runtime_root_marker=paths.target_registry,
            )
            if pull and pull.get("ok")
            else {
                "ok": False,
                "failures": [
                    {
                        "code": "pull_not_ok",
                        "detail": json.dumps((pull or {}).get("payload", {}), ensure_ascii=False),
                    }
                ],
            }
        )
        return {
            "runtime": runtime,
            "ok": bool(
                status.get("ok")
                and repair
                and repair.get("ok")
                and pull
                and pull.get("ok")
                and validation.get("ok")
            ),
            "skipped": False,
            "status": status,
            "repair": repair,
            "pull": pull,
            "validation": validation,
        }
    raise ValueError(f"unsupported runtime: {runtime}")


def selected_runtimes(value: str) -> list[str]:
    if value == "auto":
        return ["docker", "wsl"]
    if value == "all":
        return ["docker", "wsl"]
    return [value]


def run_alternate_runtime_sync_smoke(
    repo_root: str | Path,
    *,
    runtime: str = "auto",
    require_runtime: bool = False,
    keep_artifacts: bool = False,
    run_id: str | None = None,
    docker_image: str = DEFAULT_DOCKER_IMAGE,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    run_id = run_id or uuid.uuid4().hex[:10]
    temp_context = None
    if keep_artifacts:
        root = repo_root / ".tmp" / f"aippocampus-alternate-runtime-sync-{run_id}"
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
    else:
        temp_context = tempfile.TemporaryDirectory(prefix="aippocampus-alternate-runtime-sync-")
        root = Path(temp_context.name)

    try:
        runtime_dir = write_runtime_scripts(root)
        bundle = build_host_bundle(root)
        runtime_results = [
            run_runtime_smoke(item, root, runtime_dir, docker_image=docker_image)
            for item in selected_runtimes(runtime)
        ]
        ran = [item for item in runtime_results if not item.get("skipped")]
        failures = [item for item in runtime_results if not item.get("ok")]
        ok = not failures and (bool(ran) or not require_runtime)
        return {
            "ok": ok,
            "run_id": run_id,
            "artifact_root": str(root),
            "kept_artifacts": keep_artifacts,
            "claims": {
                "single_machine_dual_device_model": True,
                "alternate_runtime_executed": bool(ran),
                "docker_runtime_executed": any(
                    item.get("runtime") == "docker" and not item.get("skipped")
                    for item in runtime_results
                ),
                "wsl_runtime_executed": any(
                    item.get("runtime") == "wsl" and not item.get("skipped")
                    for item in runtime_results
                ),
                "real_cloud_backend": False,
                "physical_second_machine": False,
            },
            "host_push": bundle["push"],
            "runtimes": runtime_results,
            "failures": failures,
        }
    finally:
        if temp_context is not None:
            temp_context.cleanup()
        elif not keep_artifacts and root.exists():
            shutil.rmtree(root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(_paths.REPO_ROOT))
    parser.add_argument("--runtime", choices=["auto", "all", "docker", "wsl"], default="auto")
    parser.add_argument("--docker-image", default=DEFAULT_DOCKER_IMAGE)
    parser.add_argument("--require-runtime", action="store_true")
    parser.add_argument("--keep-artifacts", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = run_alternate_runtime_sync_smoke(
        args.repo_root,
        runtime=args.runtime,
        require_runtime=args.require_runtime,
        keep_artifacts=args.keep_artifacts,
        run_id=args.run_id,
        docker_image=args.docker_image,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"alternate-runtime sync smoke: {'ok' if result.get('ok') else 'failed'}")
        for item in result.get("runtimes") or []:
            if item.get("skipped"):
                print(f"- {item.get('runtime')}: skipped ({item.get('reason')})")
            else:
                print(f"- {item.get('runtime')}: {'ok' if item.get('ok') else 'failed'}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
