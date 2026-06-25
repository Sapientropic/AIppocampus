from __future__ import annotations

import json
import tempfile
import threading
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

from tests.aippocampus.import_path_helpers import import_smoke_module
from tests.aippocampus.timing_fixtures import host_timeout_sleep

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"

smoke_alternate_runtime_sync = import_smoke_module("smoke_alternate_runtime_sync")
smoke_cross_device_sync = import_smoke_module("smoke_cross_device_sync")

from aippocampus_runtime.registry import store as registry_store
from aippocampus_runtime.sync import bundle as sync_bundle
from aippocampus_runtime.sync import contract as sync_contract


class SyncBundleTests(unittest.TestCase):
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
        (self.clean_source / "events.jsonl").write_text(
            json.dumps(
                {
                    "event_id": "evt_1",
                    "hard_event_kind": "tool_call_failed",
                    "behavior_backed": True,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.clean_source / "source-texture.jsonl").write_text(
            json.dumps(
                {
                    "texture_id": "tex_1",
                    "signal_kind": "tool_failure_texture",
                    "truth_boundary": "texture_signal_not_source_fact",
                },
                ensure_ascii=False,
            )
            + "\n",
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
    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_plan_without_sync_dir_returns_chooser_without_scanning_registry(self) -> None:
        with (
            mock.patch.object(sync_bundle, "iter_registry_sync_files") as registry_files,
            mock.patch.object(sync_bundle, "iter_clean_source_sync_files") as clean_files,
            mock.patch.object(sync_bundle, "iter_raw_rollout_files") as raw_files,
            mock.patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            code = sync_bundle.main(["push", "--plan", "--json"])

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        registry_files.assert_not_called()
        clean_files.assert_not_called()
        raw_files.assert_not_called()
        self.assertEqual(payload["status"], "needs_sync_dir_before_plan")
        self.assertEqual(payload["requested_command"], "push")
        self.assertTrue(payload["plan_skipped_no_destination"])
        self.assertIsNone(payload["estimated_file_count"])
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertEqual(payload["foreground_action"]["id"], "check_local_sync_status")
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertTrue(all(action["mutation_risk"] == "read_only" for action in payload["safe_next_actions"]))

    def test_push_writes_device_neutral_bundle_without_raw_rollout(self) -> None:
        result = sync_bundle.push_sync_bundle(self.registry, self.sync_dir)

        manifest_path = self.sync_dir / sync_bundle.SYNC_MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        relative_paths = {item["path"] for item in manifest["files"]}
        delta = manifest["clean_source_delta"]

        self.assertTrue(result["ok"])
        self.assertEqual(manifest["kind"], sync_bundle.SYNC_BUNDLE_KIND)
        self.assertEqual(manifest["backend"], sync_bundle.LOCAL_FOLDER_BACKEND)
        self.assertEqual(
            manifest["privacy_boundary"],
            sync_contract.sync_privacy_boundary(include_raw=False),
        )
        self.assertFalse(manifest["raw_rollout_included"])
        self.assertIn("registry/threads.json", relative_paths)
        self.assertIn("registry/semantic_triggers.jsonl", relative_paths)
        self.assertIn("registry/working_memory.jsonl", relative_paths)
        self.assertIn("registry/cognitive_map.json", relative_paths)
        self.assertNotIn("registry/threads/session-test/clean-source/messages.jsonl", relative_paths)
        self.assertNotIn("registry/threads/session-test/clean-source/turns.jsonl", relative_paths)
        self.assertNotIn("registry/threads/session-test/clean-source/events.jsonl", relative_paths)
        self.assertNotIn(
            "registry/threads/session-test/clean-source/source-texture.jsonl", relative_paths
        )
        self.assertIn("registry/threads/session-test/index/manifest.json", relative_paths)
        self.assertIn("clean-source-chunks/manifest.json", relative_paths)
        self.assertEqual(delta["kind"], "content_addressed_clean_source_chunks")
        self.assertEqual(delta["generated_cache_export"], "explicit_only")
        self.assertEqual(delta["file_count"], 5)
        self.assertEqual(delta["chunk_count"], 5)
        logical_paths = {item["path"] for item in delta["files"]}
        self.assertIn("registry/threads/session-test/clean-source/messages.jsonl", logical_paths)
        self.assertIn("registry/threads/session-test/clean-source/events.jsonl", logical_paths)
        self.assertIn(
            "registry/threads/session-test/clean-source/source-texture.jsonl", logical_paths
        )
        for item in delta["files"]:
            self.assertTrue(item["chunks"], item)
            for chunk in item["chunks"]:
                self.assertTrue(chunk["path"].startswith("clean-source-chunks/sha256/"))
                self.assertIn(chunk["path"], relative_paths)
        self.assertNotIn("rollout.jsonl", "\n".join(relative_paths))
        portable_registry = json.loads(
            (self.sync_dir / "registry" / "threads.json").read_text(encoding="utf-8")
        )
        portable_paths = portable_registry["threads"][0]["paths"]
        self.assertEqual(
            portable_paths["clean_source_messages_jsonl"],
            "registry/threads/session-test/clean-source/messages.jsonl",
        )
        self.assertEqual(
            portable_paths["clean_source_events_jsonl"],
            "registry/threads/session-test/clean-source/events.jsonl",
        )
        self.assertEqual(
            portable_paths["clean_source_texture_jsonl"],
            "registry/threads/session-test/clean-source/source-texture.jsonl",
        )
        self.assertIsNone(portable_paths["workspace"])
        self.assertIsNone(portable_paths["rollout"])

    def test_missing_local_sync_manifest_returns_redacted_recovery_actions(self) -> None:
        missing_sync_dir = self.root / "missing-sync-dir"

        status = sync_bundle.status_sync_bundle(missing_sync_dir)
        repair = sync_bundle.repair_sync_bundle(missing_sync_dir)

        for payload in (status, repair):
            with self.subTest(payload=payload):
                encoded = json.dumps(payload, ensure_ascii=False)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["status"], "missing_manifest")
                self.assertEqual(payload["sync_dir_label"], "<local-sync-dir-redacted>")
                self.assertFalse(payload["privacy_boundary"]["local_paths_included"])
                self.assertEqual(payload["issues"][0]["code"], "missing_manifest")
                self.assertTrue(payload["issues"][0]["path_redacted"])
                self.assertIn("safe_next_actions", payload)
                action_ids = [action["id"] for action in payload["safe_next_actions"]]
                self.assertEqual(payload["foreground_action"]["id"], "check_local_sync_status")
                self.assertNotIn("check_local_sync_status", action_ids)
                self.assertIn("preview_local_sync_push", action_ids)
                self.assertIn("preview_local_sync_repair", action_ids)
                self.assertTrue(all(action["template_only"] for action in payload["safe_next_actions"]))
                self.assertNotIn(str(missing_sync_dir), encoded)

    def test_push_excludes_generated_sqlite_pointer_from_default_sync(self) -> None:
        (self.index_dir / "source_index.sqlite").write_bytes(b"stable sqlite cache")
        versions = self.index_dir / "versions"
        versions.mkdir()
        (versions / "source_index-current.sqlite").write_bytes(b"versioned sqlite cache")
        (self.index_dir / "source_index.pointer.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "aippocampus_sqlite_index_pointer",
                    "stable": "source_index.sqlite",
                    "current": "versions/source_index-current.sqlite",
                    "last_known_good": "source_index.sqlite",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        sync_bundle.push_sync_bundle(self.registry, self.sync_dir)

        manifest = json.loads(
            (self.sync_dir / sync_bundle.SYNC_MANIFEST_NAME).read_text(encoding="utf-8")
        )
        relative_paths = {item["path"] for item in manifest["files"]}
        self.assertFalse(any(path.endswith(".sqlite") for path in relative_paths))
        self.assertFalse(any(path.endswith("source_index.pointer.json") for path in relative_paths))
        portable_registry = json.loads(
            (self.sync_dir / "registry" / "threads.json").read_text(encoding="utf-8")
        )
        self.assertIsNone(portable_registry["threads"][0]["paths"]["sqlite"])

        target_registry = self.root / "target-no-generated-cache"
        sync_bundle.pull_sync_bundle(self.sync_dir, target_registry)
        repaired = json.loads((target_registry / "threads.json").read_text(encoding="utf-8"))
        self.assertIsNone(repaired["threads"][0]["paths"]["sqlite"])

    def test_path_repair_resolves_target_local_sqlite_pointer(self) -> None:
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir)
        target_registry = self.root / "target-with-local-cache"
        sync_bundle.pull_sync_bundle(self.sync_dir, target_registry)
        target_index = target_registry / "threads" / "session-test" / "index"
        target_versions = target_index / "versions"
        target_versions.mkdir()
        current = target_versions / "source_index-current.sqlite"
        current.write_bytes(b"locally rebuilt sqlite cache")
        (target_index / "source_index.pointer.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "kind": "aippocampus_sqlite_index_pointer",
                    "stable": "source_index.sqlite",
                    "current": "versions/source_index-current.sqlite",
                    "last_known_good": "source_index.sqlite",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        repair = sync_bundle.repair_registry_locators(target_registry)

        self.assertTrue(repair["ok"], repair)
        repaired = json.loads((target_registry / "threads.json").read_text(encoding="utf-8"))
        self.assertEqual(Path(repaired["threads"][0]["paths"]["sqlite"]).resolve(), current.resolve())

    def test_push_delta_reuses_unchanged_clean_source_chunks(self) -> None:
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir)
        first = json.loads(
            (self.sync_dir / sync_bundle.SYNC_MANIFEST_NAME).read_text(encoding="utf-8")
        )
        first_files = {item["path"]: item for item in first["clean_source_delta"]["files"]}
        first_messages_chunks = [
            chunk["path"]
            for chunk in first_files[
                "registry/threads/session-test/clean-source/messages.jsonl"
            ]["chunks"]
        ]
        first_turns_chunks = [
            chunk["path"]
            for chunk in first_files["registry/threads/session-test/clean-source/turns.jsonl"][
                "chunks"
            ]
        ]

        (self.clean_source / "messages.jsonl").write_text(
            json.dumps({"message_id": "msg_1", "text": "source backed changed"}, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir)
        second = json.loads(
            (self.sync_dir / sync_bundle.SYNC_MANIFEST_NAME).read_text(encoding="utf-8")
        )
        second_files = {item["path"]: item for item in second["clean_source_delta"]["files"]}
        second_messages_chunks = [
            chunk["path"]
            for chunk in second_files[
                "registry/threads/session-test/clean-source/messages.jsonl"
            ]["chunks"]
        ]
        second_turns_chunks = [
            chunk["path"]
            for chunk in second_files["registry/threads/session-test/clean-source/turns.jsonl"][
                "chunks"
            ]
        ]

        self.assertNotEqual(first_messages_chunks, second_messages_chunks)
        self.assertEqual(first_turns_chunks, second_turns_chunks)
        for path in first_messages_chunks + first_turns_chunks:
            self.assertTrue((self.sync_dir / path).is_file(), path)

    def test_clean_source_materialize_failure_preserves_destination_and_cleans_tmp(self) -> None:
        chunk_data = b"fresh clean source\n"
        chunk_hash = sync_bundle.bytes_sha256(chunk_data)
        chunk_path = sync_bundle.clean_source_chunk_path(chunk_hash)
        chunk_file = sync_bundle.sync_path_under(self.sync_dir, chunk_path)
        chunk_file.parent.mkdir(parents=True)
        chunk_file.write_bytes(chunk_data)
        destination = self.root / "target" / "messages.jsonl"
        destination.parent.mkdir(parents=True)
        destination.write_text("existing\n", encoding="utf-8")
        stale_fixed_tmp = destination.with_suffix(destination.suffix + ".tmp")
        stale_fixed_tmp.write_text("stale fixed tmp\n", encoding="utf-8")

        manifest = {
            "path": "registry/threads/session-test/clean-source/messages.jsonl",
            "size": len(chunk_data) + 1,
            "sha256": chunk_hash,
            "chunks": [
                {
                    "path": chunk_path.as_posix(),
                    "size": len(chunk_data),
                    "sha256": chunk_hash,
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "clean_source_file_size_mismatch"):
            sync_bundle.materialize_clean_source_delta_file(
                self.sync_dir,
                manifest,
                destination,
            )

        self.assertEqual(destination.read_text(encoding="utf-8"), "existing\n")
        self.assertEqual(stale_fixed_tmp.read_text(encoding="utf-8"), "stale fixed tmp\n")
        self.assertEqual(list(destination.parent.glob(".*.aippocampus-*.tmp")), [])

    def test_pull_copies_missing_files_and_preserves_conflicts(self) -> None:
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir)
        target_registry = self.root / "target-registry"
        target_messages = (
            target_registry / "threads" / "session-test" / "clean-source" / "messages.jsonl"
        )
        target_messages.parent.mkdir(parents=True)
        target_messages.write_text("different local content\n", encoding="utf-8")

        result = sync_bundle.pull_sync_bundle(self.sync_dir, target_registry)

        self.assertGreaterEqual(result["copied"], 6)
        self.assertEqual(result["conflicts"], 1)
        self.assertTrue(result["write_boundary"]["written"])
        self.assertFalse(result["write_boundary"]["explicit_write_required"])
        self.assertEqual(result["recovery_actions"][0]["id"], "rollback_sync_pull")
        self.assertEqual(result["rollback"]["status"], "available")
        self.assertIn("aippocampus sync rollback", result["rollback"]["command"])
        self.assertEqual(target_messages.read_text(encoding="utf-8"), "different local content\n")
        conflict_files = list((target_registry / ".sync-conflicts").rglob("messages.jsonl"))
        self.assertEqual(len(conflict_files), 1)
        self.assertIn("source backed", conflict_files[0].read_text(encoding="utf-8"))

        rollback = sync_bundle.rollback_sync_pull(
            target_registry,
            rollback_id=result["rollback"]["rollback_id"],
        )

        self.assertTrue(rollback["ok"], rollback)
        self.assertTrue(rollback["write_boundary"]["written"])
        self.assertFalse((target_registry / "threads.json").exists())
        self.assertFalse((target_registry / "threads.md").exists())
        self.assertEqual(target_messages.read_text(encoding="utf-8"), "different local content\n")

    def test_pull_preflight_rejects_tampered_file_without_target_write(self) -> None:
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir)
        tampered = self.sync_dir / "registry" / "semantic_triggers.jsonl"
        original = tampered.read_bytes()
        tampered.write_bytes(b"x" * len(original))
        target_registry = self.root / "target-preflight"

        result = sync_bundle.pull_sync_bundle(self.sync_dir, target_registry)

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "sync_pull_preflight_failed")
        self.assertEqual(result["issues"][0]["code"], "hash_mismatch")
        self.assertFalse(result["write_boundary"]["written"])
        self.assertFalse(target_registry.exists())

    def test_pull_serializes_materialize_and_repair_with_registry_writer(self) -> None:
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir)
        target_registry = self.root / "target-serialized"
        repair_entered = threading.Event()
        peer_entered = threading.Event()
        peer_done = threading.Event()
        release_repair = threading.Event()
        errors: list[BaseException] = []
        result: dict[str, object] = {}
        original_clean_source_path_fields = sync_bundle.clean_source_path_fields

        def slow_clean_source_path_fields(
            clean_root: Path,
            locator_root: Path,
            *,
            portable: bool,
        ) -> dict[str, str | None]:
            if not portable and target_registry.resolve() in clean_root.resolve().parents:
                repair_entered.set()
                release_repair.wait(timeout=5)
            return original_clean_source_path_fields(
                clean_root,
                locator_root,
                portable=portable,
            )

        def pull_worker() -> None:
            try:
                result.update(sync_bundle.pull_sync_bundle(self.sync_dir, target_registry))
            except BaseException as exc:
                errors.append(exc)

        def peer_worker() -> None:
            try:
                repair_entered.wait(timeout=5)
                peer_entered.set()

                def update(registry: dict) -> dict:
                    return registry_store.upsert_thread(
                        registry,
                        {
                            "thread_key": "peer",
                            "title": "peer",
                            "updated_at": "2026-06-03T00:00:02Z",
                        },
                    )

                registry_store.update_registry(
                    target_registry / "threads.json",
                    target_registry / "threads.md",
                    update,
                )
                peer_done.set()
            except BaseException as exc:
                errors.append(exc)

        with mock.patch.object(
            sync_bundle,
            "clean_source_path_fields",
            side_effect=slow_clean_source_path_fields,
        ):
            pull = threading.Thread(target=pull_worker)
            peer = threading.Thread(target=peer_worker)
            pull.start()
            self.assertTrue(repair_entered.wait(timeout=5))
            peer.start()
            self.assertTrue(peer_entered.wait(timeout=5))
            host_timeout_sleep(
                0.05,
                reason="prove sync pull repair holds the registry writer lease",
            )
            self.assertFalse(peer_done.is_set())
            release_repair.set()
            pull.join(timeout=5)
            peer.join(timeout=5)

        self.assertFalse(errors)
        self.assertTrue(result["ok"], result)
        self.assertTrue(peer_done.is_set())
        repaired = json.loads((target_registry / "threads.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {entry["thread_key"] for entry in repaired["threads"]},
            {"session:test", "peer"},
        )

    def test_pull_repairs_registry_paths_for_target_device(self) -> None:
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir)
        target_registry = self.root / "target-device-registry"

        result = sync_bundle.pull_sync_bundle(self.sync_dir, target_registry)

        self.assertEqual(result["conflicts"], 0)
        self.assertTrue(result["path_repair"]["ok"])
        repaired = json.loads((target_registry / "threads.json").read_text(encoding="utf-8"))
        paths = repaired["threads"][0]["paths"]
        self.assertEqual(
            Path(paths["registry_thread_store"]).resolve(),
            (target_registry / "threads" / "session-test").resolve(),
        )
        self.assertEqual(
            Path(paths["clean_source_messages_jsonl"]).resolve(),
            (
                target_registry
                / "threads"
                / "session-test"
                / "clean-source"
                / "messages.jsonl"
            ).resolve(),
        )
        self.assertEqual(
            Path(paths["clean_source_turns_jsonl"]).resolve(),
            (
                target_registry
                / "threads"
                / "session-test"
                / "clean-source"
                / "turns.jsonl"
            ).resolve(),
        )
        self.assertEqual(
            Path(paths["clean_source_texture_jsonl"]).resolve(),
            (
                target_registry
                / "threads"
                / "session-test"
                / "clean-source"
                / "source-texture.jsonl"
            ).resolve(),
        )
        self.assertEqual(
            Path(paths["graph_json"]).resolve(),
            (target_registry / "threads" / "session-test" / "index" / "graph.json").resolve(),
        )
        self.assertIsNone(paths["workspace"])
        self.assertIsNone(paths["rollout"])
        self.assertNotIn(str(self.registry), json.dumps(repaired, ensure_ascii=False))

    def test_pull_path_repair_works_on_python39_path_write_text_signature(self) -> None:
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir)
        target_registry = self.root / "python39-target-registry"
        original_write_text = Path.write_text

        def python39_write_text(path, data, encoding=None, errors=None):  # noqa: ANN001
            return original_write_text(path, data, encoding=encoding, errors=errors)

        with mock.patch.object(Path, "write_text", python39_write_text):
            result = sync_bundle.pull_sync_bundle(self.sync_dir, target_registry)

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["path_repair"]["ok"], result["path_repair"])

    def test_pull_repairs_included_raw_rollout_to_target_registry(self) -> None:
        sync_bundle.push_sync_bundle(
            self.registry, self.sync_dir, include_raw=True, allow_plaintext_raw=True
        )
        target_registry = self.root / "target-with-raw"

        result = sync_bundle.pull_sync_bundle(self.sync_dir, target_registry)

        self.assertEqual(result["conflicts"], 0)
        repaired = json.loads((target_registry / "threads.json").read_text(encoding="utf-8"))
        rollout = Path(repaired["threads"][0]["paths"]["rollout"])
        self.assertEqual(
            rollout.resolve(),
            (target_registry / "raw-rollouts" / "session-test.jsonl").resolve(),
        )
        self.assertTrue(rollout.exists())

    def test_pull_fails_when_registry_path_repair_fails(self) -> None:
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir)
        synced_registry = json.loads(
            (self.sync_dir / "registry" / "threads.json").read_text(encoding="utf-8")
        )
        synced_registry["threads"][0]["thread_key"] = "missing-thread"
        synced_registry_path = self.sync_dir / "registry" / "threads.json"
        synced_registry_path.write_text(
            json.dumps(synced_registry, ensure_ascii=False),
            encoding="utf-8",
        )
        manifest_path = self.sync_dir / sync_bundle.SYNC_MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in manifest["files"]:
            if item["path"] == "registry/threads.json":
                item["size"] = synced_registry_path.stat().st_size
                item["sha256"] = sync_bundle.file_sha256(synced_registry_path)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

        result = sync_bundle.pull_sync_bundle(self.sync_dir, self.root / "target-broken-registry")

        self.assertFalse(result["ok"])
        self.assertEqual(result["conflicts"], 0)
        self.assertFalse(result["path_repair"]["ok"])
        self.assertEqual(result["path_repair"]["issues"][0]["code"], "missing_thread_store")

    def test_repair_reports_tampered_synced_file(self) -> None:
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir)
        target = self.sync_dir / "registry" / "threads.json"
        target.write_text("tampered\n", encoding="utf-8")

        result = sync_bundle.repair_sync_bundle(self.sync_dir)

        self.assertFalse(result["ok"])
        self.assertEqual(result["issues"][0]["code"], "hash_mismatch")
        self.assertEqual(result["issues"][0]["path"], "registry/threads.json")

    def test_pull_rejects_manifest_path_traversal(self) -> None:
        self.sync_dir.mkdir()
        outside = self.root / "outside.json"
        (self.sync_dir / sync_bundle.SYNC_MANIFEST_NAME).write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "files": [{"path": "../outside.json", "sha256": "bad", "size": 1}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        outside.write_text("malicious", encoding="utf-8")

        with self.assertRaises(ValueError):
            sync_bundle.pull_sync_bundle(self.sync_dir, self.root / "target-registry")

    def test_push_without_include_raw_removes_previous_managed_raw_rollouts(self) -> None:
        sync_bundle.push_sync_bundle(
            self.registry, self.sync_dir, include_raw=True, allow_plaintext_raw=True
        )
        raw_files = list((self.sync_dir / "raw-rollouts").glob("*.jsonl"))
        self.assertEqual(len(raw_files), 1)

        sync_bundle.push_sync_bundle(self.registry, self.sync_dir, include_raw=False)

        manifest = json.loads(
            (self.sync_dir / sync_bundle.SYNC_MANIFEST_NAME).read_text(encoding="utf-8")
        )
        self.assertFalse(manifest["raw_rollout_included"])
        self.assertFalse((self.sync_dir / "raw-rollouts").exists())

    def test_push_refuses_to_clear_existing_managed_dirs_without_manifest(self) -> None:
        unmanaged_registry = self.sync_dir / "registry"
        unmanaged_registry.mkdir(parents=True)
        sentinel = unmanaged_registry / "sentinel.txt"
        sentinel.write_text("do not delete\n", encoding="utf-8")

        result = sync_bundle.push_sync_bundle(self.registry, self.sync_dir)

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "managed_sync_dir_collision")
        self.assertFalse(result["write_boundary"]["written"])
        self.assertEqual(result["recovery_actions"][0]["command"], "aippocampus sync repair --sync-dir <sync-dir> --json")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not delete\n")

    def test_push_refuses_when_managed_dir_overlaps_registry_root_even_with_manifest(self) -> None:
        sync_root = self.root
        manifest = {
            "schema_version": sync_bundle.SYNC_SCHEMA_VERSION,
            "kind": "aippocampus_sync_bundle",
            "files": [],
        }
        (sync_root / sync_bundle.SYNC_MANIFEST_NAME).write_text(
            json.dumps(manifest, ensure_ascii=False),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "overlaps registry root"):
            sync_bundle.push_sync_bundle(self.registry, sync_root)

        self.assertTrue((self.registry / "threads.json").is_file())

    def test_status_reports_invalid_manifest_instead_of_treating_it_as_missing(self) -> None:
        self.sync_dir.mkdir()
        manifest_path = self.sync_dir / sync_bundle.SYNC_MANIFEST_NAME
        manifest_path.write_text("{not json", encoding="utf-8")

        status = sync_bundle.status_sync_bundle(self.sync_dir)
        repair = sync_bundle.repair_sync_bundle(self.sync_dir)

        self.assertTrue(status["manifest_exists"])
        self.assertEqual(status["issues"][0]["code"], "invalid_manifest")
        self.assertEqual(status["recovery_actions"][0]["command"], "aippocampus sync repair --sync-dir <sync-dir> --json")
        self.assertFalse(status["write_boundary"]["written"])
        self.assertEqual(repair["issues"][0]["code"], "invalid_manifest")

    def test_status_reports_sync_schema_drift_with_rebuild_card(self) -> None:
        self.sync_dir.mkdir()
        manifest_path = self.sync_dir / sync_bundle.SYNC_MANIFEST_NAME
        manifest_path.write_text(
            json.dumps(
                {
                    "kind": sync_bundle.SYNC_BUNDLE_KIND,
                    "schema_version": sync_bundle.SYNC_SCHEMA_VERSION + 100,
                    "files": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        status = sync_bundle.status_sync_bundle(self.sync_dir)

        self.assertFalse(status["ok"])
        self.assertEqual(status["status"], "unsupported_sync_manifest_schema")
        self.assertEqual(status["issues"][0]["code"], "unsupported_sync_manifest_schema")
        self.assertEqual(status["recovery_actions"][0]["id"], "rebuild_sync_bundle")
        self.assertFalse(status["write_boundary"]["written"])

    def test_plaintext_push_rejects_raw_rollout_without_debug_override(self) -> None:
        with self.assertRaisesRegex(ValueError, "raw_requires_encryption"):
            sync_bundle.push_sync_bundle(self.registry, self.sync_dir, include_raw=True)

    def test_cross_device_sync_smoke_models_device_and_path_boundaries(self) -> None:
        result = smoke_cross_device_sync.run_cross_device_sync_smoke(ROOT)

        self.assertTrue(result["ok"], result.get("failures"))
        self.assertTrue(result["claims"]["single_machine_dual_device_model"])
        self.assertTrue(result["claims"]["cross_os_path_shape_model"])
        self.assertFalse(result["claims"]["physical_second_machine"])
        self.assertFalse(result["claims"]["real_cloud_backend"])
        self.assertGreater(result["steps"]["push_device_a"]["file_count"], 0)
        self.assertGreater(
            result["steps"]["push_raw_opt_in"]["file_count"],
            result["steps"]["push_device_a"]["file_count"],
        )
        self.assertIsNone(result["observed"]["portable_paths"]["workspace"])
        self.assertIsNone(result["observed"]["portable_paths"]["rollout"])
        self.assertIn(
            "registry/threads/", result["observed"]["portable_paths"]["clean_source_messages_jsonl"]
        )
        self.assertGreaterEqual(result["observed"]["device_b_conflict_count"], 1)
        self.assertGreaterEqual(result["observed"]["device_a_conflict_count"], 1)
        self.assertTrue(
            result["observed"]["raw_target_rollout"]
            .replace("\\", "/")
            .endswith("raw-rollouts/session-cross-device-smoke.jsonl")
        )

    def test_alternate_runtime_validation_requires_runtime_local_locators(self) -> None:
        target = self.root / "runtime-target" / "threads.json"
        runtime_root = "/work/docker-target-registry"
        target.parent.mkdir(parents=True)
        target.write_text(
            json.dumps(
                {
                    "threads": [
                        {
                            "thread_key": "session:cross-device-smoke",
                            "paths": {
                                "workspace": None,
                                "registry_thread_store": f"{runtime_root}/threads/session-cross-device-smoke",
                                "clean_source_messages_jsonl": f"{runtime_root}/threads/session-cross-device-smoke/clean-source/messages.jsonl",
                                "clean_source_turns_jsonl": f"{runtime_root}/threads/session-cross-device-smoke/clean-source/turns.jsonl",
                                "graph_json": f"{runtime_root}/threads/session-cross-device-smoke/index/graph.json",
                                "rollout": None,
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = smoke_alternate_runtime_sync.validate_target_registry(
            target,
            runtime_root_marker=runtime_root,
        )

        self.assertTrue(result["ok"], result.get("failures"))

    def test_alternate_runtime_smoke_skips_missing_runtime_unless_required(self) -> None:
        with mock.patch.object(
            smoke_alternate_runtime_sync, "docker_available", return_value=(False, "docker_missing")
        ):
            skipped = smoke_alternate_runtime_sync.run_alternate_runtime_sync_smoke(
                ROOT,
                runtime="docker",
                require_runtime=False,
            )
            required = smoke_alternate_runtime_sync.run_alternate_runtime_sync_smoke(
                ROOT,
                runtime="docker",
                require_runtime=True,
            )

        self.assertTrue(skipped["ok"])
        self.assertFalse(skipped["claims"]["alternate_runtime_executed"])
        self.assertTrue(skipped["runtimes"][0]["skipped"])
        self.assertFalse(required["ok"])
        self.assertFalse(required["claims"]["alternate_runtime_executed"])

    def test_alternate_runtime_wsl_path_failure_is_structured_skip(self) -> None:
        with (
            mock.patch.object(
                smoke_alternate_runtime_sync, "wsl_available", return_value=(True, "python3")
            ),
            mock.patch.object(
                smoke_alternate_runtime_sync,
                "wsl_paths",
                side_effect=RuntimeError("path translation failed"),
            ),
        ):
            result = smoke_alternate_runtime_sync.run_alternate_runtime_sync_smoke(
                ROOT, runtime="wsl"
            )

        self.assertTrue(result["ok"])
        self.assertFalse(result["claims"]["alternate_runtime_executed"])
        self.assertTrue(result["runtimes"][0]["skipped"])
        self.assertIn("path translation failed", result["runtimes"][0]["reason"])

if __name__ == "__main__":
    unittest.main()
