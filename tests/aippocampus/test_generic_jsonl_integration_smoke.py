from __future__ import annotations

import json
import unittest

from tests.aippocampus.import_path_helpers import import_smoke_module

smoke = import_smoke_module("smoke_generic_jsonl_integration")

class GenericJsonlIntegrationSmokeTests(unittest.TestCase):
    def test_generic_jsonl_import_then_mcp_search_smoke_passes(self) -> None:
        result = smoke.run_smoke()

        self.assertTrue(result["ok"], json.dumps(result, ensure_ascii=False, indent=2))
        proof = result["proof"]
        self.assertEqual(proof["non_native_host_label"], "internal-agent-demo")
        self.assertIn("data import/export", proof["verified_levels"])
        self.assertIn("automatic ambient recall", proof["not_claimed"])
        self.assertEqual(proof["dry_run"]["source_provider"], "generic-jsonl")
        self.assertEqual(
            proof["import"]["thread_key"],
            "generic-jsonl:session:internal-agent-runtime-demo",
        )
        self.assertFalse(proof["dry_run_created_registry"])
        self.assertGreaterEqual(proof["mcp"]["match_count"], 1)
        self.assertTrue(proof["mcp"]["registry_redacted"])
        self.assertTrue(proof["mcp"]["private_path_free_payload"])
        self.assertTrue(
            any(
                ref.startswith("generic-jsonl:session:internal-agent-runtime-demo#L")
                for ref in proof["mcp"]["source_refs"]
            )
        )

if __name__ == "__main__":
    unittest.main()
