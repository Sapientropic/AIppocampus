from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import deepseek_model_routing as routing  # noqa: E402


class DeepSeekModelRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_values = {
            name: os.environ.get(name)
            for name in [
                "DEEPSEEK_MODEL",
                "AIPPOCAMPUS_DEEPSEEK_FLASH_MODEL",
                "AIPPOCAMPUS_DEEPSEEK_PRO_MODEL",
                "DEEPSEEK_PRO_MODEL",
            ]
        }
        for name in self.old_values:
            os.environ.pop(name, None)

    def tearDown(self) -> None:
        for name, value in self.old_values.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_flash_is_default_and_pro_routes_are_explicit(self) -> None:
        self.assertEqual(routing.resolve_model_route(None).model, "deepseek-v4-flash")
        self.assertEqual(routing.resolve_model_route("default").model, "deepseek-v4-flash")
        self.assertEqual(routing.resolve_model_route("fast").model, "deepseek-v4-flash")

        for route in ["pro", "slow_adjudication", "suppressed_label_recovery", "agentic_source_review"]:
            resolved = routing.resolve_model_route(route)
            self.assertEqual(resolved.model, "deepseek-v4-pro")
            self.assertEqual(resolved.tier, "pro")

    def test_environment_overrides_keep_legacy_default_model_compatible(self) -> None:
        os.environ["DEEPSEEK_MODEL"] = "legacy-flash"
        os.environ["AIPPOCAMPUS_DEEPSEEK_PRO_MODEL"] = "pro-expensive"

        self.assertEqual(routing.resolve_model_route("default").model, "legacy-flash")
        self.assertEqual(routing.resolve_model_route("agentic_source_review").model, "pro-expensive")
        self.assertEqual(routing.resolve_model_route("default", explicit_model="manual").model, "manual")


if __name__ == "__main__":
    unittest.main()
