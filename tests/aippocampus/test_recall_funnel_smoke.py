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

from aippocampus_runtime.ops import recall_funnel_live_agent_gate, recall_funnel_smoke  # noqa: E402


class RecallFunnelSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.clean = self.cwd / ".aippocampus" / "clean-source"
        self.clean.mkdir(parents=True)
        messages = [
            {
                "message_id": "msg_user",
                "turn_id": "turn_1",
                "source_id": "src_test",
                "source_line": 2,
                "role": "user",
                "phase": "",
                "turn_index": 1,
                "is_final": False,
                "text": "Recall funnel smoke should reopen clean source without printing this private wording.",
            },
            {
                "message_id": "msg_final",
                "turn_id": "turn_1",
                "source_id": "src_test",
                "source_line": 3,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 1,
                "is_final": True,
                "text": r"The progressive recall evidence lives at E:\private\secret.txt.",
            },
        ]
        with (self.clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for item in messages:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        with (self.clean / "turns.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {
                        "turn_id": "turn_1",
                        "turn_index": 1,
                        "message_ids": ["msg_user", "msg_final"],
                        "assistant_phase": "final_answer",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_recall_funnel_reports_counts_without_leaking_cue_source_text_or_paths(self) -> None:
        report = recall_funnel_smoke.build_recall_funnel_smoke(
            "SECRET_TOKEN=abc progressive recall evidence",
            cwd=self.cwd,
            max_routes=3,
        )
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertTrue(report["ok"])
        self.assertGreaterEqual(report["context"]["route_count"], 1)
        self.assertGreaterEqual(report["context"]["handle_count"], 1)
        self.assertEqual(report["selected_route"]["suggested_next_tool"], "recall_deepen")
        self.assertEqual(report["deepen"]["source_ref_count"], 1)
        self.assertEqual(report["deepen"]["source_window_message_count"], 2)
        self.assertIn("source_window", report["deepen"]["field_names"])
        self.assertIn("source_refs", report["deepen"]["field_names"])
        self.assertFalse(report["deepen"]["wrong_or_stale_handle"])
        self.assertFalse(report["privacy"]["raw_cue_echoed"])
        self.assertFalse(report["privacy"]["source_window_text_included"])
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn("private wording", encoded)
        self.assertNotIn(r"E:\private\secret.txt", encoded)
        self.assertNotIn(str(self.cwd), encoded)

    def test_clean_source_unavailable_reports_safe_error_without_echoing_cue_or_path(self) -> None:
        missing_cwd = self.cwd / "missing-workspace"
        report = recall_funnel_smoke.build_recall_funnel_smoke(
            "SECRET_TOKEN=abc private cue",
            cwd=missing_cwd,
        )
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertFalse(report["ok"])
        self.assertTrue(report["context"]["is_error"])
        self.assertEqual(report["context"]["error"]["code"], "clean_source_unavailable")
        self.assertEqual(report["deepen"]["status"], "not_run")
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn(str(missing_cwd), encoded)

    def test_stale_deepen_error_sets_wrong_or_stale_handle_without_leaking_handle(self) -> None:
        stale_response = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "ok": False,
                            "error": {"code": "stale_recall_handle", "message": "stale"},
                            "metrics": {
                                "funnel_stage": "deepen",
                                "source_reopen_success": False,
                                "wrong_or_stale_handle": True,
                            },
                        },
                        ensure_ascii=False,
                    ),
                }
            ],
            "isError": True,
        }
        with mock.patch.object(
            recall_funnel_smoke.mcp_server,
            "call_recall_deepen",
            return_value=stale_response,
        ):
            report = recall_funnel_smoke.build_recall_funnel_smoke(
                "progressive recall evidence",
                cwd=self.cwd,
            )
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertFalse(report["ok"])
        self.assertTrue(report["deepen"]["is_error"])
        self.assertEqual(report["deepen"]["error"]["code"], "stale_recall_handle")
        self.assertTrue(report["deepen"]["wrong_or_stale_handle"])
        self.assertNotIn("aippo-nav:", encoded)

    def test_registry_only_route_is_not_misreported_as_recall_deepen_route(self) -> None:
        context_response = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "kind": "aippocampus_recall_context",
                            "status": "ok",
                            "route_count": 1,
                            "routes": [
                                {
                                    "handle": {
                                        "kind": "thread_candidate",
                                        "thread_key": "thread-private",
                                        "route_id": "route_1",
                                    },
                                    "kind": "thread_candidate",
                                    "reopenable": False,
                                    "suggested_next": {"tool": "search_memory"},
                                }
                            ],
                            "source_boundary": {"read_only": True},
                            "metrics": {"funnel_stage": "context", "handle_count": 1},
                        },
                        ensure_ascii=False,
                    ),
                }
            ],
            "isError": False,
        }
        with mock.patch.object(
            recall_funnel_smoke.mcp_server,
            "call_recall_context",
            return_value=context_response,
        ), mock.patch.object(recall_funnel_smoke.mcp_server, "call_recall_deepen") as deepen:
            report = recall_funnel_smoke.build_recall_funnel_smoke(
                "registry-only cue",
                cwd=self.cwd,
            )
        encoded = json.dumps(report, ensure_ascii=False)

        self.assertFalse(report["ok"])
        self.assertFalse(report["selected_route"]["available"])
        self.assertEqual(report["deepen"]["error"]["code"], "no_recall_deepen_route")
        self.assertNotIn("thread-private", encoded)
        deepen.assert_not_called()

    def test_live_agent_gate_warns_on_low_specificity_even_when_source_reopens(self) -> None:
        agent_recall = {
            "status": "ok",
            "route_count": 2,
            "last_recall_cache_available": True,
            "recall_selector_available": True,
            "foreground_action": {
                "id": "refine_low_specificity_recall_cue",
                "route_choice_posture": "labels_low_specificity",
                "secondary_action": {
                    "id": "deepen_top_route_low_confidence",
                    "arguments": {"request_index": 1, "recall_selector": "sel_1234567890abcdef"},
                    "route_choice_posture": "labels_low_specificity",
                },
            },
            "routes": [
                {
                    "action": {
                        "id": "deepen_this_route",
                        "arguments": {"request_index": 1, "recall_selector": "sel_1234567890abcdef"},
                    }
                }
            ],
        }
        agent_deepen = {
            "status": "ok",
            "source_window_summary": {
                "has_exact_source": True,
                "message_count": 1,
                "source_ref_count": 1,
            },
        }

        with mock.patch.object(
            recall_funnel_live_agent_gate,
            "_agent_json",
            side_effect=[(0, agent_recall, None), (0, agent_deepen, None)],
        ), mock.patch.object(
            recall_funnel_live_agent_gate,
            "_ambient_hook_readiness",
            return_value={"status": "not_installed", "counts_toward_task_usefulness": False},
        ):
            report = recall_funnel_smoke.build_recall_funnel_smoke(
                "progressive recall evidence",
                cwd=self.cwd,
            )

        gate = report["live_agent_usefulness_gate"]
        self.assertTrue(report["ok"])
        self.assertEqual(gate["route_existence"]["status"], "pass")
        self.assertEqual(gate["route_specificity"]["status"], "warn")
        self.assertEqual(gate["source_reopen"]["status"], "pass")
        self.assertEqual(gate["task_usefulness"]["status"], "warn")
        self.assertEqual(gate["status"], "warn")
        self.assertEqual(gate["source_reopen"]["selected_selector_kind"], "recall_selector")

    def test_live_agent_gate_fails_when_selector_deepen_cannot_reopen_source(self) -> None:
        agent_recall = {
            "status": "ok",
            "route_count": 1,
            "last_recall_cache_available": True,
            "recall_selector_available": True,
            "foreground_action": {
                "id": "agent_deepen_selected_route",
                "arguments": {"request_index": 1, "recall_selector": "sel_1234567890abcdef"},
            },
            "routes": [
                {
                    "action": {
                        "id": "deepen_this_route",
                        "arguments": {"request_index": 1, "recall_selector": "sel_1234567890abcdef"},
                    }
                }
            ],
        }
        agent_deepen = {
            "status": "cannot_verify",
            "error": {"code": "stale_recall_handle"},
        }

        with mock.patch.object(
            recall_funnel_live_agent_gate,
            "_agent_json",
            side_effect=[(0, agent_recall, None), (2, agent_deepen, None)],
        ), mock.patch.object(
            recall_funnel_live_agent_gate,
            "_ambient_hook_readiness",
            return_value={"status": "not_installed", "counts_toward_task_usefulness": False},
        ):
            report = recall_funnel_smoke.build_recall_funnel_smoke(
                "progressive recall evidence",
                cwd=self.cwd,
            )

        gate = report["live_agent_usefulness_gate"]
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertFalse(report["ok"])
        self.assertEqual(gate["route_existence"]["status"], "pass")
        self.assertEqual(gate["route_specificity"]["status"], "pass")
        self.assertEqual(gate["source_reopen"]["status"], "fail")
        self.assertEqual(gate["source_reopen"]["error"]["code"], "stale_recall_handle")
        self.assertEqual(gate["task_usefulness"]["status"], "fail")
        self.assertNotIn("aippo-nav:", encoded)

    def test_cli_smoke_recall_funnel_runs_via_public_facade(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "smoke",
                "recall-funnel",
                "progressive recall evidence",
                "--cwd",
                str(self.cwd),
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
        self.assertEqual(payload["kind"], "aippocampus_recall_funnel_smoke")
        self.assertTrue(payload["ok"])

    def test_cli_smoke_recall_funnel_help_explains_diagnostic_boundary(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "smoke",
                "recall-funnel",
                "--help",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Recall funnel smoke task card", proc.stdout)
        self.assertIn("No persistent-write diagnostic", proc.stdout)
        self.assertIn("agent recall -> selector-backed agent deepen", proc.stdout)
        self.assertIn("Cue text, source text, and local/private paths are redacted", proc.stdout)
        self.assertIn("not source-backed evidence", proc.stdout)
        self.assertIn("agent recall -> agent deepen", proc.stdout)

    def test_cli_smoke_recall_funnel_json_missing_cue_returns_recovery_card(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "smoke",
                "recall-funnel",
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
        self.assertEqual(proc.stderr, "")
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["kind"], "aippocampus_recall_funnel_smoke_recovery")
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["cue_required"])
        self.assertEqual(payload["error"]["code"], "cue_required")
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(payload["foreground_action"], payload["agent_next_action"])
        self.assertEqual(payload["safe_next_actions"][0], payload["foreground_action"])
        self.assertIn("diagnostic", payload["source_boundary"]["claim_boundary"])
        self.assertIn("not source evidence", payload["source_boundary"]["claim_boundary"])

        smoke_action = payload["safe_next_actions"][0]
        ordinary_action = payload["safe_next_actions"][1]
        self.assertNotIn("command", smoke_action)
        self.assertNotIn("command", ordinary_action)
        self.assertIn("{cue}", smoke_action["command_template"])
        self.assertIn("{cue}", ordinary_action["command_template"])
        self.assertNotIn("<cue>", json.dumps(payload, ensure_ascii=False))
        self.assertIn("cue", smoke_action["requires"])
        self.assertIn("cue", ordinary_action["requires"])

    def test_cli_smoke_recall_funnel_human_missing_cue_is_concise(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "smoke",
                "recall-funnel",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stderr, "")
        self.assertIn("cue required", proc.stdout.lower())
        self.assertIn("aippocampus smoke recall-funnel", proc.stdout)
        self.assertIn("aippocampus agent recall", proc.stdout)
        self.assertIn("diagnostic, not source evidence", proc.stdout)
        self.assertNotIn("usage:", proc.stdout.lower())
        self.assertNotIn("the following arguments are required", proc.stdout)


if __name__ == "__main__":
    unittest.main()
