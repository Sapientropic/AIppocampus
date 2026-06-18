from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

from aippocampus_runtime.registry import api as registry  # noqa: E402
from aippocampus_runtime.source import search as search  # noqa: E402


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

        self.assertEqual(
            Path(result["source"]).resolve(),
            (self.source / "messages.jsonl").resolve(),
        )
        self.assertEqual(result["matches"][0]["source_line"], 13)
        self.assertEqual(result["matches"][0]["phase"], "final_answer")
        self.assertEqual(result["matches"][0]["scope_labels"], ["technical_work"])
        self.assertIn("AIppocampus 是清洗后的原文记忆库", result["matches"][0]["snippet"])

    def test_search_does_not_search_source_texture_by_default(self) -> None:
        (self.source / "source-texture.jsonl").write_text(
            json.dumps(
                {
                    "texture_id": "tex_1",
                    "signal_kind": "tool_failure_texture",
                    "signal_detail": "verification_failure",
                    "signal_labels": ["texture_only_probe"],
                    "truth_boundary": "texture_signal_not_source_fact",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        result = search.search_clean_source(self.cwd, ["texture_only_probe"], limit=5)

        self.assertEqual(result["matches"], [])
        self.assertEqual(
            Path(result["source"]).resolve(),
            (self.source / "messages.jsonl").resolve(),
        )

    def test_human_search_output_leads_with_source_backed_snippet_receipt(self) -> None:
        stdout = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "search_clean_source.py",
                    "原文记忆库",
                    "--cwd",
                    str(self.cwd),
                ],
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = search.main()

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Source-backed snippets", output)
        self.assertIn("Source:", output)
        self.assertIn("turn 1", output)
        self.assertIn("AIppocampus 是清洗后的原文记忆库", output)
        self.assertIn("Next:", output)

    def test_human_search_output_is_action_card_not_ranking_trace(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "原文记忆库",
                    "--cwd",
                    str(self.cwd),
                    "--clean-source-dir",
                    str(self.source),
                ]
            )

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Source-backed action cards", output)
        self.assertIn("boundary:", output)
        self.assertNotIn("role=", output)
        self.assertNotIn("phase=", output)
        self.assertNotIn("score=", output)

    def test_public_metadata_only_human_search_renders_receipt_not_none_snippet(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "原文记忆库",
                    "--cwd",
                    str(self.cwd),
                    "--clean-source-dir",
                    str(self.source),
                    "--public",
                ]
            )

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("snippet omitted in public mode", output)
        self.assertNotIn('"None"', output)

    def test_search_marks_process_noise_and_demotes_it_behind_source_receipts(self) -> None:
        with (self.source / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {
                        "id": "msg_process",
                        "source_line": 40,
                        "role": "assistant",
                        "phase": "commentary",
                        "turn_index": 4,
                        "text": (
                            "<subagent_notification> first recall first recall first recall "
                            "process details only </subagent_notification>"
                        ),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            f.write(
                json.dumps(
                    {
                        "id": "msg_real",
                        "source_line": 41,
                        "role": "assistant",
                        "phase": "final_answer",
                        "turn_index": 4,
                        "is_final": True,
                        "text": "The first recall receipt is source-backed and ready to reopen.",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        result = search.search_clean_source(
            self.cwd,
            ["first recall"],
            clean_source_dir=self.source,
            limit=2,
        )
        by_id = {match["id"]: match for match in result["matches"]}

        self.assertEqual(result["matches"][0]["id"], "msg_real")
        self.assertTrue(by_id["msg_process"]["search_noise"])
        self.assertEqual(by_id["msg_process"]["noise_reason"], "process_notification")

    def test_human_search_no_result_gives_vague_cue_refinements_without_evidence_claim(self) -> None:
        stdout = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "search_clean_source.py",
                    "不存在的旧短语",
                    "--cwd",
                    str(self.cwd),
                ],
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = search.main()

        output = stdout.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("No source-backed snippet found", output)
        self.assertIn("Possible routes, not yet evidence", output)
        self.assertIn("exact phrase", output)
        self.assertIn("project cue", output)
        self.assertIn("time cue", output)

    def test_filters_by_scope_label(self) -> None:
        result = search.search_clean_source(
            self.cwd, ["长期问题"], scope_labels=["life_context"], limit=5
        )

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
                    "source_refs": [
                        {"message_id": "msg_metaphor", "source_line": 44, "role": "user"}
                    ],
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
        self.assertEqual(
            result["matches"][0]["semantic_scope_labels"],
            ["personal_reflection", "idea_seed", "life_context"],
        )
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

        result = search.search_clean_source(
            self.cwd, ["长期问题"], scope_labels=["life_context"], limit=5
        )

        self.assertEqual(result["matches"][0]["id"], "msg_life")
        self.assertEqual(result["warnings"][0]["code"], "missing_scope_labels")

    def test_unknown_scope_label_is_reported(self) -> None:
        result = search.search_clean_source(
            self.cwd, ["长期问题"], scope_labels=["unknown"], limit=5
        )

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
        with (
            patch.object(
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
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = registry.main()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["warnings"][0]["thread_key"], "session:bad-clean")
        self.assertEqual(payload["warnings"][0]["stage"], "clean_source")

    def test_cli_json_redacts_source_path_by_default_and_can_opt_in(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "AIppocampus",
                    "--cwd",
                    str(self.cwd),
                    "--clean-source-dir",
                    str(self.source),
                    "--json",
                ]
            )
        public_payload = json.loads(stdout.getvalue())

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            include_code = search.main(
                [
                    "AIppocampus",
                    "--cwd",
                    str(self.cwd),
                    "--clean-source-dir",
                    str(self.source),
                    "--include-paths",
                    "--json",
                ]
            )
        private_payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(include_code, 0)
        self.assertNotIn(str(self.cwd), json.dumps(public_payload, ensure_ascii=False))
        self.assertEqual(public_payload["source"], search.LOCAL_PATH_REDACTION)
        self.assertFalse(public_payload["privacy"]["paths_included"])
        self.assertEqual(
            private_payload["source"],
            str(self.source / "messages.jsonl"),
        )
        self.assertTrue(private_payload["privacy"]["paths_included"])

    def test_successful_cli_json_includes_foreground_authority_envelope(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "AIppocampus",
                    "--cwd",
                    str(self.cwd),
                    "--clean-source-dir",
                    str(self.source),
                    "--json",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["kind"], "aippocampus_search_result")
        self.assertEqual(payload["entry_state"], "explicit_search_invoked")
        self.assertEqual(payload["route_state"], "source_refs_available")
        self.assertEqual(payload["claim_permission"], "bounded_search_receipt_requires_reopen")
        self.assertEqual(payload["source_boundary"]["authority"], "bounded_evidence")
        self.assertTrue(payload["source_boundary"]["source_reopen_required_before_claim"])
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(payload["foreground_action"], payload["agent_next_action"])
        self.assertEqual(payload["safe_next_actions"][0], payload["foreground_action"])
        self.assertEqual(payload["foreground_action"]["id"], "reopen_search_match_source")
        self.assertNotIn("action_id", payload["foreground_action"])
        self.assertEqual(payload["foreground_action"]["tool_name"], "get_turn_context")
        self.assertEqual(payload["foreground_action"]["arguments"]["message_id"], "msg_final")
        self.assertEqual(payload["foreground_action"]["claim_boundary"], "source_reopen_required_before_claim")
        self.assertIn("matches", payload)

    def test_empty_cli_json_includes_no_route_authority_envelope(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "missing phrase",
                    "--cwd",
                    str(self.cwd),
                    "--clean-source-dir",
                    str(self.source),
                    "--json",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "no_matches")
        self.assertEqual(payload["claim_permission"], "no_claim_before_source_match")
        self.assertEqual(payload["source_boundary"]["authority"], "direction_only")
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v1")
        self.assertEqual(payload["foreground_action"], payload["agent_next_action"])
        self.assertEqual(payload["safe_next_actions"][0], payload["foreground_action"])
        self.assertEqual(payload["foreground_action"]["id"], "refine_or_recall")
        self.assertNotIn("action_id", payload["foreground_action"])
        self.assertEqual(payload["foreground_action"]["tool_name"], "agent_recall")

    def test_registry_search_cli_can_request_deep_budget(self) -> None:
        registry_file = self.cwd / "threads.json"
        registry_file.write_text(
            json.dumps(
                {
                    "threads": [
                        {
                            "thread_key": "session:deep-budget",
                            "title": "Deep budget thread",
                            "keywords": ["needle"],
                            "paths": {"sqlite": str(self.cwd / "missing.sqlite")},
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        captured: dict = {}

        def fake_deep_search(entry: dict, terms: list[str], **kwargs: object) -> dict:
            captured["budget"] = kwargs.get("search_budget")
            return {"score": 1.0, "hits": [], "warnings": []}

        stdout = io.StringIO()
        with (
            patch.object(registry, "deep_search_entry_result", side_effect=fake_deep_search),
            patch.object(
                sys,
                "argv",
                [
                    "registry.py",
                    "--registry-dir",
                    str(self.cwd),
                    "search",
                    "needle",
                    "--search-budget",
                    "deep",
                    "--json",
                ],
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = registry.main()

        self.assertEqual(code, 0)
        self.assertIs(captured["budget"], registry.REGISTRY_SEARCH_DEEP_BUDGET)


if __name__ == "__main__":
    unittest.main()
