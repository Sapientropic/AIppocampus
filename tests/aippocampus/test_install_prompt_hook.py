from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

import install_aippocampus_prompt_hook as installer  # noqa: E402
from aippocampus_runtime.hooks.debug_log import (  # noqa: E402
    write_debug_log,
    write_prompt_hook_audit_status,
)


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

    def test_generated_command_is_windows_shell_safe(self) -> None:
        command = installer.command_for(self.script)

        if os.name == "nt":
            self.assertTrue(command.startswith("& "), command)
        else:
            self.assertFalse(command.startswith("& "), command)
        self.assertIn(str(self.script.resolve()), command)
        self.assertIn("--max-elapsed-ms 4300", command)
        self.assertIn("--semantic-timeout 2.5", command)

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
        self.assertIn("--max-elapsed-ms 4300", prompt_hooks[0]["command"])
        self.assertIn("--semantic-timeout 2.5", prompt_hooks[0]["command"])
        self.assertEqual(
            data["hooks"]["PostToolUse"][0]["hooks"][0]["command"], "python existing.py"
        )

    def test_install_allows_explicit_foreground_budget_override(self) -> None:
        result = installer.install(
            self.hooks_json,
            self.script,
            timeout=7,
            max_elapsed_ms=6200,
            semantic_timeout=1.25,
        )

        data = self.read_hooks()
        hook = data["hooks"]["UserPromptSubmit"][0]["hooks"][0]
        self.assertTrue(result["changed"])
        self.assertEqual(hook["timeout"], 7)
        self.assertIn("--max-elapsed-ms 6200", hook["command"])
        self.assertIn("--semantic-timeout 1.25", hook["command"])

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

    def test_status_last_reads_default_sanitized_audit_status(self) -> None:
        status_path = self.codex_home / "prompt_hook_last_status.json"
        write_prompt_hook_audit_status(
            {
                "decision": "scent",
                "score": 0.7,
                "confidence": "medium",
                "query_terms": [],
                "concept_expansions": [],
                "cognitive_map": [],
                "candidates": [{"thread_key": "session:private", "title": "private candidate"}],
                "working_memory": [],
                "evidence": [],
                "ambient_recall": {
                    "mode": "active_gentle_nudge",
                    "confidence": "medium",
                    "cards": [
                        {
                            "card_id": "cached-card",
                            "theme": "private cached theme",
                            "support_level": "candidate",
                            "visibility": "active_gentle_nudge",
                            "provenance_class": "cached_warm_card",
                            "source_refs": [],
                        }
                    ],
                    "cache_status": {"status": "hit"},
                },
                "elapsed_ms": 12.0,
            },
            status_path=status_path,
        )

        installer.install(self.hooks_json, self.script, timeout=5)
        with patch(
            "aippocampus_runtime.hooks.debug_log.default_prompt_hook_status_path",
            return_value=status_path,
        ):
            result = installer.status(self.hooks_json, self.script, include_last=True)

        self.assertEqual(result["last_prompt_hook"]["status"], "found")
        self.assertEqual(result["last_prompt_hook"]["source"], "last_status")
        self.assertEqual(
            result["last_prompt_hook"]["last_prompt_hook"]["memory_surface"],
            "candidate",
        )
        encoded = json.dumps(result["last_prompt_hook"], ensure_ascii=False)
        self.assertNotIn("private cached theme", encoded)
        self.assertNotIn("private candidate", encoded)
        self.assertNotIn("private-session", encoded)
        public_status = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["path"], "hooks.json")
        self.assertTrue(result["path_redacted"])
        self.assertEqual(result["commands"], ["<redacted:hook-command>"])
        self.assertTrue(result["commands_redacted"])
        self.assertNotIn(str(self.codex_home), public_status)
        self.assertNotIn(str(self.script.resolve()), public_status)

    def test_status_last_includes_sanitized_prompt_hook_audit_summary(self) -> None:
        log_path = self.codex_home / "prompt_hook_debug.jsonl"
        write_debug_log(
            {
                "decision": "scent",
                "score": 0.7,
                "confidence": "medium",
                "query_terms": [],
                "concept_expansions": [],
                "cognitive_map": [],
                "candidates": [],
                "working_memory": [],
                "evidence": [],
                "ambient_recall": {
                    "mode": "active_gentle_nudge",
                    "confidence": "medium",
                    "cards": [
                        {
                            "card_id": "cached-card",
                            "theme": "private cached theme",
                            "support_level": "candidate",
                            "visibility": "active_gentle_nudge",
                            "provenance_class": "cached_warm_card",
                            "source_refs": [],
                        }
                    ],
                    "cache_status": {"status": "hit"},
                },
                "elapsed_ms": 12.0,
            },
            hook_input={"session_id": "private-session", "turn_id": "private-turn"},
            log_path=log_path,
        )

        result = installer.status(
            self.hooks_json,
            self.script,
            include_last=True,
            log_path=log_path,
        )

        self.assertEqual(result["last_prompt_hook"]["status"], "found")
        self.assertEqual(
            result["last_prompt_hook"]["last_prompt_hook"]["memory_surface"],
            "candidate",
        )
        encoded = json.dumps(result["last_prompt_hook"], ensure_ascii=False)
        self.assertNotIn("private cached theme", encoded)
        self.assertNotIn("private-session", encoded)

    def test_status_last_json_cli_projects_prompt_hook_audit_summary(self) -> None:
        log_path = self.codex_home / "prompt_hook_debug.jsonl"
        write_debug_log(
            {
                "decision": "scent",
                "score": 0.7,
                "confidence": "medium",
                "query_terms": [],
                "concept_expansions": [],
                "cognitive_map": [],
                "candidates": [],
                "working_memory": [],
                "evidence": [],
                "ambient_recall": {
                    "mode": "active_gentle_nudge",
                    "confidence": "medium",
                    "cards": [
                        {
                            "card_id": "cached-card",
                            "theme": "private cached theme",
                            "support_level": "candidate",
                            "visibility": "active_gentle_nudge",
                            "provenance_class": "cached_warm_card",
                            "source_refs": [],
                        }
                    ],
                    "cache_status": {"status": "hit"},
                },
                "elapsed_ms": 12.0,
            },
            hook_input={"session_id": "private-session", "turn_id": "private-turn"},
            log_path=log_path,
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = installer.main(
                [
                    "status",
                    "--hooks-json",
                    str(self.hooks_json),
                    "--script",
                    str(self.script),
                    "--last",
                    "--log-path",
                    str(log_path),
                    "--json",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["last_prompt_hook"]["status"], "found")
        self.assertEqual(
            payload["last_prompt_hook"]["last_prompt_hook"]["memory_surface"],
            "candidate",
        )
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["path"], "hooks.json")
        self.assertTrue(payload["path_redacted"])
        self.assertNotIn("private cached theme", encoded)
        self.assertNotIn(str(self.codex_home), encoded)


if __name__ == "__main__":
    unittest.main()
