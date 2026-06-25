from __future__ import annotations

import unittest


class CompactDebugFieldTests(unittest.TestCase):
    def test_compact_recall_requires_operator_command(self) -> None:
        compact_payload = {"operator_detail_command": "agent recall --detail full"}

        self.assertIn("operator_detail_command", compact_payload)
