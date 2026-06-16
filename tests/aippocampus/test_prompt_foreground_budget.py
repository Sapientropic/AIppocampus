from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.hooks import prompt as hook  # noqa: E402
from aippocampus_runtime.recall import prompt_foreground_budget as budget  # noqa: E402


class PromptForegroundBudgetTests(unittest.TestCase):
    def test_direction_only_weak_scent_foreground_stays_compact_with_debug_metrics(self) -> None:
        result = {
            "decision": "scent",
            "score": 0.72,
            "confidence": "medium",
            "query_terms": ["hook", "field", "budget"],
            "concept_expansions": [],
            "candidates": [
                {
                    "title": "AIppocampus hook field budget",
                    "anchors": ["prompt hook foreground projection"],
                    "matched_terms": ["hook", "field budget"],
                },
                {
                    "title": "Source court boundary",
                    "anchors": ["source court escalation"],
                    "matched_terms": ["source court"],
                },
                {
                    "title": "Bounded summary route",
                    "anchors": ["bounded-summary theme"],
                    "matched_terms": ["bounded summary"],
                },
            ],
            "evidence": [],
            "working_memory": [],
            "cognitive_map": [],
            "ambient_recall": {
                "mode": "scent",
                "confidence": "medium",
                "cache_status": {"status": "hit", "card_count": 3},
                "cards": [
                    {
                        "theme": "AIppocampus hook field budget",
                        "support_level": "scent",
                        "trust_level": "direction_only",
                        "action_grammar": "direction_only",
                        "visibility": "active_gentle_nudge",
                        "provenance_class": "cached_warm_card",
                        "suggested_use": "Use as route context only.",
                    },
                    {
                        "theme": "Source court boundary",
                        "support_level": "scent",
                        "trust_level": "direction_only",
                        "action_grammar": "direction_only",
                        "visibility": "active_gentle_nudge",
                        "provenance_class": "warm_scout_proposal",
                        "suggested_use": "Reopen source for claims.",
                    },
                    {
                        "theme": "Bounded summary route",
                        "support_level": "scent",
                        "trust_level": "direction_only",
                        "action_grammar": "direction_only",
                        "visibility": "active_gentle_nudge",
                        "provenance_class": "cognitive_map_route",
                        "suggested_use": "Orient only.",
                    },
                ],
            },
            "route_delivery_diagnostic": {
                "foreground_profile": "ambient_hot_path",
                "hot_path_candidates_after_merge": 3,
                "final_candidate_count": 3,
                "cold_semantic_shadowed": False,
            },
            "reasons": [
                "current prompt is about AIppocampus hook field budget",
                "weak direction_only scent",
            ],
            "elapsed_ms": 12.3,
        }

        context = hook.context_for_hook(result) or ""
        public = hook.public_hook_debug_payload(result)

        self.assertLessEqual(len(context), 650)
        self.assertLessEqual(context.count("\n") + 1, 9)
        self.assertIn("AIppocampus: prior context may matter.", context)
        self.assertIn("Next: call agent_recall with this cue before broad search.", context)
        self.assertIn("Use as route only; reopen source before quoting or making strong claims.", context)
        self.assertIn("routes:", context)
        self.assertNotIn("action: direction_only", context)
        self.assertNotIn("must_reopen_for", context)
        self.assertNotIn("Ambient recall private context", context)
        self.assertNotIn("bounded_evidence within scope", context)
        self.assertNotIn("source_open", context)
        self.assertNotIn("source-generation", context)
        self.assertEqual(public["ambient_recall"]["action_grammar_counts"]["direction_only"], 3)
        self.assertEqual(public["foreground_context"]["foreground_context_chars"], len(context))
        self.assertLessEqual(public["foreground_context"]["foreground_context_line_count"], 9)
        self.assertEqual(public["foreground_context"]["direction_only_actionable_route_count"], 3)
        self.assertEqual(public["foreground_context"]["weak_scent_payload_budget_violation_count"], 0)
        self.assertEqual(public["foreground_context"]["debug_only_field_leak_count"], 0)
        self.assertTrue(public["foreground_context"]["observatory_debug_payload_available"])

    def test_cognitive_map_direction_only_scent_uses_compact_foreground(self) -> None:
        result = {
            "decision": "scent",
            "score": 0.74,
            "confidence": "medium",
            "query_terms": ["hook", "field", "budget"],
            "concept_expansions": [],
            "candidates": [],
            "evidence": [],
            "working_memory": [],
            "cognitive_map": [
                {
                    "title": "AIppocampus hook field budget",
                    "landmark_labels": ["hook foreground projection"],
                    "matched_cues": ["hook", "field budget"],
                    "thread_keys": ["session:redacted"],
                },
                {
                    "title": "Source-court route guidance",
                    "landmark_labels": ["source court boundary"],
                    "matched_cues": ["source court"],
                    "thread_keys": ["session:redacted"],
                },
            ],
            "ambient_recall": {
                "mode": "scent",
                "confidence": "medium",
                "cache_status": {"status": "hit", "card_count": 2},
                "cards": [
                    {
                        "theme": "AIppocampus hook field budget",
                        "support_level": "scent",
                        "trust_level": "direction_only",
                        "action_grammar": "direction_only",
                        "visibility": "active_gentle_nudge",
                        "provenance_class": "cognitive_map_route",
                        "suggested_use": "Orient only.",
                    },
                    {
                        "theme": "Source-court route guidance",
                        "support_level": "scent",
                        "trust_level": "direction_only",
                        "action_grammar": "direction_only",
                        "visibility": "active_gentle_nudge",
                        "provenance_class": "cognitive_map_route",
                        "suggested_use": "Reopen before claims.",
                    },
                ],
            },
            "reasons": [
                "cognitive map route: hook foreground projection",
                "weak direction_only scent",
            ],
            "elapsed_ms": 14.2,
        }

        context = hook.context_for_hook(result) or ""
        public = hook.public_hook_debug_payload(result)

        self.assertLessEqual(len(context), 650)
        self.assertLessEqual(context.count("\n") + 1, 9)
        self.assertIn("AIppocampus: prior context may matter.", context)
        self.assertIn("AIppocampus hook field budget", context)
        self.assertIn("Source-court route guidance", context)
        self.assertIn("Use as route only", context)
        self.assertNotIn("action: direction_only", context)
        self.assertNotIn("Cognitive map routes", context)
        self.assertNotIn("Ambient recall private context", context)
        self.assertNotIn("bounded_evidence within scope", context)
        self.assertEqual(public["foreground_context"]["direction_only_boilerplate_chars"], 0)
        self.assertEqual(public["foreground_context"]["weak_scent_payload_budget_violation_count"], 0)
        self.assertEqual(
            public["foreground_context"]["direction_only_foreground_budget_violation_count"],
            0,
        )

    def test_semantic_route_foreground_uses_product_cue_without_taxonomy_dump(self) -> None:
        result = {
            "decision": "scent",
            "score": 0.81,
            "confidence": "medium",
            "query_terms": ["plugin", "frontstage"],
            "concept_expansions": [],
            "candidates": [
                {
                    "title": "AIppocampus plugin frontstage UX",
                    "anchors": ["prompt-hook foreground projection"],
                    "matched_terms": ["plugin", "frontstage"],
                }
            ],
            "evidence": [],
            "working_memory": [],
            "cognitive_map": [],
            "semantic_gate": {
                "available": True,
                "decision": "scent",
                "confidence": 0.84,
                "query_aliases": ["plugin UX", "foreground projection"],
                "memory_scope": ["registered_threads"],
            },
            "semantic_bridge_diagnostic": "semantic_evidence_without_source_bridge",
            "route_delivery_diagnostic": {
                "foreground_profile": "explicit_recall",
                "final_candidate_count": 1,
                "evidence_count": 0,
                "semantic_source_reopen_route": False,
            },
            "reasons": ["semantic gate: scent confidence=0.84 aliases=plugin UX"],
            "elapsed_ms": 18.4,
        }

        context = hook.context_for_hook(result) or ""

        self.assertLessEqual(len(context), 650)
        self.assertIn("AIppocampus: prior context may matter.", context)
        self.assertIn("Next: call agent_recall with this cue before broad search.", context)
        self.assertIn("Use as route only; reopen source before quoting or making strong claims.", context)
        for marker in (
            "bounded_evidence",
            "source_open",
            "direction_with_ref",
            "source court",
            "action grammar",
            "Semantic recall route",
        ):
            self.assertNotIn(marker, context)

    def test_source_required_fresh_packet_still_uses_compact_product_foreground(self) -> None:
        result = {
            "decision": "scent",
            "score": 0.86,
            "confidence": "medium",
            "query_terms": ["small", "hippocampus", "test"],
            "concept_expansions": [],
            "candidates": [
                {
                    "title": "Small hippocampus smoke route",
                    "anchors": ["test failed first"],
                    "matched_terms": ["small hippocampus test"],
                }
            ],
            "evidence": [],
            "working_memory": [],
            "cognitive_map": [],
            "semantic_gate": {
                "available": True,
                "decision": "evidence",
                "confidence": 0.92,
                "query_aliases": ["small hippocampus test"],
                "memory_scope": ["registered_threads"],
            },
            "semantic_source_reopen_route": True,
            "ambient_recall": {
                "mode": "active_gentle_nudge",
                "cards": [
                    {
                        "theme": "Small hippocampus smoke route",
                        "support_level": "scent",
                        "trust_level": "direction_only",
                        "action_grammar": "direction_only",
                        "visibility": "active_gentle_nudge",
                    }
                ],
                "fresh_thread_packet": {
                    "support_level": "source_required",
                    "action_grammar": "reopenable_route",
                    "reopen_plan": {"status": "ready"},
                },
            },
            "reasons": ["semantic gate: evidence confidence=0.92 aliases=small hippocampus test"],
        }

        context = hook.context_for_hook(result) or ""

        self.assertLessEqual(len(context), 650)
        self.assertIn("AIppocampus: prior context may matter.", context)
        self.assertIn(
            "Next: call agent_deepen when a handle is present; otherwise call agent_recall first.",
            context,
        )
        self.assertIn("Small hippocampus smoke route", context)
        for marker in (
            "source_required",
            "reopenable_route",
            "bounded_evidence",
            "source_open",
            "action grammar",
            "Source-required recall route",
        ):
            self.assertNotIn(marker, context)

    def test_memory_packet_budget_keeps_foreground_useful_without_profile_dump(self) -> None:
        report = budget.build_foreground_memory_budget_fixture_report()
        packets = report["foreground_packets"]
        by_id = {packet["route_id"]: packet for packet in packets}
        encoded = str(packets)

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["metrics"]["foreground_hint_count"], 4)
        self.assertEqual(report["metrics"]["foreground_packet_budget_violation_count"], 0)
        self.assertEqual(report["metrics"]["false_personalization_count"], 0)
        self.assertEqual(report["metrics"]["profile_like_suppressed_count"], 1)
        self.assertEqual(report["metrics"]["debug_or_source_field_leak_count"], 0)
        self.assertNotIn("PRIVATE_PROFILE_SENTINEL", encoded)
        self.assertNotIn("source_handles", encoded)
        self.assertNotIn("src_private", encoded)

        self.assertEqual(by_id["route_tiny_orientation"]["next_action"], "use_hint")
        self.assertEqual(by_id["route_bounded_summary"]["output_mode"], "bounded_summary_as_route")
        self.assertEqual(by_id["route_bounded_summary"]["next_action"], "use_hint")
        self.assertEqual(report["metrics"]["unnecessary_reopen_prevented_count"], 1)
        self.assertEqual(by_id["route_reopenable"]["next_action"], "reopen_source")
        self.assertEqual(report["metrics"]["cognitive_load_budget_violation_count"], 0)
        self.assertEqual(report["cognitive_load"]["primary_action_count"], 1)
        self.assertLessEqual(report["cognitive_load"]["secondary_action_count"], 2)
        self.assertLessEqual(report["cognitive_load"]["action_vocabulary_count"], 3)
        self.assertFalse(report["cognitive_load"]["requires_audit_read_to_act"])
        self.assertTrue(report["cognitive_load"]["human_readable_action_present"])

        review = by_id["route_profile_like"]
        self.assertTrue(review["review_needed"])
        self.assertEqual(review["next_action"], "ask_light_question")
        self.assertEqual(review["suppression_reason"], "profile_like_detail")
        self.assertIn("default_hook_adoption", report["cannot_claim"])

    def test_memory_packet_budget_honors_recent_dismissal_anti_nag(self) -> None:
        packets = budget.foreground_memory_budget_fixture_packets()
        report = budget.project_memory_packets_for_foreground(
            packets,
            dismissed_route_ids={"route_recently_dismissed", "route_tiny_orientation"},
        )
        route_ids = {packet["route_id"] for packet in report["foreground_packets"]}

        self.assertTrue(report["ok"], report)
        self.assertNotIn("route_recently_dismissed", route_ids)
        self.assertNotIn("route_tiny_orientation", route_ids)
        self.assertEqual(report["metrics"]["anti_nag_suppressed_count"], 2)
        self.assertEqual(report["metrics"]["anti_nag_violation_count"], 0)
        self.assertEqual(report["red_lines"]["anti_nag_violation_count"], 0)

    def test_memory_packet_budget_reports_cognitive_load_violations_by_concept(self) -> None:
        packets = [
            {
                "kind": "aippocampus_memory_packet",
                "schema_version": "agent-native-recall-facade-v0",
                "route_id": f"route_noise_{index}",
                "output_mode": "reopenable_route",
                "display_hint": "A route may matter.",
                "claim_permission": "no_claim_before_reopen",
                "next_action": next_action,
                "deepen_route_id": f"deepen:route_noise_{index}",
                "risk_flags": ["stale", "private", "diagnostic"],
                "triage_rank_reason_codes": ["debug_probe", "operator_detail"],
            }
            for index, next_action in enumerate(
                [
                    "reopen_source",
                    "ask_light_question",
                    "run_diagnostic",
                    "manual_search",
                ],
                start=1,
            )
        ]

        report = budget.project_memory_packets_for_foreground(packets, max_hints=4)

        self.assertFalse(report["ok"], report)
        self.assertGreater(report["metrics"]["cognitive_load_budget_violation_count"], 0)
        self.assertGreater(report["cognitive_load"]["action_vocabulary_count"], 3)
        self.assertGreater(report["cognitive_load"]["secondary_action_count"], 2)
        self.assertIn("too_many_action_vocabularies", report["cognitive_load"]["violations"])
        self.assertIn("too_many_secondary_actions", report["cognitive_load"]["violations"])


if __name__ == "__main__":
    unittest.main()
