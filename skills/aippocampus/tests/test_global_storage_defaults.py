import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_INDEX = ROOT / "scripts" / "build_index.py"


class GlobalStorageDefaultTests(unittest.TestCase):
    def write_rollout(self, cwd: Path, rollout: Path) -> None:
        rows = [
            {"type": "session_meta", "payload": {"id": "storage-session", "cwd": str(cwd)}},
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T00:00:00Z",
                "payload": {"type": "user_message", "message": "记住全局默认存储"},
            },
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T00:00:01Z",
                "payload": {
                    "type": "agent_message",
                    "phase": "final_answer",
                    "message": "默认写入 CodexHome。",
                },
            },
        ]
        rollout.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )

    def test_build_index_defaults_to_global_thread_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd = root / "workspace"
            cwd.mkdir()
            codex_home = root / "codex-home"
            rollout = root / "rollout.jsonl"
            self.write_rollout(cwd, rollout)
            env = {**os.environ, "CODEX_HOME": str(codex_home)}

            proc = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_INDEX),
                    "--cwd",
                    str(cwd),
                    "--rollout",
                    str(rollout),
                    "--json",
                ],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                env=env,
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            manifest = json.loads(proc.stdout)
            sqlite_path = Path(manifest["outputs"]["sqlite"])
            self.assertEqual(manifest["artifact_scope"], "global_thread_store")
            self.assertIn("aippocampus-registry", str(sqlite_path))
            self.assertTrue(sqlite_path.exists())
            self.assertFalse((cwd / ".aippocampus").exists())

    def test_explicit_relative_output_dir_preserves_project_local_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd = root / "workspace"
            cwd.mkdir()
            codex_home = root / "codex-home"
            rollout = root / "rollout.jsonl"
            self.write_rollout(cwd, rollout)
            env = {**os.environ, "CODEX_HOME": str(codex_home)}

            proc = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_INDEX),
                    "--cwd",
                    str(cwd),
                    "--rollout",
                    str(rollout),
                    "--output-dir",
                    ".aippocampus",
                    "--json",
                ],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                env=env,
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            manifest = json.loads(proc.stdout)
            self.assertEqual(manifest["artifact_scope"], "explicit_output_dir")
            self.assertTrue((cwd / ".aippocampus" / "source_index.sqlite").exists())


if __name__ == "__main__":
    unittest.main()
