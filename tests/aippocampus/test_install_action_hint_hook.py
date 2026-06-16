from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.hooks import install_action_hint as installer  # noqa: E402

DEFAULT_CACHE_LABEL = "registry/action-hints/<workspace-scope>/pretooluse-cache.jsonl"


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
        self.assertEqual(result["cache_status"], "with_missing_cache_file")
        self.assertEqual(result["cache_record_count"], 0)
        self.assertEqual(result["support_status"], "supported_by_codex_hooks_json")
        card = result["frontstage_card"]
        self.assertEqual(card["authority"], "navigation_only")
        self.assertTrue(card["fail_open"])
        self.assertTrue(card["optional"])
        self.assertEqual(card["cache_status"], "with_missing_cache_file")
        self.assertEqual(card["cache_path_label"], DEFAULT_CACHE_LABEL)
        self.assertEqual(card["cache_scope"], "current_workspace")
        commands = [step["command"] for step in card["next_steps"]]
        self.assertTrue(any("refresh-cache" in command for command in commands))
        self.assertTrue(any("--write --json" in command for command in commands))
        self.assertTrue(any("uninstall" in command for command in commands))
        self.assertNotIn("<local-cache.jsonl>", json.dumps(card, ensure_ascii=False))
        self.assertNotIn(str(self.codex_home), encoded)
        self.assertNotIn(str(SCRIPTS.resolve()), encoded)

    def test_status_reports_cache_records_without_leaking_cache_path(self) -> None:
        cache_path = self.codex_home / "action-hints.jsonl"
        cache_path.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_action_hint_prepared_cache",
                    "records": [
                        {
                            "kind": "aippocampus_action_hint_prepared_record",
                            "record_id": "record-1",
                            "provider_family": "learning_loop",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        installer.install(self.hooks_json, cache_jsonl=cache_path, timeout=3)

        result = installer.status(self.hooks_json)
        encoded = json.dumps(result, ensure_ascii=False)

        self.assertEqual(result["cache_status"], "with_fresh_records")
        self.assertEqual(result["cache_record_count"], 1)
        self.assertEqual(result["fresh_record_count"], 1)
        self.assertEqual(result["expired_record_count"], 0)
        self.assertEqual(result["provider_counts"], {"learning_loop": 1})
        self.assertEqual(result["cache_path"], "<redacted:cache-jsonl>")
        self.assertEqual(result["cache_path_label"], "explicit-cache-jsonl")
        self.assertEqual(result["cache_scope"], "explicit_override")
        self.assertTrue(result["cache_path_redacted"])
        self.assertEqual(result["frontstage_card"]["status"], "ready")
        self.assertTrue(result["frontstage_card"]["ready"])
        self.assertNotIn(str(cache_path), encoded)

    def test_status_distinguishes_missing_empty_expired_and_malformed_cache(self) -> None:
        missing = self.codex_home / "missing-action-hints.jsonl"
        installer.install(self.hooks_json, cache_jsonl=missing, timeout=3)
        missing_status = installer.status(self.hooks_json)
        self.assertEqual(missing_status["cache_status"], "with_missing_cache_file")
        self.assertFalse(missing_status["cache_exists"])

        empty = self.codex_home / "empty-action-hints.jsonl"
        empty.write_text("", encoding="utf-8")
        installer.install(self.hooks_json, cache_jsonl=empty, timeout=3)
        empty_status = installer.status(self.hooks_json)
        self.assertEqual(empty_status["cache_status"], "with_empty_cache")
        self.assertTrue(empty_status["cache_exists"])

        expired = self.codex_home / "expired-action-hints.jsonl"
        expired.write_text(
            json.dumps(
                {
                    "kind": "aippocampus_action_hint_prepared_cache",
                    "records": [
                        {
                            "kind": "aippocampus_action_hint_prepared_record",
                            "record_id": "old",
                            "provider_family": "learning_loop",
                            "expires_at_unix": 1,
                        }
                    ],
                }
            )
            + "\nnot-json\n",
            encoding="utf-8",
        )
        installer.install(self.hooks_json, cache_jsonl=expired, timeout=3)
        expired_status = installer.status(self.hooks_json)
        self.assertEqual(expired_status["cache_status"], "with_expired_records")
        self.assertEqual(expired_status["cache_record_count"], 1)
        self.assertEqual(expired_status["fresh_record_count"], 0)
        self.assertEqual(expired_status["expired_record_count"], 1)
        self.assertEqual(expired_status["malformed_cache_line_count"], 1)
        self.assertEqual(expired_status["cache_path"], "<redacted:cache-jsonl>")

    def test_unsupported_host_status_does_not_pretend_installation(self) -> None:
        result = installer.status(self.hooks_json, host="claude-code")

        self.assertFalse(result["installed"])
        self.assertFalse(result["event_supported"])
        self.assertEqual(result["support_status"], "unsupported_host:claude-code")
        self.assertEqual(result["requested_host"], "claude-code")
        self.assertEqual(result["effective_host"], "codex")
        self.assertEqual(result["host_integration"]["status"], "unsupported_host:claude-code")

    def test_cli_install_json_is_public_safe_by_default_and_reports_cache_status(self) -> None:
        cache_path = self.codex_home / "action-hints.jsonl"
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = installer.main(
                [
                    "install",
                    "--codex-home",
                    str(self.codex_home),
                    "--cache-jsonl",
                    str(cache_path),
                    "--json",
                ]
            )

        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(code, 0, payload)
        self.assertTrue(payload["installed"])
        self.assertTrue(payload["changed"])
        self.assertEqual(payload["cache_status"], "with_missing_cache_file")
        self.assertEqual(payload["cache_path"], "<redacted:cache-jsonl>")
        self.assertNotIn(str(self.codex_home), encoded)
        self.assertNotIn(str(cache_path), encoded)
        self.assertNotIn("aippocampus_runtime.hooks.action_hint", encoded)

    def test_cli_status_human_frontstage_card_names_action_time_hints(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = installer.main(
                [
                    "status",
                    "--codex-home",
                    str(self.codex_home),
                ]
            )

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Action-time hints:", output)
        self.assertIn("fail-open: true", output)
        self.assertIn("authority: navigation_only", output)
        self.assertIn("aippocampus hooks action refresh-cache --write --json", output)
        self.assertNotIn("<local-cache.jsonl>", output)

    def test_cli_install_without_cache_uses_default_cache_path_not_inert_hook(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = installer.main(
                [
                    "install",
                    "--codex-home",
                    str(self.codex_home),
                    "--json",
                ]
            )

        payload = json.loads(stdout.getvalue())
        hooks = self.read_hooks()
        command = hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(code, 0, payload)
        self.assertTrue(payload["installed"])
        self.assertTrue(payload["cache_path_configured"])
        self.assertEqual(payload["frontstage_card"]["cache_path_label"], DEFAULT_CACHE_LABEL)
        self.assertEqual(payload["frontstage_card"]["cache_scope"], "current_workspace")
        self.assertIn("--cache-jsonl", command)
        self.assertNotIn("<local-cache.jsonl>", encoded)
        self.assertNotIn(str(self.codex_home), encoded)

    def test_cli_rejects_zero_or_negative_timeout_before_writing(self) -> None:
        for value in ("0", "-1"):
            stdout = StringIO()
            stderr = StringIO()
            with self.assertRaises(SystemExit) as raised:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    installer.main(
                        [
                            "install",
                            "--codex-home",
                            str(self.codex_home),
                            "--timeout",
                            value,
                            "--json",
                        ]
                    )
            self.assertEqual(raised.exception.code, 2)
            self.assertIn("at least 1", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
