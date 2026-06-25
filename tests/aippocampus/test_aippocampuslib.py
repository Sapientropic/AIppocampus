from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT = REPO_ROOT / "skills" / "aippocampus"
SCRIPTS = ROOT / "scripts"

from aippocampus_runtime import anchor_graph, safety
from aippocampus_runtime import core as aippocampuslib
from aippocampus_runtime.cli import errors as cli_errors
from aippocampus_runtime.registry import api as registry
from conversation_sources import (
    ClaudeCodeConversationProvider,
    CodexConversationProvider,
    GenericConversationProvider,
    GenericJsonlValidationError,
    create_conversation_provider,
)
from tests.aippocampus.redaction_fixtures import (
    fake_test_credential_url,
    fake_test_database_dsn,
    fake_test_email,
)

LOCATE_ROLLOUT_CMD = [sys.executable, "-m", "aippocampus_runtime.source.locate_rollout"]

def canonical(path: str | Path) -> Path:
    return Path(path).resolve()

def write_rollout(path: Path, cwd: Path, session_id: str = "archived-session") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "timestamp": "2026-05-26T03:00:00Z",
                "cwd": str(cwd),
                "originator": "Codex Desktop",
            },
        },
        {
            "type": "event_msg",
            "timestamp": "2026-05-26T03:00:01Z",
            "payload": {"type": "user_message", "message": "归档线程也要能被定位。"},
        },
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

def write_claude_transcript(
    path: Path,
    cwd: Path,
    session_id: str = "claude-session",
    timestamp: str = "2026-05-30T03:00:00Z",
    first_cwd: Path | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    first_cwd = first_cwd or cwd
    rows = [
        {
            "type": "user",
            "sessionId": session_id,
            "uuid": "user-uuid",
            "parentUuid": None,
            "timestamp": timestamp,
            "cwd": str(first_cwd),
            "message": {"role": "user", "content": "synthetic user turn"},
        },
        {
            "type": "assistant",
            "sessionId": session_id,
            "uuid": "assistant-uuid",
            "parentUuid": "user-uuid",
            "timestamp": "2026-05-30T03:00:01Z",
            "cwd": str(cwd),
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "synthetic assistant turn"}],
            },
        },
        {"type": "ai-title", "sessionId": session_id, "aiTitle": "Synthetic Claude title"},
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

