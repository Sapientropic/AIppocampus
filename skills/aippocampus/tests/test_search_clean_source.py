from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import search_clean_source as search  # noqa: E402
import registry  # noqa: E402


class SearchCleanSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.source = self.cwd / ".aippocampus" / "clean-source"
        self.source.mkdir(parents=True)
        messages = [
            {
                "id": "msg_user",
                "source_line": 10,
                "role": "user",
                "phase": "",
                "turn_index": 1,
                "is_final": False,
                "scope_labels": ["technical_work", "open_question"],
                "text": "为什么我们要做 AIppocampus？",
            },
            {
                "id": "msg_final",
                "source_line": 13,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 1,
                "is_final": True,
                "scope_labels": ["technical_work"],
                "text": "AIppocampus 是清洗后的原文记忆库。",
            },
            {
                "id": "msg_fallback",
                "source_line": 21,
                "role": "assistant",
                "phase": "commentary",
                "turn_index": 2,
                "is_final": False,
                "scope_labels": ["technical_work"],
                "text": "没有 final 时保留 commentary fallback。",
            },
            {
                "id": "msg_life",
                "source_line": 30,
                "role": "user",
                "phase": "",
                "turn_index": 3,
                "is_final": False,
                "scope_labels": ["personal_reflection", "idea_seed", "life_context"],
                "text": "最近我有个点子，想把焦虑和生活里的长期问题也保留下来。",
            },
        ]
        with (self.source / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for message in messages:
                f.write(json.dumps(message, ensure_ascii=False) + "\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_searches_clean_source_without_raw_rollout(self) -> None:
        result = search.search_clean_source(self.cwd, ["原文记忆库"], limit=5)

        self.assertEqual(result["source"], str(self.source / "messages.jsonl"))
        self.assertEqual(result["matches"][0]["source_line"], 13)
        self.assertEqual(result["matches"][0]["phase"], "final_answer")
        self.assertEqual(result["matches"][0]["scope_labels"], ["technical_work"])
        self.assertIn("AIppocampus 是清洗后的原文记忆库", result["matches"][0]["snippet"])

    def test_filters_by_scope_label(self) -> None:
        result = search.search_clean_source(self.cwd, ["长期问题"], scope_labels=["life_context"], limit=5)

        self.assertEqual(len(result["matches"]), 1)
        self.assertEqual(result["scope_labels"], ["life_context"])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["matches"][0]["id"], "msg_life")
        self.assertIn("life_context", result["matches"][0]["scope_labels"])

    def test_scope_filter_uses_dynamic_semantic_scope_label_sidecar(self) -> None:
        with (self.source / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {
                        "id": "msg_metaphor",
                        "source_line": 44,
                        "role": "user",
                        "phase": "",
                        "turn_index": 5,
                        "is_final": False,
                        "scope_labels": [],
                        "text": (
                            "This is not a project task, but I keep circling back to the lighthouse "
                            "metaphor; it feels like a pivot, and I'm excited by it."
                        ),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        (self.source / "semantic-scope-labels.jsonl").write_text(
            json.dumps(
                {
                    "message_id": "msg_metaphor",
                    "source": "deepseek_subconscious_scope_labels",
                    "scope_labels": ["personal_reflection", "idea_seed", "life_context"],
                    "confidence": 0.94,
                    "label_evidence": [
                        {
                            "label": "personal_reflection",
                            "reason": "The source says the metaphor feels pivotal and exciting.",
                            "confidence": 0.88,
                        },
                        {
                            "label": "idea_seed",
                            "reason": "The source identifies the lighthouse metaphor as a pivot.",
                            "confidence": 0.86,
                        },
                        {
                            "label": "life_context",
                            "reason": "The source frames the metaphor as recurring lived context.",
                            "confidence": 0.94,
                        },
                    ],
                    "source_refs": [{"message_id": "msg_metaphor", "source_line": 44, "role": "user"}],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = search.search_clean_source(
            self.cwd,
            ["lighthouse metaphor pivot"],
            scope_labels=["personal_reflection", "idea_seed"],
            limit=5,
        )

        self.assertEqual(result["matches"][0]["id"], "msg_metaphor")
        self.assertEqual(result["matches"][0]["semantic_scope_labels"], ["personal_reflection", "idea_seed", "life_context"])
        self.assertIn("personal_reflection", result["matches"][0]["scope_labels"])

    def test_scope_filter_warns_for_legacy_messages_without_scope_labels(self) -> None:
        legacy = {
            "id": "msg_legacy",
            "source_line": 41,
            "role": "user",
            "phase": "",
            "turn_index": 4,
            "is_final": False,
            "text": "这个旧 clean source 里没有 scope label，但文本里有长期问题。",
        }
        with (self.source / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(legacy, ensure_ascii=False) + "\n")

        result = search.search_clean_source(self.cwd, ["长期问题"], scope_labels=["life_context"], limit=5)

        self.assertEqual(result["matches"][0]["id"], "msg_life")
        self.assertEqual(result["warnings"][0]["code"], "missing_scope_labels")

    def test_unknown_scope_label_is_reported(self) -> None:
        result = search.search_clean_source(self.cwd, ["长期问题"], scope_labels=["unknown"], limit=5)

        self.assertEqual(result["matches"], [])
        self.assertEqual(result["warnings"][0]["code"], "unknown_scope_label")

    def test_registry_deep_search_prefers_clean_source_without_sqlite(self) -> None:
        entry = {
            "paths": {
                "clean_source_messages_jsonl": str(self.source / "messages.jsonl"),
                "sqlite": str(self.cwd / "missing.sqlite"),
            }
        }

        score, hits = registry.deep_search_entry(entry, ["原文记忆库"], max_hits=2)

        self.assertGreater(score, 0)
        self.assertEqual(hits[0]["line"], 13)
        self.assertEqual(hits[0]["phase"], "final_answer")

    def test_registry_deep_search_result_reports_clean_source_read_error(self) -> None:
        bad_messages = self.cwd / "bad_messages.jsonl"
        bad_messages.mkdir()
        entry = {
            "paths": {
                "clean_source_messages_jsonl": str(bad_messages),
                "sqlite": str(self.cwd / "missing.sqlite"),
            }
        }

        result = registry.deep_search_entry_result(entry, ["原文记忆库"], max_hits=2)

        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["hits"], [])
        self.assertEqual(result["warnings"][0]["stage"], "clean_source")
        self.assertIn("bad_messages.jsonl", result["warnings"][0]["path"])

    def test_registry_search_json_includes_deep_search_warnings(self) -> None:
        bad_messages = self.cwd / "bad_messages.jsonl"
        bad_messages.mkdir()
        registry_file = self.cwd / "threads.json"
        registry_file.write_text(
            json.dumps(
                {
                    "threads": [
                        {
                            "thread_key": "session:bad-clean",
                            "title": "Bad clean-source index",
                            "keywords": ["原文记忆库"],
                            "paths": {
                                "clean_source_messages_jsonl": str(bad_messages),
                                "sqlite": str(self.cwd / "missing.sqlite"),
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with patch.object(
            sys,
            "argv",
            [
                "registry.py",
                "--registry-dir",
                str(self.cwd),
                "search",
                "原文记忆库",
                "--json",
            ],
        ), contextlib.redirect_stdout(stdout):
            code = registry.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["warnings"][0]["thread_key"], "session:bad-clean")
        self.assertEqual(payload["warnings"][0]["stage"], "clean_source")


if __name__ == "__main__":
    unittest.main()
