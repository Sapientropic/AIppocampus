from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync_bundle  # noqa: E402
import smoke_cross_device_sync  # noqa: E402
import smoke_alternate_runtime_sync  # noqa: E402


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

    def test_push_writes_device_neutral_bundle_without_raw_rollout(self) -> None:
        result = sync_bundle.push_sync_bundle(self.registry, self.sync_dir)

        manifest_path = self.sync_dir / sync_bundle.SYNC_MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        relative_paths = {item["path"] for item in manifest["files"]}

        self.assertTrue(result["ok"])
        self.assertFalse(manifest["raw_rollout_included"])
        self.assertIn("registry/threads.json", relative_paths)
        self.assertIn("registry/semantic_triggers.jsonl", relative_paths)
        self.assertIn("registry/working_memory.jsonl", relative_paths)
        self.assertIn("registry/cognitive_map.json", relative_paths)
        self.assertIn("registry/threads/session-test/clean-source/messages.jsonl", relative_paths)
        self.assertIn("registry/threads/session-test/clean-source/semantic-scope-labels.jsonl", relative_paths)
        self.assertIn("registry/threads/session-test/index/manifest.json", relative_paths)
        self.assertNotIn("rollout.jsonl", "\n".join(relative_paths))
        portable_registry = json.loads((self.sync_dir / "registry" / "threads.json").read_text(encoding="utf-8"))
        portable_paths = portable_registry["threads"][0]["paths"]
        self.assertEqual(portable_paths["clean_source_messages_jsonl"], "registry/threads/session-test/clean-source/messages.jsonl")
        self.assertIsNone(portable_paths["workspace"])
        self.assertIsNone(portable_paths["rollout"])

    def test_pull_copies_missing_files_and_preserves_conflicts(self) -> None:
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir)
        target_registry = self.root / "target-registry"
        target_messages = target_registry / "threads" / "session-test" / "clean-source" / "messages.jsonl"
        target_messages.parent.mkdir(parents=True)
        target_messages.write_text("different local content\n", encoding="utf-8")

        result = sync_bundle.pull_sync_bundle(self.sync_dir, target_registry)

        self.assertGreaterEqual(result["copied"], 6)
        self.assertEqual(result["conflicts"], 1)
        self.assertEqual(target_messages.read_text(encoding="utf-8"), "different local content\n")
        conflict_files = list((target_registry / ".sync-conflicts").rglob("messages.jsonl"))
        self.assertEqual(len(conflict_files), 1)
        self.assertIn("source backed", conflict_files[0].read_text(encoding="utf-8"))

    def test_pull_repairs_registry_paths_for_target_device(self) -> None:
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir)
        target_registry = self.root / "target-device-registry"

        result = sync_bundle.pull_sync_bundle(self.sync_dir, target_registry)

        self.assertEqual(result["conflicts"], 0)
        self.assertTrue(result["path_repair"]["ok"])
        repaired = json.loads((target_registry / "threads.json").read_text(encoding="utf-8"))
        paths = repaired["threads"][0]["paths"]
        self.assertEqual(paths["registry_thread_store"], str(target_registry / "threads" / "session-test"))
        self.assertEqual(paths["clean_source_messages_jsonl"], str(target_registry / "threads" / "session-test" / "clean-source" / "messages.jsonl"))
        self.assertEqual(paths["clean_source_turns_jsonl"], str(target_registry / "threads" / "session-test" / "clean-source" / "turns.jsonl"))
        self.assertEqual(paths["graph_json"], str(target_registry / "threads" / "session-test" / "index" / "graph.json"))
        self.assertIsNone(paths["workspace"])
        self.assertIsNone(paths["rollout"])
        self.assertNotIn(str(self.registry), json.dumps(repaired, ensure_ascii=False))

    def test_pull_repairs_included_raw_rollout_to_target_registry(self) -> None:
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir, include_raw=True)
        target_registry = self.root / "target-with-raw"

        result = sync_bundle.pull_sync_bundle(self.sync_dir, target_registry)

        self.assertEqual(result["conflicts"], 0)
        repaired = json.loads((target_registry / "threads.json").read_text(encoding="utf-8"))
        rollout = Path(repaired["threads"][0]["paths"]["rollout"])
        self.assertEqual(rollout, target_registry / "raw-rollouts" / "session-test.jsonl")
        self.assertTrue(rollout.exists())

    def test_pull_fails_when_registry_path_repair_fails(self) -> None:
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir)
        synced_registry = json.loads((self.sync_dir / "registry" / "threads.json").read_text(encoding="utf-8"))
        synced_registry["threads"][0]["thread_key"] = "missing-thread"
        (self.sync_dir / "registry" / "threads.json").write_text(
            json.dumps(synced_registry, ensure_ascii=False),
            encoding="utf-8",
        )

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
        sync_bundle.push_sync_bundle(self.registry, self.sync_dir, include_raw=True)
        raw_files = list((self.sync_dir / "raw-rollouts").glob("*.jsonl"))
        self.assertEqual(len(raw_files), 1)

        sync_bundle.push_sync_bundle(self.registry, self.sync_dir, include_raw=False)

        manifest = json.loads((self.sync_dir / sync_bundle.SYNC_MANIFEST_NAME).read_text(encoding="utf-8"))
        self.assertFalse(manifest["raw_rollout_included"])
        self.assertFalse((self.sync_dir / "raw-rollouts").exists())

    def test_cross_device_sync_smoke_models_device_and_path_boundaries(self) -> None:
        result = smoke_cross_device_sync.run_cross_device_sync_smoke(ROOT)

        self.assertTrue(result["ok"], result.get("failures"))
        self.assertTrue(result["claims"]["single_machine_dual_device_model"])
        self.assertTrue(result["claims"]["cross_os_path_shape_model"])
        self.assertFalse(result["claims"]["physical_second_machine"])
        self.assertFalse(result["claims"]["real_cloud_backend"])
        self.assertEqual(result["steps"]["push_device_a"]["file_count"], 10)
        self.assertEqual(result["steps"]["push_raw_opt_in"]["file_count"], 11)
        self.assertIsNone(result["observed"]["portable_paths"]["workspace"])
        self.assertIsNone(result["observed"]["portable_paths"]["rollout"])
        self.assertIn("registry/threads/", result["observed"]["portable_paths"]["clean_source_messages_jsonl"])
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
        with mock.patch.object(smoke_alternate_runtime_sync, "docker_available", return_value=(False, "docker_missing")):
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
            mock.patch.object(smoke_alternate_runtime_sync, "wsl_available", return_value=(True, "python3")),
            mock.patch.object(smoke_alternate_runtime_sync, "wsl_paths", side_effect=RuntimeError("path translation failed")),
        ):
            result = smoke_alternate_runtime_sync.run_alternate_runtime_sync_smoke(ROOT, runtime="wsl")

        self.assertTrue(result["ok"])
        self.assertFalse(result["claims"]["alternate_runtime_executed"])
        self.assertTrue(result["runtimes"][0]["skipped"])
        self.assertIn("path translation failed", result["runtimes"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
