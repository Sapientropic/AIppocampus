from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aippocampus_runtime.navigation.semantic_candidate_context import (
    build_semantic_candidate_context,
)
from aippocampus_runtime.recall.query_expansion import plan_query_expansion
from aippocampus_runtime.recall.semantic_bridge_map import (
    materialize_semantic_bridge_rows,
    reduce_semantic_bridge_candidates,
)
from aippocampus_runtime.recall.semantic_effectiveness import (
    append_semantic_effectiveness_rows,
    apply_semantic_effectiveness_to_candidates,
    load_semantic_effectiveness_rows,
    semantic_candidate_effectiveness_report,
    semantic_effectiveness_rows_from_candidates_and_feedback,
)


def source_ref(label: str) -> dict[str, object]:
    return {"source_id": f"public:{label}", "message_id": f"msg-{label}", "line": 12}

class SemanticCandidateContextBridgeEffectivenessTests(unittest.TestCase):
    def test_source_shaped_context_beats_misleading_generic_keyword(self) -> None:
        context = build_semantic_candidate_context(
            {
                "producer": "semantic_trigger_router",
                "source_refs": [source_ref("dream")],
                "source_families": ["dream_topology", "learning_loop"],
                "scope": "project:AIppocampus",
                "topic_epoch": "semantic-runtime-v1",
                "source_coverage_time": {
                    "start": "2026-06-15T00:00:00Z",
                    "end": "2026-06-15T01:00:00Z",
                },
                "freshness": "current",
                "task_mode": "issue_work",
                "hook_stage": "offline",
                "recent_outcomes": {"source_reopen_success": 2},
                "handles": {"dream": ["route:dream-semantic"], "learning_loop": ["finding:preflight"]},
            }
        )

        self.assertEqual(context["reducer_status"], "accepted")
        self.assertEqual(context["authority"], "navigation_only")
        self.assertEqual(context["claim_permission"], "none")
        self.assertIn("source_shape_context_preferred", context["reason_codes"])
        self.assertIn("dream_topology", context["source_families"])
        self.assertTrue(context["source_reopen_required_before_claim"])

    def test_private_stale_or_malformed_context_fails_open_without_fact_claim(self) -> None:
        private = build_semantic_candidate_context(
            {
                "producer": "semantic_trigger_router",
                "source_refs": [source_ref("private")],
                "privacy_partition": "user_private",
                "freshness": "current",
            }
        )
        stale = build_semantic_candidate_context(
            {
                "producer": "semantic_trigger_router",
                "source_refs": [source_ref("stale")],
                "freshness": "stale",
            }
        )
        malformed = build_semantic_candidate_context(
            {"producer": "semantic_trigger_router", "freshness": "current"}
        )

        self.assertEqual(private["reducer_status"], "blocked")
        self.assertEqual(stale["reducer_status"], "direction_only")
        self.assertEqual(malformed["reducer_status"], "direction_only")
        for row in (private, stale, malformed):
            self.assertEqual(row["claim_permission"], "none")
            self.assertIn("semantic_candidate_context_is_source_truth", row["cannot_claim"])

    def test_semantic_bridge_expands_lexical_near_miss_and_hides_route_text_in_diagnostics(self) -> None:
        bridge_rows = [
            {
                "candidate_id": "bridge:race-condition",
                "from_terms": ["并发 bug"],
                "to_terms": ["race condition", "thread contention"],
                "route_aliases": ["concurrency failure"],
                "source_refs": [source_ref("race")],
                "scope": "project:AIppocampus",
                "scope_bucket": "project",
                "freshness": "current",
            }
        ]

        plan = plan_query_expansion(["并发 bug"], semantic_bridge_rows=bridge_rows)

        self.assertIn("race condition", plan["expanded_terms"])
        self.assertEqual(plan["diagnostics"]["expansion_sources"]["semantic_bridge"], 1)
        self.assertEqual(
            plan["diagnostics"]["boundary"],
            "navigation_only_source_reopen_required",
        )
        self.assertNotIn("race condition", json.dumps(plan["diagnostics"], ensure_ascii=False))
        self.assertTrue(plan["diagnostics"]["semantic_bridge"]["semantic_bridge_fingerprints"])

    def test_semantic_bridge_demotes_stale_private_source_free_and_wrong_route_rows(self) -> None:
        rows = [
            {
                "candidate_id": "bridge:accepted",
                "from_terms": ["先整理"],
                "to_terms": ["run ruff before pytest"],
                "source_refs": [source_ref("workflow")],
                "scope_bucket": "project",
                "freshness": "current",
            },
            {
                "candidate_id": "bridge:stale",
                "from_terms": ["old"],
                "to_terms": ["retired route"],
                "source_refs": [source_ref("stale")],
                "freshness": "stale",
            },
            {
                "candidate_id": "bridge:private",
                "from_terms": ["private"],
                "to_terms": ["do not leak"],
                "source_refs": [source_ref("private")],
                "scope_bucket": "user_private",
            },
            {
                "candidate_id": "bridge:source-free",
                "from_terms": ["unsupported"],
                "to_terms": ["floating guess"],
            },
            {
                "candidate_id": "bridge:wrong",
                "from_terms": ["wrong"],
                "to_terms": ["bad route"],
                "source_refs": [source_ref("wrong")],
            },
            {
                "candidate_id": "bridge:already-demoted",
                "from_terms": ["old sidecar"],
                "to_terms": ["should not expand"],
                "source_refs": [source_ref("old")],
                "status": "demoted",
            },
        ]
        feedback = [{"route_id": "bridge:wrong", "signal": "wrong_route_drag"}]

        reduced = {row["candidate_id"]: row for row in reduce_semantic_bridge_candidates(rows, feedback_rows=feedback)}

        self.assertEqual(reduced["bridge:accepted"]["status"], "accepted")
        self.assertEqual(reduced["bridge:stale"]["status"], "retired")
        self.assertEqual(reduced["bridge:private"]["status"], "blocked")
        self.assertEqual(reduced["bridge:source-free"]["status"], "rejected")
        self.assertEqual(reduced["bridge:wrong"]["status"], "demoted")
        self.assertEqual(reduced["bridge:already-demoted"]["status"], "demoted")
        self.assertTrue(all(row["claim_permission"] == "none" for row in reduced.values()))

    def test_semantic_effectiveness_promotes_demotes_and_holds_sparse_conflict_by_scope(self) -> None:
        candidates = [
            {"candidate_id": "candidate:helpful", "kind": "semantic_bridge", "source_refs": [source_ref("h")], "scope_bucket": "project"},
            {"candidate_id": "candidate:wrong", "kind": "semantic_bridge", "source_refs": [source_ref("w")], "scope_bucket": "project"},
            {"candidate_id": "candidate:sparse", "kind": "semantic_bridge", "source_refs": [source_ref("s")], "scope_bucket": "project"},
            {"candidate_id": "candidate:conflict", "kind": "semantic_bridge", "source_refs": [source_ref("c")], "scope_bucket": "project"},
            {"candidate_id": "candidate:private", "kind": "semantic_bridge", "source_refs": [source_ref("p")], "scope_bucket": "user_private"},
        ]
        events = [
            {"candidate_id": "candidate:helpful", "outcome": "source_reopen_success"},
            {"candidate_id": "candidate:helpful", "outcome": "user_confirmed"},
            {"candidate_id": "candidate:wrong", "outcome": "ignored"},
            {"candidate_id": "candidate:wrong", "outcome": "wrong_route_drag"},
            {"candidate_id": "candidate:sparse", "outcome": "source_reopen_success"},
            {"candidate_id": "candidate:conflict", "outcome": "source_reopen_success"},
            {"candidate_id": "candidate:conflict", "outcome": "blocked"},
            {"candidate_id": "candidate:private", "outcome": "source_reopen_success"},
            {"candidate_id": "candidate:private", "outcome": "user_confirmed"},
        ]

        report = semantic_candidate_effectiveness_report(candidates, events)
        rows = {row["candidate_id"]: row for row in report["rows"]}

        self.assertEqual(rows["candidate:helpful"]["recommendation"], "promote_for_routing")
        self.assertEqual(rows["candidate:wrong"]["recommendation"], "demote")
        self.assertEqual(rows["candidate:sparse"]["recommendation"], "not_enough_evidence")
        self.assertEqual(rows["candidate:conflict"]["recommendation"], "conflicting_feedback_hold")
        self.assertEqual(rows["candidate:private"]["recommendation"], "scope_local_only_no_public_promotion")
        self.assertTrue(rows["candidate:private"]["scope_bucket_preserved"])
        self.assertFalse(report["policy_boundary"]["runtime_weights_changed"])
        self.assertIn("source_truth_from_semantic_feedback", report["cannot_claim"])

    def test_semantic_effectiveness_ledger_demotes_bridge_before_query_expansion(self) -> None:
        bridge_rows = [
            {
                "candidate_id": "bridge:race-condition",
                "kind": "semantic_bridge",
                "from_terms": ["并发 bug"],
                "to_terms": ["race condition"],
                "source_refs": [source_ref("race")],
                "scope_bucket": "project",
                "freshness": "current",
            }
        ]
        feedback_events = [
            {
                "candidate_id": "bridge:race-condition",
                "outcome": "candidate_delivered",
                "event_refs": [{"event_id": "surface-1"}],
            },
            {
                "candidate_id": "bridge:race-condition",
                "outcome": "wrong_route_drag",
                "event_refs": [{"event_id": "wrong-1"}],
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "semantic-effectiveness.jsonl"
            rows = semantic_effectiveness_rows_from_candidates_and_feedback(bridge_rows, feedback_events)
            append_semantic_effectiveness_rows(path, rows)
            loaded_rows = load_semantic_effectiveness_rows(path)

        plan = plan_query_expansion(
            ["并发 bug"],
            semantic_bridge_rows=bridge_rows,
            semantic_effectiveness_rows=loaded_rows,
        )

        self.assertNotIn("race condition", plan["expanded_terms"])
        self.assertEqual(plan["diagnostics"]["semantic_effectiveness"]["applied_count"], 1)
        self.assertEqual(plan["diagnostics"]["semantic_effectiveness"]["demoted_count"], 1)
        self.assertEqual(loaded_rows[0]["recommendation"], "demote")
        self.assertTrue(loaded_rows[0]["source_reopen_required_before_claim"])

    def test_semantic_bridge_materializer_feeds_query_expansion_without_private_truth_claim(self) -> None:
        rows = materialize_semantic_bridge_rows(
            feedback_rows=[
                {
                    "kind": "aippocampus_recall_feedback_event",
                    "candidate_id": "bridge:route-feedback",
                    "query_terms": ["并发 bug"],
                    "reopened_terms": ["race condition"],
                    "outcome": "source_reopen_success",
                    "source_refs": [source_ref("route-feedback")],
                    "event_refs": [{"event_id": "feedback-1"}],
                    "scope_bucket": "project",
                },
                {
                    "kind": "aippocampus_recall_feedback_event",
                    "candidate_id": "bridge:blocked",
                    "query_terms": ["旧路线"],
                    "reopened_terms": ["stale route"],
                    "outcome": "wrong_route_drag",
                    "source_refs": [source_ref("blocked")],
                    "event_refs": [{"event_id": "feedback-2"}],
                    "scope_bucket": "project",
                },
            ],
            learning_rows=[
                {
                    "kind": "aippocampus_learning_finding",
                    "finding_id": "learn-preflight",
                    "finding_kind": "workflow_order_finding",
                    "workflow_family": "cheap_preflight_before_broad_test",
                    "activation_terms": ["先整理"],
                    "route_terms": ["run cheap preflight before broad tests"],
                    "source_refs": [source_ref("learning")],
                    "event_refs": [{"event_id": "learning-1"}],
                    "scope_bucket": "project",
                }
            ],
        )
        plan = plan_query_expansion(["并发 bug"], semantic_bridge_rows=rows)
        stale_plan = plan_query_expansion(["旧路线"], semantic_bridge_rows=rows)
        encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True)

        self.assertIn("race condition", plan["expanded_terms"])
        self.assertNotIn("stale route", stale_plan["expanded_terms"])
        self.assertTrue(all(row["claim_permission"] == "none" for row in rows))
        self.assertTrue(all(row["source_reopen_required_before_claim"] for row in rows))
        self.assertNotIn("C:/", encoded)
        self.assertNotIn("raw_private", encoded)

    def test_semantic_effectiveness_scope_isolated_for_non_recall_candidates(self) -> None:
        candidates = [
            {
                "candidate_id": "dream:candidate",
                "kind": "dream_topology_candidate",
                "source_refs": [source_ref("dream")],
                "scope_bucket": "project",
            },
            {
                "candidate_id": "dream:candidate",
                "kind": "dream_topology_candidate",
                "source_refs": [source_ref("private-dream")],
                "scope_bucket": "user_private",
            },
        ]
        rows = semantic_effectiveness_rows_from_candidates_and_feedback(
            [candidates[0]],
            [
                {"candidate_id": "dream:candidate", "outcome": "candidate_delivered"},
                {"candidate_id": "dream:candidate", "outcome": "blocked"},
            ],
        )

        projected = apply_semantic_effectiveness_to_candidates(candidates, rows)

        self.assertEqual(projected[0]["effectiveness_recommendation"], "demote")
        self.assertEqual(projected[0]["status"], "demoted")
        self.assertNotIn("effectiveness_recommendation", projected[1])
        self.assertEqual(rows[0]["producer_kind"], "dream_probe")

if __name__ == "__main__":
    unittest.main()
