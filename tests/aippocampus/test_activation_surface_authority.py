from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops.activation_authority_audit import (  # noqa: E402
    AUTHORITY_AUDIT_KIND,
    activation_surface_authority_audit,
    fixture_authority_conflict_audit,
)


class ActivationSurfaceAuthorityTests(unittest.TestCase):
    def test_current_checkout_evidence_overrides_stale_strategy_surfaces(self) -> None:
        report = activation_surface_authority_audit(
            [
                {
                    "surface_id": "aar_old_guardrail",
                    "surface_kind": "aar_nudge",
                    "authority_level": "guardrail",
                    "conflict_key": "repo-test-command",
                    "freshness": "stale",
                },
                {
                    "surface_id": "dream_old_hint",
                    "surface_kind": "dream_hypothesis",
                    "conflict_key": "repo-test-command",
                    "freshness": "stale",
                },
                {
                    "surface_id": "lock_route_only",
                    "surface_kind": "active_recall_lock",
                    "conflict_key": "repo-test-command",
                    "freshness": "current",
                },
                {
                    "surface_id": "semantic_old_route",
                    "surface_kind": "semantic_trigger",
                    "conflict_key": "repo-test-command",
                    "freshness": "stale",
                },
                {
                    "surface_id": "current_repo_file",
                    "surface_kind": "current_checkout_evidence",
                    "conflict_key": "repo-test-command",
                    "source_refs": [{"source_id": "clean:repo", "thread_key": "session:repo"}],
                },
            ]
        )

        conflict = report["conflicts"][0]

        self.assertEqual(report["kind"], AUTHORITY_AUDIT_KIND)
        self.assertEqual(conflict["winner_surface_id"], "current_repo_file")
        self.assertEqual(
            conflict["resolution_reason"],
            "current_checkout_evidence_overrides_strategy_surfaces",
        )
        self.assertIn("aar_old_guardrail", conflict["suppressed_surface_ids"])
        self.assertEqual(report["metrics"]["source_or_current_evidence_override_count"], 1)
        self.assertEqual(report["metrics"]["activation_surface_authority_leak_count"], 0)

    def test_explicit_user_correction_suppresses_plausible_activation(self) -> None:
        report = activation_surface_authority_audit(
            [
                {
                    "surface_id": "user_corrected_path",
                    "surface_kind": "explicit_user_correction",
                    "conflict_key": "memory-theme",
                    "source_refs": [{"source_id": "clean:correction", "message_id": "m1"}],
                },
                {
                    "surface_id": "plausible_aar_nudge",
                    "surface_kind": "aar_nudge",
                    "authority_level": "guardrail",
                    "conflict_key": "memory-theme",
                    "freshness": "current",
                },
                {
                    "surface_id": "plausible_dream",
                    "surface_kind": "dream_hypothesis",
                    "conflict_key": "memory-theme",
                    "freshness": "current",
                },
            ]
        )
        conflict = report["conflicts"][0]

        self.assertEqual(conflict["winner_surface_id"], "user_corrected_path")
        self.assertEqual(
            conflict["resolution_reason"],
            "explicit_user_correction_suppresses_strategy_surfaces",
        )
        self.assertEqual(report["metrics"]["explicit_user_correction_override_count"], 1)

    def test_pruning_rows_change_activation_eligibility_not_truth_or_source(self) -> None:
        report = activation_surface_authority_audit(
            [
                {
                    "surface_id": "demote_noisy_trigger",
                    "surface_kind": "pruning_row",
                    "pruning_action": "demote",
                    "conflict_key": "trigger-noise",
                },
                {
                    "surface_id": "park_uncertain_dream",
                    "surface_kind": "pruning_row",
                    "pruning_action": "park",
                    "conflict_key": "dream-noise",
                },
                {
                    "surface_id": "retire_superseded_nudge",
                    "surface_kind": "pruning_row",
                    "pruning_action": "retire",
                    "conflict_key": "nudge-noise",
                },
            ]
        )
        surfaces = {row["surface_id"]: row for row in report["surfaces"]}

        self.assertEqual(surfaces["demote_noisy_trigger"]["authority_level"], "guardrail")
        self.assertEqual(surfaces["park_uncertain_dream"]["authority_level"], "blocked")
        self.assertEqual(surfaces["retire_superseded_nudge"]["authority_level"], "blocked")
        self.assertFalse(surfaces["park_uncertain_dream"]["eligible_for_foreground"])
        self.assertEqual(report["metrics"]["activation_truth_status_mutation_attempt_count"], 0)
        self.assertEqual(report["metrics"]["activation_clean_source_mutation_attempt_count"], 0)
        self.assertTrue(report["contract"]["pruning_changes_activation_eligibility_only"])

    def test_authority_leak_counts_strategy_rows_used_as_fact_without_source(self) -> None:
        report = activation_surface_authority_audit(
            [
                {
                    "surface_id": "dream_quoted_as_fact",
                    "surface_kind": "dream_hypothesis",
                    "conflict_key": "bad-claim",
                    "quoted_as_factual_evidence": True,
                },
                {
                    "surface_id": "source_backed_claim",
                    "surface_kind": "source_reopen_evidence",
                    "conflict_key": "bad-claim",
                    "quoted_as_factual_evidence": True,
                    "source_refs": [{"source_id": "clean:source", "message_id": "m2"}],
                },
            ]
        )

        self.assertEqual(report["metrics"]["activation_surface_authority_leak_count"], 1)
        leaked = [row for row in report["surfaces"] if row["authority_leak"]]
        self.assertEqual(leaked[0]["surface_id"], "dream_quoted_as_fact")

    def test_report_does_not_echo_raw_prompt_snippet_or_local_path_labels(self) -> None:
        local_path = "E:" + "\\private\\memory\\thread.jsonl"
        secretish_label = "sk-" + "test-secret-label"
        report = activation_surface_authority_audit(
            [
                {
                    "surface_id": local_path,
                    "surface_kind": "ambient_card",
                    "conflict_key": secretish_label,
                    "prompt": "raw prompt text should not be serialized",
                    "snippet": "raw source snippet should not be serialized",
                    "path": local_path,
                    "quoted_as_factual_evidence": True,
                }
            ]
        )
        serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertNotIn("raw prompt text", serialized)
        self.assertNotIn("raw source snippet", serialized)
        self.assertNotIn("private\\memory", serialized)
        self.assertNotIn(secretish_label, serialized)
        self.assertTrue(report["privacy_boundary"]["local_paths_serialized"] is False)
        self.assertEqual(report["metrics"]["activation_surface_authority_leak_count"], 1)

    def test_fixture_conflict_audit_exposes_conflicts_without_leaks(self) -> None:
        report = fixture_authority_conflict_audit()

        self.assertEqual(report["metrics"]["conflict_count"], 2)
        self.assertEqual(report["metrics"]["activation_surface_authority_leak_count"], 0)
        self.assertTrue(report["contract"]["activation_rows_are_not_factual_memory_store"])


if __name__ == "__main__":
    unittest.main()
