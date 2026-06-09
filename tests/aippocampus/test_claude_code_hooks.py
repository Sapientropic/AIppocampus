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
        self.assertIn("no_configuration_mutating_installer", status["cannot_claim"])
        self.assertFalse(dry_run["would_write"])
        self.assertIn("handler_command", dry_run)
        self.assertIn("command_resolvable", dry_run["handler_command"])
        self.assertFalse(dry_run["handler_command"]["resolved_executable_path_emitted"])
        self.assertEqual(dry_run["rollback"], "remove the displayed handlers from the selected Claude settings file")
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
