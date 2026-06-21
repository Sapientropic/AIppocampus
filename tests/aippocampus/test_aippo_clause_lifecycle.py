from __future__ import annotations

import json
import unittest

from aippocampus_runtime.aippo import clause_lifecycle as lifecycle


def clause(clause_id: str, *, status: str = "growing", kind: str = "workflow_order_clause") -> dict[str, object]:
    return {
        "clause_id": clause_id,
        "kind": kind,
        "guidance": "Run ruff before broad pytest.",
        "applies_when": ["coding", "test"],
        "support": {"support_grade": "source_supported", "source_ref_count": 2},
        "source_refs": [{"source_ref": f"src:{clause_id}:a"}, {"source_ref": f"src:{clause_id}:b"}],
        "freshness": {"last_source_seen_at": "2026-06-14T00:00:00Z"},
        "lifecycle": {"status": status},
        "activation": {"foreground_eligible": status == "ripe"},
    }

class AIppoClauseLifecycleTests(unittest.TestCase):
    def test_growing_clause_emits_probe_and_ripens_only_from_source_backed_outcome(self) -> None:
        clauses = [clause("preflight")]
        probes = lifecycle.verification_probes_from_growing_clauses(clauses)
        self_report = lifecycle.apply_probe_outcomes(
            clauses,
            [{"clause_id": "preflight", "outcome_signal": "helped", "self_report_only": True}],
        )
        ripened = lifecycle.apply_probe_outcomes(
            clauses,
            [{"clause_id": "preflight", "outcome_signal": "helped", "source_backed": True}],
        )

        self.assertEqual(len(probes), 1)
        self.assertFalse(probes[0]["can_ripen_from_agent_self_report"])
        self.assertEqual(self_report[0]["lifecycle"]["status"], "growing")
        self.assertEqual(ripened[0]["lifecycle"]["status"], "ripe")
        self.assertTrue(ripened[0]["activation"]["foreground_eligible"])

    def test_source_backed_negative_outcome_challenges_instead_of_ripening(self) -> None:
        challenged = lifecycle.apply_probe_outcomes(
            [clause("preflight")],
            [
                {
                    "clause_id": "preflight",
                    "outcome_signal": "wrong_route_drag",
                    "source_backed": True,
                }
            ],
        )

        self.assertEqual(challenged[0]["lifecycle"]["status"], "challenged")
        self.assertEqual(challenged[0]["activation"]["next_action"], "reopen_source")
        self.assertFalse(challenged[0]["activation"]["foreground_eligible"])

    def test_relations_emit_ordered_plan_or_deepen_on_conflict(self) -> None:
        ordered = [
            {**clause("preflight", status="ripe"), "relations": {"ordered_before": ["broad_test"]}},
            clause("broad_test", status="ripe"),
        ]
        conflicting = [
            {**clause("route_a", status="ripe"), "relations": {"conflicts_with": ["route_b"]}},
            clause("route_b", status="ripe"),
        ]

        ordered_plan = lifecycle.resolve_clause_relations(ordered, task="coding")
        conflict_plan = lifecycle.resolve_clause_relations(conflicting, task="coding")

        self.assertEqual(ordered_plan["next_action"], "ordered_mini_plan")
        self.assertEqual(ordered_plan["ordered_plan"][0]["before"], "preflight")
        self.assertEqual(conflict_plan["next_action"], "deepen_or_reopen_source")
        self.assertEqual(conflict_plan["selected_clause_ids"], [])
        self.assertFalse(conflict_plan["relation_metadata_raises_authority"])

    def test_decay_and_weighted_feedback_preserve_clean_source_boundary(self) -> None:
        stale_env = clause("env", status="ripe", kind="environment_workaround")
        stale_env["freshness"] = {"last_source_seen_at": "2026-05-01T00:00:00Z"}

        report = lifecycle.calibrate_clause_lifecycle(
            [stale_env],
            [
                {"clause_id": "env", "outcome_signal": "noisy", "severity": 1},
                {"clause_id": "env", "outcome_signal": "wrong_route_drag", "severity": 5},
                {"clause_id": "env", "outcome_signal": "helped", "self_report_only": True},
            ],
        )

        updated = report["updated_clauses"][0]
        self.assertEqual(updated["lifecycle"]["status"], "challenged")
        self.assertEqual(report["feedback_weight_by_clause"]["env"], 6)
        self.assertFalse(report["clean_source_mutated"])
        self.assertFalse(report["activation_packets_include_feedback_traces"])

    def test_fixture_report_has_no_raw_leaks(self) -> None:
        report = lifecycle.build_clause_lifecycle_fixture_report()
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertTrue(report["ok"], encoded)
        self.assertNotIn("pytest tests/private", encoded)
        self.assertEqual(report["red_lines"]["raw_command_or_path_leak_count"], 0)

if __name__ == "__main__":
    unittest.main()
