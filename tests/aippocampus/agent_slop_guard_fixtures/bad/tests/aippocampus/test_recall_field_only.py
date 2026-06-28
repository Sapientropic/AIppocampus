from __future__ import annotations

import unittest


class RecallFieldOnlyTests(unittest.TestCase):
    def test_reopenable_route_field_is_not_a_product_probe(self) -> None:
        payload = {
            "status": "ok",
            "foreground_action": {"tool_name": "agent_deepen"},
            "routes": [{"actionability": "low_confidence_reopenable"}],
            "source_anchor_gate": {"opened_anchor_hits": 2},
        }

        self.assertEqual(payload["foreground_action"]["tool_name"], "agent_deepen")
        self.assertEqual(payload["routes"][0]["actionability"], "low_confidence_reopenable")
        self.assertEqual(payload["source_anchor_gate"]["opened_anchor_hits"], 2)
