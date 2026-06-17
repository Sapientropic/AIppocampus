from __future__ import annotations

import contextlib
import io
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

from aippocampus_runtime.hooks import install_lifecycle as installer  # noqa: E402
from aippocampus_runtime.ops import provider_key_bridge  # noqa: E402


class InstallMemoryMaintenanceHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.hooks_json = Path(self.tmp.name) / "hooks.json"
        self.module = installer.DEFAULT_HOOK_MODULE
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
        command = installer.command_for()

        if os.name == "nt":
            self.assertIn("; & ", command)
        else:
            self.assertFalse(command.startswith("& "), command)
            self.assertTrue(command.startswith("PYTHONPATH="), command)
        self.assertIn("-m", command)
        self.assertIn(self.module, command)

    def test_install_preserves_existing_hooks_and_is_idempotent(self) -> None:
        first = installer.install(self.hooks_json, timeout=12)
        second = installer.install(self.hooks_json, timeout=12)

        data = self.read_hooks()["hooks"]
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertIn("SessionStart", data)
        self.assertIn("Stop", data)
        self.assertIn("PreCompact", data)
        self.assertIn("PostCompact", data)
        stop_commands = [handler["command"] for group in data["Stop"] for handler in group["hooks"]]
        self.assertIn("python existing_stop.py", stop_commands)
        self.assertEqual(sum(self.module in cmd for cmd in stop_commands), 1)
        prompt_commands = [
            handler["command"] for group in data["UserPromptSubmit"] for handler in group["hooks"]
        ]
        self.assertEqual(prompt_commands, ["python aippocampus_prompt_hook.py"])

    def test_status_reports_codex_host_integration_boundary(self) -> None:
        result = installer.status(self.hooks_json)

        self.assertEqual(
            result["host_integration"],
            {
                "host": "codex",
                "config_surface": "codex_hooks_json",
                "provider_neutral": False,
                "unsupported_hosts": ["claude-code", "generic-jsonl"],
            },
        )

    def test_public_status_has_foreground_action_card_for_missing_installed_and_partial(self) -> None:
        missing = installer.public_lifecycle_result(installer.status(self.hooks_json))
        self.assertEqual(missing["foreground_action"]["status"], "missing")
        self.assertEqual(missing["agent_next_action"]["id"], "install_lifecycle_hooks")
        self.assertEqual(missing["claim_boundary"], "host_setup_not_memory_evidence")
        self.assertTrue(
            any(action["id"] == "install_lifecycle_hooks" for action in missing["safe_next_actions"])
        )

        installer.install(self.hooks_json, timeout=12)
        installed = installer.public_lifecycle_result(installer.status(self.hooks_json))
        self.assertEqual(installed["foreground_action"]["status"], "installed")
        self.assertEqual(installed["agent_next_action"]["id"], "no_action_needed")
        installed_action_ids = [action["id"] for action in installed["safe_next_actions"]]
        self.assertIn("no_action_needed", installed_action_ids)
        self.assertIn("rollback_lifecycle_hooks", installed_action_ids)

        data = self.read_hooks()
        data["hooks"].pop("PostCompact", None)
        self.hooks_json.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        partial = installer.public_lifecycle_result(installer.status(self.hooks_json))
        encoded = json.dumps(partial, ensure_ascii=False)
        self.assertEqual(partial["foreground_action"]["status"], "partial")
        self.assertEqual(partial["agent_next_action"]["id"], "refresh_lifecycle_hooks")
        self.assertIn("PostCompact", partial["foreground_action"]["missing_events"])
        self.assertNotIn(str(self.hooks_json), encoded)
        self.assertNotIn("aippocampus_runtime.hooks.lifecycle", encoded)

    def test_status_treats_provider_bridge_wrapper_as_installed(self) -> None:
        root = Path(self.tmp.name)
        codex_home = root / "codex-home"
        dotenv = root / "provider.env"
        provider_env_var = "PROVIDER_LIFECYCLE_STATUS_BRIDGE"
        fixture_value = "sk-FAKE_TEST_LIFECYCLE_STATUS_BRIDGE_1234567890"
        dotenv.write_text(f"{provider_env_var}={fixture_value}\n", encoding="utf-8")

        provider_key_bridge.apply_provider_key_bridge(
            target="codex-hooks",
            source="explicit-dotenv",
            provider_env_var=provider_env_var,
            credential_dotenv=dotenv,
            codex_home_path=codex_home,
            hooks_json=self.hooks_json,
        )
        result = installer.status(self.hooks_json)
        encoded = json.dumps(result, ensure_ascii=False)

        self.assertTrue(result["installed"])
        self.assertTrue(result["provider_key_bridge_installed"])
        self.assertTrue(result["installed_via_provider_bridge"])
        self.assertEqual(set(result["events"]), set(installer.EVENTS))
        self.assertEqual(set(result["provider_key_bridge_events"]), set(installer.EVENTS))
        for commands in result["events"].values():
            self.assertEqual(len(commands), 1)
            self.assertIn("aippocampus_provider_bridge_hook.py", commands[0])
        self.assertNotIn(fixture_value, encoded)

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = installer.main(["status", "--hooks-json", str(self.hooks_json)])
        text = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("provider-key bridge: installed", text)
        self.assertIn("already-running hook process: not proven", text)
        self.assertIn("aippocampus doctor provider --json", text)
        self.assertNotIn(fixture_value, text)

    def test_uninstall_removes_only_maintenance_hooks(self) -> None:
        installer.install(self.hooks_json, timeout=12)

        result = installer.uninstall(self.hooks_json)
        data = self.read_hooks()["hooks"]

        self.assertTrue(result["changed"])
        self.assertIn("Stop", data)
        self.assertEqual(data["Stop"][0]["hooks"][0]["command"], "python existing_stop.py")
        self.assertIn("UserPromptSubmit", data)
        self.assertNotIn("SessionStart", data)
        self.assertNotIn("PreCompact", data)
        self.assertNotIn("PostCompact", data)

    def test_text_cli_labels_lifecycle_installer_as_codex_only(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = installer.main(
                [
                    "status",
                    "--hooks-json",
                    str(self.hooks_json),
                ]
            )

        self.assertEqual(code, 0)
        text = stdout.getvalue()
        self.assertIn("Codex lifecycle hooks not installed", text)
        self.assertIn("host: codex", text)
        self.assertIn("host scope: codex_hooks_only", text)
        self.assertIn("config surface: codex_hooks_json", text)
        self.assertIn("provider-neutral: false", text)
        self.assertIn("other hosts: claude-code, generic-jsonl use onboarding/MCP/import routes", text)
        self.assertIn("not a failure", text)
        self.assertNotIn("unsupported host hooks", text)


if __name__ == "__main__":
    unittest.main()
