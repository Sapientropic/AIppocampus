from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_doc_tool_module

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"

docs_health = import_doc_tool_module("check_docs_health")
ia_pressure_guard = import_doc_tool_module("ia_pressure_guard")

from aippocampus_runtime.cli import facade
from aippocampus_runtime.update import agent_status_summary
from aippocampus_runtime.update import cli as update_cli


class ForegroundIssueSweepTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "aippocampus_runtime.cli.facade", *args],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

    def test_latest_reply_commentary_omits_long_or_internal_recovery_cues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            long_rollout = root / "long-commentary.jsonl"
            internal_rollout = root / "internal-commentary.jsonl"
            long_cue = "finish the foreground issue sweep\n" + ("with many requirements " * 20)
            internal_cue = (
                "<subagent_notification>"
                "agent-internal coordination material should not become a recall command"
                "</subagent_notification>"
            )
            for path, cue in ((long_rollout, long_cue), (internal_rollout, internal_cue)):
                path.write_text(
                    "\n".join(
                        [
                            json.dumps(
                                {
                                    "timestamp": "2026-06-16T00:00:00Z",
                                    "type": "event_msg",
                                    "payload": {"type": "user_message", "message": cue},
                                }
                            ),
                            json.dumps(
                                {
                                    "timestamp": "2026-06-16T00:00:01Z",
                                    "type": "event_msg",
                                    "payload": {
                                        "type": "agent_message",
                                        "phase": "commentary",
                                        "message": "still working, not final",
                                    },
                                }
                            ),
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )

            long_proc = self.run_cli("latest-reply", "--rollout", str(long_rollout), "--json")
            internal_proc = self.run_cli("latest-reply", "--rollout", str(internal_rollout), "--json")

        for proc in (long_proc, internal_proc):
            self.assertNotEqual(proc.returncode, 0)
            payload = json.loads(proc.stdout)
            action = payload["foreground_action"]
            encoded = json.dumps(payload, ensure_ascii=False)
            self.assertEqual(action["id"], "recall_current_thread_context")
            self.assertNotIn("command", action)
            self.assertEqual(action["command_template"], 'aippocampus agent recall "{cue}" --json')
            self.assertTrue(action["cue_omitted_from_executable_command"])
            self.assertNotIn("subagent_notification", encoded)
            self.assertNotIn("with many requirements with many requirements", encoded)

    def test_background_routes_offer_templates_and_dream_status_frontdoor(self) -> None:
        agent = facade.run_command(["agent", "--json"], capture_output=True)
        dream = facade.run_command(["dream", "--json"], capture_output=True)
        subconscious = facade.run_command(["subconscious", "--json"], capture_output=True)

        self.assertEqual(agent.exit_code, 0)
        agent_payload = json.loads(agent.stdout)
        self.assertIn("background", {choice["id"] for choice in agent_payload["choices"]})
        self.assertEqual(dream.exit_code, 2)
        dream_payload = json.loads(dream.stdout)
        self.assertEqual(
            dream_payload["foreground_action"]["command_template"],
            'aippocampus agent background "{task_cue}" --json',
        )
        self.assertNotIn("command", dream_payload["foreground_action"])
        self.assertEqual(dream_payload["foreground_action"]["requires"], ["task_cue"])
        with tempfile.TemporaryDirectory() as tmp:
            dream_status = facade.run_command(
                ["dream", "status", "--registry-dir", tmp, "--json"],
                capture_output=True,
            )
        self.assertEqual(dream_status.exit_code, 0, dream_status.stderr)
        status_payload = json.loads(dream_status.stdout)
        self.assertEqual(status_payload["kind"], "aippocampus_dream_status")
        self.assertIn("dream_output_status_card", status_payload)
        self.assertEqual(subconscious.exit_code, 2)
        self.assertEqual(subconscious.stderr, "")
        self.assertNotIn("unknown command", dream.stderr)
        self.assertNotIn("unknown command", subconscious.stderr)

    def test_current_claims_guard_rejects_ambiguous_snapshot_date_with_newer_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            evidence = repo / "docs" / "evidence"
            evidence.mkdir(parents=True)
            (evidence / "current-claims.md").write_text(
                "\n".join(
                    [
                        "# Current Evidence Claims",
                        "Snapshot date: 2026-06-15.",
                        "## Current Claim Snapshot",
                        (
                            "metric_id run_date source_report claim_level cohort supersedes "
                            "supports material_limits cannot_claim"
                        ),
                        "semantic_sidecar.aggregate_materialized_rows",
                        "semantic_sidecar.strict_survival_snapshot",
                        "semantic_sidecar.source_review_green_gate",
                        "semantic_sidecar.source_review_diagnostic",
                        "track_b.private_semantic_sidecar_required",
                        "fts5.real_history_recall_2026_05_29",
                        "demo_scenarios.claim_boundaries",
                        "| metric_id | run_date | source_report | claim_level | cohort | supersedes | supports | material_limits | cannot_claim |",
                        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                        "| newer.row | 2026-06-20 | report | diagnostic | fixture | - | yes | bounded | broad |",
                        "## Claim-Boundary Owner And Retirement Ledger",
                        "| Caveat | Category | Owner issue | Retirement condition | Next review |",
                        "| --- | --- | --- | --- | --- |",
                        "| Claude Code hooks | actionable | #1020 | source-backed test | before Beta readiness update |",
                    ]
                ),
                encoding="utf-8",
            )

            issues = docs_health.current_claims_snapshot_issues(repo)

        self.assertIn(
            "current claims snapshot date is ambiguous: newer row-level dates exist "
            "without foreground text saying row-level dates are authoritative",
            issues,
        )

    def test_documented_research_folder_pressure_is_not_warning_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            research = repo / "docs" / "research"
            research.mkdir(parents=True)
            (research / "README.md").write_text(
                "\n".join(
                    [
                        "# Research Notes",
                        "",
                        "Role: speculative research index.",
                        "Status: research map, not runtime contract.",
                        "Folder pressure owner: docs/research/README.md.",
                        "Folder pressure next action: route new notes to seeds, reports, or archive.",
                    ]
                ),
                encoding="utf-8",
            )
            for index in range(ia_pressure_guard.FOLDER_PRESSURE_MARKDOWN_THRESHOLD - 1):
                (research / f"note-{index}.md").write_text(
                    "Role: research note\nStatus: active\n",
                    encoding="utf-8",
                )

            report = ia_pressure_guard.information_architecture_diagnostics(
                repo,
                allowed_root_markdown=docs_health.DOCS_ROOT_ALLOWED_MARKDOWN,
                allowed_root_directories=docs_health.DOCS_ROOT_ALLOWED_DIRECTORIES,
            )

        self.assertFalse(
            any(warning["code"] == "docs_folder_file_count_pressure" for warning in report["warnings"]),
            report["warnings"],
        )

    def test_agent_json_status_prioritizes_foreground_tool_verification(self) -> None:
        payload = agent_status_summary.compact_agent_status_report(
            {
                "ok": True,
                "mode": "status",
                "summary": {
                    "partial_readiness": True,
                    "plan_scope": "foreground_partial",
                    "agent_callable_ready": False,
                    "agent_callable_host_ready": True,
                    "agent_callable_current_thread_visible": False,
                    "agent_callable_status": "host_live_probe_ok_foreground_probe_not_checked",
                    "needs_action": [],
                    "deferred_components": ["mcp", "agent_callable"],
                },
                "surfaces": {
                    "mcp": {
                        "status": "deferred",
                        "operator_detail_available": True,
                        "deferred_component": "mcp",
                    },
                    "agent_callable": {
                        "surface": "agent_callable",
                        "ready": False,
                        "status": "host_live_probe_ok_foreground_probe_not_checked",
                        "next_command": "aippocampus update status --foreground-tools-visible --agent-json",
                        "foreground_probe_state": "not_requested",
                        "foreground_tools_visible": None,
                        "foreground_probe_requested": False,
                        "host_live_probe": {"ok": True},
                        "operator_detail_available": True,
                        "deferred_component": "agent_callable",
                    },
                },
            },
            schema_version=update_cli.SCHEMA_VERSION,
        )
        self.assertEqual(
            payload["summary"]["agent_callable_status"],
            "host_live_probe_ok_foreground_probe_not_checked",
        )
        self.assertEqual(payload["foreground_action"]["surface"], "agent_callable")
        self.assertIn("--foreground-tools-visible --agent-json", payload["foreground_action"]["command"])
        self.assertNotIn("--foreground-key-tools-callable", payload["foreground_action"]["command"])
        self.assertFalse(
            any(action.get("surface") == "operator_detail" for action in payload["safe_next_actions"]),
            payload["safe_next_actions"],
        )

    def test_agent_json_status_prioritizes_measured_ambient_blockers_over_tool_review(self) -> None:
        payload = agent_status_summary.compact_agent_status_report(
            {
                "ok": True,
                "mode": "status",
                "summary": {
                    "core_ready": True,
                    "agent_callable_ready": False,
                    "agent_callable_host_ready": True,
                    "agent_callable_current_thread_visible": False,
                    "agent_callable_status": "host_live_probe_ok_foreground_probe_not_checked",
                    "needs_action": [],
                },
                "surfaces": {
                    "agent_callable": {
                        "surface": "agent_callable",
                        "ready": False,
                        "status": "host_live_probe_ok_foreground_probe_not_checked",
                        "next_command": "aippocampus update status --foreground-tools-visible --agent-json",
                        "foreground_probe_state": "not_requested",
                        "host_live_probe": {"ok": True},
                    },
                    "hooks": {
                        "status": "current",
                        "prompt_installed": True,
                        "lifecycle_installed": True,
                        "action_hints": {
                            "installed": True,
                            "cache_status": "with_missing_cache_file",
                        },
                        "prompt_hook_status": {
                            "prompt_hook_latency_risk_status": "near_host_timeout_risk",
                            "foreground_latency_red_line_violation_count": 1,
                            "near_timeout_event_count": 2,
                        },
                        "warm_ambient": {
                            "status": "blocked",
                            "next_command": "aippocampus warm status --json",
                            "job_activity": {
                                "queue_state": "blocked_stale_pending",
                                "stale_queue_blocked": True,
                            },
                        },
                    },
                    "llm": {"status": "missing_provider_env_var"},
                },
            },
            schema_version=update_cli.SCHEMA_VERSION,
        )

        ordered_surfaces = [
            payload["foreground_action"].get("surface"),
            *[action.get("surface") for action in payload["safe_next_actions"]],
        ]
        self.assertEqual(payload["foreground_action"]["surface"], "prompt_hook_latency")
        self.assertEqual(
            ordered_surfaces[:5],
            [
                "prompt_hook_latency",
                "warm_ambient",
                "provider",
                "action_hints",
                "agent_callable",
            ],
        )
        self.assertEqual(
            payload["ambient_recall"]["next_command"],
            "aippocampus hooks prompt status --last --json",
        )

    def test_agent_json_status_keeps_true_foreground_tool_failure_first(self) -> None:
        payload = agent_status_summary.compact_agent_status_report(
            {
                "ok": True,
                "mode": "status",
                "summary": {
                    "core_ready": True,
                    "agent_callable_ready": False,
                    "agent_callable_host_ready": True,
                    "agent_callable_current_thread_visible": False,
                    "agent_callable_status": "foreground_mcp_runtime_mismatch",
                    "needs_action": [],
                },
                "surfaces": {
                    "agent_callable": {
                        "surface": "agent_callable",
                        "ready": False,
                        "status": "foreground_mcp_runtime_mismatch",
                        "next_command": "aippocampus agent recall \"old decision\" --json",
                        "foreground_probe_state": "failed",
                        "host_live_probe": {"ok": True},
                    },
                    "hooks": {
                        "status": "current",
                        "prompt_installed": True,
                        "prompt_hook_status": {
                            "prompt_hook_latency_risk_status": "near_host_timeout_risk",
                            "foreground_latency_red_line_violation_count": 1,
                        },
                    },
                },
            },
            schema_version=update_cli.SCHEMA_VERSION,
        )

        self.assertEqual(payload["foreground_action"]["surface"], "agent_callable")
        self.assertEqual(payload["foreground_action"]["status_code"], "foreground_mcp_runtime_mismatch")
        self.assertEqual(payload["safe_next_actions"][0]["surface"], "prompt_hook_latency")

if __name__ == "__main__":
    unittest.main()
