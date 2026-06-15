from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.hooks import action_hint, action_hint_cache  # noqa: E402


def source_ref(name: str) -> dict[str, str]:
    return {"source_id": f"clean:{name}", "segment_id": f"msg-{name}"}


class ActionHintHookTests(unittest.TestCase):
    def test_pre_tool_use_emits_tiny_hint_without_raw_tool_leak(self) -> None:
        cache_report = action_hint_cache.build_action_hint_cache_report(
            learning_guidance=[
                {
                    "guidance_id": "preflight",
                    "next_action": "run_preflight_before_broad_test",
                    "guidance_text": "Run ruff before pytest.",
                    "source_refs": [source_ref("learn")],
                    "reason_codes": ["learning_guidance_surface"],
                }
            ],
            now_unix=1000,
        )
        for record in cache_report["records"]:
            record["expires_at_unix"] = 9999999999
        envelope = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "pytest E:/Users/private/project/tests/test_secret.py "
                    "--token sk-FAKE-SHOULD-NOT-LEAK"
                ),
                "file_path": "E:/Users/private/project/tests/test_secret.py",
                "command_family": "pytest",
            },
        }

        report = action_hint.evaluate_action_hint(envelope, cache_report, now_unix=1001)
        serialized = json.dumps(report, ensure_ascii=False)

        self.assertEqual(report["decision"], "hint")
        self.assertTrue(report["hint"]["navigation_only"])
        self.assertTrue(report["hint"]["no_claim_before_reopen"])
        self.assertTrue(report["hint"]["source_reopen_required"])
        self.assertFalse(report["hint"]["can_support_factual_claim"])
        self.assertFalse(report["diagnostics"]["command_rewritten"])
        self.assertFalse(report["diagnostics"]["permission_system_behavior"])
        self.assertNotIn("sk-FAKE-SHOULD-NOT-LEAK", serialized)
        self.assertNotIn("E:/Users/private", serialized)
        self.assertNotIn("pytest E:/Users/private", serialized)

    def test_unrelated_or_visible_source_actions_stay_silent(self) -> None:
        cache_report = action_hint_cache.build_action_hint_cache_report(
            aar_v2_records=[
                {
                    "record_id": "aar-record",
                    "action_class": "specific_memory_source_claim",
                    "source_refs": [source_ref("aar")],
                    "nudge": {"recommended_action": "reopen_source_before_specific_claim"},
                }
            ],
            now_unix=1000,
        )
        unrelated = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "README.md"},
        }
        visible = {
            "hook_event_name": "PreToolUse",
            "tool_name": "final_answer",
            "action_class": "specific_memory_source_claim",
            "support_level": "candidate",
            "visible_source_refs": [source_ref("aar")],
        }

        unrelated_report = action_hint.evaluate_action_hint(unrelated, cache_report, now_unix=1001)
        visible_report = action_hint.evaluate_action_hint(visible, cache_report, now_unix=1001)

        self.assertEqual(unrelated_report["decision"], "silent")
        self.assertEqual(visible_report["decision"], "silent")

    def test_project_specific_learning_hint_stays_silent_for_unrelated_pytest(self) -> None:
        cache_report = action_hint_cache.build_action_hint_cache_report(
            learning_guidance=[
                {
                    "guidance_id": "preflight-other-repo",
                    "next_action": "run_preflight_before_broad_test",
                    "guidance_text": "Run ruff before pytest.",
                    "scope": "project:OtherRepo",
                    "target_fingerprint": "other-repo:specific-target",
                    "path_category_fingerprint": "other-repo:tests/payments",
                    "source_refs": [source_ref("learn")],
                }
            ],
            now_unix=1000,
        )
        unrelated = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "pytest tests/completely_unrelated.py",
                "command_family": "pytest",
            },
        }
        matching = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "pytest tests/payments/test_checkout.py",
                "command_family": "pytest",
                "target_fingerprint": "other-repo:specific-target",
            },
        }

        unrelated_report = action_hint.evaluate_action_hint(unrelated, cache_report, now_unix=1001)
        matching_report = action_hint.evaluate_action_hint(matching, cache_report, now_unix=1001)

        self.assertEqual(unrelated_report["decision"], "silent")
        self.assertEqual(matching_report["decision"], "hint")
        self.assertEqual(matching_report["hint"]["recommended_action"], "run_preflight_before_broad_test")

    def test_directory_aware_path_feature_matches_relative_path_without_private_path_leak(self) -> None:
        cache_report = action_hint_cache.build_action_hint_cache_report(
            learning_guidance=[
                {
                    "guidance_id": "preflight-payments",
                    "next_action": "run_preflight_before_broad_test",
                    "guidance_text": "Run payments preflight before the broad test.",
                    "scope": "project:OtherRepo",
                    "path_category_fingerprint": "other-repo:tests/payments",
                    "source_refs": [source_ref("learn")],
                }
            ],
            now_unix=1000,
        )
        matching = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "pytest tests/payments/test_checkout.py",
                "command_family": "pytest",
                "file_path": "tests/payments/test_checkout.py",
            },
        }
        unrelated = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "pytest tests/docs/test_docs.py",
                "command_family": "pytest",
                "file_path": "tests/docs/test_docs.py",
            },
        }
        absolute_private = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "pytest E:/Users/private/project/tests/payments/test_checkout.py",
                "command_family": "pytest",
                "file_path": "E:/Users/private/project/tests/payments/test_checkout.py",
            },
        }

        matching_report = action_hint.evaluate_action_hint(matching, cache_report, now_unix=1001)
        unrelated_report = action_hint.evaluate_action_hint(unrelated, cache_report, now_unix=1001)
        private_report = action_hint.evaluate_action_hint(absolute_private, cache_report, now_unix=1001)
        private_serialized = json.dumps(private_report, ensure_ascii=False)

        self.assertEqual(matching_report["decision"], "hint")
        self.assertIn("tests/payments", matching_report["features"]["path_category_fingerprints"])
        self.assertEqual(unrelated_report["decision"], "silent")
        self.assertEqual(private_report["decision"], "silent")
        self.assertEqual(private_report["features"]["path_category_fingerprints"], [])
        self.assertNotIn("E:/Users/private", private_serialized)
        self.assertNotIn("project/tests/payments", private_serialized)

    def test_unsupported_event_fails_open(self) -> None:
        report = action_hint.evaluate_action_hint(
            {"hook_event_name": "UserPromptSubmit", "prompt": "hello"},
            [],
            now_unix=1001,
        )

        self.assertEqual(report["decision"], "silent")
        self.assertEqual(report["reason"], "unsupported_event")

    def test_malformed_stdin_fails_open_without_raw_payload_echo(self) -> None:
        env = {**os.environ, "PYTHONPATH": str(SCRIPTS)}
        proc = subprocess.run(
            [sys.executable, "-m", "aippocampus_runtime.hooks.action_hint", "--json"],
            input="not-json PRIVATE_INPUT",
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=False,
        )

        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload["decision"], "silent")
        self.assertEqual(payload["reason"], "malformed_input")
        self.assertNotIn("PRIVATE_INPUT", encoded)
        self.assertNotIn("JSONDecodeError", proc.stderr)

    def test_malformed_cache_lines_are_skipped_and_valid_records_still_match(self) -> None:
        cache_report = action_hint_cache.build_action_hint_cache_report(
            learning_guidance=[
                {
                    "guidance_id": "preflight",
                    "next_action": "run_preflight_before_broad_test",
                    "source_refs": [source_ref("learn")],
                }
            ],
            now_unix=1000,
        )
        for record in cache_report["records"]:
            record["expires_at_unix"] = 9999999999
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "action-hints.jsonl"
            cache_path.write_text(
                "not-json PRIVATE_CACHE_LINE\n"
                + json.dumps(cache_report, ensure_ascii=False)
                + "\n"
                + "{bad-json\n",
                encoding="utf-8",
            )
            env = {**os.environ, "PYTHONPATH": str(SCRIPTS)}
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.hooks.action_hint",
                    "--cache-jsonl",
                    str(cache_path),
                    "--json",
                ],
                input=json.dumps(
                    {
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"command": "pytest tests/foo.py"},
                    }
                ),
                text=True,
                encoding="utf-8",
                capture_output=True,
                env=env,
                check=False,
            )

        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload["decision"], "hint")
        self.assertEqual(payload["diagnostics"]["malformed_cache_line_count"], 2)
        self.assertEqual(payload["diagnostics"]["prepared_record_count"], 1)
        self.assertNotIn("PRIVATE_CACHE_LINE", encoded)


if __name__ == "__main__":
    unittest.main()
