from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = REPO_ROOT / "tools" / "aippocampus" / "smoke"
sys.path.insert(0, str(SMOKE))

import smoke_openai_agents_sdk_tool_contract as smoke  # noqa: E402


class OpenAIAgentsSDKSmokeTests(unittest.TestCase):
    def test_sanitized_lookup_payload_excludes_private_locator_shapes(self) -> None:
        payload = smoke.build_sanitized_lookup_payload("Find a public source id.")

        self.assertTrue(smoke.payload_is_private_locator_free(payload))
        self.assertEqual(payload["hosted_model_input_policy"], "query_and_source_ids_only")
        self.assertFalse(payload["private_locator_forwarded"])
        self.assertFalse(payload["transcript_text_forwarded"])

    def test_openai_agents_sdk_tool_contract_smoke_passes_when_extra_installed(self) -> None:
        if importlib.util.find_spec("agents") is None:
            self.skipTest(f"install optional dependency with: {smoke.INSTALL_COMMAND}")

        result = smoke.run_smoke()

        self.assertTrue(result["ok"], json.dumps(result, ensure_ascii=False, indent=2))
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["tool_contract"]["tool_name"], "aippocampus_lookup_memory")
        self.assertIn("query", result["tool_contract"]["schema_properties"])
        self.assertTrue(result["checks"]["sample_payload_private_locator_free"])
        self.assertIn("hosted Runner execution", result["cannot_claim"])


if __name__ == "__main__":
    unittest.main()
