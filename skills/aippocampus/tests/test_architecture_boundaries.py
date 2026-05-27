from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import aippocampus_prompt_hook as prompt_hook  # noqa: E402
import sync_vault  # noqa: E402


def source_text(module: object) -> str:
    return Path(module.__file__).read_text(encoding="utf-8")


def line_count(module: object) -> int:
    return len(source_text(module).splitlines())


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_sync_vault_is_orchestration_not_dashboard_renderer(self) -> None:
        text = source_text(sync_vault)

        self.assertLessEqual(line_count(sync_vault), 260)
        self.assertNotIn("def html_dashboard", text)
        self.assertNotIn("def dashboard_css", text)
        self.assertNotIn("def dashboard_interaction_script", text)
        self.assertNotIn("def anchor_note", text)
        self.assertNotIn("def health_note", text)

    def test_prompt_hook_entrypoint_is_glue_not_recall_engine(self) -> None:
        text = source_text(prompt_hook)

        self.assertLessEqual(line_count(prompt_hook), 260)
        self.assertNotIn("def score_candidates", text)
        self.assertNotIn("def collect_evidence", text)
        self.assertNotIn("def should_suppress", text)
        self.assertNotIn("def merge_timeline_candidates", text)
        self.assertNotIn("def should_run_semantic_gate", text)

    def test_prompt_decision_module_does_not_import_hook_glue(self) -> None:
        decision_path = SCRIPTS / "prompt_recall_decision.py"
        text = decision_path.read_text(encoding="utf-8")

        self.assertNotIn("from aippocampus_prompt_hook import", text)
        self.assertNotIn("import aippocampus_prompt_hook", text)

    def test_prompt_hook_exits_zero_when_split_helper_install_lags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            shutil.copy2(
                SCRIPTS / "aippocampus_prompt_hook.py", tmp_path / "aippocampus_prompt_hook.py"
            )
            shutil.copy2(SCRIPTS / "aippocampuslib.py", tmp_path / "aippocampuslib.py")
            env = {**os.environ, "CODEX_HOME": str(tmp_path / "codex-home")}
            payload = json.dumps({"prompt": "继续清债", "cwd": str(ROOT)}, ensure_ascii=False)

            proc = subprocess.run(
                [sys.executable, str(tmp_path / "aippocampus_prompt_hook.py")],
                input=payload,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                env=env,
                check=False,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
