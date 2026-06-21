import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "aippocampus" / "scripts"

from aippocampus_runtime.recall import retrieval, score_fusion, segment_search
from aippocampus_runtime.recall.before_commitment import (
    before_commitment_surface_map,
    build_before_commitment_fixture,
)
from aippocampus_runtime.recall.candidate_planning import plan_candidates
from aippocampus_runtime.recall.outcome_feedback import (
    build_recall_outcome_event,
    recall_outcome_report,
    write_recall_outcome_event,
)
from aippocampus_runtime.recall.scoring_policy import (
    ACTIVE_RECALL_POLICY,
    PHASE_WEIGHT_POLICY,
    RAG_CHUNK_TEXT_POLICY,
    RETRIEVAL_DIVERSITY_POLICY,
    RETRIEVAL_TEXT_POLICY,
    SEGMENT_MERGE_POLICY,
)
from aippocampus_runtime.recall.strategy_planner import select_recall_strategy


class RecallScoringPolicyTests(unittest.TestCase):
    def _row(self, *, role: str, phase: str = "", is_final: int = 0) -> sqlite3.Row:
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        try:
            con.execute("CREATE TABLE messages (role TEXT, phase TEXT, is_final INTEGER)")
            con.execute(
                "INSERT INTO messages (role, phase, is_final) VALUES (?, ?, ?)",
                (role, phase, is_final),
            )
            return con.execute("SELECT role, phase, is_final FROM messages").fetchone()
        finally:
            con.close()

    def test_phase_weight_policy_names_source_preference(self) -> None:
        self.assertGreater(PHASE_WEIGHT_POLICY.final_answer, PHASE_WEIGHT_POLICY.user)
        self.assertLess(PHASE_WEIGHT_POLICY.commentary, 0.0)
        self.assertLess(PHASE_WEIGHT_POLICY.tool, PHASE_WEIGHT_POLICY.commentary)

        self.assertEqual(
            retrieval.phase_weight(self._row(role="assistant", phase="final_answer")),
            PHASE_WEIGHT_POLICY.final_answer,
        )
        self.assertEqual(
            retrieval.phase_weight(self._row(role="user")),
            PHASE_WEIGHT_POLICY.user,
        )
        self.assertEqual(
            retrieval.phase_weight(self._row(role="assistant", phase="commentary")),
            PHASE_WEIGHT_POLICY.commentary,
        )
        self.assertEqual(
            retrieval.phase_weight(self._row(role="tool")),
            PHASE_WEIGHT_POLICY.tool,
        )

    def test_text_score_helpers_read_named_policy_values(self) -> None:
        text_score = score_fusion.retrieval_text_score(
            {"fts": 5.0, "rag_chunk": 2.0},
            literal_hits=2,
            expanded_hits=5,
            anchor_hits=3,
            phase_weight=PHASE_WEIGHT_POLICY.final_answer,
        )
        self.assertEqual(
            text_score,
            5.0
            + 2.0
            + 2 * RETRIEVAL_TEXT_POLICY.literal_hit
            + 3 * RETRIEVAL_TEXT_POLICY.expanded_hit
            + 3 * RETRIEVAL_TEXT_POLICY.anchor_hit
            + PHASE_WEIGHT_POLICY.final_answer,
        )

        chunk_score = score_fusion.rag_chunk_text_score(
            {"chunk_fts": 4.0, "chunk_literal_scan": RAG_CHUNK_TEXT_POLICY.literal_scan_signal},
            literal_hits=1,
            expanded_hits=4,
            anchor_hits=2,
        )
        self.assertEqual(
            chunk_score,
            4.0
            + RAG_CHUNK_TEXT_POLICY.literal_scan_signal
            + RAG_CHUNK_TEXT_POLICY.literal_hit
            + 3 * RAG_CHUNK_TEXT_POLICY.expanded_hit
            + 2 * RAG_CHUNK_TEXT_POLICY.anchor_hit,
        )

    def test_active_recall_policy_names_decision_bands(self) -> None:
        self.assertLess(ACTIVE_RECALL_POLICY.search_threshold, ACTIVE_RECALL_POLICY.high_threshold)

        medium = retrieval.active_recall_decision(
            "请帮我回忆一下之前那个实现边界",
            [],
            None,
        )
        self.assertEqual(medium["decision"], "search")
        self.assertEqual(medium["confidence"], "medium")
        self.assertGreaterEqual(medium["score"], ACTIVE_RECALL_POLICY.search_threshold)
        self.assertLess(medium["score"], ACTIVE_RECALL_POLICY.high_threshold)

        high = retrieval.active_recall_decision(
            "继续之前那个记忆和上下文相关的长期项目",
            [{"title": "长期项目", "score": 12.0}],
            {"index": {"stale": True}, "checkpoint": {"due": True}},
        )
        self.assertEqual(high["decision"], "search")
        self.assertEqual(high["confidence"], "high")
        self.assertGreaterEqual(high["score"], ACTIVE_RECALL_POLICY.high_threshold)

    def test_diversity_policy_keeps_one_nearby_bucket_from_crowding_out_source_hits(self) -> None:
        self.assertGreater(RETRIEVAL_DIVERSITY_POLICY.bucket_repeat_penalty, 0.0)
        self.assertGreater(RETRIEVAL_DIVERSITY_POLICY.nearby_line_penalty, 0.0)

        selected = retrieval.diversify_results(
            [
                {"id": 1, "line": 10, "role": "assistant", "score": 100.0, "signals": {}},
                {"id": 2, "line": 20, "role": "assistant", "score": 99.0, "signals": {}},
                {"id": 3, "line": 450, "role": "assistant", "score": 88.0, "signals": {}},
            ],
            limit=2,
        )

        self.assertEqual([item["id"] for item in selected], [1, 3])

    def test_segment_merge_policy_keeps_one_segment_from_crowding_out_other_hits(self) -> None:
        self.assertGreater(SEGMENT_MERGE_POLICY.same_segment_penalty, 0.0)
        self.assertGreater(SEGMENT_MERGE_POLICY.nearby_line_penalty, 0.0)

        selected = segment_search.merge_topk(
            [
                {
                    "segment_id": "seg-a",
                    "id": 1,
                    "line": 10,
                    "role": "assistant",
                    "phase": "final_answer",
                    "score": 50.0,
                    "signals": {},
                },
                {
                    "segment_id": "seg-a",
                    "id": 2,
                    "line": 20,
                    "role": "assistant",
                    "score": 49.0,
                    "signals": {},
                },
                {
                    "segment_id": "seg-b",
                    "id": 1,
                    "line": 300,
                    "role": "assistant",
                    "score": 43.0,
                    "signals": {},
                },
            ],
            limit=2,
        )

        self.assertEqual([item["segment_id"] for item in selected], ["seg-a", "seg-b"])

    def test_candidate_policy_prefilters_scope_but_keeps_history_and_dispute_reachable(self) -> None:
        candidates = [
            {
                "candidate_id": "wrong-scope",
                "lexical_score": 98.0,
                "project_id": "beta",
                "freshness": "current",
                "authority": "bounded_evidence",
            },
            {
                "candidate_id": "stale-alpha",
                "lexical_score": 96.0,
                "project_id": "alpha",
                "freshness": "stale",
                "authority": "bounded_evidence",
                "stale": True,
            },
            {
                "candidate_id": "current-alpha",
                "lexical_score": 40.0,
                "project_id": "alpha",
                "freshness": "current",
                "authority": "bounded_evidence",
            },
        ]

        current_plan = plan_candidates(
            candidates,
            strategy=select_recall_strategy("current status for project alpha"),
            scope={"project_id": "alpha"},
            now="2026-06-15T00:00:00Z",
        )
        history_plan = plan_candidates(
            candidates,
            strategy=select_recall_strategy("history or disputed old alpha route"),
            scope={"project_id": "alpha"},
            now="2026-06-15T00:00:00Z",
        )

        self.assertEqual(current_plan["ranked_candidates"][0]["candidate_id"], "current-alpha")
        self.assertEqual(current_plan["diagnostics"]["prefilter_counts"]["wrong_scope"], 1)
        self.assertEqual(current_plan["diagnostics"]["soft_filter_counts"]["stale_currentness"], 1)
        self.assertEqual(current_plan["ranked_candidates"][0]["diagnostics"]["lexical_score"], 40.0)
        self.assertIn("freshness_score", current_plan["ranked_candidates"][0]["diagnostics"])

        history_ids = [item["candidate_id"] for item in history_plan["ranked_candidates"]]
        self.assertIn("stale-alpha", history_ids)
        stale = next(
            item for item in history_plan["ranked_candidates"] if item["candidate_id"] == "stale-alpha"
        )
        self.assertEqual(stale["authority"], "direction_with_ref")
        self.assertIn("history_or_dispute_allows_stale", stale["diagnostics"]["reason_codes"])

    def test_recall_strategy_controls_budget_filter_strictness_and_authority_floor(self) -> None:
        exact = select_recall_strategy("open source ref msg-42 exact wording")
        exploratory = select_recall_strategy("what do we know broadly about the old continuity thread?")
        dispute = select_recall_strategy("compare the stale disputed history from last month")

        self.assertEqual(exact["strategy"], "source_reopen")
        self.assertLess(exact["top_k"], exploratory["top_k"])
        self.assertEqual(exact["filter_strictness"], "strict")
        self.assertEqual(exact["authority_floor"], "reopenable_route")
        self.assertIn("source_ref_cue", exact["diagnostics"]["reasons"])

        self.assertEqual(exploratory["strategy"], "exploratory_recall")
        self.assertEqual(exploratory["filter_strictness"], "soft")
        self.assertEqual(exploratory["authority_floor"], "direction_with_ref")
        self.assertGreater(exploratory["fanout_budget"], exact["fanout_budget"])

        self.assertEqual(dispute["strategy"], "history_or_dispute")
        self.assertEqual(dispute["freshness_mode"], "history_friendly")
        self.assertFalse(dispute["hard_filters"]["stale"])

    def test_outcome_feedback_is_local_safe_and_reports_route_family_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recall-outcomes.jsonl"
            event = build_recall_outcome_event(
                raw_query="where is the jade memento? sk-test-public-fixture",
                run_id="run-1",
                route_family="fts_first",
                scoring_policy="freshness_current_first",
                delivered_candidates=[
                    {"route_id": "route-a", "source_ref_id": "src-1", "segment_id": "seg-1"}
                ],
                outcome_signal="source_reopen_success",
                selected_route_id="route-a",
                currentness="current",
            )
            write_recall_outcome_event(path, event)
            write_recall_outcome_event(
                path,
                build_recall_outcome_event(
                    raw_query="where is the jade memento?",
                    run_id="run-2",
                    route_family="fts_first",
                    scoring_policy="freshness_current_first",
                    delivered_candidates=[
                        {"route_id": "route-b", "source_ref_id": "src-2", "segment_id": "seg-2"}
                    ],
                    outcome_signal="wrong_route_drag",
                    selected_route_id="route-b",
                    currentness="stale",
                ),
            )
            report = recall_outcome_report(path)

        dumped_event = json.dumps(event, ensure_ascii=False)
        self.assertNotIn("jade memento", dumped_event)
        self.assertNotIn("sk-test-public-fixture", dumped_event)
        self.assertEqual(event["authority"], "retrieval_tuning_only_not_source_truth")
        self.assertEqual(report["total_events"], 2)
        self.assertEqual(report["by_route_family"]["fts_first"]["source_reopen_success"], 1)
        self.assertEqual(report["by_currentness"]["stale"]["wrong_route_drag"], 1)
        self.assertIn("query_shape", report["repeated_query_shapes"][0])
        self.assertEqual(report["surface_vs_help"]["route_surfaced_count"], 2)
        self.assertEqual(report["surface_vs_help"]["route_helped_user_count"], 1)
        self.assertEqual(report["surface_vs_help"]["route_hurt_or_noisy_count"], 1)
        self.assertEqual(report["surface_vs_help"]["help_rate"], 0.5)
        self.assertTrue(report["contract"]["surfaced_is_not_helped"])
        self.assertTrue(report["contract"]["feedback_does_not_mutate_source_truth"])

    def test_before_commitment_map_reuses_route_material_for_pull_and_nudge(self) -> None:
        surface_map = before_commitment_surface_map()
        fixture = build_before_commitment_fixture(
            {
                "route_id": "route-silent-constraint",
                "source_ref_id": "src-constraint",
                "segment_id": "seg-constraint",
                "authority": "reopenable_route",
                "currentness": "current",
                "route_family": "fts_first",
            }
        )
        silent = build_before_commitment_fixture(
            {
                "route_id": "route-stale",
                "source_ref_id": "src-stale",
                "segment_id": "seg-stale",
                "authority": "direction_only",
                "currentness": "stale",
                "route_family": "fts_first",
                "masked": True,
            }
        )

        self.assertIn("prompt_time_scent", surface_map["surfaces"])
        self.assertIn("before_final_claim_check", surface_map["surfaces"])
        self.assertEqual(surface_map["source_discussion"], "#836")
        self.assertEqual(
            surface_map["surfaces"]["before_final_claim_check"]["feedback_outcome_event"],
            "source_reopen_success",
        )

        self.assertEqual(
            fixture["pullable_ref_shelf"]["refs"][0]["route_id"],
            fixture["before_action_nudge"]["route_id"],
        )
        self.assertEqual(fixture["before_action_nudge"]["output_mode"], "tiny_nudge")
        self.assertEqual(fixture["before_answer_nudge"]["source_reopen_required"], True)
        self.assertNotIn("snippet", json.dumps(fixture, ensure_ascii=False))

        self.assertEqual(silent["negative_control"]["decision"], "silent")
        self.assertIn("masked_or_blocked", silent["negative_control"]["reason_codes"])

if __name__ == "__main__":
    unittest.main()
