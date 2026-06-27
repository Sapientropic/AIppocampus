from __future__ import annotations

import tempfile
import unittest
from importlib import import_module
from pathlib import Path

from tests.aippocampus.import_path_helpers import import_doc_tool_module

REPO_ROOT = Path(__file__).resolve().parents[2]

recall_owner_guard = import_doc_tool_module("recall_owner_guard")


class RecallOwnerGuardTests(unittest.TestCase):
    def test_current_repo_recall_flat_modules_are_classified(self) -> None:
        issues = recall_owner_guard.recall_owner_map_issues(REPO_ROOT)

        self.assertEqual([], issues)

    def test_feedback_owner_package_removed_flat_import_compatibility(self) -> None:
        new_events = import_module("aippocampus_runtime.recall.feedback.events")
        new_apw = import_module("aippocampus_runtime.recall.feedback.associative_path")

        self.assertTrue(callable(new_events.active_flow_event))
        self.assertTrue(callable(new_apw.build_followthrough_event))
        with self.assertRaises(ModuleNotFoundError):
            import_module("aippocampus_runtime.recall.feedback_events")
        with self.assertRaises(ModuleNotFoundError):
            import_module("aippocampus_runtime.recall.associative_path_feedback")

    def test_new_flat_recall_module_requires_owner_map_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            recall_dir = (
                repo
                / "skills"
                / "aippocampus"
                / "scripts"
                / "aippocampus_runtime"
                / "recall"
            )
            recall_dir.mkdir(parents=True)
            (recall_dir / "known_surface.py").write_text("", encoding="utf-8")
            (recall_dir / "new_flat_surface.py").write_text("", encoding="utf-8")
            owner_map = repo / "docs" / "architecture" / "recall" / "owner-map.md"
            owner_map.parent.mkdir(parents=True)
            owner_map.write_text(
                "\n".join(
                    [
                        "# Recall Owner Map",
                        "",
                        *sorted(recall_owner_guard.REQUIRED_OWNER_HEADINGS),
                        "",
                        "`known_surface.py`",
                        "`feedback/__init__.py`",
                        "`feedback/associative_path.py`",
                        "`feedback/capture.py`",
                        "`feedback/events.py`",
                        "`feedback/outcome.py`",
                        "No flat compatibility wrappers",
                    ]
                ),
                encoding="utf-8",
            )

            issues = recall_owner_guard.recall_owner_map_issues(repo)

        self.assertIn(
            "flat recall module missing owner classification in "
            "docs/architecture/recall/owner-map.md: new_flat_surface.py",
            issues,
        )


if __name__ == "__main__":
    unittest.main()
