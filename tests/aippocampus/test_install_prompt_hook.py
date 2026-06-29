from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"

from aippocampus_runtime.contracts import foreground_action_contract_violations
from aippocampus_runtime.hooks import install_prompt as installer
from aippocampus_runtime.hooks.debug_log import (
    write_debug_log,
    write_prompt_hook_audit_status,
)
from aippocampus_runtime.hooks.skip_telemetry import write_skip_telemetry
from aippocampus_runtime.ops import provider_key_bridge


class InstallAmbientRecallHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.codex_home = Path(self.tmp.name) / ".codex"
        self.codex_home.mkdir()
        self.hooks_json = self.codex_home / "hooks.json"
        self.module = installer.DEFAULT_HOOK_MODULE

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
        self.assertIn("--max-elapsed-ms 3500", command)
        self.assertIn("--semantic-timeout 1.2", command)

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

        first = installer.install(self.hooks_json, timeout=5)
        second = installer.install(self.hooks_json, timeout=5)

        data = self.read_hooks()
        prompt_hooks = data["hooks"]["UserPromptSubmit"][0]["hooks"]
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(len(prompt_hooks), 1)
        self.assertIn(self.module, prompt_hooks[0]["command"])
        self.assertIn("--max-elapsed-ms 3500", prompt_hooks[0]["command"])
        self.assertIn("--semantic-timeout 1.2", prompt_hooks[0]["command"])
        self.assertEqual(
            data["hooks"]["PostToolUse"][0]["hooks"][0]["command"], "python existing.py"
        )

    def test_cli_install_json_is_foreground_safe_when_changed(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = installer.main(["install", "--hooks-json", str(self.hooks_json), "--json"])

        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(code, 0, payload)
        self.assertTrue(payload["installed"])
        self.assertTrue(payload["changed"])
        self.assertNotIn("path", payload)
        self.assertNotIn("command", payload)
        self.assertFalse(payload["privacy_boundary"]["local_path_serialized"])
        self.assertFalse(payload["privacy_boundary"]["hook_command_serialized"])
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertEqual(payload["status"], "installed_ready")
        self.assertIn("foreground_action", payload)
        self.assertNotIn(payload["foreground_action"], payload["safe_next_actions"])
        self.assertEqual(payload["foreground_action"]["id"], "no_action_needed")
        action_ids = [action["id"] for action in payload["safe_next_actions"]]
        self.assertIn("status", action_ids)
        self.assertIn("rollback", action_ids)
        self.assertIn("aippocampus hooks prompt uninstall --json", encoded)
        self.assertNotIn(str(self.codex_home), encoded)
        self.assertNotIn(str(SCRIPTS.resolve()), encoded)
        self.assertNotIn(self.module, encoded)

    def test_cli_install_json_is_foreground_safe_when_already_installed(self) -> None:
        installer.install(self.hooks_json, timeout=5)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = installer.main(["install", "--hooks-json", str(self.hooks_json), "--json"])

        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(code, 0, payload)
        self.assertTrue(payload["installed"])
        self.assertFalse(payload["changed"])
        self.assertEqual(payload["status"], "installed_ready")
        self.assertIn("foreground_action", payload)
        self.assertEqual(payload["foreground_action"]["id"], "no_action_needed")
        self.assertNotIn("path", payload)
        self.assertNotIn("command", payload)
        self.assertNotIn(str(self.codex_home), encoded)
        self.assertNotIn(str(SCRIPTS.resolve()), encoded)
        self.assertNotIn(self.module, encoded)

    def test_install_allows_explicit_foreground_budget_override(self) -> None:
        result = installer.install(
            self.hooks_json,
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

    def test_status_treats_provider_bridge_wrapper_as_installed(self) -> None:
        dotenv = Path(self.tmp.name) / "provider.env"
        provider_env_var = "PROVIDER_PROMPT_STATUS_BRIDGE"
        fixture_value = "sk-FAKE_TEST_PROMPT_STATUS_BRIDGE_1234567890"
        dotenv.write_text(f"{provider_env_var}={fixture_value}\n", encoding="utf-8")

        provider_key_bridge.apply_provider_key_bridge(
            target="codex-hooks",
            source="explicit-dotenv",
            provider_env_var=provider_env_var,
            credential_dotenv=dotenv,
            codex_home_path=self.codex_home,
        )
        result = installer.status(
            self.hooks_json,
            include_last=True,
            telemetry_path=self.codex_home / "no-skip-telemetry.json",
        )
        encoded = json.dumps(result, ensure_ascii=False)

        self.assertTrue(result["installed"])
        self.assertTrue(result["provider_key_bridge_installed"])
        self.assertTrue(result["installed_via_provider_bridge"])
        self.assertEqual(result["path"], "hooks.json")
        self.assertEqual(result["commands"], ["<redacted:hook-command>"])
        self.assertTrue(result["commands_redacted"])
        self.assertNotIn(fixture_value, encoded)

        with patch("sys.stdout", new=io.StringIO()) as stdout:
            code = installer.main(["status", "--codex-home", str(self.codex_home)])
        text = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("provider-key bridge: installed", text)
        self.assertIn("already-running hook process: not proven", text)
        self.assertIn("aippocampus doctor provider --json", text)
        self.assertNotIn(fixture_value, text)

    def test_status_json_redacts_paths_and_commands_by_default_without_last(self) -> None:
        installer.install(self.hooks_json, timeout=5)

        result = installer.status(self.hooks_json)
        encoded = json.dumps(result, ensure_ascii=False)

        self.assertTrue(result["installed"])
        self.assertEqual(result["path"], "hooks.json")
        self.assertTrue(result["path_redacted"])
        self.assertEqual(result["commands"], ["<redacted:hook-command>"])
        self.assertTrue(result["commands_redacted"])
        self.assertNotIn(str(self.codex_home), encoded)
        self.assertNotIn(str(SCRIPTS.resolve()), encoded)

    def test_status_has_foreground_action_card_for_installed_missing_and_stale(self) -> None:
        missing = installer.status(self.hooks_json)
        self.assertEqual(missing["status"], "missing")
        self.assertIn("foreground_action", missing)
        self.assertNotIn(missing["foreground_action"], missing["safe_next_actions"])
        self.assertEqual(missing["foreground_action"]["id"], "install_prompt_hook")
        self.assertNotIn(
            "install_prompt_hook",
            {action["id"] for action in missing["safe_next_actions"]},
        )
        self.assertEqual(missing["claim_boundary"], "host_setup_not_memory_evidence")

        installer.install(self.hooks_json, timeout=5)
        installed = installer.status(self.hooks_json)
        self.assertEqual(installed["status"], "installed")
        self.assertIn("foreground_action", installed)
        self.assertNotIn(installed["foreground_action"], installed["safe_next_actions"])
        self.assertEqual(installed["foreground_action"]["id"], "inspect_prompt_hook_output")
        self.assertEqual(installed["foreground_action"]["mutation_risk"], "read_only")
        installed_action_ids = [action["id"] for action in installed["safe_next_actions"]]
        self.assertIn("try_first_recall_after_prompt_hook", installed_action_ids)
        self.assertNotIn("rollback_prompt_hook", installed_action_ids)
        self.assertEqual(installed["manage_command"], "aippocampus hooks prompt uninstall --json")
        self.assertTrue(all(action["mutation_risk"] == "read_only" for action in installed["safe_next_actions"]))

        self.hooks_json.write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python ambient_recall_hook.py",
                                        "timeout": 5,
                                    }
                                ]
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        stale = installer.status(self.hooks_json)
        encoded = json.dumps(stale, ensure_ascii=False)
        self.assertEqual(stale["status"], "stale")
        self.assertIn("foreground_action", stale)
        self.assertEqual(stale["foreground_action"]["id"], "refresh_prompt_hook")
        self.assertNotIn(stale["foreground_action"], stale["safe_next_actions"])
        self.assertNotIn(
            "refresh_prompt_hook",
            {action["id"] for action in stale["safe_next_actions"]},
        )
        self.assertNotIn("ambient_recall_hook.py", encoded)

    def test_uninstall_removes_only_ambient_hook(self) -> None:
        installer.install(self.hooks_json, timeout=5)
        data = self.read_hooks()
        data["hooks"]["UserPromptSubmit"][0]["hooks"].append(
            {
                "type": "command",
                "command": "python other_user_prompt_hook.py",
                "timeout": 10,
            }
        )
        self.hooks_json.write_text(json.dumps(data), encoding="utf-8")

        result = installer.uninstall(self.hooks_json)

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

        installer.install(self.hooks_json, timeout=5)
        with patch(
            "aippocampus_runtime.hooks.debug_log.default_prompt_hook_status_path",
            return_value=status_path,
        ):
            result = installer.status(
                self.hooks_json,
                include_last=True,
                telemetry_path=self.codex_home / "no-skip-telemetry.json",
            )

        self.assertEqual(result["last_prompt_hook_status"], "found")
        self.assertEqual(
            result["last_prompt_hook_memory_surface"],
            "candidate",
        )
        self.assertEqual(result["foreground_action"]["id"], "try_first_recall_after_prompt_hook")
        self.assertIn("command_template", result["foreground_action"])
        self.assertEqual(result["foreground_action"]["tool_name"], "agent_recall")
        self.assertEqual(
            result["foreground_action"]["tool_args_template"],
            {"cue": "{continuity_cue}", "detail": "compact"},
        )
        self.assertEqual(result["foreground_action"]["requires"], ["continuity_cue"])
        self.assertEqual(foreground_action_contract_violations(result), [])
        self.assertEqual(result["last_prompt_hook_review"]["id"], "review_last_prompt_hook_recall")
        self.assertIn("foreground_action", result)
        self.assertGreater(result["last_prompt_hook_useful_signal_count"], 0)
        public_status = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("last_prompt_hook", result)
        self.assertNotIn("prompt_hook_latency_risk", result)
        self.assertTrue(result["operator_json_available"])
        self.assertEqual(
            result["operator_json_command"],
            "aippocampus hooks prompt status --last --operator-json",
        )
        self.assertEqual(result["path"], "hooks.json")
        self.assertTrue(result["path_redacted"])
        self.assertEqual(result["commands"], ["<redacted:hook-command>"])
        self.assertTrue(result["commands_redacted"])
        self.assertNotIn("private cached theme", public_status)
        self.assertNotIn("private candidate", public_status)
        self.assertNotIn("private-session", public_status)
        self.assertNotIn(str(self.codex_home), public_status)
        self.assertNotIn(str(SCRIPTS.resolve()), public_status)

        with patch(
            "aippocampus_runtime.hooks.debug_log.default_prompt_hook_status_path",
            return_value=status_path,
        ):
            operator = installer.status(
                self.hooks_json,
                include_last=True,
                telemetry_path=self.codex_home / "no-skip-telemetry.json",
                include_operator_detail=True,
            )
        self.assertEqual(operator["last_prompt_hook"]["status"], "found")
        self.assertEqual(
            operator["last_prompt_hook"]["last_prompt_hook"]["memory_surface"],
            "candidate",
        )

    def test_status_last_surfaces_aggregate_latency_risk_action(self) -> None:
        telemetry_path = self.codex_home / "prompt_hook_skip_telemetry.json"
        write_skip_telemetry(
            {
                "decision": "skip",
                "score": 0.0,
                "confidence": "low",
                "reasons": ["no ambient recall cue"],
                "semantic_gate": {
                    "available": False,
                    "availability_reason": "foreground_budget_skipped",
                },
                "ambient_recall": {"cache_status": {"status": "miss"}},
                "elapsed_ms": 4310.0,
            },
            telemetry_path=telemetry_path,
            hook_budget_ms=4300,
            semantic_timeout=2.5,
            runtime_load_ms=210.0,
            hook_total_ms=4625.0,
        )
        installer.install(self.hooks_json, timeout=5)

        result = installer.status(
            self.hooks_json,
            include_last=True,
            telemetry_path=telemetry_path,
        )
        encoded = json.dumps(result, ensure_ascii=False)

        self.assertNotIn("prompt_hook_latency_risk", result)
        self.assertEqual(result["foreground_action"]["id"], "inspect_prompt_hook_output")
        self.assertEqual(result["foreground_action"]["mutation_risk"], "read_only")
        self.assertIn("foreground_action", result)
        self.assertEqual(result["prompt_hook_latency_risk_status"], "near_host_timeout_risk")
        self.assertGreaterEqual(result["foreground_latency_red_line_violation_count"], 1)
        action_ids = [action["id"] for action in result["safe_next_actions"]]
        self.assertNotIn("refresh_prompt_hook_safe_budget", action_ids)
        self.assertTrue(all(action["mutation_risk"] == "read_only" for action in result["safe_next_actions"]))
        self.assertEqual(result["manage_command"], "aippocampus hooks prompt uninstall --json")
        self.assertNotIn(str(self.codex_home), encoded)

        operator = installer.status(
            self.hooks_json,
            include_last=True,
            telemetry_path=telemetry_path,
            include_operator_detail=True,
        )
        risk = operator["prompt_hook_latency_risk"]
        self.assertEqual(risk["status"], "near_host_timeout_risk")
        self.assertGreaterEqual(risk["foreground_latency_red_line_violation_count"], 1)
        self.assertGreaterEqual(risk["near_timeout_event_count"], 1)

    def test_status_last_separates_stale_latency_history_from_current_risk(self) -> None:
        telemetry_path = self.codex_home / "prompt_hook_skip_telemetry.json"
        telemetry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "updated_at": "2000-01-01T00:00:00Z",
                    "total_events": 12,
                    "hook_budget_ms_counts": {"4300": 7},
                    "latency_ms": {
                        "buckets": {
                            "hook_elapsed": {"gte_4300": 2},
                            "hook_total": {"gte_4300": 3},
                        },
                        "last": {
                            "hook_elapsed": 2597.04,
                            "hook_total": 2737.06,
                            "runtime_load": 76.2,
                            "startup_import_io": 140.02,
                        },
                    },
                    "last_event": {
                        "timestamp": "2000-01-01T00:00:00Z",
                        "decision": "skip",
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        installer.install(self.hooks_json, timeout=5)

        result = installer.status(
            self.hooks_json,
            include_last=True,
            telemetry_path=telemetry_path,
        )
        action_ids = [action["id"] for action in result["safe_next_actions"]]

        self.assertEqual(result["prompt_hook_latency_risk_status"], "stale_history_only")
        self.assertEqual(result["prompt_hook_latency_current_status"], "stale_history_only")
        self.assertEqual(result["prompt_hook_latency_freshness_status"], "stale_history_only")
        self.assertEqual(
            result["prompt_hook_latency_historical_status"],
            "historical_near_timeout_seen",
        )
        self.assertEqual(result["foreground_latency_red_line_violation_count"], 0)
        self.assertEqual(result["prompt_hook_near_timeout_event_count"], 0)
        self.assertGreaterEqual(
            result["historical_foreground_latency_red_line_violation_count"],
            1,
        )
        self.assertNotIn("refresh_prompt_hook_safe_budget", action_ids)

        operator = installer.status(
            self.hooks_json,
            include_last=True,
            telemetry_path=telemetry_path,
            include_operator_detail=True,
        )
        risk = operator["prompt_hook_latency_risk"]
        self.assertEqual(risk["status"], "stale_history_only")
        self.assertEqual(risk["foreground_latency_red_line_violation_count"], 0)
        self.assertGreaterEqual(
            risk["historical_foreground_latency_red_line_violation_count"],
            1,
        )

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
            include_last=True,
            log_path=log_path,
            telemetry_path=self.codex_home / "no-skip-telemetry.json",
            include_operator_detail=True,
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
        installer.install(self.hooks_json, timeout=5)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = installer.main(
                [
                    "status",
                    "--hooks-json",
                    str(self.hooks_json),
                    "--last",
                    "--log-path",
                    str(log_path),
                    "--skip-telemetry-path",
                    str(self.codex_home / "no-skip-telemetry.json"),
                    "--json",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertNotIn("last_prompt_hook", payload)
        self.assertNotIn("prompt_hook_latency_risk", payload)
        self.assertEqual(payload["foreground_action"]["id"], "try_first_recall_after_prompt_hook")
        self.assertIn("command_template", payload["foreground_action"])
        self.assertEqual(payload["foreground_action"]["tool_name"], "agent_recall")
        self.assertEqual(
            payload["foreground_action"]["tool_args_template"],
            {"cue": "{continuity_cue}", "detail": "compact"},
        )
        self.assertEqual(payload["foreground_action"]["requires"], ["continuity_cue"])
        self.assertEqual(foreground_action_contract_violations(payload), [])
        self.assertEqual(payload["last_prompt_hook_review"]["id"], "review_last_prompt_hook_recall")
        self.assertIn("foreground_action", payload)
        self.assertEqual(payload["last_prompt_hook_memory_surface"], "candidate")
        self.assertGreater(payload["last_prompt_hook_useful_signal_count"], 0)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["path"], "hooks.json")
        self.assertTrue(payload["path_redacted"])
        self.assertNotIn("private cached theme", encoded)
        self.assertNotIn(str(self.codex_home), encoded)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = installer.main(
                [
                    "status",
                    "--hooks-json",
                    str(self.hooks_json),
                    "--last",
                    "--log-path",
                    str(log_path),
                    "--skip-telemetry-path",
                    str(self.codex_home / "no-skip-telemetry.json"),
                    "--operator-json",
                ]
            )

        self.assertEqual(code, 0)
        operator_payload = json.loads(stdout.getvalue())
        self.assertEqual(operator_payload["last_prompt_hook"]["status"], "found")
        self.assertEqual(
            operator_payload["last_prompt_hook"]["last_prompt_hook"]["memory_surface"],
            "candidate",
        )

    def test_text_cli_labels_prompt_installer_as_codex_only(self) -> None:
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
        self.assertIn("Codex prompt hook not installed", text)
        self.assertIn("host: codex", text)
        self.assertIn("host scope: codex_hooks_only", text)
        self.assertIn("config surface: codex_hooks_json", text)
        self.assertIn("provider-neutral: false", text)
        self.assertIn("other hosts: claude-code, generic-jsonl use onboarding/MCP/import routes", text)
        self.assertIn("not a failure", text)
        self.assertNotIn("unsupported host hooks", text)

if __name__ == "__main__":
    unittest.main()
