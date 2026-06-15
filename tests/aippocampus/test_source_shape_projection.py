from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.dream import topology_scout  # noqa: E402
from aippocampus_runtime.navigation import local_global_compatibility  # noqa: E402
from aippocampus_runtime.navigation import source_shape_projection as projection  # noqa: E402


def source_ref(name: str) -> dict[str, str]:
    return {"source_id": f"source:{name}", "message_id": f"msg:{name}"}


class SourceShapeProjectionTests(unittest.TestCase):
    def test_learning_finding_projects_across_layers_into_aippo_and_action_hint(self) -> None:
        report = projection.project_learning_findings_to_source_shape(
            [
                {
                    "finding_id": "preflight-finding",
                    "finding_kind": "workflow_order_finding",
                    "workflow_family": "cheap_preflight_before_broad_test",
                    "candidate_family": "workflow_order_candidate",
                    "status": "open",
                    "confidence": "high",
                    "source_ref_count": 3,
                    "source_refs": [source_ref("fail"), source_ref("ruff"), source_ref("pass")],
                    "scope": "project:AIppocampus",
                }
            ]
        )
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["ok"], encoded)
        self.assertEqual(report["macro_signals"][0]["pressure"], "action_order_signal")
        self.assertEqual(report["topology_signals"][0]["shape"], "weak_bridge")
        self.assertEqual(report["local_global_checks"][0]["result"], "glued_route")
        self.assertEqual(
            report["prepared_action_hint_cache"]["provider_counts"]["aippo_learned_clause"],
            1,
        )
        self.assertEqual(report["multi_pan_task_time_readout"]["action_layer"], 1)
        self.assertIn("microcircuit_diagnostics", report["navigation_projection"])
        self.assertEqual(report["red_lines"]["authority_raised_above_navigation_only_count"], 0)
        self.assertNotIn("PRIVATE", encoded)

    def test_non_aippocampus_scope_and_topic_are_preserved_through_aippo_glue(self) -> None:
        report = projection.project_learning_findings_to_source_shape(
            [
                {
                    "finding_id": "other-repo-preflight",
                    "finding_kind": "workflow_order_finding",
                    "workflow_family": "cheap_preflight_before_broad_test",
                    "candidate_family": "workflow_order_candidate",
                    "status": "open",
                    "confidence": "high",
                    "source_ref_count": 3,
                    "source_refs": [source_ref("other-fail"), source_ref("other-pass")],
                    "scope": "project:OtherRepo",
                    "topic_epoch": "release-hardening",
                    "workspace_or_environment_profile": "linux-ci",
                }
            ]
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["aippo_clause_seeds"][0]["scope"], "project:OtherRepo")
        self.assertEqual(report["aippo_clause_seeds"][0]["topic_epoch"], "release-hardening")
        self.assertEqual(report["local_global_checks"][0]["result"], "glued_route")
        contracts = report["local_global_checks"][0]["section_contracts"]
        self.assertTrue(any(item["scope"] == "project:OtherRepo" for item in contracts))

    def test_aippo_scope_mismatch_becomes_obstruction_not_glue(self) -> None:
        row = local_global_compatibility.evaluate_local_global_compatibility(
            [
                {
                    "case_id": "learning",
                    "kind": "learning_loop_section",
                    "scope": "project:OtherRepo",
                    "topic_epoch": "release-hardening",
                    "source_ids": ["src:shared"],
                },
                {
                    "case_id": "aippo",
                    "kind": "aippocampus_aippo_activation_packet",
                    "scope": "project:AIppocampus",
                    "topic_epoch": "learning-loop",
                    "source_ids": ["src:shared"],
                },
            ],
            case_id="scope_mismatch",
        )

        self.assertEqual(row["result"], "obstruction")
        self.assertIn("source_supported_sections_need_scope_review", row["reason_codes"])

    def test_stale_and_local_only_findings_stay_suppressed_without_poisoning_active_path(self) -> None:
        report = projection.project_learning_findings_to_source_shape(
            [
                {
                    "finding_id": "active",
                    "finding_kind": "recurring_failure_finding",
                    "status": "open",
                    "source_ref_count": 2,
                    "source_refs": [source_ref("a"), source_ref("b")],
                    "scope": "project:AIppocampus",
                },
                {
                    "finding_id": "stale",
                    "finding_kind": "workflow_order_finding",
                    "status": "stale",
                    "source_ref_count": 2,
                    "source_refs": [source_ref("old"), source_ref("old2")],
                },
                {
                    "finding_id": "local",
                    "finding_kind": "environment_workaround_candidate",
                    "scope": "machine:local",
                    "source_ref_count": 2,
                    "source_refs": [source_ref("local"), source_ref("local2")],
                },
            ]
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["suppressed_finding_count"], 2)
        self.assertEqual(report["red_lines"]["stale_or_local_only_foreground_count"], 0)
        self.assertEqual(len(report["macro_signals"]), 1)

    def test_local_global_obstruction_localizes_feedback_dimension(self) -> None:
        row = local_global_compatibility.evaluate_local_global_compatibility(
            [
                {
                    "case_id": "old",
                    "kind": "learning_loop_section",
                    "scope": "project:AIppocampus",
                    "source_ids": ["src:shared"],
                    "status": "stale",
                },
                {
                    "case_id": "new",
                    "kind": "aippocampus_aippo_activation_packet",
                    "scope": "project:AIppocampus",
                    "source_ids": ["src:shared"],
                },
            ],
            case_id="stale_learning_clause",
        )

        self.assertEqual(row["result"], "obstruction")
        self.assertEqual(row["obstruction_localization"]["dimension"], "freshness")
        self.assertEqual(
            row["obstruction_localization"]["feedback_layer"],
            "lifecycle_calibration",
        )

    def test_topology_shape_can_trigger_learning_loop_pattern_completion_without_authority_raise(self) -> None:
        candidate = topology_scout.candidate_or_rejection(
            {
                "case_id": "learning_cycle",
                "shape": "cycle",
                "source_anchors": ["issue:#1602"],
                "learning_finding_id": "learn_find_123",
            }
        )

        self.assertEqual(candidate["kind"], "dream_topology_candidate")
        self.assertEqual(
            candidate["cross_layer_projection"]["trigger_job"],
            "pattern_completion_learning_loop_review",
        )
        self.assertTrue(candidate["cross_layer_projection"]["does_not_raise_authority"])
        self.assertFalse(candidate["foreground_eligible"])


if __name__ == "__main__":
    unittest.main()
