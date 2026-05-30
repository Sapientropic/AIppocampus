from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = REPO_ROOT / "tools" / "aippocampus" / "smoke"
sys.path.insert(0, str(SMOKE))

import smoke_memory_pain_prompt_hook as smoke  # noqa: E402


class MemoryPainPromptHookSmokeTests(unittest.TestCase):
    def test_real_history_smoke_output_is_hash_only_by_default(self) -> None:
        private_marker = "PRIVATE_REAL_HISTORY_PROMPT_MARKER"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "registry" / "threads.json"
            registry.parent.mkdir()
            registry.write_text(
                json.dumps({"schema_version": 1, "threads": []}, ensure_ascii=False),
                encoding="utf-8",
            )

            result = smoke.run_memory_pain_smoke(
                [
                    {
                        "name": "private case name",
                        "kind": "negative",
                        "prompt": f"{private_marker}: keep this unsupported without a cited row",
                    }
                ],
                cwd=root,
                registry_path=registry,
                semantic_gate_mode="off",
                show_names=False,
            )

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["privacy"], "aggregate_hash_only")
        self.assertNotIn(private_marker, rendered)
        self.assertNotIn("private case name", rendered)
        self.assertIn("case_hash", result["rows"][0])
        self.assertNotIn("prompt", result["rows"][0])


if __name__ == "__main__":
    unittest.main()
