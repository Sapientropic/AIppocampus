from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import encrypted_sync_bundle  # noqa: E402
import sync_bundle  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
