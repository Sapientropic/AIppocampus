from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
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

from aippocampus_runtime.contracts import executable_command_violations  # noqa: E402
from aippocampus_runtime.onboarding import codex as onboard  # noqa: E402
from aippocampus_runtime.onboarding import facade as onboard_facade  # noqa: E402
from aippocampus_runtime.onboarding import frontier as onboard_frontier  # noqa: E402
from aippocampus_runtime.registry import api as registry  # noqa: E402
from conversation_sources import CodexConversationProvider  # noqa: E402

ONBOARD_CMD = [sys.executable, "-m", "aippocampus_runtime.onboarding.facade"]
PROVIDER_ENV_NOISE = (
    "AIPPOCAMPUS_DEEPSEEK_API_KEY",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_PRO_MODEL",
    "AIIPPOCAMPUS_SUBCONSCIOUS_HOOK",
)


class OnboardCodexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cwd = self.root / "Project"
        self.cwd.mkdir()
        self.registry_dir = self.root / "registry"
        self.sessions = self.root / "sessions" / "2026" / "05" / "26"
        self.sessions.mkdir(parents=True)
        self.rollout = self.sessions / "rollout-test.jsonl"
        self._write_rollout()
        self.original_home = registry.codex_home
        registry.codex_home = lambda: self.root

    def tearDown(self) -> None:
        registry.codex_home = self.original_home
        self.tmp.cleanup()

    def _append(self, item: dict) -> None:
        with self.rollout.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def _write_rollout(self) -> None:
        self._append(
            {
                "type": "session_meta",
                "payload": {
                    "id": "session-onboard",
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
                    "message": "把全部 Codex 线程纳入 AIppocampus。",
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
                    "message": "已注册为全局 clean-source 和索引。",
                },
            }
        )

    def _write_claude_transcript(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "type": "user",
                "sessionId": "claude-onboard",
                "uuid": "claude-user",
                "parentUuid": None,
                "timestamp": "2026-05-30T03:00:00Z",
                "cwd": str(self.cwd),
                "message": {"role": "user", "content": "synthetic claude user turn"},
            },
            {
                "type": "assistant",
                "sessionId": "claude-onboard",
                "uuid": "claude-assistant",
                "parentUuid": "claude-user",
                "timestamp": "2026-05-30T03:00:01Z",
                "cwd": str(self.cwd),
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "synthetic claude assistant turn"}],
                },
            },
        ]
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )

    def _write_generic_transcript(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "session_id": "generic-onboard",
                "timestamp": "2026-05-30T04:00:00Z",
                "cwd": str(self.cwd),
                "role": "user",
                "text": "generic onboarding user turn",
                "turn_id": "g1",
            },
            {
                "session_id": "generic-onboard",
                "timestamp": "2026-05-30T04:00:01Z",
                "cwd": str(self.cwd),
                "role": "assistant",
                "text": "generic onboarding assistant turn",
                "turn_id": "g1",
            },
        ]
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )

    def test_dry_run_returns_agent_native_plan_without_writing(self) -> None:
        result = onboard.run_onboarding(
            cwd=self.cwd,
            registry_dir=self.registry_dir,
            dry_run=True,
            build_index=True,
            refresh_current=False,
            build_timeline=True,
            build_cognitive_map=True,
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["dry_run"])
        self.assertEqual(result["data"]["plan"]["would_register_count"], 1)
        self.assertFalse((self.registry_dir / "threads.json").exists())
        self.assertIn("next", result)

    def test_run_onboarding_accepts_explicit_provider_without_global_codex_home_patch(
        self,
    ) -> None:
        registry.codex_home = self.original_home
        result = onboard.run_onboarding(
            cwd=self.cwd,
            registry_dir=self.registry_dir,
            provider=CodexConversationProvider(self.root),
            dry_run=True,
            build_index=True,
            refresh_current=False,
            build_timeline=True,
            build_cognitive_map=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["meta"]["provider"], "codex")
        self.assertEqual(result["data"]["plan"]["would_register_count"], 1)

    def test_onboard_facade_provider_codex_delegates_to_existing_onboarding(self) -> None:
        proc = self._run_onboard_facade(
            "--provider",
            "codex",
            "--cwd",
            str(self.cwd),
            "--registry-dir",
            str(self.registry_dir),
            "--dry-run",
            "--format",
            "json",
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data["ok"])
        self.assertEqual(data["meta"]["provider"], "codex")
        self.assertEqual(data["data"]["plan"]["would_register_count"], 1)

    def test_onboard_facade_provider_claude_code_dry_run_reports_real_provider_plan(
        self,
    ) -> None:
        self._write_claude_transcript(
            self.root / "claude-home" / "projects" / "-project" / "claude-session.jsonl"
        )

        proc = self._run_onboard_facade(
            "--provider",
            "claude-code",
            "--cwd",
            str(self.cwd),
            "--registry-dir",
            str(self.registry_dir),
            "--dry-run",
            "--format",
            "json",
            env_extra={"CLAUDE_HOME": str(self.root / "claude-home")},
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data["ok"])
        self.assertEqual(data["meta"]["provider"], "claude-code")
        self.assertEqual(data["data"]["plan"]["would_register_count"], 1)

    def test_onboard_facade_provider_claude_code_registers_after_parser_exists(
        self,
    ) -> None:
        self._write_claude_transcript(
            self.root / "claude-home" / "projects" / "-project" / "claude-session.jsonl"
        )

        proc = self._run_onboard_facade(
            "--provider",
            "claude-code",
            "--cwd",
            str(self.cwd),
            "--registry-dir",
            str(self.registry_dir),
            "--no-timeline",
            "--no-cognitive-map",
            "--no-repair",
            "--no-refresh-current",
            "--format",
            "json",
            env_extra={"CLAUDE_HOME": str(self.root / "claude-home")},
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data["ok"])
        self.assertEqual(data["meta"]["provider"], "claude-code")
        self.assertEqual(data["data"]["actions"]["scan_sessions"]["registered_count"], 1)
        threads = json.loads((self.registry_dir / "threads.json").read_text(encoding="utf-8"))
        self.assertEqual(threads["threads"][0]["thread_key"], "claude-code:session:claude-onboard")

    def test_onboard_status_reports_provider_capabilities(self) -> None:
        self._write_claude_transcript(
            self.root / "claude-home" / "projects" / "-project" / "claude-session.jsonl"
        )

        proc = self._run_onboard_facade(
            "--status",
            "--operator-json",
            "--cwd",
            str(self.cwd),
            env_extra={
                "CLAUDE_HOME": str(self.root / "claude-home"),
                "AIPPOCAMPUS_HOME": str(self.root / "aippo-home"),
            },
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        providers = {item["provider"]: item for item in data["data"]["providers"]}
        self.assertEqual(providers["codex"]["state"], "write_enabled")
        self.assertEqual(providers["claude-code"]["state"], "write_enabled")
        self.assertTrue(providers["claude-code"]["current_cwd_match"])
        self.assertEqual(
            providers["claude-code"]["next_action_code"],
            "try_search_existing_registry",
        )
        self.assertIn("aippocampus search", providers["claude-code"]["search_command_template"])
        self.assertEqual(providers["claude-code"]["requires"], ["exact_phrase"])
        primary = data["data"]["primary_next_action"]
        self.assertEqual(data["primary_next_action"], primary)
        self.assertEqual(data["agent_next_action"], primary["agent_next_action"])
        self.assertEqual(primary["provider"], "codex")
        self.assertEqual(primary["code"], "search_existing_registered_memory")
        self.assertIn("aippocampus search", primary["command_template"])
        self.assertEqual(primary["requires"], ["exact_phrase"])
        self.assertEqual(executable_command_violations(data), [])
        self.assertIn("blocked", data["data"]["state_legend"])
        self.assertEqual(data["data"]["storage"]["source"], "AIPPOCAMPUS_HOME/registry")
        self.assertFalse(data["data"]["storage"]["legacy_fallback"])
        self.assertEqual(data["data"]["storage"]["path"], "<local-path-redacted>")
        self.assertTrue(data["data"]["storage"]["path_redacted"])
        self.assertEqual(data["data"]["legacy_aliases"]["active_count"], 0)

    def test_onboard_status_json_defaults_to_bounded_frontstage_inventory(self) -> None:
        self._write_claude_transcript(
            self.root / "claude-home" / "projects" / "-project" / "claude-session.jsonl"
        )

        proc = self._run_onboard_facade(
            "--status",
            "--format",
            "json",
            "--cwd",
            str(self.cwd),
            env_extra={"CLAUDE_HOME": str(self.root / "claude-home")},
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        providers = {item["provider"]: item for item in data["provider_summary"]}
        self.assertEqual(data["kind"], "aippocampus_onboard_status_card")
        self.assertEqual(data["status"], "registration_available_after_consent")
        self.assertTrue(data["read_only"])
        self.assertEqual(data["provider_scope"], "auto")
        self.assertNotIn("data", data)
        self.assertNotIn("state_legend", json.dumps(data, ensure_ascii=False))
        self.assertNotIn("legacy_aliases", json.dumps(data, ensure_ascii=False))
        self.assertNotIn("storage", data)
        self.assertEqual(providers["codex"]["state"], "registration_available_after_consent")
        self.assertEqual(
            providers["codex"]["frontstage_state"],
            "registration_available_after_consent",
        )
        self.assertEqual(providers["claude-code"]["detected"], True)
        self.assertEqual(
            providers["claude-code"]["frontstage_state"],
            "registration_available_after_consent",
        )
        self.assertEqual(providers["generic-jsonl"]["state"], "blocked")
        primary = data["primary_next_action"]
        self.assertEqual(data["agent_next_action"], primary)
        self.assertEqual(primary["provider"], "codex")
        self.assertEqual(primary["code"], "preview_current_project_registration")
        self.assertEqual(primary["mutation_risk"], "read_only")
        self.assertNotEqual(primary["provider"], "generic-jsonl")
        self.assertIn("onboard --provider codex --dry-run", primary["command"])
        self.assertEqual(
            data["operator_detail_command"],
            "aippocampus onboard --provider auto --status --operator-json",
        )
        self.assertEqual(executable_command_violations(data), [])
        self.assertNotIn(str(self.root), proc.stdout)

    def test_onboard_status_json_redacts_storage_path_by_default_and_can_opt_in(self) -> None:
        private_home = self.root / "aippo-home"
        base_args = [
            "--status",
            "--format",
            "json",
            "--cwd",
            str(self.cwd),
        ]

        redacted = self._run_onboard_facade(
            *base_args,
            env_extra={"AIPPOCAMPUS_HOME": str(private_home)},
        )
        operator_redacted = self._run_onboard_facade(
            *base_args,
            "--operator-json",
            env_extra={"AIPPOCAMPUS_HOME": str(private_home)},
        )
        full = self._run_onboard_facade(
            *base_args,
            "--operator-json",
            "--include-private-paths",
            env_extra={"AIPPOCAMPUS_HOME": str(private_home)},
        )

        self.assertEqual(redacted.returncode, 0, redacted.stdout + redacted.stderr)
        self.assertEqual(operator_redacted.returncode, 0, operator_redacted.stdout + operator_redacted.stderr)
        self.assertEqual(full.returncode, 0, full.stdout + full.stderr)
        redacted_payload = json.loads(redacted.stdout)
        operator_payload = json.loads(operator_redacted.stdout)
        full_payload = json.loads(full.stdout)
        self.assertEqual(redacted_payload["kind"], "aippocampus_onboard_status_card")
        self.assertNotIn("storage", redacted_payload)
        self.assertEqual(operator_payload["data"]["storage"]["path"], "<local-path-redacted>")
        self.assertNotIn(str(private_home), redacted.stdout)
        self.assertIn(str(private_home), full_payload["data"]["storage"]["path"])

    def test_onboard_status_json_reports_legacy_storage_alias_without_private_path(self) -> None:
        legacy_registry = self.root / "private-legacy-registry"
        proc = self._run_onboard_facade(
            "--status",
            "--format",
            "json",
            "--operator-json",
            "--cwd",
            str(self.cwd),
            env_extra={
                "THREAD_MEMORY_REGISTRY_DIR": str(legacy_registry),
            },
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        aliases = {entry["alias"] for entry in data["data"]["legacy_aliases"]["active"]}
        encoded_aliases = json.dumps(data["data"]["legacy_aliases"], ensure_ascii=False)

        self.assertEqual(data["data"]["storage"]["source"], "THREAD_MEMORY_REGISTRY_DIR")
        self.assertTrue(data["data"]["storage"]["legacy_fallback"])
        self.assertIn("THREAD_MEMORY_REGISTRY_DIR", aliases)
        self.assertFalse(data["data"]["legacy_aliases"]["value_printed"])
        self.assertFalse(data["data"]["legacy_aliases"]["local_paths_included"])
        self.assertNotIn(str(legacy_registry), encoded_aliases)

    def test_onboard_status_respects_explicit_provider_scope(self) -> None:
        self._write_claude_transcript(
            self.root / "claude-home" / "projects" / "-project" / "claude-session.jsonl"
        )

        proc = self._run_onboard_facade(
            "--provider",
            "codex",
            "--status",
            "--format",
            "json",
            "--cwd",
            str(self.cwd),
            env_extra={
                "CLAUDE_HOME": str(self.root / "claude-home"),
                "AIPPOCAMPUS_GENERIC_IMPORT_DIR": str(self.root / "missing-generic.jsonl"),
            },
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        providers = [item["provider"] for item in data["data"]["providers"]]

        self.assertEqual(providers, ["codex"])
        self.assertEqual(data["data"]["provider_scope"], "codex")

    def test_onboard_status_generic_jsonl_routes_to_explicit_import_preview(self) -> None:
        generic = self.root / "generic" / "sessions.jsonl"
        self._write_generic_transcript(generic)

        proc = self._run_onboard_facade(
            "--provider",
            "generic-jsonl",
            "--status",
            "--format",
            "json",
            "--cwd",
            str(self.cwd),
            env_extra={"AIPPOCAMPUS_GENERIC_IMPORT_DIR": str(generic)},
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        provider = data["data"]["providers"][0]
        primary = data["data"]["primary_next_action"]
        encoded = json.dumps(data, ensure_ascii=False)

        self.assertEqual(primary["provider"], "generic-jsonl")
        self.assertEqual(primary["code"], "import_conversation_preview")
        self.assertEqual(provider["next_action_code"], "import_conversation_preview")
        self.assertIn("import conversation --format generic-jsonl", primary["command_template"])
        self.assertEqual(primary["requires"], ["input_path"])
        self.assertIn(
            "import conversation --format generic-jsonl",
            provider["preview_command_template"],
        )
        self.assertEqual(provider["requires"], ["input_path"])
        self.assertEqual(executable_command_violations(data), [])
        self.assertNotIn("onboard --provider generic-jsonl --dry-run", encoded)

    def test_onboard_status_reports_missing_non_codex_providers_as_blocked(self) -> None:
        proc = self._run_onboard_facade(
            "--status",
            "--format",
            "json",
            "--cwd",
            str(self.cwd),
            env_extra={
                "CLAUDE_HOME": str(self.root / "missing-claude-home"),
                "AIPPOCAMPUS_GENERIC_IMPORT_DIR": str(self.root / "missing-generic.jsonl"),
            },
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        providers = {item["provider"]: item for item in data["provider_summary"]}
        self.assertEqual(providers["codex"]["state"], "registration_available_after_consent")
        self.assertEqual(providers["claude-code"]["state"], "blocked")
        self.assertFalse(providers["claude-code"]["detected"])
        self.assertEqual(providers["generic-jsonl"]["state"], "blocked")
        self.assertFalse(providers["generic-jsonl"]["detected"])
        self.assertNotIn("blockers", providers["generic-jsonl"])

    def test_onboard_status_can_render_human_readable_auto_output(self) -> None:
        proc = self._run_onboard_facade(
            "--status",
            "--format",
            "text",
            "--cwd",
            str(self.cwd),
            env_extra={"CLAUDE_HOME": str(self.root / "missing-claude-home")},
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("AIppocampus provider status", proc.stdout)
        self.assertIn("primary:", proc.stdout)
        self.assertIn("next command:", proc.stdout)
        self.assertIn("- codex: registration_available_after_consent", proc.stdout)
        self.assertIn("- claude-code: blocked", proc.stdout)
        self.assertNotIn("write_enabled", proc.stdout)
        self.assertIn("registry configured", proc.stdout)
        self.assertIn("CODEX_HOME/aippocampus-registry legacy fallback", proc.stdout)
        self.assertNotIn(str(self.root), proc.stdout)

    def test_onboard_status_human_provider_scope_hides_other_provider_blockers(self) -> None:
        proc = self._run_onboard_facade(
            "--provider",
            "codex",
            "--status",
            "--format",
            "text",
            "--cwd",
            str(self.cwd),
            env_extra={"CLAUDE_HOME": str(self.root / "missing-claude-home")},
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("- codex: registration_available_after_consent", proc.stdout)
        self.assertNotIn("write_enabled", proc.stdout)
        self.assertNotIn("claude-code", proc.stdout)
        self.assertNotIn(str(self.root), proc.stdout)

    def test_onboard_facade_provider_generic_jsonl_dry_run_reports_plan(self) -> None:
        generic = self.root / "generic" / "generic-session.jsonl"
        self._write_generic_transcript(generic)

        proc = self._run_onboard_facade(
            "--provider",
            "generic-jsonl",
            "--cwd",
            str(self.cwd),
            "--registry-dir",
            str(self.registry_dir),
            "--dry-run",
            "--format",
            "json",
            env_extra={"AIPPOCAMPUS_GENERIC_IMPORT_DIR": str(generic)},
        )

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data["ok"])
        self.assertEqual(data["meta"]["provider"], "generic-jsonl")
        self.assertEqual(data["data"]["plan"]["would_register_count"], 1)
        self.assertNotIn("sample_candidates", data["data"]["plan"])

    def _run_onboard_facade(self, *args: str, env_extra: dict[str, str] | None = None) -> Any:
        import subprocess

        env = {**os.environ, "CODEX_HOME": str(self.root)}
        for name in PROVIDER_ENV_NOISE:
            env.pop(name, None)
        env.update(env_extra or {})
        return subprocess.run(
            [*ONBOARD_CMD, *args],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            env=env,
            check=False,
            cwd=SCRIPTS,
        )

    def test_onboarding_registers_indexes_and_returns_compact_stats(self) -> None:
        result = onboard.run_onboarding(
            cwd=self.cwd,
            registry_dir=self.registry_dir,
            dry_run=False,
            build_index=True,
            refresh_current=False,
            build_timeline=True,
            build_cognitive_map=True,
        )

        self.assertTrue(result["ok"])
        stats = result["data"]["stats_after"]
        self.assertEqual(stats["thread_count"], 1)
        self.assertEqual(stats["clean_source_count"], 1)
        self.assertEqual(stats["sqlite_index_count"], 1)
        self.assertEqual(stats["graph_json_count"], 1)
        self.assertEqual(result["data"]["actions"]["scan_sessions"]["registered_count"], 1)
        self.assertEqual(result["data"]["actions"]["cognitive_map"]["route_count"], 0)
        self.assertGreaterEqual(
            result["data"]["actions"]["semantic_triggers"]["trigger_count"], 1
        )
        self.assertEqual(result["data"]["boundary"]["frontier"]["status"], "not_run")
        self.assertGreaterEqual(
            result["data"]["actions"]["project_timeline"]["life_label_count"], 1
        )
        self.assertTrue((self.registry_dir / "project_timeline.json").exists())
        self.assertTrue((self.registry_dir / "semantic_triggers.jsonl").exists())
        self.assertTrue((self.registry_dir / "query_pattern_routes.jsonl").exists())
        self.assertEqual(
            result["data"]["actions"]["query_pattern_routes"]["metrics"]["live_llm_call_count"],
            0,
        )
        query_route_metrics = result["data"]["actions"]["query_pattern_routes"]["metrics"]
        self.assertGreaterEqual(query_route_metrics["route_write_count"], 2)
        self.assertEqual(
            query_route_metrics["alias_source_route_counts"]["registry_metadata"],
            1,
        )
        self.assertGreaterEqual(
            query_route_metrics["alias_source_route_counts"]["reviewed_semantic"],
            1,
        )
        self.assertTrue(
            result["data"]["actions"]["query_pattern_routes"]["contract"][
                "query_pattern_routes_are_navigation_only"
            ]
        )

        public = onboard.public_onboarding_result(result)
        encoded_public = json.dumps(public, ensure_ascii=False)
        public_query_routes = public["data"]["actions"]["query_pattern_routes"]
        self.assertGreaterEqual(public_query_routes["route_write_count"], 2)
        self.assertEqual(
            public_query_routes["alias_source_route_counts"]["registry_metadata"],
            1,
        )
        self.assertGreaterEqual(
            public_query_routes["alias_source_route_counts"]["reviewed_semantic"],
            1,
        )
        self.assertNotIn("query_aliases", encoded_public)
        self.assertNotIn("外置小海马", encoded_public)
        self.assertNotIn(str(self.root), encoded_public)

    def test_cli_json_uses_public_onboarding_projection(self) -> None:
        private_result = {
            "ok": True,
            "data": {
                "stats_after": {
                    "thread_count": 1,
                    "clean_source_count": 1,
                    "sqlite_index_count": 1,
                    "graph_json_count": 1,
                    "missing_artifacts": [str(self.rollout)],
                },
                "boundary": {"frontier": {"status": "smoke"}},
                "frontier": {
                    "status": "smoke",
                    "sample_findings": [{"summary": "private frontier finding"}],
                },
                "plan": {"sample_candidates": [{"title": "private candidate"}]},
            },
            "next": {"commands": [{"script": str(self.rollout)}]},
            "meta": {"provider": "codex", "duration_ms": 12},
        }
        stdout = io.StringIO()
        with (
            patch.object(onboard, "run_onboarding", return_value=private_result),
            patch.object(
                sys,
                "argv",
                [
                    "aippocampus_runtime.onboarding.codex",
                    "--cwd",
                    str(self.cwd),
                    "--registry-dir",
                    str(self.registry_dir),
                    "--json",
                ],
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = onboard.main()

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["frontier_status"], "smoke")
        self.assertNotIn("sample_findings", encoded)
        self.assertNotIn("sample_candidates", encoded)
        self.assertNotIn("private frontier", encoded)
        self.assertNotIn(str(self.root), encoded)

    def test_public_dry_run_projection_keeps_explicit_write_next_action(self) -> None:
        result = {
            "ok": True,
            "data": {
                "dry_run": True,
                "stats_before": {"thread_count": 1},
                "plan": {"would_register_count": 1},
                "boundary": {"frontier": {"status": "not_run"}},
                "storage_policy": {"default": "CODEX_HOME/aippocampus-registry"},
            },
            "next": [
                'aippocampus search "distinctive old phrase"',
                "aippocampus onboard --provider codex --all --format json",
            ],
            "meta": {"provider": "codex", "duration_ms": 12},
        }

        public = onboard.public_onboarding_result(result)
        commands = [item["command"] for item in public["next_actions"]]

        self.assertEqual(public["next_count"], len(public["next_actions"]))
        self.assertIn("aippocampus onboard --provider codex --all --json", commands)
        self.assertEqual(public["next_actions"][0]["mutation_risk"], "explicit_registration_write")
        self.assertNotIn("--format json", json.dumps(public, ensure_ascii=False))

    def test_facade_passes_json_format_to_provider_write_path(self) -> None:
        with (
            patch.object(onboard_facade, "create_conversation_provider", return_value=object()),
            patch.object(onboard_facade.onboard_codex, "main", return_value=0) as provider_main,
        ):
            code = onboard_facade.main(["--provider", "codex", "--all", "--format", "json"])

        self.assertEqual(code, 0)
        self.assertIn("--all", provider_main.call_args.args[0])
        self.assertIn("--json", provider_main.call_args.args[0])

    def test_text_closeout_suggests_first_recall_query_modes(self) -> None:
        result = {
            "ok": True,
            "data": {
                "stats_after": {
                    "thread_count": 1,
                    "clean_source_count": 1,
                    "sqlite_index_count": 1,
                    "graph_json_count": 0,
                },
                "boundary": {"frontier": {"status": "not_run"}},
            },
            "next": [],
        }
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            onboard.print_text(result)

        output = stdout.getvalue()
        self.assertIn("First recall", output)
        self.assertIn("exact phrase", output)
        self.assertIn("project cue", output)
        self.assertIn("time cue", output)
        self.assertIn("aippocampus search", output)

    def test_repair_detects_and_rebuilds_sqlite_stale_against_clean_source(self) -> None:
        initial = registry.register_rollout_thread(
            self.rollout,
            cwd=self.cwd,
            registry_dir=self.registry_dir,
            build_index=True,
        )
        self._append(
            {
                "type": "event_msg",
                "timestamp": "2026-05-26T03:00:03Z",
                "payload": {
                    "type": "user_message",
                    "message": "新增 clean-source 但旧 SQLite 还没有的 freshness marker。",
                },
            }
        )
        refreshed_clean_only = registry.register_rollout_thread(
            self.rollout,
            cwd=self.cwd,
            registry_dir=self.registry_dir,
            build_index=False,
        )
        self.assertEqual(
            initial["entry"]["paths"]["sqlite"], refreshed_clean_only["entry"]["paths"]["sqlite"]
        )

        stats = onboard.registry_stats(registry_dir=self.registry_dir)

        self.assertEqual(stats["stale_sqlite"], 1)
        self.assertIn("sqlite_index", stats["repair_artifacts"][0]["stale"])
        self.assertTrue(
            any(
                issue["code"] == "missing_clean_source_lines"
                for issue in stats["repair_artifacts"][0]["issues"]
            )
        )

        repair = onboard.repair_missing_artifacts(registry_dir=self.registry_dir, build_index=True)
        repaired_stats = onboard.registry_stats(registry_dir=self.registry_dir)

        self.assertEqual(repair["repaired_count"], 1)
        self.assertEqual(repaired_stats["stale_sqlite"], 0)

    def test_frontier_smoke_exposes_compact_sample_findings_and_infers_project(self) -> None:
        captured: dict[str, Any] = {}

        def fake_run_jobs(**kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {
                "job_count": 1,
                "successful_job_count": 1,
                "failure_count": 0,
                "finding_count": 3,
                "wrote": False,
                "jobs": [
                    {
                        "findings": [
                            {
                                "kind": "question_candidate",
                                "title": "Native CLI frontier",
                                "question_short": "native CLI frontier",
                                "question_text": "How should the onboarding command expose frontier smoke quality?",
                                "intent_orientation": "cli_design",
                                "phase_context": "pre-write smoke",
                                "confidence": 0.82,
                                "source_refs": [{"ref": "t0"}, {"ref": "o1"}],
                            },
                            {
                                "kind": "frontier_marker",
                                "title": "Long raw question gate",
                                "frontier_type": "scope_boundary",
                                "boundary_reason": "Overlong raw user excerpts should not be staged as question text.",
                                "confidence": 0.87,
                                "source_refs": [{"ref": "t1"}],
                            },
                            {
                                "kind": "frontier_marker",
                                "title": "Stale clean-source not automatically rewritten",
                                "frontier_type": "unresolved",
                                "boundary_reason": "旧 clean-source 注入块不会自动全量重写，除非跑 --refresh-registered。",
                                "confidence": 0.9,
                                "source_refs": [{"ref": "t2"}],
                            },
                        ]
                    }
                ],
            }

        old_run_jobs = onboard_frontier.run_jobs
        old_api_key = os.environ.get("AIPPOCAMPUS_DEEPSEEK_API_KEY")
        old_legacy_api_key = os.environ.get("DEEPSEEK_API_KEY")
        onboard_frontier.run_jobs = fake_run_jobs
        os.environ["AIPPOCAMPUS_DEEPSEEK_API_KEY"] = "test-key"
        os.environ.pop("DEEPSEEK_API_KEY", None)
        try:
            result = onboard.run_onboarding(
                cwd=self.cwd,
                registry_dir=self.registry_dir,
                dry_run=False,
                build_index=True,
                refresh_current=False,
                build_timeline=True,
                build_cognitive_map=False,
                frontier_mode="smoke",
            )
        finally:
            onboard_frontier.run_jobs = old_run_jobs
            if old_api_key is None:
                os.environ.pop("AIPPOCAMPUS_DEEPSEEK_API_KEY", None)
            else:
                os.environ["AIPPOCAMPUS_DEEPSEEK_API_KEY"] = old_api_key
            if old_legacy_api_key is None:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            else:
                os.environ["DEEPSEEK_API_KEY"] = old_legacy_api_key

        frontier = result["data"]["boundary"]["frontier"]
        self.assertEqual(captured["project"], "Project")
        self.assertEqual(frontier["project_scope"], "Project")
        self.assertEqual(frontier["sample_findings"][0]["kind"], "question_candidate")
        self.assertEqual(frontier["sample_findings"][0]["source_ref_count"], 2)
        self.assertNotIn("source_refs", frontier["sample_findings"][0])
        self.assertEqual(frontier["sample_findings"][1]["frontier_type"], "scope_boundary")
        self.assertEqual(frontier["raw_finding_count"], 3)
        self.assertEqual(frontier["finding_count"], 2)
        self.assertEqual(frontier["filtered_stale_count"], 1)
        self.assertNotIn(
            "refresh-registered", json.dumps(frontier["sample_findings"], ensure_ascii=False)
        )
        self.assertIn("Current onboarding state after maintenance", captured["objective"])
        self.assertIn("missing_clean=0", captured["objective"])

    def test_frontier_smoke_missing_deepseek_key_blocks_instead_of_skipping(self) -> None:
        old_api_key = os.environ.get("AIPPOCAMPUS_DEEPSEEK_API_KEY")
        old_legacy_api_key = os.environ.get("DEEPSEEK_API_KEY")
        os.environ.pop("AIPPOCAMPUS_DEEPSEEK_API_KEY", None)
        os.environ.pop("DEEPSEEK_API_KEY", None)
        try:
            result = onboard.run_onboarding(
                cwd=self.cwd,
                registry_dir=self.registry_dir,
                dry_run=False,
                build_index=True,
                refresh_current=False,
                build_timeline=True,
                build_cognitive_map=False,
                frontier_mode="smoke",
            )
        finally:
            if old_api_key is None:
                os.environ.pop("AIPPOCAMPUS_DEEPSEEK_API_KEY", None)
            else:
                os.environ["AIPPOCAMPUS_DEEPSEEK_API_KEY"] = old_api_key
            if old_legacy_api_key is None:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            else:
                os.environ["DEEPSEEK_API_KEY"] = old_legacy_api_key

        self.assertEqual(result["ok"], "partial")
        self.assertEqual(
            result["data"]["boundary"]["frontier"]["status"], "blocked_missing_api_key"
        )


if __name__ == "__main__":
    unittest.main()
