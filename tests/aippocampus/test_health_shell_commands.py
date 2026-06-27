from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from aippocampus_runtime import health


class HealthShellCommandTests(unittest.TestCase):
    def test_recommended_commands_quote_shell_sensitive_cwd_by_shell(self) -> None:
        with mock.patch.object(health.os, "name", "posix"):
            posix = health.recommended_script_command(
                "build_index.py",
                Path("/tmp/work $space`quote' bang!"),
            )
            posix_facade = health.recommended_facade_command(
                "build_index",
                Path("/tmp/work $space`quote' bang!"),
            )
        self.assertIn("--cwd '/tmp/work $space`quote'\"'\"' bang!'", posix)
        self.assertEqual(
            posix_facade,
            "aippocampus maintenance --cwd '/tmp/work $space`quote'\"'\"' bang!'",
        )

        with mock.patch.object(health.os, "name", "nt"):
            powershell = health.recommended_script_command(
                "build_index.py",
                'C:/work $space`tick "quote" O\'Brien!',
            )
            powershell_facade = health.recommended_facade_command(
                "build_index",
                'C:/work $space`tick "quote" O\'Brien!',
            )
        expected_cwd = "C:" + "\\work $space`tick \"quote\" O'Brien!"
        escaped_cwd = expected_cwd.replace(chr(39), chr(39) * 2)
        self.assertIn(f"--cwd '{escaped_cwd}'", powershell)
        self.assertEqual(
            powershell_facade,
            f"aippocampus maintenance --cwd '{escaped_cwd}'",
        )
