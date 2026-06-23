from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime.recall import segment_builder as build_segments


class BuildSegmentsTests(unittest.TestCase):
    def _message(self, line: int, turn_index: int, role: str = "assistant") -> dict:
        return {
            "line": line,
            "timestamp": f"2026-06-05T00:00:0{line}Z",
            "role": role,
            "kind": "user_message" if role == "user" else "agent_message",
            "phase": "final_answer" if role == "assistant" else "",
            "turn_index": turn_index,
            "is_final": role == "assistant",
            "sha1": f"sha-{line}",
            "text": f"message {line}",
        }

    def _write_rollout(self, path: Path, cwd: Path, marker: str) -> None:
        path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {"type": "session_meta", "payload": {"id": "test", "cwd": str(cwd)}}
                    ),
                    json.dumps(
                        {
                            "type": "event_msg",
                            "payload": {"type": "user_message", "message": f"hello {marker}"},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "event_msg",
                            "payload": {
                                "type": "agent_message",
                                "phase": "final_answer",
                                "message": f"world {marker}",
                            },
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def test_segment_groups_allow_bounded_overshoot_to_keep_normal_turn_together(self) -> None:
        messages = [
            self._message(1, 1, "user"),
            self._message(2, 1, "assistant"),
            self._message(3, 2, "user"),
        ]
        offsets = {1: (0, 20), 2: (20, 40), 3: (40, 50)}

        groups = build_segments.segment_groups(
            messages,
            offsets,
            segment_bytes=25,
            max_messages=1,
        )

        self.assertEqual(len(groups), 2)
        self.assertEqual([item["line"] for item in groups[0]["messages"]], [1, 2])
        self.assertEqual(groups[0]["start_turn_index"], 1)
        self.assertEqual(groups[0]["end_turn_index"], 1)
        self.assertFalse(groups[0]["starts_with_partial_turn"])
        self.assertFalse(groups[0]["ends_with_partial_turn"])
        self.assertGreater(groups[0]["budget_overshoot_bytes"], 0)
        self.assertGreater(groups[0]["budget_overshoot_messages"], 0)
        self.assertEqual(groups[0]["turn_boundary_policy"], "bounded_complete_turn")

    def test_segment_groups_record_timestamp_range_for_temporal_planning(self) -> None:
        messages = [
            self._message(1, 1, "user"),
            self._message(2, 1, "assistant"),
            self._message(3, 2, "user"),
        ]
        offsets = {1: (0, 20), 2: (20, 40), 3: (40, 60)}

        groups = build_segments.segment_groups(
            messages,
            offsets,
            segment_bytes=45,
            max_messages=2,
        )

        self.assertEqual(groups[0]["start_timestamp"], "2026-06-05T00:00:01Z")
        self.assertEqual(groups[0]["end_timestamp"], "2026-06-05T00:00:02Z")
        self.assertEqual(groups[1]["start_timestamp"], "2026-06-05T00:00:03Z")
        self.assertEqual(groups[1]["end_timestamp"], "2026-06-05T00:00:03Z")

    def test_segment_groups_mark_pathological_oversized_turn_partial(self) -> None:
        messages = [
            self._message(1, 1, "user"),
            self._message(2, 1, "assistant"),
            self._message(3, 1, "assistant"),
            self._message(4, 2, "user"),
        ]
        offsets = {1: (0, 12), 2: (12, 24), 3: (24, 36), 4: (36, 48)}

        groups = build_segments.segment_groups(
            messages,
            offsets,
            segment_bytes=15,
            max_messages=1,
        )

        self.assertEqual([[item["line"] for item in group["messages"]] for group in groups], [[1, 2], [3], [4]])
        self.assertFalse(groups[0]["starts_with_partial_turn"])
        self.assertTrue(groups[0]["ends_with_partial_turn"])
        self.assertEqual(groups[0]["partial_turn_indices"], [1])
        self.assertEqual(groups[0]["turn_boundary_policy"], "forced_partial_turn")
        self.assertEqual(groups[0]["partial_turn_reason"], "turn_exceeds_bounded_overshoot")
        self.assertTrue(groups[1]["starts_with_partial_turn"])
        self.assertFalse(groups[1]["ends_with_partial_turn"])
        self.assertEqual(groups[1]["partial_turn_indices"], [1])
        self.assertEqual(groups[1]["turn_boundary_policy"], "forced_partial_turn")
        self.assertEqual(groups[1]["partial_turn_reason"], "turn_exceeds_bounded_overshoot")

    def test_rebuild_lease_rejects_concurrent_writer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "segments"
            with build_segments.rebuild_lease(output_dir):
                with self.assertRaisesRegex(RuntimeError, "lease already held"):
                    with build_segments.rebuild_lease(output_dir):
                        pass

    def test_rebuild_lease_recovers_stale_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "segments"
            output_dir.mkdir()
            lease = output_dir / build_segments.REBUILD_LEASE_NAME
            lease.write_text('{"pid": 123}', encoding="utf-8")
            stale_time = time.time() - 60
            os.utime(lease, (stale_time, stale_time))

            with build_segments.rebuild_lease(output_dir, stale_after_seconds=1) as acquired:
                self.assertEqual(acquired, lease)
                self.assertTrue(lease.exists())

            self.assertFalse(lease.exists())

    def test_failed_rebuild_preserves_existing_segments_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd = root / "workspace"
            cwd.mkdir()
            rollout = root / "rollout-test.jsonl"
            rollout.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {"type": "session_meta", "payload": {"id": "test", "cwd": str(cwd)}}
                        ),
                        json.dumps(
                            {
                                "type": "event_msg",
                                "payload": {"type": "user_message", "message": "hello"},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "event_msg",
                                "payload": {
                                    "type": "agent_message",
                                    "phase": "final_answer",
                                    "message": "world",
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            output_dir = root / "segments"
            old_segment = output_dir / "seg-0001"
            old_segment.mkdir(parents=True)
            (old_segment / "sentinel.txt").write_text("last-known-good", encoding="utf-8")
            (output_dir / "manifest.json").write_text(
                json.dumps({"schema_version": 0, "segment_count": 1}),
                encoding="utf-8",
            )

            argv = [
                "build_segments.py",
                "--cwd",
                str(cwd),
                "--rollout",
                str(rollout),
                "--output-dir",
                str(output_dir),
                "--no-rag-cache",
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(
                    build_segments,
                    "make_sqlite",
                    side_effect=RuntimeError("simulated index failure"),
                ),
            ):
                with self.assertRaises(RuntimeError):
                    build_segments.main()

            self.assertTrue((old_segment / "sentinel.txt").exists())
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 0)

    def test_rebuild_publishes_generation_pointer_and_keeps_old_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd = root / "workspace"
            cwd.mkdir()
            rollout = root / "rollout-test.jsonl"
            output_dir = root / "segments"

            self._write_rollout(rollout, cwd, "old")
            argv = [
                "build_segments.py",
                "--cwd",
                str(cwd),
                "--rollout",
                str(rollout),
                "--output-dir",
                str(output_dir),
                "--no-rag-cache",
            ]
            with (
                patch.object(sys, "argv", argv),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                build_segments.main()

            pointer_path = output_dir / "segments.pointer.json"
            first_pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            first_generation = first_pointer["current_generation"]
            first_manifest_path = output_dir / first_pointer["current"]
            first_manifest = json.loads(first_manifest_path.read_text(encoding="utf-8"))
            first_sqlite = Path(first_manifest["segments"][0]["sqlite"])

            self.assertEqual(first_manifest_path.name, "manifest.json")
            self.assertEqual(first_manifest_path.parent.name, first_generation)
            self.assertEqual(first_manifest_path.parent.parent.name, "generations")
            self.assertTrue(first_sqlite.is_file())
            self.assertEqual(first_pointer["last_known_good_generation"], first_generation)
            self.assertEqual(first_pointer["compatibility_path"], "manifest.json")
            self.assertTrue((output_dir / "manifest.json").is_file())
            self.assertEqual(first_manifest["segments"][0]["start_turn_index"], 1)
            self.assertEqual(first_manifest["segments"][0]["end_turn_index"], 1)
            self.assertFalse(first_manifest["segments"][0]["starts_with_partial_turn"])
            self.assertFalse(first_manifest["segments"][0]["ends_with_partial_turn"])
            self.assertEqual(first_manifest["segments"][0]["partial_turn_indices"], [])

            self._write_rollout(rollout, cwd, "new")
            with (
                patch.object(sys, "argv", argv),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                build_segments.main()

            second_pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            second_manifest_path = output_dir / second_pointer["current"]
            self.assertNotEqual(second_pointer["current_generation"], first_generation)
            self.assertEqual(second_pointer["last_known_good_generation"], first_generation)
            self.assertTrue(first_manifest_path.is_file())
            self.assertTrue(first_sqlite.is_file())
            self.assertTrue(second_manifest_path.is_file())

    def test_pointer_publish_failure_preserves_previous_manifest_and_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "segments"
            old_gen = output_dir / "generations" / "gen_old"
            old_gen.mkdir(parents=True)
            (old_gen / "manifest.json").write_text(
                json.dumps({"schema_version": 0, "generation_id": "gen_old"}),
                encoding="utf-8",
            )
            (output_dir / "manifest.json").write_text(
                json.dumps({"schema_version": 0, "generation_id": "gen_old"}),
                encoding="utf-8",
            )
            (output_dir / "segments.pointer.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "aippocampus_segments_pointer",
                        "current_generation": "gen_old",
                        "last_known_good_generation": "gen_old",
                        "current": "generations/gen_old/manifest.json",
                        "last_known_good": "generations/gen_old/manifest.json",
                        "stable": "manifest.json",
                    }
                ),
                encoding="utf-8",
            )
            staging = output_dir / ".rebuild-test"
            staged_segment = staging / "seg-0001"
            staged_segment.mkdir(parents=True)
            (staged_segment / "messages.jsonl").write_text("{}", encoding="utf-8")
            generation_dir = output_dir / "generations" / "gen_new"
            generation_dir.mkdir(parents=True)
            original_write = build_segments.write_json_atomic

            def fail_on_pointer(path: Path, payload: dict) -> None:
                if path.name == "segments.pointer.json":
                    raise RuntimeError("simulated pointer write failure")
                original_write(path, payload)

            with patch.object(build_segments, "write_json_atomic", side_effect=fail_on_pointer):
                with self.assertRaisesRegex(RuntimeError, "pointer write failure"):
                    build_segments.install_staged_segments(
                        staging,
                        output_dir,
                        generation_dir,
                        {"schema_version": 1, "created_at": "2026-06-05T00:00:00Z", "segments": []},
                    )

            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            pointer = json.loads(
                (output_dir / "segments.pointer.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["generation_id"], "gen_old")
            self.assertEqual(pointer["current_generation"], "gen_old")
            self.assertFalse(generation_dir.exists())

if __name__ == "__main__":
    unittest.main()
