from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_TOOLS = REPO_ROOT / "tools" / "aippocampus" / "docs"
sys.path.insert(0, str(DOC_TOOLS))

from discussion_atlas_guard import (  # noqa: E402
    discussion_atlas_drift_report,
    discussion_atlas_navigation_pointer,
    discussion_atlas_static_issues,
    parse_discussion_atlas_rows,
)


class DiscussionAtlasGuardTests(unittest.TestCase):
    def test_current_atlas_has_parseable_rows(self) -> None:
        atlas = REPO_ROOT / "docs" / "research" / "discussion-atlas.md"
        rows = parse_discussion_atlas_rows(atlas.read_text(encoding="utf-8"))

        self.assertGreaterEqual(len(rows), 30)
        self.assertIn(519, rows)
        self.assertIn(2127, rows)
        self.assertEqual(discussion_atlas_static_issues(REPO_ROOT), [])

    def test_discussion_2127_has_compact_navigation_pointer(self) -> None:
        atlas = REPO_ROOT / "docs" / "research" / "discussion-atlas.md"

        pointer = discussion_atlas_navigation_pointer(
            atlas.read_text(encoding="utf-8"),
            "discussion 2127 source-backed conversation",
        )
        encoded = str(pointer)

        self.assertTrue(pointer["ok"], encoded)
        self.assertEqual(pointer["pointer"]["discussion"], 2127)
        self.assertEqual(
            pointer["pointer"]["url"],
            "https://github.com/Sapientropic/AIppocampus/discussions/2127",
        )
        self.assertIn("Moving Ground", pointer["pointer"]["title"])
        self.assertIn("next_action", pointer["pointer"])
        self.assertNotIn("A safe packet that leaves the agent lost", encoded)

    def test_drift_report_catches_missing_and_stale_pointer_cases(self) -> None:
        atlas_text = """
| Discussion | Layer | Status | Owner | Execution / evidence | Next action | Cannot claim |
| --- | --- | --- | --- | --- | --- | --- |
| [#10 Alpha](https://github.com/Sapientropic/AIppocampus/discussions/10) | route_attention | active_design | owner_missing | none | Keep pointer. | none |
| [#11 Beta](https://github.com/Sapientropic/AIppocampus/discussions/11) | source_ground | research_seed | [doc](doc.md) | #100 | Keep pointer. | none |
| [#12 Gamma](https://github.com/Sapientropic/AIppocampus/discussions/12) | source_ground | implemented_slice | [doc](doc.md) | closed #101 | Keep pointer. | none |
"""
        discussions = [
            {
                "number": 10,
                "title": "Alpha",
                "expected_status": "current_contract",
                "requires_execution_issue": True,
            },
            {"number": 12, "title": "Gamma", "closed_execution_needs_successor": True},
            {"number": 99, "title": "New discussion"},
        ]

        report = discussion_atlas_drift_report(atlas_text, discussions)
        codes = {finding["code"] for finding in report["findings"]}

        self.assertFalse(report["ok"])
        self.assertIn("missing_row", codes)
        self.assertIn("status_maybe_stale", codes)
        self.assertIn("owner_missing", codes)
        self.assertIn("execution_issue_missing", codes)
        self.assertIn("successor_missing", codes)
        missing = next(finding for finding in report["findings"] if finding["code"] == "missing_row")
        self.assertEqual(missing["owner"], "discussion_atlas_guard")
        self.assertIn("compact atlas row", missing["next_action"])
        self.assertFalse(report["public_boundary"]["discussion_bodies_serialized"])

    def test_transit_report_separates_category_issue_state_and_comment_review(self) -> None:
        atlas_text = """
Last checked: 2026-06-16 through GitHub GraphQL; 2 discussions found.

| Discussion | Layer | Status | Owner | Execution / evidence | Next action | Cannot claim |
| --- | --- | --- | --- | --- | --- | --- |
| [#20 Category](https://github.com/Sapientropic/AIppocampus/discussions/20) | source_ground | active_design | [doc](doc.md) | #200 | Keep pointer. | none |
| [#21 Closed](https://github.com/Sapientropic/AIppocampus/discussions/21) | learning_loop | implemented_slice | [doc](doc.md) | #201 | Continue slice. | none |
"""
        discussions = [
            {
                "number": 20,
                "title": "Category",
                "github_category": "Ideas",
                "updatedAt": "2026-06-16T10:00:00Z",
                "latestCommentAt": "2026-06-17T10:00:00Z",
                "latestCommentUrl": "https://github.example/comment/20",
            },
            {
                "number": 21,
                "title": "Closed",
                "github_category": "Q&A",
                "updatedAt": "2026-06-16T10:00:00Z",
            },
        ]

        report = discussion_atlas_drift_report(
            atlas_text,
            discussions,
            issue_state_by_number={
                200: {"state": "open"},
                201: {"state": "closed"},
            },
        )
        codes = {finding["code"] for finding in report["findings"]}

        self.assertFalse(report["ok"])
        self.assertEqual(report["live_check_depth"], "comment_pointer_review")
        self.assertTrue(report["issue_state_transit_checked"])
        self.assertTrue(report["comment_pointer_review_checked"])
        self.assertTrue(report["github_category_distinct_from_atlas_layer"])
        self.assertIn("comment_review_needed", codes)
        self.assertIn("successor_missing", codes)
        self.assertNotIn("status_maybe_stale", codes)
        encoded = str(report)
        self.assertIn("https://github.example/comment/20", encoded)
        self.assertNotIn("comment body should never appear", encoded)

    def test_active_design_without_execution_path_reports_gap(self) -> None:
        atlas_text = """
| Discussion | Layer | Status | Owner | Execution / evidence | Next action | Cannot claim |
| --- | --- | --- | --- | --- | --- | --- |
| [#30 Gap](https://github.com/Sapientropic/AIppocampus/discussions/30) | source_ground | active_design | owner_missing | none | Keep alive. | none |
"""

        report = discussion_atlas_drift_report(
            atlas_text,
            [{"number": 30, "title": "Gap", "github_category": "Ideas"}],
            issue_state_by_number={},
        )
        codes = {finding["code"] for finding in report["findings"]}

        self.assertIn("active_design_execution_gap", codes)


if __name__ == "__main__":
    unittest.main()
