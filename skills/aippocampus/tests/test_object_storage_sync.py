from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import smoke_cross_device_sync  # noqa: E402
import smoke_object_storage_sync  # noqa: E402
import sync_bundle  # noqa: E402
import sync_object_storage  # noqa: E402


class RecordingObjectHandler(BaseHTTPRequestHandler):
    server: "RecordingObjectServer"

    def object_path(self) -> tuple[str, Path] | None:
        key = unquote(self.path).lstrip("/")
        try:
            relative = sync_bundle.validate_relative_sync_path(key)
        except ValueError:
            self.send_error(400)
            return None
        return key, self.server.bucket_root / relative

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


class RecordingObjectServer(ThreadingHTTPServer):
    def __init__(self, bucket_root: Path) -> None:
        super().__init__(("127.0.0.1", 0), RecordingObjectHandler)
        self.bucket_root = bucket_root
        self.requests: list[dict[str, object]] = []


class ObjectStorageSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bucket = self.root / "object-bucket"
        self.server = RecordingObjectServer(self.bucket)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"
        self.prefix = "stage3/test-object-sync"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def create_registry(self) -> dict[str, object]:
        return smoke_cross_device_sync.create_device_registry(
            self.root / "device-a",
            device_name="device-a",
            workspace_locator=smoke_cross_device_sync.fake_windows_workspace(),
            message_text="Object storage sync source memory.",
        )

    def test_http_object_store_push_status_pull_uses_http_protocol(self) -> None:
        device = self.create_registry()
        target_registry = self.root / "target-device" / "registry"

        push = sync_object_storage.push_object_storage_bundle(
            device["registry"],
            self.endpoint,
            prefix=self.prefix,
        )
        status = sync_object_storage.status_object_storage_bundle(self.endpoint, prefix=self.prefix)
        pull = sync_object_storage.pull_object_storage_bundle(
            self.endpoint,
            target_registry,
            prefix=self.prefix,
        )

        self.assertTrue(push["ok"], push)
        self.assertEqual(push["backend"], "http_object_store")
        self.assertGreater(push["object_count"], 1)
        self.assertTrue(status["ok"], status)
        self.assertEqual(status["backend"], "http_object_store")
        self.assertTrue(pull["ok"], pull)
        self.assertTrue((target_registry / "threads.json").is_file())
        self.assertFalse((target_registry / "raw-rollouts").exists())
        methods = {request["method"] for request in self.server.requests}
        self.assertIn("PUT", methods)
        self.assertIn("GET", methods)
        object_keys = {request["key"] for request in self.server.requests}
        self.assertIn(f"{self.prefix}/{sync_bundle.SYNC_MANIFEST_NAME}", object_keys)

    def test_object_storage_repair_reports_tampered_object(self) -> None:
        device = self.create_registry()
        sync_object_storage.push_object_storage_bundle(device["registry"], self.endpoint, prefix=self.prefix)
        tampered = self.bucket / self.prefix / "registry" / "threads.json"
        tampered.write_text("tampered\n", encoding="utf-8")

        repair = sync_object_storage.repair_object_storage_bundle(self.endpoint, prefix=self.prefix)

        self.assertFalse(repair["ok"])
        self.assertEqual(repair["issues"][0]["code"], "hash_mismatch")
        self.assertEqual(repair["issues"][0]["path"], "registry/threads.json")

    def test_object_storage_repair_reports_invalid_manifest(self) -> None:
        manifest_path = self.bucket / self.prefix / sync_bundle.SYNC_MANIFEST_NAME
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text("{not json", encoding="utf-8")

        repair = sync_object_storage.repair_object_storage_bundle(self.endpoint, prefix=self.prefix)

        self.assertFalse(repair["ok"])
        self.assertEqual(repair["issues"][0]["code"], "invalid_manifest")

    def test_object_storage_pull_rejects_manifest_path_traversal(self) -> None:
        manifest = {
            "schema_version": sync_bundle.SYNC_SCHEMA_VERSION,
            "kind": "aippocampus_sync_bundle",
            "backend": "http_object_store",
            "files": [{"path": "../outside.json", "sha256": "bad", "size": 1}],
            "file_count": 1,
        }
        manifest_path = self.bucket / self.prefix / sync_bundle.SYNC_MANIFEST_NAME
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

        with self.assertRaises(ValueError):
            sync_object_storage.pull_object_storage_bundle(
                self.endpoint,
                self.root / "target-registry",
                prefix=self.prefix,
            )

    def test_object_storage_smoke_claims_protocol_not_cloud(self) -> None:
        result = smoke_object_storage_sync.run_object_storage_sync_smoke(ROOT)

        self.assertTrue(result["ok"], result.get("failures"))
        self.assertTrue(result["claims"]["object_storage_protocol_executed"])
        self.assertTrue(result["claims"]["single_machine_http_object_store"])
        self.assertFalse(result["claims"]["real_cloud_backend"])
        self.assertFalse(result["claims"]["physical_second_machine"])
        self.assertIn("PUT", result["observed"]["http_methods"])
        self.assertIn("GET", result["observed"]["http_methods"])
        self.assertFalse(result["observed"]["raw_rollout_synced_without_opt_in"])


if __name__ == "__main__":
    unittest.main()
