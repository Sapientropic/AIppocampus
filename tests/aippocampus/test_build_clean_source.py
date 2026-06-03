from __future__ import annotations

import json
import os
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

import build_clean_source as clean_source  # noqa: E402
from conversation_sources import ConversationSourceRef, GenericConversationProvider  # noqa: E402
from tests.aippocampus.redaction_fixtures import (  # noqa: E402
    fake_test_database_dsn,
    fake_test_email,
    fake_test_windows_path,
)


class MemoryConversationProvider:
    name = "memory-test"

    def __init__(self, path: Path, cwd: Path) -> None:
        self.path = path
        self.cwd = cwd

    def discover_sessions(self):
        return [ConversationSourceRef(provider=self.name, path=self.path, session_id="port-session")]

    def locate_current(self, cwd: str | Path, *, latest: bool = False) -> ConversationSourceRef:
        del cwd, latest
        return ConversationSourceRef(
            provider=self.name,
            path=self.path,
            session_id="port-session",
            cwd=self.cwd,
        )

    def read_metadata(self, source: str | Path | ConversationSourceRef) -> dict:
        del source
        return {"id": "port-session", "cwd": str(self.cwd)}

    def thread_key(self, source: str | Path | ConversationSourceRef, meta: dict | None = None) -> str:
        del source, meta
        return "memory-test:session:port-session"

    def read_normalized_messages(
        self,
        source: str | Path | ConversationSourceRef,
        *,
        include_tools: bool = False,
    ) -> tuple[list[dict], list[dict]]:
        del source, include_tools
        messages = [
            {
                "line": 10,
                "timestamp": "2026-05-31T01:00:00Z",
                "role": "user",
                "kind": "message",
                "phase": "",
                "turn_index": 1,
                "is_final": False,
                "raw_start_line": 10,
                "raw_end_line": 10,
                "source_ref": "memory-test:session:port-session#L10",
                "provider_turn_id": "provider-turn-1",
                "sha1": "u1",
                "text": "Protocol ports must keep source evidence keys.",
            },
            {
                "line": 11,
                "timestamp": "2026-05-31T01:00:01Z",
                "role": "assistant",
                "kind": "message",
                "phase": "final_answer",
                "turn_index": 1,
                "is_final": True,
                "raw_start_line": 11,
                "raw_end_line": 11,
                "source_ref": "memory-test:session:port-session#L11",
                "provider_turn_id": "provider-turn-1",
                "sha1": "a1",
                "text": "The clean source remains source backed.",
            },
        ]
        turns = [
            {
                "id": 1,
                "user_line": 10,
                "final_line": 11,
                "fallback_assistant_line": None,
                "start_line": 10,
                "end_line": 11,
            }
        ]
        return messages, turns


class BuildCleanSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.old_codex_home = os.environ.get("CODEX_HOME")
        self.codex_home = self.cwd / "codex-home"
        os.environ["CODEX_HOME"] = str(self.codex_home)
        self.rollout = self.cwd / "rollout-test.jsonl"
        self._write_rollout()

    def tearDown(self) -> None:
        if self.old_codex_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = self.old_codex_home
        self.tmp.cleanup()

    def _append(self, item: dict) -> None:
        with self.rollout.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def _write_rollout(self) -> None:
        self._append(
            {"type": "session_meta", "payload": {"id": "session-test", "cwd": str(self.cwd)}}
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T01:00:00Z",
                "payload": {"type": "user_message", "message": "为什么我们要做 AIppocampus？"},
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T01:00:01Z",
                "payload": {
                    "type": "agent_message",
                    "phase": "commentary",
                    "message": "我先查一下旧线程。",
                },
            }
        )
        self._append(
            {
                "type": "response_item",
                "timestamp": "2026-05-26T01:00:02Z",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": "very large tool output",
                },
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T01:00:03Z",
                "payload": {
                    "type": "agent_message",
                    "phase": "final_answer",
                    "message": "AIppocampus 是一份清洗后的原文记忆库，而不是摘要。",
                },
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T01:01:00Z",
                "payload": {"type": "user_message", "message": "如果这一轮没有 final 呢？"},
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T01:01:01Z",
                "payload": {
                    "type": "agent_message",
                    "phase": "commentary",
                    "message": "那就保留末尾 commentary 作为 fallback。",
                },
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T01:02:00Z",
                "payload": {
                    "type": "user_message",
                    "message": "# AGENTS.md instructions for workspace\n重复注入，不应进 clean source。",
                },
            }
        )

    def test_clean_source_keeps_original_user_and_final_text_without_tool_noise(self) -> None:
        result = clean_source.build_clean_source(self.cwd, rollout=self.rollout)

        self.assertEqual(result["schema_version"], 2)
        self.assertEqual(
            result["upgrade_contract"]["principle"], "approximate_locate_then_exact_reconstruct"
        )
        self.assertIn("message_id", result["identity_policy"]["stable_join_keys"])
        self.assertEqual(result["artifact_scope"], "global_thread_store")
        self.assertEqual(result["source_transcript"], str(self.rollout))
        self.assertEqual(result["source_transcript_size"], self.rollout.stat().st_size)
        self.assertEqual(result["source_transcript_mtime"], self.rollout.stat().st_mtime)
        self.assertIsNone(result["source_transcript_sha256"])
        self.assertEqual(
            result["source_artifact"],
            {
                "kind": "provider_transcript",
                "provider": "codex",
                "path": str(self.rollout),
                "size": self.rollout.stat().st_size,
                "mtime": self.rollout.stat().st_mtime,
                "sha256": None,
            },
        )
        self.assertEqual(result["source_rollout"], result["source_transcript"])
        self.assertEqual(result["source_rollout_size"], result["source_transcript_size"])
        self.assertEqual(result["source_rollout_mtime"], result["source_transcript_mtime"])
        self.assertEqual(result["source_rollout_sha256"], result["source_transcript_sha256"])
        self.assertEqual(result["legacy_field_aliases"]["source_rollout"], "source_transcript")
        self.assertEqual(result["message_count"], 4)
        self.assertEqual(result["turn_count"], 2)
        messages_path = Path(result["outputs"]["messages_jsonl"])
        turns_path = Path(result["outputs"]["turns_jsonl"])
        events_path = Path(result["outputs"]["events_jsonl"])
        self.assertTrue(messages_path.exists())
        self.assertTrue(turns_path.exists())
        self.assertTrue(events_path.exists())
        self.assertIn("aippocampus-registry", str(messages_path))
        self.assertFalse((self.cwd / ".aippocampus").exists())

        messages = [
            json.loads(line) for line in messages_path.read_text(encoding="utf-8").splitlines()
        ]
        text = "\n".join(item["text"] for item in messages)

        self.assertIn("为什么我们要做 AIppocampus？", text)
        self.assertIn("AIppocampus 是一份清洗后的原文记忆库，而不是摘要。", text)
        self.assertIn("那就保留末尾 commentary 作为 fallback。", text)
        self.assertNotIn("very large tool output", text)
        self.assertNotIn("AGENTS.md instructions", text)
        self.assertNotIn("我先查一下旧线程。", text)
        events_text = events_path.read_text(encoding="utf-8")
        self.assertNotIn("very large tool output", events_text)
        events = [json.loads(line) for line in events_text.splitlines()]
        self.assertEqual(result["event_count"], 1)
        self.assertEqual(events[0]["event_kind"], "tool_call_observed")
        self.assertEqual(events[0]["behavior_backed"], True)
        self.assertIn("observation_sha256", events[0])

        first = messages[0]
        self.assertTrue(first["source_id"].startswith("src_"))
        self.assertTrue(first["turn_id"].startswith("turn_"))
        self.assertEqual(first["id"], first["message_id"])
        self.assertTrue(first["message_id"].startswith("msg_"))
        self.assertTrue(first["semantic_key"].startswith("sem_"))
        self.assertEqual(first["signature_key"], first["message_id"])
        self.assertEqual(first["raw_start_line"], first["source_line"])
        self.assertEqual(first["raw_end_line"], first["source_line"])
        self.assertEqual(first["clean_ordinal"], 0)
        self.assertEqual(len(first["content_sha256"]), 64)
        self.assertEqual(first["scope_labels"], ["technical_work", "open_question"])

        turns = [json.loads(line) for line in turns_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(turns[0]["assistant_phase"], "final_answer")
        self.assertEqual(turns[1]["assistant_phase"], "commentary_fallback")
        self.assertEqual(turns[0]["source_id"], first["source_id"])
        self.assertEqual(turns[0]["turn_id"], first["turn_id"])
        self.assertEqual(turns[0]["user_message_id"], first["message_id"])
        self.assertEqual(turns[0]["message_ids"][0], first["message_id"])
        self.assertEqual(turns[0]["clean_start_ordinal"], 0)
        self.assertEqual(turns[0]["clean_end_ordinal"], 1)
        self.assertEqual(turns[0]["scope_labels"], ["technical_work", "open_question"])

    def test_clean_source_adds_life_wide_scope_labels(self) -> None:
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T01:03:00Z",
                "payload": {
                    "type": "user_message",
                    "message": "最近我读到一篇文章，突然有个点子：把这些焦虑和长期问题也保留下来，可以吗？",
                },
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T01:03:05Z",
                "payload": {
                    "type": "agent_message",
                    "phase": "final_answer",
                    "message": "可以，它应该作为 life-wide clean source 保存，而不是只算项目任务。",
                },
            }
        )

        result = clean_source.build_clean_source(self.cwd, rollout=self.rollout)
        messages = [
            json.loads(line)
            for line in Path(result["outputs"]["messages_jsonl"])
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        turns = [
            json.loads(line)
            for line in Path(result["outputs"]["turns_jsonl"])
            .read_text(encoding="utf-8")
            .splitlines()
        ]

        life_message = next(item for item in messages if "突然有个点子" in item["text"])
        self.assertEqual(
            life_message["scope_labels"],
            ["personal_reflection", "reading_notes", "idea_seed", "life_context", "open_question"],
        )
        self.assertEqual(
            turns[2]["scope_labels"],
            [
                "personal_reflection",
                "reading_notes",
                "idea_seed",
                "life_context",
                "technical_work",
                "open_question",
            ],
        )

    def test_scope_labels_do_not_match_short_ascii_needles_inside_words(self) -> None:
        self.assertNotIn(
            "technical_work",
            clean_source.infer_scope_labels(
                "I read an article about capital cities and daily life."
            ),
        )
        self.assertIn(
            "technical_work", clean_source.infer_scope_labels("Call the API from the CLI.")
        )
        self.assertNotIn(
            "open_question",
            clean_source.infer_scope_labels("The archive should remember casual sparks."),
        )
        self.assertIn(
            "open_question", clean_source.infer_scope_labels("Should I keep casual sparks?")
        )

    def test_scope_labels_keep_fuzzy_casual_importance_out_of_static_lexicon(self) -> None:
        labels = clean_source.infer_scope_labels(
            "This is not a project task, but I keep circling back to the lighthouse metaphor; "
            "it feels like a pivot, and I'm excited by it."
        )

        self.assertEqual(labels, [])

        dissatisfied = clean_source.infer_scope_labels(
            "I'm dissatisfied with the current framing; it feels like a dilemma, not a task."
        )
        self.assertEqual(dissatisfied, [])

    def test_clean_source_drops_skill_injection_blocks(self) -> None:
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T04:00:03Z",
                "payload": {
                    "type": "user_message",
                    "message": "<skill>\n<name>aippocampus</name>\n<path>secret-local-path</path>\n---</skill>",
                },
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T04:00:04Z",
                "payload": {
                    "type": "agent_message",
                    "phase": "final_answer",
                    "message": "真实回答仍然保留。",
                },
            }
        )

        result = clean_source.build_clean_source(self.cwd, rollout=self.rollout)
        text = Path(result["outputs"]["messages_jsonl"]).read_text(encoding="utf-8")

        self.assertNotIn("<skill>", text)
        self.assertNotIn("secret-local-path", text)
        self.assertIn("真实回答仍然保留。", text)

    def test_clean_source_can_write_public_export_projection_without_replacing_canonical_text(
        self,
    ) -> None:
        private_path = fake_test_windows_path("token.py")
        email = fake_test_email()
        database_dsn = fake_test_database_dsn()
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T04:10:03Z",
                "payload": {
                    "type": "user_message",
                    "message": (
                        f"Please preserve source refs for {private_path}. "
                        f"email {email}; "
                        f"database {database_dsn}."
                    ),
                },
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T04:10:04Z",
                "payload": {
                    "type": "agent_message",
                    "phase": "final_answer",
                    "message": "Projection rows are privacy surfaces, not source truth.",
                },
            }
        )

        result = clean_source.build_clean_source(
            self.cwd,
            rollout=self.rollout,
            redaction_profiles=["public-export"],
        )

        canonical_text = Path(result["outputs"]["messages_jsonl"]).read_text(encoding="utf-8")
        self.assertIn(email, canonical_text)
        self.assertIn(database_dsn, canonical_text)
        canonical_rows = [json.loads(line) for line in canonical_text.splitlines()]

        projection_path = Path(
            result["outputs"]["redaction_profiles"]["public-export"]["messages_jsonl"]
        )
        projection_rows = [
            json.loads(line) for line in projection_path.read_text(encoding="utf-8").splitlines()
        ]
        projected_row = next(item for item in projection_rows if "<redacted:email>" in item["text"])
        projected_text = projected_row["text"]
        canonical_row = next(
            item for item in canonical_rows if item["message_id"] == projected_row["message_id"]
        )

        self.assertEqual(projected_row["redaction_profile"], "public-export")
        self.assertEqual(projected_row["source_ref"], canonical_row["source_ref"])
        self.assertEqual(projected_row["source_id"], canonical_row["source_id"])
        self.assertEqual(projected_row["content_sha256"], canonical_row["content_sha256"])
        self.assertIn("redacted_text_sha256", projected_row)
        self.assertIn("<redacted:email>", projected_text)
        self.assertIn("<redacted:connection-string>", projected_text)
        self.assertIn("<redacted:local-path>", projected_text)
        self.assertNotIn(email, projected_text)
        self.assertNotIn(database_dsn, projected_text)
        self.assertNotIn("FAKE_TEST_LOCAL_PATH", projected_text)
        self.assertEqual(
            result["redaction_profiles"]["public-export"]["source_fidelity"],
            "projection",
        )
        self.assertEqual(
            result["cleaning_policy"]["redaction_default_profile"],
            "raw-private",
        )
        self.assertEqual(
            result["cleaning_policy"]["projection_boundary"],
            "redacted profiles preserve join keys but are not canonical source truth",
        )

    def test_clean_source_builds_from_provider_normalized_generic_transcript(self) -> None:
        transcript = self.cwd / "generic.jsonl"
        rows = [
            {
                "session_id": "generic-clean",
                "timestamp": "2026-05-30T04:10:00Z",
                "cwd": str(self.cwd),
                "role": "user",
                "text": "generic import should keep source refs",
                "turn_id": "t1",
            },
            {
                "session_id": "generic-clean",
                "timestamp": "2026-05-30T04:10:01Z",
                "cwd": str(self.cwd),
                "role": "assistant",
                "text": "generic import builds clean source",
                "turn_id": "t1",
            },
        ]
        transcript.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )

        result = clean_source.build_clean_source(
            self.cwd,
            rollout=transcript,
            output_dir=self.cwd / "generic-clean-source",
            provider_name="generic-jsonl",
            provider=GenericConversationProvider(transcript),
        )

        self.assertEqual(result["source_provider"], "generic-jsonl")
        self.assertEqual(result["source_thread_key"], "generic-jsonl:session:generic-clean")
        self.assertEqual(result["source_artifact"]["provider"], "generic-jsonl")
        self.assertEqual(result["source_artifact"]["path"], str(transcript))
        self.assertEqual(result["source_rollout"], result["source_transcript"])
        self.assertEqual(
            result["legacy_field_aliases"]["source_rollout_sha256"],
            "source_transcript_sha256",
        )
        self.assertIn("source_ref", result["identity_policy"]["stable_join_keys"])
        messages = [
            json.loads(line)
            for line in Path(result["outputs"]["messages_jsonl"])
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(messages[0]["source_ref"], "generic-jsonl:session:generic-clean#L1")
        self.assertEqual(messages[1]["source_ref"], "generic-jsonl:session:generic-clean#L2")

    def test_protocol_provider_port_preserves_source_evidence_keys(self) -> None:
        source = self.cwd / "memory-provider.jsonl"
        source.write_text("placeholder for provider-owned source\n", encoding="utf-8")
        provider = MemoryConversationProvider(source, self.cwd)

        result = clean_source.build_clean_source(
            self.cwd,
            rollout=source,
            output_dir=self.cwd / "memory-clean-source",
            provider_name=provider.name,
            provider=provider,
        )

        self.assertEqual(result["source_provider"], "memory-test")
        self.assertEqual(result["source_thread_key"], "memory-test:session:port-session")
        self.assertIn("source_ref", result["identity_policy"]["stable_join_keys"])
        self.assertIn("message_id", result["identity_policy"]["stable_join_keys"])
        messages = [
            json.loads(line)
            for line in Path(result["outputs"]["messages_jsonl"])
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        turns = [
            json.loads(line)
            for line in Path(result["outputs"]["turns_jsonl"])
            .read_text(encoding="utf-8")
            .splitlines()
        ]

        self.assertEqual(messages[0]["source_ref"], "memory-test:session:port-session#L10")
        self.assertEqual(messages[1]["source_ref"], "memory-test:session:port-session#L11")
        self.assertEqual(messages[0]["source_id"], result["source_id"])
        self.assertEqual(turns[0]["source_id"], result["source_id"])
        self.assertEqual(turns[0]["user_message_id"], messages[0]["message_id"])
        self.assertEqual(turns[0]["assistant_message_id"], messages[1]["message_id"])
        self.assertNotIn("truth", messages[0])

    def test_provider_thread_identity_keeps_source_id_stable_across_path_moves(self) -> None:
        rows = [
            {
                "session_id": "path-move-stable",
                "timestamp": "2026-05-30T04:20:00Z",
                "cwd": str(self.cwd),
                "role": "user",
                "text": "path moves should not change source identity",
            },
            {
                "session_id": "path-move-stable",
                "timestamp": "2026-05-30T04:20:01Z",
                "cwd": str(self.cwd),
                "role": "assistant",
                "text": "source ids come from provider thread keys when available",
            },
        ]
        first = self.cwd / "first" / "generic.jsonl"
        second = self.cwd / "second" / "generic.jsonl"
        first.parent.mkdir()
        second.parent.mkdir()
        payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
        first.write_text(payload, encoding="utf-8")
        second.write_text(payload, encoding="utf-8")

        first_manifest = clean_source.build_clean_source(
            self.cwd,
            rollout=first,
            output_dir=self.cwd / "first-clean",
            provider_name="generic-jsonl",
            provider=GenericConversationProvider(first),
        )
        second_manifest = clean_source.build_clean_source(
            self.cwd,
            rollout=second,
            output_dir=self.cwd / "second-clean",
            provider_name="generic-jsonl",
            provider=GenericConversationProvider(second),
        )

        self.assertEqual(first_manifest["source_thread_key"], "generic-jsonl:session:path-move-stable")
        self.assertEqual(first_manifest["source_id"], second_manifest["source_id"])
        first_message = json.loads(
            Path(first_manifest["outputs"]["messages_jsonl"])
            .read_text(encoding="utf-8")
            .splitlines()[0]
        )
        second_message = json.loads(
            Path(second_manifest["outputs"]["messages_jsonl"])
            .read_text(encoding="utf-8")
            .splitlines()[0]
        )
        self.assertEqual(first_message["source_id"], second_message["source_id"])

    def test_clean_source_events_record_tool_failure_without_raw_payload(self) -> None:
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T02:00:00Z",
                "payload": {"type": "user_message", "message": "跑一下测试。"},
            }
        )
        self._append(
            {
                "type": "response_item",
                "timestamp": "2026-05-26T02:00:01Z",
                "payload": {
                    "type": "function_call",
                    "name": "functions.shell_command",
                    "call_id": "call-test-fail",
                    "arguments": json.dumps(
                        {
                            "command": (
                                "python tests\\aippocampus\\test_secret.py "
                                "C:\\Users\\Administrator\\secret\\tests\\test_token.py "
                                "API_KEY=super-secret"
                            )
                        },
                        ensure_ascii=False,
                    ),
                },
            }
        )
        self._append(
            {
                "type": "response_item",
                "timestamp": "2026-05-26T02:00:02Z",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-test-fail",
                    "output": (
                        "Exit code: 1\nWall time: 0.1s\n"
                        "Traceback from C:\\Users\\Administrator\\secret\\tests\\test_token.py\n"
                        "SECRET_PATH\\test_secret.py failed with API_KEY=super-secret"
                    ),
                },
            }
        )

        result = clean_source.build_clean_source(self.cwd, rollout=self.rollout)
        events = [
            json.loads(line)
            for line in Path(result["outputs"]["events_jsonl"])
            .read_text(encoding="utf-8")
            .splitlines()
        ]

        failed = next(item for item in events if item.get("status") == "failed")
        self.assertEqual(failed["hard_event_kind"], "tool_call_failed")
        self.assertEqual(failed["command_class"], "test")
        self.assertEqual(failed["tool_intent"], "test_check")
        self.assertEqual(failed["command_family"], "python_unittest")
        self.assertEqual(failed["test_target_class"], "focused_test_path")
        self.assertEqual(failed["failure_family"], "python_exception")
        self.assertEqual(failed["critical_operation_family"], "test_check_command_result")
        self.assertEqual(failed["exit_code"], 1)
        self.assertEqual(failed["tool_name"], "functions.shell_command")
        self.assertIn("test", failed["path_categories"])
        self.assertIn("source", failed["path_categories"])
        self.assertEqual(failed["path_extensions"], ["py"])
        self.assertGreaterEqual(failed["path_count"], 1)
        self.assertTrue(
            all(str(item).startswith("sha256:") for item in failed.get("path_fingerprints", []))
        )
        serialized = json.dumps(events, ensure_ascii=False)
        self.assertNotIn("test_secret.py", serialized)
        self.assertNotIn("test_token.py", serialized)
        self.assertNotIn("C:\\Users", serialized)
        self.assertNotIn("SECRET_PATH", serialized)
        self.assertNotIn("API_KEY", serialized)
        self.assertNotIn("Traceback from", serialized)
        self.assertNotIn("python tests", serialized)


if __name__ == "__main__":
    unittest.main()
