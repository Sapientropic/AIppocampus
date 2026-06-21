from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aippocampus_runtime.core import default_thread_clean_source_dir
from aippocampus_runtime.source import emergency_snapshot


def write_rollout(path: Path, cwd: Path, *, session_id: str = "snap-session") -> None:
    rows = [
        {
            "type": "session_meta",
            "timestamp": "2026-06-07T00:00:00Z",
            "payload": {"id": session_id, "cwd": str(cwd)},
        },
        {
            "type": "event_msg",
            "timestamp": "2026-06-07T00:00:01Z",
            "payload": {"type": "user_message", "message": "first user"},
        },
        {
            "type": "event_msg",
            "timestamp": "2026-06-07T00:00:02Z",
            "payload": {
                "type": "agent_message",
                "phase": "commentary",
                "message": "routine commentary should drop",
            },
        },
        {
            "type": "response_item",
            "timestamp": "2026-06-07T00:00:03Z",
            "payload": {
                "type": "function_call_output",
                "output": "tool payload should never appear",
            },
        },
        {
            "type": "event_msg",
            "timestamp": "2026-06-07T00:00:04Z",
            "payload": {
                "type": "agent_message",
                "phase": "final_answer",
                "message": "first final",
            },
        },
        {
            "type": "event_msg",
            "timestamp": "2026-06-07T00:00:05Z",
            "payload": {"type": "user_message", "message": "second user visible"},
        },
        {
            "type": "event_msg",
            "timestamp": "2026-06-07T00:00:06Z",
            "payload": {
                "type": "agent_message",
                "phase": "commentary",
                "message": "second routine commentary without final should still drop",
            },
        },
    ]
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

class EmergencySnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cwd = self.root / "workspace"
        self.cwd.mkdir()
        self.rollout = self.root / "rollout.jsonl"
        write_rollout(self.rollout, self.cwd)
        self.registry = self.root / "registry"
        self.env_patch = mock.patch.dict(
            os.environ,
            {"AIPPOCAMPUS_REGISTRY_DIR": str(self.registry)},
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.tmp.cleanup()

    def test_precompact_snapshot_writes_bounded_visible_tail_to_thread_store(self) -> None:
        result = emergency_snapshot.create_emergency_snapshot(
            self.cwd,
            rollout=self.rollout,
            max_messages=4,
            max_bytes=10_000,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["message_count"], 3)
        self.assertEqual(result["turn_count"], 2)
        snapshot_path = Path(result["snapshot_path"])
        latest_path = Path(result["latest_path"])
        self.assertTrue(snapshot_path.is_file())
        self.assertTrue(latest_path.is_file())
        self.assertTrue(snapshot_path.resolve().is_relative_to(self.registry.resolve()))
        self.assertFalse(snapshot_path.resolve().is_relative_to(self.cwd.resolve()))

        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        texts = [item["text"] for item in payload["messages"]]
        self.assertEqual(texts, ["first user", "first final", "second user visible"])
        self.assertNotIn("routine commentary should drop", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn("tool payload should never appear", json.dumps(payload, ensure_ascii=False))
        self.assertEqual(payload["authority"], "emergency_bridge_not_clean_source")
        self.assertEqual(payload["source"]["thread_key"], "session:snap-session")
        self.assertIsInstance(payload["source"]["rollout_ref_sha256"], str)

    def test_snapshot_diagnostic_omits_private_text_and_paths(self) -> None:
        result = emergency_snapshot.create_emergency_snapshot(
            self.cwd,
            rollout=self.rollout,
            max_messages=4,
            max_bytes=10_000,
        )

        diagnostic = emergency_snapshot.public_snapshot_diagnostic(result)
        rendered = json.dumps(diagnostic, ensure_ascii=False)
        self.assertTrue(diagnostic["ok"])
        self.assertEqual(diagnostic["message_count"], 3)
        self.assertIn("artifact", diagnostic)
        self.assertNotIn("first user", rendered)
        self.assertNotIn(str(self.cwd), rendered)
        self.assertNotIn(str(self.rollout), rendered)

    def test_snapshot_respects_message_and_byte_caps(self) -> None:
        result = emergency_snapshot.create_emergency_snapshot(
            self.cwd,
            rollout=self.rollout,
            max_messages=1,
            max_bytes=6,
        )

        payload = json.loads(Path(result["snapshot_path"]).read_text(encoding="utf-8"))
        self.assertEqual([item["text"] for item in payload["messages"]], ["second"])
        self.assertEqual(payload["message_count"], 1)
        self.assertLessEqual(payload["text_bytes"], 6)

    def test_snapshot_zero_message_cap_writes_empty_bridge(self) -> None:
        result = emergency_snapshot.create_emergency_snapshot(
            self.cwd,
            rollout=self.rollout,
            max_messages=0,
            max_bytes=10_000,
        )

        payload = json.loads(Path(result["snapshot_path"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["messages"], [])
        self.assertEqual(payload["message_count"], 0)

    def test_snapshot_skips_turns_already_represented_in_clean_source(self) -> None:
        provider = emergency_snapshot.codex_provider(emergency_snapshot.codex_home())
        messages, _ = provider.read_normalized_messages(self.rollout, include_tools=False)
        represented = [
            item
            for item in messages
            if item.get("turn_index") == 1 and (item.get("role") == "user" or item.get("is_final"))
        ]
        clean_dir = default_thread_clean_source_dir(self.cwd, self.rollout)
        clean_dir.mkdir(parents=True, exist_ok=True)
        with (clean_dir / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for item in represented:
                f.write(
                    json.dumps(
                        {
                            "role": item["role"],
                            "source_ref": item["source_ref"],
                            "source_line": item["line"],
                            "text_sha1": item["sha1"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        result = emergency_snapshot.create_emergency_snapshot(
            self.cwd,
            rollout=self.rollout,
            max_messages=4,
            max_bytes=10_000,
        )

        payload = json.loads(Path(result["snapshot_path"]).read_text(encoding="utf-8"))
        self.assertEqual([item["text"] for item in payload["messages"]], ["second user visible"])

    def test_snapshot_reports_clean_source_loss_while_skipping_valid_represented_turns(self) -> None:
        provider = emergency_snapshot.codex_provider(emergency_snapshot.codex_home())
        messages, _ = provider.read_normalized_messages(self.rollout, include_tools=False)
        represented = [
            item
            for item in messages
            if item.get("turn_index") == 1 and (item.get("role") == "user" or item.get("is_final"))
        ]
        clean_dir = default_thread_clean_source_dir(self.cwd, self.rollout)
        clean_dir.mkdir(parents=True, exist_ok=True)
        with (clean_dir / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            f.write("{bad-json}\n")
            for item in represented:
                f.write(
                    json.dumps(
                        {
                            "role": item["role"],
                            "source_ref": item["source_ref"],
                            "source_line": item["line"],
                            "text_sha1": item["sha1"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        result = emergency_snapshot.create_emergency_snapshot(
            self.cwd,
            rollout=self.rollout,
            max_messages=4,
            max_bytes=10_000,
        )
        diagnostic = emergency_snapshot.public_snapshot_diagnostic(result)

        self.assertEqual(result["clean_source_jsonl_loss"]["invalid_json_line_count"], 1)
        self.assertEqual(diagnostic["clean_source_jsonl_loss"]["invalid_json_line_count"], 1)
        payload = json.loads(Path(result["snapshot_path"]).read_text(encoding="utf-8"))
        self.assertEqual([item["text"] for item in payload["messages"]], ["second user visible"])

    def test_latest_snapshot_diagnostic_reports_existing_pointer_without_raw_text(self) -> None:
        created = emergency_snapshot.create_emergency_snapshot(
            self.cwd,
            rollout=self.rollout,
            max_messages=4,
            max_bytes=10_000,
        )

        latest = emergency_snapshot.latest_emergency_snapshot_diagnostic(
            self.cwd,
            rollout=self.rollout,
        )

        self.assertTrue(latest["ok"])
        self.assertEqual(latest["snapshot_id"], created["snapshot_id"])
        rendered = json.dumps(latest, ensure_ascii=False)
        self.assertNotIn("first final", rendered)
        self.assertNotIn(str(self.rollout), rendered)

if __name__ == "__main__":
    unittest.main()
