from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

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

from aippocampus_runtime.hooks import diagnose as diagnose_shim  # noqa: E402
from aippocampus_runtime.hooks import diagnose as packaged_diagnose  # noqa: E402

diagnose: Any = diagnose_shim


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
        script = self.root / "aippocampus_prompt_hook.py"
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

    def test_diagnose_blocks_posix_injection_shape_by_default(self) -> None:
        script = self.root / "aippocampus_prompt_hook.py"
        marker = self.root / "ran.txt"
        injected = self.root / "injected.txt"
        script.write_text(
            f"import pathlib, sys\nsys.stdin.read()\npathlib.Path({str(marker)!r}).write_text('ran')\n",
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
                                            f'"{sys.executable}" "{script}" && '
                                            f'"{sys.executable}" -c "open({str(injected)!r}, '
                                            "'w').write('pwned')\""
                                        ),
                                        "timeout": 5,
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

        self.assertEqual(result["summary"]["blocked"], 1)
        self.assertEqual(result["handlers"][0]["risk"], "blocked_untrusted_shell_command")
        self.assertEqual(result["handlers"][0]["reason_code"], "blocked_untrusted_shell_command")
        self.assertFalse(result["handlers"][0]["ran"])
        self.assertFalse(marker.exists())
        self.assertFalse(injected.exists())

    def test_diagnose_blocks_windows_injection_shape_by_default(self) -> None:
        script = self.root / "aippocampus_lifecycle_hook.py"
        marker = self.root / "ran.txt"
        script.write_text(
            f"import pathlib, sys\nsys.stdin.read()\npathlib.Path({str(marker)!r}).write_text('ran')\n",
            encoding="utf-8",
        )
        hooks_json = self.root / "hooks.json"
        hooks_json.write_text(
            json.dumps(
                {
                    "hooks": {
                        "Stop": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": f'& "{sys.executable}" "{script}" ; Write-Output pwned',
                                        "timeout": 5,
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
            events={"Stop"},
            run=True,
            prompt="diagnostic prompt",
            last_assistant_message="diagnostic run",
            max_seconds=2.0,
            padding_seconds=1.0,
            warn_ratio=0.8,
        )

        self.assertEqual(result["summary"]["blocked"], 1)
        self.assertEqual(result["handlers"][0]["risk"], "blocked_untrusted_shell_command")
        self.assertFalse(marker.exists())

    def test_diagnose_blocks_unknown_command_without_shell_metacharacters(self) -> None:
        script = self.root / "ordinary_helper.py"
        marker = self.root / "ran.txt"
        script.write_text(
            f"import pathlib, sys\nsys.stdin.read()\npathlib.Path({str(marker)!r}).write_text('ran')\n",
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
                                        "command": f'"{sys.executable}" "{script}"',
                                        "timeout": 5,
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

        self.assertEqual(result["summary"]["blocked"], 1)
        self.assertEqual(result["handlers"][0]["risk"], "blocked_untrusted_shell_command")
        self.assertFalse(marker.exists())

    def test_diagnose_runs_known_prompt_and_lifecycle_commands_without_shell_by_default(
        self,
    ) -> None:
        prompt_script = self.root / "aippocampus_prompt_hook.py"
        lifecycle_script = self.root / "aippocampus_lifecycle_hook.py"
        prompt_script.write_text(
            "import json, sys\npayload = json.load(sys.stdin)\nprint(payload['hook_event_name'])\n",
            encoding="utf-8",
        )
        lifecycle_script.write_text(
            "import json, sys\npayload = json.load(sys.stdin)\nprint(payload['hook_event_name'])\n",
            encoding="utf-8",
        )
        hooks_json = self.root / "hooks.json"
        prompt_command = (
            f'& "{sys.executable}" "{prompt_script}"'
            if os.name == "nt"
            else f'"{sys.executable}" "{prompt_script}"'
        )
        lifecycle_command = (
            f'& "{sys.executable}" "{lifecycle_script}"'
            if os.name == "nt"
            else f'"{sys.executable}" "{lifecycle_script}"'
        )
        hooks_json.write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {
                                "hooks": [
                                    {"type": "command", "command": prompt_command, "timeout": 5}
                                ]
                            }
                        ],
                        "Stop": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": lifecycle_command,
                                        "timeout": 5,
                                    }
                                ]
                            }
                        ],
                    }
                }
            ),
            encoding="utf-8",
        )

        result = diagnose.diagnose(
            hooks_json=hooks_json,
            cwd=self.root,
            events={"UserPromptSubmit", "Stop"},
            run=True,
            prompt="diagnostic prompt",
            last_assistant_message="diagnostic run",
            max_seconds=2.0,
            padding_seconds=1.0,
            warn_ratio=0.8,
        )

        self.assertEqual(result["summary"]["ran"], 2)
        self.assertEqual(result["summary"]["blocked"], 0)
        by_event = {handler["event"]: handler for handler in result["handlers"]}
        self.assertEqual(by_event["UserPromptSubmit"]["risk"], "ok")
        self.assertEqual(by_event["UserPromptSubmit"]["execution_mode"], "safe_argv")
        self.assertIn("UserPromptSubmit", by_event["UserPromptSubmit"]["stdout_tail"])
        self.assertEqual(by_event["Stop"]["risk"], "ok")
        self.assertEqual(by_event["Stop"]["execution_mode"], "safe_argv")
        self.assertIn("Stop", by_event["Stop"]["stdout_tail"])

    def test_allow_shell_labels_raw_reproduction_as_operator_chosen(self) -> None:
        script = self.root / "aippocampus_prompt_hook.py"
        script.write_text("import sys\nsys.stdin.read()\nprint('ok')\n", encoding="utf-8")
        hooks_json = self.root / "hooks.json"
        command = (
            f'& "{sys.executable}" "{script}"'
            if os.name == "nt"
            else f'"{sys.executable}" "{script}"'
        )
        hooks_json.write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {"hooks": [{"type": "command", "command": command, "timeout": 5}]}
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
            allow_shell=True,
            prompt="diagnostic prompt",
            last_assistant_message="diagnostic run",
            max_seconds=2.0,
            padding_seconds=1.0,
            warn_ratio=0.8,
        )

        self.assertEqual(result["handlers"][0]["risk"], "ok")
        self.assertEqual(result["handlers"][0]["execution_mode"], "unsafe_shell")
        self.assertTrue(result["handlers"][0]["unsafe_operator_chosen"])

    def test_help_text_explains_safe_run_and_raw_shell_reproduction(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "aippocampus_runtime.hooks.diagnose", "--help"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0)
        self.assertIn("--run", proc.stdout)
        self.assertIn("--no-run", proc.stdout)
        self.assertIn("--allow-shell", proc.stdout)
        self.assertIn("safe", proc.stdout.lower())
        self.assertIn("raw shell", proc.stdout.lower())

    def test_diagnose_reports_codex_host_diagnostic_boundary(self) -> None:
        hooks_json = self.root / "hooks.json"
        hooks_json.write_text(json.dumps({"hooks": {}}, ensure_ascii=False), encoding="utf-8")

        result = diagnose.diagnose(
            hooks_json=hooks_json,
            cwd=self.root,
            events={"UserPromptSubmit"},
            run=False,
            prompt="diagnostic prompt",
            last_assistant_message="diagnostic run",
            max_seconds=2.0,
            padding_seconds=1.0,
            warn_ratio=0.8,
        )

        self.assertEqual(
            result["host_integration"],
            {
                "host": "codex",
                "config_surface": "codex_hooks_json",
                "provider_neutral": False,
                "unsupported_hosts": ["claude-code", "generic-jsonl"],
            },
        )


if __name__ == "__main__":
    unittest.main()
