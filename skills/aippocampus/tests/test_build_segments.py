from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import build_segments  # noqa: E402


class BuildSegmentsTests(unittest.TestCase):
    def test_failed_rebuild_preserves_existing_segments_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd = root / "workspace"
            cwd.mkdir()
            rollout = root / "rollout-test.jsonl"
            rollout.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "session_meta", "payload": {"id": "test", "cwd": str(cwd)}}),
                        json.dumps({"type": "event_msg", "payload": {"type": "user_message", "message": "hello"}}),
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
            with patch.object(sys, "argv", argv), patch.object(
                build_segments,
                "make_sqlite",
                side_effect=RuntimeError("simulated index failure"),
            ):
                with self.assertRaises(RuntimeError):
                    build_segments.main()

            self.assertTrue((old_segment / "sentinel.txt").exists())
            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 0)


if __name__ == "__main__":
    unittest.main()
