from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))


class ClaudeCodeHooksTests(unittest.TestCase):
    def run_module(self, *args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "aippocampus_runtime.hooks.claude_code", *args],
            cwd=SCRIPTS,
            input=input_text,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

    def test_status_and_dry_run_report_event_level_boundaries_without_paths(self) -> None:
        from aippocampus_runtime.hooks import claude_code

        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            status = claude_code.status_report(settings_path=settings)
            dry_run = claude_code.dry_run_report(settings_path=settings)

        encoded = json.dumps({"status": status, "dry_run": dry_run}, ensure_ascii=False)
        self.assertEqual(status["host"], "claude-code")
        self.assertEqual(status["settings"]["status"], "not_installed")
        self.assertTrue(status["settings"]["path_redacted"])
        self.assertIn("installable", status["status_vocabulary"])
        self.assertIn("firing", status["status_vocabulary"])
        self.assertEqual(status["events"]["UserPromptSubmit"]["status"], "installable")
        self.assertEqual(status["events"]["Stop"]["status"], "installable")
        self.assertEqual(status["events"]["PostToolUse"]["status"], "unsupported_event")
        self.assertEqual(
            status["agent_next_action"]["command"],
            "aippocampus hooks claude-code dry-run --json",
        )
        self.assertEqual(
            status["foreground_action"]["unsupported_events"]["action"],
            "do_not_install_or_claim_unsupported_events_yet",
        )
        self.assertIn("PostToolUse", status["foreground_action"]["unsupported_events"]["events"])
        self.assertTrue(status["foreground_action"]["claim_boundary"]["no_configuration_mutation_happened"])
        self.assertNotIn("no_configuration_mutating_installer", status["cannot_claim"])
        self.assertFalse(dry_run["would_write"])
        self.assertIn("handler_command", dry_run)
        self.assertIn("command_resolvable", dry_run["handler_command"])
        self.assertFalse(dry_run["handler_command"]["resolved_executable_path_emitted"])
        self.assertEqual(dry_run["rollback_command"], "aippocampus hooks claude-code uninstall --json")
        self.assertEqual(dry_run["install_command"], "aippocampus hooks claude-code install --json")
        self.assertNotIn(str(settings), encoded)

    def test_install_is_idempotent_and_uninstall_preserves_unrelated_settings(self) -> None:
        from aippocampus_runtime.hooks import claude_code

        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(
                json.dumps(
                    {
                        "permissions": {"allow": ["Bash(git status:*)"]},
                        "hooks": {
                            "UserPromptSubmit": [
                                {
                                    "matcher": "",
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": "echo existing",
                                        }
                                    ],
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )

            first = claude_code.install_hooks(settings_path=settings)
            second = claude_code.install_hooks(settings_path=settings)
            status = claude_code.status_report(settings_path=settings)
            removed = claude_code.uninstall_hooks(settings_path=settings)
            final = json.loads(settings.read_text(encoding="utf-8"))

        encoded = json.dumps(
            {"first": first, "second": second, "status": status, "removed": removed},
            ensure_ascii=False,
        )
        self.assertTrue(first["ok"], first)
        self.assertTrue(first["wrote"])
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(status["settings"]["status"], "installed")
        self.assertEqual(status["events"]["UserPromptSubmit"]["status"], "installed")
        self.assertEqual(status["events"]["Stop"]["status"], "installed")
        self.assertTrue(removed["ok"], removed)
        self.assertTrue(removed["changed"])
        self.assertEqual(final["permissions"], {"allow": ["Bash(git status:*)"]})
        self.assertEqual(
            final["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"],
            "echo existing",
        )
        self.assertNotIn("Stop", final["hooks"])
        self.assertNotIn(str(settings), encoded)

    def test_status_card_switches_to_smoke_when_supported_hooks_are_installed(self) -> None:
        from aippocampus_runtime.hooks import claude_code

        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "UserPromptSubmit": [
                                {
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": "aippocampus hooks claude-code handle",
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            status = claude_code.status_report(settings_path=settings)

        self.assertEqual(status["settings"]["status"], "installed")
        self.assertEqual(
            status["agent_next_action"]["command"],
            "aippocampus hooks claude-code smoke --json",
        )
        action_commands = {action["command"] for action in status["safe_next_actions"] if action.get("command")}
        self.assertIn("aippocampus hooks claude-code uninstall --json", action_commands)
        self.assertIn(
            "UserPromptSubmit",
            status["foreground_action"]["supported_installed_or_firing_events"],
        )
        encoded = json.dumps(status, ensure_ascii=False)
        self.assertNotIn(str(settings), encoded)

    def test_malformed_settings_status_is_blocked_without_path_leak_or_crash(self) -> None:
        from aippocampus_runtime.hooks import claude_code

        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text("{not json", encoding="utf-8")

            status = claude_code.status_report(settings_path=settings)
            install = claude_code.install_hooks(settings_path=settings)
            uninstall = claude_code.uninstall_hooks(settings_path=settings)

        encoded = json.dumps(
            {"status": status, "install": install, "uninstall": uninstall},
            ensure_ascii=False,
        )
        self.assertEqual(status["settings"]["status"], "blocked")
        self.assertEqual(status["settings"]["blocker"], "settings_json_unreadable")
        self.assertEqual(status["events"]["UserPromptSubmit"]["status"], "blocked")
        self.assertEqual(status["events"]["Stop"]["blocker"], "settings_json_unreadable")
        self.assertEqual(
            status["agent_next_action"]["id"],
            "repair_claude_code_settings_json",
        )
        self.assertFalse(install["ok"])
        self.assertFalse(uninstall["ok"])
        self.assertEqual(install["error"]["code"], "claude_settings_json_invalid")
        self.assertEqual(uninstall["error"]["code"], "claude_settings_json_invalid")
        self.assertNotIn(str(settings), encoded)

    def test_dry_run_uses_module_fallback_when_console_script_is_not_on_path(self) -> None:
        from aippocampus_runtime.hooks import claude_code

        def fake_which(command: str) -> str | None:
            return "/redacted/python3" if command == "python3" else None

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            claude_code.shutil,
            "which",
            side_effect=fake_which,
        ):
            settings = Path(tmp) / "settings.json"
            dry_run = claude_code.dry_run_report(settings_path=settings)

        command = dry_run["proposed_hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        encoded = json.dumps(dry_run, ensure_ascii=False)
        self.assertEqual(
            command,
            "python3 -m aippocampus_runtime.cli.facade hooks claude-code handle",
        )
        self.assertEqual(dry_run["handler_command"]["command_kind"], "module_fallback")
        self.assertTrue(dry_run["handler_command"]["command_resolvable"])
        self.assertFalse(dry_run["handler_command"]["console_script_resolvable"])
        self.assertTrue(dry_run["handler_command"]["module_fallback_available"])
        self.assertFalse(dry_run["handler_command"]["resolved_executable_path_emitted"])
        self.assertNotIn("/redacted/python3", encoded)

    def test_dry_run_reports_operator_path_blocker_when_no_command_is_resolvable(self) -> None:
        from aippocampus_runtime.hooks import claude_code

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            claude_code.shutil,
            "which",
            return_value=None,
        ):
            settings = Path(tmp) / "settings.json"
            dry_run = claude_code.dry_run_report(settings_path=settings)

        command = dry_run["proposed_hooks"]["Stop"][0]["hooks"][0]["command"]
        self.assertEqual(command, "aippocampus hooks claude-code handle")
        self.assertEqual(dry_run["handler_command"]["command_kind"], "console_script_unverified")
        self.assertFalse(dry_run["handler_command"]["command_resolvable"])
        self.assertFalse(dry_run["handler_command"]["copy_paste_ready"])
        self.assertIn("PATH", dry_run["next_operator_step"])

    def test_synthetic_smoke_handles_claude_events_without_payload_leakage(self) -> None:
        from aippocampus_runtime.hooks import claude_code

        report = claude_code.synthetic_smoke_report()
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertTrue(report["ok"])
        self.assertEqual(report["events"]["UserPromptSubmit"]["exit_code"], 0)
        self.assertEqual(report["events"]["Stop"]["exit_code"], 0)
        self.assertTrue(report["privacy"]["raw_prompt_omitted"])
        self.assertTrue(report["privacy"]["session_id_omitted"])
        self.assertTrue(report["privacy"]["transcript_path_omitted"])
        self.assertNotIn("synthetic prompt marker must not leak", encoded)
        self.assertNotIn("synthetic-session-marker", encoded)
        self.assertNotIn("<redacted:transcript-path>", encoded)

    def test_handle_user_prompt_submit_can_emit_bounded_context_only_when_requested(self) -> None:
        event = {
            "session_id": "synthetic-session-marker",
            "transcript_path": "<redacted:transcript-path>",
            "cwd": "<redacted:cwd>",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "synthetic prompt marker must not leak",
        }

        quiet = self.run_module("handle", input_text=json.dumps(event))
        loud = self.run_module("handle", "--diagnostic-context", input_text=json.dumps(event))

        self.assertEqual(quiet.returncode, 0, quiet.stderr)
        self.assertEqual(quiet.stdout, "")
        self.assertEqual(quiet.stderr, "")
        self.assertEqual(loud.returncode, 0, loud.stderr)
        payload = json.loads(loud.stdout)
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("additionalContext", payload["hookSpecificOutput"])
        combined = loud.stdout + loud.stderr
        self.assertNotIn("synthetic prompt marker must not leak", combined)
        self.assertNotIn("synthetic-session-marker", combined)
        self.assertNotIn("<redacted:transcript-path>", combined)

    def test_cli_smoke_json_is_public_safe(self) -> None:
        proc = self.run_module("smoke", "--json")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["privacy"]["raw_prompt_omitted"])
        self.assertNotIn("synthetic prompt marker must not leak", proc.stdout)


if __name__ == "__main__":
    unittest.main()
