from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import export_bundle  # noqa: E402


class ExportBundleTests(unittest.TestCase):
    def test_handoff_points_search_to_extracted_index_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            handoff = Path(tmp) / "handoff.md"

            export_bundle.write_handoff(
                handoff,
                {
                    "created_at": "2026-05-30T00:00:00Z",
                    "cwd": "source-device",
                    "message_count": 1,
                    "anchor_count": 0,
                    "graph": {"node_count": 0},
                },
                include_raw=False,
            )

            text = handoff.read_text(encoding="utf-8")
            self.assertIn("<extracted>\\index\\source_index.sqlite", text)
            self.assertIn("resolves the version pointer", text)


if __name__ == "__main__":
    unittest.main()
