from __future__ import annotations

import unittest


class RecallFieldOnlyTests(unittest.TestCase):
    def test_recall_selector_field_is_not_a_product_probe(self) -> None:
        payload = {
            "status": "ok",
            "recall_selector_id": "sel_123",
            "route_count": 1,
        }

        self.assertIn("recall_selector_id", payload)
        self.assertGreater(payload["route_count"], 0)
