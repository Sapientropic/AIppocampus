#!/usr/bin/env python3
"""HTTP object-storage adapter for AIppocampus sync bundles.

The adapter intentionally reuses the local bundle manifest contract instead of
inventing a second sync format. The object store is only the transport/storage
boundary: generated clean-source artifacts stay hash-addressed by manifest,
source-device locators stay portable, and raw rollouts remain opt-in.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import sync_bundle

OBJECT_BACKEND = "http_object_store"
DEFAULT_PREFIX = "aippocampus/sync"
DEFAULT_TIMEOUT_SECONDS = 20.0


def normalize_object_prefix(value: str | None) -> str:
    text = str(value or "").replace("\\", "/").strip("/")
    if not text:
        return ""
    return sync_bundle.validate_relative_sync_path(text).as_posix()


def object_key(prefix: str | None, relative_path: str | Path) -> str:
    path = sync_bundle.validate_relative_sync_path(relative_path)
    normalized_prefix = normalize_object_prefix(prefix)
    if not normalized_prefix:
        return path.as_posix()
    return f"{normalized_prefix}/{path.as_posix()}"


def safe_endpoint_label(endpoint_url: str) -> str:
    parsed = urlsplit(endpoint_url)
    netloc = parsed.hostname or parsed.netloc
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class HttpObjectStoreClient:
    endpoint_url: str
    prefix: str = DEFAULT_PREFIX
    token: str | None = None
    timeout: float = DEFAULT_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        parsed = urlsplit(self.endpoint_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("object store endpoint must be an http(s) URL")
        normalize_object_prefix(self.prefix)

    def url_for(self, relative_path: str | Path) -> str:
        key = object_key(self.prefix, relative_path)
        quoted = "/".join(quote(part, safe="") for part in key.split("/"))
        return f"{self.endpoint_url.rstrip('/')}/{quoted}"

    def headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = {"User-Agent": "AIppocampus-object-sync/0.1"}
        if content_type:
            headers["Content-Type"] = content_type
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def request(self, method: str, relative_path: str | Path, data: bytes | None = None) -> bytes:
        key = object_key(self.prefix, relative_path)
        request = Request(
            self.url_for(relative_path),
            data=data,
            headers=self.headers("application/octet-stream" if data is not None else None),
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError(key) from exc
            detail = exc.read(512).decode("utf-8", errors="replace")
            raise RuntimeError(
                f"object store {method} failed for {key}: HTTP {exc.code} {detail}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"object store {method} failed for {key}: {exc.reason}") from exc

    def put_object(self, relative_path: str | Path, data: bytes) -> dict[str, Any]:
        self.request("PUT", relative_path, data)
        return {"key": object_key(self.prefix, relative_path), "size": len(data)}

    def get_object(self, relative_path: str | Path) -> bytes:
        return self.request("GET", relative_path)


def client_for(
    object_store_url: str,
    *,
    prefix: str = DEFAULT_PREFIX,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> HttpObjectStoreClient:
    return HttpObjectStoreClient(object_store_url, prefix=prefix, token=token, timeout=timeout)


def load_object_manifest(client: HttpObjectStoreClient) -> dict[str, Any]:
    data = client.get_object(sync_bundle.SYNC_MANIFEST_NAME)
    manifest = json.loads(data.decode("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("object store manifest must be a JSON object")
    return manifest


def local_manifest_for_object_storage(manifest_path: Path, *, prefix: str) -> dict[str, Any]:
    manifest = sync_bundle.load_json(manifest_path)
    if not manifest:
        raise FileNotFoundError(f"missing local sync manifest: {manifest_path}")
    rewritten = dict(manifest)
    rewritten["backend"] = OBJECT_BACKEND
    rewritten["bundle_format"] = "aippocampus_sync_bundle"
    rewritten["object_prefix"] = normalize_object_prefix(prefix)
    rewritten["transport"] = {
        "kind": OBJECT_BACKEND,
        "manifest_object": object_key(prefix, sync_bundle.SYNC_MANIFEST_NAME),
        "raw_rollout_default": "excluded",
    }
    return rewritten


def iter_manifest_paths(manifest: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for item in manifest.get("files") or []:
        paths.append(sync_bundle.validate_relative_sync_path(str(item.get("path") or "")))
    return paths


def verify_manifest_objects(
    client: HttpObjectStoreClient, manifest: dict[str, Any]
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    checked = 0
    for item in manifest.get("files") or []:
        try:
            relative_path = sync_bundle.validate_relative_sync_path(str(item.get("path") or ""))
        except ValueError as exc:
            issues.append(
                {"code": "unsafe_path", "path": str(item.get("path") or ""), "message": str(exc)}
            )
            continue
        try:
            data = client.get_object(relative_path)
        except FileNotFoundError:
            issues.append({"code": "missing_file", "path": relative_path.as_posix()})
            continue
        checked += 1
        actual_hash = hash_bytes(data)
        if actual_hash != item.get("sha256"):
            issues.append(
                {
                    "code": "hash_mismatch",
                    "path": relative_path.as_posix(),
                    "expected": item.get("sha256"),
                    "actual": actual_hash,
                    "expected_size": item.get("size"),
                    "actual_size": len(data),
                }
            )
    return {"ok": not issues, "checked": checked, "issues": issues}


def push_object_storage_bundle(
    registry_dir: str | Path | None,
    object_store_url: str,
    *,
    prefix: str = DEFAULT_PREFIX,
    include_raw: bool = False,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    client = client_for(object_store_url, prefix=prefix, token=token, timeout=timeout)
    with tempfile.TemporaryDirectory(prefix="aippocampus-object-sync-push-") as tmp:
        sync_root = Path(tmp)
        local_push = sync_bundle.push_sync_bundle(registry_dir, sync_root, include_raw=include_raw)
        manifest = local_manifest_for_object_storage(
            sync_root / sync_bundle.SYNC_MANIFEST_NAME, prefix=prefix
        )
        uploaded: list[dict[str, Any]] = []
        for relative_path in iter_manifest_paths(manifest):
            source = sync_bundle.ensure_within(sync_root, sync_root / relative_path)
            uploaded.append(client.put_object(relative_path, source.read_bytes()))

        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        manifest_upload = client.put_object(sync_bundle.SYNC_MANIFEST_NAME, manifest_bytes)
        return {
            "ok": True,
            "backend": OBJECT_BACKEND,
            "object_store": safe_endpoint_label(object_store_url),
            "object_prefix": normalize_object_prefix(prefix),
            "manifest_key": manifest_upload["key"],
            "file_count": manifest.get("file_count", len(uploaded)),
            "object_count": len(uploaded) + 1,
            "raw_rollout_included": bool(manifest.get("raw_rollout_included")),
            "local_bundle_file_count": local_push.get("file_count"),
        }


def repair_object_storage_bundle(
    object_store_url: str,
    *,
    prefix: str = DEFAULT_PREFIX,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    client = client_for(object_store_url, prefix=prefix, token=token, timeout=timeout)
    try:
        manifest = load_object_manifest(client)
    except FileNotFoundError:
        return {
            "ok": False,
            "backend": OBJECT_BACKEND,
            "object_store": safe_endpoint_label(object_store_url),
            "object_prefix": normalize_object_prefix(prefix),
            "manifest_exists": False,
            "issues": [
                {
                    "code": "missing_manifest",
                    "path": object_key(prefix, sync_bundle.SYNC_MANIFEST_NAME),
                }
            ],
        }
    except RuntimeError as exc:
        return {
            "ok": False,
            "backend": OBJECT_BACKEND,
            "object_store": safe_endpoint_label(object_store_url),
            "object_prefix": normalize_object_prefix(prefix),
            "manifest_exists": None,
            "issues": [{"code": "object_store_unreachable", "message": str(exc)}],
        }
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        return {
            "ok": False,
            "backend": OBJECT_BACKEND,
            "object_store": safe_endpoint_label(object_store_url),
            "object_prefix": normalize_object_prefix(prefix),
            "manifest_exists": True,
            "issues": [{"code": "invalid_manifest", "message": str(exc)}],
        }
    verification = verify_manifest_objects(client, manifest)
    return {
        "ok": verification["ok"],
        "backend": OBJECT_BACKEND,
        "object_store": safe_endpoint_label(object_store_url),
        "object_prefix": normalize_object_prefix(prefix),
        "manifest_exists": True,
        "schema_version": manifest.get("schema_version"),
        "file_count": manifest.get("file_count", 0),
        "raw_rollout_included": bool(manifest.get("raw_rollout_included")),
        "checked": verification["checked"],
        "issues": verification["issues"],
    }


def status_object_storage_bundle(
    object_store_url: str,
    *,
    prefix: str = DEFAULT_PREFIX,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    repair = repair_object_storage_bundle(
        object_store_url, prefix=prefix, token=token, timeout=timeout
    )
    return {
        "ok": bool(repair.get("ok")),
        "backend": OBJECT_BACKEND,
        "object_store": repair.get("object_store"),
        "object_prefix": repair.get("object_prefix"),
        "manifest_exists": repair.get("manifest_exists"),
        "schema_version": repair.get("schema_version"),
        "file_count": repair.get("file_count", 0),
        "raw_rollout_included": repair.get("raw_rollout_included", False),
        "issues": repair.get("issues", []),
    }


def download_object_bundle(client: HttpObjectStoreClient, sync_root: Path) -> dict[str, Any]:
    manifest = load_object_manifest(client)
    manifest_path = sync_root / sync_bundle.SYNC_MANIFEST_NAME
    sync_bundle.save_json(manifest_path, manifest)
    issues: list[dict[str, Any]] = []
    downloaded = 0
    for item in manifest.get("files") or []:
        relative_path = sync_bundle.validate_relative_sync_path(str(item.get("path") or ""))
        try:
            data = client.get_object(relative_path)
        except FileNotFoundError:
            issues.append({"code": "missing_file", "path": relative_path.as_posix()})
            continue
        actual_hash = hash_bytes(data)
        if actual_hash != item.get("sha256"):
            issues.append(
                {
                    "code": "hash_mismatch",
                    "path": relative_path.as_posix(),
                    "expected": item.get("sha256"),
                    "actual": actual_hash,
                    "expected_size": item.get("size"),
                    "actual_size": len(data),
                }
            )
            continue
        destination = sync_bundle.ensure_within(sync_root, sync_root / relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        downloaded += 1
    return {"ok": not issues, "manifest": manifest, "downloaded": downloaded, "issues": issues}


def pull_object_storage_bundle(
    object_store_url: str,
    target_registry_dir: str | Path | None = None,
    *,
    prefix: str = DEFAULT_PREFIX,
    token: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    client = client_for(object_store_url, prefix=prefix, token=token, timeout=timeout)
    with tempfile.TemporaryDirectory(prefix="aippocampus-object-sync-pull-") as tmp:
        sync_root = Path(tmp)
        downloaded = download_object_bundle(client, sync_root)
        if not downloaded["ok"]:
            return {
                "ok": False,
                "backend": OBJECT_BACKEND,
                "object_store": safe_endpoint_label(object_store_url),
                "object_prefix": normalize_object_prefix(prefix),
                "downloaded": downloaded["downloaded"],
                "issues": downloaded["issues"],
            }
        pull = sync_bundle.pull_sync_bundle(sync_root, target_registry_dir)
        return {
            "ok": bool(pull.get("ok")),
            "backend": OBJECT_BACKEND,
            "object_store": safe_endpoint_label(object_store_url),
            "object_prefix": normalize_object_prefix(prefix),
            "downloaded": downloaded["downloaded"],
            "file_count": downloaded["manifest"].get("file_count", 0),
            "raw_rollout_included": bool(downloaded["manifest"].get("raw_rollout_included")),
            "pull": pull,
        }


def token_from_env(env_name: str | None) -> str | None:
    if not env_name:
        return None
    return os.environ.get(env_name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "push", "pull", "repair"])
    parser.add_argument(
        "--object-store-url", default=os.environ.get("AIPPOCAMPUS_OBJECT_STORE_URL")
    )
    parser.add_argument(
        "--object-prefix", default=os.environ.get("AIPPOCAMPUS_OBJECT_PREFIX", DEFAULT_PREFIX)
    )
    parser.add_argument("--token-env", default="AIPPOCAMPUS_OBJECT_STORE_TOKEN")
    parser.add_argument("--registry-dir", default=None)
    parser.add_argument("--include-raw", action="store_true")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    if not args.object_store_url:
        parser.error("--object-store-url or AIPPOCAMPUS_OBJECT_STORE_URL is required")

    token = token_from_env(args.token_env)
    if args.command == "status":
        result = status_object_storage_bundle(
            args.object_store_url, prefix=args.object_prefix, token=token, timeout=args.timeout
        )
    elif args.command == "push":
        result = push_object_storage_bundle(
            args.registry_dir,
            args.object_store_url,
            prefix=args.object_prefix,
            include_raw=args.include_raw,
            token=token,
            timeout=args.timeout,
        )
    elif args.command == "pull":
        result = pull_object_storage_bundle(
            args.object_store_url,
            args.registry_dir,
            prefix=args.object_prefix,
            token=token,
            timeout=args.timeout,
        )
    else:
        result = repair_object_storage_bundle(
            args.object_store_url, prefix=args.object_prefix, token=token, timeout=args.timeout
        )

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"object sync {args.command}: {'ok' if result.get('ok') else 'needs attention'}")
        if result.get("manifest_key"):
            print(f"manifest object: {result['manifest_key']}")
        for issue in result.get("issues") or []:
            print(f"- {issue.get('code')}: {issue.get('path') or issue.get('message')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
