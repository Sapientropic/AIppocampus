from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.sync import bundle as sync_bundle  # noqa: E402
from aippocampus_runtime.sync import contract as sync_contract  # noqa: E402
from aippocampus_runtime.sync.encrypted import bundle as encrypted_sync_bundle  # noqa: E402
from aippocampus_runtime.sync.encrypted import keys as encrypted_sync_keys  # noqa: E402
from aippocampus_runtime.sync.encrypted import migration as encrypted_sync_migration  # noqa: E402


class EncryptedSyncBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry = self.root / "registry"
        self.sync_dir = self.root / "sync"
        self.thread_store = self.registry / "threads" / "session-test"
        self.clean_source = self.thread_store / "clean-source"
        self.index_dir = self.thread_store / "index"
        self.clean_source.mkdir(parents=True)
        self.index_dir.mkdir(parents=True)
        (self.registry / "threads.json").write_text(
            json.dumps(
                {
                    "threads": [
                        {
                            "thread_key": "session:test",
                            "paths": {
                                "clean_source_dir": str(self.clean_source),
                                "rollout": str(self.root / "rollout.jsonl"),
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.root / "rollout.jsonl").write_text("raw private rollout\n", encoding="utf-8")
        (self.registry / "semantic_triggers.jsonl").write_text(
            json.dumps({"trigger": "小海马体"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (self.registry / "working_memory.jsonl").write_text(
            json.dumps({"memory_id": "wm_1"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (self.registry / "cognitive_map.json").write_text(
            json.dumps({"routes": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.clean_source / "manifest.json").write_text(
            json.dumps({"kind": "aippocampus_clean_source"}, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.clean_source / "messages.jsonl").write_text(
            json.dumps({"message_id": "msg_1", "text": "source backed"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (self.clean_source / "turns.jsonl").write_text(
            json.dumps({"turn_id": "turn_1"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (self.clean_source / "semantic-scope-labels.jsonl").write_text(
            json.dumps(
                {
                    "message_id": "msg_1",
                    "source": "deepseek_subconscious_scope_labels",
                    "scope_labels": ["personal_reflection"],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.index_dir / "manifest.json").write_text(
            json.dumps({"kind": "aippocampus_index"}, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.index_dir / "graph.json").write_text(
            json.dumps({"nodes": [], "edges": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        self.fake_age = self.write_fake_age()
        self.fake_age_keygen = self.write_fake_age_keygen()
        self.identity = self.root / "identity.txt"
        self.identity.write_text("trusted identity\n", encoding="utf-8")
        self.wrong_identity = self.root / "wrong-identity.txt"
        self.wrong_identity.write_text("wrong identity\n", encoding="utf-8")
        self.recipient = "age1testrecipient0000000000000000000000000000000000000000000"

    def tearDown(self) -> None:
        self.tmp.cleanup()

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

    def write_fake_age_keygen(self) -> Path:
        path = self.root / "fake-age-keygen.py"
        path.write_text(
            """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

args = sys.argv[1:]
if "--version" in args:
    print("age-keygen fake-test")
    raise SystemExit(0)

if "-y" in args:
    identity = Path(args[-1]).read_text(encoding="utf-8")
    if "device-b" in identity:
        print("age1deviceb00000000000000000000000000000000000000000000000")
    else:
        print("age1devicea00000000000000000000000000000000000000000000000")
    raise SystemExit(0)

if "-o" not in args:
    raise SystemExit(2)
output = Path(args[args.index("-o") + 1])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text("AGE-SECRET-KEY-1FAKE-DEVICE-A\\n", encoding="utf-8")
raise SystemExit(0)
""",
            encoding="utf-8",
        )
        if os.name == "nt":
            wrapper = self.root / "fake-age-keygen.cmd"
            wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{path}" %*\r\n', encoding="utf-8")
            return wrapper
        path.chmod(0o755)
        return path

    def test_device_key_init_trust_revoke_and_trusted_push(self) -> None:
        init = encrypted_sync_keys.init_device_key(
            self.registry,
            device_name="device-a",
            age_keygen_bin=self.fake_age_keygen,
        )
        trusted = encrypted_sync_keys.trust_recipient(
            self.registry,
            recipient="age1deviceb00000000000000000000000000000000000000000000000",
            device_name="device-b",
        )
        listing = encrypted_sync_keys.list_device_keys(self.registry)

        self.assertTrue(init["ok"], init)
        self.assertTrue(init["identity_available"])
        self.assertEqual(init["identity_location"], "local_registry_state")
        self.assertNotIn("AGE-SECRET-KEY", json.dumps(init, ensure_ascii=False))
        stored_keys = encrypted_sync_keys.load_device_keys(self.registry)
        self.assertNotIn("identity_file", stored_keys["local_device"])
        self.assertTrue(trusted["ok"], trusted)
        self.assertEqual(listing["trusted_recipient_count"], 2)

        trusted_sync_dir = self.root / "trusted-sync"
        trusted_push = encrypted_sync_bundle.push_encrypted_sync_bundle(
            self.registry,
            trusted_sync_dir,
            age_bin=self.fake_age,
        )
        trusted_repair = encrypted_sync_bundle.repair_encrypted_sync_bundle(
            trusted_sync_dir,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )
        self.assertTrue(trusted_push["ok"], trusted_push)
        self.assertTrue(trusted_repair["ok"], trusted_repair)
        self.assertEqual(trusted_repair["inner_manifest"]["recipient_count"], 2)

        revoke_plan = encrypted_sync_keys.revoke_recipient(
            self.registry,
            "age1deviceb00000000000000000000000000000000000000000000000",
            dry_run=True,
        )
        revoked = encrypted_sync_keys.revoke_recipient(
            self.registry,
            "age1deviceb00000000000000000000000000000000000000000000000",
            confirm=True,
        )
        retrust = encrypted_sync_keys.trust_recipient(
            self.registry,
            recipient="age1deviceb00000000000000000000000000000000000000000000000",
            device_name="device-b",
        )
        self.assertTrue(revoke_plan["ok"], revoke_plan)
        self.assertTrue(revoke_plan["dry_run"])
        self.assertTrue(revoked["ok"], revoked)
        self.assertEqual(retrust["issues"][0]["code"], "revoked_recipient")

        push = encrypted_sync_bundle.push_encrypted_sync_bundle(
            self.registry,
            self.sync_dir,
            age_bin=self.fake_age,
        )

        self.assertTrue(push["ok"], push)
        sync_text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in self.sync_dir.rglob("*")
            if path.is_file()
        )
        self.assertNotIn("AGE-SECRET-KEY", sync_text)
        repair = encrypted_sync_bundle.repair_encrypted_sync_bundle(
            self.sync_dir,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )
        self.assertTrue(repair["ok"], repair)
        self.assertEqual(repair["inner_manifest"]["recipient_count"], 1)

    def test_encrypted_sync_admin_cli_key_recipient_redacts_identity(self) -> None:
        init_proc = subprocess.run(
            [
                sys.executable,
                "-m", "aippocampus_runtime.sync.encrypted.admin",
                "key",
                "init",
                "--registry-dir",
                str(self.registry),
                "--device-name",
                "device-a",
                "--age-keygen-bin",
                str(self.fake_age_keygen),
                "--json",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        recipient_proc = subprocess.run(
            [
                sys.executable,
                "-m", "aippocampus_runtime.sync.encrypted.admin",
                "key",
                "recipient",
                "--registry-dir",
                str(self.registry),
                "--age-keygen-bin",
                str(self.fake_age_keygen),
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(init_proc.returncode, 0, init_proc.stderr)
        self.assertNotIn("AGE-SECRET-KEY", init_proc.stdout)
        self.assertEqual(recipient_proc.returncode, 0, recipient_proc.stderr)
        self.assertTrue(recipient_proc.stdout.strip().startswith("age1devicea"))

    def test_recovery_recipient_and_revocation_reencrypt_boundary(self) -> None:
        init = encrypted_sync_keys.init_device_key(
            self.registry,
            device_name="device-a",
            age_keygen_bin=self.fake_age_keygen,
        )
        device_b = "age1deviceb00000000000000000000000000000000000000000000000"
        recovery_recipient = "age1recovery00000000000000000000000000000000000000000000"
        trusted = encrypted_sync_keys.trust_recipient(
            self.registry,
            recipient=device_b,
            device_name="device-b",
        )
        recovery = encrypted_sync_keys.trust_recipient(
            self.registry,
            recipient=recovery_recipient,
            device_name="paper-recovery-kit",
            role=encrypted_sync_keys.RECIPIENT_ROLE_RECOVERY,
        )
        listing = encrypted_sync_keys.list_device_keys(self.registry)

        self.assertTrue(init["ok"], init)
        self.assertTrue(trusted["ok"], trusted)
        self.assertTrue(recovery["ok"], recovery)
        self.assertEqual(recovery["role"], "recovery")
        self.assertTrue(listing["recovery_configured"])
        self.assertEqual(listing["recovery_state"]["recovery_recipient_count"], 1)
        self.assertIsNone(listing["reencryption_required"])

        first_push = encrypted_sync_bundle.push_encrypted_sync_bundle(
            self.registry,
            self.sync_dir,
            age_bin=self.fake_age,
        )
        first_repair = encrypted_sync_bundle.repair_encrypted_sync_bundle(
            self.sync_dir,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )
        self.assertTrue(first_push["ok"], first_push)
        self.assertEqual(first_repair["inner_manifest"]["recipient_count"], 3)

        revoked = encrypted_sync_keys.revoke_recipient(self.registry, device_b, confirm=True)
        pending = encrypted_sync_keys.list_device_keys(self.registry)
        self.assertTrue(revoked["ok"], revoked)
        self.assertTrue(revoked["reencryption_required"]["old_ciphertexts_remain_decryptable"])
        self.assertEqual(
            revoked["reencryption_required"]["remaining_recovery_recipient_count"],
            1,
        )
        self.assertEqual(pending["reencryption_required"]["status"], "pending_after_revoke")

        revoked_push = encrypted_sync_bundle.push_encrypted_sync_bundle(
            self.registry,
            self.root / "revoked-sync",
            recipients=[device_b],
            age_bin=self.fake_age,
        )
        self.assertFalse(revoked_push["ok"])
        self.assertEqual(revoked_push["issues"][0]["code"], "revoked_recipient")

        partial_push = encrypted_sync_bundle.push_encrypted_sync_bundle(
            self.registry,
            self.root / "partial-sync",
            recipients=[init["recipient"]],
            age_bin=self.fake_age,
        )
        self.assertTrue(partial_push["ok"], partial_push)
        self.assertFalse(partial_push["reencryption"]["cleared"])
        self.assertEqual(
            partial_push["reencryption"]["reason"],
            "remaining_trusted_recipients_missing",
        )

        fresh_push = encrypted_sync_bundle.push_encrypted_sync_bundle(
            self.registry,
            self.sync_dir,
            age_bin=self.fake_age,
        )
        fresh_repair = encrypted_sync_bundle.repair_encrypted_sync_bundle(
            self.sync_dir,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )
        cleared = encrypted_sync_keys.list_device_keys(self.registry)
        self.assertTrue(fresh_push["ok"], fresh_push)
        self.assertTrue(fresh_push["reencryption"]["cleared"])
        self.assertIsNone(cleared["reencryption_required"])
        self.assertEqual(fresh_repair["inner_manifest"]["recipient_count"], 2)

    def test_encrypted_local_push_status_repair_pull_round_trip(self) -> None:
        push = encrypted_sync_bundle.push_encrypted_sync_bundle(
            self.registry,
            self.sync_dir,
            recipients=[self.recipient],
            age_bin=self.fake_age,
        )

        encrypted_root = self.sync_dir / encrypted_sync_bundle.ENCRYPTED_SYNC_DIR_NAME
        outer_manifest = encrypted_root / encrypted_sync_bundle.ENCRYPTED_SYNC_MANIFEST_NAME
        self.assertTrue(push["ok"], push)
        self.assertTrue(outer_manifest.is_file())
        self.assertFalse((self.sync_dir / sync_bundle.SYNC_MANIFEST_NAME).exists())
        self.assertFalse((self.sync_dir / "registry").exists())
        ciphertext_text = "\n".join(
            path.read_text(encoding="utf-8") for path in encrypted_root.rglob("*.age")
        )
        self.assertNotIn("source backed", ciphertext_text)

        outer = json.loads(outer_manifest.read_text(encoding="utf-8"))
        self.assertEqual(outer["kind"], "aippocampus_encrypted_sync_bundle")
        self.assertNotIn("created_at", outer)
        self.assertNotIn("manifest_revision", outer)
        self.assertNotIn("recipient_count", json.dumps(outer, ensure_ascii=False))
        self.assertNotIn("vault_id_hash", json.dumps(outer, ensure_ascii=False))

        status = encrypted_sync_bundle.status_encrypted_sync_bundle(self.sync_dir)
        repair = encrypted_sync_bundle.repair_encrypted_sync_bundle(
            self.sync_dir,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )
        target_registry = self.root / "encrypted-target"
        pull = encrypted_sync_bundle.pull_encrypted_sync_bundle(
            self.sync_dir,
            target_registry,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )

        self.assertTrue(status["ok"], status)
        self.assertEqual(status["recipient_match"], "unknown")
        self.assertTrue(repair["ok"], repair)
        self.assertGreater(repair["checked"], 0)
        self.assertEqual(
            repair["inner_manifest"]["sync_manifest"]["privacy_boundary"],
            sync_contract.sync_privacy_boundary(include_raw=False),
        )
        self.assertTrue(pull["ok"], pull)
        messages = target_registry / "threads" / "session-test" / "clean-source" / "messages.jsonl"
        self.assertIn("source backed", messages.read_text(encoding="utf-8"))

    def test_encrypted_push_rejects_mixed_plaintext_sync_dir(self) -> None:
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir)

        result = encrypted_sync_bundle.push_encrypted_sync_bundle(
            self.registry,
            self.sync_dir,
            recipients=[self.recipient],
            age_bin=self.fake_age,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["issues"][0]["code"], "mixed_sync_dir")

    def test_encrypted_repair_reports_wrong_key_tamper_and_missing_object(self) -> None:
        encrypted_sync_bundle.push_encrypted_sync_bundle(
            self.registry,
            self.sync_dir,
            recipients=[self.recipient],
            age_bin=self.fake_age,
        )

        missing_identity = encrypted_sync_bundle.repair_encrypted_sync_bundle(
            self.sync_dir,
            identity_files=[],
            age_bin=self.fake_age,
        )
        self.assertFalse(missing_identity["ok"])
        self.assertEqual(missing_identity["issues"][0]["code"], "identity_missing")

        wrong_key = encrypted_sync_bundle.repair_encrypted_sync_bundle(
            self.sync_dir,
            identity_files=[self.wrong_identity],
            age_bin=self.fake_age,
        )
        self.assertFalse(wrong_key["ok"])
        self.assertEqual(wrong_key["issues"][0]["code"], "wrong_key")

        repair = encrypted_sync_bundle.repair_encrypted_sync_bundle(
            self.sync_dir,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )
        object_path = self.sync_dir / repair["inner_manifest"]["objects"][0]["object_path"]
        object_path.write_text("tampered\n", encoding="utf-8")
        tampered = encrypted_sync_bundle.repair_encrypted_sync_bundle(
            self.sync_dir,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )
        self.assertFalse(tampered["ok"])
        self.assertEqual(tampered["issues"][0]["code"], "hash_mismatch")

        encrypted_sync_bundle.push_encrypted_sync_bundle(
            self.registry,
            self.sync_dir,
            recipients=[self.recipient],
            age_bin=self.fake_age,
        )
        repair = encrypted_sync_bundle.repair_encrypted_sync_bundle(
            self.sync_dir,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )
        missing_path = self.sync_dir / repair["inner_manifest"]["objects"][0]["object_path"]
        missing_path.unlink()
        missing = encrypted_sync_bundle.repair_encrypted_sync_bundle(
            self.sync_dir,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["issues"][0]["code"], "missing_file")

    def test_encrypted_pull_rejects_replayed_old_snapshot(self) -> None:
        encrypted_sync_bundle.push_encrypted_sync_bundle(
            self.registry,
            self.sync_dir,
            recipients=[self.recipient],
            age_bin=self.fake_age,
        )
        old_snapshot = self.root / "old-encrypted-sync"
        sync_bundle.copy_file(
            self.sync_dir
            / encrypted_sync_bundle.ENCRYPTED_SYNC_DIR_NAME
            / encrypted_sync_bundle.ENCRYPTED_SYNC_MANIFEST_NAME,
            old_snapshot
            / encrypted_sync_bundle.ENCRYPTED_SYNC_DIR_NAME
            / encrypted_sync_bundle.ENCRYPTED_SYNC_MANIFEST_NAME,
        )
        source_objects = self.sync_dir / encrypted_sync_bundle.ENCRYPTED_SYNC_DIR_NAME / "objects"
        for source in source_objects.glob("*"):
            sync_bundle.copy_file(
                source,
                old_snapshot / encrypted_sync_bundle.ENCRYPTED_SYNC_DIR_NAME / "objects" / source.name,
            )

        (self.clean_source / "messages.jsonl").write_text(
            json.dumps({"message_id": "msg_2", "text": "newer source"}, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        encrypted_sync_bundle.push_encrypted_sync_bundle(
            self.registry,
            self.sync_dir,
            recipients=[self.recipient],
            age_bin=self.fake_age,
        )
        target_registry = self.root / "replay-target"
        second = encrypted_sync_bundle.pull_encrypted_sync_bundle(
            self.sync_dir,
            target_registry,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )
        self.assertTrue(second["ok"], second)

        replay = encrypted_sync_bundle.pull_encrypted_sync_bundle(
            old_snapshot,
            target_registry,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )

        self.assertFalse(replay["ok"])
        self.assertEqual(replay["issues"][0]["code"], "stale_manifest")

    def test_encrypted_raw_rollout_round_trip_requires_explicit_include_raw(self) -> None:
        encrypted_sync_bundle.push_encrypted_sync_bundle(
            self.registry,
            self.sync_dir,
            recipients=[self.recipient],
            include_raw=True,
            age_bin=self.fake_age,
        )
        target_registry = self.root / "encrypted-target-with-raw"

        pull = encrypted_sync_bundle.pull_encrypted_sync_bundle(
            self.sync_dir,
            target_registry,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )

        self.assertTrue(pull["ok"], pull)
        repaired = json.loads((target_registry / "threads.json").read_text(encoding="utf-8"))
        rollout = Path(repaired["threads"][0]["paths"]["rollout"])
        self.assertEqual(
            rollout.resolve(),
            (target_registry / "raw-rollouts" / "session-test.jsonl").resolve(),
        )
        self.assertTrue(rollout.exists())

    def test_encrypted_push_rejects_secret_key_as_recipient(self) -> None:
        result = encrypted_sync_bundle.push_encrypted_sync_bundle(
            self.registry,
            self.sync_dir,
            recipients=["AGE-SECRET-KEY-1TEST"],
            age_bin=self.fake_age,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["issues"][0]["code"], "recipient_secret_rejected")

    def test_plaintext_migration_inventory_migrate_and_cleanup(self) -> None:
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir)
        encrypted_target = self.root / "encrypted-target-sync"
        wrong_registry = self.root / "wrong-registry"
        sync_bundle.pull_sync_bundle(self.sync_dir, wrong_registry)
        (wrong_registry / "threads" / "session-test" / "clean-source" / "messages.jsonl").write_text(
            json.dumps({"message_id": "wrong", "text": "wrong registry"}, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )

        inventory = encrypted_sync_migration.inventory_plaintext_sync_dir(
            self.sync_dir,
            target_sync_dir=encrypted_target,
        )
        dry_migration = encrypted_sync_migration.migrate_plaintext_sync_dir_to_encrypted(
            self.sync_dir,
            encrypted_target,
            registry_dir=self.registry,
            recipients=[self.recipient],
            age_bin=self.fake_age,
            dry_run=True,
        )
        self.assertTrue(dry_migration["ok"], dry_migration)
        self.assertTrue(dry_migration["dry_run"])
        self.assertFalse((encrypted_target / encrypted_sync_bundle.ENCRYPTED_SYNC_DIR_NAME).exists())

        migration = encrypted_sync_migration.migrate_plaintext_sync_dir_to_encrypted(
            self.sync_dir,
            encrypted_target,
            registry_dir=wrong_registry,
            recipients=[self.recipient],
            age_bin=self.fake_age,
        )
        migrated_target = self.root / "migrated-target-registry"
        migrated_pull = encrypted_sync_bundle.pull_encrypted_sync_bundle(
            encrypted_target,
            migrated_target,
            identity_files=[self.identity],
            age_bin=self.fake_age,
        )
        mixed_target = encrypted_sync_migration.migrate_plaintext_sync_dir_to_encrypted(
            self.sync_dir,
            encrypted_target,
            registry_dir=self.registry,
            recipients=[self.recipient],
            age_bin=self.fake_age,
        )
        cleanup_plan = encrypted_sync_migration.cleanup_plaintext_sync_dir(
            self.sync_dir,
            dry_run=True,
        )
        cleanup_without_confirm = encrypted_sync_migration.cleanup_plaintext_sync_dir(
            self.sync_dir,
            dry_run=False,
        )
        cleanup_without_verified = encrypted_sync_migration.cleanup_plaintext_sync_dir(
            self.sync_dir,
            dry_run=False,
            confirm=True,
        )
        cleanup = encrypted_sync_migration.cleanup_plaintext_sync_dir(
            self.sync_dir,
            dry_run=False,
            confirm=True,
            verified_encrypted_target=True,
        )

        self.assertTrue(inventory["ok"], inventory)
        self.assertTrue(inventory["plaintext_exposure"])
        self.assertGreater(inventory["plaintext_object_count"], 1)
        self.assertTrue(migration["ok"], migration)
        self.assertTrue(
            (encrypted_target / encrypted_sync_bundle.ENCRYPTED_SYNC_DIR_NAME).is_dir()
        )
        self.assertTrue(migrated_pull["ok"], migrated_pull)
        migrated_messages = (
            migrated_target / "threads" / "session-test" / "clean-source" / "messages.jsonl"
        ).read_text(encoding="utf-8")
        self.assertIn("source backed", migrated_messages)
        self.assertNotIn("wrong registry", migrated_messages)
        self.assertFalse(mixed_target["ok"])
        self.assertEqual(mixed_target["issues"][0]["code"], "target_not_fresh")
        self.assertTrue(cleanup_plan["ok"], cleanup_plan)
        self.assertTrue(cleanup_plan["dry_run"])
        self.assertGreater(cleanup_plan["would_delete_count"], 1)
        self.assertFalse(cleanup_without_confirm["ok"])
        self.assertEqual(cleanup_without_confirm["issues"][0]["code"], "cleanup_confirmation_required")
        self.assertFalse(cleanup_without_verified["ok"])
        self.assertEqual(
            cleanup_without_verified["issues"][0]["code"],
            "encrypted_target_verification_required",
        )
        self.assertTrue(cleanup["ok"], cleanup)
        self.assertFalse((self.sync_dir / sync_bundle.SYNC_MANIFEST_NAME).exists())

    def test_plaintext_migration_failed_push_preserves_plaintext_and_partial_target(self) -> None:
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir)
        encrypted_target = self.root / "partial-encrypted-target"

        def partial_push(
            registry_dir: str | Path | None,
            sync_dir: str | Path,
            **kwargs: object,
        ) -> dict[str, object]:
            partial = (
                encrypted_sync_bundle.encrypted_root(Path(sync_dir))
                / encrypted_sync_bundle.ENCRYPTED_OBJECTS_DIR_NAME
                / "partial.age"
            )
            partial.parent.mkdir(parents=True, exist_ok=True)
            partial.write_text("partial encrypted object", encoding="utf-8")
            return {
                "ok": False,
                "encrypted": True,
                "issues": [
                    {
                        "code": "simulated_interrupted_push",
                        "message": "simulated encrypted push interruption",
                    }
                ],
                "object_count": 1,
            }

        with patch.object(
            encrypted_sync_migration.encrypted_sync_bundle,
            "push_encrypted_sync_bundle",
            side_effect=partial_push,
        ):
            migration = encrypted_sync_migration.migrate_plaintext_sync_dir_to_encrypted(
                self.sync_dir,
                encrypted_target,
                registry_dir=self.registry,
                recipients=[self.recipient],
                age_bin=self.fake_age,
            )

        self.assertFalse(migration["ok"])
        self.assertEqual(migration["issues"][0]["code"], "simulated_interrupted_push")
        self.assertEqual(migration["issues"][-1]["code"], "partial_migration_preserved")
        self.assertEqual(migration["migration_recovery"]["status"], "partial_migration_preserved")
        self.assertTrue(migration["migration_recovery"]["plaintext_source_preserved"])
        self.assertTrue(migration["migration_recovery"]["target_preserved_for_inspection"])
        self.assertFalse(migration["migration_recovery"]["cleanup_allowed"])
        self.assertEqual(migration["migration_recovery"]["partial_encrypted_artifact_count"], 1)
        self.assertTrue((self.sync_dir / sync_bundle.SYNC_MANIFEST_NAME).is_file())
        self.assertTrue(
            (
                encrypted_sync_bundle.encrypted_root(encrypted_target)
                / encrypted_sync_bundle.ENCRYPTED_OBJECTS_DIR_NAME
                / "partial.age"
            ).is_file()
        )


if __name__ == "__main__":
    unittest.main()
