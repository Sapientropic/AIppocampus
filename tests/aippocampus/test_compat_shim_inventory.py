from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools" / "aippocampus" / "docs"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import compat_shim_inventory as inventory  # noqa: E402


def write_fixture_script(repo_root: Path, script_name: str, source: str) -> None:
    scripts_dir = repo_root / "skills" / "aippocampus" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    path = scripts_dir / script_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


class CompatibilityShimInventoryTests(unittest.TestCase):
    def test_repository_has_no_top_level_compat_shims(self) -> None:
        report = inventory.build_inventory(ROOT)

        self.assertEqual(report.top_level_script_count, 0)
        self.assertEqual(report.top_level_scripts, [])
        self.assertEqual(report.keep_cli, [])
        self.assertEqual(report.temporary_compat, [])
        self.assertEqual(report.delete_now, [])
        self.assertEqual(report.legacy_bridge, [])
        self.assertEqual(report.shim_style_counts, {})
        self.assertEqual(report.unknown_shim_styles, [])
        self.assertEqual(report.reexport_blocks, [])
        self.assertEqual(report.manual_export_surfaces, [])
        self.assertEqual(report.unbucketed, [])

    def test_archived_direct_invocation_does_not_keep_shim_temporary(self) -> None:
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            write_fixture_script(
                repo_root,
                "archived_helper.py",
                '''#!/usr/bin/env python3
"""Compatibility shim for a helper referenced only by archived plans."""

from __future__ import annotations

import sys

from aippocampus_runtime.archived import helper as _impl

sys.modules[__name__] = _impl
''',
            )
            write_fixture_script(
                repo_root,
                "aippocampus_runtime/archived/helper.py",
                "def main() -> int:\n    return 0\n",
            )
            archive_dir = repo_root / "docs" / "archive" / "plans"
            archive_dir.mkdir(parents=True)
            (archive_dir / "old.md").write_text(
                "Use `archived_helper.py` for an old migration.\n",
                encoding="utf-8",
            )

            report = inventory.build_inventory(repo_root)
            delete_now = {item.script: item for item in report.delete_now}

            self.assertIn("archived_helper.py", delete_now)


if __name__ == "__main__":
    unittest.main()
