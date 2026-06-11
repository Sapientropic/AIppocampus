from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.aippo import working_contract as aippo  # noqa: E402


class AIppoWorkingContractTests(unittest.TestCase):
    def test_extracts_partial_package_with_clause_level_lifecycle(self) -> None:
        report = aippo.build_aippo_working_contract_fixture_report()
        package = report["contract_package"]
        clauses = {clause["clause_id"]: clause for clause in package["clauses"]}

        self.assertTrue(report["ok"], json.dumps(report, ensure_ascii=False, indent=2))
        self.assertEqual(package["kind"], "aippo_working_contract")
        self.assertEqual(package["package_status"], "partial")
        self.assertEqual(package["scope"]["project"], "AIppocampus")
        self.assertIn("project_aippo_activation", package["mvp_activation_targets"])

        scoped = clauses["clause_keep_changes_scoped"]
        stale = clauses["clause_benchmark_default_claim"]
        reporting = clauses["clause_preserve_useful_result_claims"]

        self.assertEqual(scoped["lifecycle"]["status"], "ripe")
        self.assertEqual(scoped["claim_permission"], "working_contract_allowed_no_fact_claim")
        self.assertIn("low_risk_orientation", scoped["allowed_without_reopen_for"])
        self.assertIn("public_claim", scoped["requires_reopen_for"])

        self.assertEqual(reporting["lifecycle"]["status"], "ripe")
        self.assertIn("benchmark_reporting", reporting["applies_when"])

        self.assertEqual(stale["lifecycle"]["status"], "stale")
        self.assertEqual(stale["activation"]["next_action"], "reopen_source")
        self.assertEqual(stale["lifecycle"]["degrade_to"], "reopenable_route")
        self.assertNotIn(stale["clause_id"], report["activation_packet"]["active_clause_ids"])

    def test_candidate_surfaces_nominate_but_do_not_ripen_without_source_support(self) -> None:
        report = aippo.build_aippo_working_contract_fixture_report()
        by_id = {case["case_id"]: case for case in report["fixture_cases"]}

        self_note = by_id["self_note_candidate_without_source"]
        dream = by_id["dream_candidate_backstage"]
        cognitive = by_id["cognitive_route_to_source_support"]

        self.assertFalse(self_note["ripened"])
        self.assertEqual(self_note["result_status"], "needs_review")
        self.assertIn("self_note_promoted_without_source", report["red_lines"])
        self.assertEqual(report["red_lines"]["self_note_promoted_without_source"], 0)

        self.assertFalse(dream["ripened"])
        self.assertEqual(dream["result_status"], "backstage_candidate")
        self.assertEqual(report["red_lines"]["dream_candidate_promoted_without_source"], 0)

        self.assertTrue(cognitive["ripened"])
        self.assertEqual(cognitive["navigation_signal_used"], "cognitive_map")
        self.assertEqual(cognitive["truth_authority"], "source_supported")
        self.assertEqual(report["red_lines"]["cognitive_route_used_as_truth"], 0)

    def test_challenged_and_gappy_pathlets_degrade_to_reopenable_routes(self) -> None:
        report = aippo.build_aippo_working_contract_fixture_report()
        clauses = {clause["clause_id"]: clause for clause in report["contract_package"]["clauses"]}

        challenged = clauses["clause_issue_closeout_convention"]
        gappy = clauses["clause_ordered_do_not_repeat_route"]

        self.assertEqual(challenged["lifecycle"]["status"], "challenged")
        self.assertGreater(challenged["support"]["counter_evidence_ref_count"], 0)
        self.assertEqual(challenged["activation"]["next_action"], "reopen_source")
        self.assertNotIn(challenged["clause_id"], report["activation_packet"]["active_clause_ids"])

        self.assertEqual(gappy["support"]["path_provenance"], "gappy")
        self.assertEqual(gappy["lifecycle"]["review_state"], "needs_review")
        self.assertEqual(gappy["lifecycle"]["degrade_to"], "reopenable_route")
        self.assertEqual(report["red_lines"]["gappy_pathlet_promoted_without_review"], 0)

    def test_foreground_activation_packet_is_compact_and_not_a_provenance_dump(self) -> None:
        report = aippo.build_aippo_working_contract_fixture_report()
        packet = report["activation_packet"]
        encoded = json.dumps(packet, ensure_ascii=False, sort_keys=True)

        self.assertEqual(packet["kind"], "aippocampus_aippo_activation_packet")
        self.assertEqual(packet["output_mode"], "working_contract")
        self.assertEqual(packet["claim_permission"], "working_contract_allowed_no_fact_claim")
        self.assertEqual(packet["next_action"], "use_hint")
        self.assertIn("benchmark_reporting", packet["task_families"])
        self.assertTrue(packet["use_guidance"])
        self.assertIn("measured results", " ".join(packet["use_guidance"]))
        self.assertLessEqual(
            report["metrics"]["foreground_packet_bytes"],
            report["foreground_packet_budget_bytes"],
        )
        self.assertEqual(packet["active_clause_count"], 2)
        self.assertEqual(report["metrics"]["available_active_clause_count"], 3)
        self.assertEqual(report["metrics"]["suppressed_clause_count"], 3)
        self.assertGreater(report["metrics"]["active_clause_information_density"], 0)
        self.assertEqual(report["metrics"]["generic_safety_posture_only_count"], 0)
        self.assertGreaterEqual(report["metrics"]["stable_workflow_search_avoided_count"], 2)
        self.assertEqual(report["metrics"]["aippo_next_action_delta_count"], 1)
        self.assertGreaterEqual(report["metrics"]["stale_clause_suppressed_count"], 2)
        self.assertGreaterEqual(
            report["metrics"]["low_risk_guidance_allowed_without_reopen_count"],
            2,
        )
        self.assertTrue(report["usefulness_gate"]["usefulness_gate_ok"])
        generic = report["negative_fixtures"]["generic_safety_posture_only"]
        self.assertFalse(generic["usefulness_gate_ok"])
        self.assertEqual(generic["generic_safety_posture_only_count"], 1)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("candidate_provenance", encoded)
        self.assertNotIn("support_ledger", encoded)
        self.assertNotIn("PRIVATE_SOURCE_SENTINEL", encoded)
        self.assertNotIn("C:\\", encoded)

    def test_task_family_selection_changes_activation_emphasis(self) -> None:
        contract = aippo.build_project_workflow_public_safe_contract()
        packets = {
            task: aippo.activation_packet_from_working_contract(contract, task=task)
            for task in ("issue writing", "benchmark reporting", "PR review", "coding patch")
        }

        self.assertIn("issue_writing", packets["issue writing"]["task_families"])
        self.assertIn("benchmark_reporting", packets["benchmark reporting"]["task_families"])
        self.assertIn("PR_review", packets["PR review"]["task_families"])
        self.assertIn("coding", packets["coding patch"]["task_families"])
        self.assertNotEqual(
            packets["benchmark reporting"]["active_clause_ids"],
            packets["coding patch"]["active_clause_ids"],
        )
        self.assertIn("cannot_claim", " ".join(packets["benchmark reporting"]["use_guidance"]))

    def test_deepen_and_stability_surfaces_preserve_audit_without_foreground_leakage(self) -> None:
        report = aippo.build_aippo_working_contract_fixture_report()
        deepen = report["deepen_surface"]

        self.assertEqual(deepen["kind"], "aippocampus_aippo_deepen_surface")
        self.assertEqual(deepen["source_support_ledger"]["source_ref_count"], 8)
        self.assertIn("agent_self_notes", deepen["candidate_provenance"]["allowed_candidate_inputs"])
        self.assertFalse(deepen["candidate_provenance"]["candidate_inputs_are_truth"])
        self.assertEqual(report["metrics"]["stable_rebuild_hash_changed_count"], 0)
        self.assertIn("clause_benchmark_default_claim", report["stability"]["changed_clause_ids"])
        self.assertEqual(report["red_lines"]["masked_or_private_source_in_activation_packet"], 0)
        self.assertEqual(report["red_lines"]["source_backed_claim_without_reopen"], 0)


if __name__ == "__main__":
    unittest.main()
