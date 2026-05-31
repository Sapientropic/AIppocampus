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
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import diagnose_hooks as diagnose  # noqa: E402
from aippocampus_runtime.hooks import diagnose as packaged_diagnose  # noqa: E402


class HookDiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_top_level_script_is_compatibility_shim_for_package_owner(self) -> None:
        self.assertIs(diagnose.diagnose, packaged_diagnose.diagnose)
        self.assertIs(diagnose.script_paths_from_command, packaged_diagnose.script_paths_from_command)
        self.assertIs(diagnose.main, packaged_diagnose.main)

    def test_script_paths_from_windows_hook_command(self) -> None:
        command = r'& "python.exe" "skills\aippocampus\scripts\aippocampus_prompt_hook.py"'

        paths = diagnose.script_paths_from_command(command)

        self.assertEqual(paths, [Path(r"skills\aippocampus\scripts\aippocampus_prompt_hook.py")])

    def test_diagnose_marks_handler_that_would_exceed_hook_timeout(self) -> None:
        script = self.root / "slow_hook.py"
        script.write_text(
            "import sys, time\nsys.stdin.read()\ntime.sleep(0.2)\nprint('ok')\n",
            encoding="utf-8",
        )
        hooks_json = self.root / "hooks.json"
        hooks_json.write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": (
                                            f'& "{sys.executable}" "{script}"'
                                            if os.name == "nt"
                                            else f'"{sys.executable}" "{script}"'
                                        ),
                                        "timeout": 0.05,
                                    }
                                ]
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )

        result = diagnose.diagnose(
            hooks_json=hooks_json,
            cwd=self.root,
            events={"UserPromptSubmit"},
            run=True,
            prompt="diagnostic prompt",
            last_assistant_message="diagnostic run",
            max_seconds=2.0,
            padding_seconds=1.0,
            warn_ratio=0.8,
        )

        self.assertEqual(result["summary"]["would_timeout"], 1)
        self.assertEqual(result["handlers"][0]["risk"], "would_timeout")
        self.assertFalse(result["handlers"][0]["timed_out"])


if __name__ == "__main__":
    unittest.main()
