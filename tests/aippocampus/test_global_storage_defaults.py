import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
BUILD_INDEX_CMD = [sys.executable, "-m", "aippocampus_runtime.recall.index_builder"]

from aippocampus_runtime import core


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
                    *BUILD_INDEX_CMD,
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
                cwd=SCRIPTS,
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
                    *BUILD_INDEX_CMD,
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
                cwd=SCRIPTS,
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            manifest = json.loads(proc.stdout)
            self.assertEqual(manifest["artifact_scope"], "explicit_output_dir")
            self.assertTrue((cwd / ".aippocampus" / "source_index.sqlite").exists())

    def test_codex_home_infers_installed_skill_root_when_env_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex-home"
            installed_core = (
                codex_home
                / "skills"
                / "aippocampus"
                / "scripts"
                / "aippocampus_runtime"
                / "core.py"
            )
            installed_core.parent.mkdir(parents=True)
            (codex_home / "config.toml").write_text("", encoding="utf-8")

            with (
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(core, "__file__", str(installed_core)),
            ):
                self.assertEqual(core.codex_home(), codex_home)
                self.assertEqual(
                    core.aippocampus_registry_dir(),
                    codex_home / "aippocampus-registry",
                )

if __name__ == "__main__":
    unittest.main()
