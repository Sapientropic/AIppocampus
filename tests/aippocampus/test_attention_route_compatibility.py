from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.navigation import (  # noqa: E402
    attention_hot_router,
    attention_route_projection,
    route_compatibility_diagnostics,
)
from aippocampus_runtime.recall import feedback_events  # noqa: E402


def _route(route_id: str, *, semantic_score: float, source_id: str) -> dict[str, object]:
    return {
        "route_id": route_id,
        "route_label": "issue 1544 compatibility source route",
        "route_topic": "compatibility source routing",
        "summary": "compatibility routing source-backed candidate",
        "currentness": "current",
        "source_refs": [{"source_id": source_id, "message_id": route_id, "line": 10}],
        "route_hints": {
            "semantic_warming": {
                "semantic_score": semantic_score,
                "semantic_aliases": ["compatibility", "routing"],
            }
        },
    }


class AttentionRouteCompatibilityTests(unittest.TestCase):
    def test_local_global_obstruction_is_visible_and_demotes_route(self) -> None:
        routes = [
            _route("steady_route", semantic_score=0.72, source_id="issue:#1544-a"),
            _route("obstructed_route", semantic_score=0.98, source_id="issue:#1544-b"),
        ]
        compatibility = [
            {
                "route_ids": ["obstructed_route", "steady_route"],
                "result": "obstruction",
                "reason_codes": ["source_supported_sections_need_scope_review"],
                "next_safe_action": "review_obstruction_before_action",
            }
        ]

        reordered, diagnostics = attention_route_projection.rerank_routes_with_attention_router(
            query="issue 1544 compatibility routing",
            routes=routes,
            max_routes=2,
            compatibility_diagnostics=compatibility,
        )
        encoded = json.dumps(diagnostics, ensure_ascii=False, sort_keys=True)

        self.assertEqual(reordered[0]["route_id"], "steady_route")
        self.assertEqual(diagnostics["compatibility_diagnostic_count"], 1)
        self.assertEqual(diagnostics["compatibility_affected_route_count"], 2)
        self.assertIn("source_supported_sections_need_scope_review", encoded)
        self.assertIn("local_global_compatibility", encoded)
        self.assertNotIn("source_refs", encoded)

    def test_compatibility_hint_cannot_override_hard_masks_or_claim_boundary(self) -> None:
        routes = [
            {
                **_route("masked_route", semantic_score=0.99, source_id="issue:#1544-c"),
                "hard_masks": ["privacy_domain"],
            }
        ]

        compatibility_by_route = route_compatibility_diagnostics.compatibility_by_route_id(
            routes,
            [
                {
                    "route_ids": ["masked_route"],
                    "result": "glued_route",
                    "reason_codes": ["source_scope_and_epoch_overlap"],
                    "next_safe_action": "deepen_compatible_route",
                }
            ],
        )
        token = attention_route_projection.attention_token_for_route(
            routes[0],
            index=0,
            compatibility=compatibility_by_route["masked_route"],
        )
        packet = attention_hot_router.route_attention(
            {
                "query": "issue 1544 compatibility routing",
                "query_terms": ["issue", "1544", "compatibility", "routing"],
                "scope": "project:AIppocampus",
                "risk": "low",
                "privacy_domain": "public",
            },
            [token],
        )[0]

        self.assertEqual(packet["output_mode"], "silence")
        self.assertEqual(packet["claim_permission"], "blocked")
        self.assertTrue(packet["contract"]["attention_score_is_not_evidence"])
        self.assertEqual(
            packet["route_hints"]["local_global_compatibility"]["claim_permission"],
            "no_claim_before_reopen",
        )

    def test_feedback_calibration_reranks_existing_routes_without_claim_upgrade(self) -> None:
        routes = [
            _route("stale_drag_route", semantic_score=0.72, source_id="issue:#1544-a"),
            _route("helpful_reopen_route", semantic_score=0.72, source_id="issue:#1544-b"),
        ]
        calibration = feedback_events.recall_feedback_calibration_report(
            [
                feedback_events.active_flow_event(
                    route_id="helpful_reopen_route",
                    route_kind="active_path",
                    signal="source_reopen_success",
                ),
                feedback_events.active_flow_event(
                    route_id="helpful_reopen_route",
                    route_kind="active_path",
                    signal="user_confirmed",
                ),
                feedback_events.active_flow_event(
                    route_id="stale_drag_route",
                    route_kind="active_path",
                    signal="wrong_route_drag",
                ),
                feedback_events.active_flow_event(
                    route_id="stale_drag_route",
                    route_kind="active_path",
                    signal="blocked",
                ),
            ]
        )

        reordered, diagnostics = attention_route_projection.rerank_routes_with_attention_router(
            query="issue 1544 compatibility routing",
            routes=routes,
            max_routes=2,
            feedback_calibration=calibration,
        )
        encoded = json.dumps(diagnostics, ensure_ascii=False, sort_keys=True)

        self.assertEqual(reordered[0]["route_id"], "helpful_reopen_route")
        self.assertEqual(diagnostics["feedback_calibration"]["matched_route_count"], 2)
        self.assertEqual(diagnostics["feedback_calibration"]["positive_delta_count"], 1)
        self.assertEqual(diagnostics["feedback_calibration"]["negative_delta_count"], 1)
        self.assertIn("feedback_calibration_lift", reordered[0]["_route_delta_reason_codes"])
        self.assertTrue(
            diagnostics["feedback_calibration"]["policy_boundary"][
                "source_reopen_required_for_claims"
            ]
        )
        self.assertIn("feedback_calibration_can_emit_source_open", encoded)
        self.assertNotIn("source_refs", encoded)
        self.assertNotIn("source_open_token_ids", encoded)
        self.assertNotIn('"claim_permission": "source_open"', encoded)

    def test_feedback_calibration_cannot_override_hard_masked_route(self) -> None:
        routes = [
            {
                **_route("masked_feedback_route", semantic_score=0.99, source_id="issue:#1544-d"),
                "hard_masks": ["privacy_domain"],
            }
        ]
        calibration = feedback_events.recall_feedback_calibration_report(
            [
                feedback_events.active_flow_event(
                    route_id="masked_feedback_route",
                    route_kind="active_path",
                    signal="source_reopen_success",
                ),
                feedback_events.active_flow_event(
                    route_id="masked_feedback_route",
                    route_kind="active_path",
                    signal="user_confirmed",
                ),
            ]
        )

        reordered, diagnostics = attention_route_projection.rerank_routes_with_attention_router(
            query="issue 1544 compatibility routing",
            routes=routes,
            max_routes=1,
            feedback_calibration=calibration,
        )

        self.assertEqual(reordered[0]["route_id"], "masked_feedback_route")
        self.assertFalse(diagnostics["applied"])
        self.assertEqual(diagnostics["feedback_calibration"]["matched_route_count"], 0)
        self.assertTrue(
            diagnostics["feedback_calibration"]["policy_boundary"][
                "clean_source_mutation_allowed"
            ]
            is False
        )


if __name__ == "__main__":
    unittest.main()
