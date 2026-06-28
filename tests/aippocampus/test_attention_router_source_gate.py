from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime.recall import (
    agent_continuity,
    agent_recall_pipeline,
)
from aippocampus_runtime.recall.source_open import source_anchor_gate_routing


class AttentionRouterSourceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.clean = self.cwd / ".aippocampus" / "clean-source"
        self.clean.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_attention_router_rolls_back_promoted_top_after_source_gate_blocks(self) -> None:
        fake_packet = {
            "kind": "aippocampus_recall_context",
            "status": "ok",
            "routes": [
                {
                    "route_id": "route_generic",
                    "kind": "source_ref",
                    "handle": "handle:generic",
                    "route_label": "python typo source route",
                    "route_topic": "python typo",
                    "source_refs": [{"source_id": "src_generic", "message_id": "msg_generic"}],
                },
                {
                    "route_id": "route_attention",
                    "kind": "source_ref",
                    "handle": "handle:attention",
                    "route_label": "attention router score fusion route",
                    "route_topic": "attention_router",
                    "source_refs": [
                        {"source_id": "src_attention", "message_id": "msg_attention"}
                    ],
                },
            ],
        }
        passed_auto_gate = {
            "surface": "explicit_agent_recall",
            "gate_ok": True,
            "public_quality_gate_ok": True,
            "default_adoption_gate_ok": True,
            "promotion_decision": "promoted",
            "blockers": [],
            "metrics": {},
        }

        def gate_for_top_route(**kwargs: object) -> dict[str, object]:
            raw_routes = kwargs.get("routes")
            top_route = raw_routes[0] if isinstance(raw_routes, list) and raw_routes else {}
            top_route_id = str(top_route.get("route_id") if isinstance(top_route, dict) else "")
            if top_route_id == "route_attention":
                return {
                    "status": "blocked",
                    "reason": "top_route_source_not_reopenable",
                    "opened_anchor_hits": 0,
                    "required_anchor_hits": 2,
                    "target_source_matched": False,
                }
            return {
                "status": "passed",
                "reason": "opened_source_anchor_coverage",
                "opened_anchor_hits": 3,
                "required_anchor_hits": 2,
                "target_source_matched": True,
            }

        for mode in ("on", "auto"):
            with self.subTest(mode=mode):
                with (
                    patch.object(
                        agent_recall_pipeline,
                        "recall_context_packet",
                        return_value=fake_packet,
                    ),
                    patch.object(
                        agent_recall_pipeline.attention_router_policy,
                        "explicit_recall_auto_gate",
                        return_value=passed_auto_gate,
                    ),
                    patch.object(
                        source_anchor_gate_routing.recall_source_anchor_gate,
                        "top_route_source_anchor_gate",
                        side_effect=gate_for_top_route,
                    ),
                ):
                    report = agent_continuity.recall(
                        "attention router score fusion route selection",
                        cwd=self.cwd,
                        clean_source_dir=self.clean,
                        max_routes=2,
                        attention_router=mode,
                    )

                navigation = report["attention_router_navigation"]
                self.assertEqual(report["memory_packets"][0]["route_id"], "route_generic")
                self.assertEqual(report["source_anchor_gate"]["status"], "passed")
                self.assertFalse(navigation["top_route_changed"])
                self.assertTrue(navigation["post_source_anchor_rollback_applied"])
                self.assertTrue(navigation["router_top_changed_to_blocked_route"])
                self.assertEqual(navigation["demoted_router_route_id"], "route_attention")
                self.assertEqual(
                    report["metrics"]["attention_router_top_changed_to_blocked_route_count"],
                    1,
                )


if __name__ == "__main__":
    unittest.main()
