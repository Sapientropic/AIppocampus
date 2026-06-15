from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.hooks import install_action_hint as installer  # noqa: E402


class InstallActionHintHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.codex_home = Path(self.tmp.name) / ".codex"
        self.codex_home.mkdir()
        self.hooks_json = self.codex_home / "hooks.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def read_hooks(self) -> dict:
        return json.loads(self.hooks_json.read_text(encoding="utf-8"))

    def test_install_is_idempotent_and_preserves_existing_surfaces(self) -> None:
        self.hooks_json.write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "prompt"}]}],
                        "Stop": [{"hooks": [{"type": "command", "command": "stop"}]}],
                    }
                }
            ),
            encoding="utf-8",
        )

        first = installer.install(self.hooks_json, timeout=3)
        second = installer.install(self.hooks_json, timeout=3)
        data = self.read_hooks()

        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(first["surface_event"], "PreToolUse")
        self.assertTrue(first["event_supported"])
        self.assertIn("PreToolUse", data["hooks"])
        self.assertEqual(data["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"], "prompt")
        self.assertEqual(data["hooks"]["Stop"][0]["hooks"][0]["command"], "stop")
        action_handlers = data["hooks"]["PreToolUse"][0]["hooks"]
        self.assertEqual(len(action_handlers), 1)
        self.assertIn("aippocampus_runtime.hooks.action_hint", action_handlers[0]["command"])

    def test_status_redacts_paths_and_commands_by_default(self) -> None:
        installer.install(self.hooks_json, timeout=3)

        result = installer.status(self.hooks_json)
        encoded = json.dumps(result, ensure_ascii=False)

        self.assertTrue(result["installed"])
        self.assertEqual(result["path"], "hooks.json")
        self.assertTrue(result["path_redacted"])
        self.assertEqual(result["commands"], ["<redacted:hook-command>"])
        self.assertTrue(result["commands_redacted"])
        self.assertEqual(result["support_status"], "supported_by_codex_hooks_json")
        self.assertNotIn(str(self.codex_home), encoded)
        self.assertNotIn(str(SCRIPTS.resolve()), encoded)

    def test_unsupported_host_status_does_not_pretend_installation(self) -> None:
        result = installer.status(self.hooks_json, host="claude-code")

        self.assertFalse(result["installed"])
        self.assertFalse(result["event_supported"])
        self.assertEqual(result["support_status"], "unsupported_host:claude-code")


if __name__ == "__main__":
    unittest.main()