class AippocampusLibTests(unittest.TestCase):
    def test_deepseek_cache_metrics_from_usage(self) -> None:
        metrics = aippocampuslib.deepseek_cache_metrics_from_usage(
            {
                "prompt_tokens": 125,
                "prompt_cache_hit_tokens": 80,
                "prompt_cache_miss_tokens": 20,
            }
        )

        self.assertTrue(metrics["available"])
        self.assertEqual(metrics["hit_tokens"], 80)
        self.assertEqual(metrics["miss_tokens"], 20)
        self.assertEqual(metrics["hit_rate"], 0.8)

    def test_strip_empty_preserves_empty_dicts_by_default(self) -> None:
        payload = {
            "keep": {"boundary": {}},
            "drop_none": None,
            "drop_empty_string": "",
            "drop_empty_list": [],
            "items": [{"a": ""}, {"b": "value"}, []],
        }

        self.assertEqual(
            aippocampuslib.strip_empty(payload),
            {"keep": {"boundary": {}}, "items": [{}, {"b": "value"}]},
        )

    def test_strip_empty_can_drop_empty_dicts_for_legacy_projection_callers(self) -> None:
        payload = {
            "keep": {"value": "present"},
            "drop_nested": {"empty": {}},
            "items": [{"a": ""}, {"b": "value"}, {}],
        }

        self.assertEqual(
            aippocampuslib.strip_empty(payload, drop_empty_dicts=True),
            {"keep": {"value": "present"}, "items": [{"b": "value"}]},
        )

    def test_legacy_stable_id_shapes_remain_canonical_helpers(self) -> None:
        tuple_parts = ("aar_v2", {"b": 2, "a": 1})
        tuple_raw = json.dumps(tuple_parts, ensure_ascii=False, sort_keys=True, default=str)
        tuple_digest = hashlib.sha256(tuple_raw.encode("utf-8")).hexdigest()[:16]
        self.assertEqual(
            aippocampuslib.stable_json_tuple_digest(*tuple_parts, ensure_ascii=False),
            tuple_digest,
        )
        self.assertEqual(
            aippocampuslib.stable_json_tuple_id("apw", *tuple_parts, ensure_ascii=False),
            f"apw_{tuple_digest}",
        )

        text_raw = "\0".join(["src-key", "msg-1"])
        text_digest = hashlib.sha256(text_raw.encode("utf-8")).hexdigest()[:20]
        self.assertEqual(
            aippocampuslib.stable_text_join_id(
                "src",
                "src-key",
                "msg-1",
                sep="\0",
                length=20,
            ),
            f"src_{text_digest}",
        )
        non_null_raw = "|".join(str(part) for part in ("route", 0, False))
        self.assertEqual(
            aippocampuslib.stable_text_non_null_join_id(
                "rt", "route", None, 0, False, sep="|", length=16
            ),
            f"rt_{hashlib.sha256(non_null_raw.encode('utf-8', errors='replace')).hexdigest()[:16]}",
        )

        json_lines_raw = "\n".join(
            json.dumps(part, ensure_ascii=False, sort_keys=True)
            for part in ("thread", 7)
        )
        json_lines_digest = hashlib.sha256(
            json_lines_raw.encode("utf-8", errors="replace")
        ).hexdigest()[:18]
        self.assertEqual(
            aippocampuslib.stable_json_lines_id(
                "source_line",
                "thread",
                7,
                ensure_ascii=False,
                default_str=False,
            ),
            f"source_line_{json_lines_digest}",
        )
        compact_raw = json.dumps(
            {"b": 2, "a": 1},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        self.assertEqual(
            aippocampuslib.stable_json_digest(
                {"b": 2, "a": 1},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            hashlib.sha256(compact_raw.encode("utf-8")).hexdigest()[:16],
        )

        json_join_raw = "\0".join(
            json.dumps(part, ensure_ascii=False, sort_keys=True, default=str)
            for part in ("episode", {"n": 1})
        )
        json_join_digest = hashlib.sha256(
            json_join_raw.encode("utf-8", errors="replace")
        ).hexdigest()[:14]
        self.assertEqual(
            aippocampuslib.stable_json_join_id(
                "seq",
                "episode",
                {"n": 1},
                sep="\0",
                ensure_ascii=False,
                length=14,
            ),
            f"seq_{json_join_digest}",
        )

    def test_safety_owner_preserves_redaction_and_transport_behavior(self) -> None:
        project_path = REPO_ROOT / "skills" / "aippocampus" / "scripts" / "aippocampus_runtime" / "safety.py"
        sanitized, policy = safety.sanitize_external_model_text(
            f"token=sk-abcdefghijklmnopqrstuvwxyz and {project_path}",
            project_root=REPO_ROOT,
        )

        self.assertIn("<redacted:api-key>", sanitized)
        self.assertIn("<redacted:local-path>", sanitized)
        self.assertIn("<path-anchor", sanitized)
        self.assertIn("scope=project", sanitized)
        self.assertIn("class=python", sanitized)
        self.assertIn("ext=py", sanitized)
        self.assertIn("hash=sha256:", sanitized)
        self.assertNotIn(str(REPO_ROOT), sanitized)
        self.assertNotIn("safety.py", sanitized)
        self.assertTrue(policy["redacted"])

        with self.assertRaises(ValueError):
            safety.validate_private_credential_transport(
                "http://example.com/api",
                service_name="model route",
                credential_label="API key",
            )

        safety.validate_private_credential_transport(
            "http://127.0.0.1:8080/api",
            service_name="local model route",
            credential_label="API key",
        )

    def test_external_path_anchor_does_not_create_stable_path_identity(self) -> None:
        sanitized, policy = safety.sanitize_external_model_text(
            "Check C:\\Users\\Name\\private\\memory_gate.py for recall behavior.",
            project_root=REPO_ROOT,
        )

        self.assertTrue(policy["redacted"])
        self.assertIn("<redacted:local-path>", sanitized)
        self.assertIn("<path-anchor", sanitized)
        self.assertIn("scope=external", sanitized)
        self.assertIn("class=python", sanitized)
        self.assertIn("ext=py", sanitized)
        self.assertNotIn("hash=sha256:", sanitized)
        self.assertNotIn("Users", sanitized)
        self.assertNotIn("Name", sanitized)
        self.assertNotIn("memory_gate.py", sanitized)

    def test_project_path_anchor_recognizes_macos_private_var_alias(self) -> None:
        sanitized, policy = safety.sanitize_external_model_text(
            "Continue /var/folders/ab/cd/T/workspace/src/warm_recall.ts",
            project_root="/private/var/folders/ab/cd/T/workspace",
        )

        self.assertTrue(policy["redacted"])
        self.assertIn("<redacted:local-path>", sanitized)
        self.assertIn("scope=project", sanitized)
        self.assertIn("class=typescript", sanitized)
        self.assertIn("ext=ts", sanitized)
        self.assertIn("hash=sha256:", sanitized)
        self.assertNotIn("/var/folders", sanitized)
        self.assertNotIn("/private/var", sanitized)
        self.assertNotIn("warm_recall.ts", sanitized)

    def test_private_key_blocks_preserve_safe_context_or_hard_block_when_mostly_secret(self) -> None:
        private_key_block = "\n".join(
            [
                "-----" + "BEGIN PRIVATE KEY" + "-----",
                "abc123",
                "-----" + "END PRIVATE KEY" + "-----",
            ]
        )

        mixed, mixed_policy = safety.sanitize_external_model_text(
            "Please continue AIppocampus semantic recall for redaction anchors.\n"
            f"{private_key_block}\n"
            "The safe task context is external-model path anchor design."
        )

        self.assertFalse(mixed_policy["hard_block"])
        self.assertTrue(mixed_policy["redacted"])
        self.assertIn("private_key_block", mixed_policy["redaction_types"])
        self.assertIn("<redacted:private-key-block>", mixed)
        self.assertIn("AIppocampus semantic recall", mixed)
        self.assertIn("path anchor design", mixed)
        self.assertNotIn("abc123", mixed)
        self.assertNotIn("BEGIN PRIVATE KEY", mixed)

        mostly_secret, mostly_secret_policy = safety.sanitize_external_model_text(
            private_key_block
        )

        self.assertTrue(mostly_secret_policy["hard_block"])
        self.assertEqual(mostly_secret, "<redacted:private-key-block>")

    def test_benchmark_sensitive_text_policy_reuses_runtime_safety_boundary(self) -> None:
        database_dsn = fake_test_database_dsn()
        credential_url = fake_test_credential_url()
        email = fake_test_email()
        cases = {
            database_dsn: {
                "database_connection_string",
                "private_hostname",
            },
            credential_url: {"credential_url", "private_hostname"},
            f"contact me at {email}": {"email_address"},
            "service endpoint http://10.0.0.8:8080": {"private_ip_address"},
            "token=super-secret and /home/sdy/private.txt": {
                "secret_assignment",
                "posix_local_path",
            },
        }

        for text, expected_reasons in cases.items():
            with self.subTest(text=text):
                policy = safety.benchmark_sensitive_text_policy(text)
                self.assertTrue(policy["sensitive"])
                self.assertTrue(policy["uses_runtime_redaction"])
                self.assertLessEqual(
                    expected_reasons,
                    set(policy["reason_categories"]),
                )

        normal_policy = safety.benchmark_sensitive_text_policy(
            "The blue lighthouse recall marker belongs to this source message."
        )
        self.assertFalse(normal_policy["sensitive"])
        self.assertEqual(normal_policy["reason_categories"], [])

    def test_clean_source_redaction_profiles_mask_text_without_replacing_source_truth(self) -> None:
        project_file = REPO_ROOT / "skills" / "aippocampus" / "scripts" / "aippocampus_runtime" / "safety.py"
        database_dsn = fake_test_database_dsn()
        email = fake_test_email()
        private_key_block = "\n".join(
            [
                "-----" + "BEGIN PRIVATE KEY" + "-----",
                "FAKE_TEST_PRIVATE_KEY_PAYLOAD",
                "-----" + "END PRIVATE KEY" + "-----",
            ]
        )
        text = (
            f"Keep source refs for {project_file}. "
            f"Contact {email}. "
            f"Use {database_dsn}. "
            "token=sk-FAKE_TEST_OPENAI_REDACTION_1234567890.\n"
            f"{private_key_block}"
        )

        raw_text, raw_policy = safety.project_clean_source_text(
            text,
            profile="raw-private",
            project_root=REPO_ROOT,
        )
        self.assertEqual(raw_text, text)
        self.assertEqual(raw_policy["source_fidelity"], "canonical")
        self.assertFalse(raw_policy["redacted"])

        projected, policy = safety.project_clean_source_text(
            text,
            profile="public-export",
            project_root=REPO_ROOT,
        )

        self.assertEqual(policy["profile"], "public-export")
        self.assertEqual(policy["source_fidelity"], "projection")
        self.assertTrue(policy["redacted"])
        self.assertIn("private_key_block", policy["redaction_types"])
        self.assertIn("openai_api_key", policy["redaction_types"])
        self.assertIn("email_address", policy["redaction_types"])
        self.assertIn("database_connection_string", policy["redaction_types"])
        self.assertIn("<redacted:private-key-block>", projected)
        self.assertIn("<redacted:api-key>", projected)
        self.assertIn("<redacted:email>", projected)
        self.assertIn("<redacted:connection-string>", projected)
        self.assertIn("<redacted:local-path>", projected)
        self.assertIn("<path-anchor", projected)
        self.assertNotIn("FAKE_TEST_PRIVATE_KEY_PAYLOAD", projected)
        self.assertNotIn(email, projected)
        self.assertNotIn(database_dsn, projected)
        self.assertNotIn(str(REPO_ROOT), projected)
        self.assertNotIn("safety.py", projected)

    def test_clean_source_redaction_profile_design_doc_links_policy_surfaces(self) -> None:
        doc = (
            REPO_ROOT
            / "docs"
            / "architecture"
            / "source"
            / "clean-source-redaction-profiles.md"
        )
        text = doc.read_text(encoding="utf-8")
        docs_index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        privacy_checklist = (
            REPO_ROOT / "docs" / "guides" / "community" / "privacy-security-checklist.md"
        ).read_text(encoding="utf-8")

        for term in (
            "#591",
            "#352",
            "#357",
            "raw-private",
            "redacted-local",
            "public-export",
            "external-model",
            "source refs",
            "canonical evidence source",
        ):
            self.assertIn(term, text)
        self.assertIn("clean-source-redaction-profiles.md", docs_index)
        self.assertIn("clean-source redaction profiles", privacy_checklist)

    def test_cli_error_owner_preserves_payload_shape(self) -> None:
        payload = cli_errors.cli_error_payload_from_message("missing API key")

        self.assertEqual(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "missing_api_key")
        self.assertEqual(payload["error"]["class"], "missing_prerequisite")
        self.assertEqual(cli_errors.cli_exit_code_for_error_code("missing_api_key"), 2)
        self.assertEqual(cli_errors.cli_error_class_for_error_code("invalid_json"), "validation_error")
        self.assertEqual(cli_errors.cli_error_class_for_error_code("privacy_blocked"), "privacy_block")
        self.assertEqual(cli_errors.cli_exit_code_for_error_code("privacy_blocked"), 2)
        self.assertEqual(cli_errors.cli_exit_code_for_error_code("future_unknown_error"), 1)
        self.assertEqual(
            cli_errors.cli_public_error_object({"code": "private_token_code"}),
            {"code": "runtime_error", "class": "runtime_error"},
        )
        self.assertIs(
            aippocampuslib.cli_error_payload_from_message,
            cli_errors.cli_error_payload_from_message,
        )

    def test_anchor_graph_owner_parses_and_builds_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "anchors.md"
            path.write_text(
                "\n".join(
                    [
                        "## Recall boundary",
                        "- Keywords: source refs, semantic labels",
                        "- Preserved phrase: source-backed continuity needs evidence",
                        "- Source: docs/architecture/runtime-script-map.md",
                    ]
                ),
                encoding="utf-8",
            )

            anchors = anchor_graph.parse_anchor_file(path)
            graph = anchor_graph.build_anchor_graph(anchors, "session-1")

        self.assertEqual(anchors[0]["title"], "Recall boundary")
        self.assertIn("source refs", anchors[0]["keywords"])
        self.assertTrue(any(node["type"] == "quote" for node in graph["nodes"]))
        self.assertIs(aippocampuslib.parse_anchor_file, anchor_graph.parse_anchor_file)

    def test_locate_rollout_searches_archived_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "codex-home"
            cwd = root / "Project Alpha"
            cwd.mkdir()
            rollout = home / "archived_sessions" / "rollout-archived.jsonl"
            write_rollout(rollout, cwd)

            self.assertIn(rollout, list(aippocampuslib.iter_rollouts(home)))
            self.assertEqual(aippocampuslib.locate_rollout(cwd, home), rollout)

            store = aippocampuslib.default_thread_store_dir(
                cwd,
                home=home,
                registry_dir=root / "registry",
            )
            self.assertEqual(store.name, "session-archived-session")

    def test_locate_rollout_cli_reports_archived_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "codex-home"
            cwd = root / "Project Alpha"
            cwd.mkdir()
            rollout = home / "archived_sessions" / "rollout-archived.jsonl"
            write_rollout(rollout, cwd)

            proc = subprocess.run(
                [
                    *LOCATE_ROLLOUT_CMD,
                    "--cwd",
                    str(cwd),
                    "--codex-home",
                    str(home),
                ],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                cwd=SCRIPTS,
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            data = json.loads(proc.stdout)
            self.assertEqual(Path(data["path"]), rollout)
            self.assertEqual(data["session_meta"]["id"], "archived-session")

    def test_codex_provider_discovers_live_and_archived_rollouts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "codex-home"
            cwd = root / "Project Alpha"
            cwd.mkdir()
            live = home / "sessions" / "2026" / "05" / "30" / "rollout-live.jsonl"
            archived = home / "archived_sessions" / "rollout-archived.jsonl"
            write_rollout(live, cwd, session_id="live-session")
            write_rollout(archived, cwd, session_id="archived-session")

            provider = CodexConversationProvider(home)
            sessions = list(provider.discover_sessions())

            self.assertEqual({session.path for session in sessions}, {live, archived})
            self.assertEqual(
                {session.session_id for session in sessions},
                {"live-session", "archived-session"},
            )
            self.assertEqual(provider.read_metadata(archived)["id"], "archived-session")

    def test_legacy_rollout_helpers_match_codex_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "codex-home"
            cwd = root / "Project Alpha"
            cwd.mkdir()
            rollout = home / "sessions" / "2026" / "05" / "30" / "rollout-live.jsonl"
            write_rollout(rollout, cwd, session_id="live-session")

            provider = CodexConversationProvider(home)
            source = provider.locate_current(cwd)

            self.assertEqual(source.path, rollout)
            self.assertEqual(aippocampuslib.locate_rollout(cwd, home), source.path)
            self.assertEqual(list(aippocampuslib.iter_rollouts(home)), [source.path])
            self.assertEqual(
                aippocampuslib.read_session_meta(source.path),
                provider.read_metadata(source.path),
            )

    def test_registry_storage_precedence_prefers_aippocampus_envs_then_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(
                os.environ,
                {"AIPPOCAMPUS_REGISTRY_DIR": str(root / "exact-registry")},
                clear=True,
            ):
                resolution = aippocampuslib.aippocampus_registry_resolution()
                self.assertEqual(Path(resolution["path"]), root / "exact-registry")
                self.assertEqual(resolution["source"], "AIPPOCAMPUS_REGISTRY_DIR")
                self.assertFalse(resolution["legacy_fallback"])

            with patch.dict(os.environ, {"AIPPOCAMPUS_HOME": str(root / "home")}, clear=True):
                resolution = aippocampuslib.aippocampus_registry_resolution()
                self.assertEqual(Path(resolution["path"]), root / "home" / "registry")
                self.assertEqual(resolution["source"], "AIPPOCAMPUS_HOME/registry")
                self.assertFalse(resolution["legacy_fallback"])

            with patch.dict(os.environ, {"CODEX_HOME": str(root / "codex-home")}, clear=True):
                resolution = aippocampuslib.aippocampus_registry_resolution()
                self.assertEqual(
                    Path(resolution["path"]), root / "codex-home" / "aippocampus-registry"
                )
                self.assertEqual(resolution["source"], "CODEX_HOME/aippocampus-registry")
                self.assertTrue(resolution["legacy_fallback"])

    def test_registry_scan_accepts_explicit_conversation_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "codex-home"
            cwd = root / "Project Alpha"
            cwd.mkdir()
            rollout = home / "sessions" / "2026" / "05" / "30" / "rollout-live.jsonl"
            write_rollout(rollout, cwd, session_id="provider-session")
            provider = CodexConversationProvider(home)

            result = registry.scan_session_rollouts(
                registry_dir=root / "registry",
                provider=provider,
                dry_run=True,
            )

            self.assertEqual(result["count"], 1)
            self.assertEqual(result["planned"][0]["thread_key"], "session:provider-session")
            self.assertEqual(Path(result["planned"][0]["rollout"]), rollout)

    def test_claude_code_provider_discovers_and_locates_project_transcripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "claude-home"
            cwd = root / "Project Claude"
            cwd.mkdir()
            transcript = home / "projects" / "-project-claude" / "session.jsonl"
            write_claude_transcript(transcript, cwd)

            provider = ClaudeCodeConversationProvider(home)
            sessions = list(provider.discover_sessions())

            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0].provider, "claude-code")
            self.assertEqual(sessions[0].path, transcript)
            self.assertEqual(sessions[0].session_id, "claude-session")
            self.assertEqual(sessions[0].cwd, cwd)
            self.assertEqual(provider.locate_current(cwd).path, transcript)
            self.assertEqual(provider.thread_key(transcript), "claude-code:session:claude-session")
            self.assertEqual(provider.read_metadata(transcript)["originator"], "Claude Code")

    def test_claude_code_provider_locates_cwd_after_first_metadata_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "claude-home"
            first_cwd = root / "Other Project"
            target_cwd = root / "Target Project"
            first_cwd.mkdir()
            target_cwd.mkdir()
            transcript = home / "projects" / "-mixed" / "session.jsonl"
            write_claude_transcript(transcript, target_cwd, first_cwd=first_cwd)

            target_cwd_alias = first_cwd / ".." / "Target Project"
            source = ClaudeCodeConversationProvider(home).locate_current(target_cwd_alias)

            self.assertEqual(source.path, transcript)
            self.assertEqual(source.cwd, canonical(target_cwd))

    def test_claude_code_provider_normalizes_visible_text_without_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "claude-home"
            cwd = root / "Project Claude"
            cwd.mkdir()
            transcript = home / "projects" / "-project-claude" / "session.jsonl"
            transcript.parent.mkdir(parents=True, exist_ok=True)
            rows = [
                {
                    "type": "user",
                    "sessionId": "claude-session",
                    "uuid": "user-uuid",
                    "timestamp": "2026-05-30T03:00:00Z",
                    "cwd": str(cwd),
                    "message": {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "visible user text"},
                            {"type": "tool_result", "content": "private tool result"},
                        ],
                    },
                },
                {
                    "type": "assistant",
                    "sessionId": "claude-session",
                    "uuid": "assistant-uuid",
                    "parentUuid": "user-uuid",
                    "timestamp": "2026-05-30T03:00:01Z",
                    "cwd": str(cwd),
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "thinking", "thinking": "private chain"},
                            {"type": "tool_use", "name": "Read", "input": {"file_path": "secret"}},
                            {"type": "text", "text": "visible assistant text"},
                        ],
                    },
                },
            ]
            transcript.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                encoding="utf-8",
            )

            messages, turns = ClaudeCodeConversationProvider(home).read_normalized_messages(
                transcript
            )

            self.assertEqual([message["text"] for message in messages], ["visible user text", "visible assistant text"])
            self.assertNotIn("private", json.dumps(messages, ensure_ascii=False))
            self.assertEqual(messages[1]["phase"], "final_answer")
            self.assertEqual(messages[1]["source_ref"], "claude-code:session:claude-session#L2")
            self.assertEqual(turns[0]["final_line"], 2)

    def test_claude_code_provider_keeps_repeated_user_text_as_distinct_turns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "claude-home"
            cwd = root / "Project Claude"
            cwd.mkdir()
            transcript = home / "projects" / "-project-claude" / "session.jsonl"
            transcript.parent.mkdir(parents=True, exist_ok=True)
            rows = [
                {
                    "type": "user",
                    "sessionId": "claude-session",
                    "uuid": "user-1",
                    "timestamp": "2026-05-30T03:00:00Z",
                    "cwd": str(cwd),
                    "message": {"role": "user", "content": "repeat this"},
                },
                {
                    "type": "assistant",
                    "sessionId": "claude-session",
                    "uuid": "assistant-1",
                    "parentUuid": "user-1",
                    "timestamp": "2026-05-30T03:00:01Z",
                    "cwd": str(cwd),
                    "message": {"role": "assistant", "content": "first answer"},
                },
                {
                    "type": "user",
                    "sessionId": "claude-session",
                    "uuid": "user-2",
                    "timestamp": "2026-05-30T03:01:00Z",
                    "cwd": str(cwd),
                    "message": {"role": "user", "content": "repeat this"},
                },
                {
                    "type": "assistant",
                    "sessionId": "claude-session",
                    "uuid": "assistant-2",
                    "parentUuid": "user-2",
                    "timestamp": "2026-05-30T03:01:01Z",
                    "cwd": str(cwd),
                    "message": {"role": "assistant", "content": "second answer"},
                },
            ]
            transcript.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                encoding="utf-8",
            )

            messages, turns = ClaudeCodeConversationProvider(home).read_normalized_messages(
                transcript
            )

            self.assertEqual([message["turn_index"] for message in messages], [1, 1, 2, 2])
            self.assertEqual([turn["user_line"] for turn in turns], [1, 3])
            self.assertEqual([turn["final_line"] for turn in turns], [2, 4])

    def test_registry_scan_accepts_claude_code_provider_for_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "claude-home"
            cwd = root / "Project Claude"
            cwd.mkdir()
            transcript = home / "projects" / "-project-claude" / "session.jsonl"
            write_claude_transcript(transcript, cwd)

            result = registry.scan_session_rollouts(
                registry_dir=root / "registry",
                provider=ClaudeCodeConversationProvider(home),
                dry_run=True,
            )

            self.assertEqual(result["count"], 1)
            self.assertEqual(
                result["planned"][0]["thread_key"], "claude-code:session:claude-session"
            )
            self.assertEqual(Path(result["planned"][0]["rollout"]), transcript)

    def test_generic_jsonl_provider_validates_and_normalizes_public_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd = root / "Generic Project"
            cwd.mkdir()
            transcript = root / "generic.jsonl"
            rows = [
                {
                    "session_id": "generic-session",
                    "timestamp": "2026-05-30T04:00:00Z",
                    "cwd": str(cwd),
                    "role": "user",
                    "text": "generic user text",
                    "turn_id": "turn-a",
                    "source_ref": "host://conversation/generic-session/messages/1",
                    "provider_metadata": {"provider": "synthetic-agent"},
                },
                {
                    "session_id": "generic-session",
                    "timestamp": "2026-05-30T04:00:01Z",
                    "cwd": str(cwd),
                    "role": "assistant",
                    "text": "generic assistant text",
                    "turn_id": "turn-a",
                },
            ]
            transcript.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
                encoding="utf-8",
            )
            provider = GenericConversationProvider(transcript)

            sessions = list(provider.discover_sessions())
            messages, turns = provider.read_normalized_messages(transcript)

            self.assertEqual(sessions[0].session_id, "generic-session")
            self.assertEqual(provider.thread_key(transcript), "generic-jsonl:session:generic-session")
            self.assertEqual(
                messages[0]["source_ref"], "host://conversation/generic-session/messages/1"
            )
            self.assertEqual(messages[1]["turn_index"], 1)
            self.assertEqual(turns[0]["final_line"], 2)

            bad = root / "bad.jsonl"
            bad.write_text('{"session_id":"s","role":"assistant","text":"orphan"}\n', encoding="utf-8")
            with self.assertRaises(GenericJsonlValidationError) as raised:
                GenericConversationProvider(bad).read_normalized_messages(bad)
            self.assertEqual(raised.exception.asdict()["code"], "orphan_assistant")
            self.assertEqual(raised.exception.asdict()["line"], 1)

    def test_generic_jsonl_provider_skips_directory_named_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd = root / "project"
            cwd.mkdir()
            directory = root / "looks-like-file.jsonl"
            directory.mkdir()
            transcript = root / "valid.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "session_id": "generic-session",
                        "cwd": str(cwd),
                        "role": "user",
                        "text": "hello from a real file",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            provider = GenericConversationProvider(root)

            sessions = list(provider.discover_sessions())

            self.assertEqual([session.path for session in sessions], [transcript])
            with self.assertRaises(GenericJsonlValidationError) as raised:
                provider.read_normalized_messages(directory)
            self.assertEqual(raised.exception.asdict()["code"], "source_not_file")

    def test_conversation_provider_factory_creates_claude_code_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider = create_conversation_provider("claude_code", claude_home_dir=Path(tmp))

            self.assertEqual(provider.name, "claude-code")

if __name__ == "__main__":
    unittest.main()
