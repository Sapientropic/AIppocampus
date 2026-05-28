from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import warm_ambient_recall as warm  # noqa: E402


class WarmAmbientRecallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.cache_path = self.root / "ambient-thread-cache.json"
        self.residue_path = self.root / "ambient-residue.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_quorum_returns_without_waiting_for_all_scouts(self) -> None:
        calls: list[str] = []

        def scout_fn(scout, payload, **kwargs):
            del payload, kwargs
            calls.append(scout)
            if scout in {"query_expansion", "life_wide_cue_classifier"}:
                return {
                    "decision": "candidate",
                    "confidence": 0.72,
                    "themes": [f"{scout} theme"],
                    "candidates": [
                        {
                            "theme": f"{scout} theme",
                            "support_level": "candidate",
                            "matched_terms": ["ambient recall"],
                        }
                    ],
                }
            time.sleep(0.25)
            return {"decision": "skip", "confidence": 0.1}

        started = time.perf_counter()
        result = warm.run_warm_ambient_recall(
            "继续 ambient recall 这条线",
            cwd=self.workspace,
            thread_id="thread-a",
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            quorum=2,
            timeout=0.12,
            no_write=True,
        )
        elapsed = time.perf_counter() - started

        self.assertTrue(result["available"])
        self.assertTrue(result["quorum_met"])
        self.assertLess(elapsed, 0.2)
        self.assertEqual(result["accepted_scout_count"], 2)
        self.assertGreaterEqual(len(warm.DEFAULT_SCOUTS), 10)
        self.assertIn("query_expansion", calls)
        self.assertIn("life_wide_cue_classifier", calls)

    def test_malformed_scout_is_isolated(self) -> None:
        def scout_fn(scout, payload, **kwargs):
            del payload, kwargs
            if scout == "query_expansion":
                raise ValueError("not valid JSON")
            return {
                "decision": "candidate",
                "confidence": 0.8,
                "candidates": [{"theme": "warm cache", "support_level": "candidate"}],
            }

        result = warm.run_warm_ambient_recall(
            "继续 warm cache",
            cwd=self.workspace,
            thread_id="thread-a",
            cache_path=self.cache_path,
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("query_expansion", "theme_matcher"),
            quorum=1,
            timeout=0.5,
            no_write=True,
        )

        self.assertTrue(result["available"])
        self.assertEqual(result["accepted_scout_count"], 1)
        self.assertEqual(result["failed_scout_count"], 1)
        self.assertEqual(result["scouts"][0]["ok"], False)
        self.assertEqual(result["scouts"][1]["ok"], True)
        self.assertEqual(result["cards"][0]["theme"], "warm cache")

    def test_warm_merge_writes_thread_cache_and_residue_without_raw_inputs(self) -> None:
        local_path = "E:" + "\\private\\notes\\ambient.md"
        prompt = f"继续 {local_path} 里的 ambient recall 方案"

        def scout_fn(scout, payload, **kwargs):
            del scout, payload, kwargs
            return {
                "decision": "evidence",
                "confidence": 0.91,
                "negative_contexts": ["do not treat unsourced scent as fact"],
                "candidates": [
                    {
                        "theme": "ambient recall cache first",
                        "support_level": "evidence",
                        "resonance": "high",
                        "suggested_use": "Use as source-backed prior only when helpful.",
                        "key_line": "Card/cache first, then warm scouts.",
                        "matched_terms": ["ambient recall", "cache"],
                        "source_refs": [
                            {
                                "thread_key": "session:old",
                                "title": "Ambient design",
                                "line": 42,
                                "message_id": "msg-1",
                            }
                        ],
                    }
                ],
            }

        result = warm.run_warm_ambient_recall(
            prompt,
            cwd=self.workspace,
            thread_id="thread-a",
            topic_epoch="epoch-test",
            cache_path=self.cache_path,
            residue_path=self.residue_path,
            residue_reason="warm_scout_unused",
            api_key="test-key",
            scout_fn=scout_fn,
            scouts=("evidence_judge",),
            quorum=1,
            timeout=0.5,
        )
        cache_raw = self.cache_path.read_text(encoding="utf-8")
        residue_rows = [
            json.loads(line)
            for line in self.residue_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        joined = cache_raw + "\n" + self.residue_path.read_text(encoding="utf-8")

        self.assertEqual(result["cache_write"]["status"], "written")
        self.assertEqual(result["cache_write"]["residue_export"]["status"], "written")
        self.assertEqual(residue_rows[0]["source"], "ambient_thread_cache")
        self.assertEqual(residue_rows[0]["reason"], "warm_scout_unused")
        self.assertNotIn(str(self.workspace), joined)
        self.assertNotIn("private", joined.casefold())
        self.assertNotIn("notes", joined.casefold())
        self.assertNotIn(prompt, joined)

    def test_missing_api_key_fails_open_without_writing(self) -> None:
        result = warm.run_warm_ambient_recall(
            "继续 ambient recall",
            cwd=self.workspace,
            thread_id="thread-a",
            cache_path=self.cache_path,
            api_key=None,
            api_key_env="AIPPOCAMPUS_TEST_MISSING_KEY",
        )

        self.assertFalse(result["available"])
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "missing api key")
        self.assertFalse(self.cache_path.exists())


if __name__ == "__main__":
    unittest.main()
