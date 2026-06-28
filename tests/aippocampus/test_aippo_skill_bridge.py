from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

from aippocampus_runtime.aippo import skill_bridge, skill_observed_use
from aippocampus_runtime.recall import (
    agent_continuity,
)
from aippocampus_runtime.recall.feedback import events as feedback_events


class AIppoSkillBridgeTests(unittest.TestCase):
    def test_imports_public_skill_as_lower_authority_seed_not_ripe_aippo(self) -> None:
        skill_path = REPO_ROOT / "skills" / "aippocampus" / "SKILL.md"
        report = skill_bridge.build_skill_to_aippo_fixture_report(skill_path)
        seed = report["seed"]
        clauses = {clause["clause_kind"] for clause in seed["clauses"]}

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(seed["kind"], "candidate_aippo_seed")
        self.assertNotIn("compat_aliases", seed)
        self.assertEqual(seed["source_kind"], "skill_file")
        self.assertEqual(seed["skill_id"], "aippocampus")
        self.assertEqual(seed["source_ref"], "skills/aippocampus/SKILL.md")
        self.assertEqual(seed["support_status"], "declared_not_observed")
        self.assertFalse(seed["declared_instruction_is_observed_usefulness"])
        self.assertTrue(seed["requires_observation_for_ripening"])
        self.assertIn("trigger", clauses)
        self.assertIn("workflow", clauses)
        self.assertIn("command", clauses)
        self.assertIn("boundary", clauses)
        self.assertIn("output_expectation", clauses)

        for clause in seed["clauses"]:
            self.assertEqual(clause["authority"], "skill_declared_instruction")
            self.assertNotEqual(clause["support_status"], "source_supported_usefulness")
            self.assertTrue(clause["requires_observation_for_ripening"])

    def test_foreground_packet_is_compact_seed_guidance_not_raw_skill_dump(self) -> None:
        report = skill_bridge.build_skill_to_aippo_fixture_report(
            REPO_ROOT / "skills" / "aippocampus" / "SKILL.md"
        )
        packet = report["activation_packet"]
        deepen = report["deepen_surface"]
        encoded_packet = json.dumps(packet, ensure_ascii=False, sort_keys=True)

        self.assertEqual(packet["output_mode"], "working_contract_seed")
        self.assertEqual(
            packet["claim_permission"],
            "declared_skill_guidance_not_observed_usefulness",
        )
        self.assertEqual(packet["next_action"], "try_seed_when_relevant")
        self.assertLessEqual(report["metrics"]["skill_seed_activation_packet_bytes"], 700)
        self.assertGreater(report["metrics"]["raw_skill_bytes"], report["metrics"]["skill_seed_activation_packet_bytes"])
        self.assertLess(report["metrics"]["foreground_compression_ratio"], 0.35)
        self.assertNotIn("Useful portable commands", encoded_packet)
        self.assertNotIn("source_refs", encoded_packet)
        self.assertNotIn("C:\\", encoded_packet)
        self.assertGreaterEqual(len(deepen["commands"]), 3)
        self.assertIn("aippocampus plugin install --codex --verify", deepen["commands"])
        self.assertIn("python tools/aippocampus/docs/check_docs_health.py", deepen["commands"])
        self.assertGreaterEqual(len(deepen["references"]), 2)

    def test_overbroad_skill_instruction_is_suppressed_before_activation(self) -> None:
        report = skill_bridge.build_skill_to_aippo_report(
            skill_bridge.overbroad_skill_fixture(),
            skill_id="overbroad-demo",
            source_ref="fixtures/overbroad/SKILL.md",
            declared_need_class="all_tasks",
        )
        suppressed = {
            clause["clause_id"]: clause
            for clause in report["seed"]["clauses"]
            if clause["activation"]["foreground_eligible"] is False
        }

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertIn("skill_overbroad_demo_trigger_001", suppressed)
        self.assertIn("skill_overbroad_demo_boundary_001", suppressed)
        self.assertGreaterEqual(report["metrics"]["skill_clause_suppressed_count"], 2)
        self.assertEqual(report["red_lines"]["skill_instruction_treated_as_observed_usefulness_count"], 0)
        self.assertEqual(report["red_lines"]["raw_skill_text_dumped_to_foreground_count"], 0)
        self.assertEqual(report["red_lines"]["skill_seed_promoted_to_ripe_without_source_or_feedback_count"], 0)

    def test_seed_feedback_and_eval_candidacy_stay_cost_bounded(self) -> None:
        report = skill_bridge.build_skill_to_aippo_fixture_report(
            REPO_ROOT / "skills" / "aippocampus" / "SKILL.md"
        )
        feedback = report["feedback_seed_rows"]
        eval_candidacy = report["eval_candidacy"]

        self.assertGreaterEqual(len(feedback), 3)
        self.assertIn("used", {row["agent_action"] for row in feedback})
        self.assertIn("manual_search_after_packet", {row["agent_action"] for row in feedback})
        self.assertTrue(all(row["packet_mode"] == "working_contract_seed" for row in feedback))
        self.assertEqual(eval_candidacy["seed_default"]["eval_environment_required"], False)
        self.assertEqual(eval_candidacy["seed_default"]["cost_tier"], "no_eval_required")
        self.assertEqual(
            eval_candidacy["after_observed_usefulness_or_risk"]["eval_environment_required"],
            "recommended",
        )
        self.assertTrue(eval_candidacy["expensive_multi_arm_runs_require_operator_opt_in"])

    def test_observed_use_promotes_selected_skill_clauses_into_ripe_aippo(self) -> None:
        report = skill_observed_use.build_skill_observed_use_fixture_report(
            REPO_ROOT / "skills" / "aippocampus" / "SKILL.md",
            target_task="coding issue closeout with continuity-sensitive context",
        )
        seed = report["seed"]
        contract = report["ripened_contract"]
        packet = report["activation_packet"]
        deepen = report["deepen_surface"]
        encoded_packet = json.dumps(packet, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(seed["kind"], "candidate_aippo_seed")
        self.assertEqual(contract["kind"], "aippo_working_contract")
        self.assertEqual(contract["package_status"], "partial")
        self.assertEqual(packet["output_mode"], "working_contract")
        self.assertEqual(packet["claim_permission"], "working_contract_allowed_no_fact_claim")
        self.assertEqual(packet["next_action"], "use_hint")
        self.assertIn("follow it before broad manual search", " ".join(packet["use_guidance"]))
        self.assertLessEqual(report["metrics"]["activation_packet_bytes"], 700)
        self.assertGreater(report["metrics"]["source_backed_clause_count"], 0)
        self.assertGreater(report["metrics"]["skill_clause_ripened_count"], 0)
        self.assertGreater(report["metrics"]["next_action_clarity_count"], 0)
        self.assertGreater(report["metrics"]["unnecessary_deepen_suppression_count"], 0)
        self.assertGreater(report["metrics"]["candidate_only_clause_count"], 0)
        self.assertEqual(report["metrics"]["trace_backed_observed_use_count"], 0)
        self.assertGreater(report["metrics"]["synthetic_observed_use_count"], 0)
        self.assertTrue(report["metrics"]["contract_smoke_gate_ok"])
        self.assertFalse(report["metrics"]["synthetic_rows_count_as_product_usefulness"])
        self.assertFalse(report["metrics"]["usefulness_gate_ok"])
        self.assertIn(
            "product_quality_ripening_from_synthetic_observed_use_rows",
            report["cannot_claim"],
        )
        self.assertNotIn("source_refs", encoded_packet)
        self.assertNotIn("source_support_ledger", encoded_packet)
        self.assertNotIn("aippocampus health", encoded_packet)
        self.assertNotIn("C:\\", encoded_packet)
        self.assertGreater(
            deepen["source_support_ledger"]["source_ref_count"],
            packet["active_clause_count"],
        )
        self.assertEqual(report["red_lines"]["skill_instruction_promoted_without_observed_use_count"], 0)
        self.assertEqual(report["red_lines"]["self_report_promoted_to_source_supported_count"], 0)
        self.assertEqual(report["red_lines"]["source_trail_foreground_leak_count"], 0)

    def test_unobserved_or_self_report_skill_clauses_remain_candidate_only(self) -> None:
        report = skill_observed_use.build_skill_observed_use_fixture_report(
            REPO_ROOT / "skills" / "aippocampus" / "SKILL.md"
        )
        contract = report["ripened_contract"]
        active_ids = set(report["activation_packet"]["active_clause_ids"])
        command_clauses = [
            clause
            for clause in contract["clauses"]
            if clause["kind"] == "command"
        ]
        self_report_only_ids = {
            row["clause_id"]
            for row in report["observed_use_rows"]
            if row["source_support"].get("self_report_only")
        }

        self.assertGreater(len(command_clauses), 0)
        self.assertTrue(self_report_only_ids)
        self.assertTrue(active_ids.isdisjoint(self_report_only_ids))
        self.assertTrue(
            all(
                clause["support"]["support_grade"] == "candidate_only"
                for clause in command_clauses
                if clause["clause_id"] in self_report_only_ids
            )
        )
        self.assertEqual(report["red_lines"]["overbroad_declared_clause_ripened_count"], 0)
        self.assertEqual(report["metrics"]["skill_clause_ripening_candidate_count"], 2)
        self.assertGreater(report["metrics"]["candidate_only_clause_count"], 0)

    def test_trace_backed_foreground_feedback_can_feed_skill_observed_use(self) -> None:
        skill_path = REPO_ROOT / "skills" / "aippocampus" / "SKILL.md"
        markdown = skill_path.read_text(encoding="utf-8")
        seed = skill_bridge.build_skill_to_aippo_report(
            markdown,
            source_ref="skills/aippocampus/SKILL.md",
        )["seed"]
        positive_clause = "skill_aippocampus_workflow_003"
        control_clause = "skill_aippocampus_workflow_001"
        positive = feedback_events.active_flow_event(
            route_id=f"skill_clause:{positive_clause}",
            route_kind="active_path",
            signal="source_reopen_success",
            source_id="public-fixture:skill-observed-use-positive",
        )
        positive.update(
            {
                "skill_id": seed["skill_id"],
                "clause_id": positive_clause,
                "evidence_origin": "trace_backed",
            }
        )
        control = feedback_events.active_flow_event(
            route_id=f"skill_clause:{control_clause}",
            route_kind="active_path",
            signal="wrong_route_drag",
            source_id="public-fixture:skill-observed-use-control",
        )
        control.update(
            {
                "skill_id": seed["skill_id"],
                "clause_id": control_clause,
                "evidence_origin": "trace_backed",
            }
        )

        rows = skill_observed_use.observed_use_rows_from_foreground_feedback(
            seed,
            [positive, control],
        )
        report = skill_observed_use.build_skill_observed_use_report(
            markdown,
            source_ref="skills/aippocampus/SKILL.md",
            foreground_feedback_rows=[positive, control],
            target_task="coding issue closeout with continuity-sensitive context",
        )
        contract_clauses = {
            clause["clause_id"]: clause
            for clause in report["ripened_contract"]["clauses"]
        }

        self.assertEqual(len(rows), 2)
        self.assertEqual(report["status"], "trace_backed_usefulness_candidate")
        self.assertEqual(report["observed_use_ingestion"]["source"], "foreground_feedback")
        self.assertEqual(report["metrics"]["trace_backed_observed_use_count"], 2)
        self.assertEqual(report["metrics"]["trace_backed_positive_observed_use_count"], 1)
        self.assertEqual(report["metrics"]["trace_backed_no_help_observed_use_count"], 1)
        self.assertEqual(report["metrics"]["synthetic_observed_use_count"], 0)
        self.assertTrue(report["metrics"]["usefulness_gate_ok"])
        self.assertNotIn(
            "product_quality_ripening_from_synthetic_observed_use_rows",
            report["cannot_claim"],
        )
        self.assertEqual(
            contract_clauses[positive_clause]["support"]["support_grade"],
            "source_supported",
        )
        self.assertNotEqual(
            contract_clauses[control_clause]["support"]["support_grade"],
            "source_supported",
        )
        self.assertEqual(
            report["red_lines"]["skill_instruction_promoted_without_observed_use_count"],
            0,
        )

    def test_trace_backed_observed_use_can_load_from_jsonl_replay(self) -> None:
        skill_path = REPO_ROOT / "skills" / "aippocampus" / "SKILL.md"
        markdown = skill_path.read_text(encoding="utf-8")
        positive_clause = "skill_aippocampus_workflow_003"
        positive = feedback_events.active_flow_event(
            route_id=f"skill_clause:{positive_clause}",
            route_kind="active_path",
            signal="source_reopen_success",
            source_id="public-fixture:skill-observed-use-jsonl",
        )
        positive.update(
            {
                "skill_id": "aippocampus",
                "clause_id": positive_clause,
                "evidence_origin": "replay_backed",
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            replay_path = Path(tmp) / "foreground-feedback.jsonl"
            replay_path.write_text(
                json.dumps(positive, ensure_ascii=False) + "\nnot-json\n",
                encoding="utf-8",
            )
            report = skill_observed_use.build_skill_observed_use_report(
                markdown,
                source_ref="skills/aippocampus/SKILL.md",
                foreground_feedback_path=replay_path,
                target_task="coding issue closeout with continuity-sensitive context",
            )

        self.assertEqual(report["observed_use_ingestion"]["source"], "foreground_feedback")
        self.assertEqual(report["observed_use_ingestion"]["foreground_feedback_row_count"], 1)
        self.assertEqual(report["observed_use_ingestion"]["invalid_feedback_line_count"], 1)
        self.assertEqual(report["metrics"]["trace_backed_observed_use_count"], 1)
        self.assertEqual(report["metrics"]["synthetic_observed_use_count"], 0)

    def test_low_authority_feedback_does_not_ripen_skill_observed_use(self) -> None:
        skill_path = REPO_ROOT / "skills" / "aippocampus" / "SKILL.md"
        markdown = skill_path.read_text(encoding="utf-8")
        clause_id = "skill_aippocampus_workflow_003"
        receipt = agent_continuity.capture_feedback(
            route_id=f"skill_clause:{clause_id}",
            outcome="helped",
        )
        event = dict(receipt["event"])
        event.update({"skill_id": "aippocampus", "clause_id": clause_id})

        rows = skill_observed_use.observed_use_rows_from_foreground_feedback(
            skill_bridge.build_skill_to_aippo_report(
                markdown,
                source_ref="skills/aippocampus/SKILL.md",
            )["seed"],
            [event],
        )
        report = skill_observed_use.build_skill_observed_use_report(
            markdown,
            source_ref="skills/aippocampus/SKILL.md",
            foreground_feedback_rows=[event],
            target_task="coding issue closeout with continuity-sensitive context",
        )

        self.assertEqual(rows, [])
        self.assertEqual(report["status"], "contract_smoke_only")
        self.assertEqual(report["metrics"]["trace_backed_observed_use_count"], 0)
        self.assertFalse(report["metrics"]["usefulness_gate_ok"])

    def test_self_report_only_trace_row_does_not_ripen_skill_observed_use(self) -> None:
        skill_path = REPO_ROOT / "skills" / "aippocampus" / "SKILL.md"
        markdown = skill_path.read_text(encoding="utf-8")
        clause_id = "skill_aippocampus_workflow_003"
        event = feedback_events.active_flow_event(
            route_id=f"skill_clause:{clause_id}",
            route_kind="active_path",
            signal="source_reopen_success",
            source_id="public-fixture:self-report-only",
        )
        event.update(
            {
                "skill_id": "aippocampus",
                "clause_id": clause_id,
                "evidence_origin": "trace_backed",
                "source_support": {
                    "feedback_is_source_backed": True,
                    "self_report_only": True,
                    "source_ref_count": 1,
                    "source_ref": "public-fixture:self-report-only",
                },
            }
        )

        report = skill_observed_use.build_skill_observed_use_report(
            markdown,
            source_ref="skills/aippocampus/SKILL.md",
            foreground_feedback_rows=[event],
            target_task="coding issue closeout with continuity-sensitive context",
        )

        self.assertEqual(report["metrics"]["trace_backed_observed_use_count"], 0)
        self.assertFalse(report["metrics"]["usefulness_gate_ok"])

if __name__ == "__main__":
    unittest.main()
