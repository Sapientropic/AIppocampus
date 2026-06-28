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

    def test_recall_fragmentation_inventory_names_owner_subpackages(self) -> None:
        inventory = recall_owner_guard.recall_fragmentation_inventory(REPO_ROOT)

        self.assertEqual(inventory["issues"], [])
        self.assertTrue(inventory["new_flat_files_rejected_by_default"])
        self.assertGreater(inventory["sealed_legacy_flat_count"], 100)
        semantic = next(
            family
            for family in inventory["owner_families"]
            if family["owner"] == "Semantic"
        )
        self.assertIn("semantic/confidence_policy.py", semantic["owner_package_files"])
        self.assertNotIn("confidence_policy.py", semantic["flat_files"])

    def test_feedback_owner_package_removed_flat_import_compatibility(self) -> None:
        new_events = import_module("aippocampus_runtime.recall.feedback.events")
        new_apw = import_module("aippocampus_runtime.recall.feedback.associative_path")

        self.assertTrue(callable(new_events.active_flow_event))
        self.assertTrue(callable(new_apw.build_followthrough_event))
        with self.assertRaises(ModuleNotFoundError):
            import_module("aippocampus_runtime.recall.feedback_events")
        with self.assertRaises(ModuleNotFoundError):
            import_module("aippocampus_runtime.recall.associative_path_feedback")

    def _write_owner_map(
        self,
        repo: Path,
        *,
        legacy_modules: set[str],
        current_modules: set[str] | None = None,
        extra_lines: list[str] | None = None,
    ) -> None:
        listed_modules = legacy_modules if current_modules is None else current_modules
        owner_map = repo / "docs" / "architecture" / "recall" / "owner-map.md"
        owner_map.parent.mkdir(parents=True)
        owner_map.write_text(
            "\n".join(
                [
                    "# Recall Owner Map",
                    "",
                    *sorted(recall_owner_guard.REQUIRED_OWNER_HEADINGS),
                    "",
                    "Legacy flat inventory seal:",
                    "",
                    f"- sealed_count: {len(legacy_modules)}",
                    f"- sealed_sha256: {recall_owner_guard._flat_inventory_hash(legacy_modules)}",
                    "",
                    "## Flat File Exceptions",
                    "",
                    "| File | Kind | Owner | Removal condition | Default import guidance |",
                    "| --- | --- | --- | --- | --- |",
                    *(extra_lines or []),
                    "",
                    "Current flat files:",
                    "",
                    *(f"- `{name}`" for name in sorted(listed_modules)),
                    "",
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

    def test_new_flat_recall_module_is_rejected_even_if_added_to_owner_map(self) -> None:
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
            self._write_owner_map(
                repo,
                legacy_modules={"known_surface.py"},
                current_modules={"known_surface.py", "new_flat_surface.py"},
            )

            issues = recall_owner_guard.recall_owner_map_issues(repo)

        self.assertIn(
            "recall owner map legacy flat inventory changed; "
            "new recall files must use owner subpackages or explicit flat exception metadata",
            issues,
        )

    def test_new_owner_subpackage_file_passes_without_flat_exception(self) -> None:
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
            owner_dir = recall_dir / "search"
            owner_dir.mkdir()
            (owner_dir / "new_surface.py").write_text("", encoding="utf-8")
            self._write_owner_map(repo, legacy_modules={"known_surface.py"})

            issues = recall_owner_guard.recall_owner_map_issues(repo)

        self.assertEqual([], issues)

    def test_flat_exception_requires_owner_removal_and_default_import_metadata(self) -> None:
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
            (recall_dir / "compat_bridge.py").write_text("", encoding="utf-8")
            self._write_owner_map(
                repo,
                legacy_modules={"known_surface.py"},
                extra_lines=[
                    "| `compat_bridge.py` | temporary_compatibility_wrapper | feedback | - | import feedback.capture |"
                ],
            )

            issues = recall_owner_guard.recall_owner_map_issues(repo)

        self.assertIn(
            "flat recall exception missing removal condition metadata: compat_bridge.py",
            issues,
        )

    def test_flat_entrypoint_exception_with_metadata_passes(self) -> None:
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
            (recall_dir / "entrypoint_bridge.py").write_text("", encoding="utf-8")
            self._write_owner_map(
                repo,
                legacy_modules={"known_surface.py"},
                extra_lines=[
                    "| `entrypoint_bridge.py` | entrypoint | foreground projection | keep while public CLI imports it | import recall.foreground.entrypoint |"
                ],
            )

            issues = recall_owner_guard.recall_owner_map_issues(repo)

        self.assertEqual([], issues)


if __name__ == "__main__":
    unittest.main()
