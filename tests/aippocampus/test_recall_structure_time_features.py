from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.recall import index_builder, retrieval  # noqa: E402


def _message(
    *,
    line: int,
    timestamp: str,
    role: str = "assistant",
    phase: str = "final_answer",
    is_final: bool = True,
    text: str,
) -> dict:
    return {
        "line": line,
        "timestamp": timestamp,
        "role": role,
        "kind": "message",
        "phase": phase,
        "turn_index": line // 10,
        "is_final": is_final,
        "sha1": hashlib.sha1(text.encode("utf-8")).hexdigest(),
        "text": text,
    }


class RecallStructureTimeFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.index = self.root / "source_index.sqlite"
        self.messages = [
            _message(
                line=10,
                timestamp="2026-02-10T09:30:00Z",
                text=(
                    "# Rescue note\n"
                    "Warning: keep the source reopen gate intact.\n\n"
                    "```python\n"
                    "print('source backed')\n"
                    "```\n\n"
                    "- preserve clean source evidence\n"
                    "- keep scalar structure features searchable\n\n"
                    "| cue | signal |\n"
                    "| --- | --- |\n"
                    "| code | true |\n"
                ),
            ),
            _message(
                line=20,
                timestamp="2026-02-13T23:35:00Z",
                text="Calendar resonance checkpoint for time lane calibration.",
            ),
            _message(
                line=30,
                timestamp="2026-01-03T10:00:00Z",
                text="Calendar resonance checkpoint from an older unrelated session.",
            ),
            _message(
                line=40,
                timestamp="2026-02-14T08:00:00Z",
                text="Plain lexical target for D0 D3 regression smoke.",
            ),
        ]

        index_builder.make_sqlite(
            self.index,
            self.messages,
            anchors=[],
            rag_cache=False,
            publish_lock=False,
            source_created_at="2026-02-01T00:00:00Z",
            source_updated_at="2026-02-14T09:00:00Z",
            last_active_at="2026-02-14T09:00:00Z",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_index_builds_message_features_sidecar_with_hot_columns_and_indexes(self) -> None:
        con = sqlite3.connect(self.index)
        con.row_factory = sqlite3.Row
        try:
            columns = {
                row["name"]
                for row in con.execute("PRAGMA table_info(message_features)").fetchall()
            }
            for column in {
                "message_id",
                "source_ref",
                "has_code_block",
                "code_languages_json",
                "has_warning",
                "has_list",
                "has_table",
                "heading_count",
                "line_count",
                "role",
                "phase",
                "is_final",
                "message_timestamp",
                "thread_created_at",
                "thread_updated_at",
                "active_timestamp",
                "metadata_json",
            }:
                self.assertIn(column, columns)

            row = con.execute(
                """
                SELECT *
                FROM message_features
                WHERE message_id = 1
                """
            ).fetchone()
            self.assertEqual(row["has_code_block"], 1)
            self.assertEqual(json.loads(row["code_languages_json"]), ["python"])
            self.assertEqual(row["has_warning"], 1)
            self.assertEqual(row["has_list"], 1)
            self.assertEqual(row["has_table"], 1)
            self.assertEqual(row["heading_count"], 1)
            self.assertGreaterEqual(row["line_count"], 10)
            self.assertEqual(row["role"], "assistant")
            self.assertEqual(row["phase"], "final_answer")
            self.assertEqual(row["is_final"], 1)
            self.assertEqual(row["message_timestamp"], "2026-02-10T09:30:00Z")
            self.assertEqual(row["thread_created_at"], "2026-02-01T00:00:00Z")
            self.assertEqual(row["thread_updated_at"], "2026-02-14T09:00:00Z")
            self.assertEqual(row["active_timestamp"], "2026-02-10T09:30:00Z")
            self.assertTrue(str(row["source_ref"]).startswith("message_sha1:"))

            indexes = {
                row["name"]
                for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                ).fetchall()
            }
            self.assertIn("idx_message_features_code_block", indexes)
            self.assertIn("idx_message_features_warning", indexes)
            self.assertIn("idx_message_features_table", indexes)
            self.assertIn("idx_message_features_active_timestamp", indexes)
        finally:
            con.close()

    def test_structure_cues_retrieve_sources_through_explicit_structure_signals(self) -> None:
        structure_cues = retrieval.parse_structure_cues(
            "find the final answer with a code block, warning, list, and table"
        )

        results = retrieval.search_hybrid_index(
            self.index,
            query_terms=[],
            expanded_terms=[],
            anchor_matches=[],
            limit=3,
            use_rag_chunks=False,
            structure_cues=structure_cues,
        )

        self.assertEqual(results[0]["id"], 1)
        self.assertGreater(results[0]["signals"]["structure_match_score"], 0.0)
        self.assertEqual(
            results[0]["signals"]["structure_signals"],
            {
                "has_code_block": True,
                "has_warning": True,
                "has_list": True,
                "has_table": True,
                "is_final": True,
            },
        )
        self.assertIn("source backed", results[0]["snippet"])

    def test_temporal_cues_rank_nearby_sources_without_hard_filtering_vague_matches(self) -> None:
        temporal_cue = retrieval.parse_temporal_cue("around 2026-02-13 late at night")

        self.assertIsNotNone(temporal_cue)
        self.assertEqual(temporal_cue["cue_kind"], "date_time_of_day")
        self.assertGreater(temporal_cue["confidence"], 0.0)
        self.assertLess(temporal_cue["window_start"], temporal_cue["window_end"])

        results = retrieval.search_hybrid_index(
            self.index,
            query_terms=["calendar", "resonance"],
            expanded_terms=["calendar", "resonance"],
            anchor_matches=[],
            limit=4,
            use_rag_chunks=False,
            temporal_cue=temporal_cue,
        )

        self.assertEqual(results[0]["id"], 2)
        self.assertIn(3, [result["id"] for result in results])
        self.assertGreater(results[0]["signals"]["temporal_affinity_score"], 0.0)
        self.assertEqual(results[0]["signals"]["temporal_cue_kind"], "date_time_of_day")
        self.assertIn("text_score", results[0]["signals"])

    def test_relative_temporal_cues_parse_to_deterministic_windows(self) -> None:
        last_month = retrieval.parse_temporal_cue(
            "what happened last month",
            now="2026-06-08T12:00:00Z",
        )
        half_year = retrieval.parse_temporal_cue(
            "半年前我们聊过什么",
            now="2026-06-08T12:00:00Z",
        )
        few_months = retrieval.parse_temporal_cue(
            "几个月前那个方案",
            now="2026-06-08T12:00:00Z",
        )
        about_six = retrieval.parse_temporal_cue(
            "about six months ago",
            now="2026-06-08T12:00:00Z",
        )

        self.assertIsNotNone(last_month)
        self.assertEqual(last_month["cue_kind"], "relative_last_month")
        self.assertEqual(last_month["window_start"], "2026-05-01T00:00:00Z")
        self.assertEqual(last_month["window_end"], "2026-06-01T00:00:00Z")
        self.assertFalse(last_month["hard_filter"])

        self.assertIsNotNone(half_year)
        self.assertEqual(half_year["cue_kind"], "relative_half_year")
        self.assertEqual(half_year["window_start"], "2025-12-01T00:00:00Z")
        self.assertEqual(half_year["window_end"], "2026-01-01T00:00:00Z")

        self.assertIsNotNone(few_months)
        self.assertEqual(few_months["cue_kind"], "relative_few_months")
        self.assertEqual(few_months["window_start"], "2026-02-01T00:00:00Z")
        self.assertEqual(few_months["window_end"], "2026-05-01T00:00:00Z")
        self.assertLess(few_months["confidence"], half_year["confidence"])

        self.assertIsNotNone(about_six)
        self.assertEqual(about_six["cue_kind"], "relative_half_year")
        self.assertEqual(about_six["window_start"], "2025-11-01T00:00:00Z")
        self.assertEqual(about_six["window_end"], "2026-02-01T00:00:00Z")

    def test_text_only_search_still_works_when_structure_time_lanes_are_not_requested(self) -> None:
        results = retrieval.search_hybrid_index(
            self.index,
            query_terms=["plain", "lexical"],
            expanded_terms=["plain", "lexical"],
            anchor_matches=[],
            limit=3,
            use_rag_chunks=False,
        )

        self.assertEqual(results[0]["id"], 4)
        self.assertNotIn("structure_match_score", results[0]["signals"])
        self.assertNotIn("temporal_affinity_score", results[0]["signals"])


if __name__ == "__main__":
    unittest.main()
