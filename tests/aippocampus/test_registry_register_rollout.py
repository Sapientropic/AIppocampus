from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
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

from aippocampus_runtime import core as aippocampuslib  # noqa: E402
from aippocampus_runtime.registry import api as registry  # noqa: E402
from aippocampus_runtime.warm_ambient.hook_seen_threads import (  # noqa: E402
    hook_seen_ledger_path_for_registry,
    record_hook_seen_thread,
)
from conversation_sources import CodexConversationProvider  # noqa: E402

REGISTRY_CMD = [sys.executable, "-m", "aippocampus_runtime.registry.api"]
AIPPOCAMPUS_CLI_CMD = [sys.executable, "-m", "aippocampus_runtime.cli.facade"]


class RegisterRolloutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cwd = self.root / "Project Alpha"
        self.cwd.mkdir()
        self.rollout = self.root / "rollout-other-thread.jsonl"
        self.registry_dir = self.root / "registry"
        self._write_rollout()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _append(self, item: dict) -> None:
        with self.rollout.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def _write_rollout(self) -> None:
        self._append(
            {
                "type": "session_meta",
                "payload": {
                    "id": "session-other",
                    "timestamp": "2026-05-26T03:00:00Z",
                    "cwd": str(self.cwd),
                    "originator": "Codex Desktop",
                },
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T03:00:01Z",
                "payload": {
                    "type": "user_message",
                    "message": "把这个旧线程纳入 AIppocampus 记忆范围。",
                },
            }
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T03:00:02Z",
                "payload": {
                    "type": "agent_message",
                    "phase": "final_answer",
                    "message": "旧线程已经注册为可检索的 clean-source 原文参考。",
                },
            }
        )

    def _write_generic_jsonl(self, path: Path, *, malformed: bool = False) -> None:
        rows = [
            {
                "session_id": "generic-import-session",
                "timestamp": "2026-05-30T04:10:00Z",
                "cwd": str(self.cwd),
                "role": "user",
                "text": "generic import should register from an explicit path",
                "turn_id": "t1",
                "source_ref": "browser:session:generic-import-session#L1",
                "provider_metadata": {"provider": "browser-test"},
            },
            {
                "session_id": "generic-import-session",
                "timestamp": "2026-05-30T04:10:01Z",
                "cwd": str(self.cwd),
                "role": "assistant",
                "text": "clean source is built through the generic provider",
                "turn_id": "t1",
                "source_ref": "browser:session:generic-import-session#L2",
                "provider_metadata": {"provider": "browser-test"},
            },
        ]
        if malformed:
            rows[1].pop("text")
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )

    def _copy_rollout_into_codex_sessions(self) -> Path:
        target = self.root / "sessions" / "2026" / "05" / "26" / "rollout-copy.jsonl"
        target.parent.mkdir(parents=True)
        target.write_text(self.rollout.read_text(encoding="utf-8"), encoding="utf-8")
        return target

    def test_register_rollout_writes_per_thread_store_and_project_tags(self) -> None:
        result = registry.register_rollout_thread(
            self.rollout,
            project="Life OS",
            tags=["codex", "memory"],
            registry_dir=self.registry_dir,
        )

        entry = result["entry"]
        self.assertEqual(entry["thread_key"], "session:session-other")
        self.assertEqual(entry["artifact_scope"], "registry_thread_store")
        self.assertEqual(entry["project_label"], "Life OS")
        self.assertIn("memory", entry["project_tags"])
        self.assertEqual(entry["clean_message_count"], 2)

        clean_messages = Path(entry["paths"]["clean_source_messages_jsonl"])
        self.assertTrue(clean_messages.exists())
        self.assertIn("旧线程已经注册", clean_messages.read_text(encoding="utf-8"))
        self.assertIn("threads", entry["paths"]["registry_thread_store"])

        score, hits = registry.deep_search_entry(entry, ["clean-source"], max_hits=2)
        self.assertGreater(score, 0)
        self.assertEqual(hits[0]["source"], "clean_source")
        self.assertEqual(hits[0]["phase"], "final_answer")

        metadata_score = registry.entry_search_score(entry, ["Life OS"])
        self.assertGreater(metadata_score, 0)

        data = json.loads((self.registry_dir / "threads.json").read_text(encoding="utf-8"))
        self.assertEqual(data["threads"][0]["thread_key"], "session:session-other")

    def test_existing_registry_json_corruption_blocks_write_path(self) -> None:
        registry_path = self.registry_dir / "threads.json"
        self.registry_dir.mkdir()
        original = "{broken registry json"
        registry_path.write_text(original, encoding="utf-8")

        with self.assertRaises(registry.RegistryReadError):
            registry.register_rollout_thread(
                self.rollout,
                project="Life OS",
                registry_dir=self.registry_dir,
            )

        self.assertEqual(registry_path.read_text(encoding="utf-8"), original)

    def test_scan_sessions_dry_run_reports_unregistered_rollouts(self) -> None:
        original_home = registry.codex_home
        registry.codex_home = lambda: self.root
        self._copy_rollout_into_codex_sessions()
        try:
            result = registry.scan_session_rollouts(registry_dir=self.registry_dir, dry_run=True)
        finally:
            registry.codex_home = original_home

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["planned"][0]["thread_key"], "session:session-other")

    def test_scan_sessions_hook_seen_only_limits_repair_scope(self) -> None:
        original_home = registry.codex_home
        registry.codex_home = lambda: self.root
        self._copy_rollout_into_codex_sessions()
        unseen = self.root / "sessions" / "2026" / "05" / "26" / "rollout-unseen.jsonl"
        unseen.write_text(
            "\n".join(
                json.dumps(row, ensure_ascii=False)
                for row in [
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": "session-unseen",
                            "timestamp": "2026-05-26T03:10:00Z",
                            "cwd": str(self.cwd),
                            "originator": "Codex Desktop",
                        },
                    },
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "user_message",
                            "message": "this other session was never hook seen",
                        },
                    },
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        ledger_path = hook_seen_ledger_path_for_registry(self.registry_dir / "threads.json")
        record_hook_seen_thread(
            ledger_path,
            thread_id="session-other",
            workspace=str(self.cwd),
        )
        try:
            result = registry.scan_session_rollouts(
                registry_dir=self.registry_dir,
                dry_run=True,
                hook_seen_only=True,
                hook_seen_ledger=ledger_path,
            )
        finally:
            registry.codex_home = original_home

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["hook_seen_filter"]["seen_thread_count"], 1)
        self.assertEqual(result["planned"][0]["thread_key"], "session:session-other")

    def test_registry_cli_scan_sessions_accepts_explicit_provider(self) -> None:
        self._copy_rollout_into_codex_sessions()

        proc = subprocess.run(
            [
                *REGISTRY_CMD,
                "--registry-dir",
                str(self.registry_dir),
                "scan-sessions",
                "--provider",
                "codex",
                "--dry-run",
                "--json",
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            cwd=SCRIPTS,
            env={**os.environ, "CODEX_HOME": str(self.root)},
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["planned"][0]["thread_key"], "session:session-other")

    def test_registry_cli_register_source_dry_run_validates_generic_jsonl(self) -> None:
        transcript = self.root / "generic-import.jsonl"
        self._write_generic_jsonl(transcript)

        proc = subprocess.run(
            [
                *REGISTRY_CMD,
                "--registry-dir",
                str(self.registry_dir),
                "register-source",
                "--provider",
                "generic-jsonl",
                "--input",
                str(transcript),
                "--project",
                "External Import",
                "--dry-run",
                "--json",
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
        self.assertTrue(data["ok"])
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["source_provider"], "generic-jsonl")
        self.assertEqual(data["thread_key"], "generic-jsonl:session:generic-import-session")
        self.assertEqual(data["message_count"], 2)
        self.assertFalse((self.registry_dir / "threads.json").exists())

    def test_aippocampus_import_conversation_registers_generic_jsonl(self) -> None:
        transcript = self.root / "generic-import.jsonl"
        self._write_generic_jsonl(transcript)

        proc = subprocess.run(
            [
                *AIPPOCAMPUS_CLI_CMD,
                "import",
                "conversation",
                "--registry-dir",
                str(self.registry_dir),
                "--format",
                "generic-jsonl",
                "--input",
                str(transcript),
                "--project",
                "External Import",
                "--json",
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
        self.assertTrue(data["ok"])
        self.assertFalse(data["dry_run"])
        self.assertEqual(data["source_provider"], "generic-jsonl")
        self.assertEqual(data["entry"]["source_provider"], "generic-jsonl")
        self.assertEqual(data["entry"]["thread_key"], "generic-jsonl:session:generic-import-session")
        clean_messages = Path(data["entry"]["paths"]["clean_source_messages_jsonl"])
        self.assertTrue(clean_messages.exists())
        self.assertIn("generic import should register", clean_messages.read_text(encoding="utf-8"))

    def test_register_source_reports_generic_jsonl_line_diagnostics(self) -> None:
        transcript = self.root / "bad-generic-import.jsonl"
        self._write_generic_jsonl(transcript, malformed=True)

        proc = subprocess.run(
            [
                *REGISTRY_CMD,
                "--registry-dir",
                str(self.registry_dir),
                "register-source",
                "--provider",
                "generic-jsonl",
                "--input",
                str(transcript),
                "--json",
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            cwd=SCRIPTS,
        )

        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], "missing_required_fields")
        self.assertEqual(data["error"]["class"], "validation_error")
        self.assertEqual(data["error"]["line"], 2)
        self.assertEqual(data["error"]["details"]["missing"], ["text"])
        self.assertFalse((self.registry_dir / "threads.json").exists())

    def test_registry_cli_register_source_reports_writer_busy_json(self) -> None:
        transcript = self.root / "generic-import.jsonl"
        self._write_generic_jsonl(transcript)
        old_argv = sys.argv[:]
        stdout = io.StringIO()
        stderr = io.StringIO()

        try:
            sys.argv = [
                "registry",
                "--registry-dir",
                str(self.registry_dir),
                "register-source",
                "--provider",
                "generic-jsonl",
                "--input",
                str(transcript),
                "--json",
            ]
            with (
                mock.patch.object(
                    registry,
                    "register_source_thread",
                    side_effect=registry.RegistryWriteBusyError(
                        self.registry_dir / "threads.json",
                        wait_timeout_seconds=0.0,
                    ),
                ),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                code = registry.main()
        finally:
            sys.argv = old_argv

        self.assertEqual(code, 1)
        self.assertEqual(stderr.getvalue(), "")
        data = json.loads(stdout.getvalue())
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], "registry_writer_busy")
        self.assertTrue(data["error"]["retryable"])
        self.assertFalse((self.registry_dir / "threads.json").exists())

    def test_registry_cli_search_redacts_top_level_registry_path(self) -> None:
        registry.register_rollout_thread(
            self.rollout,
            project="Life OS",
            registry_dir=self.registry_dir,
        )

        proc = subprocess.run(
            [
                *REGISTRY_CMD,
                "--registry-dir",
                str(self.registry_dir),
                "search",
                "Life",
                "--json",
                "--redact-paths",
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
        self.assertEqual(data["registry"], "<local-path-redacted>")
        self.assertNotIn(str(self.registry_dir), proc.stdout)

    def test_register_current_thread_build_passes_provider_rollout_to_child_scripts(
        self,
    ) -> None:
        target = self._copy_rollout_into_codex_sessions()
        old_codex_home = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(self.root)
        self.addCleanup(
            lambda: (
                os.environ.pop("CODEX_HOME", None)
                if old_codex_home is None
                else os.environ.__setitem__("CODEX_HOME", old_codex_home)
            )
        )
        index_dir = aippocampuslib.default_thread_index_dir(self.cwd, target)
        clean_dir = aippocampuslib.default_thread_clean_source_dir(self.cwd, target)
        calls: list[list[str]] = []

        def fake_run_json(cmd: list[str]) -> dict:
            call = [str(part) for part in cmd]
            calls.append(call)
            module_name = call[2] if len(call) > 2 and call[1] == "-m" else Path(call[1]).stem
            rollout_arg = call[call.index("--rollout") + 1]
            self.assertEqual(Path(rollout_arg), target)
            if module_name == "aippocampus_runtime.recall.index_builder":
                index_dir.mkdir(parents=True, exist_ok=True)
                (index_dir / "manifest.json").write_text(
                    json.dumps(
                        {
                            "created_at": "2026-05-26T03:00:00Z",
                            "session_meta": {"id": "session-other"},
                            "source_rollout": str(target),
                            "outputs": {},
                            "sqlite": {},
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            if module_name == "aippocampus_runtime.source.clean_source":
                clean_dir.mkdir(parents=True, exist_ok=True)
                (clean_dir / "manifest.json").write_text(
                    json.dumps(
                        {
                            "created_at": "2026-05-26T03:00:00Z",
                            "message_count": 2,
                            "turn_count": 1,
                            "outputs": {
                                "messages_jsonl": str(clean_dir / "messages.jsonl"),
                                "turns_jsonl": str(clean_dir / "turns.jsonl"),
                            },
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            return {}

        with mock.patch.object(registry, "run_json", side_effect=fake_run_json):
            result = registry.register_current_thread(
                self.cwd,
                registry_dir=self.registry_dir,
                build_index=True,
                health={"ok": True},
                provider=CodexConversationProvider(self.root),
            )

        self.assertEqual(result["entry"]["thread_key"], "session:session-other")
        self.assertEqual(
            [call[2] for call in calls],
            [
                "aippocampus_runtime.recall.index_builder",
                "aippocampus_runtime.source.clean_source",
            ],
        )

    def test_scan_sessions_dry_run_reports_archived_rollouts(self) -> None:
        original_home = registry.codex_home
        registry.codex_home = lambda: self.root
        archived = self.root / "archived_sessions"
        archived.mkdir(parents=True)
        target = archived / "rollout-archived.jsonl"
        target.write_text(self.rollout.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            result = registry.scan_session_rollouts(registry_dir=self.registry_dir, dry_run=True)
        finally:
            registry.codex_home = original_home

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["planned"][0]["thread_key"], "session:session-other")
        self.assertIn("archived_sessions", result["planned"][0]["rollout"])

    def test_deep_search_demotes_injected_skill_hits(self) -> None:
        clean_dir = self.root / "clean"
        clean_dir.mkdir()
        messages = clean_dir / "messages.jsonl"
        rows = [
            {
                "message_id": "msg-noise",
                "turn_id": "turn-noise",
                "source_line": 10,
                "role": "user",
                "phase": "",
                "turn_index": 1,
                "is_final": False,
                "text": "<skill><name>aippocampus</name> AIppocampus CodexHome global project</skill>",
            },
            {
                "message_id": "msg-real",
                "turn_id": "turn-real",
                "source_line": 20,
                "role": "assistant",
                "phase": "final_answer",
                "turn_index": 2,
                "is_final": True,
                "text": "AIppocampus 生成产物默认写到 CodexHome global store，project-local 只是兼容模式。",
            },
        ]
        messages.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8"
        )
        entry = {
            "paths": {
                "clean_source_messages_jsonl": str(messages),
            }
        }

        score, hits = registry.deep_search_entry(
            entry, ["AIppocampus", "CodexHome", "global", "project"], max_hits=2
        )

        self.assertGreater(score, 0)
        self.assertEqual(hits[0]["message_id"], "msg-real")
        self.assertTrue(hits[1]["search_noise"])
        self.assertLess(hits[1]["rank_score"], hits[0]["rank_score"])

    def test_deep_search_merges_semantic_scope_label_sidecar(self) -> None:
        clean_dir = self.root / "semantic-clean"
        clean_dir.mkdir()
        messages = clean_dir / "messages.jsonl"
        messages.write_text(
            json.dumps(
                {
                    "message_id": "msg-metaphor",
                    "turn_id": "turn-metaphor",
                    "source_line": 12,
                    "role": "user",
                    "phase": "",
                    "turn_index": 1,
                    "scope_labels": [],
                    "text": "This lighthouse metaphor feels like a pivot.",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (clean_dir / "semantic-scope-labels.jsonl").write_text(
            json.dumps(
                {
                    "message_id": "msg-metaphor",
                    "source": "deepseek_subconscious_scope_labels",
                    "scope_labels": ["personal_reflection", "idea_seed"],
                    "confidence": 0.86,
                    "label_evidence": [
                        {
                            "label": "personal_reflection",
                            "reason": "The source says the metaphor feels pivotal.",
                            "confidence": 0.86,
                        },
                        {
                            "label": "idea_seed",
                            "reason": "The source frames the lighthouse metaphor as a pivot idea.",
                            "confidence": 0.86,
                        },
                    ],
                    "source_refs": [{"message_id": "msg-metaphor", "source_line": 12}],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        entry = {"paths": {"clean_source_messages_jsonl": str(messages)}}

        score, hits = registry.deep_search_entry(entry, ["lighthouse", "metaphor"], max_hits=1)

        self.assertGreater(score, 0)
        self.assertEqual(hits[0]["message_id"], "msg-metaphor")
        self.assertEqual(hits[0]["semantic_scope_labels"], ["personal_reflection", "idea_seed"])
        self.assertEqual(hits[0]["scope_labels"], ["personal_reflection", "idea_seed"])


if __name__ == "__main__":
    unittest.main()
