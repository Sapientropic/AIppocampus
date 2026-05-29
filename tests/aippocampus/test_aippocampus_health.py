from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"
for _path in (
    SCRIPTS,
    REPO_ROOT / "benchmarks" / "aippocampus",
    REPO_ROOT / "tools" / "aippocampus" / "smoke",
    REPO_ROOT / "tools" / "aippocampus" / "docs",
):
    sys.path.insert(0, str(_path))

import aippocampus_health as health  # noqa: E402


class AippocampusHealthTests(unittest.TestCase):
    def test_recommended_script_command_uses_posix_codex_home_on_macos(self) -> None:
        with mock.patch.object(health.os, "name", "posix"):
            command = health.recommended_script_command("build_index.py", Path("/tmp/work space"))

        self.assertEqual(
            command,
            'python "$CODEX_HOME/skills/aippocampus/scripts/build_index.py" --cwd "/tmp/work space"',
        )

    def test_recommended_script_command_keeps_powershell_shape_on_windows(self) -> None:
        with mock.patch.object(health.os, "name", "nt"):
            command = health.recommended_script_command("build_index.py", "C:/work")
        expected_cwd = "C:" + "\\work"

        self.assertEqual(
            command,
            f'python "$env:CODEX_HOME\\skills\\aippocampus\\scripts\\build_index.py" --cwd "{expected_cwd}"',
        )


if __name__ == "__main__":
    unittest.main()
