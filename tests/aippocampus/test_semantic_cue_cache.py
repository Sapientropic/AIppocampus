from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

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

from aippocampus_runtime.recall import semantic_cue_cache as cues  # noqa: E402


class SemanticCueCacheTests(unittest.TestCase):
    def test_semantic_cue_cache_keys_use_sha256(self) -> None:
        prompt = "继续 外置海马体"
        cue = "外置海马体"
        route = "semantic_gate"
        normalized_prompt = " ".join(prompt.split())
        cue_material = f"{route}\n{cue.casefold()}"

        self.assertEqual(
            cues.prompt_hash(prompt),
            hashlib.sha256(normalized_prompt.encode("utf-8")).hexdigest()[:16],
        )
        self.assertEqual(
            cues.cue_key(cue, route),
            "sc_" + hashlib.sha256(cue_material.encode("utf-8")).hexdigest()[:18],
        )

    def test_repeated_source_backed_hits_promote_multilingual_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "semantic_cues.jsonl"
            semantic_result = {
                "available": True,
                "decision": "scent",
                "confidence": 0.86,
                "query_aliases": [
                    "memoria externa",
                    "外置海马体",
                    "внешний гиппокамп",
                    "ذاكرة سياقية",
                ],
            }
            source_refs = [
                {
                    "thread_key": "session:aippocampus",
                    "message_id": "m1",
                    "source_line": 12,
                }
            ]

            first = cues.record_semantic_cue_hits(
                cache_path,
                prompt="¿Seguimos con la memoria externa?",
                semantic_result=semantic_result,
                source_refs=source_refs,
                route="semantic_gate",
            )
            second = cues.record_semantic_cue_hits(
                cache_path,
                prompt="¿Puedes continuar esa memoria externa?",
                semantic_result=semantic_result,
                source_refs=source_refs,
                route="semantic_gate",
            )

            self.assertEqual(first["active_count"], 0)
            self.assertEqual(second["active_count"], 4)
            rows = cues.load_semantic_cues(cache_path)
            by_cue = {row["cue"]: row for row in rows}
            self.assertEqual(
                set(by_cue),
                {"memoria externa", "外置海马体", "внешний гиппокамп", "ذاكرة سياقية"},
            )
            self.assertEqual(by_cue["memoria externa"]["script"], "Latn")
            self.assertEqual(by_cue["外置海马体"]["script"], "Hani")
            self.assertEqual(by_cue["внешний гиппокамп"]["script"], "Cyrl")
            self.assertEqual(by_cue["ذاكرة سياقية"]["script"], "Arab")

            triggers = cues.semantic_cue_triggers(cache_path)
            trigger_aliases = {
                alias for trigger in triggers for alias in trigger.get("aliases") or []
            }
            self.assertIn("memoria externa", trigger_aliases)
            self.assertIn("внешний гиппокамп", trigger_aliases)

    def test_false_positive_pressure_keeps_noisy_cue_out_of_trigger_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "semantic_cues.jsonl"
            semantic_result = {
                "available": True,
                "decision": "scent",
                "confidence": 0.9,
                "query_aliases": ["generic continuity"],
            }
            source_refs = [{"thread_key": "session:aippocampus", "message_id": "m1"}]
            for _ in range(2):
                cues.record_semantic_cue_hits(
                    cache_path,
                    prompt="continue the generic continuity thread",
                    semantic_result=semantic_result,
                    source_refs=source_refs,
                    route="semantic_gate",
                )

            cues.record_semantic_cue_misses(
                cache_path,
                cues=["generic continuity"],
                reason="matched an unrelated project",
            )
            cues.record_semantic_cue_misses(
                cache_path,
                cues=["generic continuity"],
                reason="matched an unrelated project again",
            )

            triggers = cues.semantic_cue_triggers(cache_path)

            self.assertEqual(triggers, [])

    def test_semantic_cue_cache_report_is_count_only_and_source_backed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "semantic_cues.jsonl"
            semantic_result = {
                "available": True,
                "decision": "scent",
                "confidence": 0.9,
                "query_aliases": ["private cue text"],
            }
            source_refs = [{"thread_key": "session:aippocampus", "message_id": "m1"}]
            for _ in range(2):
                cues.record_semantic_cue_hits(
                    cache_path,
                    prompt="private prompt text",
                    semantic_result=semantic_result,
                    source_refs=source_refs,
                    route="semantic_gate",
                )
            cues.record_semantic_cue_misses(
                cache_path,
                cues=["private cue text"],
                reason="matched an unrelated project",
            )

            report = cues.semantic_cue_cache_report(cache_path)
            encoded = json.dumps(report, ensure_ascii=False)

            self.assertEqual(report["entry_count"], 1)
            self.assertEqual(report["active_count"], 1)
            self.assertEqual(report["source_backed_count"], 1)
            self.assertEqual(report["false_positive_count"], 1)
            self.assertIn("net_hit_buckets", report)
            self.assertNotIn("private cue text", encoded)
            self.assertNotIn("private prompt text", encoded)


if __name__ == "__main__":
    unittest.main()
