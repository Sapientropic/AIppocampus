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

import install_aippocampus_lifecycle_hook as installer  # noqa: E402


class InstallMemoryMaintenanceHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.hooks_json = Path(self.tmp.name) / "hooks.json"
        self.script = SCRIPTS / "aippocampus_lifecycle_hook.py"
        self.hooks_json.write_text(
            json.dumps(
                {
                    "hooks": {
                        "Stop": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python existing_stop.py",
                                        "timeout": 30,
                                    }
                                ]
                            }
                        ],
                        "UserPromptSubmit": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python aippocampus_prompt_hook.py",
                                        "timeout": 5,
                                    }
                                ]
                            }
                        ],
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def read_hooks(self) -> dict:
        return json.loads(self.hooks_json.read_text(encoding="utf-8"))

    def test_generated_command_is_windows_shell_safe(self) -> None:
        command = installer.command_for(self.script)

        if os.name == "nt":
            self.assertTrue(command.startswith("& "), command)
        else:
            self.assertFalse(command.startswith("& "), command)
        self.assertIn(str(self.script.resolve()), command)

    def test_install_preserves_existing_hooks_and_is_idempotent(self) -> None:
        first = installer.install(self.hooks_json, self.script, timeout=12)
        second = installer.install(self.hooks_json, self.script, timeout=12)

        data = self.read_hooks()["hooks"]
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertIn("SessionStart", data)
        self.assertIn("Stop", data)
        self.assertIn("PreCompact", data)
        self.assertIn("PostCompact", data)
        stop_commands = [handler["command"] for group in data["Stop"] for handler in group["hooks"]]
        self.assertIn("python existing_stop.py", stop_commands)
        self.assertEqual(sum("aippocampus_lifecycle_hook.py" in cmd for cmd in stop_commands), 1)
        prompt_commands = [
            handler["command"] for group in data["UserPromptSubmit"] for handler in group["hooks"]
        ]
        self.assertEqual(prompt_commands, ["python aippocampus_prompt_hook.py"])

    def test_uninstall_removes_only_maintenance_hooks(self) -> None:
        installer.install(self.hooks_json, self.script, timeout=12)

        result = installer.uninstall(self.hooks_json, self.script)
        data = self.read_hooks()["hooks"]

        self.assertTrue(result["changed"])
        self.assertIn("Stop", data)
        self.assertEqual(data["Stop"][0]["hooks"][0]["command"], "python existing_stop.py")
        self.assertIn("UserPromptSubmit", data)
        self.assertNotIn("SessionStart", data)
        self.assertNotIn("PreCompact", data)
        self.assertNotIn("PostCompact", data)


if __name__ == "__main__":
    unittest.main()
