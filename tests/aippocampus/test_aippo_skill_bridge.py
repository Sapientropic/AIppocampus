from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.aippo import skill_bridge, skill_observed_use  # noqa: E402


class AIppoSkillBridgeTests(unittest.TestCase):
    def test_imports_public_skill_as_lower_authority_seed_not_ripe_aippo(self) -> None:
        skill_path = REPO_ROOT / "skills" / "aippocampus" / "SKILL.md"
        report = skill_bridge.build_skill_to_aippo_fixture_report(skill_path)
        seed = report["seed"]
        clauses = {clause["clause_kind"] for clause in seed["clauses"]}

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(seed["kind"], "candidate_aippo_seed")
        self.assertIn("candidate_aiipo_seed", seed["compat_aliases"])
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
        self.assertIn("aippocampus health", " ".join(deepen["commands"]))
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


if __name__ == "__main__":
    unittest.main()
