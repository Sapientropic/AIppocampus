from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = REPO_ROOT / "benchmarks" / "aippocampus"
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
for _path in (BENCHMARKS, SCRIPTS):
    sys.path.insert(0, str(_path))

import benchmark_warm_ambient_recall as benchmark  # noqa: E402


class WarmAmbientRecallBenchmarkTests(unittest.TestCase):
    def test_deterministic_benchmark_emits_sanitized_metrics_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = benchmark.run_warm_ambient_recall_benchmark(
                cwd=Path(tmp) / "workspace",
                case_limit=2,
                live=False,
            )

        raw = json.dumps(payload, ensure_ascii=False).casefold()

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["live_model"])
        self.assertEqual(payload["metrics"]["case_count"], 2)
        self.assertGreater(payload["metrics"]["total_scout_calls"], 0)
        self.assertEqual(payload["privacy_boundary"]["raw_prompt_emitted"], False)
        self.assertEqual(payload["privacy_boundary"]["raw_cards_emitted"], False)
        self.assertIn("prompt_sha1", payload["cases"][0])
        self.assertNotIn("那个脑内续接器", raw)
        self.assertNotIn("cards", payload["cases"][0])


if __name__ == "__main__":
    unittest.main()
