from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.ops.capture_consolidation_boundary import (  # noqa: E402
    STATUS_ORDER,
    capture_consolidation_readout,
    fixture_capture_consolidation_readout,
)


class CaptureConsolidationBoundaryTests(unittest.TestCase):
    def test_fixture_shows_full_no_write_state_flow_without_private_text(self) -> None:
        report = fixture_capture_consolidation_readout()

        self.assertTrue(report["ok"])
        self.assertTrue(report["no_write"])
        self.assertEqual([item["status"] for item in report["items"]], list(STATUS_ORDER))
        self.assertFalse(report["privacy_boundary"]["raw_text_serialized"])
        self.assertNotIn("private text", json.dumps(report, ensure_ascii=False))
        self.assertTrue(report["contract"]["edge_capture_local_first"])
        self.assertTrue(report["contract"]["consolidation_is_async"])

    def test_source_reopenable_requires_source_refs(self) -> None:
        report = capture_consolidation_readout(
            [
                {
                    "item_id": "claimed-reopenable",
                    "source_reopenable": True,
                    "sidecars_ready": True,
                    "source_refs": [],
                }
            ]
        )

        self.assertEqual(report["items"][0]["status"], "consolidated_sidecars_ready")
        self.assertEqual(report["metrics"]["source_reopenable_count"], 0)


if __name__ == "__main__":
    unittest.main()
