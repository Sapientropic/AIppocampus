from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import living_cue_cache as cues  # noqa: E402


class LivingCueCacheTests(unittest.TestCase):
    def test_entry_schema_keeps_source_refs_and_navigation_boundary(self) -> None:
        entry = cues.normalize_living_cue_entry(
            {
                "cue": "那个树的问题",
                "aliases": ["tree problem", "component tree confusion"],
                "source_refs": [
                    {
                        "source_id": "clean:tree:m7",
                        "thread_key": "session:tree",
                        "message_id": "m7",
                        "line": 14,
                        "snippet": "raw source text must not survive",
                    }
                ],
                "confidence": 0.91,
                "sensitivity": "safe",
                "freshness": "current",
                "status": "current",
                "decay": 0.03,
                "last_helpful_count": 3,
                "last_harmful_count": 0,
            }
        )
        encoded = json.dumps(entry, ensure_ascii=False, sort_keys=True)

        self.assertEqual(entry["kind"], cues.LIVING_CUE_KIND)
        self.assertEqual(entry["schema_version"], cues.LIVING_CUE_SCHEMA_VERSION)
        self.assertTrue(entry["cue_id"].startswith("lc_"))
        self.assertEqual(entry["status"], "current")
        self.assertEqual(entry["currentness"], "current")
        self.assertEqual(entry["confidence"], 0.91)
        self.assertEqual(entry["sensitivity"], "safe")
        self.assertEqual(entry["freshness"], "current")
        self.assertEqual(entry["decay"], 0.03)
        self.assertEqual(entry["last_helpful_count"], 3)
        self.assertEqual(entry["last_harmful_count"], 0)
        self.assertTrue(entry["source_reopen_required"])
        self.assertTrue(entry["source_boundary"]["living_cache_entries_are_navigation_only"])
        self.assertEqual(
            entry["source_refs"],
            [{"source_id": "clean:tree:m7", "thread_key": "session:tree", "message_id": "m7", "line": 14}],
        )
        self.assertNotIn("raw source text", encoded)

    def test_learned_phrase_bridges_to_source_handles_without_live_llm(self) -> None:
        target = cues.normalize_living_cue_entry(
            {
                "cue": "那个树的问题",
                "aliases": ["tree problem", "component tree confusion"],
                "source_refs": [
                    {"source_id": "clean:tree:m7", "thread_key": "session:tree", "message_id": "m7", "line": 14}
                ],
                "confidence": 0.92,
                "sensitivity": "safe",
                "freshness": "current",
                "status": "current",
                "last_helpful_count": 2,
            }
        )
        distractor = cues.normalize_living_cue_entry(
            {
                "cue": "树形数据展示",
                "aliases": ["tree view"],
                "source_refs": [{"thread_key": "session:view", "message_id": "m2"}],
                "confidence": 0.78,
                "sensitivity": "safe",
                "freshness": "current",
                "status": "current",
            }
        )

        packet = cues.select_living_cue_packet(
            "继续那个树的问题，用英文也可以叫 tree problem",
            [distractor, target],
            max_entries=1,
        )
        encoded = json.dumps(packet, ensure_ascii=False, sort_keys=True)

        self.assertEqual(packet["kind"], "aippocampus_living_cue_packet")
        self.assertEqual(packet["decision"], "scent")
        self.assertEqual(packet["support_level"], "source_required")
        self.assertEqual(packet["selected_count"], 1)
        self.assertEqual(packet["candidate_refs"][0]["source_id"], "clean:tree:m7")
        self.assertEqual(packet["diagnostics"]["cache_hit_count"], 1)
        self.assertEqual(packet["diagnostics"]["selected_count"], 1)
        self.assertEqual(packet["diagnostics"]["live_llm_call_count"], 0)
        self.assertTrue(packet["source_boundary"]["source_reopen_required_before_claim"])
        self.assertNotIn("那个树的问题", encoded)
        self.assertNotIn("tree problem", encoded)
        self.assertNotIn("component tree", encoded)

    def test_temporary_mood_does_not_become_durable_fresh_thread_cue(self) -> None:
        temporary = cues.normalize_living_cue_entry(
            {
                "cue": "压力好大",
                "aliases": ["stressed tonight"],
                "source_refs": [{"source_id": "clean:mood:one-off", "thread_key": "session:mood"}],
                "confidence": 0.88,
                "sensitivity": "caution",
                "freshness": "current",
                "status": "temporary",
                "last_helpful_count": 0,
                "last_harmful_count": 1,
            }
        )

        packet = cues.select_living_cue_packet("我今天压力好大", [temporary])
        encoded = json.dumps(packet, ensure_ascii=False, sort_keys=True)

        self.assertEqual(packet["decision"], "skip")
        self.assertEqual(packet["support_level"], "suppressed")
        self.assertEqual(packet["selected_count"], 0)
        self.assertEqual(packet["candidate_refs"], [])
        self.assertEqual(packet["diagnostics"]["would_overpersonalize_count"], 1)
        self.assertEqual(packet["diagnostics"]["temporary_suppressed_count"], 1)
        self.assertEqual(packet["diagnostics"]["stale_suppressed_count"], 0)
        self.assertNotIn("压力好大", encoded)
        self.assertNotIn("stressed tonight", encoded)

    def test_stale_or_superseded_hits_are_suppressed_with_count_only_diagnostics(self) -> None:
        stale = cues.normalize_living_cue_entry(
            {
                "cue": "旧路线",
                "aliases": ["old route"],
                "source_refs": [{"source_id": "clean:old:m1", "thread_key": "session:old"}],
                "confidence": 0.95,
                "sensitivity": "safe",
                "freshness": "stale",
                "status": "superseded",
            }
        )

        packet = cues.select_living_cue_packet("old route 怎么继续？", [stale])
        report = cues.living_cue_cache_report([stale])
        encoded_packet = json.dumps(packet, ensure_ascii=False, sort_keys=True)
        encoded_report = json.dumps(report, ensure_ascii=False, sort_keys=True)

        self.assertEqual(packet["decision"], "skip")
        self.assertEqual(packet["support_level"], "suppressed")
        self.assertEqual(packet["diagnostics"]["cache_hit_count"], 1)
        self.assertEqual(packet["diagnostics"]["stale_suppressed_count"], 1)
        self.assertEqual(report["entry_count"], 1)
        self.assertEqual(report["source_backed_count"], 1)
        self.assertEqual(report["status_counts"]["superseded"], 1)
        self.assertEqual(report["output_boundary"], "living_cue_cache_report_counts_only")
        self.assertNotIn("旧路线", encoded_packet + encoded_report)
        self.assertNotIn("old route", encoded_packet + encoded_report)


if __name__ == "__main__":
    unittest.main()
