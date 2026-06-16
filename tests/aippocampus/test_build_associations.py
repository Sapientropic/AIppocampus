from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

from aippocampus_runtime.navigation import associations as assoc  # noqa: E402


class BuildAssociationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.thread = self.root / "old-thread"
        self.index_dir = self.thread / ".aippocampus"
        self.index_dir.mkdir(parents=True)
        self.sqlite = self.index_dir / "source_index.sqlite"
        self.registry = self.root / "registry" / "threads.json"
        self.registry.parent.mkdir()
        self._write_sqlite()
        self._write_registry()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_sqlite(self) -> None:
        con = sqlite3.connect(self.sqlite)
        try:
            con.execute(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY,
                    line INTEGER,
                    timestamp TEXT,
                    role TEXT,
                    kind TEXT,
                    phase TEXT,
                    turn_index INTEGER,
                    is_final INTEGER,
                    text TEXT
                )
                """
            )
            rows = [
                (
                    1,
                    10,
                    "2026-05-25T01:00:00Z",
                    "assistant",
                    "message",
                    "final_answer",
                    2,
                    1,
                    "我们把小海马体做成触发式联想，靠 UserPromptSubmit hook 读取 associations.json。",
                ),
                (
                    2,
                    11,
                    "2026-05-25T01:01:00Z",
                    "assistant",
                    "message",
                    "final_answer",
                    3,
                    1,
                    "好，开干。",
                ),
                (
                    3,
                    12,
                    "2026-05-25T01:02:00Z",
                    "assistant",
                    "message",
                    "final_answer",
                    4,
                    1,
                    "Current goal for this thread: status ACTIVE, token budget remaining, GOAL mode reminder.",
                ),
                (
                    4,
                    13,
                    "2026-05-25T01:03:00Z",
                    "assistant",
                    "message",
                    "commentary",
                    5,
                    0,
                    "我先读一下文件再继续。",
                ),
            ]
            con.executemany(
                """
                INSERT INTO messages
                (id, line, timestamp, role, kind, phase, turn_index, is_final, text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            con.commit()
        finally:
            con.close()

    def _write_registry(self) -> None:
        entry = {
            "thread_key": "session:test-old",
            "title": "old-thread",
            "workspace_name": "old-thread",
            "updated_at": "2026-05-25T19:00:00Z",
            "anchor_titles": ["Ambient recall hook design"],
            "keywords": ["external hippocampus", "ambient recall"],
            "summary": "旧线程沉淀了小海马体 hook 的触发式联想设计。",
            "paths": {
                "workspace": str(self.thread),
                "sqlite": str(self.sqlite),
                "anchors": None,
            },
        }
        self.registry.write_text(
            json.dumps(
                {"schema_version": 1, "updated_at": "2026-05-25T19:00:00Z", "threads": [entry]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_builder_extracts_dynamic_terms_but_filters_short_and_goal_noise(self) -> None:
        result = assoc.build_associations(self.registry, max_messages_per_thread=50)
        terms = result["terms"]
        flattened = "\n".join(sorted(terms))

        self.assertIn("小海马体", terms)
        self.assertIn("触发式联想", terms)
        self.assertIn("UserPromptSubmit", terms)
        self.assertIn("associations.json", terms)
        self.assertNotIn("好", flattened)
        self.assertNotIn("开干", flattened)
        self.assertNotIn("再想想", flattened)
        self.assertNotIn("GOAL", flattened)
        self.assertNotIn("token budget", flattened)

    def test_noise_filter_rejects_cjk_glue_fragments(self) -> None:
        self.assertTrue(assoc.term_is_noise("我们把小海马体做"))
        self.assertTrue(assoc.term_is_noise("阶段的"))
        self.assertTrue(assoc.term_is_noise("体验更像工具"))

    def test_ascii_domain_and_repo_terms_emit_component_aliases(self) -> None:
        text = " ".join(
            [
                "T-Sense",
                "Telegram",
                "Telethon",
                "OpenAI",
                "Pydantic",
                "runtime",
                "desktop",
                "scheduler",
                "profile",
                "review-card.tsx",
                "source_index.sqlite",
                "gogram.fun",
                "gotd-runtime-spike",
                "references",
            ]
        )
        terms = assoc.extract_terms_from_text(text)

        self.assertIn("gogram.fun", terms)
        self.assertIn("gogram", terms)
        self.assertIn("gotd-runtime-spike", terms)
        self.assertIn("gotd", terms)

    def test_dynamic_matching_does_not_reverse_trigger_related_terms(self) -> None:
        associations = {
            "terms": {
                "random": {
                    "term": "random",
                    "status": "staging",
                    "confidence": 0.5,
                    "related_terms": ["外置海马体"],
                    "threads": [],
                },
                "外置海马体": {
                    "term": "外置海马体",
                    "status": "verified",
                    "confidence": 0.95,
                    "related_terms": ["external hippocampus"],
                    "threads": [],
                },
            }
        }

        matches = assoc.match_associations("这个外置海马体还要再收一下", associations)

        self.assertEqual([item["term"] for item in matches], ["外置海马体"])

    def test_matching_large_term_set_avoids_regex_compile_churn(self) -> None:
        associations = {
            "terms": {
                f"term-{index:04d}": {
                    "term": f"term-{index:04d}",
                    "status": "staging",
                    "confidence": 0.1,
                    "threads": [],
                }
                for index in range(2500)
            }
        }
        associations["terms"]["AIppocampus"] = {
            "term": "AIppocampus",
            "status": "verified",
            "confidence": 0.99,
            "threads": [],
        }
        associations["terms"]["海马体联想"] = {
            "term": "海马体联想",
            "status": "verified",
            "confidence": 0.98,
            "threads": [],
        }
        original_compile = assoc.re._compile
        compile_count = 0

        def counted_compile(*args, **kwargs):
            nonlocal compile_count
            compile_count += 1
            return original_compile(*args, **kwargs)

        with mock.patch.object(assoc.re, "_compile", side_effect=counted_compile):
            matches = assoc.match_associations(
                "AIppocampus 的海马体联想要保持 source-backed",
                associations,
            )

        matched_terms = {item["term"] for item in matches}
        self.assertIn("AIppocampus", matched_terms)
        self.assertIn("海马体联想", matched_terms)
        self.assertLess(compile_count, 20)
        self.assertFalse(assoc.term_in_text("AIppo", "AIppocampus"))
        self.assertTrue(assoc.term_in_text("AIppocampus", "AIppocampus"))

    def test_anchor_keywords_are_verified_and_final_answer_terms_are_staging(self) -> None:
        result = assoc.build_associations(self.registry, max_messages_per_thread=50)
        terms = result["terms"]

        self.assertEqual(terms["external hippocampus"]["status"], "verified")
        self.assertEqual(terms["小海马体"]["status"], "staging")
        self.assertEqual(terms["小海马体"]["threads"][0]["phase"], "final_answer")
        self.assertEqual(terms["小海马体"]["threads"][0]["line"], 10)

    def test_builder_uses_clean_source_when_sqlite_is_missing(self) -> None:
        clean_dir = self.thread / "clean-source"
        clean_dir.mkdir()
        clean_messages = clean_dir / "messages.jsonl"
        clean_messages.write_text(
            json.dumps(
                {
                    "source_line": 30,
                    "role": "assistant",
                    "phase": "final_answer",
                    "turn_index": 9,
                    "is_final": True,
                    "text": "registry-managed clean source 可以让其他线程也进入被动联想范围。",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        entry = {
            "thread_key": "session:clean-only",
            "title": "clean-only",
            "workspace_name": "clean-only",
            "updated_at": "2026-05-25T19:00:00Z",
            "paths": {
                "workspace": str(self.thread),
                "clean_source_messages_jsonl": str(clean_messages),
            },
        }
        clean_registry = self.root / "registry" / "clean-only.json"
        clean_registry.write_text(
            json.dumps(
                {"schema_version": 1, "updated_at": "2026-05-25T19:00:00Z", "threads": [entry]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = assoc.build_associations(clean_registry, max_messages_per_thread=50)
        terms = result["terms"]

        self.assertIn("进入被动联想范围", terms)
        self.assertEqual(
            terms["进入被动联想范围"]["threads"][0]["source"], "clean_source_final_answer"
        )
        self.assertEqual(terms["进入被动联想范围"]["threads"][0]["line"], 30)


if __name__ == "__main__":
    unittest.main()
