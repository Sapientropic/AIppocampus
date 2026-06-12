from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.dream import topology_scout  # noqa: E402


class DreamTopologyScoutTests(unittest.TestCase):
    def test_fixture_emits_source_backed_candidates_without_foreground_leaks(self) -> None:
        report = topology_scout.build_dream_topology_scout_report()
        candidates = {item["case_id"]: item for item in report["candidates"]}
        controls = {item["case_id"]: item for item in report["controls"]}

        self.assertEqual(report["kind"], "aippocampus_dream_topology_scout_report")
        self.assertTrue(report["contract_gate_ok"], json.dumps(report, indent=2))
        self.assertTrue(report["safety_gate_ok"], json.dumps(report, indent=2))
        self.assertEqual(report["authority_level"], "dream_synthesized_candidate_not_fact")
        self.assertEqual(report["runtime_boundary"], "detached_background_or_explain_only")
        self.assertFalse(report["every_turn_scan"])
        self.assertFalse(report["foreground_default"])
        self.assertFalse(report["truth_layer"])
        self.assertTrue(report["contract"]["uses_packet_topology_diagnostic"])
        self.assertTrue(report["contract"]["failed_glue_can_be_candidate_not_assignment"])
        self.assertEqual(report["metrics"]["dream_topology_candidate_count"], 5)
        self.assertEqual(report["metrics"]["dream_topology_source_anchor_coverage"], 1.0)
        self.assertEqual(report["metrics"]["dream_topology_foreground_leak_count"], 0)
        self.assertEqual(report["metrics"]["dream_topology_private_interpretation_count"], 0)
        self.assertEqual(report["metrics"]["dream_topology_shape_false_positive_count"], 0)
        self.assertEqual(report["metrics"]["shadow_route_candidate_count"], 2)
        self.assertEqual(report["metrics"]["shadow_route_generic_vocab_false_positive_count"], 0)
        self.assertEqual(report["metrics"]["transform_orbit_deepen_candidate_count"], 1)

        self.assertEqual(candidates["stale_route_cycle"]["shape"], "cycle")
        self.assertEqual(candidates["stale_route_cycle"]["dream_function"], "compensatory")
        self.assertEqual(candidates["missing_middle_cut_point"]["shape"], "cut_point")
        self.assertEqual(candidates["weak_bridge_between_issues"]["shape"], "weak_bridge")
        self.assertEqual(candidates["weak_bridge_between_issues"]["dream_function"], "amplification")
        self.assertEqual(candidates["obligation_knot_needs_unlinking"]["shape"], "knot")
        self.assertEqual(
            candidates["obligation_knot_needs_unlinking"]["dream_function"],
            "active_imagination",
        )
        self.assertEqual(candidates["islanded_useful_cluster"]["shape"], "island")
        self.assertIn("healthy_no_shape_control", controls)
        self.assertEqual(controls["healthy_no_shape_control"]["control_result"], "no_candidate")

        for candidate in report["candidates"]:
            self.assertEqual(candidate["kind"], "dream_topology_candidate")
            self.assertEqual(candidate["authority"], "dream_synthesized_candidate_not_fact")
            self.assertFalse(candidate["foreground_eligible"])
            self.assertTrue(candidate["source_anchors"])
            self.assertTrue(candidate["source_reopen_required_before_claim"])
            self.assertEqual(candidate["next_safe_action"], "review_or_route_only")

        shadow = {item["case_id"]: item for item in report["shadow_route_candidates"]}
        self.assertEqual(
            shadow["shadow_route_repeated_failure_orbit"]["kind"],
            "dream_shadow_route_candidate",
        )
        self.assertEqual(
            shadow["shadow_route_repeated_failure_orbit"]["candidate_authority"],
            "candidate_only",
        )
        self.assertEqual(
            shadow["shadow_route_repeated_failure_orbit"]["action_grammar"],
            "direction_with_ref",
        )
        self.assertTrue(
            shadow["shadow_route_repeated_failure_orbit"]["source_reopen_required_before_claim"]
        )
        self.assertFalse(shadow["shadow_route_repeated_failure_orbit"]["foreground_eligible"])
        self.assertFalse(shadow["shadow_route_repeated_failure_orbit"]["fact_claim_allowed"])
        self.assertIn(
            "failed_route_residue_reappeared",
            shadow["shadow_route_repeated_failure_orbit"]["reason_codes"],
        )
        self.assertTrue(
            shadow["shadow_route_repeated_failure_orbit"]["transform_orbit_candidate"][
                "selected_for_deepen"
            ]
        )
        self.assertEqual(
            shadow["shadow_route_partial_glue"]["glue_status"],
            "partial_glue",
        )
        self.assertFalse(shadow["shadow_route_partial_glue"]["glued_route"])

    def test_shadow_route_requires_source_overlap_or_residue_not_generic_vocabulary(self) -> None:
        report = topology_scout.build_dream_topology_scout_report(
            [
                {
                    "case_id": "generic_vocab_only",
                    "shadow_route_probe": True,
                    "visible_route_id": "dream-visible",
                    "latent_route_id": "dream-latent",
                    "shared_topic_tokens": ["dream", "bridge", "topology"],
                    "visible_hexagram": "既济",
                    "latent_hexagram": "未济",
                },
                {
                    "case_id": "orbit_without_shadow_overlap",
                    "visible_route_id": "macro-visible",
                    "latent_route_id": "macro-latent",
                    "visible_hexagram": "乾",
                    "latent_hexagram": "坤",
                },
            ]
        )
        controls = {item["case_id"]: item for item in report["controls"]}

        self.assertEqual(report["metrics"]["shadow_route_candidate_count"], 0)
        self.assertEqual(report["metrics"]["shadow_route_generic_vocab_false_positive_count"], 0)
        self.assertEqual(controls["generic_vocab_only"]["control_result"], "no_shadow_candidate")
        self.assertIn(
            "shared_vocabulary_without_source_or_residue",
            controls["generic_vocab_only"]["reason_codes"],
        )
        self.assertEqual(
            controls["generic_vocab_only"]["transform_orbit_candidate"]["selected_for_deepen"],
            False,
        )
        self.assertEqual(
            controls["orbit_without_shadow_overlap"]["transform_orbit_candidate"][
                "default_ranking_effect"
            ],
            "none",
        )

    def test_hard_negatives_are_rejected_instead_of_interpreted(self) -> None:
        report = topology_scout.build_dream_topology_scout_report(
            [
                {
                    "case_id": "private_psych_interpretation",
                    "shape": "weak_bridge",
                    "source_anchors": ["issue:#163", "issue:#1268"],
                    "private_psychological_interpretation": True,
                },
                {
                    "case_id": "user_diagnosis",
                    "shape": "cycle",
                    "source_anchors": ["issue:#163"],
                    "user_diagnosis": True,
                },
                {
                    "case_id": "profile_claim",
                    "shape": "island",
                    "source_anchors": ["issue:#163"],
                    "profile_claim": True,
                },
                {
                    "case_id": "source_free_symbolic_claim",
                    "shape": "knot",
                    "symbolic_claim": True,
                    "source_anchors": [],
                },
            ]
        )
        rejected = {item["case_id"]: item for item in report["rejected"]}

        self.assertEqual(report["metrics"]["dream_topology_candidate_count"], 0)
        self.assertEqual(report["metrics"]["hard_negative_rejected_count"], 4)
        self.assertEqual(report["metrics"]["source_free_symbolic_claim_rejected_count"], 1)
        self.assertEqual(report["metrics"]["profile_claim_rejected_count"], 1)
        self.assertEqual(report["metrics"]["user_diagnosis_rejected_count"], 1)
        self.assertEqual(report["metrics"]["private_interpretation_rejected_count"], 1)
        self.assertIn("private_psychological_interpretation", rejected["private_psych_interpretation"]["reasons"])
        self.assertIn("user_diagnosis", rejected["user_diagnosis"]["reasons"])
        self.assertIn("profile_claim", rejected["profile_claim"]["reasons"])
        self.assertIn("missing_source_anchor", rejected["source_free_symbolic_claim"]["reasons"])

    def test_cli_sanitizes_private_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "dream-topology-private.json"
            rows = [
                {
                    "case_id": "private_topology_row",
                    "shape": "cycle",
                    "source_anchors": ["source://private/raw-handle"],
                    "raw_source_text": "PRIVATE_DREAM_TOPOLOGY_TEXT must not leave diagnostics",
                    "local_path": str(root / "private-rollout.jsonl"),
                    "private_psychological_interpretation": True,
                }
            ]
            input_path.write_text(json.dumps(rows), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.dream.topology_scout",
                    "--input",
                    str(input_path),
                    "--json",
                ],
                check=False,
                text=True,
                capture_output=True,
                cwd=REPO_ROOT,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        self.assertTrue(payload["safety_gate_ok"])
        self.assertEqual(payload["privacy_boundary"]["forbidden_marker_count"], 0)
        self.assertNotIn("PRIVATE_DREAM_TOPOLOGY_TEXT", encoded)
        self.assertNotIn(str(root), encoded)
        self.assertNotIn("source://private/raw-handle", encoded)


if __name__ == "__main__":
    unittest.main()
