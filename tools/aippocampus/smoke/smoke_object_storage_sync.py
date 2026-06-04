#!/usr/bin/env python3
"""HTTP object-storage sync smoke for AIppocampus Stage 3.

This smoke starts a local HTTP object store and exercises the production
object-storage adapter over PUT/GET. It proves the object protocol path and the
sync privacy/path-repair contract, but it does not claim a managed cloud
provider, a physical second machine, or external credentials.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()
from urllib.parse import unquote

import smoke_cross_device_sync

from aippocampus_runtime.sync import bundle as sync_bundle
from aippocampus_runtime.sync.object_storage import cli as sync_object_storage


class LocalObjectStoreHandler(BaseHTTPRequestHandler):
    server: "LocalObjectStoreServer"

    def object_path(self) -> tuple[str, Path] | None:
        key = unquote(self.path).lstrip("/")
        try:
            path = sync_bundle.sync_path_under(self.server.bucket_root, key)
        except ValueError:
            self.send_error(400)
            return None
        return key, path

    def do_PUT(self) -> None:  # noqa: N802
        resolved = self.object_path()
        if resolved is None:
            return
        key, path = resolved
        body = self.rfile.read(int(self.headers.get("Content-Length") or "0"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        self.server.requests.append({"method": "PUT", "key": key, "size": len(body)})
        self.send_response(200)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        resolved = self.object_path()
        if resolved is None:
            return
        key, path = resolved
        if not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.server.requests.append({"method": "GET", "key": key, "size": len(body)})
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class LocalObjectStoreServer(ThreadingHTTPServer):
    def __init__(self, bucket_root: Path) -> None:
        super().__init__(("127.0.0.1", 0), LocalObjectStoreHandler)
        self.bucket_root = bucket_root.resolve()
        self.bucket_root.mkdir(parents=True, exist_ok=True)
        self.requests: list[dict[str, object]] = []


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, code: str, failures: list[dict[str, str]], detail: str = "") -> None:
    if not condition:
        failures.append({"code": code, "detail": detail})


def run_object_storage_sync_smoke(
    repo_root: str | Path,
    *,
    keep_artifacts: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    run_id = run_id or uuid.uuid4().hex[:10]
    temp_context = None
    if keep_artifacts:
        root = repo_root / ".tmp" / f"aippocampus-object-storage-sync-{run_id}"
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
    else:
        temp_context = tempfile.TemporaryDirectory(prefix="aippocampus-object-storage-sync-")
        root = Path(temp_context.name)

    bucket_root = root / "object-store-bucket"
    server = LocalObjectStoreServer(bucket_root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}"
    prefix = f"stage3/{run_id}/sync-bundle"
    failures: list[dict[str, str]] = []
    result: dict[str, Any] = {
        "ok": False,
        "run_id": run_id,
        "artifact_root": str(root),
        "kept_artifacts": keep_artifacts,
        "claims": {
            "object_storage_protocol_executed": True,
            "single_machine_http_object_store": True,
            "single_machine_dual_device_model": True,
            "real_cloud_backend": False,
            "physical_second_machine": False,
        },
        "steps": {},
        "observed": {},
        "failures": failures,
    }

    try:
        device_a = smoke_cross_device_sync.create_device_registry(
            root / "device-a",
            device_name="device-a",
            workspace_locator=smoke_cross_device_sync.fake_windows_workspace(),
            message_text="Object storage smoke clean-source memory.",
        )
        target_b = root / "device-b" / "registry"

        push = sync_object_storage.push_object_storage_bundle(
            device_a["registry"], endpoint, prefix=prefix
        )
        status = sync_object_storage.status_object_storage_bundle(endpoint, prefix=prefix)
        repair = sync_object_storage.repair_object_storage_bundle(endpoint, prefix=prefix)
        pull = sync_object_storage.pull_object_storage_bundle(endpoint, target_b, prefix=prefix)

        target_registry = (
            read_json(target_b / "threads.json") if (target_b / "threads.json").is_file() else {}
        )
        source_markers = [
            str(device_a["registry"]),
            str(device_a["raw_rollout"]),
            smoke_cross_device_sync.fake_windows_workspace(),
            smoke_cross_device_sync.fake_posix_workspace(),
        ]
        if target_registry:
            smoke_cross_device_sync.validate_target_registry(
                target_registry,
                target_registry=target_b,
                source_markers=source_markers,
                failures=failures,
            )
        else:
            failures.append(
                {"code": "missing_target_registry", "detail": str(target_b / "threads.json")}
            )

        methods = sorted({str(item.get("method")) for item in server.requests})
        object_keys = {str(item.get("key")) for item in server.requests}
        manifest_key = sync_object_storage.object_key(prefix, sync_bundle.SYNC_MANIFEST_NAME)
        require(
            push.get("ok") is True, "push_failed", failures, json.dumps(push, ensure_ascii=False)
        )
        require(
            status.get("ok") is True,
            "status_failed",
            failures,
            json.dumps(status, ensure_ascii=False),
        )
        require(
            repair.get("ok") is True,
            "repair_failed",
            failures,
            json.dumps(repair, ensure_ascii=False),
        )
        require(
            pull.get("ok") is True, "pull_failed", failures, json.dumps(pull, ensure_ascii=False)
        )
        require("PUT" in methods, "missing_put_request", failures)
        require("GET" in methods, "missing_get_request", failures)
        require(manifest_key in object_keys, "missing_manifest_object", failures, manifest_key)
        require(
            not (target_b / "raw-rollouts").exists(), "raw_rollout_synced_without_opt_in", failures
        )

        result["steps"] = {
            "push": push,
            "status": status,
            "repair": repair,
            "pull": pull,
        }
        result["observed"] = {
            "backend": sync_object_storage.OBJECT_BACKEND,
            "http_methods": methods,
            "request_count": len(server.requests),
            "manifest_key": manifest_key,
            "object_count": push.get("object_count"),
            "target_paths": smoke_cross_device_sync.locator_values(target_registry),
            "raw_rollout_synced_without_opt_in": (target_b / "raw-rollouts").exists(),
        }
        result["ok"] = not failures
        return result
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if temp_context is not None:
            temp_context.cleanup()
        elif not keep_artifacts and root.exists():
            shutil.rmtree(root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(_paths.REPO_ROOT))
    parser.add_argument("--run-id")
    parser.add_argument("--keep-artifacts", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = run_object_storage_sync_smoke(
        args.repo_root,
        run_id=args.run_id,
        keep_artifacts=args.keep_artifacts,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"object-storage sync smoke: {'ok' if result.get('ok') else 'failed'}")
        for failure in result.get("failures") or []:
            print(f"- {failure.get('code')}: {failure.get('detail')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
