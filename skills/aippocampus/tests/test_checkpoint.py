import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "checkpoint.py"
SCRIPTS = SCRIPT.parent
sys.path.insert(0, str(SCRIPTS))

from aippocampuslib import default_thread_index_dir  # noqa: E402


class CheckpointTests(unittest.TestCase):
    def test_append_anchor_uses_portable_source_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            index_dir = cwd / ".aippocampus"
            index_dir.mkdir()
            messages = [
                {"role": "user", "text": "测试 checkpoint source path", "line": 7},
                {"role": "assistant", "text": "ok", "line": 8},
            ]
            (index_dir / "messages.jsonl").write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in messages) + "\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--cwd",
                    str(cwd),
                    "--no-build",
                    "--index-dir",
                    ".aippocampus",
                    "--state",
                    ".aippocampus/checkpoint_state.json",
                    "--append",
                    "--json",
                ],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            anchor_text = (cwd / "thread-anchors.md").read_text(encoding="utf-8")
            self.assertIn(".aippocampus/messages.jsonl lines 7-8", anchor_text)
            self.assertNotIn(str(cwd), anchor_text)

    def test_default_checkpoint_reads_global_thread_store_without_absolute_anchor_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd = root / "workspace"
            cwd.mkdir()
            codex_home = root / "codex-home"
            old_codex_home = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = str(codex_home)
            try:
                index_dir = default_thread_index_dir(cwd)
                index_dir.mkdir(parents=True)
                messages = [
                    {"role": "user", "text": "global checkpoint source", "line": 11},
                    {"role": "assistant", "text": "ok", "line": 12},
                ]
                (index_dir / "messages.jsonl").write_text(
                    "\n".join(json.dumps(item, ensure_ascii=False) for item in messages) + "\n",
                    encoding="utf-8",
                )

                proc = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--cwd",
                        str(cwd),
                        "--no-build",
                        "--append",
                        "--json",
                    ],
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                anchor_text = (cwd / "thread-anchors.md").read_text(encoding="utf-8")
                self.assertIn("$CODEX_HOME/aippocampus-registry/threads/", anchor_text)
                self.assertIn("messages.jsonl lines 11-12", anchor_text)
                self.assertNotIn(str(codex_home), anchor_text)
            finally:
                if old_codex_home is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = old_codex_home


if __name__ == "__main__":
    unittest.main()
