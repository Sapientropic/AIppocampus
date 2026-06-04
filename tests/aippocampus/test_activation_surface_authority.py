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
    activation_dead_letter_candidate_report,
    activation_surface_authority_audit,
    apply_activation_lifecycle_manifest,
    apply_dead_letter_candidate_manifest,
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

    def test_foreground_usefulness_metrics_count_noise_reduction_not_only_size(self) -> None:
        report = activation_surface_authority_audit(
            [
                {
                    "surface_id": "stale_false_scent",
                    "surface_kind": "ambient_card",
                    "conflict_key": "old-route",
                    "freshness": "stale",
                    "would_emit_scent": True,
                    "pruning_action": "demote",
                    "wrong_route_drag_count": 2,
                    "estimated_verification_tool_calls": 3,
                    "recent_helpful_count": 0,
                    "recent_harmful_count": 2,
                },
                {
                    "surface_id": "duplicate_lock",
                    "surface_kind": "active_recall_lock",
                    "conflict_key": "old-route",
                    "would_emit_scent": True,
                    "pruning_action": "retire",
                    "estimated_verification_tool_calls": 1,
                    "recent_helpful_count": 1,
                    "recent_harmful_count": 0,
                },
                {
                    "surface_id": "fresh_useful_route",
                    "surface_kind": "semantic_trigger",
                    "conflict_key": "new-route",
                    "freshness": "current",
                    "would_emit_scent": True,
                    "pruning_action": "keep",
                    "estimated_verification_tool_calls": 2,
                    "recent_helpful_count": 3,
                    "recent_harmful_count": 0,
                },
            ]
        )
        metrics = report["metrics"]

        self.assertEqual(metrics["false_scent_reduction_count"], 1)
        self.assertEqual(metrics["wrong_route_drag_reduction_count"], 1)
        self.assertEqual(metrics["duplicate_route_collapse_count"], 1)
        self.assertEqual(metrics["foreground_budget_saved_tool_calls"], 4)
        self.assertEqual(metrics["recent_helpfulness_count"], 4)
        self.assertEqual(metrics["recent_harmfulness_count"], 2)
        self.assertEqual(metrics["active_surface_count_before_pruning"], 3)
        self.assertEqual(metrics["active_surface_count_after_pruning"], 1)

    def test_apply_manifest_is_bounded_append_only_and_preserves_source_refs(self) -> None:
        manifest = apply_activation_lifecycle_manifest(
            [
                {
                    "surface_id": "noisy_card",
                    "surface_kind": "ambient_card",
                    "conflict_key": "old-route",
                    "pruning_action": "park",
                    "source_refs": [
                        {
                            "source_id": "clean:1",
                            "message_id": "m1",
                            "thread_key": "E:" + "\\private\\thread.jsonl",
                        }
                    ],
                    "prompt": "raw prompt text should not enter apply manifest",
                    "path": "E:" + "\\private\\thread.jsonl",
                },
                {
                    "surface_id": "source_row",
                    "surface_kind": "source_reopen_evidence",
                    "conflict_key": "old-route",
                    "pruning_action": "retire",
                    "source_refs": [{"source_id": "clean:source", "message_id": "m2"}],
                },
            ]
        )

        self.assertTrue(manifest["ok"], manifest)
        self.assertEqual(manifest["update_count"], 1)
        update = manifest["updates"][0]
        self.assertEqual(update["surface_id"], "noisy_card")
        self.assertEqual(update["action"], "park")
        self.assertEqual(update["lifecycle_state_after"], "parked")
        self.assertFalse(update["activation_eligible_after"])
        self.assertEqual(update["source_refs"][0]["source_id"], "clean:1")
        self.assertEqual(update["source_refs"][0]["thread_key"], "<redacted-sensitive-label>")
        self.assertTrue(update["source_refs_preserved"])
        self.assertFalse(update["clean_source_mutation"])
        self.assertFalse(update["truth_status_changed"])
        self.assertTrue(manifest["contract"]["append_only_lifecycle_update"])

        serialized = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("raw prompt text", serialized)
        self.assertNotIn("private\\thread", serialized)
        self.assertNotIn("source_row", {item["surface_id"] for item in manifest["updates"]})

    def test_dead_letter_report_flags_only_unreferenced_drag_after_lifecycle_pruning(self) -> None:
        report = activation_dead_letter_candidate_report(
            [
                {
                    "surface_id": "retired_wrong_route",
                    "surface_kind": "ambient_card",
                    "conflict_key": "old-route",
                    "pruning_action": "retire",
                    "wrong_route_drag_count": 4,
                    "source_refs": [{"source_id": "clean:1", "message_id": "m1"}],
                    "provenance_pointer": "manifest:ambient-card-1",
                },
                {
                    "surface_id": "parked_without_reopen",
                    "surface_kind": "dream_hypothesis",
                    "conflict_key": "old-dream",
                    "pruning_action": "park",
                    "no_source_reopen_count": 3,
                    "source_refs": [{"source_id": "clean:2", "message_id": "m2"}],
                },
                {
                    "surface_id": "referenced_bad_route",
                    "surface_kind": "semantic_trigger",
                    "conflict_key": "protected-route",
                    "pruning_action": "retire",
                    "wrong_route_drag_count": 8,
                    "referenced_by": ["promotion_candidate:semantic-trigger-review"],
                    "source_refs": [{"source_id": "clean:3", "message_id": "m3"}],
                },
                {
                    "surface_id": "current_helpful_route",
                    "surface_kind": "active_recall_lock",
                    "conflict_key": "current-route",
                    "pruning_action": "keep",
                    "wrong_route_drag_count": 10,
                    "recent_helpful_count": 5,
                },
                {
                    "surface_id": "source_row_not_activation",
                    "surface_kind": "source_reopen_evidence",
                    "conflict_key": "old-route",
                    "pruning_action": "retire",
                    "wrong_route_drag_count": 10,
                    "source_refs": [{"source_id": "clean:source", "message_id": "m4"}],
                },
            ],
            wrong_route_drag_threshold=3,
            no_source_reopen_threshold=3,
        )

        self.assertEqual(report["kind"], "aippocampus_activation_dead_letter_candidate_report")
        self.assertFalse(report["write_mode"])
        self.assertEqual(report["metrics"]["dead_letter_candidate_count"], 2)
        self.assertEqual(report["metrics"]["payload_compacted_count"], 0)
        self.assertEqual(report["metrics"]["wrong_route_drag_threshold_hits"], 1)
        self.assertEqual(report["metrics"]["no_source_reopen_threshold_hits"], 1)
        self.assertEqual(report["metrics"]["referenced_row_protection_count"], 1)
        self.assertEqual(report["metrics"]["protected_surface_count"], 1)

        reason_sets = [set(candidate["reason_codes"]) for candidate in report["candidates"]]
        self.assertIn({"wrong_route_drag_threshold", "lifecycle_not_foreground_eligible"}, reason_sets)
        self.assertIn({"no_source_reopen_threshold", "lifecycle_not_foreground_eligible"}, reason_sets)
        for candidate in report["candidates"]:
            self.assertIn("surface_id_hash", candidate)
            self.assertIn("source_ref_count", candidate)
            self.assertNotIn("source_refs", candidate)
            self.assertTrue(candidate["source_refs_preserved"])
            self.assertEqual(candidate["recommended_action"], "dead_letter_candidate_no_write")

        self.assertTrue(report["contract"]["no_write_report_only"])
        self.assertTrue(report["contract"]["clean_source_preserved"])
        self.assertTrue(report["contract"]["foreground_hook_mutation"] is False)

    def test_dead_letter_report_stays_public_safe_and_embeds_in_authority_audit(self) -> None:
        local_path = "E:" + "\\private\\activation\\surface.json"
        report = activation_surface_authority_audit(
            [
                {
                    "surface_id": local_path,
                    "surface_kind": "ambient_card",
                    "conflict_key": "sk-" + "activation-secret-label",
                    "pruning_action": "retire",
                    "wrong_route_drag_count": 5,
                    "prompt": "raw prompt text should not leak",
                    "snippet": "raw source snippet should not leak",
                    "path": local_path,
                    "source_refs": [
                        {
                            "source_id": "clean:private",
                            "thread_key": local_path,
                            "message_id": "m1",
                        }
                    ],
                }
            ]
        )
        dead_letter = report["dead_letter_report"]
        serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(dead_letter["metrics"]["dead_letter_candidate_count"], 1)
        self.assertEqual(report["metrics"]["dead_letter_candidate_count"], 1)
        self.assertEqual(report["metrics"]["payload_compacted_count"], 0)
        self.assertEqual(report["metrics"]["wrong_route_drag_threshold_hits"], 1)
        self.assertNotIn("raw prompt text", serialized)
        self.assertNotIn("raw source snippet", serialized)
        self.assertNotIn("private\\activation", serialized)
        self.assertTrue(dead_letter["privacy_boundary"]["raw_prompt_serialized"] is False)
        self.assertTrue(dead_letter["privacy_boundary"]["raw_source_snippets_serialized"] is False)
        self.assertTrue(dead_letter["privacy_boundary"]["local_paths_serialized"] is False)
        self.assertTrue(report["contract"]["foreground_hook_mutation"] is False)

    def test_dead_letter_apply_manifest_requires_reference_safety_and_preserves_source(self) -> None:
        manifest = apply_dead_letter_candidate_manifest(
            [
                {
                    "surface_id": "retired_wrong_route",
                    "surface_kind": "ambient_card",
                    "conflict_key": "old-route",
                    "pruning_action": "retire",
                    "wrong_route_drag_count": 4,
                    "source_refs": [{"source_id": "clean:1", "message_id": "m1"}],
                    "provenance_pointer": "manifest:ambient-card-1",
                    "prompt": "raw prompt text should not enter dead-letter manifest",
                    "payload": "raw activation payload should not enter dead-letter manifest",
                },
                {
                    "surface_id": "protected_wrong_route",
                    "surface_kind": "ambient_card",
                    "conflict_key": "old-route",
                    "pruning_action": "retire",
                    "wrong_route_drag_count": 4,
                    "referenced_by": ["review_artifact:keep-this-visible"],
                    "source_refs": [{"source_id": "clean:2", "message_id": "m2"}],
                    "provenance_pointer": "manifest:ambient-card-2",
                },
            ],
            applied_at="2026-06-04T20:00:00Z",
        )

        self.assertTrue(manifest["ok"], manifest)
        self.assertEqual(manifest["kind"], "aippocampus_activation_dead_letter_apply_manifest")
        self.assertEqual(manifest["update_count"], 1)
        self.assertEqual(manifest["skipped_count"], 1)
        self.assertEqual(manifest["metrics"]["dead_lettered_count"], 1)
        self.assertEqual(manifest["metrics"]["payload_compacted_count"], 0)
        update = manifest["updates"][0]
        self.assertEqual(update["lifecycle_action"], "dead_lettered")
        self.assertEqual(update["source_ref_count"], 1)
        self.assertTrue(update["source_refs_preserved"])
        self.assertFalse(update["payload_compacted"])
        self.assertEqual(update["applied_at"], "2026-06-04T20:00:00Z")
        self.assertIn("wrong_route_drag_threshold", update["reason_codes"])
        self.assertIn("rebuild_or_review_note", update)
        self.assertTrue(manifest["contract"]["append_only_lifecycle_update"])
        self.assertTrue(manifest["contract"]["clean_source_mutation"] is False)
        self.assertTrue(manifest["contract"]["foreground_hook_mutation"] is False)

        serialized = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("raw prompt text", serialized)
        self.assertNotIn("raw activation payload", serialized)
        self.assertNotIn("protected_wrong_route", serialized)


if __name__ == "__main__":
    unittest.main()
