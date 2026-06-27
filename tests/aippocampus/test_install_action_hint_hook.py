from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"

from aippocampus_runtime.hooks import install_action_hint as installer

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

    def test_status_default_is_compact_and_keeps_operator_fields_out(self) -> None:
        installer.install(self.hooks_json, timeout=3)

        result = installer.status(self.hooks_json)
        encoded = json.dumps(result, ensure_ascii=False)

        self.assertTrue(result["installed"])
        self.assertEqual(result["kind"], "aippocampus_action_hint_status_compact")
        self.assertEqual(result["cache_status"], "with_missing_cache_file")
        self.assertEqual(result["cache_record_count"], 0)
        self.assertEqual(result["support_status"], "supported_by_codex_hooks_json")
        self.assertEqual(result["authority"], "navigation_only")
        self.assertTrue(result["fail_open"])
        self.assertFalse(result["optional"])
        self.assertFalse(result["recall_blocking"])
        self.assertEqual(result["setup_role"], "cleanup_or_prepare_required")
        self.assertEqual(result["cache_path_label"], DEFAULT_CACHE_LABEL)
        self.assertEqual(result["cache_scope"], "current_workspace")
        self.assertTrue(result["operator_json_available"])
        self.assertEqual(
            result["operator_detail_command"],
            "aippocampus hooks action status --operator-json",
        )
        self.assertNotIn("frontstage_card", result)
        self.assertNotIn("path", result)
        self.assertNotIn("commands", result)
        self.assertNotIn("cache_path", result)
        self.assertNotIn("provider_counts", result)
        commands = [
            action.get("command")
            for action in [result["foreground_action"], *result["safe_next_actions"]]
            if action.get("command")
        ]
        self.assertTrue(any("refresh-cache" in command for command in commands))
        self.assertTrue(any("--write --json" in command for command in commands))
        self.assertFalse(any("uninstall" in command for command in commands))
        self.assertEqual(result["manage_command"], "aippocampus hooks action uninstall --json")
        self.assertNotIn(str(self.codex_home), encoded)
        self.assertNotIn(str(SCRIPTS.resolve()), encoded)

    def test_status_not_installed_primary_is_ordered_setup_chain(self) -> None:
        result = installer.status(self.hooks_json)

        self.assertFalse(result["installed"])
        self.assertEqual(result["foreground_action"]["id"], "review_action_hint_guidance")
        action_ids = [action["id"] for action in result["safe_next_actions"]]
        self.assertEqual(action_ids, ["check_action_hint_status"])
        self.assertNotIn("follow_up_action", result["foreground_action"])
        self.assertEqual(result["manage_command"], "aippocampus hooks action install --json")
        self.assertNotIn(
            "refresh-cache --write",
            result["foreground_action"].get("command", ""),
        )

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
        self.assertEqual(result["cache_path_label"], "explicit-cache-jsonl")
        self.assertEqual(result["cache_scope"], "explicit_override")
        self.assertNotIn("expired_record_count", result)
        self.assertNotIn("provider_counts", result)
        self.assertNotIn("cache_path", result)
        self.assertNotIn("frontstage_card", result)
        self.assertEqual(result["status"], "active")
        self.assertEqual(result["stage"], "active")
        self.assertFalse(result["useful"])
        self.assertTrue(result["hot_path_active"])
        self.assertEqual(result["foreground_action"]["id"], "probe_action_hint_hot_path")
        self.assertIn("hooks action probe", result["foreground_action"]["command"])
        self.assertEqual(result["foreground_action"]["mutation_risk"], "read_only")
        self.assertIn("safe_next_actions", result)
        self.assertIn("check_action_hint_status", [action["id"] for action in result["safe_next_actions"]])
        self.assertNotIn(str(cache_path), encoded)

    def test_status_aliases_frontstage_next_steps_to_shared_action_contract(self) -> None:
        installer.install(self.hooks_json, timeout=3)

        result = installer.status(self.hooks_json)
        action_ids = [action["id"] for action in result["safe_next_actions"]]

        self.assertEqual(result["status"], "callable")
        self.assertEqual(result["stage"], "callable")
        self.assertEqual(result["cache_status"], "with_missing_cache_file")
        self.assertEqual(result["foreground_action"]["id"], "refresh_action_hint_cache")
        self.assertEqual(result["foreground_action"]["mutation_risk"], "explicit_local_cache_write")
        self.assertNotIn("refresh_action_hint_cache", action_ids)
        self.assertIn("check_action_hint_status", action_ids)
        self.assertNotIn("rollback_action_hint_hook", action_ids)
        self.assertEqual(result["manage_command"], "aippocampus hooks action uninstall --json")
        self.assertEqual(
            result["foreground_action"]["mutation_risk"],
            "explicit_local_cache_write",
        )
        action_commands = {
            result["foreground_action"]["command"],
            *(
                action["command"]
                for action in result["safe_next_actions"]
                if action.get("command") and action["id"] != "check_action_hint_status"
            ),
        }
        self.assertIn("aippocampus hooks action refresh-cache --write --json", action_commands)
        self.assertNotIn("aippocampus hooks action uninstall --json", action_commands)

    def test_status_distinguishes_missing_empty_expired_and_malformed_cache(self) -> None:
        missing = self.codex_home / "missing-action-hints.jsonl"
        installer.install(self.hooks_json, cache_jsonl=missing, timeout=3)
        missing_status = installer.status(self.hooks_json, include_private_paths=True)
        self.assertEqual(missing_status["cache_status"], "with_missing_cache_file")
        self.assertFalse(missing_status["cache_exists"])

        empty = self.codex_home / "empty-action-hints.jsonl"
        empty.write_text("", encoding="utf-8")
        installer.install(self.hooks_json, cache_jsonl=empty, timeout=3)
        empty_status = installer.status(self.hooks_json, include_private_paths=True)
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
        expired_status = installer.status(self.hooks_json, include_private_paths=True)
        self.assertEqual(expired_status["cache_status"], "with_expired_records")
        self.assertEqual(expired_status["cache_record_count"], 1)
        self.assertEqual(expired_status["fresh_record_count"], 0)
        self.assertEqual(expired_status["expired_record_count"], 1)
        self.assertEqual(expired_status["malformed_cache_line_count"], 1)
        self.assertEqual(expired_status["cache_path"], str(expired))

    def test_installed_empty_cache_warns_that_hot_hook_is_inactive(self) -> None:
        empty = self.codex_home / "empty-action-hints.jsonl"
        empty.write_text("", encoding="utf-8")
        installer.install(self.hooks_json, cache_jsonl=empty, timeout=3)

        result = installer.status(self.hooks_json)

        self.assertTrue(result["installed"])
        self.assertEqual(result["cache_status"], "with_empty_cache")
        self.assertEqual(result["warning_state"], "installed_cache_not_useful")
        self.assertFalse(result["hot_path_active"])
        self.assertEqual(result["setup_role"], "cleanup_or_prepare_required")
        self.assertNotIn("frontstage_card", result)
        self.assertEqual(result["foreground_action"]["id"], "refresh_action_hint_cache")
        self.assertEqual(result["foreground_action"]["mutation_risk"], "explicit_local_cache_write")
        self.assertIn(
            "check_action_hint_status",
            [action["id"] for action in result["safe_next_actions"]],
        )
        self.assertNotIn(
            "rollback_action_hint_hook",
            [action["id"] for action in result["safe_next_actions"]],
        )
        self.assertEqual(result["manage_command"], "aippocampus hooks action uninstall --json")

    def test_unsupported_host_status_does_not_pretend_installation(self) -> None:
        result = installer.status(self.hooks_json, host="claude-code", include_private_paths=True)

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
        self.assertFalse(payload["privacy_boundary"]["local_path_serialized"])
        self.assertFalse(payload["privacy_boundary"]["hook_command_serialized"])
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertEqual(payload["status"], "installed_needs_cache")
        self.assertEqual(payload["foreground_action"]["id"], "refresh_action_hint_cache")
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertIn("status", action_ids)
        self.assertIn("rollback", action_ids)
        self.assertIn("aippocampus hooks action uninstall --json", encoded)
        self.assertNotIn(str(self.codex_home), encoded)
        self.assertNotIn(str(cache_path), encoded)
        self.assertNotIn("aippocampus_runtime.hooks.action_hint", encoded)

    def test_cli_install_json_reports_empty_cache_as_not_ready_closeout(self) -> None:
        cache_path = self.codex_home / "empty-action-hints.jsonl"
        cache_path.write_text("", encoding="utf-8")

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
        self.assertEqual(payload["cache_status"], "with_empty_cache")
        self.assertEqual(payload["status"], "installed_needs_cache")
        self.assertEqual(payload["foreground_action"]["id"], "refresh_action_hint_cache")
        self.assertIn("aippocampus hooks action refresh-cache --write --json", encoded)
        self.assertIn("aippocampus hooks action status --json", encoded)
        self.assertIn("aippocampus hooks action uninstall --json", encoded)
        self.assertNotIn(str(cache_path), encoded)
        self.assertNotIn(str(SCRIPTS.resolve()), encoded)
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
        self.assertIn("aippocampus learning guidance --json", output)
        self.assertNotIn("aippocampus hooks action refresh-cache --write --json", output)
        self.assertNotIn("<local-cache.jsonl>", output)

    def test_cli_status_json_is_compact_by_default_and_operator_json_keeps_detail(self) -> None:
        empty = self.codex_home / "empty-action-hints.jsonl"
        empty.write_text("", encoding="utf-8")
        installer.install(self.hooks_json, cache_jsonl=empty, timeout=3)

        stdout = StringIO()
        with redirect_stdout(stdout):
            code = installer.main(
                [
                    "status",
                    "--codex-home",
                    str(self.codex_home),
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["kind"], "aippocampus_action_hint_status_compact")
        self.assertEqual(payload["status"], "callable")
        self.assertEqual(payload["stage"], "callable")
        self.assertEqual(payload["cache_status"], "with_empty_cache")
        self.assertEqual(payload["foreground_action"]["id"], "refresh_action_hint_cache")
        self.assertNotIn("frontstage_card", payload)
        self.assertNotIn("commands", payload)
        self.assertNotIn("cache_path", payload)
        self.assertNotIn("cache_exists", payload)
        self.assertNotIn("provider_counts", payload)
        self.assertNotIn(str(empty), encoded)
        self.assertNotIn("aippocampus_runtime.hooks.action_hint", encoded)

        operator_stdout = StringIO()
        with redirect_stdout(operator_stdout):
            operator_code = installer.main(
                [
                    "status",
                    "--codex-home",
                    str(self.codex_home),
                    "--operator-json",
                    "--json",
                ]
            )
        operator_payload = json.loads(operator_stdout.getvalue())
        operator_encoded = json.dumps(operator_payload, ensure_ascii=False)

        self.assertEqual(operator_code, 0, operator_payload)
        self.assertEqual(operator_payload["cache_status"], "with_empty_cache")
        self.assertTrue(operator_payload["cache_exists"])
        self.assertEqual(operator_payload["cache_path"], str(empty))
        self.assertIn("frontstage_card", operator_payload)
        self.assertIn("commands", operator_payload)
        self.assertIn("aippocampus_runtime.hooks.action_hint", operator_encoded)

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
