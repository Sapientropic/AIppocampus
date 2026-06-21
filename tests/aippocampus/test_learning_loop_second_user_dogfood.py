from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "learning_loop" / "second_user_dogfood_cases.jsonl"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.learning_loop.dogfood_cases import (  # noqa: E402
    build_sanitized_repro_package,
    build_second_user_dogfood_report,
    load_second_user_cases,
)


class LearningLoopSecondUserDogfoodTests(unittest.TestCase):
    def test_second_user_cases_report_hint_effects_without_private_leaks(self) -> None:
        rows = load_second_user_cases(FIXTURE)
        report = build_second_user_dogfood_report(rows)
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        metrics = report["metrics"]

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["case_count"], 6)
        self.assertGreaterEqual(metrics["first_wrong_action_avoided"], 3)
        self.assertGreaterEqual(metrics["broad_search_avoided"], 3)
        self.assertGreaterEqual(metrics["source_reopen_before_claim"], 4)
        self.assertEqual(metrics["hint_ignored_or_dismissed"], 0)
        self.assertEqual(metrics["repeat_failure_after_hint"], 0)
        self.assertEqual(metrics["stale_warning_suppressed"], 1)
        self.assertEqual(metrics["current_thread_visibility_boundary_preserved"], 1)
        self.assertEqual(metrics["hint_absent_due_to_no_cache"], 1)
        self.assertEqual(metrics["no_cache_not_algorithmic_miss"], 1)
        self.assertEqual(metrics["prepared_cache_navigation_only_hint_emitted"], 1)
        self.assertTrue(report["privacy_boundary"]["navigation_only"])
        self.assertFalse(report["privacy_boundary"]["raw_tool_args_serialized"])
        self.assertNotIn("PRIVATE_", encoded)
        self.assertNotIn("C:/", encoded)

    def test_sanitized_repro_package_preserves_issue_shape_without_private_leaks(self) -> None:
        package = build_sanitized_repro_package(
            {
                "surface": "agent_recall",
                "command": (
                    "aippocampus agent recall --cwd E:/SDY/private "
                    "--query sk-test-public-fixture"
                ),
                "stdout": {
                    "kind": "aippocampus_agent_recall",
                    "route_id": "route-public",
                    "local_path": "E:/SDY/private/thread.jsonl",
                    "metrics": {"candidate_count": 2},
                    "source_refs": [{"thread_key": "session-private", "message_id": "msg-1"}],
                },
                "stderr": "warning: token=super-secret-value",
                "expected": "route should explain next action",
                "actual": "route exposed noisy private path",
            },
            version="0.2.0-test",
            commit="abcdef1234567890",
            plugin_manifest_version="0.2.0-test",
        )
        encoded = json.dumps(package, ensure_ascii=False, sort_keys=True)

        self.assertEqual(package["kind"], "aippocampus_sanitized_repro_package")
        self.assertTrue(package["ok"], package)
        self.assertEqual(package["surface"], "agent_recall")
        self.assertEqual(package["versions"]["aippocampus"], "0.2.0-test")
        self.assertEqual(package["versions"]["git_commit"], "abcdef123456")
        self.assertGreaterEqual(package["output_shape"]["byte_count"], 1)
        self.assertEqual(package["privacy_scan"]["private_field_leak_count"], 0)
        self.assertIn("expected_vs_actual_template", package)
        self.assertIn("privacy_note", package)
        self.assertNotIn("E:/SDY/private", encoded)
        self.assertNotIn("sk-test-public-fixture", encoded)
        self.assertNotIn("super-secret-value", encoded)

    def test_sanitized_repro_package_redacts_prompt_like_stdio_fields(self) -> None:
        package = build_sanitized_repro_package(
            {
                "surface": "agent_recall",
                "command": "aippocampus agent recall --query vague",
                "stdout": {
                    "raw_prompt": "PRIVATE_USER_PROMPT_SHOULD_NOT_SURVIVE",
                    "user_prompt": "PRIVATE_USER_PROMPT_SHOULD_NOT_SURVIVE",
                    "ordinary_text": "PRIVATE_USER_PROMPT_SHOULD_NOT_SURVIVE",
                    "metrics": {"candidate_count": 2},
                },
                "stderr": "PRIVATE_USER_PROMPT_SHOULD_NOT_SURVIVE",
                "expected": "no raw prompt text in public package",
                "actual": "prompt-like fields survive",
            }
        )
        sample = package["compact_sample_payload"]
        encoded = json.dumps(package, ensure_ascii=False, sort_keys=True)

        self.assertTrue(package["ok"], package)
        self.assertTrue(package["privacy_boundary"]["safe_to_paste_public_issue_by_default"])
        self.assertFalse(package["privacy_boundary"]["raw_prompt_serialized"])
        self.assertFalse(package["privacy_boundary"]["raw_stdout_stderr_serialized"])
        self.assertFalse(package["privacy_boundary"]["raw_output_text_preserved"])
        self.assertEqual(sample["stdout"]["raw_prompt"], "<prompt-like-text-redacted>")
        self.assertEqual(sample["stdout"]["user_prompt"], "<prompt-like-text-redacted>")
        self.assertEqual(sample["stdout"]["ordinary_text"], "<raw-output-text-redacted>")
        self.assertEqual(sample["stdout"]["metrics"]["candidate_count"], 2)
        self.assertEqual(sample["stderr"], "<raw-output-text-redacted>")
        self.assertNotIn("PRIVATE_USER_PROMPT_SHOULD_NOT_SURVIVE", encoded)

    def test_learning_cli_builds_sanitized_repro_package_from_saved_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "command.json"
            input_path.write_text(
                json.dumps(
                    {
                        "surface": "benchmark",
                        "command": "python E:/SDY/private/benchmark.py --json",
                        "stdout": {"status": "failed", "path": "E:/SDY/private/out.json"},
                        "expected": "public-safe no-go",
                        "actual": "absolute path leaked",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "learning",
                    "repro-package",
                    "--input-json",
                    str(input_path),
                    "--json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertEqual(payload["kind"], "aippocampus_learning_frontdoor")
        self.assertEqual(payload["mode"], "repro_package")
        self.assertEqual(payload["repro_package"]["surface"], "benchmark")
        self.assertNotIn("E:/SDY/private", encoded)

    def test_top_level_repro_package_alias_supports_template_and_stdin(self) -> None:
        help_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "repro",
                "package",
                "--help",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        self.assertEqual(help_proc.returncode, 0, help_proc.stderr)
        self.assertIn("usage: aippocampus repro package", help_proc.stdout)
        self.assertNotIn("aippocampus learning repro-package", help_proc.stdout)

        template = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "repro",
                "package",
                "--template",
                "--json",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        self.assertEqual(template.returncode, 0, template.stderr)
        template_payload = json.loads(template.stdout)
        self.assertEqual(template_payload["mode"], "repro_package_template")
        self.assertIn("template", template_payload)
        self.assertEqual(template_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", template_payload)
        self.assertNotIn(template_payload["foreground_action"], template_payload["safe_next_actions"])
        self.assertEqual(
            template_payload["foreground_action"]["command"],
            "aippocampus repro package --input-json repro-input.json --json",
        )
        self.assertNotIn("compatibility", template_payload)
        encoded_template = json.dumps(template_payload, ensure_ascii=False)
        self.assertIn(
            "aippocampus repro package --input-json repro-input.json --json",
            encoded_template,
        )
        self.assertIn(
            "cat repro-input.json | aippocampus repro package --stdin --json",
            encoded_template,
        )
        self.assertNotIn("type repro-input.json |", encoded_template)

        recovery = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "repro",
                "package",
                "--json",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        self.assertEqual(recovery.returncode, 2)
        recovery_payload = json.loads(recovery.stdout)
        self.assertEqual(recovery_payload["mode"], "repro_package_recovery")
        self.assertEqual(recovery_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", recovery_payload)
        self.assertEqual(recovery_payload["foreground_action"]["id"], "show_repro_package_template")

        stdin_payload = {
            "surface": "agent_recall",
            "command": "aippocampus agent recall --query vague",
            "stdout": {"raw_prompt": "PRIVATE_USER_PROMPT_SHOULD_NOT_SURVIVE"},
            "expected": "prompt redacted",
            "actual": "raw prompt survived",
        }
        packaged = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "repro",
                "package",
                "--stdin",
                "--json",
            ],
            cwd=SCRIPTS,
            input=json.dumps(stdin_payload, ensure_ascii=False),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        self.assertEqual(packaged.returncode, 0, packaged.stderr)
        packaged_payload = json.loads(packaged.stdout)
        encoded = json.dumps(packaged_payload, ensure_ascii=False, sort_keys=True)
        self.assertEqual(packaged_payload["mode"], "repro_package")
        self.assertEqual(packaged_payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", packaged_payload)
        self.assertNotIn(packaged_payload["foreground_action"], packaged_payload["safe_next_actions"])
        self.assertEqual(packaged_payload["foreground_action"]["id"], "review_public_safe_repro_package")
        self.assertNotIn("PRIVATE_USER_PROMPT_SHOULD_NOT_SURVIVE", encoded)

    def test_learning_repro_package_missing_input_json_returns_recovery_card(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "learning",
                "repro-package",
                "--json",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("usage:", proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["mode"], "repro_package_recovery")
        self.assertNotIn("cannot_claim", payload)
        self.assertIn("cannot_claim", payload["boundary_detail"])
        self.assertEqual(payload["error"]["code"], "learning_repro_input_required")
        self.assertEqual(payload["error"]["next_command"], "aippocampus repro package --template --json")
        self.assertIn("expected_input_schema", payload)
        self.assertIn("redacted_example", payload["expected_input_schema"])
        self.assertEqual(
            {item["label"] for item in payload["recovery_paths"]},
            {"from sanitized replay or guidance output", "fresh command/output capture template"},
        )
        self.assertIn("copyable_package_command", payload["recovery_paths"][0])
        self.assertIn("copyable_template_command", payload["recovery_paths"][1])
        self.assertIn("copyable_stdin_command", payload["recovery_paths"][1])
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertIn(
            "cat command-output.json | aippocampus repro package --stdin --json",
            encoded,
        )
        self.assertNotIn("type command-output.json |", encoded)
        self.assertFalse(payload["privacy_boundary"]["raw_prompt_or_stdout_serialized"])

    def test_learning_repro_package_malformed_input_returns_recovery_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "bad.json"
            input_path.write_text(
                json.dumps({"command": "pytest", "expected": "pass"}, ensure_ascii=False),
                encoding="utf-8",
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "learning",
                    "repro-package",
                    "--input-json",
                    str(input_path),
                    "--json",
                ],
                cwd=SCRIPTS,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("usage:", proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertNotIn("cannot_claim", payload)
        self.assertIn("cannot_claim", payload["boundary_detail"])
        self.assertEqual(payload["error"]["code"], "learning_repro_input_malformed")
        self.assertIn("missing required repro fields", payload["error"]["malformed_error"])
        self.assertIn("expected_input_schema", payload)
        self.assertFalse(payload["privacy_boundary"]["raw_prompt_or_stdout_serialized"])


if __name__ == "__main__":
    unittest.main()
