from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"

from aippocampus_runtime.hooks import action_hint, action_hint_cache, foreground_status
from aippocampus_runtime.hooks.install_action_hint_projection import action_hint_frontstage_card


def source_ref(name: str) -> dict[str, str]:
    return {"source_id": f"clean:{name}", "segment_id": f"msg-{name}"}

class ActionHintHookTests(unittest.TestCase):
    def test_active_status_points_foreground_agent_to_compact_probe(self) -> None:
        card = action_hint_frontstage_card(
            {
                "installed": True,
                "cache_status": "with_fresh_records",
                "cache_record_count": 1,
                "fresh_record_count": 1,
            }
        )
        status = foreground_status.action_hint_status_contract(card)

        self.assertEqual(status["foreground_action"]["id"], "probe_action_hint_hot_path")
        self.assertEqual(
            status["foreground_action"]["command"],
            "aippocampus hooks action probe --compact-json",
        )

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

    def test_prepared_reopenable_route_hints_before_broad_search(self) -> None:
        cache_report = action_hint_cache.build_action_hint_cache_report(
            attention_route_tokens=[
                {
                    "token_id": "prepared-route-before-broad-search",
                    "action_hint_kind": "reopen_route_before_broad_search",
                    "next_action": "reopen_prepared_route_before_broad_search",
                    "source_handles": [
                        {
                            "source_id": "clean:issue1844",
                            "segment_id": "msg-issue1844",
                            "reopen_required": True,
                        }
                    ],
                    "route_features": {"terms": ["issue1844", "prepared", "route"]},
                    "route_metadata": {"privacy": "public", "currentness": "current"},
                    "command_terms": ["broad_search", "search"],
                }
            ],
            now_unix=1000,
        )
        envelope = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "rg issue1844 PRIVATE_REPO_SENTINEL",
            },
            "intent": "broad search for issue1844",
        }

        report = action_hint.evaluate_action_hint(envelope, cache_report, now_unix=1001)
        serialized = json.dumps(report, ensure_ascii=False)

        self.assertEqual(report["decision"], "hint")
        self.assertIn("broad_search", report["features"]["command_terms"])
        self.assertEqual(
            report["hint"]["recommended_action"],
            "reopen_prepared_route_before_broad_search",
        )
        self.assertTrue(report["hint"]["navigation_only"])
        self.assertNotIn("PRIVATE_REPO_SENTINEL", serialized)

    def test_probe_reports_useful_only_with_followthrough_source_handle(self) -> None:
        cache_report = action_hint_cache.build_action_hint_cache_report(
            recent_recall_routes=[
                {
                    "record_id": "recent-route",
                    "route_id": "route_recent",
                    "request_index": 1,
                    "recall_selector": "sel_1234567890abcdef",
                    "query": "黏菌 联想回忆 探索算法",
                    "opened_count": 1,
                }
            ],
            now_unix=1000,
        )
        for record in cache_report["records"]:
            record["expires_at_unix"] = 9999999999
        report = action_hint.evaluate_action_hint(
            action_hint._default_probe_envelope(),
            cache_report,
            now_unix=1001,
        )
        with mock.patch(
            "aippocampus_runtime.hooks.recent_recall_routes.probe_recent_recall_handle_followthrough",
            return_value={
                "status": "passed",
                "reason": "opened_source_anchor_coverage",
                "opened_anchor_hits": 2,
                "target_source_matched": True,
            },
        ):
            full_payload = action_hint._with_probe_usefulness(dict(report))
        payload = action_hint.compact_probe_report(full_payload)
        encoded = json.dumps(payload, ensure_ascii=False)
        full_encoded = json.dumps(full_payload, ensure_ascii=False)
        self.assertEqual(payload["detail"], "compact")
        self.assertEqual(payload["kind"], "aippocampus_action_hint_probe_compact")
        self.assertEqual(payload["decision"], "hint")
        self.assertTrue(payload["useful"])
        self.assertEqual(payload["usefulness_stage"], "useful")
        self.assertNotIn("features", payload)
        self.assertNotIn("diagnostics", payload)
        self.assertNotIn("privacy_boundary", payload)
        self.assertNotIn("diagnostic_fields_omitted", payload)
        self.assertNotIn("operator_detail_command", payload)
        self.assertNotIn("source_reopen_boundary", payload)
        self.assertNotIn("claim_boundary", payload)
        self.assertNotIn("safe_next_actions", payload)
        self.assertEqual(payload["foreground_action"]["tool_name"], "agent_deepen")
        self.assertNotIn("claim_boundary", payload["foreground_action"])
        self.assertIn("agent deepen", payload["foreground_action"]["command"])
        self.assertEqual(
            payload["foreground_action"]["arguments"]["recall_selector"],
            "sel_1234567890abcdef",
        )
        self.assertNotIn("source_handle", payload["hint"])
        self.assertNotIn("local_reopen_token", encoded)
        self.assertEqual(
            full_payload["diagnostics"]["source_followthrough_handle_count"],
            1,
        )
        self.assertEqual(
            full_payload["diagnostics"]["source_followthrough_probe"]["status"],
            "passed",
        )
        handle = full_payload["hint"]["source_handles"][0]
        self.assertEqual(handle["tool_name"], "agent_deepen")
        self.assertEqual(handle["arguments"]["recall_selector"], "sel_1234567890abcdef")
        self.assertEqual(handle["query"], "黏菌 联想回忆 探索算法")
        self.assertIn("features", full_payload)
        self.assertIn("diagnostics", full_payload)
        self.assertNotIn("local_reopen_token", full_encoded)

        with mock.patch(
            "aippocampus_runtime.hooks.recent_recall_routes.probe_recent_recall_handle_followthrough",
            return_value={"status": "blocked", "reason": "stale_recall_handle"},
        ):
            stale_payload = action_hint.compact_probe_report(
                action_hint._with_probe_usefulness(dict(report))
            )
        self.assertFalse(stale_payload["useful"])
        self.assertEqual(stale_payload["usefulness_stage"], "active")
        self.assertEqual(stale_payload["reason"], "stale_recall_handle")
        self.assertEqual(stale_payload["foreground_action"]["id"], "refresh_probe_source_route")
        self.assertNotIn("agent deepen", stale_payload["foreground_action"]["command"])
        self.assertEqual(stale_payload["foreground_action"]["mutation_risk"], "read_only")
        self.assertNotIn("claim_boundary", stale_payload["foreground_action"])

    def test_compact_probe_labels_cache_refresh_as_explicit_write(self) -> None:
        payload = action_hint.compact_probe_report(
            {
                "schema_version": 1,
                "ok": True,
                "decision": "silent",
                "reason": "cache_not_ready",
                "hint": None,
                "useful": False,
                "usefulness_stage": "callable",
            }
        )

        action = payload["foreground_action"]
        self.assertEqual(action["id"], "refresh_probe_source_route")
        self.assertIn("refresh-cache --write", action["command"])
        self.assertEqual(action["mutation_risk"], "explicit_local_cache_write")
        self.assertNotIn("claim_boundary", action)
        self.assertNotIn("claim_boundary", payload)
        self.assertNotIn("source_reopen_boundary", payload)
        self.assertTrue(payload["details_available"])
        self.assertFalse(payload["useful"])

    def test_probe_auto_chains_missing_cache_before_foregrounding_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "action-hints.jsonl"

            def fake_refresh(**kwargs: object) -> dict[str, object]:
                record = {
                    "schema_version": 1,
                    "kind": "aippocampus_action_hint_prepared_record",
                    "record_id": "auto-chain-record",
                    "provider_family": "recent_recall_route",
                    "action_hint_kind": "reopen_route_before_action",
                    "next_action": "reopen_route_before_action",
                    "navigation_only": True,
                    "no_claim_before_reopen": True,
                    "source_reopen_required": True,
                    "can_support_factual_claim": False,
                    "authority": "navigation_only",
                    "freshness": "current",
                    "expires_at_unix": 9999999999,
                    "confidence": "high",
                    "occurrence_count": 1,
                    "source_refs": [source_ref("auto-chain")],
                    "source_handles": [
                        {
                            "tool_name": "agent_deepen",
                            "command": "aippocampus agent deepen --recall-selector sel_auto",
                            "arguments": {"recall_selector": "sel_auto"},
                            "query": "AIppocampus recall source route",
                            "reopen_required": True,
                        }
                    ],
                    "command_terms": ["rg", "search"],
                    "match_terms": ["aippocampus", "recall", "source", "route"],
                    "privacy_boundary": {
                        "raw_prompt_stored": False,
                        "raw_command_text_stored": False,
                        "raw_tool_args_stored": False,
                        "local_paths_stored": False,
                        "model_reasoning_stored": False,
                    },
                }
                report = {
                    "kind": "aippocampus_action_hint_prepared_cache",
                    "schema_version": 1,
                    "record_count": 1,
                    "records": [record],
                    "provider_counts": {"recent_recall_route": 1},
                    "privacy_boundary": {},
                }
                action_hint_cache.write_action_hint_cache(Path(kwargs["cache_jsonl"]), report)
                return {
                    "ok": True,
                    "cache_status": "with_cache_records",
                    "cache": report,
                    "action_hints_ready": True,
                    "foreground_action": {
                        "id": "check_action_hint_status",
                        "label": "Check action hint status",
                        "command": "aippocampus hooks action status --json",
                        "mutation_risk": "read_only",
                        "claim_boundary": "action_hints_are_navigation_not_source_truth",
                    },
                }

            stdout = io.StringIO()
            with (
                mock.patch("sys.stdin", io.StringIO("")),
                mock.patch(
                    "aippocampus_runtime.hooks.action_hint_auto_chain.refresh_action_hint_cache",
                    side_effect=fake_refresh,
                ),
                mock.patch(
                    "aippocampus_runtime.hooks.recent_recall_routes.probe_recent_recall_handle_followthrough",
                    return_value={"status": "passed"},
                ),
                contextlib.redirect_stdout(stdout),
            ):
                code = action_hint.main(
                    ["probe", "--cache-jsonl", str(cache_path), "--compact-json"]
                )

        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(code, 0, payload)
        self.assertTrue(payload["auto_chained"])
        self.assertEqual(payload["auto_chain_status"], "auto_chained")
        self.assertNotIn("deferred_auto_chain_reason", payload)
        self.assertTrue(payload["useful"])
        self.assertEqual(payload["foreground_action"]["id"], "deepen_probe_source_route")
        self.assertNotIn("refresh-cache --write", encoded)
        self.assertNotIn(str(cache_path), encoded)

    def test_probe_explains_deferred_auto_chain_when_write_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "action-hints.jsonl"
            stdout = io.StringIO()
            with (
                mock.patch("sys.stdin", io.StringIO("")),
                mock.patch(
                    "aippocampus_runtime.hooks.action_hint.action_hint_refresh_auto_chain"
                ) as auto_chain,
                contextlib.redirect_stdout(stdout),
            ):
                auto_chain.return_value = {
                    "status": "deferred",
                    "reason": "auto_chain_disabled",
                }
                code = action_hint.main(
                    [
                        "probe",
                        "--cache-jsonl",
                        str(cache_path),
                        "--no-auto-chain",
                        "--compact-json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0, payload)
        self.assertFalse(payload["auto_chained"])
        self.assertEqual(payload["auto_chain_status"], "deferred")
        self.assertEqual(payload["deferred_auto_chain_reason"], "auto_chain_disabled")
        self.assertIn("refresh-cache --write", payload["foreground_action"]["command"])

    def test_probe_defers_auto_chain_when_lock_busy_or_latency_budget_spent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "action-hints.jsonl"
            lock_path = cache_path.with_suffix(cache_path.suffix + ".auto-chain.lock")
            lock_path.write_text('{"owner_token":"other","created_at":"now"}', encoding="utf-8")
            busy_stdout = io.StringIO()
            with (
                mock.patch("sys.stdin", io.StringIO("")),
                mock.patch(
                    "aippocampus_runtime.hooks.action_hint_auto_chain.refresh_action_hint_cache"
                ) as refresh,
                contextlib.redirect_stdout(busy_stdout),
            ):
                busy_code = action_hint.main(
                    ["probe", "--cache-jsonl", str(cache_path), "--compact-json"]
                )
            refresh.assert_not_called()

            latency_stdout = io.StringIO()
            with (
                mock.patch("sys.stdin", io.StringIO("")),
                contextlib.redirect_stdout(latency_stdout),
            ):
                latency_code = action_hint.main(
                    [
                        "probe",
                        "--cache-jsonl",
                        str(cache_path),
                        "--auto-chain-max-elapsed-ms",
                        "0",
                        "--compact-json",
                    ]
                )

        busy_payload = json.loads(busy_stdout.getvalue())
        latency_payload = json.loads(latency_stdout.getvalue())
        self.assertEqual(busy_code, 0, busy_payload)
        self.assertEqual(busy_payload["auto_chain_status"], "deferred")
        self.assertEqual(busy_payload["deferred_auto_chain_reason"], "refresh_lock_busy")
        self.assertEqual(latency_code, 0, latency_payload)
        self.assertEqual(latency_payload["auto_chain_status"], "deferred")
        self.assertEqual(
            latency_payload["deferred_auto_chain_reason"],
            "latency_budget_exhausted",
        )

    def test_hot_run_path_never_auto_chains_cache_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "action-hints.jsonl"
            stdout = io.StringIO()
            with (
                mock.patch(
                    "sys.stdin",
                    io.StringIO(
                        json.dumps(
                            {
                                "hook_event_name": "PreToolUse",
                                "tool_name": "Bash",
                                "tool_input": {"command": "rg recall", "command_family": "rg"},
                            }
                        )
                    ),
                ),
                mock.patch(
                    "aippocampus_runtime.hooks.action_hint.action_hint_refresh_auto_chain"
                ) as auto_chain,
                contextlib.redirect_stdout(stdout),
            ):
                code = action_hint.main(["run", "--cache-jsonl", str(cache_path), "--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0, payload)
        auto_chain.assert_not_called()
        self.assertFalse(cache_path.exists())
        self.assertEqual(payload["decision"], "silent")
        self.assertEqual(payload["diagnostics"]["cache_status"], "with_missing_cache_file")

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

    def test_empty_cache_fast_bails_before_feature_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "empty-action-hints.jsonl"
            cache_path.write_text("", encoding="utf-8")
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
                        "tool_input": {
                            "command": "pytest E:/Users/private/project/tests/test_secret.py",
                            "file_path": "E:/Users/private/project/tests/test_secret.py",
                        },
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
        self.assertEqual(payload["decision"], "silent")
        self.assertEqual(payload["reason"], "cache_not_ready")
        self.assertEqual(payload["features"], {})
        self.assertTrue(payload["diagnostics"]["hot_path_bailed"])
        self.assertEqual(payload["diagnostics"]["cache_status"], "with_empty_cache")
        self.assertNotIn("E:/Users/private", encoded)

if __name__ == "__main__":
    unittest.main()
