from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))


class AippocampusCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "aippocampus_runtime.cli.facade", *args],
            cwd=SCRIPTS,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

    def test_help_leads_with_personal_path_before_operator_flows(self) -> None:
        proc = self.run_cli("--help")

        self.assertEqual(proc.returncode, 0)
        self.assertIn("Personal path", proc.stdout)
        self.assertIn("Advanced/operator diagnostics", proc.stdout)
        self.assertLess(proc.stdout.index("Personal path"), proc.stdout.index("Advanced/operator"))
        self.assertLess(proc.stdout.index("search"), proc.stdout.index("doctor provider"))
        self.assertIn("health", proc.stdout)
        self.assertIn("onboard", proc.stdout)
        self.assertIn("search", proc.stdout)
        self.assertIn("agent recall", proc.stdout)
        self.assertIn("continuity-domain", proc.stdout)
        self.assertIn("work-guard", proc.stdout)
        self.assertIn("update status", proc.stdout)
        self.assertIn("mcp list-tools", proc.stdout)
        self.assertIn("smoke recall-funnel", proc.stdout)
        self.assertIn("storage gc", proc.stdout)
        self.assertIn("doctor config", proc.stdout)
        self.assertIn("doctor spend", proc.stdout)
        self.assertIn("telepathy", proc.stdout)
        self.assertIn("why-recall", proc.stdout)
        self.assertIn("plugin install", proc.stdout)
        self.assertIn("hooks [kind]        Host hook status/install/uninstall surfaces", proc.stdout)

    def test_package_facade_is_the_public_python_entrypoint(self) -> None:
        from aippocampus_runtime.cli import facade
        from aippocampus_runtime.cli import facade as aippocampus_cli

        self.assertIs(aippocampus_cli.main, facade.main)
        self.assertIs(aippocampus_cli.run_script, facade.run_script)
        self.assertIs(aippocampus_cli.run_command, facade.run_command)
        self.assertIs(aippocampus_cli.resolve_command, facade.resolve_command)
        self.assertIs(aippocampus_cli.CommandInvocation, facade.CommandInvocation)
        self.assertIs(aippocampus_cli.CommandResult, facade.CommandResult)
        self.assertEqual(facade.SCRIPT_DIR, SCRIPTS)

    def test_package_facade_resolves_commands_without_running_child_processes(self) -> None:
        from aippocampus_runtime.cli import facade

        invocation = facade.resolve_command(["mcp", "list-tools", "--json"])

        self.assertEqual(invocation.command, "mcp")
        self.assertEqual(invocation.module_name, "aippocampus_runtime.mcp.server")
        self.assertEqual(invocation.script_name, "aippocampus_mcp_server.py")
        self.assertEqual(invocation.args, ["--list-tools", "--json"])

        search_invocation = facade.resolve_command(["search", "source", "--json"])
        self.assertEqual(search_invocation.command, "search")
        self.assertEqual(search_invocation.module_name, "aippocampus_runtime.source.search")
        self.assertEqual(search_invocation.script_name, "search_clean_source.py")

        agent_continuity_invocation = facade.resolve_command(
            ["agent", "recall", "continue project", "--json"]
        )
        self.assertEqual(agent_continuity_invocation.command, "agent")
        self.assertEqual(
            agent_continuity_invocation.module_name,
            "aippocampus_runtime.recall.agent_continuity",
        )
        self.assertEqual(agent_continuity_invocation.script_name, "agent_continuity.py")

        export_invocation = facade.resolve_command(["export", "--cwd", "."])
        self.assertEqual(export_invocation.command, "export")
        self.assertEqual(export_invocation.module_name, "aippocampus_runtime.artifacts.export_bundle")
        self.assertEqual(export_invocation.script_name, "export_bundle.py")

        import_invocation = facade.resolve_command(["import", "bundle.zip"])
        self.assertEqual(import_invocation.command, "import")
        self.assertEqual(import_invocation.module_name, "aippocampus_runtime.artifacts.import_bundle")
        self.assertEqual(import_invocation.script_name, "import_bundle.py")

        doctor_invocation = facade.resolve_command(["doctor", "provider", "--json"])
        self.assertEqual(doctor_invocation.command, "doctor")
        self.assertEqual(doctor_invocation.module_name, "aippocampus_runtime.ops.provider_doctor")
        self.assertEqual(doctor_invocation.script_name, "provider_doctor.py")
        self.assertEqual(doctor_invocation.args, ["provider", "--json"])

        doctor_config_invocation = facade.resolve_command(["doctor", "config", "--json"])
        self.assertEqual(doctor_config_invocation.command, "doctor")
        self.assertEqual(
            doctor_config_invocation.module_name,
            "aippocampus_runtime.ops.provider_doctor",
        )
        self.assertEqual(doctor_config_invocation.script_name, "provider_doctor.py")
        self.assertEqual(doctor_config_invocation.args, ["config", "--json"])

        update_invocation = facade.resolve_command(["update", "status", "--json"])
        self.assertEqual(update_invocation.command, "update")
        self.assertEqual(update_invocation.module_name, "aippocampus_runtime.update.cli")
        self.assertEqual(update_invocation.script_name, "update.py")
        self.assertEqual(update_invocation.args, ["status", "--json"])

        plugin_invocation = facade.resolve_command(["plugin", "install", "--codex", "--verify"])
        self.assertEqual(plugin_invocation.command, "plugin")
        self.assertEqual(
            plugin_invocation.module_name,
            "aippocampus_runtime.update.plugin_installer",
        )
        self.assertEqual(plugin_invocation.script_name, "plugin.py")
        self.assertEqual(plugin_invocation.args, ["install", "--codex", "--verify"])

        smoke_invocation = facade.resolve_command(
            ["smoke", "recall-funnel", "progressive recall", "--json"]
        )
        self.assertEqual(smoke_invocation.command, "smoke")
        self.assertEqual(
            smoke_invocation.module_name,
            "aippocampus_runtime.ops.recall_funnel_smoke",
        )
        self.assertEqual(smoke_invocation.script_name, "recall_funnel_smoke.py")
        self.assertEqual(
            smoke_invocation.args,
            ["recall-funnel", "progressive recall", "--json"],
        )

        storage_invocation = facade.resolve_command(["storage", "gc", "--dry-run", "--json"])
        self.assertEqual(storage_invocation.command, "storage")
        self.assertEqual(
            storage_invocation.module_name,
            "aippocampus_runtime.ops.storage_governance",
        )
        self.assertEqual(storage_invocation.script_name, "storage_governance.py")
        self.assertEqual(storage_invocation.args, ["gc", "--dry-run", "--json"])

        why_invocation = facade.resolve_command(["why-recall", "continue memory", "--json"])
        self.assertEqual(why_invocation.command, "why-recall")
        self.assertEqual(why_invocation.module_name, "aippocampus_runtime.recall.why_cli")
        self.assertEqual(why_invocation.script_name, "why_recall.py")
        self.assertEqual(why_invocation.args, ["why-recall", "continue memory", "--json"])

        why_not_invocation = facade.resolve_command(["why-not-recall", "continue memory"])
        self.assertEqual(why_not_invocation.command, "why-not-recall")
        self.assertEqual(why_not_invocation.module_name, "aippocampus_runtime.recall.why_cli")
        self.assertEqual(why_not_invocation.args, ["why-not-recall", "continue memory"])

        work_guard_invocation = facade.resolve_command(
            ["work-guard", "--title", "Fix LongMemEval source-side cache", "--json"]
        )
        self.assertEqual(work_guard_invocation.command, "work-guard")
        self.assertEqual(
            work_guard_invocation.module_name,
            "aippocampus_runtime.ops.issue_work_guard",
        )
        self.assertEqual(work_guard_invocation.script_name, "issue_work_guard.py")

        conversation_import = facade.resolve_command(
            [
                "import",
                "conversation",
                "--registry-dir",
                "registry",
                "--format",
                "generic-jsonl",
                "--input",
                "conversation.jsonl",
                "--json",
            ]
        )
        self.assertEqual(conversation_import.command, "import")
        self.assertEqual(conversation_import.module_name, "aippocampus_runtime.registry.api")
        self.assertEqual(conversation_import.script_name, "registry.py")
        self.assertEqual(
            conversation_import.args,
            [
                "--registry-dir",
                "registry",
                "register-source",
                "--provider",
                "generic-jsonl",
                "--input",
                "conversation.jsonl",
                "--json",
            ],
        )

        prompt_hook_status = facade.resolve_command(
            ["hooks", "prompt", "status", "--last", "--json"]
        )
        self.assertEqual(prompt_hook_status.command, "hooks")
        self.assertEqual(
            prompt_hook_status.module_name,
            "aippocampus_runtime.hooks.install_prompt",
        )
        self.assertEqual(
            prompt_hook_status.script_name,
            "install_aippocampus_prompt_hook.py",
        )
        self.assertEqual(prompt_hook_status.args, ["status", "--last", "--json"])

        claude_hook_status = facade.resolve_command(
            ["hooks", "claude-code", "status", "--json"]
        )
        self.assertEqual(claude_hook_status.command, "hooks")
        self.assertEqual(
            claude_hook_status.module_name,
            "aippocampus_runtime.hooks.claude_code",
        )
        self.assertEqual(
            claude_hook_status.script_name,
            "aippocampus_claude_code_hooks.py",
        )
        self.assertEqual(claude_hook_status.args, ["status", "--json"])

        log_rotation = facade.resolve_command(["logs", "rotate", "--json"])
        self.assertEqual(log_rotation.command, "logs")
        self.assertEqual(
            log_rotation.module_name,
            "aippocampus_runtime.ops.log_retention",
        )
        self.assertEqual(log_rotation.script_name, "log_retention.py")
        self.assertEqual(log_rotation.args, ["rotate", "--json"])

        self_note_append = facade.resolve_command(
            ["self-note", "append", "--current-thread", "--stdin", "--json"]
        )
        self.assertEqual(self_note_append.command, "self-note")
        self.assertEqual(
            self_note_append.module_name,
            "aippocampus_runtime.source.agent_self_note_cli",
        )
        self.assertEqual(self_note_append.script_name, "agent_self_note_cli.py")
        self.assertEqual(
            self_note_append.args,
            ["append", "--current-thread", "--stdin", "--json"],
        )

        continuity_domain_append = facade.resolve_command(
            ["continuity-domain", "append", "--event-json", "{}", "--json"]
        )
        self.assertEqual(continuity_domain_append.command, "continuity-domain")
        self.assertEqual(
            continuity_domain_append.module_name,
            "aippocampus_runtime.recall.continuity_domain_cli",
        )
        self.assertEqual(continuity_domain_append.script_name, "continuity_domain.py")
        self.assertEqual(
            continuity_domain_append.args,
            ["append", "--event-json", "{}", "--json"],
        )

        telepathy_list = facade.resolve_command(["telepathy", "list", "--json"])
        self.assertEqual(telepathy_list.command, "telepathy")
        self.assertEqual(
            telepathy_list.module_name,
            "aippocampus_runtime.ops.telepathy_handoff_store",
        )
        self.assertEqual(telepathy_list.script_name, "telepathy_handoff_store.py")
        self.assertEqual(telepathy_list.args, ["list", "--json"])

        continuity_domain_produce = facade.resolve_command(
            ["continuity-domain", "produce", "--dry-run", "--json"]
        )
        self.assertEqual(continuity_domain_produce.command, "continuity-domain")
        self.assertEqual(
            continuity_domain_produce.module_name,
            "aippocampus_runtime.recall.continuity_domain_cli",
        )
        self.assertEqual(continuity_domain_produce.script_name, "continuity_domain.py")
        self.assertEqual(continuity_domain_produce.args, ["produce", "--dry-run", "--json"])

    def test_self_note_current_thread_append_round_trips_as_atmosphere(self) -> None:
        note = "future posture: move decisively, but keep source boundary explicit."
        raw_thread_id = "codex-raw-thread-id-should-not-escape"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {
                **os.environ,
                "AIPPOCAMPUS_REGISTRY_DIR": str(root / "registry"),
                "CODEX_THREAD_ID": raw_thread_id,
            }
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "self-note",
                    "append",
                    "--current-thread",
                    "--cwd",
                    str(root),
                    "--stdin",
                    "--json",
                ],
                cwd=SCRIPTS,
                input=note,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                env=env,
            )

        raw = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, raw)
        payload = json.loads(proc.stdout)
        preview = payload["round_trip_preview"]
        atmosphere = preview["memory_atmosphere"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["kind"], "aippocampus_agent_self_note_append")
        self.assertTrue(payload["source_ref_attached"])
        self.assertEqual(preview["decision"], "context")
        self.assertEqual(preview["surface_counts"]["agent_self_notes"], 1)
        self.assertEqual(atmosphere[0]["action_grammar"], "direction_only")
        self.assertFalse(atmosphere[0]["trust_contract"]["treat_as_fact"])
        self.assertFalse(atmosphere[0]["claims_user_fact"])
        self.assertFalse(atmosphere[0]["claims_source_fact"])
        self.assertTrue(atmosphere[0]["source_reopen_required_before_claim"])
        self.assertNotIn(raw_thread_id, raw)
        self.assertNotIn(str(root), raw)
        self.assertNotIn("raw prompt", raw.casefold())

    def test_self_note_current_thread_long_append_returns_compact_projection_only(self) -> None:
        note = (
            "opening posture: be bold about the observed magic, "
            + "but keep the source boundary explicit and atmosphere-only; " * 14
            + "hidden tail marker should stay private."
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {**os.environ, "AIPPOCAMPUS_REGISTRY_DIR": str(root / "registry")}
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "self-note",
                    "append",
                    "--current-thread",
                    "--cwd",
                    str(root),
                    "--stdin",
                    "--json",
                ],
                cwd=SCRIPTS,
                input=note,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                env=env,
            )

        raw = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, raw)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertLessEqual(len(payload["note"]["note_text"]), 280)
        self.assertTrue(payload["note"]["note_body_private_available"])
        self.assertFalse(payload["note"]["note_body_private_default_visible"])
        self.assertNotIn("note_body_private\":", raw)
        self.assertNotIn("hidden tail marker should stay private", raw)

    def test_self_note_current_thread_append_rejects_raw_payload_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {**os.environ, "AIPPOCAMPUS_REGISTRY_DIR": str(root / "registry")}
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "aippocampus_runtime.cli.facade",
                    "self-note",
                    "append",
                    "--current-thread",
                    "--cwd",
                    str(root),
                    "--stdin",
                    "--json",
                ],
                cwd=SCRIPTS,
                input="tool_result stdout stderr should not become a margin note",
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                env=env,
            )

        raw = proc.stdout + proc.stderr
        self.assertNotEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "agent_self_note_raw_payload_rejected")
        self.assertNotIn(str(root), raw)

    def test_onboard_status_text_points_to_first_recall_modes(self) -> None:
        from aippocampus_runtime.onboarding import facade as onboard_facade

        report = {
            "ok": True,
            "data": {
                "providers": [
                    {
                        "provider": "codex",
                        "state": "write_enabled",
                        "detected": True,
                        "transcript_count": 2,
                        "current_cwd_match": False,
                        "blockers": [],
                    }
                ],
                "auto": {"default_provider": "codex", "why": "safe default"},
                "storage": {"path": "C:/private/aippocampus/registry", "source": "AIPPOCAMPUS_HOME"},
            },
        }

        output = onboard_facade.render_status_text(report)

        self.assertIn("First recall", output)
        self.assertIn("exact phrase", output)
        self.assertIn("project cue", output)
        self.assertIn("time cue", output)
        self.assertIn("aippocampus search", output)
        self.assertIn("registry configured", output)
        self.assertNotIn("C:/private/aippocampus/registry", output)

    def test_onboard_status_default_is_frontstage_text_not_json_inventory(self) -> None:
        from aippocampus_runtime.onboarding import facade as onboard_facade

        report = {
            "ok": True,
            "data": {
                "provider_scope": "auto",
                "providers": [
                    {
                        "provider": "codex",
                        "state": "write_enabled",
                        "detected": True,
                        "transcript_count": 3,
                        "transcript_count_label": "3+",
                        "scan_status": "partial_frontstage_sample",
                        "current_cwd_match": False,
                        "blockers": [],
                    }
                ],
                "auto": {"default_provider": "codex", "why": "safe default"},
                "storage": {"path": "C:/private/aippocampus/registry", "source": "AIPPOCAMPUS_HOME"},
            },
        }

        with (
            patch.object(onboard_facade, "provider_status_report", return_value=report),
            patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = onboard_facade.main(["--provider", "auto", "--status"])

        output = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("AIppocampus provider status", output)
        self.assertIn("partial frontstage sample", output)
        self.assertNotIn('"providers"', output)
        self.assertNotIn("C:/private/aippocampus/registry", output)

    def test_onboard_status_frontstage_samples_provider_inventory(self) -> None:
        from aippocampus_runtime.onboarding import facade as onboard_facade

        class FakeProvider:
            def discover_sessions(self):
                for index in range(10):
                    yield types.SimpleNamespace(session_id=f"s{index}")

        with patch.object(
            onboard_facade,
            "create_conversation_provider",
            return_value=FakeProvider(),
        ):
            report = onboard_facade.provider_status_report(provider="codex", detailed=False)

        provider = report["data"]["providers"][0]
        self.assertTrue(provider["detected"])
        self.assertEqual(provider["transcript_count"], 3)
        self.assertEqual(provider["transcript_count_label"], "3+")
        self.assertEqual(provider["scan_status"], "partial_frontstage_sample")

    def test_package_facade_default_runner_is_in_process(self) -> None:
        from aippocampus_runtime.cli import facade

        with (
            patch("subprocess.run", side_effect=AssertionError("facade should not spawn")),
            patch("sys.stdout", new=StringIO()) as stdout,
        ):
            code = facade.main(["mcp", "list-tools"])

        self.assertEqual(code, 0)
        tools = json.loads(stdout.getvalue())["tools"]
        self.assertTrue(any(tool["name"] == "search_memory" for tool in tools))

    def test_package_facade_exposes_captureable_python_api(self) -> None:
        from aippocampus_runtime.cli import facade

        with (
            patch("subprocess.run", side_effect=AssertionError("facade should not spawn")),
            patch("sys.stdout", new=StringIO()) as ambient_stdout,
            patch("sys.stderr", new=StringIO()) as ambient_stderr,
        ):
            result = facade.run_command(["mcp", "list-tools"], capture_output=True)

        self.assertTrue(result.ok)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.invocation.command, "mcp")
        tools = json.loads(result.stdout)["tools"]
        self.assertTrue(any(tool["name"] == "search_memory" for tool in tools))
        self.assertEqual(result.stderr, "")
        self.assertEqual(ambient_stdout.getvalue(), "")
        self.assertEqual(ambient_stderr.getvalue(), "")

    def test_package_facade_prefers_argv_aware_main_without_sys_argv_shim(self) -> None:
        from aippocampus_runtime.cli import facade

        module_name = "tests._fake_facade_argv_main"
        fake_module = types.ModuleType(module_name)
        seen: dict[str, object] = {}

        def main(argv: list[str] | None = None) -> int:
            seen["argv"] = list(argv or [])
            seen["sys_argv"] = list(sys.argv)
            return 7

        fake_module.main = main  # type: ignore[attr-defined]
        old_module = sys.modules.get(module_name)
        old_argv = sys.argv[:]
        sys.modules[module_name] = fake_module
        sys.argv = ["outer-host", "--keep"]
        try:
            code = facade.run_module_main(module_name, "fake_child.py", ["--flag", "value"])
        finally:
            sys.argv = old_argv
            if old_module is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = old_module

        self.assertEqual(code, 7)
        self.assertEqual(seen["argv"], ["--flag", "value"])
        self.assertEqual(seen["sys_argv"], ["outer-host", "--keep"])

    def test_package_facade_public_bundle_and_sync_commands_are_argv_aware(self) -> None:
        from aippocampus_runtime.artifacts import export_bundle, import_bundle
        from aippocampus_runtime.cli import facade
        from aippocampus_runtime.sync import bundle
        from aippocampus_runtime.sync.object_storage import cli as object_storage_cli

        self.assertTrue(facade.main_accepts_argv(export_bundle.main))
        self.assertTrue(facade.main_accepts_argv(import_bundle.main))
        self.assertTrue(facade.main_accepts_argv(bundle.main))
        self.assertTrue(facade.main_accepts_argv(object_storage_cli.main))

    def test_package_facade_capture_api_handles_usage_and_unknown_commands(self) -> None:
        from aippocampus_runtime.cli import facade

        help_result = facade.run_command(["--help"], capture_output=True)
        unknown_result = facade.run_command(["nope"], capture_output=True)

        self.assertTrue(help_result.ok)
        self.assertIn("Commands:", help_result.stdout)
        self.assertIsNone(help_result.invocation)
        self.assertFalse(unknown_result.ok)
        self.assertEqual(unknown_result.exit_code, 2)
        self.assertIn("unknown command: nope", unknown_result.stderr)
        self.assertIn("Commands:", unknown_result.stderr)

    def test_mcp_list_tools_preserves_json_stdout(self) -> None:
        proc = self.run_cli("mcp", "list-tools")

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        tools = json.loads(proc.stdout)["tools"]
        self.assertTrue(any(tool["name"] == "search_memory" for tool in tools))

    def test_first_run_command_aliases_are_copy_pasteable(self) -> None:
        from aippocampus_runtime.cli import facade
        from aippocampus_runtime.mcp import server as mcp_server

        plugin_status = facade.resolve_command(["plugin", "status", "--json"])
        maintenance = facade.resolve_command(["maintenance", "--json"])

        self.assertEqual(plugin_status.module_name, "aippocampus_runtime.update.cli")
        self.assertEqual(plugin_status.args, ["status", "--json"])
        self.assertEqual(maintenance.module_name, "aippocampus_runtime.ops.maintenance")

        with patch("sys.stdout", new=StringIO()) as stdout:
            code = mcp_server.main(["list-tools"])
        self.assertEqual(code, 0)
        tools = json.loads(stdout.getvalue())["tools"]
        self.assertTrue(any(tool["name"] == "memory_health" for tool in tools))

    def test_sync_status_without_sync_dir_matches_mcp_capability_truth(self) -> None:
        proc = self.run_cli("sync", "status", "--json")

        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["status"], "available_requires_sync_dir")
        self.assertEqual(data["backend"], "local_folder")
        self.assertIn("push", data["commands"])

    def test_sync_status_without_sync_dir_human_output_is_not_configured_ok(self) -> None:
        proc = self.run_cli("sync", "status")

        self.assertEqual(proc.returncode, 0)
        self.assertIn("capability available; no sync folder selected", proc.stdout)
        self.assertIn("next: aippocampus sync status --sync-dir <folder> --json", proc.stdout)
        self.assertNotIn("sync status: ok", proc.stdout)

    def test_sync_status_preserves_child_exit_code_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.run_cli("sync", "status", "--sync-dir", tmp, "--json")

        self.assertEqual(proc.returncode, 1)
        data = json.loads(proc.stdout)
        self.assertFalse(data["ok"])
        self.assertFalse(data["manifest_exists"])


if __name__ == "__main__":
    unittest.main()
