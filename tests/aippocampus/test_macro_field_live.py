from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import macro_field_live  # noqa: E402


def route(handle: str, posture: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "handle": handle,
        "route_label": f"{handle} route",
        "route_topic": "issue_backlog_interpretation",
        "scope_bucket": "project:AIppocampus",
        "freshness": "current",
        "privacy_state": "public_safe",
        "posture_id": posture,
        "source_refs": [{"source_id": f"source:{handle}", "message_id": f"msg:{handle}"}],
    }
    row.update(overrides)
    return row


class MacroFieldLiveTests(unittest.TestCase):
    def test_recall_routes_feed_declared_edges_posture_lifts_and_timing_warnings(self) -> None:
        routes = [
            route(
                "r1",
                "seed_probe",
                declared_edges=[
                    {
                        "from_route_id": "r1",
                        "to_route_id": "r2",
                        "relation": "precondition",
                        "source_event_id": "event:shared",
                        "source_refs": [{"source_id": "source:declared", "message_id": "msg:declared"}],
                    }
                ],
            ),
            route("r2", "archivist_boundary"),
            route("gap", "seed_probe", scope_bucket="project:other"),
            route("r3", "seed_probe"),
            route("r4", "archivist_boundary"),
        ]

        report = macro_field_live.materialize_for_recall(
            query="r1 r2",
            routes=routes,
            foreground_outcomes=[{"outcome": "read_timeout"}, {"outcome": "source_miss"}],
            macro_transition_history=["乾", "坤", "乾", "坤", "乾"],
        )
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
        projection = report["foreground_projection"]  # type: ignore[index]

        self.assertEqual(report["kind"], "macro_field_live_recall_materialization")
        self.assertGreaterEqual(report["declared_edge_count"], 1)
        self.assertGreaterEqual(report["posture_policy_count"], 1)
        self.assertIn("timing_affordance_falsified", projection["warnings"])
        self.assertIn("source_reanchoring_required", projection["warnings"])
        self.assertIn("orbit_oscillation_warning", projection["warnings"])
        self.assertEqual(projection["claim_permission"], "none")
        self.assertNotIn("raw_private_source_text", encoded)
        self.assertNotIn("C:\\", encoded)

    def test_blocked_stale_and_missing_source_rows_do_not_emit_edges_or_policies(self) -> None:
        routes = [
            route("blocked", "seed_probe", privacy_state="blocked"),
            route("stale", "archivist_boundary", freshness="stale"),
            route("missing", "seed_probe", source_refs=[]),
            route("ok", "archivist_boundary"),
        ]

        sections = macro_field_live.sections_from_recall_routes(routes)
        declared = macro_field_live.declared_edges_from_recall_routes(routes, sections)
        policies = macro_field_live.posture_policies_from_recall_routes(routes)

        self.assertEqual(len(sections), 3)
        self.assertEqual(declared, [])
        self.assertEqual(policies, [])

    def test_live_materialization_can_merge_into_macro_projection_without_authority_upgrade(self) -> None:
        live = macro_field_live.materialize_for_recall(
            query="r1 r2",
            routes=[route("r1", "seed_probe"), route("r2", "archivist_boundary")],
        )
        merged = macro_field_live.merge_projection(
            {
                "kind": "macro_live_projection",
                "status": "current",
                "state": {"active_layer": "人"},
            },
            live,
        )

        self.assertIn("foreground_projection", merged)
        self.assertEqual(merged["macro_field_live"]["source_reopen_required_before_claim"], True)
        self.assertEqual(merged["foreground_projection"]["authority_level"], "direction_only")
        self.assertEqual(merged["foreground_projection"]["claim_permission"], "none")


if __name__ == "__main__":
    unittest.main()
