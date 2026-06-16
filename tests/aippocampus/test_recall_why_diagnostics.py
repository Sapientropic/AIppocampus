from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.cli import facade  # noqa: E402
from aippocampus_runtime.mcp import server as mcp  # noqa: E402
from aippocampus_runtime.recall import why_diagnostics as why  # noqa: E402
from aippocampus_runtime.recall import why_reason_codes as reason_codes  # noqa: E402
from aippocampus_runtime.recall import why_surfaces as surfaces  # noqa: E402


class RecallWhyDiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.clean = self.cwd / ".aippocampus" / "clean-source"
        self.clean.mkdir(parents=True)
        self._write_clean_source(
            [
                {
                    "message_id": "msg-final",
                    "turn_id": "turn-1",
                    "source_id": "src-test",
                    "source_line": 4,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 1,
                    "is_final": True,
                    "text": "Clean source continuity routes require reopen before claims.",
                }
            ]
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_clean_source(self, messages: list[dict]) -> None:
        with (self.clean / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
            for row in messages:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        turn_rows = [
            {
                "turn_id": row.get("turn_id"),
                "turn_index": row.get("turn_index"),
                "message_ids": [row.get("message_id")],
                "assistant_phase": row.get("phase"),
            }
            for row in messages
        ]
        with (self.clean / "turns.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
            for row in turn_rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def test_successful_route_is_hash_only_and_requires_source_reopen(self) -> None:
        cue = "SECRET_TOKEN=abc123 clean source continuity"

        payload = why.recall_diagnostic_report(
            cue=cue,
            mode="why-recall",
            cwd=self.cwd,
            clean_source_dir=self.clean,
        )

        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["kind"], "aippocampus_recall_diagnostic")
        self.assertEqual(payload["decision"], "surfaced")
        self.assertIn("route_returned", payload["reasons"])
        self.assertIn("source_reopen_required", payload["reasons"])
        self.assertEqual(payload["next_safe_action"], "reopen_source")
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn("clean source continuity", encoded)
        self.assertNotIn(str(self.cwd), encoded)
        self.assertNotIn("Clean source continuity routes", encoded)
        self.assertTrue(payload["privacy_boundary"]["diagnostic_is_not_truth_source"])
        self.assertIn("diagnostic_reason_is_not_memory_evidence", payload["cannot_claim"])

    def test_common_reason_code_mappings_cover_issue_acceptance_cases(self) -> None:
        payload = why.recall_diagnostic_report(
            cue="private recall cue",
            mode="why-not-recall",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            recall_context_payload={"status": "no_routes", "routes": [], "query_terms": ["private"]},
            active_lock_payload={
                "state": "expired",
                "lock_id": "arl_test",
                "candidate_ref_count": 0,
                "reopenable_ref_count": 0,
                "source_reopen_required": True,
                "diagnostics": {"invalidated_by": ["ttl_expired"]},
            },
            ambient_cache_payload={
                "status": "hit",
                "cards": [
                    {
                        "support_level": "candidate",
                        "source_thickness": "thin",
                        "source_reopen_required": True,
                        "source_refs": [],
                    }
                ],
                "suppression_diagnostics": {
                    "reason_buckets": [
                        "secret_or_property_risk_blocked",
                        "external_payload_blocked",
                        "local_route_handle_only",
                        "current_thread_echo",
                        "source_validation_failed",
                    ]
                },
            },
            semantic_gate_payload={
                "available": False,
                "decision": "skip",
                "availability_reason": "semantic_worker_timeout",
                "diagnostic": "semantic_provider_read_timeout",
                "error_buckets": {"read_timeout": 1},
                "worker_count": 1,
            },
        )

        reasons = set(payload["reasons"])
        self.assertGreaterEqual(
            reasons,
            {
                "no_source_refs",
                "stale_handle",
                "secret_or_property_risk_blocked",
                "external_payload_blocked",
                "local_route_handle_only",
                "anti_nag_source_already_visible",
                "semantic_provider_timeout",
                "source_thickness_thin",
                "source_reopen_required",
                "source_ref_not_found",
            },
        )
        self.assertEqual(payload["decision"], "suppressed")
        self.assertEqual(payload["reason_code_catalog_version"], 1)

    def test_ambient_cache_surface_distinguishes_bounded_evidence_ready(self) -> None:
        report = surfaces.ambient_cache_surface_report(
            {
                "status": "hit",
                "cards": [
                    {
                        "support_level": "evidence",
                        "authority_state": "bounded_evidence_ready",
                        "source_reopen_required": False,
                        "reopen_required_before_claim": False,
                        "reopen_recommended_for_exact_quote": True,
                        "source_refs": [{"thread_key": "session:old", "line": 4}],
                    }
                ],
            }
        )

        self.assertIn("bounded_evidence_ready", report["reason_codes"])
        self.assertIn("reopen_recommended_for_exact_quote", report["reason_codes"])
        self.assertNotIn("source_reopen_required", report["reason_codes"])
        self.assertTrue(report["details"]["bounded_evidence_ready"])
        self.assertFalse(report["details"]["source_reopen_required"])
        self.assertEqual(
            reason_codes.next_safe_action(report["reason_codes"]),
            "use_bounded_evidence_when_relevant",
        )

    def test_cli_facade_exposes_why_not_recall_json_without_raw_cue(self) -> None:
        result = facade.run_command(
            [
                "why-not-recall",
                "SECRET_TOKEN=abc123 clean source continuity",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
                "--json",
            ],
            capture_output=True,
        )

        self.assertTrue(result.ok, result.stderr)
        payload = json.loads(result.stdout)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["mode"], "why-not-recall")
        self.assertEqual(payload["kind"], "aippocampus_recall_diagnostic")
        self.assertIn("recall_context", payload["searched_surfaces"])
        action_ids = [item["id"] for item in payload["safe_next_actions"]]
        self.assertEqual(action_ids.count("recall_same_cue"), 1)
        self.assertEqual(payload["next_safe_action"], payload["agent_next_action"]["id"])
        self.assertEqual(payload["authority_next_safe_action"], "reopen_source")
        deepen_action = next(item for item in payload["safe_next_actions"] if item["id"] == "deepen_after_recall")
        self.assertEqual(deepen_action["depends_on"], "recall_same_cue")
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn(str(self.cwd), encoded)

    def test_cli_help_and_human_output_are_frontstage_cards(self) -> None:
        help_result = facade.run_command(["why-recall", "--help"], capture_output=True)
        human = facade.run_command(
            [
                "why-recall",
                "clean source continuity",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
            ],
            capture_output=True,
        )

        self.assertTrue(help_result.ok, help_result.stderr)
        self.assertIn("usage: aippocampus why-recall", help_result.stdout)
        self.assertNotIn("{why-recall,why-not-recall}", help_result.stdout)
        self.assertTrue(human.ok, human.stderr)
        self.assertIn("AIppocampus why-recall", human.stdout)
        self.assertIn("what happened:", human.stdout)
        self.assertIn("next:", human.stdout)
        self.assertIn("boundary:", human.stdout)
        self.assertNotIn("cue_hash", human.stdout)
        self.assertNotIn("route_ids", human.stdout)
        self.assertNotIn('"<cue>"', human.stdout)
        self.assertIn('aippocampus agent recall "clean source continuity" --json', human.stdout)

    def test_human_missing_source_card_uses_the_provided_cue(self) -> None:
        human = facade.run_command(
            [
                "why-recall",
                "old correction",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.cwd / "missing-clean-source"),
            ],
            capture_output=True,
        )

        self.assertTrue(human.ok, human.stderr)
        self.assertIn("aippocampus onboard --provider auto --status --json", human.stdout)
        self.assertNotIn('"<distinctive exact phrase>"', human.stdout)
        self.assertNotIn('"<cue>"', human.stdout)

    def test_json_why_recall_actions_use_real_cue_and_align_primary_command(self) -> None:
        result = facade.run_command(
            [
                "why-recall",
                "old correction",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.cwd / "missing-clean-source"),
                "--json",
            ],
            capture_output=True,
        )

        self.assertTrue(result.ok, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["agent_next_action"]["id"], "check_onboarding_status")
        self.assertEqual(
            payload["action_card"]["next_command"],
            payload["agent_next_action"]["command"],
        )
        encoded = json.dumps(payload, ensure_ascii=False)
        commands = [item["command"] for item in payload["safe_next_actions"]]
        self.assertEqual(payload["next_safe_action"], "check_onboarding_status")
        self.assertIn('aippocampus agent recall "old correction" --json', commands)
        self.assertNotIn('"<cue>"', encoded)
        self.assertNotIn('"<distinctive exact phrase>"', encoded)

    def test_bare_why_commands_return_recovery_cards(self) -> None:
        for command in ("why-recall", "why-not-recall"):
            with self.subTest(command=command):
                result = facade.run_command([command], capture_output=True)

                self.assertFalse(result.ok)
                self.assertEqual(result.exit_code, 2)
                self.assertNotIn("usage:", result.stdout + result.stderr)
                self.assertIn("AIppocampus " + command, result.stdout)
                self.assertIn("example cue:", result.stdout)
                self.assertIn("aippocampus agent recall", result.stdout)
                self.assertIn("source evidence", result.stdout)

    def test_cli_help_leads_with_use_case_before_diagnostic_flags(self) -> None:
        why_help = facade.run_command(["why-recall", "--help"], capture_output=True)
        why_not_help = facade.run_command(["why-not-recall", "--help"], capture_output=True)
        advanced = facade.run_command(["why-recall", "--help-advanced"], capture_output=True)

        self.assertTrue(why_help.ok, why_help.stderr)
        self.assertTrue(why_not_help.ok, why_not_help.stderr)
        self.assertIn("What this command is for", why_help.stdout)
        self.assertIn("What this command is for", why_not_help.stdout)
        self.assertIn("deepen selected route", why_help.stdout)
        self.assertIn("refine cue", why_not_help.stdout)
        self.assertIn('aippocampus why-recall "old decision about setup"', why_help.stdout)
        self.assertIn('aippocampus agent deepen --request 1 --last-recall --json', why_help.stdout)
        self.assertIn("source evidence", why_help.stdout)
        self.assertNotIn("--semantic-result-json", why_help.stdout)
        self.assertNotIn("--lock-path", why_help.stdout)
        self.assertNotIn("--registry-dir", why_help.stdout)
        self.assertNotIn("--semantic-result-json", why_not_help.stdout)
        self.assertTrue(advanced.ok, advanced.stderr)
        self.assertIn("--semantic-result-json", advanced.stdout)
        self.assertIn("--lock-path", advanced.stdout)
        self.assertIn("--registry-dir", advanced.stdout)

    def test_why_not_recall_distinguishes_low_specificity_surface_from_silence(self) -> None:
        payload = why.recall_diagnostic_report(
            cue="vague context",
            mode="why-not-recall",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            recall_context_payload={
                "status": "ok",
                "query_terms": ["vague"],
                "routes": [
                    {
                        "route_id": f"route-{index}",
                        "source_refs": [{"source_id": f"src-{index}"}],
                        "source_reopen_required": True,
                    }
                    for index in range(5)
                ],
            },
        )

        self.assertEqual(payload["decision"], "surfaced")
        self.assertEqual(payload["diagnostic_class"], "surfaced_but_low_specificity")
        self.assertFalse(payload["why_not_applicable"])
        self.assertEqual(payload["route_specificity"], "low")
        self.assertIn("tighten_cue", payload["suggested_next"])

    def test_why_not_low_specificity_json_has_one_primary_action_card(self) -> None:
        payload = why.recall_diagnostic_report(
            cue="vague context",
            mode="why-not-recall",
            cwd=self.cwd,
            clean_source_dir=self.clean,
            recall_context_payload={
                "status": "ok",
                "query_terms": ["vague"],
                "routes": [
                    {
                        "route_id": f"route-{index}",
                        "source_refs": [{"source_id": f"src-{index}"}],
                        "source_reopen_required": True,
                    }
                    for index in range(5)
                ],
            },
        )

        card = payload["action_card"]
        self.assertEqual(card["primary_action"], "refine_cue_first")
        self.assertIn("tighten", card["next_command"])
        self.assertIn("deepen only if continuity matters", card["do_not"])
        self.assertNotIn("route_ids", card)
        self.assertEqual(payload["foreground_next_action"], card["primary_action"])

    def test_mcp_recall_diagnostic_returns_public_safe_payload(self) -> None:
        response = mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 678,
                "method": "tools/call",
                "params": {
                    "name": "recall_diagnostic",
                    "arguments": {
                        "cue": "SECRET_TOKEN=abc123 clean source continuity",
                        "mode": "why-recall",
                        "cwd": str(self.cwd),
                        "clean_source_dir": str(self.clean),
                    },
                },
            }
        )

        payload = json.loads(response["result"]["content"][0]["text"])
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(response["result"].get("isError", False))
        self.assertEqual(payload["kind"], "aippocampus_recall_diagnostic")
        self.assertIn("source_reopen_required", payload["reasons"])
        self.assertNotIn("SECRET_TOKEN", encoded)
        self.assertNotIn(str(self.cwd), encoded)


if __name__ == "__main__":
    unittest.main()
