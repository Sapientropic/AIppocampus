from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime.contracts import (
    executable_command_violations,
    foreground_action_contract_violations,
)
from aippocampus_runtime.macro import state as macro_state
from aippocampus_runtime.recall import (
    agent_continuity,
)
from tests.aippocampus.frontstage_assertions import assert_semantic_human_output

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"

class AgentOptInAippoSemanticTests(unittest.TestCase):
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
                "text": "继续 agent-native recall opt-in path，但不要把 SECRET_TOKEN=abc123 放进前台。",
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
                "text": "Opt-in continuity should return a compact MemoryPacket, then deepen source before claims.",
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

    def assertCanonicalForegroundAction(self, payload: dict[str, object]) -> None:
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertIsInstance(payload["foreground_action"], dict)
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn("next_safe_action", payload)
        self.assertNotIn(payload["foreground_action"], payload.get("safe_next_actions", []))
        self.assertEqual(foreground_action_contract_violations(payload), [])

    def _append_clean_rows(self, rows: list[dict[str, object]]) -> None:
        with (self.clean / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _macro_state_path(
        self,
        *,
        active_layer: str = "人",
        momentum: dict[str, object] | None = None,
    ) -> Path:
        macro_path = self.cwd / f"macro-{active_layer}.jsonl"
        entry = macro_state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="乾",
            changing_lines=(1, 2, 3),
            source_refs=({"source_id": f"macro-live-{active_layer}"},),
            updated_at=macro_state.utc_now_iso(),
            active_layer=active_layer,
            momentum=momentum,
        )
        macro_state.append_macro_orientation_state(macro_path, entry)
        return macro_path

    def _append_default_macro_state(
        self,
        *,
        active_layer: str = "人",
        changing_lines: tuple[int, ...] = (1, 2, 3),
    ) -> Path:
        macro_path = self.cwd / ".aippocampus" / "macro-orientation.jsonl"
        entry = macro_state.build_macro_orientation_state(
            project="AIppocampus",
            hexagram="乾",
            changing_lines=changing_lines,
            source_refs=({"source_id": f"default-macro-{active_layer}"},),
            updated_at=macro_state.utc_now_iso(),
            active_layer=active_layer,
            momentum={"basis": {"counter_evidence_delta": 0.2}},
        )
        macro_state.append_macro_orientation_state(macro_path, entry)
        return macro_path

    def test_aippo_activation_agent_deepen_explain_and_feedback_stay_low_authority(self) -> None:
        """agent_deepen keeps source support in detail while foreground stays low-authority."""

        activation = agent_continuity.activate_aippo(task="coding issue closeout")
        encoded_activation = json.dumps(activation, ensure_ascii=False, sort_keys=True)

        self.assertEqual(activation["kind"], "aippocampus_agent_continuity_path")
        self.assertEqual(activation["mode"], "aippo")
        self.assertEqual(activation["activation_packet"]["kind"], "aippocampus_aippo_activation_packet")
        self.assertIn("coding", activation["activation_packet"]["task_families"])
        self.assertTrue(activation["activation_packet"]["use_guidance"])
        self.assertEqual(activation["metrics"]["generic_safety_posture_only_count"], 0)
        self.assertGreaterEqual(
            activation["metrics"]["low_risk_guidance_allowed_without_reopen_count"],
            1,
        )
        self.assertTrue(activation["metrics"]["usefulness_gate_ok"])
        self.assertEqual(
            activation["activation_packet"]["claim_permission"],
            "working_contract_allowed_no_fact_claim",
        )
        self.assertNotIn("source_refs", encoded_activation)
        self.assertNotIn("candidate_provenance", encoded_activation)
        self.assertEqual(activation["red_lines"]["stale_clause_activated_as_current"], 0)

        deepened = agent_continuity.deepen(
            activation["activation_packet"]["deepen_route_id"],
            cwd=self.cwd,
            clean_source_dir=self.clean,
        )
        self.assertEqual(deepened["surface"], "aippo")
        self.assertGreater(
            deepened["result"]["source_support_ledger"]["source_ref_count"],
            0,
        )
        self.assertFalse(deepened["result"]["candidate_provenance"]["candidate_inputs_are_truth"])

        explanation = agent_continuity.explain(activation["activation_packet"]["deepen_route_id"])
        self.assertEqual(explanation["surface"], "aippo")
        self.assertIn(
            "candidate_surfaces_are_navigation_not_truth",
            explanation["explanation"]["reason_codes"],
        )

        receipt = agent_continuity.capture_feedback(
            route_id=activation["activation_packet"]["aippo_id"],
            outcome="source_reopen_success",
            route_kind="active_path",
            reason="user accepted after source reopen",
        )
        self.assertEqual(receipt["mode"], "feedback")
        self.assertEqual(receipt["authority"], "low_authority_feedback_signal")
        self.assertEqual(receipt["red_lines"]["feedback_promoted_without_source"], 0)
        self.assertTrue(receipt["policy_boundary"]["source_reopen_required_for_claims"])

    def test_agent_recall_accepts_semantic_controls_as_diagnostic_sidecar(self) -> None:
        with patch(
            "aippocampus_runtime.recall.why_diagnostics.recall_diagnostic_report",
            return_value={
                "decision": "surfaced",
                "reasons": ["route_returned", "source_reopen_required"],
                "next_safe_action": "reopen_source",
                "surface_reports": [
                    {
                        "surface": "semantic_gate",
                        "status": "available",
                        "reason_codes": ["background_only"],
                        "details": {"decision": "background_only"},
                    }
                ],
            },
        ) as diagnostic:
            report = agent_continuity.recall(
                "我之前说那个字符打错导致 python 出问题的事是什么",
                cwd=self.cwd,
                clean_source_dir=self.clean,
                semantic_gate_mode="on",
                semantic_timeout=8,
            )

        diagnostic.assert_called_once()
        semantic = report["semantic_gate_diagnostics"]
        self.assertEqual(semantic["mode"], "on")
        self.assertEqual(semantic["timeout_seconds"], 8)
        self.assertNotIn("decision", semantic)
        self.assertEqual(semantic["overall_recall_diagnostic"]["decision"], "surfaced")
        self.assertEqual(
            semantic["overall_recall_diagnostic"]["reasons"],
            ["route_returned", "source_reopen_required"],
        )
        self.assertEqual(semantic["semantic_sidecar"]["status"], "available")
        self.assertEqual(semantic["semantic_sidecar"]["decision"], "background_only")
        self.assertEqual(
            semantic["semantic_sidecar"]["contribution"],
            "diagnostic_only_no_selected_route_change",
        )
        self.assertEqual(semantic["next_step_hint"], "reopen_source")

    def test_agent_recall_semantic_timeout_is_degraded_no_contribution(self) -> None:
        with patch(
            "aippocampus_runtime.recall.why_diagnostics.recall_diagnostic_report",
            return_value={
                "decision": "degraded",
                "reasons": [
                    "route_returned",
                    "source_reopen_required",
                    "semantic_provider_timeout",
                ],
                "next_safe_action": "reopen_source",
                "surface_reports": [
                    {
                        "surface": "semantic_gate",
                        "status": "available",
                        "reason_codes": ["semantic_provider_timeout", "route_returned"],
                        "details": {"decision": "evidence"},
                    }
                ],
            },
        ):
            report = agent_continuity.recall(
                "what should I remember before filing a GitHub issue for AIppocampus",
                cwd=self.cwd,
                clean_source_dir=self.clean,
                semantic_gate_mode="auto",
                run_semantic_gate=True,
                semantic_timeout=8,
            )

        sidecar = report["semantic_gate_diagnostics"]["semantic_sidecar"]
        self.assertEqual(sidecar["status"], "degraded")
        self.assertEqual(sidecar["decision"], "degraded")
        self.assertEqual(sidecar["contribution"], "none_semantic_timeout")
        self.assertIn("semantic_provider_timeout", sidecar["reason_codes"])

    def test_cli_agent_recall_auto_attention_reports_promotion_blockers(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "recall",
                "attention router score fusion route selection",
                "--cwd",
                str(self.cwd),
                "--clean-source-dir",
                str(self.clean),
                "--attention-router-mode",
                "auto",
                "--json",
                "--detail",
                "full",
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
        policy = payload["attention_router_navigation"]["policy"]
        self.assertEqual(policy["mode"], "auto")
        self.assertTrue(policy["default_adoption_allowed"])
        self.assertEqual(policy["promotion_blockers"], [])

    def test_cli_agent_aippo_task_selects_useful_clause_family(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "aippo",
                "--task",
                "benchmark reporting issue closeout",
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

        self.assertEqual(payload["mode"], "aippo")
        self.assertEqual(payload["surface"], "agent_aippo_guidance_card")
        self.assertIn("benchmark_reporting", payload["task_families"])
        self.assertIn("measured results", " ".join(payload["use_guidance"]))
        self.assertEqual(payload["foreground_action"]["action_type"], "use_project_working_guidance")
        self.assertNotIn("tool_name", payload["foreground_action"])
        self.assertNotIn("arguments", payload["foreground_action"])
        refresh_action = next(
            action
            for action in payload["safe_next_actions"]
            if action["id"] == "refresh_aippo_guidance_for_task"
        )
        self.assertEqual(refresh_action["tool_name"], "agent_aippo")
        self.assertEqual(refresh_action["arguments"], {"task": "benchmark reporting issue closeout"})
        self.assertEqual(
            refresh_action["command"],
            "aippocampus agent aippo --task 'benchmark reporting issue closeout' --json",
        )
        self.assertCanonicalForegroundAction(payload)
        self.assertNotIn("cannot_claim", payload)
        self.assertIn("source_backed_facts", payload["claim_boundary"]["must_reopen_for"])
        self.assertNotIn("operator_detail", payload)
        self.assertNotIn("operator_json_command_template", payload)
        self.assertEqual(
            payload["operator_json_command"],
            (
                "aippocampus agent aippo --task "
                "'benchmark reporting issue closeout' --json --operator-json"
            ),
        )
        self.assertEqual(
            payload["claim_boundary"]["detail_available_with_command"],
            payload["operator_json_command"],
        )
        self.assertNotIn("operator_json_requires", payload)
        self.assertNotIn("activation_packet", payload)
        self.assertNotIn("metrics", payload)
        self.assertNotIn("red_lines", payload)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("candidate_provenance", encoded)
        self.assertNotIn("<task_cue>", encoded)
        self.assertEqual(executable_command_violations(payload), [])

    def test_cli_agent_aippo_use_hint_reports_available_clause(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "aippo",
                "--json",
                "--operator-json",
                "fix failing pytest after forgetting ruff",
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
        card = payload["foreground_guidance_card"]
        packet = payload["activation_packet"]

        self.assertEqual(card["foreground_action"]["id"], "use_hint")
        self.assertEqual(card["foreground_action"]["action_type"], "use_project_working_guidance")
        self.assertNotIn("arguments", card["foreground_action"])
        self.assertNotIn("cannot_claim", card)
        self.assertIn("source_backed_facts", card["claim_boundary"]["must_reopen_for"])
        self.assertGreaterEqual(packet["available_active_clause_count"], 1)
        self.assertEqual(packet["available_active_clause_count"], packet["active_clause_count"])
        self.assertGreaterEqual(packet["contract_active_clause_count"], packet["active_clause_count"])
        self.assertIn("active_not_foreground_available_count", packet)

    def test_cli_agent_aippo_no_match_recovers_instead_of_use_hint(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "aippo",
                "--json",
                "casual chat about weather",
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

        self.assertEqual(payload["status"], "no_active_contract")
        self.assertNotIn("operator_detail", payload)
        self.assertNotEqual(payload["foreground_action"]["id"], "use_hint")
        self.assertEqual(payload["foreground_action"]["tool_name"], "agent_recall")
        self.assertIn("no_task_family_match", payload["reason_codes"])
        self.assertEqual(len(payload["reason_codes"]), len(set(payload["reason_codes"])))
        self.assertNotIn(
            "deepen_aippo_working_contract",
            {action.get("id") for action in payload["safe_next_actions"]},
        )

    def test_cli_agent_aippo_no_task_returns_needs_input_action_card(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "aippo",
                "--json",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 2, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        action = payload["foreground_action"]

        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["error"]["code"], "aippo_task_required")
        self.assertCanonicalForegroundAction(payload)
        self.assertEqual(action["id"], "provide_task_cue")
        self.assertEqual(action["tool_name"], "agent_aippo")
        self.assertEqual(action["requires"], ["task_cue"])
        self.assertEqual(action["blocked_by"], ["task_cue_required"])
        self.assertNotIn("operator_detail", payload)
        self.assertNotIn("operator_json_command", payload)
        self.assertIn("operator_json_command_template", payload)
        self.assertEqual(payload["operator_json_requires"], ["task_cue"])
        self.assertNotIn("<task_cue>", encoded)
        self.assertEqual(executable_command_violations(payload), [])

    def test_cli_agent_aippo_operator_json_aligns_no_task_foreground_action(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "aippo",
                "--json",
                "--operator-json",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 2, proc.stderr)
        payload = json.loads(proc.stdout)
        packet = payload["activation_packet"]

        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["error"]["code"], "aippo_task_required")
        self.assertEqual(payload["foreground_action"]["id"], "provide_task_cue")
        self.assertEqual(packet["next_action"], "provide_task_cue")
        self.assertEqual(packet["contract_next_action"], "stay_silent")
        self.assertEqual(packet["blocked_by"], ["task_cue_required"])

    def test_cli_agent_aippo_operator_json_exposes_foreground_contract(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "aippo",
                "--task",
                "critique foreground JSON agent-unfriendly placeholder cue",
                "--json",
                "--operator-json",
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

        self.assertEqual(payload["surface"], "project_workflow_ai_ppocampus")
        self.assertIn("activation_packet", payload)
        self.assertCanonicalForegroundAction(payload)
        self.assertIn("product_workflow", payload["activation_packet"]["task_families"])
        self.assertIn("foreground_guidance_card", payload)
        self.assertIn("operator_json_command", payload["foreground_guidance_card"])
        self.assertNotIn(
            "operator_json_command_template",
            payload["foreground_guidance_card"],
        )
        self.assertNotIn("<task_cue>", encoded)
        self.assertEqual(executable_command_violations(payload), [])

    def test_cli_agent_aippo_core_product_journeys_are_not_empty_contracts(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "aippo",
                "--json",
                "install plugin and verify MCP host readiness",
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
        self.assertEqual(payload["status"], "ok")
        self.assertIn("host_readiness", payload["task_families"])
        self.assertEqual(payload["foreground_action"]["id"], "verify_plugin_mcp_hooks")

    def test_cli_agent_aippo_product_workflow_terms_are_not_empty_contracts(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "aippo",
                "--public",
                "--json",
                "semantic gate, attention router, MCP health",
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
        guidance = " ".join(payload["use_guidance"])
        self.assertEqual(payload["status"], "ok")
        self.assertIn("product_workflow", payload["task_families"])
        self.assertNotEqual(payload["foreground_action"]["id"], "stay_silent")
        self.assertIn("semantic gate", guidance)

    def test_cli_agent_aippo_default_output_is_human_guidance(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "aippocampus_runtime.cli.facade",
                "agent",
                "aippo",
                "--task",
                "benchmark reporting issue closeout",
            ],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("AIppo:", proc.stdout)
        assert_semantic_human_output(
            self,
            proc.stdout,
            max_lines=8,
            forbidden_boilerplate=(),
        )
        self.assertNotIn("activation_packet", proc.stdout)
        self.assertNotIn("policy_boundary", proc.stdout)

if __name__ == "__main__":
    unittest.main()
