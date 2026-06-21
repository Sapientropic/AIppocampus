from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from aippocampus_runtime.cli import facade


class CliRuntimeFloorTests(unittest.TestCase):
    def test_package_facade_blocks_old_python_with_clean_runtime_floor(self) -> None:
        payload = facade.python_runtime_floor_payload((3, 11, 9))

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["blocking_issue"]["id"], "python_runtime_too_old")
        self.assertIn("3.12", payload["blocking_issue"]["required_python"])
        self.assertIsNone(facade.python_runtime_floor_payload((3, 12, 0)))

    def test_package_facade_emits_json_runtime_floor_before_dispatch(self) -> None:
        with patch.object(facade.sys, "version_info", (3, 11, 9)):
            result = facade.run_command(["version", "--json"], capture_output=True)
        payload = json.loads(result.stdout)

        self.assertEqual(result.exit_code, 2)
        self.assertEqual(payload["blocking_issue"]["id"], "python_runtime_too_old")
        self.assertEqual(payload["foreground_action"]["command"], "py -3.12 --version")
