from __future__ import annotations

import unittest

from tests.aippocampus.product_probe_helpers import assert_cli_recall_deepens_to_source


class RecallFollowthroughTests(unittest.TestCase):
    def test_recall_uses_product_probe_before_selector_claim(self) -> None:
        recall, deepen = assert_cli_recall_deepens_to_source(
            self,
            cue="quiet room",
            cwd=None,
            clean_source_dir=None,
            registry_dir=None,
            last_recall_path=None,
            expectation=None,
        )

        self.assertIn("recall_selector_id", recall)
        self.assertIn("source_window", deepen["result"])
