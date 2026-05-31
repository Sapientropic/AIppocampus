import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import smoke_cross_device_sync  # noqa: E402
import smoke_object_storage_sync  # noqa: E402
import smoke_real_provider_encrypted_sync  # noqa: E402

import encrypted_sync_bundle  # noqa: E402
import encrypted_sync_migration  # noqa: E402
from aippocampus_runtime.sync import bundle as sync_bundle  # noqa: E402
from aippocampus_runtime.sync import contract as sync_contract  # noqa: E402
from aippocampus_runtime.sync.object_storage import cli as sync_object_storage  # noqa: E402


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
        self.server.requests.append(
            {"method": "PUT", "key": key, "size": len(body), "headers": dict(self.headers)}
        )
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
        self.server.requests.append(
            {"method": "GET", "key": key, "size": len(body), "headers": dict(self.headers)}
        )
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_DELETE(self) -> None:  # noqa: N802
        resolved = self.object_path()
        if resolved is None:
            return
        key, path = resolved
        if not path.is_file():
            self.send_error(404)
            return
        path.unlink()
        self.server.requests.append(
            {"method": "DELETE", "key": key, "size": 0, "headers": dict(self.headers)}
        )
        self.send_response(204)
        self.end_headers()

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
        self.fake_age = self.write_fake_age()
        self.identity = self.root / "identity.txt"
        self.identity.write_text("trusted identity\n", encoding="utf-8")
        self.wrong_identity = self.root / "wrong-identity.txt"
        self.wrong_identity.write_text("wrong identity\n", encoding="utf-8")
        self.recipient = "age1testrecipient0000000000000000000000000000000000000000000"

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

    def write_fake_age(self) -> Path:
        path = self.root / "fake-age.py"
        path.write_text(
            """#!/usr/bin/env python3
from __future__ import annotations

import base64
import sys
from pathlib import Path

args = sys.argv[1:]
if args == ["--version"]:
    print("age fake-test")
    raise SystemExit(0)

if "-o" not in args:
    raise SystemExit(2)
output = Path(args[args.index("-o") + 1])
input_path = Path(args[-1])
if "-d" in args:
    if "-i" not in args:
        raise SystemExit(2)
    identity = Path(args[args.index("-i") + 1]).read_text(encoding="utf-8")
    if "wrong" in identity:
        print("no identity matched", file=sys.stderr)
        raise SystemExit(1)
    data = input_path.read_bytes()
    if not data.startswith(b"FAKEAGE\\n"):
        print("invalid header", file=sys.stderr)
        raise SystemExit(1)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(base64.b64decode(data.split(b"\\n", 1)[1]))
    raise SystemExit(0)

if "-r" not in args:
    raise SystemExit(2)
data = input_path.read_bytes()
output.parent.mkdir(parents=True, exist_ok=True)
output.write_bytes(b"FAKEAGE\\n" + base64.b64encode(data))
""",
            encoding="utf-8",
        )
        if os.name == "nt":
            wrapper = self.root / "fake-age.cmd"
            wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{path}" %*\r\n', encoding="utf-8")
            return wrapper
        path.chmod(0o755)
        return path

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
        uploaded_manifest = json.loads(
            (self.bucket / self.prefix / sync_bundle.SYNC_MANIFEST_NAME).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(uploaded_manifest["bundle_format"], sync_contract.SYNC_BUNDLE_KIND)
        self.assertEqual(
            uploaded_manifest["privacy_boundary"],
            sync_contract.sync_privacy_boundary(include_raw=False),
        )
        self.assertEqual(
            uploaded_manifest["transport"],
            sync_contract.sync_transport_metadata(
                kind="http_object_store",
                manifest_object=f"{self.prefix}/{sync_bundle.SYNC_MANIFEST_NAME}",
            ),
        )
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

    def test_object_store_token_requires_https_unless_endpoint_is_loopback(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires HTTPS"):
            sync_object_storage.client_for(
                "http://object-store.example.invalid",
                prefix=self.prefix,
                token="test-token",
            )

        local_client = sync_object_storage.client_for(
            self.endpoint,
            prefix=self.prefix,
            token="test-token",
        )
        self.assertEqual(local_client.headers()["Authorization"], "Bearer test-token")

    def test_s3_compatible_provider_uses_sigv4_headers(self) -> None:
        client = sync_object_storage.client_for_provider(
            provider="s3",
            bucket="memory-bucket",
            endpoint_url=self.endpoint,
            prefix=self.prefix,
            region="us-west-2",
            access_key_id="TESTACCESS",
            secret_access_key="test-secret",
        )

        client.put_object("probe.txt", b"probe")
        client.get_object("probe.txt")

        put_request = next(request for request in self.server.requests if request["method"] == "PUT")
        get_request = next(request for request in self.server.requests if request["method"] == "GET")
        self.assertEqual(put_request["key"], f"memory-bucket/{self.prefix}/probe.txt")
        put_headers = {key.casefold(): value for key, value in put_request["headers"].items()}
        get_headers = {key.casefold(): value for key, value in get_request["headers"].items()}
        self.assertEqual(
            put_headers["x-amz-content-sha256"],
            hashlib.sha256(b"probe").hexdigest(),
        )
        self.assertEqual(
            get_headers["x-amz-content-sha256"],
            hashlib.sha256(b"").hexdigest(),
        )
        self.assertIn("AWS4-HMAC-SHA256 Credential=TESTACCESS/", put_headers["authorization"])
        self.assertIn("/us-west-2/s3/aws4_request", put_headers["authorization"])
        self.assertIn(
            "SignedHeaders=host;x-amz-content-sha256;x-amz-date",
            put_headers["authorization"],
        )
        self.assertNotIn("bearer", put_headers["authorization"].casefold())

    def test_provider_factory_builds_r2_and_gcs_xml_endpoints(self) -> None:
        r2 = sync_object_storage.client_for_provider(
            provider="r2",
            account_id="account123",
            bucket="memory-bucket",
            prefix=self.prefix,
            access_key_id="R2ACCESS",
            secret_access_key="r2-secret",
        )
        self.assertEqual(
            r2.endpoint_url,
            "https://account123.r2.cloudflarestorage.com/memory-bucket",
        )
        self.assertIn("/memory-bucket/stage3/test-object-sync/probe.txt", r2.url_for("probe.txt"))
        self.assertIn("/auto/s3/aws4_request", r2.headers()["Authorization"])

        gcs = sync_object_storage.client_for_provider(
            provider="gcs-xml",
            bucket="memory-bucket",
            prefix=self.prefix,
            access_key_id="GOOGACCESS",
            secret_access_key="gcs-secret",
        )
        self.assertEqual(gcs.endpoint_url, "https://storage.googleapis.com/memory-bucket")
        self.assertIn("/memory-bucket/stage3/test-object-sync/probe.txt", gcs.url_for("probe.txt"))
        self.assertIn("GOOG4-HMAC-SHA256 Credential=GOOGACCESS/", gcs.headers()["Authorization"])
        self.assertIn("/auto/storage/goog4_request", gcs.headers()["Authorization"])

    def test_provider_signing_keys_require_https_unless_endpoint_is_loopback(self) -> None:
        with self.assertRaisesRegex(ValueError, "secret access key"):
            sync_object_storage.client_for_provider(
                provider="s3",
                bucket="memory-bucket",
                endpoint_url=self.endpoint,
                prefix=self.prefix,
                region="us-east-1",
                access_key_id="TESTACCESS",
            )

        with self.assertRaisesRegex(ValueError, "requires HTTPS"):
            sync_object_storage.client_for_provider(
                provider="s3",
                bucket="memory-bucket",
                endpoint_url="http://object-store.example.invalid",
                prefix=self.prefix,
                region="us-east-1",
                access_key_id="TESTACCESS",
                secret_access_key="test-secret",
            )

    def test_object_storage_push_pull_accepts_s3_compatible_provider(self) -> None:
        device = self.create_registry()
        target_registry = self.root / "signed-target" / "registry"
        provider = {
            "provider": "s3",
            "bucket": "memory-bucket",
            "region": "us-west-2",
            "access_key_id": "TESTACCESS",
            "secret_access_key": "test-secret",
        }

        push = sync_object_storage.push_object_storage_bundle(
            device["registry"],
            self.endpoint,
            prefix=self.prefix,
            **provider,
        )
        status = sync_object_storage.status_object_storage_bundle(
            self.endpoint,
            prefix=self.prefix,
            **provider,
        )
        pull = sync_object_storage.pull_object_storage_bundle(
            self.endpoint,
            target_registry,
            prefix=self.prefix,
            **provider,
        )

        self.assertTrue(push["ok"], push)
        self.assertTrue(status["ok"], status)
        self.assertTrue(pull["ok"], pull)
        self.assertTrue((target_registry / "threads.json").is_file())
        signed = [
            request
            for request in self.server.requests
            if "Authorization" in request["headers"]
        ]
        self.assertGreater(len(signed), 1)
        self.assertTrue(
            all(
                request["headers"]["Authorization"].startswith("AWS4-HMAC-SHA256")
                for request in signed
            )
        )

    def test_encrypted_object_storage_accepts_s3_compatible_provider(self) -> None:
        device = self.create_registry()
        target_registry = self.root / "signed-encrypted-target" / "registry"
        provider = {
            "provider": "s3",
            "bucket": "memory-bucket",
            "region": "us-west-2",
            "access_key_id": "TESTACCESS",
            "secret_access_key": "test-secret",
        }

        push = sync_object_storage.push_encrypted_object_storage_bundle(
            device["registry"],
            self.endpoint,
            prefix=self.prefix,
            recipients=[self.recipient],
            age_bin=self.fake_age,
            **provider,
        )
        repair = sync_object_storage.repair_encrypted_object_storage_bundle(
            self.endpoint,
            prefix=self.prefix,
            identity_files=[self.identity],
            age_bin=self.fake_age,
            **provider,
        )
        pull = sync_object_storage.pull_encrypted_object_storage_bundle(
            self.endpoint,
            target_registry,
            prefix=self.prefix,
            identity_files=[self.identity],
            age_bin=self.fake_age,
            **provider,
        )

        self.assertTrue(push["ok"], push)
        self.assertTrue(repair["ok"], repair)
        self.assertTrue(pull["ok"], pull)
        self.assertTrue((target_registry / "threads.json").is_file())
        object_keys = {request["key"] for request in self.server.requests}
        self.assertIn(
            f"memory-bucket/{self.prefix}/{encrypted_sync_bundle.ENCRYPTED_SYNC_DIR_NAME}/"
            f"{encrypted_sync_bundle.ENCRYPTED_SYNC_MANIFEST_NAME}",
            object_keys,
        )
        self.assertFalse(any(key.endswith("registry/threads.json") for key in object_keys))

    def test_cli_reads_provider_env_for_signed_s3_push(self) -> None:
        device = self.create_registry()
        env = {
            **os.environ,
            "AIPPOCAMPUS_OBJECT_PROVIDER": "s3",
            "AIPPOCAMPUS_OBJECT_STORE_URL": self.endpoint,
            "AIPPOCAMPUS_OBJECT_BUCKET": "memory-bucket",
            "AIPPOCAMPUS_OBJECT_REGION": "us-west-2",
            "AIPPOCAMPUS_OBJECT_ACCESS_KEY_ID": "TESTACCESS",
            "AIPPOCAMPUS_OBJECT_SECRET_ACCESS_KEY": "test-secret",
        }

        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "sync_object_storage.py"),
                "push",
                "--registry-dir",
                str(device["registry"]),
                "--json",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"], payload)
        signed = [
            request
            for request in self.server.requests
            if request["headers"].get("Authorization", "").startswith("AWS4-HMAC-SHA256")
        ]
        self.assertGreater(len(signed), 1)

    def test_object_storage_repair_reports_tampered_object(self) -> None:
        device = self.create_registry()
        sync_object_storage.push_object_storage_bundle(
            device["registry"], self.endpoint, prefix=self.prefix
        )
        tampered = self.bucket / self.prefix / "registry" / "threads.json"
        tampered.write_text("tampered\n", encoding="utf-8")

        repair = sync_object_storage.repair_object_storage_bundle(self.endpoint, prefix=self.prefix)

        self.assertFalse(repair["ok"])
        self.assertEqual(repair["issues"][0]["code"], "hash_mismatch")
        self.assertEqual(repair["issues"][0]["path"], "registry/threads.json")

    def test_plaintext_object_store_rejects_raw_rollout_sync(self) -> None:
        device = self.create_registry()

        push = sync_object_storage.push_object_storage_bundle(
            device["registry"],
            self.endpoint,
            prefix=self.prefix,
            include_raw=True,
        )

        self.assertFalse(push["ok"])
        self.assertEqual(push["issues"][0]["code"], "raw_requires_encryption")

    def test_encrypted_object_store_push_status_repair_pull_uses_ciphertext_objects(self) -> None:
        device = self.create_registry()
        target_registry = self.root / "encrypted-target" / "registry"

        push = sync_object_storage.push_encrypted_object_storage_bundle(
            device["registry"],
            self.endpoint,
            prefix=self.prefix,
            recipients=[self.recipient],
            age_bin=self.fake_age,
        )
        status = sync_object_storage.status_encrypted_object_storage_bundle(
            self.endpoint,
            prefix=self.prefix,
        )
        repair = sync_object_storage.repair_encrypted_object_storage_bundle(
            self.endpoint,
            prefix=self.prefix,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )
        pull = sync_object_storage.pull_encrypted_object_storage_bundle(
            self.endpoint,
            target_registry,
            prefix=self.prefix,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )

        self.assertTrue(push["ok"], push)
        self.assertTrue(status["ok"], status)
        self.assertEqual(status["recipient_match"], "unknown")
        self.assertTrue(repair["ok"], repair)
        self.assertTrue(pull["ok"], pull)
        self.assertTrue((target_registry / "threads.json").is_file())
        object_keys = {request["key"] for request in self.server.requests}
        self.assertIn(
            f"{self.prefix}/{encrypted_sync_bundle.ENCRYPTED_SYNC_DIR_NAME}/"
            f"{encrypted_sync_bundle.ENCRYPTED_SYNC_MANIFEST_NAME}",
            object_keys,
        )
        self.assertFalse(any(key.endswith("registry/threads.json") for key in object_keys))

    def test_encrypted_object_store_reports_wrong_key_and_tampered_object(self) -> None:
        device = self.create_registry()
        sync_object_storage.push_encrypted_object_storage_bundle(
            device["registry"],
            self.endpoint,
            prefix=self.prefix,
            recipients=[self.recipient],
            age_bin=self.fake_age,
        )

        wrong_key = sync_object_storage.repair_encrypted_object_storage_bundle(
            self.endpoint,
            prefix=self.prefix,
            identity_files=[self.wrong_identity],
            age_bin=self.fake_age,
        )
        self.assertFalse(wrong_key["ok"])
        self.assertEqual(wrong_key["issues"][0]["code"], "wrong_key")

        object_paths = list(
            (self.bucket / self.prefix / encrypted_sync_bundle.ENCRYPTED_SYNC_DIR_NAME / "objects")
            .glob("*.age")
        )
        self.assertGreater(len(object_paths), 1)
        object_paths[0].write_text("tampered\n", encoding="utf-8")
        tampered = sync_object_storage.repair_encrypted_object_storage_bundle(
            self.endpoint,
            prefix=self.prefix,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )
        self.assertFalse(tampered["ok"])
        self.assertIn(tampered["issues"][0]["code"], {"hash_mismatch", "wrong_key"})

    def test_encrypted_object_store_rejects_plaintext_prefix(self) -> None:
        device = self.create_registry()
        sync_object_storage.push_object_storage_bundle(
            device["registry"],
            self.endpoint,
            prefix=self.prefix,
        )

        encrypted_push = sync_object_storage.push_encrypted_object_storage_bundle(
            device["registry"],
            self.endpoint,
            prefix=self.prefix,
            recipients=[self.recipient],
            age_bin=self.fake_age,
        )

        self.assertFalse(encrypted_push["ok"])
        self.assertEqual(encrypted_push["issues"][0]["code"], "mixed_object_prefix")

    def test_plaintext_object_store_migration_and_cleanup(self) -> None:
        device = self.create_registry()
        target_prefix = f"{self.prefix}-encrypted"
        sync_object_storage.push_object_storage_bundle(
            device["registry"],
            self.endpoint,
            prefix=self.prefix,
        )
        wrong_registry = self.root / "wrong-object-registry"
        sync_object_storage.pull_object_storage_bundle(
            self.endpoint,
            wrong_registry,
            prefix=self.prefix,
        )
        wrong_messages = next(wrong_registry.glob("threads/*/clean-source/messages.jsonl"))
        wrong_messages.write_text(
            json.dumps({"message_id": "wrong", "text": "wrong registry"}, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )

        inventory = encrypted_sync_migration.inventory_plaintext_object_storage_bundle(
            self.endpoint,
            prefix=self.prefix,
        )
        dry_migration = encrypted_sync_migration.migrate_plaintext_object_storage_to_encrypted(
            wrong_registry,
            self.endpoint,
            prefix=self.prefix,
            target_prefix=target_prefix,
            recipients=[self.recipient],
            age_bin=self.fake_age,
            dry_run=True,
        )
        self.assertTrue(dry_migration["ok"], dry_migration)
        self.assertTrue(dry_migration["dry_run"])
        self.assertFalse(
            (
                self.bucket
                / target_prefix
                / encrypted_sync_bundle.ENCRYPTED_SYNC_DIR_NAME
                / encrypted_sync_bundle.ENCRYPTED_SYNC_MANIFEST_NAME
            ).exists()
        )

        migration = encrypted_sync_migration.migrate_plaintext_object_storage_to_encrypted(
            wrong_registry,
            self.endpoint,
            prefix=self.prefix,
            target_prefix=target_prefix,
            recipients=[self.recipient],
            age_bin=self.fake_age,
        )
        migrated_encrypted_target = self.root / "migrated-encrypted-object-target" / "registry"
        migrated_pull = sync_object_storage.pull_encrypted_object_storage_bundle(
            self.endpoint,
            migrated_encrypted_target,
            prefix=target_prefix,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )
        mixed_target = encrypted_sync_migration.migrate_plaintext_object_storage_to_encrypted(
            device["registry"],
            self.endpoint,
            prefix=self.prefix,
            target_prefix=target_prefix,
            recipients=[self.recipient],
            age_bin=self.fake_age,
        )
        cleanup_plan = encrypted_sync_migration.cleanup_plaintext_object_storage_bundle(
            self.endpoint,
            prefix=self.prefix,
            dry_run=True,
        )
        cleanup_without_confirm = encrypted_sync_migration.cleanup_plaintext_object_storage_bundle(
            self.endpoint,
            prefix=self.prefix,
            dry_run=False,
        )
        cleanup_without_verified = encrypted_sync_migration.cleanup_plaintext_object_storage_bundle(
            self.endpoint,
            prefix=self.prefix,
            dry_run=False,
            confirm=True,
        )
        cleanup = encrypted_sync_migration.cleanup_plaintext_object_storage_bundle(
            self.endpoint,
            prefix=self.prefix,
            dry_run=False,
            confirm=True,
            verified_encrypted_target=True,
        )

        self.assertTrue(inventory["ok"], inventory)
        self.assertTrue(inventory["plaintext_exposure"])
        self.assertGreater(inventory["plaintext_object_count"], 1)
        self.assertTrue(migration["ok"], migration)
        self.assertTrue(migrated_pull["ok"], migrated_pull)
        migrated_messages = next(
            migrated_encrypted_target.glob("threads/*/clean-source/messages.jsonl")
        ).read_text(encoding="utf-8")
        self.assertIn("Object storage sync source memory.", migrated_messages)
        self.assertNotIn("wrong registry", migrated_messages)
        self.assertFalse(mixed_target["ok"])
        self.assertEqual(mixed_target["issues"][0]["code"], "target_not_fresh")
        self.assertTrue(cleanup_plan["ok"], cleanup_plan)
        self.assertGreater(cleanup_plan["would_delete_count"], 1)
        self.assertFalse(cleanup_without_confirm["ok"])
        self.assertEqual(cleanup_without_confirm["issues"][0]["code"], "cleanup_confirmation_required")
        self.assertFalse(cleanup_without_verified["ok"])
        self.assertEqual(
            cleanup_without_verified["issues"][0]["code"],
            "encrypted_target_verification_required",
        )
        self.assertTrue(cleanup["ok"], cleanup)
        self.assertFalse((self.bucket / self.prefix / sync_bundle.SYNC_MANIFEST_NAME).exists())
        self.assertTrue(
            (
                self.bucket
                / target_prefix
                / encrypted_sync_bundle.ENCRYPTED_SYNC_DIR_NAME
                / encrypted_sync_bundle.ENCRYPTED_SYNC_MANIFEST_NAME
            ).is_file()
        )

    def test_real_provider_smoke_cleanup_paths_include_all_encrypted_objects(self) -> None:
        inner_manifest = {
            "outer_manifest": {
                "encryption": {
                    "manifest_object": "encrypted-sync/objects/inner-manifest.age",
                }
            },
            "objects": [
                {"object_path": "encrypted-sync/objects/a.age"},
                {"object_path": "encrypted-sync/objects/b.age"},
            ],
        }

        paths = smoke_real_provider_encrypted_sync.encrypted_cleanup_relative_paths(
            inner_manifest
        )

        self.assertEqual(
            [path.as_posix() for path in paths],
            [
                "encrypted-sync/aippocampus-encrypted-sync-manifest.json",
                "encrypted-sync/objects/a.age",
                "encrypted-sync/objects/b.age",
                "encrypted-sync/objects/inner-manifest.age",
            ],
        )

    def test_real_provider_smoke_deletes_all_encrypted_objects(self) -> None:
        result = smoke_real_provider_encrypted_sync.run_real_provider_encrypted_sync_smoke(
            object_store_url=self.endpoint,
            prefix=self.prefix,
            recipient=self.recipient,
            identity_files=[self.identity],
            age_bin=self.fake_age,
            run_id="unit-test",
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["cleanup"]["errors"], [])
        self.assertEqual(result["cleanup"]["missing_after_delete"], [])
        self.assertEqual(
            result["cleanup"]["attempted"],
            result["steps"]["push"]["object_count"],
        )
        self.assertNotIn("inner_manifest", result["steps"]["repair"])
        self.assertNotIn("sync_dir", result["steps"]["repair"])
        self.assertNotIn("sync_dir", result["steps"]["pull"])
        self.assertNotIn("target_registry_dir", result["steps"]["pull"])
        self.assertNotIn("object_store", result["steps"]["push"])
        self.assertGreater(result["cleanup"]["attempted"], 1)
        self.assertEqual(list((self.bucket / self.prefix).rglob("*.age")), [])
        self.assertIn("DELETE", {request["method"] for request in self.server.requests})

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
