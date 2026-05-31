from __future__ import annotations

import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import export_bundle  # noqa: E402
from aippocampus_runtime.artifacts import export_bundle as packaged_export_bundle  # noqa: E402


class ExportBundleTests(unittest.TestCase):
    def test_top_level_script_is_compatibility_shim_for_package_owner(self) -> None:
        self.assertIs(export_bundle.write_handoff, packaged_export_bundle.write_handoff)
        self.assertIs(export_bundle.run_build_index, packaged_export_bundle.run_build_index)
        self.assertIs(export_bundle.main, packaged_export_bundle.main)

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

    def test_run_build_index_uses_package_api_without_subprocess(self) -> None:
        seen: dict[str, list[str]] = {}

        def fake_index_main(argv: list[str] | None = None) -> int:
            seen["argv"] = list(argv or [])
            print('{"message_count": 1, "anchor_count": 0, "graph": {"node_count": 0}}')
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(
                    packaged_export_bundle.index_builder,
                    "main",
                    side_effect=fake_index_main,
                ),
                patch("subprocess.run", side_effect=AssertionError("export should not spawn")),
                patch("sys.stdout", new=StringIO()) as stdout,
            ):
                result = packaged_export_bundle.run_build_index(
                    root,
                    root / "rollout.jsonl",
                    root / "index",
                    root / "thread-anchors.md",
                    hash_source=True,
                )

        self.assertEqual(result["message_count"], 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(
            seen["argv"],
            [
                "--cwd",
                str(root),
                "--rollout",
                str(root / "rollout.jsonl"),
                "--output-dir",
                str(root / "index"),
                "--anchors",
                str(root / "thread-anchors.md"),
                "--json",
                "--hash-source",
            ],
        )


if __name__ == "__main__":
    unittest.main()
