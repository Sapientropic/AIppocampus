from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aippocampus_runtime import core
from aippocampus_runtime.cli import facade as cli_facade
from aippocampus_runtime.contracts import foreground_action_contract_violations
from aippocampus_runtime.registry import api as registry
from aippocampus_runtime.source import search as search
from tests.aippocampus.frontstage_assertions import assert_semantic_human_output


class SearchCleanSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.registry_root = self.cwd / "registry-default"
        self.env_patch = patch.dict(
            "os.environ",
            {"AIPPOCAMPUS_REGISTRY_DIR": str(self.registry_root)},
        )
        self.env_patch.start()
        self.source = core.default_thread_clean_source_dir(self.cwd)
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
        self.env_patch.stop()
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

    def test_search_reports_malformed_jsonl_loss_without_losing_valid_rows(self) -> None:
        with (self.source / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write("{not-json}\n")
            f.write(json.dumps(["not", "an", "object"], ensure_ascii=False) + "\n")
            f.write(
                json.dumps(
                    {
                        "id": "msg_after_bad_row",
                        "source_line": 90,
                        "role": "assistant",
                        "phase": "final_answer",
                        "turn_index": 9,
                        "is_final": True,
                        "scope_labels": ["technical_work"],
                        "text": "The recall surface should still find this unique valid row.",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        result = search.search_clean_source(self.cwd, ["unique valid row"], limit=5)

        self.assertEqual(result["matches"][0]["id"], "msg_after_bad_row")
        self.assertEqual(result["jsonl_loss"]["invalid_json_line_count"], 1)
        self.assertEqual(result["jsonl_loss"]["non_object_line_count"], 1)
        warning = next(item for item in result["warnings"] if item["code"] == "jsonl_read_degraded")
        self.assertEqual(warning["stage"], "clean_source")
        self.assertEqual(warning["path"], "messages.jsonl")

    def test_search_uses_cjk_sidecar_terms_for_near_exact_phrase(self) -> None:
        with (self.source / "messages.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {
                        "id": "msg_cjk_route",
                        "source_line": 50,
                        "role": "assistant",
                        "phase": "final_answer",
                        "turn_index": 5,
                        "is_final": True,
                        "scope_labels": ["technical_work"],
                        "text": "复开源头路线有界证据需要先看 source。",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        result = search.search_clean_source(self.cwd, ["复开源头路线有界材料"], limit=5)

        self.assertEqual(result["matches"][0]["id"], "msg_cjk_route")
        self.assertIn("源头路线", result["query_terms"])
        self.assertIn("复开源头路线有界证据", result["matches"][0]["snippet"])

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
        self.assertIn("Source-backed matches", output)
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
        self.assertIn("Source-backed matches", output)
        self.assertEqual(output.count("Boundary:"), 1)
        assert_semantic_human_output(self, output, max_lines=8)
        self.assertNotIn("role=", output)
        self.assertNotIn("phase=", output)
        self.assertNotIn("score=", output)

    def test_public_human_search_renders_capped_snippet_receipt(self) -> None:
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
        self.assertIn("AIppocampus 是清洗后的原文记忆库", output)
        self.assertNotIn("snippet omitted in public mode", output)
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
        self.assertIn("current resolved thread clean-source directory only", output)
        self.assertIn("Next:", output)
        assert_semantic_human_output(self, output, max_lines=8)
        self.assertNotIn("Possible routes, not yet evidence", output)
        self.assertNotIn("- exact phrase:", output)
        self.assertNotIn("- project cue:", output)
        self.assertNotIn("- time cue:", output)

    def test_registry_no_match_human_output_is_action_led_without_low_level_warning(self) -> None:
        output = search.render_human_search_result(
            {
                "kind": "aippocampus_registry_source_search",
                "status": "no_phrase_like_matches",
                "search_scope": "registered_clean_source_and_indexes",
                "scope_description": "registered clean-source/index entries across the local registry",
                "query_text": "over conservative verbose cannot_claim navigation_only compact foreground payload",
                "query_terms": [
                    "over",
                    "conservative",
                    "verbose",
                    "cannot_claim",
                    "navigation_only",
                    "compact",
                    "foreground",
                    "payload",
                ],
                "suppressed_low_coverage_match_count": 2044,
                "matches": [],
                "warnings": [{"code": None, "message": "unable to open database file"}],
            }
        )

        self.assertIn("No exact or phrase-like source match found", output)
        self.assertIn("Next: try a shorter source search", output)
        self.assertIn("aippocampus search --all", output)
        self.assertIn("conservative verbose cannot_claim", output)
        self.assertIn("source index note:", output)
        self.assertNotIn("warning: None", output)
        self.assertNotIn("Possible routes, not yet evidence", output)

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

    def test_registry_search_json_defaults_to_safe_diagnostic_summary(self) -> None:
        registry_file = self.cwd / "threads.json"
        registry_file.write_text(
            json.dumps(
                {
                    "threads": [
                        {
                            "thread_key": "session:rawish",
                            "title": "Raw-ish registry entry",
                            "keywords": ["needle"],
                            "session_meta": {"base_instructions": "do not emit this blob"},
                            "paths": {
                                "workspace": str(self.cwd / "private-workspace"),
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
                    "needle",
                    "--json",
                    "--redact-paths",
                ],
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = registry.main()
        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "aippocampus_registry_search_diagnostic")
        self.assertEqual(payload["output_boundary"], "diagnostic_summary_not_foreground_recall")
        self.assertFalse(payload["privacy"]["raw_registry_entries_emitted"])
        self.assertFalse(payload["privacy"]["paths_included"])
        self.assertFalse(payload["privacy"]["session_meta_emitted"])
        self.assertIn("aippocampus search --all", payload["safe_alternative_command"])
        self.assertNotIn('"session_meta":', encoded)
        self.assertNotIn('"paths":', encoded)
        self.assertNotIn("private-workspace", encoded)
        self.assertNotIn("base_instructions", encoded)

        diagnostic_stdout = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "registry.py",
                    "--registry-dir",
                    str(self.cwd),
                    "search",
                    "needle",
                    "--json",
                    "--redact-paths",
                    "--diagnostic-entries",
                ],
            ),
            contextlib.redirect_stdout(diagnostic_stdout),
        ):
            diagnostic_code = registry.main()
        diagnostic = json.loads(diagnostic_stdout.getvalue())

        self.assertEqual(diagnostic_code, 0)
        self.assertEqual(diagnostic["kind"], "aippocampus_registry_search_diagnostic_entries")
        self.assertTrue(diagnostic["privacy"]["raw_registry_entries_emitted"])
        self.assertIn("session_meta", json.dumps(diagnostic, ensure_ascii=False))

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
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn(payload["foreground_action"], payload.get("safe_next_actions", []))
        self.assertEqual(payload["foreground_action"]["id"], "reopen_search_match_source")
        self.assertNotIn("action_id", payload["foreground_action"])
        self.assertEqual(payload["foreground_action"]["tool_name"], "get_turn_context")
        self.assertEqual(payload["foreground_action"]["arguments"]["message_id"], "msg_final")
        self.assertEqual(
            payload["foreground_action"]["command"],
            "aippocampus search --open-current-source --message-id msg_final --json",
        )
        self.assertTrue(payload["foreground_action"]["cli_equivalent_for_tool_action"])
        self.assertEqual(
            payload["matches"][0]["reopen_command"],
            payload["foreground_action"]["command"],
        )
        self.assertIn("source_window_command", payload["matches"][0])
        self.assertEqual(payload["foreground_action"]["claim_boundary"], "source_reopen_required_before_claim")
        self.assertEqual(foreground_action_contract_violations(payload), [])
        self.assertIn("matches", payload)

    def test_current_thread_search_reopen_command_opens_bounded_source_window(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--open-current-source",
                    "--message-id",
                    "msg_final",
                    "--cwd",
                    str(self.cwd),
                    "--clean-source-dir",
                    str(self.source),
                    "--json",
                ]
            )

        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "aippocampus_current_thread_source_window")
        self.assertEqual(payload["status"], "source_open")
        self.assertEqual(payload["source_boundary"]["authority"], "source_open")
        self.assertEqual(payload["metrics"]["source_reopen_success"], True)
        self.assertGreaterEqual(payload["metrics"]["window_message_count"], 1)
        self.assertIn("AIppocampus 是清洗后的原文记忆库", encoded)
        self.assertNotIn(str(self.cwd), encoded)

    def test_human_search_result_prints_current_thread_reopen_command(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "AIppocampus",
                    "--cwd",
                    str(self.cwd),
                    "--clean-source-dir",
                    str(self.source),
                ]
            )

        self.assertEqual(code, 0)
        self.assertIn(
            "reopen: aippocampus search --open-current-source --message-id msg_final --json",
            stdout.getvalue(),
        )

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
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn(payload["foreground_action"], payload.get("safe_next_actions", []))
        self.assertEqual(payload["foreground_action"]["id"], "refine_or_recall")
        self.assertNotIn("action_id", payload["foreground_action"])
        self.assertEqual(payload["foreground_action"]["tool_name"], "agent_recall")
        self.assertEqual(foreground_action_contract_violations(payload), [])
        self.assertIn("current resolved thread clean-source directory only", payload["searched_scope"])
        self.assertIn(
            'aippocampus search --all "distinctive exact phrase" --json',
            payload["recovery_actions"],
        )

    def test_empty_query_json_is_needs_input_not_no_match(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "   ",
                    "--cwd",
                    str(self.cwd),
                    "--clean-source-dir",
                    str(self.source),
                    "--json",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "needs_input")
        self.assertEqual(payload["error"]["code"], "search_cue_required")
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn(payload["foreground_action"], payload.get("safe_next_actions", []))
        self.assertTrue(
            set(payload["foreground_action"]["requires"]) & {"query", "cue", "exact_phrase"}
        )
        self.assertNotIn(
            "Search found no source-backed snippet",
            json.dumps(payload, ensure_ascii=False),
        )

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

    def test_search_help_names_current_thread_scope_not_global_memory(self) -> None:
        stdout = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            self.assertRaises(SystemExit) as raised,
        ):
            search.main(["--help"])

        output = stdout.getvalue()
        normalized_output = " ".join(output.split())
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("current resolved thread clean-source directory only", normalized_output)
        self.assertIn("aippocampus search --all", output)
        self.assertNotIn("global clean source", output)

    def test_facade_exposes_registry_command(self) -> None:
        invocation = cli_facade.resolve_command(["registry", "search", "needle"])

        self.assertIsNotNone(invocation)
        assert invocation is not None
        self.assertEqual(invocation.command, "registry")
        self.assertEqual(invocation.module_name, "aippocampus_runtime.registry.api")

    def test_registry_search_help_uses_supported_command_name(self) -> None:
        stdout = io.StringIO()
        with (
            patch.object(sys, "argv", ["registry.py", "search", "--help"]),
            contextlib.redirect_stdout(stdout),
            self.assertRaises(SystemExit) as raised,
        ):
            registry.main()

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("usage: aippocampus registry search", stdout.getvalue())

    def test_search_all_registry_returns_cross_thread_snippets_without_paths_by_default(
        self,
    ) -> None:
        second_clean = self.cwd / "thread-two" / "clean-source"
        second_clean.mkdir(parents=True)
        third_clean = self.cwd / "thread-three" / "clean-source"
        third_clean.mkdir(parents=True)
        for path, message_id, text in (
            (
                second_clean,
                "msg_second",
                "The cross-thread exact registry phrase lives in the second thread.",
            ),
            (
                third_clean,
                "msg_third",
                "Another cross-thread exact registry phrase appears in a later thread.",
            ),
        ):
            with (path / "messages.jsonl").open("w", encoding="utf-8", newline="\n") as f:
                f.write(
                    json.dumps(
                        {
                            "id": message_id,
                            "message_id": message_id,
                            "source_line": 7,
                            "role": "assistant",
                            "phase": "final_answer",
                            "turn_index": 2,
                            "is_final": True,
                            "text": text,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        (self.cwd / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:two",
                            "title": "Second thread",
                            "paths": {
                                "workspace": str(self.cwd / "project-two"),
                                "clean_source_messages_jsonl": str(second_clean / "messages.jsonl"),
                                "sqlite": str(self.cwd / "missing-two.sqlite"),
                            },
                        },
                        {
                            "thread_key": "session:three",
                            "title": "Third thread",
                            "paths": {
                                "workspace": str(self.cwd / "project-three"),
                                "clean_source_messages_jsonl": str(third_clean / "messages.jsonl"),
                                "sqlite": str(self.cwd / "missing-three.sqlite"),
                            },
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--all",
                    "cross-thread exact registry phrase",
                    "--registry-dir",
                    str(self.cwd),
                    "--cwd",
                    str(self.cwd),
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["kind"], "aippocampus_registry_source_search")
        self.assertEqual(payload["search_scope"], "registered_clean_source_and_indexes")
        self.assertEqual(payload["match_count"], 2)
        self.assertEqual(
            {match["thread"]["thread_key"] for match in payload["matches"]},
            {"session:two", "session:three"},
        )
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(str(self.cwd), encoded)
        self.assertEqual(payload["registry"], search.LOCAL_PATH_REDACTION)
        self.assertFalse(payload["privacy"]["paths_included"])
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", payload)
        self.assertNotIn(payload["foreground_action"], payload.get("safe_next_actions", []))
        self.assertEqual(payload["foreground_action"]["id"], "open_registry_search_source_window")
        self.assertEqual(payload["matches"][0]["hit_index"], 1)
        self.assertIn("hit_selector", payload["matches"][0])
        self.assertNotIn("score", payload["matches"][0])
        self.assertNotIn("query_match_profile", payload["matches"][0])
        self.assertNotIn("query_match_gate", payload)
        self.assertIn("diagnostic_detail_command", payload)
        self.assertIn("--open-source", payload["matches"][0]["reopen_command"])
        self.assertEqual(
            payload["matches"][0]["reopen_command"],
            payload["matches"][0]["source_window_command"],
        )
        self.assertEqual(
            payload["matches"][0]["last_search_reopen_command"],
            "aippocampus search --hit 1 --last-search --json",
        )
        self.assertIn("source_window_command", payload["matches"][0])
        self.assertEqual(foreground_action_contract_violations(payload), [])

        reopen_stdout = io.StringIO()
        with contextlib.redirect_stdout(reopen_stdout):
            reopen_code = search.main(
                [
                    "--hit",
                    "1",
                    "--last-search",
                    "--registry-dir",
                    str(self.cwd),
                    "--cwd",
                    str(self.cwd),
                    "--json",
                ]
            )
        reopened = json.loads(reopen_stdout.getvalue())

        self.assertEqual(reopen_code, 0)
        self.assertEqual(reopened["kind"], "aippocampus_registry_source_window")
        self.assertTrue(reopened["metrics"]["source_reopen_success"])
        self.assertEqual(reopened["source_boundary"]["authority"], "source_open")
        self.assertIn(
            "cross-thread exact registry phrase",
            json.dumps(reopened["source_window"], ensure_ascii=False),
        )
        self.assertNotIn(str(self.cwd), json.dumps(reopened, ensure_ascii=False))

    def test_search_all_registry_collapses_mirrored_duplicate_snippets(self) -> None:
        duplicate_text = "主动回忆层 潜意识 momentum line_topology Dream mirrored source note."
        unique_text = "主动回忆层 潜意识 momentum line_topology Dream unique follow-up route."
        threads = []
        for index in range(1, 5):
            clean = self.cwd / f"mirror-{index}" / "clean-source"
            clean.mkdir(parents=True)
            text = duplicate_text if index < 4 else unique_text
            (clean / "messages.jsonl").write_text(
                json.dumps(
                    {
                        "id": f"msg_mirror_{index}",
                        "message_id": f"msg_mirror_{index}",
                        "source_line": index,
                        "role": "assistant",
                        "phase": "final_answer",
                        "is_final": True,
                        "text": text,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            threads.append(
                {
                    "thread_key": f"session:mirror-{index}",
                    "title": f"Mirror {index}",
                    "paths": {
                        "clean_source_messages_jsonl": str(clean / "messages.jsonl"),
                        "sqlite": str(self.cwd / f"missing-{index}.sqlite"),
                    },
                }
            )
        (self.cwd / "threads.json").write_text(
            json.dumps({"schema_version": 1, "threads": threads}, ensure_ascii=False),
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--all",
                    "主动回忆层 潜意识 momentum line_topology Dream",
                    "--registry-dir",
                    str(self.cwd),
                    "--cwd",
                    str(self.cwd),
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["match_count"], 2)
        self.assertEqual(payload["duplicate_cluster_count"], 1)
        self.assertEqual(payload["duplicate_collapsed_hit_count"], 2)
        duplicate = next(match for match in payload["matches"] if match.get("duplicate_count"))
        self.assertEqual(duplicate["source_count"], 3)
        self.assertTrue(any("unique follow-up" in match["snippet"] for match in payload["matches"]))

    def test_search_all_discussion_id_surfaces_atlas_pointer_before_registry_chatter(self) -> None:
        atlas = self.cwd / "docs" / "research"
        atlas.mkdir(parents=True)
        (atlas / "discussion-atlas.md").write_text(
            "\n".join(
                [
                    "| Discussion | Layer | Status | Owner | Execution / evidence | Next action | Cannot claim |",
                    "| --- | --- | --- | --- | --- | --- | --- |",
                    "| [#2127 Moving Ground: source-backed memory and continuous craft](https://github.com/Sapientropic/AIppocampus/discussions/2127) | route_attention | active_design | [agent-native recall facade](../architecture/recall/agent-native-recall-facade.md) | #2489 | Keep a compact atlas pointer recallable. | Discussion row as source truth. |",
                ]
            ),
            encoding="utf-8",
        )
        (self.cwd / "threads.json").write_text(
            json.dumps({"schema_version": 1, "threads": []}, ensure_ascii=False),
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--all",
                    "discussion 2127",
                    "--registry-dir",
                    str(self.cwd),
                    "--cwd",
                    str(self.cwd),
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 1)
        self.assertEqual(payload["foreground_action"]["id"], "open_discussion_atlas_pointer")
        self.assertEqual(payload["discussion_atlas_pointer"]["discussion"], 2127)
        self.assertIn("/discussions/2127", json.dumps(payload, ensure_ascii=False))

    def test_search_all_unrelated_tooling_cue_does_not_surface_atlas_pointer(self) -> None:
        atlas = self.cwd / "docs" / "research"
        atlas.mkdir(parents=True)
        (atlas / "discussion-atlas.md").write_text(
            "\n".join(
                [
                    "| Discussion | Layer | Status | Owner | Execution / evidence | Next action | Cannot claim |",
                    "| --- | --- | --- | --- | --- | --- | --- |",
                    "| [#587 When models learn to smell memory, they still need a way back to the source](https://github.com/Sapientropic/AIppocampus/discussions/587) | source_ground | current_contract | [agent-native recall facade](../architecture/recall/agent-native-recall-facade.md) | MCP/CLI recall tests | Keep deepen/reopen visible. | Scent/support as source evidence. |",
                ]
            ),
            encoding="utf-8",
        )
        (self.cwd / "threads.json").write_text(
            json.dumps({"schema_version": 1, "threads": []}, ensure_ascii=False),
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--all",
                    "benchmark 实测检索不弱 recall deepen 实际都好差劲",
                    "--registry-dir",
                    str(self.cwd),
                    "--cwd",
                    str(self.cwd),
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 1)
        self.assertNotEqual(payload["foreground_action"]["id"], "open_discussion_atlas_pointer")
        self.assertNotIn("discussion_atlas_pointer", payload)

    def test_search_all_surfaces_known_repo_docs_from_current_checkout(self) -> None:
        docs = self.cwd / "docs" / "architecture" / "ops"
        docs.mkdir(parents=True)
        (docs / "compatibility-shim-inventory.md").write_text(
            "# Compatibility shim inventory\n\nCompatibility historical fields inventory report.\n",
            encoding="utf-8",
        )
        (docs / "legacy-alias-inventory.md").write_text(
            "# Legacy alias inventory\n\nLegacy alias report.\n",
            encoding="utf-8",
        )
        (self.cwd / "threads.json").write_text(
            json.dumps({"schema_version": 1, "threads": []}, ensure_ascii=False),
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--all",
                    "compatibility historical fields inventory/report",
                    "--registry-dir",
                    str(self.cwd),
                    "--cwd",
                    str(self.cwd),
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(code, 0)
        self.assertEqual(payload["matches"][0]["source"], "repo_checkout_doc")
        self.assertIn("docs/architecture/ops/compatibility-shim-inventory.md", encoded)
        self.assertEqual(payload["repo_doc_match_count"], 1)
        self.assertEqual(payload["foreground_action"]["id"], "open_registry_search_source_window")
        self.assertIn("compatibility-shim-inventory.md", payload["foreground_action"]["command"])

    def test_search_all_registry_can_include_paths_as_local_diagnostic(self) -> None:
        registry_clean = self.cwd / "registry-thread" / "clean-source"
        registry_clean.mkdir(parents=True)
        (registry_clean / "messages.jsonl").write_text(
            json.dumps(
                {
                    "id": "msg_registry_path",
                    "source_line": 4,
                    "role": "user",
                    "text": "diagnostic registry path opt in phrase",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.cwd / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:path",
                            "title": "Path opt-in",
                            "paths": {
                                "workspace": str(self.cwd / "project-path"),
                                "clean_source_messages_jsonl": str(
                                    registry_clean / "messages.jsonl"
                                ),
                                "sqlite": str(self.cwd / "missing.sqlite"),
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--all",
                    "diagnostic registry path opt in phrase",
                    "--registry-dir",
                    str(self.cwd),
                    "--include-paths",
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertTrue(payload["privacy"]["paths_included"])
        self.assertEqual(
            payload["matches"][0]["local_diagnostic"]["clean_source_messages_jsonl"],
            str(registry_clean / "messages.jsonl"),
        )

    def test_search_all_registry_skips_workspace_only_entries_without_low_level_warning(self) -> None:
        (self.cwd / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "workspace:scripts:abc",
                            "title": "Workspace-only registration",
                            "paths": {"workspace": str(self.cwd / "scripts")},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--all",
                    "registry phrase",
                    "--registry-dir",
                    str(self.cwd),
                    "--cwd",
                    str(self.cwd),
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["skipped_entry_count"], 1)
        self.assertEqual(
            payload["skipped_reason_counts"],
            {"not_searchable_workspace_entry": 1},
        )
        self.assertEqual(payload["unavailable_source_count"], 0)
        self.assertEqual(payload["warnings"], [])
        self.assertNotIn("skipped_entries", payload)
        self.assertNotIn("unable to open database file", encoded)
        self.assertNotIn(str(self.cwd), encoded)

        detail_stdout = io.StringIO()
        with contextlib.redirect_stdout(detail_stdout):
            detail_code = search.main(
                [
                    "--all",
                    "registry phrase",
                    "--registry-dir",
                    str(self.cwd),
                    "--search-budget",
                    "deep",
                    "--cwd",
                    str(self.cwd),
                    "--json",
                ]
            )
        detail = json.loads(detail_stdout.getvalue())

        self.assertEqual(detail_code, 1)
        self.assertEqual(detail["skipped_entries"][0]["reason"], "not_searchable_workspace_entry")
        self.assertEqual(detail["skipped_entries"][0]["thread"]["thread_key"], "workspace:scripts:abc")

    def test_search_all_registry_reports_missing_search_artifacts_as_maintenance_action(self) -> None:
        (self.cwd / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:missing-search-artifacts",
                            "title": "Missing search artifacts",
                            "paths": {
                                "workspace": str(self.cwd / "workspace"),
                                "clean_source_messages_jsonl": str(self.cwd / "missing-messages.jsonl"),
                                "sqlite": str(self.cwd / "missing.sqlite"),
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--all",
                    "missing artifact phrase",
                    "--registry-dir",
                    str(self.cwd),
                    "--cwd",
                    str(self.cwd),
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(code, 1)
        self.assertEqual(payload["skipped_entry_count"], 1)
        self.assertEqual(
            payload["skipped_reason_counts"],
            {"configured_search_sources_missing": 1},
        )
        self.assertEqual(payload["unavailable_source_count"], 1)
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(
            payload["maintenance_actions"][0]["command"],
            "aippocampus registry audit --json",
        )
        self.assertNotIn("unable to open database file", encoded)

    def test_search_all_phrase_like_absent_query_suppresses_low_coverage_noise(self) -> None:
        noisy_clean = self.cwd / "noisy-thread" / "clean-source"
        noisy_clean.mkdir(parents=True)
        (noisy_clean / "messages.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "id": "msg_noise_1",
                            "message_id": "msg_noise_1",
                            "source_line": 3,
                            "role": "assistant",
                            "text": "The agent memory source-backed route is safe, but unrelated.",
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            "id": "msg_noise_2",
                            "message_id": "msg_noise_2",
                            "source_line": 4,
                            "role": "assistant",
                            "text": "A packet exists in another context without the remembered phrase.",
                        },
                        ensure_ascii=False,
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (self.cwd / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:noisy",
                            "title": "Noisy phrase decoy",
                            "paths": {
                                "clean_source_messages_jsonl": str(noisy_clean / "messages.jsonl"),
                                "sqlite": str(self.cwd / "missing-noisy.sqlite"),
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--all",
                    "A safe packet that leaves the agent lost is not a success",
                    "--registry-dir",
                    str(self.cwd),
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "no_phrase_like_matches")
        self.assertEqual(payload["match_count"], 0)
        self.assertEqual(payload["suppressed_low_coverage_match_count"], 2)
        self.assertNotIn("suppressed_low_coverage_matches", payload)
        self.assertNotIn("query_match_gate", payload)
        self.assertTrue(payload["source_boundary"]["phrase_like_low_coverage_suppressed"])
        self.assertEqual(payload["foreground_action_contract"], "foreground-action-v2")
        self.assertNotIn("agent_next_action", payload)

    def test_search_all_phrase_like_absent_query_suppresses_generic_two_anchor_decoy(self) -> None:
        noisy_clean = self.cwd / "generic-anchor-thread" / "clean-source"
        noisy_clean.mkdir(parents=True)
        (noisy_clean / "messages.jsonl").write_text(
            json.dumps(
                {
                    "id": "msg_generic_anchor_decoy",
                    "message_id": "msg_generic_anchor_decoy",
                    "source_line": 5,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": (
                        "No blocking findings in run_task_group_prepare; a future change could emit "
                        "a success payload before link completion or leaves stale binding state."
                    ),
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.cwd / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:generic-anchor-decoy",
                            "title": "Generic two-anchor decoy",
                            "paths": {
                                "clean_source_messages_jsonl": str(noisy_clean / "messages.jsonl"),
                                "sqlite": str(self.cwd / "missing-generic-anchor.sqlite"),
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--all",
                    "A safe packet that leaves the agent lost is not a success",
                    "--registry-dir",
                    str(self.cwd),
                    "--search-budget",
                    "deep",
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "no_phrase_like_matches")
        self.assertEqual(payload["match_count"], 0)
        self.assertEqual(payload["suppressed_low_coverage_match_count"], 1)
        self.assertTrue(payload["source_boundary"]["phrase_like_low_coverage_suppressed"])

    def test_search_all_phrase_like_present_query_ranks_exact_source_first(self) -> None:
        exact_clean = self.cwd / "exact-thread" / "clean-source"
        exact_clean.mkdir(parents=True)
        exact_phrase = "A safe packet that leaves the agent lost is not a success"
        (exact_clean / "messages.jsonl").write_text(
            json.dumps(
                {
                    "id": "msg_exact",
                    "message_id": "msg_exact",
                    "source_line": 8,
                    "role": "assistant",
                    "phase": "final_answer",
                    "is_final": True,
                    "text": f"{exact_phrase}; it should reopen source, not lecture.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.cwd / "threads.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "threads": [
                        {
                            "thread_key": "session:exact",
                            "title": "Exact phrase source",
                            "paths": {
                                "clean_source_messages_jsonl": str(exact_clean / "messages.jsonl"),
                                "sqlite": str(self.cwd / "missing-exact.sqlite"),
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = search.main(
                [
                    "--all",
                    exact_phrase,
                    "--registry-dir",
                    str(self.cwd),
                    "--search-budget",
                    "deep",
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["match_count"], 1)
        self.assertTrue(payload["matches"][0]["query_match_profile"]["exact_phrase_match"])
        self.assertEqual(payload["matches"][0]["message_id"], "msg_exact")

if __name__ == "__main__":
    unittest.main()
