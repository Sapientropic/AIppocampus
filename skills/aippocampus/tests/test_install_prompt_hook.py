from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import install_aippocampus_prompt_hook as installer  # noqa: E402


class InstallAmbientRecallHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.codex_home = Path(self.tmp.name) / ".codex"
        self.codex_home.mkdir()
        self.hooks_json = self.codex_home / "hooks.json"
        self.script = SCRIPTS / "aippocampus_prompt_hook.py"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def read_hooks(self) -> dict:
        return json.loads(self.hooks_json.read_text(encoding="utf-8"))

    def test_install_preserves_existing_hooks_and_is_idempotent(self) -> None:
        self.hooks_json.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PostToolUse": [
                            {
                                "matcher": "Bash",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python existing.py",
                                        "timeout": 30,
                                    }
                                ],
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )

        first = installer.install(self.hooks_json, self.script, timeout=5)
        second = installer.install(self.hooks_json, self.script, timeout=5)

        data = self.read_hooks()
        prompt_hooks = data["hooks"]["UserPromptSubmit"][0]["hooks"]
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(len(prompt_hooks), 1)
        self.assertIn(str(self.script), prompt_hooks[0]["command"])
        self.assertEqual(data["hooks"]["PostToolUse"][0]["hooks"][0]["command"], "python existing.py")

    def test_uninstall_removes_only_ambient_hook(self) -> None:
        installer.install(self.hooks_json, self.script, timeout=5)
        data = self.read_hooks()
        data["hooks"]["UserPromptSubmit"][0]["hooks"].append(
            {
                "type": "command",
                "command": "python other_user_prompt_hook.py",
                "timeout": 10,
            }
        )
        self.hooks_json.write_text(json.dumps(data), encoding="utf-8")

        result = installer.uninstall(self.hooks_json, self.script)

        data = self.read_hooks()
        remaining = data["hooks"]["UserPromptSubmit"][0]["hooks"]
        self.assertTrue(result["changed"])
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["command"], "python other_user_prompt_hook.py")


if __name__ == "__main__":
    unittest.main()
